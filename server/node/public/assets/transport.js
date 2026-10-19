'use strict';
window.AppReviveTransport = (() => {
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  const ready = location.protocol === 'https:' || local ? Promise.resolve(true) :
    fetch('/site-config', {cache:'no-store', credentials:'omit'}).then(r => r.ok ? r.json() : null)
      .then(config => config?.transport?.http_auth_origin === location.origin).catch(() => false);
  return {
    ready,
    async requireAllowed() { if (!await ready) throw Error('Вход по HTTP не включён для этого адреса. Проверьте настройки сервера или используйте HTTPS.'); },
    requestId() { const bytes = new Uint8Array(16); crypto.getRandomValues(bytes); return Array.from(bytes, n => n.toString(16).padStart(2,'0')).join(''); }
  };
})();
