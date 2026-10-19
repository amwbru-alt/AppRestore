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
