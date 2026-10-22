import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {JSDOM,VirtualConsole} from 'jsdom';
const root=new URL('../public/',import.meta.url),origin='http://185.173.93.200:3000';
const aid='a'.repeat(64);
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));};
async function page(t,name='account',{allowed=true,logged=false,role='user',hash='',override={}}={}){
 const errors=[],calls=[];let authenticated=logged;
 const dom=new JSDOM(await readFile(new URL(name+'.html',root),'utf8'),{url:origin+'/'+name+hash,runScripts:'outside-only',virtualConsole:new VirtualConsole().on('jsdomError',e=>errors.push(e.message))});
 t.after(()=>dom.window.close());const w=dom.window;
 const endpoints={
  '/site-config':{transport:{http_auth_origin:allowed?origin:''}},
  '/v3/me':logged?{user:{email:'unit@example.test',role},accounts:[{account_id:aid,email:'unit@example.test'}]}:{status:'service_login_required'},
  ['/v3/account?account_id='+aid]:{credits:1,installations:0,history:[],partner:{referral_code:'RVP-ABCDEF123456',invited:0,paid_buyers:0,purchased_codes:0,revenue_kopecks:0},ledger:{available_kopecks:0,held_kopecks:0,paid_kopecks:0,pending_kopecks:0},payouts:[]},
  '/v3/partner':{partner:{account_id:aid,referral_code:'RVP-ABCDEF123456',invited:0,paid_buyers:0,paid_orders:0,purchased_codes:0,revenue_kopecks:0},ledger:{available_kopecks:0,held_kopecks:0,paid_kopecks:0,pending_kopecks:0},payouts:[]},
  '/v3/security/sessions':{sessions:[]},
  '/v3/admin/users?page=1&size=25':{rows:[],page:1,pages:1,total:0},
  '/v3/orders':{orders:[],codes:[]},'/v3/status':{payments_enabled:false,commission_policy:{rate:0,days:14}},
  '/v3/admin/groups':{groups:[]},'/v3/admin/snapshot':{users:[],orders:[],restorations:[],payouts:[],commissions:[],checkouts:[],audit:[]}
 };
 w.confirm=()=>true;w.fetch=async(path,options={})=>{
  calls.push({path,body:options.body?JSON.parse(options.body):null});
  if(path.startsWith('/v3/shop/orders?')){
   const mock=override['/v3/orders'];const response=mock?await mock(options,w):{ok:true,status:200,json:async()=>endpoints['/v3/orders']};
   return {...response,json:async()=>({page:1,pages:1,total:0,stats:{total:0,unused:0,activated:0,invalidated:0},...await response.json()})};
  }
  if(override[path])return override[path](options,w);
  if(path==='/v3/auth/login')authenticated=true;
  if(path.startsWith('/v3/admin/users?')||path.startsWith('/v3/admin/orders?'))return {ok:true,status:200,json:async()=>({rows:[],page:1,pages:1,total:0})};
  if(path==='/v3/admin/metrics')return {ok:true,status:200,json:async()=>({users:0,registered_referrals:0,paid_orders:0,revenue_kopecks:0,codes:0,pending_restorations:0,updated_at:new Date().toISOString()})};
  const data=path==='/v3/me'&&authenticated?{user:{email:'unit@example.test',role},accounts:logged?[{account_id:aid,email:'unit@example.test'}]:[]}:endpoints[path]||{status:'ok',unused_codes:['RV-UNIT-ONLY']};
  const status=path==='/v3/me'&&!authenticated?401:200;
  return {ok:status<400,status,json:async()=>data};
 };
 for(const file of ['transport','portal',name])w.eval(await readFile(new URL('assets/'+file+'.js',root),'utf8'));
 await settle();
 return {w,calls,errors,notice:()=>w.document.getElementById('message').querySelector('span')?.textContent||'',form:id=>w.document.getElementById(id)};
}
function fill(form,values){for(const [name,value] of Object.entries(values)){const field=form.elements.namedItem(name);if(field.type==='checkbox')field.checked=value;else field.value=value;}}
async function submit(form){form.querySelector('button').click();await settle();}
test('blocked HTTP registration stays explainable and never transmits credentials',async t=>{
 const p=await page(t,'account',{allowed:false});
 assert(!p.form('register-form').querySelector('button').disabled);
 fill(p.form('register-form'),{email:'unit@example.test',password:'A unit service password'});await submit(p.form('register-form'));
 assert.match(p.notice(),/заблокированы настройками сервера/);
 assert(!p.calls.some(c=>c.path.startsWith('/v3/auth/')));assert.deepEqual(p.errors,[]);
});
test('registration validates input and sends exactly one request on configured HTTP',async t=>{
 const p=await page(t);const form=p.form('register-form');
 fill(form,{email:'invalid',password:'short'});await submit(form);assert.match(p.notice(),/Проверьте поля/);assert(!p.calls.some(c=>c.path==='/v3/auth/register'));
 fill(form,{email:'unit@example.test',password:'A unit service password'});await submit(form);
 assert.equal(p.calls.filter(c=>c.path==='/v3/auth/register').length,1);assert.match(p.notice(),/Аккаунт создан/i);assert(!form.querySelector('button').disabled);assert.equal(form.elements.password.value,'');assert.deepEqual(p.errors,[]);
});
test('registration exposes sender failure and malformed API responses',async t=>{
 const p=await page(t,'account',{override:{'/v3/auth/register':async()=>({ok:false,status:503,json:async()=>({status:'mail_not_configured'})})}});
 fill(p.form('register-form'),{email:'unit@example.test',password:'A unit service password'});await submit(p.form('register-form'));assert.match(p.notice(),/Отправка писем пока не настроена/);
 const q=await page(t,'account',{override:{'/v3/auth/register':async()=>({ok:false,status:502,json:async()=>{throw Error('HTML instead of JSON');}})}});
 fill(q.form('register-form'),{email:'unit@example.test',password:'A unit service password'});await submit(q.form('register-form'));assert.match(q.notice(),/некорректный ответ/);
});
test('busy registration prevents duplicate requests and returns controls after completion',async t=>{
 let finish;const p=await page(t,'account',{override:{'/v3/auth/register':()=>new Promise(r=>{finish=r;})}});
 const f=p.form('register-form');fill(f,{email:'unit@example.test',password:'A unit service password'});await submit(f);
 assert(f.querySelector('button').disabled);assert.match(p.notice(),/Выполняем/);
 f.dispatchEvent(new p.w.Event('submit',{bubbles:true,cancelable:true}));await settle();assert.equal(p.calls.filter(c=>c.path==='/v3/auth/register').length,1);
 finish({ok:true,status:200,json:async()=>({status:'email_sent'})});await settle();assert(!f.querySelector('button').disabled);
});
test('login, reset and resend handlers submit their own form data',async t=>{
 const p=await page(t);
 fill(p.form('login-form'),{email:'unit@example.test',password:'A unit service password'});await submit(p.form('login-form'));
 fill(p.form('reset-form'),{email:'unit@example.test'});await submit(p.form('reset-form'));p.w.document.getElementById('resend').click();await settle();
 for(const path of ['/v3/auth/login','/v3/auth/reset','/v3/auth/resend'])assert.equal(p.calls.find(c=>c.path===path)?.body.email,'unit@example.test');
 assert.deepEqual(p.errors,[]);
});
test('cabinet checkout needs no Apple ID and refresh works on HTTP',async t=>{
 const p=await page(t,'account',{logged:true});
 assert(!p.form('cabinet').hidden);assert.equal(p.form('apple-form'),null);assert.equal(p.form('redeem-form'),null);
 fill(p.form('buy-form'),{quantity:'1'});await submit(p.form('buy-form'));
 const purchase=p.calls.find(c=>c.path==='/v3/checkout');assert.match(purchase.body.request_id,/^[a-f0-9]{32}$/);assert.equal(purchase.body.account_id,undefined);
 p.form('refresh').click();await settle();assert.equal(p.notice(),'Готово.');assert.deepEqual(p.errors,[]);
});
test('admin catalog, groups, manual purchase, refund, policy and payouts handlers work',async t=>{
 const p=await page(t,'admin',{logged:true,role:'admin'});
 assert(!p.form('admin').hidden);
 const cases=[
  ['group-form',{id:'unit-bank',name:'Unit Bank',iconUrl:'',apps:'123456789; Unit App; '},'/v3/admin/groups'],
  ['catalog-form',{store_id:'123456789',name:'Unit App',icon_url:'',enabled:true},'/v3/admin/catalog'],
  ['manual-form',{buyer_id:aid,quantity:'1',amount_kopecks:'10000',payment_reference:'unit-test-only',confirmed:true},'/v3/admin/purchase'],
  ['manual-refund-form',{payment_reference:'unit-test-only',confirmed:true},'/v3/admin/manual-refund'],
  ['policy-form',{percent:'10',days:'0'},'/v3/admin/policy'],
  ['payout-form',{partner_id:aid,amount_kopecks:'1000',reference:'unit-payout-only'},'/v3/admin/payout/create']
 ];
 for(const [id,values,path]of cases){fill(p.form(id),values);await submit(p.form(id));assert(p.calls.some(c=>c.path===path),path+' '+p.notice());}
 assert.deepEqual(p.errors,[]);
});


test('network timeout shows an error and makes registration retryable',async t=>{
 const p=await page(t,'account',{override:{'/v3/auth/register':(options,w)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new w.DOMException('Aborted','AbortError'))))}});
 const timer=p.w.setTimeout.bind(p.w);p.w.setTimeout=(fn,ms,...args)=>timer(fn,ms===20000?0:ms,...args);
 const form=p.form('register-form');fill(form,{email:'unit@example.test',password:'A unit service password'});await submit(form);await new Promise(r=>setTimeout(r,10));
 assert.match(p.notice(),/не ответил за 20 секунд/);assert(!form.querySelector('button').disabled);assert.equal(form.dataset.busy,undefined);
});


test('email verification, password reset confirmation and logout have working handlers',async t=>{
 for(const purpose of ['verify','reset','apple']){
  const token='c'.repeat(64);const p=await page(t,'account',{logged:purpose==='apple',hash:'#token='+token+'&purpose='+purpose});
  assert(!p.form('verify').hidden);if(purpose!=='apple')p.w.document.getElementById('new-password').value='A unit replacement password';
  await submit(p.form('verify-form'));const call=p.calls.find(c=>c.path==='/v3/auth/consume');assert.equal(call?.body.token,token);assert(p.form('verify').hidden);
 }
 const p=await page(t,'account',{logged:true});p.w.document.getElementById('logout').click();await settle();assert(p.calls.some(c=>c.path==='/v3/auth/logout'));assert(p.form('cabinet').hidden);assert(!p.form('auth').hidden);
});

test('landing catalog filtering, internal anchors, downloads and referral copy fallback work',async t=>{
 const errors=[];const dom=new JSDOM(await readFile(new URL('index.html',root),'utf8'),{url:origin+'/?ref=RVP-ABCDEF123456',runScripts:'outside-only',virtualConsole:new VirtualConsole().on('jsdomError',e=>errors.push(e.message))});t.after(()=>dom.window.close());const w=dom.window;
 w.fetch=async path=>({ok:true,json:async()=>path==='/v1/catalog'?{status:'ok',apps:[{name:'Unit Bank',trackId:'123456789'},{name:'Unit Other',trackId:'234567890'}]}:path==='/site-config'?{downloads:{macos:false,windows:true}}:{payments_enabled:false,commission_policy:{rate:0}}});
 w.eval(await readFile(new URL('assets/site.js',root),'utf8'));await settle();
 assert.equal(w.document.querySelectorAll('.app-card').length,2);const field=w.document.getElementById('app-search');field.value='Bank';field.dispatchEvent(new w.Event('input'));assert.equal(w.document.querySelectorAll('.app-card').length,1);
 assert.match(w.document.getElementById('mac-status').textContent,/ещё не опубликован/);assert.match(w.document.getElementById('windows-status').textContent,/готов/);
 w.document.getElementById('copy-referral').click();await settle();assert.match(w.document.getElementById('copy-status').textContent,/вручную/);
 for(const link of w.document.querySelectorAll('a[href^="#"]')){const id=link.getAttribute('href').slice(1);if(id)assert(w.document.getElementById(id),'Missing anchor '+id);}
 assert.deepEqual(errors,[]);
});

test('partner code is available without a linked Apple ID and invitation links survive login',async t=>{
 const p=await page(t,'account',{logged:true,hash:'?ref=RVP-123456ABCDEF',override:{'/v3/me':async()=>({ok:true,status:200,json:async()=>({user:{email:'partner@example.test',role:'user'},accounts:[]})})}});
 assert.match(p.form('partner').textContent,/RVP-ABCDEF123456/);
 assert.match(p.form('partner').querySelector('input').value,/\/register\?ref=RVP-ABCDEF123456/);
 assert.equal(p.form('register-form').elements.referral_code.value,'RVP-123456ABCDEF');
 assert(!p.calls.some(c=>c.path.startsWith('/v3/account?')));
 assert.equal(p.errors.length,0);
});
test('notices expire, may be dismissed, and old timers are cancelled',async t=>{
 const p=await page(t);const timers=new Map();let next=0;
 p.w.setTimeout=(fn,delay)=>{timers.set(++next,{fn,delay});return next;};p.w.clearTimeout=id=>timers.delete(id);
 p.w.AppRevivePortal.notice('First');p.w.AppRevivePortal.notice('Second');
 assert.equal(timers.size,1);assert.equal([...timers.values()][0].delay,5500);
 [...timers.values()][0].fn();assert(p.form('message').hidden);
 p.w.AppRevivePortal.notice('Error',true);assert.equal(p.form('message').dataset.kind,'error');
 p.form('message').querySelector('button').click();assert(p.form('message').hidden);assert.equal(p.notice(),'');
});

test('registration sends invitation, logs in and opens the cabinet immediately',async t=>{
 const p=await page(t,'account',{hash:'?ref=RVP-123456ABCDEF#register-form'});
 fill(p.form('register-form'),{email:'new@example.test',password:'A unit service password'});
 await submit(p.form('register-form'));
 assert.equal(p.calls.find(c=>c.path==='/v3/auth/register').body.referral_code,'RVP-123456ABCDEF');
 assert.equal(p.calls.filter(c=>c.path==='/v3/auth/login').length,1);
 assert.equal(p.w.location.hash,'#cabinet');assert(!p.form('cabinet').hidden);
 assert.match(p.form('partner').textContent,/RVP-ABCDEF123456/);
});
test('a failed orders panel never hides the partner code',async t=>{
 const p=await page(t,'account',{logged:true,override:{'/v3/orders':async()=>({ok:false,status:503,json:async()=>({status:'unavailable'})})}});
 assert.match(p.form('partner').textContent,/RVP-ABCDEF123456/);
 assert.match(p.form('orders').textContent,/Не удалось загрузить/);
 assert.match(p.notice(),/Некоторые разделы/);
});

test('security controls submit credentials only to password endpoint and allow session revocation',async t=>{
 const p=await page(t,'account',{logged:true});
 fill(p.form('password-form'),{current_password:'Old service password',new_password:'A new service password'});await submit(p.form('password-form'));
 assert.equal(p.calls.find(c=>c.path==='/v3/security/password').body.current_password,'Old service password');
 assert.equal(p.form('password-form').elements.current_password.value,'');
 p.form('revoke-others').click();await settle();assert.equal(p.calls.find(c=>c.path==='/v3/security/revoke').body.others,true);
 p.w.dispatchEvent(new p.w.CustomEvent('apprevive:expired'));assert(p.form('cabinet').hidden);assert(!p.form('auth').hidden);
});
test('admin searches the full server dataset and CSV neutralizes spreadsheet formulas',async t=>{
 const p=await page(t,'admin',{logged:true,role:'admin'});
 fill(p.form('users-search'),{q:'name@example.test',state:'user'});await submit(p.form('users-search'));
 assert(p.calls.some(c=>c.path.includes('admin/users?q=name%40example.test&state=user&page=1')));
 assert.match(p.form('users-pagination').textContent,/найдено 0/);
 const csv=p.w.AppRevivePortal.csv([['=HYPERLINK("x")','normal',' +SUM(1,2)']]);
 assert(csv.includes("\"'=HYPERLINK"));assert(csv.includes("\"' +SUM"));assert(csv.startsWith('\uFEFF'));
});

test('visible cabinet refreshes data and pauses in background or offline',async t=>{
 const p=await page(t,'account',{logged:true});
 Object.defineProperty(p.w.document,'hidden',{configurable:true,value:false});
 let count=p.calls.filter(c=>c.path==='/v3/partner').length;p.w.dispatchEvent(new p.w.Event('online'));await settle();
 assert.equal(p.calls.filter(c=>c.path==='/v3/partner').length,count+1);
 count++;
 Object.defineProperty(p.w.document,'hidden',{configurable:true,value:true});p.w.dispatchEvent(new p.w.Event('online'));await settle();
 assert.equal(p.calls.filter(c=>c.path==='/v3/partner').length,count);
 Object.defineProperty(p.w.document,'hidden',{configurable:true,value:false});Object.defineProperty(p.w.navigator,'onLine',{configurable:true,value:false});p.w.dispatchEvent(new p.w.Event('online'));await settle();
 assert.equal(p.calls.filter(c=>c.path==='/v3/partner').length,count);
});

test('purchased codes remain visible with real unused and activated labels; site never links Apple ID',async t=>{
 const checkout='c'.repeat(32);
 const p=await page(t,'account',{logged:true,override:{'/v3/orders':async()=>({ok:true,status:200,json:async()=>({orders:[{checkout_id:checkout,quantity:2,amount_kopecks:20000,state:'paid'}],codes:[{checkout_id:checkout,code:'RV-UNUSED',activation_status:'unused'},{checkout_id:checkout,code:'RV-USED',activation_status:'activated',activated_at:'2026-10-19T20:00:00Z'}]})})}});
 assert.match(p.form('orders').textContent,/Не активирован/);assert.match(p.form('orders').textContent,/Активирован/);
 const values=[...p.form('orders').querySelectorAll('input')].map(input=>input.value);assert.deepEqual(values,['RV-UNUSED','RV-USED']);
 assert.equal(p.form('apple-form'),null);assert.equal(p.form('accounts'),null);
 assert(!p.calls.some(c=>c.path==='/v3/auth/apple'||c.path.startsWith('/v3/account?')));
});

test('shop filters use the site endpoint and reset returns to the first page',async t=>{
 const p=await page(t,'account',{logged:true});
 fill(p.form('shop-filter'),{state:'paid',activation:'unused',q:'abc'});await submit(p.form('shop-filter'));
 assert(p.calls.some(c=>c.path.startsWith('/v3/shop/orders?')&&c.path.includes('activation=unused')&&c.path.includes('state=paid')&&c.path.includes('page=1')));
 p.form('shop-reset').click();await settle();assert.equal(p.form('shop-filter').elements.activation.value,'');
 assert.match(p.form('shop-pagination').textContent,/Страница 1/);
 assert(!p.calls.some(c=>c.path==='/v3/orders'));
});

test('landing journeys, catalog expansion, calculator and mobile navigation respond to real controls',async t=>{
 const dom=new JSDOM(await readFile(new URL('index.html',root),'utf8'),{url:origin,runScripts:'outside-only'});t.after(()=>dom.window.close());const w=dom.window;
 w.fetch=async path=>({ok:true,json:async()=>path==='/v1/catalog'?{status:'ok',apps:Array.from({length:12},(_,i)=>({name:'Application '+i,trackId:String(123456789+i)}))}:path==='/site-config'?{downloads:{macos:true,windows:true}}:{payments_enabled:false}});
 w.eval(await readFile(new URL('assets/site.js',root),'utf8'));await settle();
 assert.equal(w.document.querySelectorAll('.app-card').length,8);w.document.getElementById('catalog-more').click();assert.equal(w.document.querySelectorAll('.app-card').length,12);assert(w.document.getElementById('catalog-more').hidden);
 w.document.querySelector('#catalog-suggestions button').click();assert.equal(w.document.getElementById('app-search').value,'Application 0');assert.equal(w.document.querySelectorAll('.app-card').length,1);
 w.document.getElementById('catalog-clear').click();assert.equal(w.document.getElementById('app-search').value,'');
 w.document.getElementById('journey-code').click();assert.equal(w.document.getElementById('journey-action').getAttribute('href'),'/account');assert.match(w.document.getElementById('journey-steps').textContent,/Apple ID на сайте не нужен/);
 w.document.getElementById('journey-code').dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));assert.equal(w.document.getElementById('journey-self').getAttribute('aria-selected'),'true');
 const quantity=w.document.getElementById('code-quantity');quantity.value='3';quantity.dispatchEvent(new w.Event('input'));assert.equal(w.document.getElementById('code-total').textContent,'300 ₽');assert.equal(w.document.getElementById('code-checkout').getAttribute('href'),'/account?quantity=3');
 quantity.value='101';quantity.dispatchEvent(new w.Event('input'));assert(!w.document.getElementById('code-checkout').hasAttribute('href'));
 const menu=w.document.getElementById('menu-toggle');menu.click();assert.equal(menu.getAttribute('aria-expanded'),'true');w.document.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));assert.equal(menu.getAttribute('aria-expanded'),'false');
});
test('catalog load failure exposes a working retry',async t=>{
 const dom=new JSDOM(await readFile(new URL('index.html',root),'utf8'),{url:origin,runScripts:'outside-only'});t.after(()=>dom.window.close());const w=dom.window;let attempts=0;
 w.fetch=async path=>{if(path==='/v1/catalog'&&++attempts===1)throw new TypeError('offline');return {ok:true,json:async()=>path==='/v1/catalog'?{status:'ok',apps:[{name:'Recovered application'}]}:{downloads:{}}};};
 w.eval(await readFile(new URL('assets/site.js',root),'utf8'));await settle();const retry=w.document.getElementById('catalog-retry');assert(!retry.hidden);retry.click();await settle();assert(retry.hidden);assert.equal(w.document.querySelectorAll('.app-card').length,1);
});
test('cabinet accepts a valid quantity from the landing calculator and ignores invalid values',async t=>{
 const valid=await page(t,'account',{hash:'?quantity=3'});assert.equal(valid.form('buy-form').elements.quantity.value,'3');
 const invalid=await page(t,'account',{hash:'?quantity=1000'});assert.equal(invalid.form('buy-form').elements.quantity.value,'1');
});
test('database errors show a support reference without pretending the password is wrong',async t=>{
 const p=await page(t,'account',{override:{'/v3/auth/login':async()=>({ok:false,status:503,json:async()=>({status:'database_schema_outdated',request_id:'abcdef0123456789'})})}});
 fill(p.form('login-form'),{email:'unit@example.test',password:'A unit service password'});await submit(p.form('login-form'));
 assert.match(p.notice(),/База сайта требует обновления/);assert.match(p.notice(),/abcdef0123456789/);assert(!p.form('login-form').querySelector('button').disabled);
});
test('registration reports account creation separately from subsequent cabinet failure',async t=>{
 const p=await page(t,'account',{override:{'/v3/me':async()=>({ok:false,status:503,json:async()=>({status:'database_schema_outdated',request_id:'1234567890abcdef'})})}});
 fill(p.form('register-form'),{email:'unit@example.test',password:'A unit service password'});await submit(p.form('register-form'));
 assert.match(p.notice(),/Аккаунт создан, вход выполнен/);assert.match(p.notice(),/Не регистрируйтесь повторно/);
 assert.equal(p.calls.filter(c=>c.path==='/v3/auth/register').length,1);
 assert(!p.form('register-form').querySelector('button').disabled);
});
test('admin reviews discovered apps with text-safe metadata and editable names',async t=>{
 const p=await page(t,'admin',{logged:true,role:'admin',override:{
  '/v3/admin/discoveries?page=1':async()=>({ok:true,status:200,json:async()=>({apps:[{store_id:'12345678',bundle_id:'bank.old',name:'<img src=x onerror=alert(1)>',source:'apple_history',created_at:'2026-10-22'}],total:1,page:1,pages:1})}),
  '/v3/admin/discoveries/review':async()=>({ok:true,status:200,json:async()=>({status:'ok'})})
 }});
 await settle();const area=p.w.document.getElementById('discoveries');assert(area.textContent.includes('<img'));assert(!area.querySelector('img'));
 const name=area.querySelector('input');name.value='Reviewed bank';const publish=[...area.querySelectorAll('button')].find(b=>b.textContent==='Опубликовать');assert(publish);publish.click();await settle();
 const call=p.calls.find(c=>c.path==='/v3/admin/discoveries/review');assert.equal(call.body.name,'Reviewed bank');assert.equal(call.body.action,'approve');assert.equal(call.body.store_id,'12345678');
});
