import { ApiError, safeIcon } from './service.mjs';
const storeId = value => typeof value==='string' && /^[1-9][0-9]{7,11}$/.test(value);
export function discoveryInput(body) {
  if(!body||!Array.isArray(body.apps)||!body.apps.length||body.apps.length>50)throw new ApiError(400,'invalid_discoveries');
  const seen=new Set(),apps=[];
  for(const app of body.apps){
    if(!app||!storeId(app.trackId)||typeof app.bundleId!=='string'||app.bundleId.length>255||! /^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/.test(app.bundleId)||typeof app.name!=='string'||!app.name.trim()||app.name.length>255||/[\x00-\x1f\x7f]/.test(app.name)||!['apple_history','device_offloaded'].includes(app.source))throw new ApiError(400,'invalid_discoveries');
    if(!seen.has(app.trackId)){seen.add(app.trackId);apps.push({trackId:app.trackId,bundleId:app.bundleId,name:app.name.trim(),source:app.source});}
  }
  return apps;
}
export async function discover(pool,body) {
  const apps=discoveryInput(body);let added=0;
  for(const app of apps){
    // Existing public/disabled entries and rejected candidates remain unchanged.
    const [result]=await pool.execute('INSERT IGNORE INTO apprevive_catalog_discoveries(store_id,bundle_id,name,source) SELECT ?,?,?,? FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM apprevive_app_catalog WHERE store_id=?)',[app.trackId,app.bundleId,app.name,app.source,app.trackId]);
    added+=result.affectedRows;
  }
  return {status:'ok',added};
}
export async function discoveries(pool,query) {
  const requested=query.get('page')||'1';if(!/^[1-9][0-9]{0,4}$/.test(requested))throw new ApiError(400,'invalid_page');
  const [[count]]=await pool.execute("SELECT COUNT(*) AS total FROM apprevive_catalog_discoveries WHERE state='pending'");
  const total=Number(count.total),pages=Math.max(1,Math.ceil(total/25)),page=Math.min(Number(requested),pages),offset=(page-1)*25;
  const [apps]=await pool.execute(`SELECT store_id,bundle_id,name,source,created_at FROM apprevive_catalog_discoveries WHERE state='pending' ORDER BY store_id LIMIT 25 OFFSET ${offset}`);
  return {status:'ok',apps,total,pages,page};
}
export async function reviewDiscovery(pool,body) {
  if(!storeId(body?.store_id)||!['approve','reject'].includes(body?.action))throw new ApiError(400,'invalid_discovery_review');
  if(body.action==='approve'&&(typeof body.name!=='string'||!body.name.trim()||body.name.length>255||/[\x00-\x1f\x7f]/.test(body.name)||typeof body.icon_url!=='string'||body.icon_url&&!safeIcon(body.icon_url)))throw new ApiError(400,'invalid_discovery_review');
  const db=await pool.getConnection();
  try{
    await db.beginTransaction();
    const [rows]=await db.execute('SELECT state FROM apprevive_catalog_discoveries WHERE store_id=? FOR UPDATE',[body.store_id]);
    if(!rows.length)throw new ApiError(404,'discovery_not_found');
    if(rows[0].state!=='pending'){await db.commit();return {status:'ok',state:rows[0].state};}
    if(body.action==='approve')await db.execute('INSERT IGNORE INTO apprevive_app_catalog(store_id,name,icon_url,enabled) VALUES (?,?,?,1)',[body.store_id,body.name.trim(),body.icon_url]);
    const state=body.action==='approve'?'approved':'rejected';
    await db.execute('UPDATE apprevive_catalog_discoveries SET state=?,reviewed_at=UTC_TIMESTAMP() WHERE store_id=?',[state,body.store_id]);
    await db.commit();return {status:'ok',state};
  }catch(error){await db.rollback();throw error;}finally{db.release();}
}
