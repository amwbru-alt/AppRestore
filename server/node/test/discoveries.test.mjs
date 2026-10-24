import test from 'node:test';
import assert from 'node:assert/strict';
import { discoveryInput, discover, reviewDiscovery } from '../src/discoveries.mjs';
const app={trackId:'12345678',bundleId:'bank.old',name:'Bank',source:'apple_history'};
test('discovery input accepts only exact IDs in bounded batches',()=>{
 assert.deepEqual(discoveryInput({apps:[app,app]}),[app]);
 for(const apps of [[],Array(51).fill(app),[{...app,trackId:'random'}],[{...app,bundleId:'bad'}],[{...app,name:'Bad\nname'}],[{...app,source:'verified'}]])assert.throws(()=>discoveryInput({apps}),e=>e.status===400);
 assert.deepEqual(Object.keys(discoveryInput({apps:[{...app,email:'private',udid:'private'}]})[0]).sort(),Object.keys(app).sort());
});
test('repeated discoveries do not overwrite existing catalog or review decisions',async()=>{
 const seen=new Set(),calls=[];
 const pool={execute:async(sql,params)=>{calls.push({sql,params});const added=seen.has(params[0])?0:1;seen.add(params[0]);return [{affectedRows:added}];}};
 assert.equal((await discover(pool,{apps:[app]})).added,1);
 assert.equal((await discover(pool,{apps:[{...app,name:'Spoofed'}]})).added,0);
 assert.match(calls[0].sql,/INSERT IGNORE/);assert.match(calls[0].sql,/NOT EXISTS.*apprevive_app_catalog/);
 assert(!calls[0].sql.includes('UPDATE'));assert.equal(calls[0].params.length,5);
});
test('review requires explicit admin-validated metadata and rolls back on write failure',async()=>{
 await assert.rejects(reviewDiscovery({}, {store_id:app.trackId,action:'approve',name:'Bank',icon_url:'http://bad.test/icon'}),e=>e.status===400);
 const events=[];
 const db={beginTransaction:async()=>events.push('begin'),execute:async sql=>{if(sql.startsWith('SELECT'))return [[{state:'pending'}]];throw Error('write failed');},rollback:async()=>events.push('rollback'),commit:async()=>events.push('commit'),release:()=>events.push('release')};
 await assert.rejects(reviewDiscovery({getConnection:async()=>db},{store_id:app.trackId,action:'approve',name:'Bank',icon_url:''}));
 assert.deepEqual(events,['begin','rollback','release']);
});
