import test from 'node:test';
import { checkDatabase } from '../src/doctor.mjs';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { createDatabase } from '../src/db.mjs';
import { AuthService,appleId } from '../src/auth.mjs';
import { PartnerService } from '../src/partners.mjs';
import { AccountService } from '../src/accounts.mjs';
import { PaymentService } from '../src/payments.mjs';
import { Platform } from '../src/platform.mjs';
import { hash, PromoService } from '../src/service.mjs';
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
 const pool=createDatabase();t.after(()=>pool.end());assert.deepEqual(await checkDatabase(pool),[]);const mail=[];const auth=new AuthService(pool,{mail:async value=>mail.push(value)});
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
 // A service user receives a stable invitation code before linking any Apple ID.
 const partnerBefore=await (await call('/v3/partner',undefined,stranger.token)).json();
 assert.match(partnerBefore.partner.referral_code,/^RVP-[A-F0-9]{12}$/);
 assert.equal((await (await call('/v3/partner',undefined,stranger.token)).json()).partner.referral_code,partnerBefore.partner.referral_code);
 assert.equal((await call('/v3/partner',undefined,'')).status,401);
 const ownPartner=await (await call('/v3/partner')).json();
 assert.equal((await call('/v2/partner/bind',{account_id:aid,referral_code:ownPartner.partner.referral_code})).status,409);

 assert.equal((await call('/v2/account/balance',{account_id:aid},'')).status,401);
 assert.equal((await call('/v2/account/balance',{account_id:other})).status,403);
 assert.equal((await call('/v2/account/balance',{account_id:aid})).status,200);
 assert.equal((await call('/v3/admin/snapshot')).status,403);
 assert.equal((await call('/v1/redeem',{code:'FORGED',installation_token:'a'.repeat(64),request_id:id()},'')).status,410);
 assert.equal((await call('/v2/account/balance',{account_id:aid},owner.token,{Origin:'https://evil.example'})).status,403);
 const inviter='de'.repeat(32);const profile=await partners.profile({account_id:inviter});await partners.bind({account_id:aid,referral_code:profile.referral_code});
 await pool.execute("INSERT INTO apprevive_settings(name,value) VALUES ('commission_policy',?) ON DUPLICATE KEY UPDATE value=VALUES(value)",[JSON.stringify({rate:1000,days:0})]);
 const purchase={quantity:2,request_id:id()};
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
 assert((await (await call('/v3/orders')).json()).codes.every(c=>c.activation_status==='invalidated'));
 await payments.webhook({event:'payment.succeeded',object:{id:row.provider_id}});assert.equal((await payments.row(created.checkout_id)).state,'refunded');
 // Website registration attributes a real user before an Apple ID exists.
 const invitation=partnerBefore.partner.referral_code;
 const newEmail='registered-referral@example.test';
 const badEmail='invalid-referral@example.test';
 assert.equal((await call('/v3/auth/register',{email:badEmail,password:pass,referral_code:'RVP-000000000000'},'')).status,422);
 const [notCreated]=await pool.execute('SELECT user_id FROM apprevive_users WHERE email=?',[badEmail]);assert.equal(notCreated.length,0);
 assert.equal((await call('/v3/auth/register',{email:newEmail,password:pass,referral_code:invitation},'')).status,200);
 const loginResponse=await call('/v3/auth/login',{email:newEmail,password:pass},'');assert.match(loginResponse.headers.get('set-cookie'),/HttpOnly/);
 const referred=await loginResponse.json();const referredSession=await auth.session({headers:{authorization:'Bearer '+referred.token}});
 let partnerStats=await (await call('/v3/partner',undefined,stranger.token)).json();
 assert.equal(partnerStats.partner.registered,1);assert.equal(partnerStats.partner.registrations[0].paid_orders,0);
 assert.equal((await (await call('/v3/me',undefined,referred.token)).json()).invited_by,invitation);
 // Website buyer has no Apple ID at all; the server selects a service buyer ID.
 const [linkedBefore]=await pool.execute('SELECT account_id FROM apprevive_user_accounts WHERE user_id=?',[referred.user.user_id]);assert.equal(linkedBefore.length,0);
 const referralCheckout=await (await call('/v3/checkout',{quantity:2,request_id:id(),account_id:aid},referred.token)).json();
 const referralRow=await payments.row(referralCheckout.checkout_id);assert.notEqual(referralRow.account_id,aid);assert.equal(referralRow.amount_kopecks,20000);const referralPayment=provider.payments.get(referralRow.provider_id);
 referralPayment.status='succeeded';referralPayment.paid=true;
 await Promise.all([payments.sync(referralCheckout.checkout_id,referred.user),payments.sync(referralCheckout.checkout_id,referred.user)]);
 partnerStats=await (await call('/v3/partner',undefined,stranger.token)).json();
 assert.equal(partnerStats.partner.registered,1);assert.equal(partnerStats.partner.invited,1);assert.equal(partnerStats.partner.purchased_codes,2);
 assert.equal(partnerStats.partner.paid_buyers,1);assert.equal(partnerStats.ledger.available_kopecks,2000);
 assert.equal(partnerStats.partner.registrations[0].purchased_codes,2);
 const bought=await (await call('/v3/orders',undefined,referred.token)).json();assert.equal(bought.codes.length,2);assert(bought.codes.every(c=>c.activation_status==='unused'));
 const deliveredCode=bought.codes[0].code;
 // A different executor activates the bearer code in the native app, on their verified Apple ID.
 assert.equal((await call('/v2/account/redeem',{account_id:aid,code:deliveredCode,request_id:id()})).status,200);
 const activated=await (await call('/v3/orders',undefined,referred.token)).json();
 assert.equal(activated.codes.find(c=>c.code===deliveredCode).activation_status,'activated');
 assert(activated.codes.find(c=>c.code===deliveredCode).activated_at);
 assert.equal(activated.codes.filter(c=>c.activation_status==='unused').length,1);
 const filtered=await (await call('/v3/shop/orders?size=1&activation=activated',undefined,referred.token)).json();
 assert.equal(filtered.orders.length,1);assert.equal(filtered.codes.length,1);assert.equal(filtered.codes[0].code,deliveredCode);
 assert.equal(filtered.stats.activated,1);assert.equal(filtered.stats.unused,1);
 const untouched=await (await call('/v3/shop/orders?activation=unused',undefined,referred.token)).json();assert.equal(untouched.codes.length,1);assert.equal(untouched.codes[0].activation_status,'unused');
 const privateShop=await (await call('/v3/shop/orders',undefined,stranger.token)).json();assert.equal(privateShop.total,0);assert.equal(privateShop.codes.length,0);
 assert.equal((await call('/v3/shop/orders?page=-1',undefined,referred.token)).status,400);

 const [linkedAfter]=await pool.execute('SELECT account_id FROM apprevive_user_accounts WHERE user_id=?',[referred.user.user_id]);assert.equal(linkedAfter.length,0);
 assert(!(await (await call('/v3/orders',undefined,stranger.token)).json()).codes.some(c=>c.code===deliveredCode));

 await payments.refund(referralCheckout.checkout_id);
 partnerStats=await (await call('/v3/partner',undefined,stranger.token)).json();
 assert.equal(partnerStats.partner.registered,1);assert.equal(partnerStats.partner.purchased_codes,0);assert.equal(partnerStats.ledger.available_kopecks,0);
 // Site history reaches beyond the native API's original 100-order window.
 const extra=[];for(let i=0;i<101;i++)extra.push(id(),referred.user.user_id,referralRow.account_id,id(),1,10000);
 await pool.execute('INSERT INTO apprevive_checkouts(checkout_id,user_id,account_id,request_id,quantity,amount_kopecks) VALUES '+Array(101).fill('(?,?,?,?,?,?)').join(','),extra);
 const lastPage=await (await call('/v3/shop/orders?page=6&size=20',undefined,referred.token)).json();assert.equal(lastPage.total,102);assert.equal(lastPage.pages,6);assert.equal(lastPage.orders.length,2);
 // User-scoped session control: another user's session cannot be revoked.
 const second=await auth.login({email:stranger.user.email,password:pass});
 let sessions=await (await call('/v3/security/sessions',undefined,stranger.token)).json();
 assert(sessions.sessions.some(s=>s.current));assert(sessions.sessions.some(s=>!s.current));
 assert(!JSON.stringify(sessions).includes(stranger.token));
 await call('/v3/security/revoke',{session_id:hash(owner.token)},stranger.token);
 await auth.session({headers:{authorization:'Bearer '+owner.token}});
 await call('/v3/security/revoke',{others:true},stranger.token);
 await assert.rejects(auth.session({headers:{authorization:'Bearer '+second.token}}),e=>e.status===401);
 const third=await auth.login({email:stranger.user.email,password:pass});
 assert.equal((await call('/v3/security/password',{current_password:'incorrect',new_password:'A replacement service password'},stranger.token)).status,403);
 assert.equal((await call('/v3/security/password',{current_password:pass,new_password:'A replacement service password'},stranger.token)).status,200);
 await auth.session({headers:{authorization:'Bearer '+stranger.token}});
 await assert.rejects(auth.session({headers:{authorization:'Bearer '+third.token}}),e=>e.status===401);
 await assert.rejects(auth.login({email:stranger.user.email,password:pass}),e=>e.status===401);
 await auth.login({email:stranger.user.email,password:'A replacement service password'});
 assert.equal((await call('/v3/admin/users?page=1&size=1',undefined,stranger.token)).status,403);
 await pool.execute("UPDATE apprevive_users SET role='admin' WHERE user_id=?",[owner.user.user_id]);
 const listed=await (await call('/v3/admin/users?page=1&size=1&q=platform-')).json();
 assert.equal(listed.rows.length,1);assert.equal(listed.total,2);assert.equal(listed.pages,2);
 const secondPage=await (await call('/v3/admin/users?page=2&size=1&q=platform-')).json();assert.notEqual(secondPage.rows[0].user_id,listed.rows[0].user_id);
 const injection=await (await call('/v3/admin/users?q='+encodeURIComponent("%' OR 1=1 --"))).json();assert.equal(injection.total,0);
 assert.equal((await call('/v3/admin/orders?page=-1')).status,400);
 const metrics=await (await call('/v3/admin/metrics')).json();assert(metrics.users>=3);assert.equal(typeof metrics.revenue_kopecks,'number');
 // Password reset revokes existing sessions.
 await auth.requestReset({email:owner.user.email});await auth.consume({token:mail.at(-1).token,password:'A changed service password'});
 await assert.rejects(auth.session({headers:{authorization:'Bearer '+owner.token}}),e=>e.status===401);
});
