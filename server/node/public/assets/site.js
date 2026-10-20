'use strict';
const normalize = text => String(text).toLocaleLowerCase('ru').replaceAll('ё', 'е');
const grid = document.querySelector('#catalog');
const search = document.querySelector('#app-search');
let apps = [],visibleLimit=8,catalogBusy=false;
function renderApps() {
 const query=normalize(search.value.trim()),matches=apps.filter(app=>normalize(app.name).includes(query)),result=matches.slice(0,visibleLimit);
 grid.replaceChildren();
 document.getElementById('catalog-count').textContent=`Показано ${result.length} из ${matches.length}`;
 document.getElementById('catalog-more').hidden=result.length>=matches.length;
 document.getElementById('catalog-clear').hidden=!query;
 if(!result.length){const message=document.createElement('p');message.className='catalog-message';message.textContent=query?'Совпадений нет. Измените запрос или продолжите проверку в AppRevive.':'Каталог пока пуст. Проверьте приложения в AppRevive.';grid.append(message);return;}
 for(const app of result){
  const card=document.createElement('a');card.className='app-card';card.href='#download';
  const placeholder=document.createElement('span');placeholder.className='app-placeholder';placeholder.textContent='↺';placeholder.setAttribute('aria-hidden','true');card.append(placeholder);
  try{const url=new URL(app.iconUrl);if(url.protocol==='https:'&&!url.username&&!url.password){const img=document.createElement('img');img.src=url.href;img.alt='';img.loading='lazy';img.referrerPolicy='no-referrer';img.addEventListener('error',()=>img.replaceWith(placeholder),{once:true});placeholder.replaceWith(img);}}catch{}
  const text=document.createElement('div'),name=document.createElement('h3'),caption=document.createElement('span');name.textContent=app.name;caption.textContent='Проверить в AppRevive ↗';text.append(name,caption);card.append(text);grid.append(card);
 }
}
async function loadCatalog(){
 if(catalogBusy)return;catalogBusy=true;const retry=document.getElementById('catalog-retry');retry.disabled=true;grid.setAttribute('aria-busy','true');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
 try{
  const response=await fetch('/v1/catalog',{headers:{Accept:'application/json'},signal:controller.signal});if(!response.ok)throw Error();
  const data=await response.json();if(data.status!=='ok'||!Array.isArray(data.apps))throw Error();
  const seen=new Set();apps=data.apps.filter(app=>app&&typeof app.name==='string'&&app.name.trim()).flatMap(app=>{if(!app.groupId||!app.groupName)return [app];if(seen.has(app.groupId))return [];seen.add(app.groupId);return [{...app,name:app.groupName,iconUrl:app.groupIconUrl||app.iconUrl}];});
  visibleLimit=8;retry.hidden=true;
  const suggestions=document.getElementById('catalog-suggestions');suggestions.replaceChildren(...apps.slice(0,4).map(app=>{const button=document.createElement('button');button.type='button';button.textContent=app.name;button.onclick=()=>{search.value=app.name;visibleLimit=8;renderApps();};return button;}));renderApps();
 }catch{grid.replaceChildren();const message=document.createElement('p');message.className='catalog-message';message.textContent='Каталог сейчас недоступен. Повторите загрузку или проверьте приложения в AppRevive.';grid.append(message);document.getElementById('catalog-count').textContent='Не удалось загрузить';document.getElementById('catalog-more').hidden=true;retry.hidden=false;}
 finally{clearTimeout(timer);catalogBusy=false;retry.disabled=false;grid.removeAttribute('aria-busy');}
}
search.addEventListener('input',()=>{visibleLimit=8;if(apps.length)renderApps();});
document.getElementById('catalog-more').onclick=()=>{visibleLimit+=8;renderApps();};
document.getElementById('catalog-clear').onclick=()=>{search.value='';visibleLimit=8;renderApps();search.focus();};
document.getElementById('catalog-retry').onclick=loadCatalog;
loadCatalog();
fetch('/site-config').then(response => response.ok ? response.json() : Promise.reject()).then(data => {
  for (const [platform, id] of [['macos', 'mac-status'], ['windows', 'windows-status']]) {
    document.getElementById(id).textContent = data.downloads?.[platform] ? 'Архив готов к скачиванию' : 'Архив ещё не опубликован. Свяжитесь с поддержкой.';
  }
}).catch(() => { for (const id of ['mac-status', 'windows-status']) document.getElementById(id).textContent = 'Наличие архива проверим по кнопке скачивания.'; });
const referral = new URLSearchParams(location.search).get('ref')?.trim().toUpperCase();
if (referral && /^RVP-[A-F0-9]{12}$/.test(referral)) {
  try{localStorage.setItem('apprevive_referral',referral);}catch{}
  document.getElementById('referral').hidden = false;
  document.getElementById('referral-code').value = referral;
  document.getElementById('register-referral').href='/register?ref='+encodeURIComponent(referral);
  document.getElementById('copy-referral').addEventListener('click', async () => {
    const field = document.getElementById('referral-code'); field.select();
    try { await navigator.clipboard.writeText(referral); document.getElementById('copy-status').textContent = 'Скопировано. Код применяется при регистрации на сайте.'; }
    catch { field.focus(); field.select(); document.getElementById('copy-status').textContent = 'Скопируйте выделенный код вручную.'; }
  });
}

fetch('/v3/status').then(r=>r.ok?r.json():Promise.reject()).then(data=>{
  if(data.payments_enabled){const link=document.querySelector('#pricing .text-link');if(link){link.href='/account';link.textContent='Купить код в кабинете ↗';link.removeAttribute('target');const copy=document.querySelector('#pricing h2 + p');if(copy)copy.textContent='Первое успешное восстановление — в подарок для каждого Apple ID. Следующие коды можно купить в личном кабинете.';}}
  if(data.commission_policy?.rate>0){const note=document.querySelector('#partners small');if(note)note.textContent=`Вознаграждение по новым заказам: ${data.commission_policy.rate/100}%. Удержание ${data.commission_policy.days} дней. Выплаты подтверждает администратор.`;}
}).catch(()=>{});

const scenarios={
 self:{heading:'Компьютер, iPhone и ваш Apple ID.',steps:['Скачайте AppRevive для Mac или Windows.','Подключите iPhone по USB и войдите в Apple ID в приложении.','Проверьте доступность восстановления. Первый успешный раз — в подарок.'],href:'#download',action:'Выбрать версию ↓'},
 code:{heading:'Купите код. Передайте исполнителю.',steps:['Войдите в кабинет AppRevive. Apple ID на сайте не нужен.','Выберите количество кодов. После подтверждённой оплаты они появятся в заказе.','Передайте код исполнителю. После использования статус изменится на «Активирован».'],href:'/account',action:'Открыть кабинет ↗'}
};
function chooseJourney(key){
 const value=scenarios[key];for(const name of ['self','code']){const tab=document.getElementById('journey-'+name);tab.setAttribute('aria-selected',String(name===key));tab.tabIndex=name===key?0:-1;}
 document.getElementById('journey-content').setAttribute('aria-labelledby','journey-'+key);document.getElementById('journey-heading').textContent=value.heading;
 document.getElementById('journey-steps').replaceChildren(...value.steps.map(step=>{const item=document.createElement('li');item.textContent=step;return item;}));
 const link=document.getElementById('journey-action');link.href=value.href;link.textContent=value.action;
}
for(const key of ['self','code']){const tab=document.getElementById('journey-'+key);tab.onclick=()=>chooseJourney(key);tab.onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?'self':event.key==='End'?'code':key==='self'?'code':'self';chooseJourney(next);document.getElementById('journey-'+next).focus();}};}
const quantity=document.getElementById('code-quantity');
quantity.addEventListener('input',()=>{const count=Number(quantity.value),valid=Number.isInteger(count)&&count>=1&&count<=100,link=document.getElementById('code-checkout');document.getElementById('code-total').textContent=valid?(count*100).toLocaleString('ru-RU')+' ₽':'—';link.setAttribute('aria-disabled',String(!valid));if(valid)link.href='/account?quantity='+count;else link.removeAttribute('href');});
document.getElementById('code-checkout').onclick=event=>{if(event.currentTarget.getAttribute('aria-disabled')==='true'){event.preventDefault();quantity.reportValidity();}};
const toggle=document.getElementById('menu-toggle'),navigation=document.getElementById('main-nav');
function closeMenu(){toggle.setAttribute('aria-expanded','false');navigation.dataset.open='false';}
toggle.onclick=()=>{const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));navigation.dataset.open=String(open);};
navigation.addEventListener('click',event=>{if(event.target.closest('a'))closeMenu();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&toggle.getAttribute('aria-expanded')==='true'){closeMenu();toggle.focus();}});
document.body.dataset.enhanced='true';
