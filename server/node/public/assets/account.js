'use strict';
const $ = id => document.getElementById(id);
const message=AppRevivePortal.notice;
const api=AppRevivePortal.request;
const run=AppRevivePortal.run;
const plaintext=location.protocol!=='https:';
function transportState(allowed){
  // Keep controls clickable so a blocked deployment gives an explicit reason.
  for(const button of document.querySelectorAll('[data-secure]'))button.disabled=false;
  if(!allowed)message('Вход и регистрация по HTTP заблокированы настройками сервера. Администратор должен включить HTTP-режим и перезапустить сервис.');
  else if(plaintext)message('Временный режим HTTP: пароль AppRevive и сессия передаются без шифрования.');
  else message('Можно войти или зарегистрироваться.');
}
AppReviveTransport.ready.then(transportState);
$('connection-retry').onclick=run(async()=>{transportState(await AppReviveTransport.retry());});
function table(target, headings, rows){ const t=document.createElement('table'), head=document.createElement('tr');headings.forEach(x=>{const c=document.createElement('th');c.textContent=x;head.append(c);});t.append(head); for(const row of rows){const tr=document.createElement('tr');row.forEach(value=>{const td=document.createElement('td'); if(value instanceof Node)td.append(value);else td.textContent=String(value??'');tr.append(td);});t.append(tr);}$(target).replaceChildren(t); }
const status = value => ({pending:'Ожидает',paid:'Оплачен',cancelled:'Отменён',refunded:'Возвращён',completed:'Завершено',failed:'Ошибка, попытка возвращена',reserved:'Ожидает подтверждения'}[value]||value);
const rub = value => (Number(value)/100).toLocaleString('ru-RU',{style:'currency',currency:'RUB'});
function stats(target, items){$(target).replaceChildren(...items.map(([title,value])=>{const box=document.createElement('div');box.className='stat';const b=document.createElement('b'),s=document.createElement('span');b.textContent=value;s.textContent=title;box.append(b,s);return box;}));}
let profile=null, checkoutRequest=null;
function account(){const id=$('accounts').value;if(!id)throw Error('Сначала привяжите и подтвердите Apple ID.');return id;}
async function refreshAccount(){if(!$('accounts').value){stats('balance',[['Apple ID','Не привязан']]);table('history',['История восстановлений'],[['Привяжите Apple ID, чтобы увидеть баланс и восстановления.']]);return;}const data=await api('/v3/account?account_id='+account()); stats('balance',[['Осталось восстановлений',data.credits],['Успешных установок',data.installations]]); table('history',['Приложение','ID операции','Состояние','Дата'],data.history.map(r=>[r.name||r.store_id||'Восстановление',r.request_id,status(r.state),r.created_at]));}
async function refreshPartner(){
 const data=await api('/v3/partner'),p=data.partner;
 if(!p?.referral_code)throw Error('Не удалось получить код приглашения. Обновите сервер и выполните миграцию базы.');
 const box=$('partner');box.replaceChildren();
 const label=document.createElement('p');label.textContent='Ваш персональный код приглашения';
 const code=document.createElement('strong');code.className='referral-code';code.textContent=p.referral_code;
 const link=new URL('/register',location.origin);link.searchParams.set('ref',p.referral_code);
 const field=document.createElement('input');field.readOnly=true;field.value=link.href;field.setAttribute('aria-label','Ваша ссылка приглашения');
 const copyCode=document.createElement('button');copyCode.type='button';copyCode.className='button ghost';copyCode.textContent='Скопировать код';copyCode.onclick=run(async()=>{try{await navigator.clipboard.writeText(p.referral_code);message('Код скопирован.');}catch{field.value=p.referral_code;field.focus();field.select();message('Скопируйте выделенный код.');}});
 const copy=document.createElement('button');copy.type='button';copy.className='button primary';copy.textContent='Скопировать ссылку';copy.onclick=run(async()=>{try{await navigator.clipboard.writeText(field.value);message('Ссылка скопирована.');}catch{field.focus();field.select();message('Скопируйте выделенную ссылку.');}});
 const terms=document.createElement('p');terms.textContent=`Вознаграждение: ${Number(p.commission_rate_bps||0)/100}%. Удержание: ${p.hold_days||0} дней. ${p.commission_rate_bps?'Начисляем за подтверждённые покупки.':'Администратор ещё не установил процент вознаграждения.'} Возвраты исключаются из начислений.`;
 const identity=document.createElement('small');identity.textContent='ID партнёра для выплаты: '+p.account_id;
 box.append(label,code,field,copy,copyCode,terms,identity);
 stats('partner-stats',[['Зарегистрировано',p.registered??p.invited],['Всего приглашено',p.invited],['Купили коды',p.paid_buyers],['Оплаченных заказов',p.paid_orders||0],['Куплено кодов',p.purchased_codes],['Продажи',rub(p.revenue_kopecks)]]);
 table('referrals',['Реферал','Регистрация','Оплаченных заказов','Куплено кодов','Продажи','Начислено вам'],(p.registrations?.length?p.registrations:p.referrals||[]).map(r=>[r.buyer,r.created_at,r.paid_orders,r.purchased_codes,rub(r.revenue_kopecks),rub(r.commission_kopecks||0)]));
 const l=data.ledger;stats('ledger',[['Доступно к выплате',rub(l.available_kopecks)],['На удержании',rub(l.held_kopecks)],['Выплачено',rub(l.paid_kopecks)],['Зарезервировано',rub(l.pending_kopecks)]]);
 table('payouts',['Сумма','Состояние','Дата'],data.payouts.map(p=>[rub(p.amount_kopecks),status(p.state),p.created_at]));
}

async function refreshOrders(){const data=await api('/v3/orders');table('orders',['Заказ','Количество','Сумма','Состояние','Коды / действие'],data.orders.map(order=>{const cell=document.createElement('div'); for(const code of data.codes.filter(c=>c.checkout_id===order.checkout_id)){const p=document.createElement('p');p.textContent=code.code;cell.append(p);}if(order.state==='pending'){const b=document.createElement('button');b.className='button ghost';b.textContent='Проверить оплату';b.onclick=run(async()=>{const updated=await api('/v3/checkout/sync',{checkout_id:order.checkout_id});if(updated.confirmation_url){const a=document.createElement('a');a.href=updated.confirmation_url;a.textContent='Перейти к оплате ↗';a.className='button primary';cell.append(a);}else await refreshOrders();});cell.append(b);}return [order.checkout_id,order.quantity,rub(order.amount_kopecks),status(order.state),cell];}));}
async function refresh(){
 profile=await api('/v3/me');$('auth').hidden=true;$('cabinet').hidden=false;$('who').textContent=profile.user.email;
 $('ref-form').hidden=!!profile.invited_by;$('invited-by').textContent=profile.invited_by?'Вы зарегистрированы по приглашению '+profile.invited_by+'. Пригласивший закреплён.':'';
 const current=$('accounts').value;$('accounts').replaceChildren(...profile.accounts.map(a=>{const o=document.createElement('option');o.value=a.account_id;o.textContent=a.email;return o;}));
 if(profile.accounts.some(a=>a.account_id===current))$('accounts').value=current;
 const jobs=[['partner',refreshPartner],['balance',refreshAccount],['orders',refreshOrders],['payment-status',async()=>{const settings=await api('/v3/status');$('payment-status').textContent=settings.payments_enabled?'':'Онлайн-оплата пока не настроена.';}]];
 const results=await Promise.allSettled(jobs.map(async([id,load])=>{try{await load();}catch(error){$(id).textContent='Не удалось загрузить раздел: '+error.message;throw error;}}));
 const errors=results.filter(r=>r.status==='rejected');if(errors.length)message('Некоторые разделы не загрузились. Нажмите «Обновить». '+errors[0].reason.message,true);
}
function enterCabinet(){if(new URLSearchParams(location.search).get('next')==='admin'&&profile?.user.role==='admin'){location.assign('/admin');return;}history.replaceState(null,'','/account#cabinet');$('cabinet').scrollIntoView?.({block:'start'});}
$('login-form').onsubmit=run(async event=>{await api('/v3/auth/login',Object.fromEntries(new FormData(event.target)));event.target.reset();await refresh();enterCabinet();message('Вход выполнен.');});
$('register-form').onsubmit=run(async event=>{
 const details=Object.fromEntries(new FormData(event.target));await api('/v3/auth/register',details);
 try{await api('/v3/auth/login',{email:details.email,password:details.password});}catch(error){message('Аккаунт создан. Войдите с указанным паролем. '+error.message,true);return;}
 event.target.reset();try{localStorage.removeItem('apprevive_referral');}catch{}
 await refresh();enterCabinet();message('Добро пожаловать! Аккаунт создан'+(details.referral_code?' — пригласивший закреплён.':'.'));
});
$('reset-form').onsubmit=run(async event=>{await api('/v3/auth/reset',Object.fromEntries(new FormData(event.target)));message('Если аккаунт существует, письмо отправлено.');});
$('resend').onclick=run(async()=>{await api('/v3/auth/resend',{email:$('reset-form').elements.email.value});message('Если требуется подтверждение, письмо отправлено.');});
$('apple-form').onsubmit=run(async event=>{await api('/v3/auth/apple',Object.fromEntries(new FormData(event.target)));message('Откройте письмо на почте Apple ID. Для подтверждения войдите в этот же аккаунт AppRevive.');});
$('accounts').onchange=run(refreshAccount);$('refresh').onclick=run(refresh);
$('logout').onclick=run(async()=>{await api('/v3/auth/logout',{});profile=null;$('cabinet').hidden=true;$('auth').hidden=false;message('Вы вышли.');});
$('buy-form').onsubmit=run(async event=>{const quantity=Number(event.target.elements.quantity.value);if(!checkoutRequest||checkoutRequest.account_id!==account()||checkoutRequest.quantity!==quantity)checkoutRequest={account_id:account(),quantity,request_id:AppReviveTransport.requestId()};const data=await api('/v3/checkout',checkoutRequest);if(data.confirmation_url)location.assign(data.confirmation_url);else{checkoutRequest=null;message('Оплата подтверждена. Коды доступны в заказе.');await refreshOrders();}});
$('redeem-form').onsubmit=run(async event=>{await api('/v2/account/redeem',{account_id:account(),code:event.target.elements.code.value,request_id:AppReviveTransport.requestId()});event.target.reset();message('Код активирован.');await refreshAccount();});
$('register-form').elements.referral_code.addEventListener('input',event=>{event.target.value=event.target.value.toUpperCase();});
let storedReferral='';try{storedReferral=localStorage.getItem('apprevive_referral')||'';}catch{}
const invited=(new URLSearchParams(location.search).get('ref')||storedReferral).trim().toUpperCase();
if(invited&&/^RVP-[A-F0-9]{12}$/.test(invited)){
 try{localStorage.setItem('apprevive_referral',invited);}catch{}
 $('register-form').elements.referral_code.value=invited;$('ref-form').elements.referral_code.value=invited;
}
if(location.hash==='#register-form')$('register-form').elements.email.focus();
$('ref-form').onsubmit=run(async event=>{await api('/v2/partner/bind',{account_id:account(),referral_code:event.target.elements.referral_code.value});try{localStorage.removeItem('apprevive_referral');}catch{}message('Пригласивший закреплён.');await refreshPartner();});
const verification=new URLSearchParams(location.hash.slice(1));
if(verification.has('token')){$('verify').hidden=false;const purpose=verification.get('purpose');$('new-password-label').hidden=purpose==='apple';$('new-password').required=purpose!=='apple';$('verify-note').textContent=purpose==='apple'?'Войдите в аккаунт AppRevive, из которого запрашивали привязку, и подтвердите её.':'Задайте пароль AppRevive. Это не пароль Apple ID.';$('verify-form').onsubmit=run(async()=>{await api('/v3/auth/consume',{token:verification.get('token'),...(purpose==='apple'?{}:{password:$('new-password').value})});history.replaceState(null,'','/account');$('verify').hidden=true;$('new-password').value='';message('Подтверждено. Теперь можно войти или обновить кабинет.');try{await refresh();}catch{}});}

refresh().then(async()=>{const checkout=new URLSearchParams(location.search).get('payment');if(checkout&&/^[a-f0-9]{32}$/.test(checkout)){await api('/v3/checkout/sync',{checkout_id:checkout});await refreshOrders();history.replaceState(null,'','/account');}}).catch(error=>{if(error.status!==401)message(error.message,true);});
