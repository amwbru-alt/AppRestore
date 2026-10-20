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
function table(target, headings, rows){ const t=document.createElement('table'), head=document.createElement('tr');headings.forEach(x=>{const c=document.createElement('th');c.textContent=x;head.append(c);});t.append(head); for(const row of rows){const tr=document.createElement('tr');row.forEach(value=>{const td=document.createElement('td'); if(value instanceof Node)td.append(value);else td.textContent=String(value??'');tr.append(td);});t.append(tr);}if(!rows.length){const empty=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=headings.length;cell.textContent='Нет записей по выбранным условиям';cell.className='empty-state';empty.append(cell);t.append(empty);}$(target).replaceChildren(t); }
const status = value => ({pending:'Ожидает',paid:'Оплачен',cancelled:'Отменён',refunded:'Возвращён',completed:'Завершено',failed:'Ошибка, попытка возвращена',reserved:'Ожидает подтверждения'}[value]||value);
const rub = value => (Number(value)/100).toLocaleString('ru-RU',{style:'currency',currency:'RUB'});
function stats(target, items){$(target).replaceChildren(...items.map(([title,value])=>{const box=document.createElement('div');box.className='stat';const b=document.createElement('b'),s=document.createElement('span');b.textContent=value;s.textContent=title;box.append(b,s);return box;}));}
let profile=null, checkoutRequest=null, viewEpoch=0, shopPage=1, shopVersion=0;
function clearPrivateView(){
 viewEpoch++;profile=null;checkoutRequest=null;$('cabinet').hidden=true;$('auth').hidden=false;
 for(const id of ['orders','code-stats','shop-pagination','partner','partner-stats','referrals','ledger','payouts','sessions'])$(id).replaceChildren();
 for(const id of ['password-form','buy-form','shop-filter'])$(id).reset();
 $('who').textContent='';shopPage=1;shopVersion++;
}
async function refreshPartner(){
 const epoch=viewEpoch,data=await api('/v3/partner'),p=data.partner;if(epoch!==viewEpoch)return;
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

async function refreshOrders(page=shopPage){
 const epoch=viewEpoch,version=++shopVersion,query=new URLSearchParams(new FormData($('shop-filter')));query.set('page',String(page));query.set('size','20');
 const data=await api('/v3/shop/orders?'+query);if(epoch!==viewEpoch||version!==shopVersion)return;
 shopPage=data.page;
 stats('code-stats',[['Всего кодов',data.stats.total],['Не активировано',data.stats.unused],['Активировано',data.stats.activated],['Аннулировано',data.stats.invalidated]]);
 renderShopPagination(data);
table('orders',['Заказ','Куплено в заказе','Сумма','Состояние','Промокоды / действие'],data.orders.map(order=>{const cell=document.createElement('div'); for(const code of data.codes.filter(c=>c.checkout_id===order.checkout_id)){const line=document.createElement('div');line.className='purchased-code';
 const field=document.createElement('input');field.readOnly=true;field.value=code.code||('Исторический код · '+code.code_id);field.setAttribute('aria-label','Купленный промокод');
 const badge=document.createElement('span');badge.className='code-status '+code.activation_status;badge.textContent=({unused:'Не активирован',activated:'Активирован',invalidated:'Аннулирован',unavailable:'Статус требует проверки'})[code.activation_status]||'Статус требует проверки';
 line.append(field,badge);
 if(code.activated_at){const time=document.createElement('small');time.textContent='Активирован '+new Date(code.activated_at).toLocaleString('ru-RU');line.append(time);}
 if(code.code){const copy=document.createElement('button');copy.className='button ghost';copy.textContent='Копировать';copy.onclick=run(async()=>{try{await navigator.clipboard.writeText(code.code);message('Промокод скопирован.');}catch{field.focus();field.select();message('Скопируйте выделенный промокод.');}});line.append(copy);}else{const note=document.createElement('small');note.textContent='Текст старого кода не сохранялся до обновления.';line.append(note);}
 cell.append(line);}if(order.state==='pending'){const b=document.createElement('button');b.className='button ghost';b.textContent='Проверить оплату';b.onclick=run(async()=>{const updated=await api('/v3/checkout/sync',{checkout_id:order.checkout_id});if(updated.confirmation_url){const a=document.createElement('a');a.href=updated.confirmation_url;a.textContent='Перейти к оплате ↗';a.className='button primary';cell.append(a);}else await refreshOrders();});cell.append(b);}return [order.checkout_id,order.quantity,rub(order.amount_kopecks),status(order.state),cell];}));}
function renderShopPagination(data){
 const box=$('shop-pagination'),label=document.createElement('span');label.textContent=`Страница ${data.page} из ${data.pages} · заказов по фильтру ${data.total}`;box.replaceChildren(label);
 for(const [text,target,disabled]of [['← Назад',data.page-1,data.page<=1],['Далее →',data.page+1,data.page>=data.pages]]){const button=document.createElement('button');button.type='button';button.className='button ghost';button.textContent=text;button.disabled=disabled;button.onclick=run(()=>refreshOrders(target));box.append(button);}
}
$('shop-filter').onsubmit=run(()=>refreshOrders(1));
$('shop-reset').onclick=run(async()=>{$('shop-filter').reset();await refreshOrders(1);});
async function refresh(){
 const epoch=viewEpoch,next=await api('/v3/me');if(epoch!==viewEpoch)return;profile=next;$('auth').hidden=true;$('cabinet').hidden=false;$('who').textContent=profile.user.email;
 $('invited-by').textContent=profile.invited_by?'Вы зарегистрированы по приглашению '+profile.invited_by+'. Пригласивший закреплён.':'';
 const jobs=[['sessions',refreshSessions],['partner',refreshPartner],['orders',refreshOrders],['payment-status',async()=>{const settings=await api('/v3/status');$('payment-status').textContent=settings.payments_enabled?'':'Онлайн-оплата пока не настроена.';}]];
 const results=await Promise.allSettled(jobs.map(async([id,load])=>{try{await load();}catch(error){if(epoch!==viewEpoch)return;$(id).textContent='Не удалось загрузить раздел: '+error.message;throw error;}}));
 if(epoch!==viewEpoch)return;
 $('sync-status').textContent='Обновлено '+new Date().toLocaleTimeString('ru-RU');
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
$('refresh').onclick=run(refresh);
$('logout').onclick=run(async()=>{await api('/v3/auth/logout',{});clearPrivateView();message('Вы вышли.');});
$('buy-form').onsubmit=run(async event=>{const quantity=Number(event.target.elements.quantity.value);if(!checkoutRequest||checkoutRequest.quantity!==quantity)checkoutRequest={quantity,request_id:AppReviveTransport.requestId()};const data=await api('/v3/checkout',checkoutRequest);if(data.confirmation_url)location.assign(data.confirmation_url);else{checkoutRequest=null;message('Оплата подтверждена. Коды доступны в заказе.');await refreshOrders();}});
$('register-form').elements.referral_code.addEventListener('input',event=>{event.target.value=event.target.value.toUpperCase();});
let storedReferral='';try{storedReferral=localStorage.getItem('apprevive_referral')||'';}catch{}
const invited=(new URLSearchParams(location.search).get('ref')||storedReferral).trim().toUpperCase();
if(invited&&/^RVP-[A-F0-9]{12}$/.test(invited)){
 try{localStorage.setItem('apprevive_referral',invited);}catch{}
 $('register-form').elements.referral_code.value=invited;
}
if(location.hash==='#register-form')$('register-form').elements.email.focus();
const verification=new URLSearchParams(location.hash.slice(1));
if(verification.has('token')){$('verify').hidden=false;const purpose=verification.get('purpose');$('new-password-label').hidden=purpose==='apple';$('new-password').required=purpose!=='apple';$('verify-note').textContent=purpose==='apple'?'Войдите в аккаунт AppRevive, из которого запрашивали привязку, и подтвердите её.':'Задайте пароль AppRevive. Это не пароль Apple ID.';$('verify-form').onsubmit=run(async()=>{await api('/v3/auth/consume',{token:verification.get('token'),...(purpose==='apple'?{}:{password:$('new-password').value})});history.replaceState(null,'','/account');$('verify').hidden=true;$('new-password').value='';message('Подтверждено. Теперь можно войти или обновить кабинет.');try{await refresh();}catch{}});}

refresh().then(async()=>{const checkout=new URLSearchParams(location.search).get('payment');if(checkout&&/^[a-f0-9]{32}$/.test(checkout)){await api('/v3/checkout/sync',{checkout_id:checkout});await refreshOrders();history.replaceState(null,'','/account');}}).catch(error=>{if(error.status!==401)message(error.message,true);});

async function refreshSessions(){
 const epoch=viewEpoch,data=await api('/v3/security/sessions');if(epoch!==viewEpoch)return;
 $('sessions').replaceChildren(...data.sessions.map(session=>{
  const row=document.createElement('div');row.className='session-row';
  const text=document.createElement('span');text.textContent=(session.current?'Этот вход':'Другая сессия')+' · до '+new Date(session.expires_at).toLocaleString('ru-RU');row.append(text);
  if(!session.current){const button=document.createElement('button');button.type='button';button.className='button ghost';button.textContent='Завершить';button.onclick=run(async()=>{await api('/v3/security/revoke',{session_id:session.id});await refreshSessions();message('Сессия завершена.');});row.append(button);}return row;
 }));
}
$('refresh-sessions').onclick=run(refreshSessions);
$('revoke-others').onclick=run(async()=>{await api('/v3/security/revoke',{others:true});await refreshSessions();message('Остальные сессии завершены.');});
$('password-form').onsubmit=run(async event=>{await api('/v3/security/password',Object.fromEntries(new FormData(event.target)));event.target.reset();await refreshSessions();message('Пароль изменён. Остальные сессии завершены.');});
window.addEventListener('apprevive:expired',()=>{if(!profile)return;clearPrivateView();$('sessions').replaceChildren();message('Сессия завершена. Войдите снова.',true);});
let liveBusy=false;
async function liveRefresh(){
 if(liveBusy||!profile||document.hidden||navigator.onLine===false||document.querySelector('form[data-busy="true"]')||document.activeElement?.matches('input,textarea,select'))return;
 liveBusy=true;
 try{
  const results=await Promise.allSettled([refreshPartner(),refreshOrders()]);
  $('sync-status').textContent=results.some(r=>r.status==='rejected')?'Не удалось обновить. Повторим автоматически.':'Обновлено '+new Date().toLocaleTimeString('ru-RU');
 }finally{liveBusy=false;}
}
const liveTimer=setInterval(liveRefresh,30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)liveRefresh();});
window.addEventListener('online',liveRefresh);
window.addEventListener('pagehide',()=>clearInterval(liveTimer));

const requestedQuantity=Number(new URLSearchParams(location.search).get('quantity'));
if(Number.isInteger(requestedQuantity)&&requestedQuantity>=1&&requestedQuantity<=100)$('buy-form').elements.quantity.value=String(requestedQuantity);
