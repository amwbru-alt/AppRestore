import test from 'node:test';
import assert from 'node:assert/strict';
import {pageInput,records} from '../src/admin-data.mjs';
test('pagination validates bounds and binds search text rather than interpreting SQL',async()=>{
 for(const query of ['page=-1','page=1.5','size=1000','q='+ 'x'.repeat(101)])assert.throws(()=>pageInput(new URLSearchParams(query)));
 const calls=[];const pool={execute:async(sql,params)=>{calls.push({sql,params});return sql.startsWith('SELECT COUNT')?[[{total:4}]]:[[{user_id:'one'}]];}};
 const result=await records(pool,'users',new URLSearchParams({page:'999',size:'2',q:"%' OR 1=1 --"}));
 assert.equal(result.page,2);assert.equal(result.pages,2);assert.equal(result.total,4);
 assert(calls[1].sql.endsWith('LIMIT 2 OFFSET 2'));assert(!calls[1].sql.includes("OR 1=1"));assert(calls[1].params.includes("%' OR 1=1 --"));
 await assert.rejects(records(pool,'orders',new URLSearchParams({state:'admin'})),e=>e.status===400);
});
