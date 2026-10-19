'use strict';
const normalize = text => String(text).toLocaleLowerCase('ru').replaceAll('ё', 'е');
const grid = document.querySelector('#catalog');
const search = document.querySelector('#app-search');
let apps = [];
function renderApps() {
  const query = normalize(search.value.trim());
  const result = apps.filter(app => normalize(app.name).includes(query)).slice(0, 8);
  grid.replaceChildren();
  if (!result.length) {
    const message = document.createElement('p');
    message.className = 'catalog-message';
    message.textContent = query ? 'В каталоге не нашли. Попробуйте поиск в AppRevive.' : 'Каталог пока пуст. Проверьте приложения в AppRevive.';
    grid.append(message); return;
  }
  for (const app of result) {
    const card = document.createElement('a'); card.className = 'app-card'; card.href = '#download';
    const placeholder = document.createElement('span'); placeholder.className = 'app-placeholder'; placeholder.textContent = '↺'; placeholder.setAttribute('aria-hidden', 'true');
    card.append(placeholder);
    try {
      const url = new URL(app.iconUrl);
      if (url.protocol === 'https:' && !url.username && !url.password) {
        const img = document.createElement('img'); img.src = url.href; img.alt = ''; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
        img.addEventListener('error', () => img.replaceWith(placeholder), { once: true });
        placeholder.replaceWith(img);
      }
    } catch { /* use a neutral local placeholder */ }
    const text = document.createElement('div'); const name = document.createElement('h3'); name.textContent = app.name;
    const caption = document.createElement('span'); caption.textContent = 'Проверить в AppRevive ↗';
    text.append(name, caption); card.append(text); grid.append(card);
  }
}
search.addEventListener('input', () => { if (apps.length) renderApps(); });
fetch('/v1/catalog', { headers: { Accept: 'application/json' } }).then(async response => {
  if (!response.ok) throw Error('unavailable');
  const data = await response.json();
  if (data.status !== 'ok' || !Array.isArray(data.apps)) throw Error('bad catalog');
  apps = data.apps.filter(app => typeof app.name === 'string' && app.name.trim()); renderApps();
}).catch(() => {
  grid.replaceChildren(); const p = document.createElement('p'); p.className = 'catalog-message';
  p.textContent = 'Каталог сейчас недоступен. Поиск можно продолжить в AppRevive.'; grid.append(p);
});
fetch('/site-config').then(response => response.ok ? response.json() : Promise.reject()).then(data => {
  for (const [platform, id] of [['macos', 'mac-status'], ['windows', 'windows-status']]) {
    document.getElementById(id).textContent = data.downloads?.[platform] ? 'Архив готов к скачиванию' : 'Архив ещё не опубликован. Свяжитесь с поддержкой.';
  }
}).catch(() => { for (const id of ['mac-status', 'windows-status']) document.getElementById(id).textContent = 'Наличие архива проверим по кнопке скачивания.'; });
const referral = new URLSearchParams(location.search).get('ref')?.trim().toUpperCase();
if (referral && /^RVP-[A-F0-9]{12}$/.test(referral)) {
  document.getElementById('referral').hidden = false;
  document.getElementById('referral-code').value = referral;
  document.getElementById('copy-referral').addEventListener('click', async () => {
    const field = document.getElementById('referral-code'); field.select();
    try { await navigator.clipboard.writeText(referral); document.getElementById('copy-status').textContent = 'Скопировано. Введите код в AppRevive до первой покупки.'; }
    catch { field.focus(); field.select(); document.getElementById('copy-status').textContent = 'Скопируйте выделенный код вручную.'; }
  });
}
