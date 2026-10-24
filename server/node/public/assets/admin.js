'use strict';
const $=id=>document.getElementById(id);const msg=AppRevivePortal.notice;
const api=(path,body)=>AppRevivePortal.request('/v3/'+path,body);
const run=AppRevivePortal.run;
const rub=x=>(Number(x)/100).toLocaleString('ru-RU',{style:'currency',currency:'RUB'});
function table(id,columns,rows){const t=document.createElement('table'),tr=document.createElement('tr');for(const title of columns){const th=document.createElement('th');th.textContent=title;tr.append(th);}t.append(tr);for(const cells of rows){const row=document.createElement('tr');for(const value of cells){const td=document.createElement('td');if(value instanceof Node)td.append(value);else td.textContent=String(value??'');row.append(td);}t.append(row);}if(!rows.length){const empty=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=columns.length;cell.textContent='Нет записей по выбранным условиям';cell.className='empty-state';empty.append(cell);t.append(empty);}$(id).replaceChildren(t);}
function actions(list){const box=document.createElement('div');for(const [title,action,question] of list){const b=document.createElement('button');b.className='button ghost';b.textContent=title;b.onclick=run(async()=>{if(question&&!confirm(question))return;b.disabled=true;try{await action();msg('Действие выполнено.');await snapshot();}finally{b.disabled=false;}});box.append(b);}return box;}
let groups=[];
async function loadGroups(){groups=(await api('admin/groups')).groups;const choice=$('group-select').value;$('group-select').replaceChildren();const blank=document.createElement('option');blank.value='';blank.textContent='Новая группа';$('group-select').append(blank);for(const g of groups){const o=document.createElement('option');o.value=g.id;o.textContent=g.name;$('group-select').append(o);}if(groups.some(g=>g.id===choice))$('group-select').value=choice;fillGroup();}
function fillGroup(){const g=groups.find(g=>g.id===$('group-select').value),f=$('group-form');f.elements.id.value=g?.id||'';f.elements.id.readOnly=!!g;f.elements.name.value=g?.name||'';f.elements.iconUrl.value=g?.iconUrl||'';f.elements.apps.value=(g?.apps||[]).map(a=>[a.trackId,a.name,a.iconUrl||''].join('; ')).join('\n');$('delete-group').disabled=!g;}
$('group-select').onchange=fillGroup;
$('group-form').onsubmit=run(async e=>{const data=Object.fromEntries(new FormData(e.target));const next={id:data.id,name:data.name,iconUrl:data.iconUrl,apps:data.apps.split('\n').filter(line=>line.trim()).map(line=>{const [trackId,name,iconUrl='']=line.split(';').map(x=>x.trim());return{trackId,name,iconUrl};})};await api('admin/groups',{groups:[...groups.filter(g=>g.id!==next.id),next]});await loadGroups();msg('Группа сохранена. Перезапустите клиент для обновления каталога.');});
$('delete-group').onclick=run(async()=>{const id=$('group-select').value;if(!id||!confirm('Отключить группу? Остальные группы сохранятся.'))return;await api('admin/groups',{groups:groups.filter(g=>g.id!==id)});await loadGroups();msg('Группа отключена.');});
$('catalog-form').onsubmit=run(async e=>{const data=Object.fromEntries(new FormData(e.target));data.enabled=e.target.elements.enabled.checked;await api('admin/catalog',data);msg('Название и иконка сохранены.');});
$('manual-form').onsubmit=run(async e=>{const b=Object.fromEntries(new FormData(e.target));b.quantity=Number(b.quantity);b.amount_kopecks=Number(b.amount_kopecks);b.confirmed=e.target.elements.confirmed.checked;const result=await api('admin/purchase',b);$('issued-codes').textContent=(result.unused_codes||[]).join('\n');msg('Заказ зарегистрирован. Передайте выпущенные коды покупателю.');await snapshot();});
$('manual-refund-form').onsubmit=run(async e=>{await api('admin/manual-refund',{payment_reference:e.target.elements.payment_reference.value,confirmed:e.target.elements.confirmed.checked});msg('Возврат записан.');await snapshot();});
$('policy-form').onsubmit=run(async e=>{await api('admin/policy',{rate:Math.round(Number(e.target.elements.percent.value)*100),days:Number(e.target.elements.days.value)});msg('Условия сохранены для новых заказов. Старые начисления не пересчитываются.');});
$('payout-form').onsubmit=run(async e=>{const b=Object.fromEntries(new FormData(e.target));b.amount_kopecks=Number(b.amount_kopecks);await api('admin/payout/create',b);msg('Выплата зарезервирована. Перевод денег выполняется отдельно.');await snapshot();});
async function snapshot(){const d=await api('admin/snapshot');
 table('partner-list',['Партнёр','Почта AppRevive','Код приглашения','Регистраций','Привязанных Apple ID','Оплаченных заказов','Куплено кодов','Продажи'],(d.partners||[]).map(p=>[p.account_id,p.email||'Из приложения',p.referral_code,p.registered||0,p.invited,p.paid_orders,p.purchased_codes,rub(p.revenue_kopecks)]));
table('users',['Пользователь','Почта','Подтверждён','Роль','Пригласивший'],d.users.map(u=>[u.user_id,u.email,u.verified,u.role,u.invited_by||'Без приглашения']));table('orders',['Оплата','Покупатель','Партнёр','Коды','Сумма','Состояние'],d.orders.map(o=>[o.payment_reference,o.buyer_id,o.partner_id,o.quantity,rub(o.amount_kopecks),o.state]));table('checkouts',['Онлайн-заказ','Покупатель','Сумма','Состояние','Действия'],d.checkouts.map(c=>[c.checkout_id,c.account_id,rub(c.amount_kopecks),c.state,actions([['Проверить',()=>api('admin/sync',{checkout_id:c.checkout_id})],['Полный возврат',()=>api('admin/refund',{checkout_id:c.checkout_id}),'Отправить провайдеру запрос полного возврата этой оплаты?']])]));table('restorations',['Apple ID','Операция','Начато','Проверенный итог'],d.restorations.map(r=>[r.account_id,r.request_id,r.created_at,actions([['Успех',()=>api('admin/resolve',{account_id:r.account_id,request_id:r.request_id,success:true}),'Подтверждаете, что приложение действительно установилось?'],['Ошибка',()=>api('admin/resolve',{account_id:r.account_id,request_id:r.request_id,success:false}),'Подтверждаете, что установка не состоялась и нужно вернуть попытку?']])]));table('commissions',['Заказ','Партнёр','Ставка','Сумма','Доступно с','Состояние'],d.commissions.map(c=>[c.order_id,c.partner_id,c.rate_bps/100+'%',rub(c.amount_kopecks),c.available_at,c.state]));table('payouts',['Партнёр','Сумма','Номер','Состояние','Действия'],d.payouts.map(p=>[p.partner_id,rub(p.amount_kopecks),p.reference,p.state,p.state==='pending'?actions([['Выплачено',()=>api('admin/payout/finish',{payout_id:p.payout_id,state:'paid'}),'Деньги действительно переведены партнёру?'],['Отменить',()=>api('admin/payout/finish',{payout_id:p.payout_id,state:'cancelled'}),'Отменить резерв выплаты?']]):'']));table('audit',['Дата','Администратор','Действие','Объект'],d.audit.map(a=>[a.created_at,a.user_id,a.action,a.target]));const loaded=await Promise.allSettled([loadRecords('users',pages.users),loadRecords('orders',pages.orders),loadMetrics(),loadDiscoveries()]);const failed=loaded.find(r=>r.status==='rejected');if(failed)msg('Часть данных не загрузилась. '+failed.reason.message);}
$('refresh').onclick=run(snapshot);
(async()=>{try{const me=await api('me');if(me.user.role!=='admin')throw Error('Недостаточно прав. Войдите как администратор через личный кабинет.');$('admin').hidden=false;msg('Вы вошли как '+me.user.email);const results=await Promise.allSettled([loadGroups(),snapshot(),(async()=>{const policy=(await api('status')).commission_policy;$('policy-form').elements.percent.value=policy.rate/100;$('policy-form').elements.days.value=policy.days;})()]);const failure=results.find(r=>r.status==='rejected');if(failure)msg('Не все разделы загрузились. '+failure.reason.message);}catch(error){msg(error.message+' Откройте вход ниже.');const link=document.createElement('a');link.href='/login?next=admin';link.className='button primary';link.textContent='Войти в админку';$('admin').before(link);}})();

const pages={users:1,orders:1},versions={users:0,orders:0};
async function loadRecords(kind,page=1){
 const version=++versions[kind],form=$(kind+'-search'),query=new URLSearchParams(new FormData(form));query.set('page',page);query.set('size','25');
 const area=$(kind+'-pagination');area.setAttribute('aria-busy','true');
 try{
  const data=await api('admin/'+kind+'?'+query);if(version!==versions[kind])return;pages[kind]=data.page;
  const headings=kind==='users'?['Пользователь','Почта','Подтверждён','Роль','Пригласивший']:['Оплата','Покупатель','Партнёр','Коды','Сумма','Состояние'];
  const rows=data.rows.map(r=>kind==='users'?[r.user_id,r.email,r.verified?'Да':'Нет',r.role,r.invited_by||'Без приглашения']:[r.payment_reference,r.buyer_id,r.partner_id||'Без партнёра',r.quantity,rub(r.amount_kopecks),r.state]);
  table(kind,headings,rows);area.replaceChildren();
  const label=document.createElement('span');label.textContent=`Страница ${data.page} из ${data.pages} · найдено ${data.total}`;
  for(const [text,target,disabled]of [['← Назад',data.page-1,data.page<=1],['Далее →',data.page+1,data.page>=data.pages]]){const b=document.createElement('button');b.type='button';b.className='button ghost';b.textContent=text;b.disabled=disabled;b.onclick=run(()=>loadRecords(kind,target));area.append(b);}
  area.prepend(label);
  const download=document.createElement('button');download.type='button';download.className='button ghost';download.textContent='CSV этой страницы';download.onclick=()=>AppRevivePortal.downloadCsv(kind+'-page-'+data.page+'.csv',[headings,...rows]);area.append(download);
 }catch(error){if(version===versions[kind]){$(kind).textContent='Не удалось загрузить: '+error.message;area.replaceChildren();}throw error;}finally{if(version===versions[kind])area.removeAttribute('aria-busy');}
}
async function loadMetrics(){
 const d=await api('admin/metrics');
 $('admin-metrics').replaceChildren(...[['Пользователей',d.users],['Рефералов',d.registered_referrals],['Оплаченных заказов',d.paid_orders],['Продажи',rub(d.revenue_kopecks)],['Куплено кодов',d.codes],['Восстановлений в работе',d.pending_restorations]].map(([title,value])=>{const card=document.createElement('div');card.className='stat';const b=document.createElement('b'),span=document.createElement('span');b.textContent=value;span.textContent=title;card.append(b,span);return card;}));
 $('metrics-time').textContent='По всей базе · обновлено '+new Date(d.updated_at).toLocaleString('ru-RU');
}
for(const kind of ['users','orders'])$(kind+'-search').onsubmit=run(()=>loadRecords(kind,1));

window.addEventListener('apprevive:expired',()=>{$('admin').hidden=true;msg('Сессия завершена. Войдите снова через ссылку вверху страницы.');});

async function loadDiscoveries(page=1){
 const d=await api('admin/discoveries?page='+page);
 table('discoveries',['App Store ID','Bundle ID','Название кандидата','Заявленный источник','Впервые найдено','Проверка'],(d.apps||[]).map(app=>{
  const controls=document.createElement('div'),name=document.createElement('input'),icon=document.createElement('input');
  name.value=app.name;name.maxLength=255;name.setAttribute('aria-label','Проверенное название '+app.store_id);
  icon.type='url';icon.placeholder='https://… · иконка необязательно';icon.setAttribute('aria-label','Иконка '+app.store_id);
  controls.append(name,icon);
  for(const [label,action]of [['Опубликовать','approve'],['Отклонить','reject']]){
   const b=document.createElement('button');b.type='button';b.className='button ghost';b.textContent=label;
   b.onclick=run(async()=>{await api('admin/discoveries/review',{store_id:app.store_id,action,name:name.value,icon_url:icon.value});await loadDiscoveries(page);msg(action==='approve'?'Приложение добавлено в каталог. Существующая запись, если была, сохранена.':'Кандидат отклонён.');});controls.append(b);
  }
  return [app.store_id,app.bundle_id,app.name,app.source,app.created_at,controls];
 }));
 const area=$('discoveries-pagination'),label=document.createElement('span');label.textContent=`Кандидатов: ${d.total||0} · страница ${d.page||1} из ${d.pages||1}`;area.replaceChildren(label);
 for(const [text,target,disabled]of [['← Назад',d.page-1,d.page<=1],['Далее →',d.page+1,d.page>=d.pages]]){const b=document.createElement('button');b.type='button';b.className='button ghost';b.textContent=text;b.disabled=disabled;b.onclick=run(()=>loadDiscoveries(target));area.append(b);}
}
$('discoveries-refresh').onclick=run(()=>loadDiscoveries());
