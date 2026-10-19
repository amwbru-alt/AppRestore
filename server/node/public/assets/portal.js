'use strict';
window.AppRevivePortal = (() => {
  const labels = {
    https_required:'Вход и регистрация по HTTP ещё не включены на сервере. Обратитесь к администратору.',
    service_login_required:'Войдите в AppRevive.', login_failed_or_unverified:'Неверная почта/пароль или почта ещё не подтверждена.',
    password_min_12:'Пароль AppRevive должен содержать от 12 символов.', invalid_email:'Введите корректный адрес электронной почты.',
    mail_not_configured:'Отправка писем пока не настроена на сервере. Администратор должен подключить почтовый сервис.',
    mail_unavailable:'Почтовый сервис не принял письмо. Повторите позже или обратитесь к администратору.',
    payments_not_configured:'Приём оплаты пока не настроен.', verify_apple_email_required:'Подтвердите почту этого Apple ID.',
    apple_already_linked:'Этот Apple ID уже привязан к другому аккаунту AppRevive.',
    invalid_or_expired_token:'Ссылка недействительна или истекла. Запросите новое письмо.',
    login_as_link_requester:'Войдите в аккаунт AppRevive, из которого запрашивали привязку Apple ID.',
    invalid_code:'Код не найден или уже использован.', rate_limited:'Слишком много запросов. Повторите позже.',
    admin_required:'Недостаточно прав. Войдите как администратор.', unavailable:'Сервер временно недоступен. Повторите позже.'
  };
  const notice = (text,focus=false) => {
    const box=document.getElementById('message');if(!box)return;
    box.textContent=text;if(focus){box.tabIndex=-1;box.focus({preventScroll:true});if(box.scrollIntoView)box.scrollIntoView({block:'nearest'});}
  };
  async function request(path,body) {
    if(!window.AppReviveTransport)throw Error('Не загрузился модуль подключения. Обновите страницу.');
    await AppReviveTransport.requireAllowed();
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
    try {
      const response=await fetch(path,{signal:controller.signal,credentials:'same-origin',method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
      let data;try{data=await response.json();}catch{throw Error('Сервер вернул некорректный ответ. Проверьте обновление API и повторите позже.');}
      if(!data || typeof data!=='object')throw Error('Сервер вернул некорректный ответ. Обновите страницу и повторите.');
      if(!response.ok){const error=Error(labels[data.status]||'Операция не выполнена. Код: '+(data.status||response.status));error.status=response.status;throw error;}
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
    try{await fn(event);if(document.getElementById('message')?.textContent==='Выполняем запрос…')notice('Готово.');}catch(error){notice(error.message,true);}finally{
      if(form){delete form.dataset.busy;form.removeAttribute('aria-busy');}
      if(button){button.disabled=false;button.textContent=label;}
    }
  };
  function bindForms(){
    for(const form of document.forms){form.noValidate=true;form.addEventListener('input',()=>form.querySelectorAll('[aria-invalid]').forEach(input=>input.removeAttribute('aria-invalid')));}
  }
  bindForms();
  return {request,run,notice};
})();
