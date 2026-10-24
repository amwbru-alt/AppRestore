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
$('connection-retry').onclick=run(async()=>{transportState(await AppReviveTransport.retry());try{await refresh();enterCabinet();}catch(error){if(error.status!==401)throw error;}});
function table(target, headings, rows){ const t=document.createElement('table'), head=document.createElement('tr');headings.forEach(x=>{const c=document.createElement('th');c.textContent=x;head.append(c);});t.append(head); for(const row of rows){const tr=document.createElement('tr');row.forEach(value=>{const td=document.createElement('td'); if(value instanceof Node)td.append(value);else td.textContent=String(value??'');tr.append(td);});t.append(tr);}if(!rows.length){const empty=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=headings.length;cell.textContent='Нет записей по выбранным условиям';cell.className='empty-state';empty.append(cell);t.append(empty);}$(target).replaceChildren(t); }
const status = value => ({pending:'Ожидает',paid:'Оплачен',cancelled:'Отменён',refunded:'Возвращён',completed:'Завершено',failed:'Ошибка, попытка возвращена',reserved:'Ожидает подтверждения'}[value]||value);
const rub = value => (Number(value)/100).toLocaleString('ru-RU',{style:'currency',currency:'RUB'});
function stats(target, items){$(target).replaceChildren(...items.map(([title,value])=>{const box=document.createElement('div');box.className='stat';const b=document.createElement('b'),s=document.createElement('span');b.textContent=value;s.textContent=title;box.append(b,s);return box;}));}
let profile=null, checkoutRequest=null, viewEpoch=0, shopPage=1, shopVersion=0;
function clearPrivateView(){
 viewEpoch++;paymentWatcher.stop();$('payment-watch').hidden=true;profile=null;checkoutRequest=null;$('cabinet').hidden=true;$('auth').hidden=false;
 for(const id of ['orders','code-stats','shop-pagination','partner','partner-stats','referrals','ledger','payouts','sessions'])$(id).replaceChildren();
 for(const id of ['password-form','buy-form','shop-filter'])$(id).reset();
 $('who').textContent='';shopPage=1;shopVersion++;$('code-copy-text').value='';$('code-copy-panel').hidden=true;paymentAvailable=null;updatePurchaseTotal();
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
 closeCodeCopy();
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
 cell.append(line);}if(order.state==='pending'){const b=document.createElement('button');b.className='button ghost';b.textContent='Проверить оплату';b.onclick=run(async()=>{trackPayment(order.checkout_id);$('payment-watch').scrollIntoView?.({block:'center'});});cell.append(b);}const support=document.createElement('a');support.href='https://t.me/llifegoldll?text='+encodeURIComponent('Здравствуйте! Вопрос по заказу AppRevive '+order.checkout_id+'. Статус: '+status(order.state)+'.');support.target='_blank';support.rel='noopener noreferrer';support.className='order-support';support.textContent='Поддержка по заказу ↗';cell.append(support);return [order.checkout_id,order.quantity,rub(order.amount_kopecks),status(order.state),cell];}));}
function renderShopPagination(data){
 const box=$('shop-pagination'),label=document.createElement('span');label.textContent=`Страница ${data.page} из ${data.pages} · заказов по фильтру ${data.total}`;box.replaceChildren(label);
 for(const [text,target,disabled]of [['← Назад',data.page-1,data.page<=1],['Далее →',data.page+1,data.page>=data.pages]]){const button=document.createElement('button');button.type='button';button.className='button ghost';button.textContent=text;button.disabled=disabled;button.onclick=run(()=>refreshOrders(target));box.append(button);}
}
$('shop-filter').onsubmit=run(()=>refreshOrders(1));
$('shop-reset').onclick=run(async()=>{$('shop-filter').reset();await refreshOrders(1);});
async function refresh(){
 const epoch=viewEpoch,next=await api('/v3/me');if(epoch!==viewEpoch)return;profile=next;$('auth').hidden=true;$('cabinet').hidden=false;$('who').textContent=profile.user.email;
 $('invited-by').textContent=profile.invited_by?'Вы зарегистрированы по приглашению '+profile.invited_by+'. Пригласивший закреплён.':'';
 const jobs=[['sessions',refreshSessions],['partner',refreshPartner],['orders',refreshOrders],['payment-status',async()=>{const settings=await api('/v3/status');paymentAvailable=!!settings.payments_enabled;$('payment-status').textContent=paymentAvailable?'':'Онлайн-оплата пока не настроена.';updatePurchaseTotal();}]];
 const results=await Promise.allSettled(jobs.map(async([id,load])=>{try{await load();}catch(error){if(epoch!==viewEpoch)return;$(id).textContent='Не удалось загрузить раздел: '+error.message;throw error;}}));
 if(epoch!==viewEpoch)return;
 $('sync-status').textContent='Обновлено '+new Date().toLocaleTimeString('ru-RU');
 const errors=results.filter(r=>r.status==='rejected');if(errors.length)message('Некоторые разделы не загрузились. Нажмите «Обновить». '+errors[0].reason.message,true);
 resumePaymentFromUrl();
 return errors.length===0;
}
function enterCabinet(){if(new URLSearchParams(location.search).get('next')==='admin'&&profile?.user.role==='admin'){location.assign('/admin');return;}const url=new URL(location.href);url.pathname='/account';url.searchParams.delete('next');url.hash='cabinet';history.replaceState(null,'',url.pathname+url.search+url.hash);$('cabinet').scrollIntoView?.({block:'start'});}
$('login-form').onsubmit=run(async event=>{await api('/v3/auth/login',Object.fromEntries(new FormData(event.target)));event.target.reset();let complete;try{complete=await refresh();}catch(error){message('Вход выполнен, но кабинет не загрузился. Не нужно вводить пароль повторно. Нажмите «Проверить подключение». '+error.message,true);return;}enterCabinet();if(complete)message('Вход выполнен.');});
$('register-form').onsubmit=run(async event=>{
 const details=Object.fromEntries(new FormData(event.target));await api('/v3/auth/register',details);
 try{await api('/v3/auth/login',{email:details.email,password:details.password});}catch(error){message('Аккаунт создан. Войдите с указанным паролем. '+error.message,true);return;}
 event.target.reset();try{localStorage.removeItem('apprevive_referral');}catch{}
 let complete;try{complete=await refresh();}catch(error){message('Аккаунт создан, вход выполнен, но кабинет не загрузился. Не регистрируйтесь повторно. Нажмите «Проверить подключение». '+error.message,true);return;}
 enterCabinet();if(complete)message('Добро пожаловать! Аккаунт создан'+(details.referral_code?' — пригласивший закреплён.':'.'));
});
$('reset-form').onsubmit=run(async event=>{await api('/v3/auth/reset',Object.fromEntries(new FormData(event.target)));message('Если аккаунт существует, письмо отправлено.');});
$('resend').onclick=run(async()=>{await api('/v3/auth/resend',{email:$('reset-form').elements.email.value});message('Если требуется подтверждение, письмо отправлено.');});
$('refresh').onclick=run(refresh);
$('logout').onclick=run(async()=>{await api('/v3/auth/logout',{});clearPrivateView();message('Вы вышли.');});
$('buy-form').onsubmit=run(async event=>{const quantity=Number(event.target.elements.quantity.value),intent=checkoutIntent(quantity);const data=await api('/v3/checkout',{quantity:intent.quantity,request_id:intent.request_id});if(/^[a-f0-9]{32}$/.test(data.checkout_id||'')){intent.checkout_id=data.checkout_id;try{sessionStorage.setItem(intentKey,JSON.stringify(intent));}catch{}}const destination=safePaymentUrl(data.confirmation_url);if(destination&&data.state==='pending')location.assign(destination);else if(/^[a-f0-9]{32}$/.test(data.checkout_id||''))trackPayment(data.checkout_id);else throw Error('Не удалось получить состояние заказа. Повторите запрос — номер покупки сохранён.');});
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

refresh().catch(error=>{if(error.status!==401)message(error.message,true);});

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
let liveTimer=setInterval(liveRefresh,30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)liveRefresh();});
window.addEventListener('online',liveRefresh);
window.addEventListener('pagehide',()=>{paymentWatcher.stop();clearInterval(liveTimer);liveTimer=null;$('code-copy-text').value='';$('code-copy-panel').hidden=true;});
window.addEventListener('pageshow',()=>{resumePaymentFromUrl();if(!liveTimer)liveTimer=setInterval(liveRefresh,30000);liveRefresh();});

const requestedQuantity=Number(new URLSearchParams(location.search).get('quantity'));
if(Number.isInteger(requestedQuantity)&&requestedQuantity>=1&&requestedQuantity<=100)$('buy-form').elements.quantity.value=String(requestedQuantity);

let paymentAvailable=null;
function updatePurchaseTotal(){
 const form=$('buy-form'),quantity=Number(form.elements.quantity.value),valid=Number.isInteger(quantity)&&quantity>=1&&quantity<=100;
 $('purchase-total').textContent=valid?'Итого: '+rub(quantity*10000):'Укажите от 1 до 100 кодов';
 const button=form.querySelector('button');button.disabled=!valid||paymentAvailable===false;
}
$('buy-form').elements.quantity.addEventListener('input',updatePurchaseTotal);
updatePurchaseTotal();
function closeCodeCopy(){$('code-copy-text').value='';$('code-copy-panel').hidden=true;}
$('close-code-copy').onclick=closeCodeCopy;
async function freshUnusedCodes(){
 if(!profile)throw Error('Войдите в AppRevive.');
 const epoch=viewEpoch,query=new URLSearchParams(new FormData($('shop-filter')));query.set('page',String(shopPage));query.set('size','20');
 const signature=query.toString(),page=shopPage;
 const data=await api('/v3/shop/orders?'+query);
 const current=new URLSearchParams(new FormData($('shop-filter')));current.set('page',String(shopPage));current.set('size','20');
 if(signature!==current.toString()||page!==shopPage)throw Error('Фильтры или страница изменились. Повторите копирование кодов.');
 if(epoch!==viewEpoch||!profile)throw Error('Сессия изменилась. Войдите снова.');
 const paid=new Set(data.orders.filter(order=>order.state==='paid').map(order=>order.checkout_id));
 const codes=[...new Set(data.codes.filter(code=>paid.has(code.checkout_id)&&code.activation_status==='unused'&&code.code).map(code=>code.code))];
 if(!codes.length)throw Error('На этой странице нет неактивированных кодов оплаченных заказов. Измените фильтры или страницу.');
 return codes;
}
$('copy-unused').onclick=run(async()=>{
 closeCodeCopy();const codes=await freshUnusedCodes(),text=codes.join('\n');
 try{await navigator.clipboard.writeText(text);message('Скопировано кодов: '+codes.length+'. Статус проверен перед копированием.');}
 catch{$('code-copy-panel').hidden=false;const field=$('code-copy-text');field.value=text;field.focus();field.select();message('Буфер обмена недоступен. Скопируйте выделенные коды вручную.');}
});
$('download-unused').onclick=run(async()=>{
 const codes=await freshUnusedCodes(),url=URL.createObjectURL(new Blob([codes.join('\r\n')+'\r\n'],{type:'text/plain;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download='AppRevive-unused-codes-'+new Date().toISOString().slice(0,10)+'.txt';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 message('Сохранено кодов: '+codes.length+'. Файл содержит действующие промокоды — передавайте его только выбранному исполнителю.');
});

const intentKey='apprevive_checkout_intent';
function checkoutIntent(quantity){
 const user=profile?.user?.user_id;
 let saved=checkoutRequest;try{if(!saved)saved=JSON.parse(sessionStorage.getItem(intentKey)||'null');}catch{}
 if(!saved||!user||saved.user_id!==user||saved.quantity!==quantity||!/^[a-f0-9]{32}$/.test(saved.request_id||'')||!Number.isFinite(saved.created_at)||Date.now()-saved.created_at<0||Date.now()-saved.created_at>6*3600000)saved={user_id:user,quantity,request_id:AppReviveTransport.requestId(),created_at:Date.now()};
 checkoutRequest=saved;if(user)try{sessionStorage.setItem(intentKey,JSON.stringify(saved));}catch{}
 return saved;
}
function clearCheckoutIntent(id){let saved=checkoutRequest;try{saved=saved||JSON.parse(sessionStorage.getItem(intentKey)||'null');}catch{}if(saved?.checkout_id!==id)return;checkoutRequest=null;try{sessionStorage.removeItem(intentKey);}catch{}}
function safePaymentUrl(value){try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password&&(!url.port||url.port==='443')&&/(^|\.)(yoomoney\.ru|yookassa\.ru)$/.test(url.hostname)?url.href:'';}catch{return '';}}
function trackPayment(id){if(!/^[a-f0-9]{32}$/.test(id))return;const url=new URL(location.href);url.searchParams.set('payment',id);history.replaceState(null,'',url.pathname+url.search+url.hash);paymentWatcher.start(id);}
function cleanPaymentUrl(){const url=new URL(location.href);url.searchParams.delete('payment');history.replaceState(null,'',url.pathname+url.search+url.hash);}
const paymentWatcher=AppRevivePaymentWatch({
 request:api,canPoll:()=>!!profile&&!document.hidden&&navigator.onLine!==false,
 onChange:data=>{
  $('payment-watch').hidden=false;$('payment-watch').dataset.state=data.state;
  $('payment-watch-order').textContent='Заказ '+data.checkout_id;
  $('payment-watch-support').href='https://t.me/llifegoldll?text='+encodeURIComponent('Здравствуйте! Проверьте заказ AppRevive '+data.checkout_id+'.');
  const notes={checking:'Проверяем платёж у провайдера…',pending:'Платёж пока не подтверждён. Не оплачивайте этот заказ повторно: проверка продолжится автоматически.',paid:'Оплата подтверждена. Промокоды доступны в заказе.',cancelled:'Провайдер сообщил об отмене платежа. По этому платежу коды не выдаются.',refunded:'По заказу оформлен возврат. Срок зачисления зависит от банка.',error:data.message};
  $('payment-watch-note').textContent=(notes[data.state]||'Не удалось определить состояние заказа.')+(data.paused?' Автопроверка остановлена. Нажмите «Проверить сейчас» или обратитесь в поддержку.':'');
  const destination=data.state==='pending'?safePaymentUrl(data.confirmation_url):'';const link=$('payment-watch-continue');link.hidden=!destination;if(destination)link.href=destination;else link.removeAttribute('href');
  $('payment-watch-retry').disabled=data.state==='checking';
 },
 onSettled:async data=>{clearCheckoutIntent(data.checkout_id);cleanPaymentUrl();try{await refreshOrders();}catch(error){message('Состояние платежа получено, но список кодов не обновился. '+error.message,true);}}
});
function resumePaymentFromUrl(){const checkout=new URLSearchParams(location.search).get('payment');if(profile&&/^[a-f0-9]{32}$/.test(checkout||'')&&paymentWatcher.currentId!==checkout)paymentWatcher.start(checkout);}
$('payment-watch-retry').onclick=()=>paymentWatcher.retry();
$('payment-watch-hide').onclick=()=>{paymentWatcher.stop();$('payment-watch').hidden=true;cleanPaymentUrl();};
$('payment-watch-show').onclick=run(async()=>{const id=paymentWatcher.currentId;if(!id)return;$('shop-filter').reset();$('shop-filter').elements.q.value=id;await refreshOrders(1);$('orders').scrollIntoView?.({block:'start'});});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)paymentWatcher.check();});
window.addEventListener('online',()=>paymentWatcher.check());
