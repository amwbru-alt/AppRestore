import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { createDatabase } from '../src/db.mjs';
import { AuthService,appleId } from '../src/auth.mjs';
import { PartnerService } from '../src/partners.mjs';
import { AccountService } from '../src/accounts.mjs';
import { PaymentService } from '../src/payments.mjs';
import { Platform } from '../src/platform.mjs';
import { PromoService } from '../src/service.mjs';
import { createApi } from '../src/http.mjs';
const id=()=>randomBytes(16).toString('hex');
class FakeProvider{
 configured=true;payments=new Map();refunds=new Map();creates=0;
 async create(row){this.creates++;const key='pay-'+row.checkout_id;let p=this.payments.get(key);if(!p){p={id:key,status:'pending',paid:false,amount:{currency:'RUB',value:(row.amount_kopecks/100).toFixed(2)},metadata:{checkout_id:row.checkout_id},confirmation:{confirmation_url:'https://yoomoney.ru/confirm/'+key}};this.payments.set(key,p);}return p;}
 async payment(key){return this.payments.get(key);}
 async refund(row){const r={id:'refund-'+row.checkout_id,status:'succeeded',payment_id:row.provider_id,amount:{currency:'RUB',value:(row.amount_kopecks/100).toFixed(2)}};this.refunds.set(r.id,r);return r;}
 async refundInfo(key){return this.refunds.get(key);}
}
test('production HTTP authorization, verified ownership, paid orders and payout ledger', {skip:process.env.APPREVIVE_TEST_MYSQL!=='1'},async t=>{
 if(!/^apprevive_test(?:_[a-z0-9]+)?$/.test(process.env.DB_NAME||''))throw Error('Isolated test database required');
 const pool=createDatabase();t.after(()=>pool.end());const mail=[];const auth=new AuthService(pool,{mail:async value=>mail.push(value)});
 const pass='A service password 2026';
 async function signup(email){const before=mail.length;assert.equal((await auth.register({email,password:pass})).status,'registered');assert.equal(mail.length,before);return auth.login({email,password:pass});}
 const owner=await signup('platform-owner@example.test'), stranger=await signup('platform-stranger@example.test');
 const ownerSession=await auth.session({headers:{authorization:'Bearer '+owner.token}});
 const aid=appleId(owner.user.email),other=appleId(stranger.user.email);
 // Entering an email during password-only signup must not claim its existing Apple balance.
 await assert.rejects(auth.requireAccount(ownerSession,aid),e=>e.status===403);
 await auth.requestApple(ownerSession,{email:owner.user.email});await auth.consume({token:mail.at(-1).token},ownerSession);
 await auth.requireAccount(ownerSession,aid);
 await assert.rejects(auth.requireAccount(ownerSession,other),e=>e.status===403);
 // A different Apple ID requires a token sent to that mailbox and the requesting service user.
 await auth.requestApple(ownerSession,{email:'platform-apple@example.test'});const link=mail.at(-1).token;
 await assert.rejects(auth.consume({token:link},stranger.user),e=>e.status===401);
 await auth.consume({token:link},ownerSession);await auth.requireAccount(ownerSession,appleId('platform-apple@example.test'));
 await assert.rejects(auth.consume({token:link},ownerSession),e=>e.status===422);
 const partners=new PartnerService(pool);const accounts=new AccountService(pool);const provider=new FakeProvider();const payments=new PaymentService(pool,partners,provider);
 const platform=new Platform(pool,{auth,accounts,partners,payments,env:{DEV_ALLOW_INSECURE_AUTH:'true',PUBLIC_URL:'https://apprevive.example'}});
 const server=createApi(new PromoService(pool),{requireHttps:false,platform,accounts,partners});await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>{server.close(r);server.closeAllConnections();}));const base='http://127.0.0.1:'+server.address().port;
 const call=(path,body,token=owner.token,extra={})=>fetch(base+path,{method:body===undefined?'GET':'POST',headers:{...(body===undefined?{}:{'Content-Type':'application/json'}),...(token?{Authorization:'Bearer '+token}:{}),...extra},...(body===undefined?{}:{body:JSON.stringify(body)})});
 assert.equal((await call('/v2/account/balance',{account_id:aid},'')).status,401);
 assert.equal((await call('/v2/account/balance',{account_id:other})).status,403);
 assert.equal((await call('/v2/account/balance',{account_id:aid})).status,200);
 assert.equal((await call('/v3/admin/snapshot')).status,403);
 assert.equal((await call('/v1/redeem',{code:'FORGED',installation_token:'a'.repeat(64),request_id:id()},'')).status,410);
 assert.equal((await call('/v2/account/balance',{account_id:aid},owner.token,{Origin:'https://evil.example'})).status,403);
 const inviter='de'.repeat(32);const profile=await partners.profile({account_id:inviter});await partners.bind({account_id:aid,referral_code:profile.referral_code});
 await pool.execute("INSERT INTO apprevive_settings(name,value) VALUES ('commission_policy',?) ON DUPLICATE KEY UPDATE value=VALUES(value)",[JSON.stringify({rate:1000,days:0})]);
 const purchase={account_id:aid,quantity:2,request_id:id()};
 let response=await call('/v3/checkout',purchase);assert.equal(response.status,200);const created=await response.json();assert.match(created.confirmation_url,/yoomoney/);
 const row=await payments.row(created.checkout_id);
 // A forged webhook says succeeded, but provider still says pending: issue no codes.
 await payments.webhook({event:'payment.succeeded',object:{id:row.provider_id,status:'succeeded',paid:true}});
 let [orders]=await pool.execute('SELECT * FROM apprevive_orders WHERE payment_reference=?',['yk_'+row.provider_id]);assert.equal(orders.length,0);
 const payment=provider.payments.get(row.provider_id);payment.status='succeeded';payment.paid=true;
 await Promise.all([payments.webhook({event:'payment.succeeded',object:{id:row.provider_id}}),payments.sync(created.checkout_id,owner.user)]);
 [orders]=await pool.execute('SELECT * FROM apprevive_orders WHERE payment_reference=?',['yk_'+row.provider_id]);assert.equal(orders.length,1);
 const issued=await (await call('/v3/orders')).json();assert.equal(issued.codes.length,2);
 const strangerOrders=await (await call('/v3/orders',undefined,stranger.token)).json();assert.equal(strangerOrders.codes.length,0);
 const ledger=await platform.payouts.balance(inviter);assert.equal(ledger.available_kopecks,2000);
 const payout={partner_id:inviter,amount_kopecks:1500,reference:'payout-'+id()};
 const out=await platform.payouts.create(payout);assert.equal((await platform.payouts.balance(inviter)).available_kopecks,500);
 await assert.rejects(platform.payouts.create({...payout,reference:'other-'+id(),amount_kopecks:1000}),e=>e.status===409);
 await platform.payouts.finish({payout_id:out.payout_id,state:'paid'});await platform.payouts.finish({payout_id:out.payout_id,state:'paid'});
 assert.equal((await platform.payouts.balance(inviter)).paid_kopecks,1500);
 await payments.refund(created.checkout_id);assert.equal((await platform.payouts.balance(inviter)).available_kopecks,-1500);
 assert.equal((await (await call('/v3/orders')).json()).codes.length,0);
 await payments.webhook({event:'payment.succeeded',object:{id:row.provider_id}});assert.equal((await payments.row(created.checkout_id)).state,'refunded');
 // Password reset revokes existing sessions.
 await auth.requestReset({email:owner.user.email});await auth.consume({token:mail.at(-1).token,password:'A changed service password'});
 await assert.rejects(auth.session({headers:{authorization:'Bearer '+owner.token}}),e=>e.status===401);
});
