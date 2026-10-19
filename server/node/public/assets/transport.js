'use strict';
window.AppReviveTransport = (() => {
  const local=['localhost','127.0.0.1','[::1]'].includes(location.hostname);
  const warning='Вход и регистрация по HTTP пока заблокированы настройками сервера. Администратор должен включить HTTP-режим и перезапустить сервис.';
  let pending;
  function check(){
    if(location.protocol==='https:'||local)return Promise.resolve(true);
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
    return fetch('/site-config',{cache:'no-store',credentials:'omit',signal:controller.signal})
      .then(response=>response.ok?response.json():null)
      .then(config=>config?.transport?.http_auth_origin===location.origin)
      .catch(()=>false).finally(()=>clearTimeout(timer));
  }
  pending=check();
  return {
    get ready(){return pending;},
    retry(){pending=check();return pending;},
    async requireAllowed(){if(!await pending)throw Error(warning);},
    requestId(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('');}
  };
})();
