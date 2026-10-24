import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeEmail,passwordHash,verifyPassword } from '../src/auth.mjs';
test('passwords are salted, checked with scrypt, and never stored in plaintext',async()=>{
 const a=await passwordHash('A long service password'),b=await passwordHash('A long service password');
 assert.notEqual(a,b);assert(!a.includes('A long'));assert(await verifyPassword('A long service password',a));assert(!await verifyPassword('wrong',a));
 await assert.rejects(passwordHash('short'));assert.equal(normalizeEmail(' PERSON@Example.com '),'person@example.com');assert.throws(()=>normalizeEmail('bad\r\nvalue@example.com'));
});

import { commissionPolicy } from '../src/ledger.mjs';
import { Platform } from '../src/platform.mjs';
test('zero-day commission hold stays zero and proxy TLS cannot be forged remotely',()=>{
 assert.deepEqual(commissionPolicy({PARTNER_COMMISSION_BPS:1000,PARTNER_HOLD_DAYS:0}),{rate:1000,days:0});
 const p=Object.create(Platform.prototype);p.env={PUBLIC_URL:'https://apprevive.example'};
 assert.throws(()=>p.secure({method:'POST',headers:{'x-forwarded-proto':'https'},socket:{remoteAddress:'203.0.113.5'}}),e=>e.status===426);
 assert.doesNotThrow(()=>p.secure({method:'POST',headers:{'x-forwarded-proto':'https',origin:'https://apprevive.example'},socket:{remoteAddress:'127.0.0.1'}}));
 assert.throws(()=>p.secure({method:'POST',headers:{origin:'https://evil.example'},socket:{encrypted:true}}),e=>e.status===403);
});

import { AuthService } from '../src/auth.mjs';
test('password-only signup needs no mail and never marks the mailbox verified',async()=>{
 const writes=[];const auth=new AuthService({execute:async(sql,args)=>{writes.push({sql,args});return sql.startsWith('SELECT')?[[]]:[{affectedRows:1}];}},{mail:async()=>assert.fail('Registration must not send mail')});
 assert.equal((await auth.register({email:'new@example.test',password:'A service test password'})).status,'registered');
 assert(writes.some(w=>w.sql.startsWith('INSERT INTO apprevive_users')));
 assert(!writes.some(w=>/email_tokens|verified=1|user_accounts/.test(w.sql)));
});
test('signup cannot replace an existing password, including previously pending users',async()=>{
 const writes=[];const auth=new AuthService({execute:async sql=>{writes.push(sql);return [[{user_id:'existing',verified:0}]];}},{mail:async()=>assert.fail('No signup mail')});
 await assert.rejects(auth.register({email:'pending@example.test',password:'A service test password'}),e=>e.code==='account_exists');
 assert(!writes.some(sql=>/INSERT|UPDATE/.test(sql)));
});
test('unverified service users may log in but cannot auto-claim an Apple ID balance',async()=>{
 const encoded=await passwordHash('A service test password');let linked=false;
 const auth=new AuthService({execute:async(sql,args)=>{
  if(sql.includes('password_hash'))return [[{user_id:'new',email:'new@example.test',password_hash:encoded,verified:0,role:'user'}]];
  if(sql.startsWith('INSERT INTO apprevive_sessions'))return [{affectedRows:1}];
  if(sql.startsWith('INSERT IGNORE INTO apprevive_user_accounts'))linked=true;
  return [[]];
 }});
 const result=await auth.login({email:'new@example.test',password:'A service test password'});assert.equal(result.status,'ok');assert.equal(linked,false);
 await assert.rejects(auth.requireAccount({user_id:'new',email:'new@example.test',verified:0},'0'.repeat(64)),e=>e.status===403);assert.equal(linked,false);
});

test('service partner identity is stable, preserves legacy codes and releases transaction locks',async()=>{
 for(const legacy of [false,true]){
  let mapping,commits=0,released=0;
  const db={beginTransaction:async()=>{},commit:async()=>commits++,rollback:async()=>assert.fail('Unexpected rollback'),release:()=>released++,execute:async(sql,args)=>{
   if(sql.includes('SELECT partner_id'))return [mapping?[{partner_id:mapping}]:[]];
   if(sql.includes('JOIN apprevive_user_accounts'))return [legacy?[{account_id:'a'.repeat(64)}]:[]];
   if(sql.startsWith('INSERT INTO apprevive_user_partners'))mapping=args[1];
   return [[]];
  }};
  const auth=new AuthService({getConnection:async()=>db});const user={user_id:'1'.repeat(32)};
  const first=await auth.partnerAccount(user);assert.match(first,/^[a-f0-9]{64}$/);
  assert.equal(await auth.partnerAccount(user),first);if(legacy)assert.equal(first,'a'.repeat(64));
  assert.equal(commits,2);assert.equal(released,2);
 }
});
