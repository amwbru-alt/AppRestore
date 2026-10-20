import test from 'node:test';
import assert from 'node:assert/strict';
import {shopOrders} from '../src/shop-orders.mjs';
test('shop history binds owner, limits code loading to the page and validates filters',async()=>{
 const calls=[];const pool={execute:async(sql,params)=>{calls.push({sql,params});
  if(sql.startsWith('SELECT COUNT(*) AS total FROM apprevive_checkouts'))return [[{total:41}]];
  if(sql.startsWith('SELECT c.checkout_id,c.quantity'))return [[{checkout_id:'c'.repeat(32)}]];
  if(sql.startsWith('SELECT c.checkout_id,oc.code_hash'))return [[{checkout_id:'c'.repeat(32),code_hash:'a'.repeat(64),code:Buffer.from('RV-TEST'),activation_status:'unused'}]];
  return [[{total:5,unused:3,activated:2,invalidated:0,unavailable:0}]];
 }};
 const data=await shopOrders(pool,{user_id:'owner'},new URLSearchParams({page:'2',size:'20',activation:'unused',q:"x' OR 1=1"}));
 assert.equal(data.page,2);assert.equal(data.pages,3);assert.equal(data.codes[0].code,'RV-TEST');assert.equal(data.stats.unused,3);
 assert(calls[0].sql.includes('inner_c.checkout_id=c.checkout_id'));assert(calls[0].sql.includes('oc.order_id'));
 assert(!calls[0].sql.includes("x' OR"));assert.equal(calls[0].params[0],'owner');
 assert(calls[1].sql.endsWith('LIMIT 20 OFFSET 20'));
 assert(calls[2].sql.includes('c.checkout_id IN (?)'));assert.deepEqual(calls[2].params,['owner','c'.repeat(32),'unused']);
 await assert.rejects(shopOrders(pool,{user_id:'owner'},new URLSearchParams({activation:'anything'})),e=>e.status===400);
});
