'use strict';
window.AppRevivePortal = (() => {
  const labels = {
    https_required:'Вход и регистрация по HTTP ещё не включены на сервере. Обратитесь к администратору.',
    service_login_required:'Войдите в AppRevive.', login_failed_or_unverified:'Неверная почта или пароль AppRevive.', account_exists:'Аккаунт с этой почтой уже существует. Войдите с прежним паролем.',
    password_min_12:'Пароль AppRevive должен содержать от 12 символов.', invalid_email:'Введите корректный адрес электронной почты.',
    mail_not_configured:'Отправка писем пока не настроена на сервере. Администратор должен подключить почтовый сервис.',
    mail_unavailable:'Почтовый сервис не принял письмо. Повторите позже или обратитесь к администратору.',
    current_password_incorrect:'Текущий пароль неверен.',invalid_session:'Некорректная сессия.',invalid_page:'Некорректный номер страницы.',invalid_filter:'Некорректный фильтр.',
    payments_not_configured:'Приём оплаты пока не настроен.', verify_apple_email_required:'Подтвердите почту этого Apple ID.',
    unknown_referral:'Код приглашения не найден.', self_referral:'Нельзя пригласить себя.', referral_locked:'Пригласивший уже закреплён.', purchase_already_recorded:'Пригласившего нужно указать до первой покупки.',
    apple_already_linked:'Этот Apple ID уже привязан к другому аккаунту AppRevive.',
    invalid_or_expired_token:'Ссылка недействительна или истекла. Запросите новое письмо.',
    login_as_link_requester:'Войдите в аккаунт AppRevive, из которого запрашивали привязку Apple ID.',
    invalid_code:'Код не найден или уже использован.', rate_limited:'Слишком много запросов. Повторите позже.',
    invalid_date_range:'Укажите корректные даты: дата начала должна быть не позже даты окончания.',
    invalid_discoveries:'Некорректные данные приложения.',invalid_discovery_review:'Проверьте ID, название и HTTPS-адрес иконки.',discovery_not_found:'Кандидат уже недоступен. Обновите список.',
    database_schema_outdated:'База сайта требует обновления. Сообщите поддержке: нужно выполнить миграции сервера.',
    database_unavailable:'Сайт временно не может подключиться к базе. Повторите позже или обратитесь в поддержку.',
    database_configuration_error:'Ошибка настроек базы сайта. Обратитесь в поддержку.',
    admin_required:'Недостаточно прав. Войдите как администратор.', unavailable:'Сервер временно недоступен. Повторите позже.'
  };
  let noticeTimer;
  const notice = (text,focus=false) => {
    const box=document.getElementById('message');if(!box)return;
    clearTimeout(noticeTimer);box.hidden=!text;box.replaceChildren();box.dataset.kind=focus?'error':'info';
    const content=document.createElement('span');content.textContent=text;
    const close=document.createElement('button');close.type='button';close.className='notice-close';close.textContent='×';close.setAttribute('aria-label','Закрыть уведомление');
    close.onclick=()=>{clearTimeout(noticeTimer);box.hidden=true;box.replaceChildren();};box.append(content,close);
    if(focus){box.tabIndex=-1;box.focus({preventScroll:true});}
    noticeTimer=setTimeout(()=>{box.hidden=true;box.replaceChildren();},focus?9000:5500);
  };
  async function request(path,body) {
    if(!window.AppReviveTransport)throw Error('Не загрузился модуль подключения. Обновите страницу.');
    await AppReviveTransport.requireAllowed();
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
    try {
      const response=await fetch(path,{cache:'no-store',signal:controller.signal,credentials:'same-origin',method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
      let data;try{data=await response.json();}catch{throw Error('Сервер вернул некорректный ответ. Проверьте обновление API и повторите позже.');}
      if(!data || typeof data!=='object')throw Error('Сервер вернул некорректный ответ. Обновите страницу и повторите.');
      if(!response.ok){if(response.status===401&&!path.startsWith('/v3/auth/'))window.dispatchEvent(new CustomEvent('apprevive:expired'));const error=Error(labels[data.status]||'Операция не выполнена. Код: '+(data.status||response.status));if(/^[a-f0-9]{16}$/.test(data.request_id||'')){error.message+=' Номер ошибки: '+data.request_id;error.requestId=data.request_id;}error.status=response.status;throw error;}
      return data;
    } catch(error) {
      if(controller.signal.aborted)throw Error('Сервер не ответил за 20 секунд. Повторите позже.');
      if(error instanceof TypeError)throw Error('Не удалось связаться с сервером. Проверьте подключение и повторите.');
      throw error;
    } finally {clearTimeout(timer);}
  }
  const run=fn=>async event=>{
    event?.preventDefault();
    const form=event?.target?.tagName==='FORM'?event.target:null;
    if(form && !form.checkValidity()){form.reportValidity();notice('Проверьте поля формы: укажите почту и заполните обязательные значения. Пароль — от 12 символов.');return;}
    if(form?.dataset.busy==='true')return;
    const button=event?.submitter||(event?.currentTarget?.tagName==='BUTTON'?event.currentTarget:null);
    const label=button?.textContent;
    if(form){form.dataset.busy='true';form.setAttribute('aria-busy','true');}
    if(button){button.disabled=true;button.textContent='Выполняем…';}
    notice('Выполняем запрос…');
    try{await fn(event);if(document.getElementById('message')?.querySelector('span')?.textContent==='Выполняем запрос…')notice('Готово.');}catch(error){notice(error.message,true);}finally{
      if(form){delete form.dataset.busy;form.removeAttribute('aria-busy');}
      if(button){button.disabled=false;button.textContent=label;}
    }
  };
  function bindForms(){
    for(const form of document.forms){form.noValidate=true;form.addEventListener('input',()=>form.querySelectorAll('[aria-invalid]').forEach(input=>input.removeAttribute('aria-invalid')));}
  }
  bindForms();
  function csv(rows){
    return '\uFEFF'+rows.map(row=>row.map(value=>{let text=String(value??'');if(/^[\s]*[=+@-]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';}).join(';')).join('\r\n');
  }
  function downloadCsv(name,rows){
    const url=URL.createObjectURL(new Blob([csv(rows)],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return {request,run,notice,csv,downloadCsv};
})();
