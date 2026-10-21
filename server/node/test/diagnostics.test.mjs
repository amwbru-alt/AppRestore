import test from 'node:test';
import assert from 'node:assert/strict';
import { createApi } from '../src/http.mjs';
import { failureKind } from '../src/diagnostics.mjs';
import { checkDatabase, expectedSchema } from '../src/doctor.mjs';

test('website failures distinguish schema problems with safe correlated diagnostics',async t=>{
 const logs=[],secret='SQL password=secret email@example.test';
 const server=createApi({}, {requireHttps:false,platform:{route(){throw Object.assign(new Error(secret),{code:'ER_NO_SUCH_TABLE',sql:secret});}},reportError:entry=>logs.push(entry)});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>{server.close(resolve);server.closeAllConnections();}));
 const url='http://127.0.0.1:'+server.address().port;
 const response=await fetch(url+'/v3/auth/login?secret='+encodeURIComponent(secret)),data=await response.json();
 assert.equal(response.status,503);assert.equal(data.status,'database_schema_outdated');assert.match(data.request_id,/^[a-f0-9]{16}$/);assert.equal(response.headers.get('x-request-id'),data.request_id);
 assert.deepEqual(logs,[{event:'request_failed',request_id:data.request_id,kind:'database_schema_outdated'}]);assert(!JSON.stringify({data,logs}).includes(secret));
 const legacy=await fetch(url+'/v1/catalog');assert.deepEqual(await legacy.json(),{status:'unavailable'});
});
test('database doctor reads required tables and detects missing referral schema without writes',async()=>{
 const definitions=await expectedSchema();assert(definitions.length>20);
 for(const name of ['apprevive_users','apprevive_sessions','apprevive_user_referrals','apprevive_issued_codes'])assert(definitions.some(x=>x.table===name));
 assert(definitions.find(x=>x.table==='apprevive_users').columns.includes('password_hash'));
 const failures=await checkDatabase({query:async sql=>{assert.match(sql,/^SELECT .* LIMIT 0$/);if(sql.includes('`apprevive_user_referrals`'))throw {code:'ER_NO_SUCH_TABLE'};return [[]];}});
 assert.deepEqual(failures,[{table:'apprevive_user_referrals',kind:'database_schema_outdated'}]);
 assert.equal(failureKind({code:'ECONNREFUSED'}),'database_unavailable');assert.equal(failureKind({code:'ER_ACCESS_DENIED_ERROR'}),'database_configuration_error');assert.equal(failureKind({code:'secret'}),'unavailable');
});
