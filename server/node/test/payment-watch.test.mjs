import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {JSDOM} from 'jsdom';
const source=await readFile(new URL('../public/assets/payment-watch.js',import.meta.url),'utf8');
const id='a'.repeat(32),other='b'.repeat(32);
const settle=async()=>{for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));};
function setup(t,options={}){const dom=new JSDOM('',{runScripts:'outside-only'});t.after(()=>dom.window.close());const jobs=new Map();let next=0;dom.window.setTimeout=fn=>{jobs.set(++next,fn);return next;};dom.window.clearTimeout=id=>jobs.delete(id);dom.window.eval(source);const states=[],settled=[];const watch=dom.window.AppRevivePaymentWatch({request:async()=>({checkout_id:id,state:'pending'}),onChange:d=>states.push(d),onSettled:d=>settled.push(d),...options});return {watch,states,settled,jobs,async tick(){const [key,fn]=jobs.entries().next().value||[];if(fn){jobs.delete(key);await fn();await settle();}}};}
test('pending payment keeps checking and only server-paid status settles the order',async t=>{
 let n=0;const p=setup(t,{request:async()=>({checkout_id:id,state:++n===1?'pending':'paid'})});p.watch.start(id);await settle();assert.equal(p.states.at(-1).state,'pending');assert.equal(p.settled.length,0);await p.tick();assert.equal(p.states.at(-1).state,'paid');assert.equal(p.settled.length,1);assert.equal(p.jobs.size,0);
});
test('automatic checks are bounded and explicit retry resets the budget',async t=>{
 const p=setup(t,{maxAttempts:2});p.watch.start(id);await settle();await p.tick();assert.equal(p.states.at(-1).paused,true);assert.equal(p.jobs.size,0);p.watch.retry();await settle();assert.equal(p.states.at(-1).attempts,1);assert.equal(p.jobs.size,1);
});
test('old account or order response is ignored after stop or switching order',async t=>{
 let resolve;const p=setup(t,{request:()=>new Promise(r=>{resolve=r;})});p.watch.start(id);p.watch.stop();resolve({checkout_id:id,state:'paid'});await settle();assert.equal(p.settled.length,0);assert.equal(p.watch.currentId,'');assert.equal(p.jobs.size,0);
});
test('an inconsistent server response cannot mark a payment paid',async t=>{
 const p=setup(t,{request:async()=>({checkout_id:other,state:'paid'}),maxAttempts:1});p.watch.start(id);await settle();assert.equal(p.settled.length,0);assert.equal(p.states.at(-1).state,'error');assert(p.states.at(-1).paused);
});
test('hidden or offline page sends no request and unauthorized orders do not loop',async t=>{
 let calls=0,visible=false;const p=setup(t,{canPoll:()=>visible,request:async()=>{calls++;throw Object.assign(Error('forbidden'),{status:403});}});p.watch.start(id);await settle();assert.equal(calls,0);visible=true;await p.tick();assert.equal(calls,1);assert.equal(p.jobs.size,0);assert.equal(p.states.at(-1).paused,true);
});
test('switching orders ignores the previous in-flight paid response',async t=>{
 const pending=[];const p=setup(t,{request:()=>new Promise(resolve=>pending.push(resolve))});p.watch.start(id);p.watch.start(other);pending[0]({checkout_id:id,state:'paid'});await settle();assert.equal(p.settled.length,0);assert.equal(p.watch.currentId,other);pending[1]({checkout_id:other,state:'cancelled'});await settle();assert.equal(p.settled[0].state,'cancelled');assert.equal(p.jobs.size,0);
});
