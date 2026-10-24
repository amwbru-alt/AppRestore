import test from 'node:test';
import assert from 'node:assert/strict';
import { createDatabase } from '../src/db.mjs';
import { discover, reviewDiscovery } from '../src/discoveries.mjs';
import { createApi } from '../src/http.mjs';
import { Platform } from '../src/platform.mjs';
import { PromoService } from '../src/service.mjs';

test('real MySQL: discovery races, moderation, catalog isolation and public API permissions',{skip:process.env.APPREVIVE_TEST_MYSQL!=='1'},async t=>{
 if(!/^apprevive_test(?:_[a-z0-9]+)?$/.test(process.env.DB_NAME||''))throw Error('Isolated test database required');
 const pool=createDatabase();t.after(()=>pool.end());
 const ids=['998881111101','998881111102','998881111103'];
 for(const id of ids){await pool.execute('DELETE FROM apprevive_catalog_discoveries WHERE store_id=?',[id]);await pool.execute('DELETE FROM apprevive_app_catalog WHERE store_id=?',[id]);}
 const app={trackId:ids[0],bundleId:'test.discovery.bank',name:'Candidate bank',source:'apple_history'};
 const results=await Promise.all(Array.from({length:6},()=>discover(pool,{apps:[app]})));
 assert.equal(results.reduce((sum,r)=>sum+r.added,0),1);
 let [[row]]=await pool.execute('SELECT state,bundle_id FROM apprevive_catalog_discoveries WHERE store_id=?',[app.trackId]);assert.equal(row.state,'pending');assert.equal(row.bundle_id,app.bundleId);
 assert(!(await new PromoService(pool).catalog()).apps.some(a=>a.trackId===app.trackId));
 await reviewDiscovery(pool,{store_id:app.trackId,action:'approve',name:'Reviewed bank',icon_url:''});
 assert((await new PromoService(pool).catalog()).apps.some(a=>a.trackId===app.trackId&&a.name==='Reviewed bank'));
 await discover(pool,{apps:[{...app,name:'Malicious replacement'}]});
 [[row]]=await pool.execute('SELECT name FROM apprevive_app_catalog WHERE store_id=?',[app.trackId]);assert.equal(row.name,'Reviewed bank');
 await pool.execute('INSERT INTO apprevive_app_catalog(store_id,name,enabled) VALUES (?, ?, 0)',[ids[1],'Operator disabled app']);
 assert.equal((await discover(pool,{apps:[{...app,trackId:ids[1]}]})).added,0);
 await discover(pool,{apps:[{...app,trackId:ids[2]}]});await reviewDiscovery(pool,{store_id:ids[2],action:'reject'});
 assert.equal((await discover(pool,{apps:[{...app,trackId:ids[2]}]})).added,0);
 [[row]]=await pool.execute('SELECT state FROM apprevive_catalog_discoveries WHERE store_id=?',[ids[2]]);assert.equal(row.state,'rejected');
 const platform=new Platform(pool,{env:{DEV_ALLOW_INSECURE_AUTH:'true'}});
 const server=createApi(new PromoService(pool),{requireHttps:false,platform});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>{server.close(resolve);server.closeAllConnections();}));
 const url='http://127.0.0.1:'+server.address().port;
 const post=(path,body)=>fetch(url+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 assert.equal((await post('/v3/catalog/discover',{apps:[app]})).status,200);
 assert.equal((await fetch(url+'/v3/admin/discoveries')).status,401);
 assert.equal((await post('/v3/admin/discoveries/review',{store_id:ids[0],action:'reject'})).status,401);
 for(let n=0;n<9;n++)assert.equal((await post('/v3/catalog/discover',{apps:[app]})).status,200);
 assert.equal((await post('/v3/catalog/discover',{apps:[app]})).status,429);
});
