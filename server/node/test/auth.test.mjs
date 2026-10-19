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
test('registration retries send a fresh verification link without replacing the pending password',async()=>{
 const writes=[],mail=[];
 const pool={execute:async(sql,args)=>{writes.push(sql);return sql.startsWith('SELECT')?[[{user_id:'test-user',verified:0}]]:[{affectedRows:1}];}};
 const auth=new AuthService(pool,{mail:async data=>mail.push(data)});
 assert.equal((await auth.register({email:'pending@example.test',password:'A service test password'})).status,'email_sent');
 assert.equal(mail.length,1);assert.equal(mail[0].purpose,'verify');
 assert(!writes.some(sql=>/UPDATE apprevive_users|INSERT INTO apprevive_users/.test(sql)));
});
