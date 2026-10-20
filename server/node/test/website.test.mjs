import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApi } from '../src/http.mjs';
import { createWebsite } from '../src/website.mjs';

async function setup(t, config = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'apprevive-web-'));
  const website = createWebsite({ downloadsDir: dir, macUrl: '', windowsUrl: '', ...config });
  const service = { catalog: async () => ({ status: 'ok', apps: [{ trackId: '492224193', name: 'Каталог AppRevive', iconUrl: '' }] }), redeem: async () => ({ status: 'activated' }) };
  const server = createApi(service, { requireHttps: false, website });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }); await rm(dir, { recursive: true, force: true }); });
  return { url: `http://127.0.0.1:${server.address().port}`, dir };
}
test('site serves its own page and bundled assets; API continues to work', async t => {
  const { url } = await setup(t);
  const page = await fetch(url + '/');
  assert.equal(page.status, 200);
  assert.match(page.headers.get('content-security-policy'), /object-src 'none'/);
  const html = await page.text();
  assert(html.includes('AppRevive')); assert(html.includes('/download/macos')); assert(!html.includes('appback.ru'));
  for (const path of ['/assets/site.css', '/assets/site.js', '/assets/onest.ttf', '/assets/apprevive.png', '/account', '/admin', '/assets/portal.css', '/assets/account.js', '/assets/admin.js']) {
    const asset = await fetch(url + path); assert.equal(asset.status, 200); assert((await asset.arrayBuffer()).byteLength > 0);
  }
  assert.equal((await (await fetch(url + '/v1/catalog')).json()).apps.length, 1);
  assert.equal((await (await fetch(url + '/health')).json()).status, 'ok');
});
test('unpublished downloads are clearly reported instead of fake installers', async t => {
  const { url } = await setup(t);
  assert.deepEqual((await (await fetch(url + '/site-config')).json()).downloads, { macos: false, windows: false });
  const response = await fetch(url + '/download/macos');
  assert.equal(response.status, 503); assert.match(response.headers.get('content-type'), /text\/html/);
  assert((await response.text()).includes('Архив пока'));
});
test('ZIP streaming, HEAD and byte ranges support actual downloads', async t => {
  const { url, dir } = await setup(t);
  await writeFile(join(dir, 'AppRevive-macOS.zip'), 'ZIP-EXAMPLE');
  const config = await (await fetch(url + '/site-config')).json(); assert.equal(config.downloads.macos, true);
  const full = await fetch(url + '/download/macos');
  assert.equal(full.status, 200); assert.match(full.headers.get('content-disposition'), /AppRevive-macOS.zip/); assert.equal(await full.text(), 'ZIP-EXAMPLE');
  const head = await fetch(url + '/download/macos', { method: 'HEAD' }); assert.equal(head.headers.get('content-length'), '11'); assert.equal(await head.text(), '');
  const part = await fetch(url + '/download/macos', { headers: { Range: 'bytes=4-6' } }); assert.equal(part.status, 206); assert.equal(await part.text(), 'EXA');
  const suffix = await fetch(url + '/download/macos', { headers: { Range: 'bytes=-3' } }); assert.equal(await suffix.text(), 'PLE');
  const bad = await fetch(url + '/download/macos', { headers: { Range: 'bytes=999-' } }); assert.equal(bad.status, 416);
});
test('no arbitrary files, credentials or public installer upload routes are exposed', async t => {
  const { url } = await setup(t);
  for (const path of ['/.env', '/src/db.mjs', '/assets/../../.env', '/download/constructor', '/download/__proto__']) assert.equal((await fetch(url + path)).status, 404);
  const post = await fetch(url + '/download/windows', { method: 'POST' }); assert.equal(post.status, 405);
  const invalid = await setup(t, { macUrl: 'javascript:alert(1)', windowsUrl: 'https://user:password@example.com/a.zip' });
  assert.deepEqual((await (await fetch(invalid.url + '/site-config')).json()).downloads, { macos: false, windows: false });
});
test('operator may configure direct HTTP or HTTPS download URLs', async t => {
  const { url } = await setup(t, { macUrl: 'https://downloads.example.org/AppRevive.zip' });
  const response = await fetch(url + '/download/macos', { redirect: 'manual' }); assert.equal(response.status, 302);
  assert.equal(response.headers.get('location'), 'https://downloads.example.org/AppRevive.zip');
});

test('website exposes explicit HTTP transport settings and serves the shared transport script', async t => {
  const { url }=await setup(t,{env:{ALLOW_HTTP:'true',ALLOW_HTTP_AUTH:'true',PUBLIC_URL:'http://185.173.93.200:3000'}});
  const config=await (await fetch(url+'/site-config')).json();
  assert.equal(config.transport.http_auth_origin,'http://185.173.93.200:3000');
  assert.equal((await fetch(url+'/assets/transport.js')).status,200);
  for(const page of ['/account','/admin'])assert.match(await (await fetch(url+page)).text(),/transport\.js.*(?:account|admin)\.js/);
});

test('HTML uses content-versioned scripts and JavaScript revalidates instead of staying stale for an hour',async t=>{
 const {url}=await setup(t);const html=await(await fetch(url+'/account')).text();
 for(const script of ['transport','portal','account'])assert.match(html,new RegExp('/assets/'+script+'\\.js\\?v=[a-f0-9]{12}'));
 const asset=await fetch(url+'/assets/portal.js?v=old-version');assert.equal(asset.status,200);assert.equal(asset.headers.get('cache-control'),'no-cache');
 const head=await fetch(url+'/account',{method:'HEAD'});assert.equal(Number(head.headers.get('content-length')),Buffer.byteLength(html));
});

test('account aliases preserve invitation and admin destination without external redirects',async t=>{
 const {url:base}=await setup(t);
 for(const [path,target] of [['/register?ref=RVP-123456ABCDEF','/account?ref=RVP-123456ABCDEF#register-form'],['/login?next=admin','/account?next=admin#login-form'],['/partners','/account#partners'],['/account/','/account']]){
  const response=await fetch(base+path,{redirect:'manual'});assert.equal(response.status,302);assert.equal(response.headers.get('location'),target);
 }
});
test('commercial documents are reachable, explicit drafts, and preserve API behaviour', async t => {
  const { url } = await setup(t, { env: { DB_PASSWORD: 'must-not-leak' } });
  const paths = ['/legal','/terms','/offer','/privacy','/refund','/cookies','/contacts','/instructions','/referral-terms'];
  for (const path of paths) {
    const response = await fetch(url + path); const html = await response.text();
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.match(html, /Проект документов/); assert.match(html, /name="robots" content="noindex"/);
    assert(!html.includes('must-not-leak'));
    assert.match(html, /legal\.css\?v=[a-f0-9]{12}/);
    const head = await fetch(url + path, { method: 'HEAD' });
    assert.equal(await head.text(), ''); assert.equal(Number(head.headers.get('content-length')), Buffer.byteLength(html));
    assert.equal((await fetch(url + path, { method:'POST' })).status, 405);
  }
  assert.match(await (await fetch(url + '/offer')).text(), /а не доказательство успешной установки/);
  assert.match(await (await fetch(url + '/instructions')).text(), /Apple ID на сайте вводить не нужно/);
  for (const path of ['/', '/account']) assert.match(await (await fetch(url + path)).text(), /href="\/offer"/);
});
test('operator configuration is escaped and only complete documents can be indexed', async t => {
  const env = { LEGAL_OPERATOR_NAME:'ИП <script>alert(1)</script>', LEGAL_OPERATOR_INN:'123', LEGAL_OPERATOR_OGRNIP:'456', LEGAL_OPERATOR_ADDRESS:'Адрес', LEGAL_CONTACT_EMAIL:'support@example.test', LEGAL_DATA_LOCATION:'Указанное оператором место', DB_PASSWORD:'secret-test' };
  const { url } = await setup(t, { env });
  const html = await (await fetch(url + '/contacts')).text();
  assert(!html.includes('<script>')); assert(html.includes('&lt;script&gt;')); assert(!html.includes('secret-test'));
  assert(!html.includes('Проект документов')); assert(!html.includes('content="noindex"'));
});
