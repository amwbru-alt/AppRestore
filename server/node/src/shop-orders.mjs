import { ApiError } from './service.mjs';
import { pageInput } from './admin-data.mjs';
const activation="CASE WHEN r.code_hash IS NOT NULL THEN 'activated' WHEN o.state='refunded' THEN 'invalidated' WHEN p.code IS NOT NULL THEN 'unused' ELSE 'unavailable' END";
const source="apprevive_checkouts c JOIN apprevive_orders o ON o.payment_reference=CONCAT('yk_',c.provider_id) JOIN apprevive_order_codes oc ON oc.order_id=o.order_id LEFT JOIN apprevive_issued_codes v ON v.code_hash=oc.code_hash LEFT JOIN apprevive_promo_codes p ON SHA2(p.code,256)=oc.code_hash LEFT JOIN apprevive_promo_redemptions r ON r.code_hash=oc.code_hash";
export async function shopOrders(pool,user,query){
 const {page,size,search}=pageInput(query),state=query.get('state')||'',filter=query.get('activation')||'';
 if(state&&!['pending','paid','cancelled','refunded'].includes(state)||filter&&!['unused','activated','invalidated','unavailable'].includes(filter))throw new ApiError(400,'invalid_filter');
 const where=['c.user_id=?'],params=[user.user_id];
 if(state){where.push('c.state=?');params.push(state);}
 if(search){where.push('LOCATE(?,c.checkout_id)>0');params.push(search);}
 if(filter){where.push('EXISTS (SELECT 1 FROM '+source.replace('apprevive_checkouts c ', 'apprevive_checkouts inner_c ').replace('c.provider_id','inner_c.provider_id')+" WHERE inner_c.checkout_id=c.checkout_id AND "+activation+'=?)');params.push(filter);}
 const condition=where.join(' AND ');
 const [count]=await pool.execute('SELECT COUNT(*) AS total FROM apprevive_checkouts c WHERE '+condition,params);
 const total=Number(count[0].total),pages=Math.max(1,Math.ceil(total/size)),current=Math.min(page,pages);
 const [orders]=await pool.execute('SELECT c.checkout_id,c.quantity,c.amount_kopecks,c.state,c.created_at FROM apprevive_checkouts c WHERE '+condition+` ORDER BY c.created_at DESC,c.checkout_id LIMIT ${size} OFFSET ${(current-1)*size}`,params);
 let codes=[];
 if(orders.length){
  const args=[user.user_id,...orders.map(o=>o.checkout_id)];
  const sql='SELECT c.checkout_id,oc.code_hash,COALESCE(v.code,p.code) AS code,r.activated_at,'+activation+' AS activation_status FROM '+source+' WHERE c.user_id=? AND c.checkout_id IN ('+orders.map(()=>'?').join(',')+") AND c.state IN ('paid','refunded')"+(filter?' AND '+activation+'=?':'');
  if(filter)args.push(filter);
  const [rows]=await pool.execute(sql,args);
  codes=rows.map(row=>({checkout_id:row.checkout_id,code:row.code?Buffer.from(row.code).toString():null,code_id:row.code_hash.slice(0,12),activation_status:row.activation_status,activated_at:row.activated_at}));
 }
 const [stats]=await pool.execute("SELECT COUNT(*) AS total,COALESCE(SUM(s.activation_status='unused'),0) AS unused,COALESCE(SUM(s.activation_status='activated'),0) AS activated,COALESCE(SUM(s.activation_status='invalidated'),0) AS invalidated,COALESCE(SUM(s.activation_status='unavailable'),0) AS unavailable FROM (SELECT "+activation+' AS activation_status FROM '+source+" WHERE c.user_id=? AND c.state IN ('paid','refunded')) s",[user.user_id]);
 return {status:'ok',orders,codes,page:current,size,pages,total,stats:Object.fromEntries(Object.entries(stats[0]).map(([key,value])=>[key,Number(value)]))};
}
