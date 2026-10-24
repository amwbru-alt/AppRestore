import test from 'node:test';
import assert from 'node:assert/strict';
import {referralCode,registerReferred} from '../src/user-referrals.mjs';
test('invitation codes normalize and reject malformed values',()=>{
 assert.equal(referralCode(' rvp-abcdef123456 '),'RVP-ABCDEF123456');assert.equal(referralCode(undefined),'');
 for(const value of ['bad',{},'RVP-123456ABCDEF\ninvalid'])assert.throws(()=>referralCode(value));
});
test('registration and invitation commit together; failures roll back the new user',async()=>{
 for(const mode of ['ok','unknown','write-failed']){
  const log=[];const db={beginTransaction:async()=>log.push('begin'),commit:async()=>log.push('commit'),rollback:async()=>log.push('rollback'),release:()=>log.push('release'),execute:async(sql)=>{
   if(sql.startsWith('SELECT'))return [mode==='unknown'?[]:[{account_id:'a'.repeat(64)}]];
   if(sql.includes('INSERT INTO apprevive_users'))log.push('user');
   if(sql.includes('INSERT INTO apprevive_user_referrals')){if(mode==='write-failed')throw Error('write failed');log.push('referral');}return [{}];
  }};
  const run=()=>registerReferred({getConnection:async()=>db},{id:'1'.repeat(32),email:'a@example.test',encoded:'scrypt hash',code:'RVP-ABCDEF123456'});
  if(mode==='ok'){await run();assert.deepEqual(log,['begin','user','referral','commit','release']);}
  else{await assert.rejects(run());assert(log.includes('rollback'));assert(!log.includes('commit'));if(mode==='unknown')assert(!log.includes('user'));}
 }
});
