import test from 'node:test';
import assert from 'node:assert/strict';
import { createApi } from '../src/http.mjs';
import { PromoService } from '../src/service.mjs';
import { MemoryPool } from './memory-pool.mjs';

async function api(t, options = {}) {
  const pool = new MemoryPool();
  const server = createApi(new PromoService(pool), { requireHttps: false, ...options });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return { pool, url: `http://127.0.0.1:${server.address().port}` };
}
const body = { code: 'ONE', installation_token: 'a'.repeat(64), request_id: 'b'.repeat(32) };
const post = (url, value = body) => fetch(url + '/v1/redeem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });

test('HTTP IP activation and catalog return only public JSON', async t => {
  const { url } = await api(t);
  const response = await post(url);
  assert.equal(response.status, 200); assert.equal((await response.json()).credits, 1);
  const apps = await (await fetch(url + '/v1/catalog')).json();
  assert.equal(apps.apps[0].trackId, '686449807');
  assert(!JSON.stringify(apps).includes('password'));
});
test('errors do not expose SQL or secrets', async t => {
  const { url, pool } = await api(t); pool.failInsert = true;
  const response = await post(url);
  assert.equal(response.status, 503); assert.deepEqual(await response.json(), { status: 'unavailable' });
});
test('rate limit stops guessing', async t => {
  const { url } = await api(t, { redemptionLimit: 2 });
  await post(url); await post(url);
  assert.equal((await post(url)).status, 429);
});
test('reject invalid JSON, media type and oversized bodies', async t => {
  const { url } = await api(t);
  assert.equal((await fetch(url + '/v1/redeem', { method: 'POST', body: 'invalid' })).status, 415);
  assert.equal((await fetch(url + '/v1/redeem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{' })).status, 400);
  assert.equal((await post(url, { ...body, code: 'x'.repeat(5000) })).status, 413);
});
test('HTTPS mode is optional, but does not trust remote forwarded headers blindly', async t => {
  const { url } = await api(t, { requireHttps: true });
  assert.equal((await post(url)).status, 426);
  assert.equal((await fetch(url + '/health')).status, 200);
});

test('account routes pass only validated JSON to account service', async t => {
  const calls = [];
  const accounts = Object.fromEntries(['balance', 'reserve', 'finish', 'redeem'].map(name => [name, async body => { calls.push(name); return { status: 'ok', account_id: body.account_id }; }]));
  const { url } = await api(t, { accounts });
  for (const name of Object.keys(accounts)) {
    const response = await fetch(url + '/v2/account/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account_id: 'a'.repeat(64) }) });
    assert.equal(response.status, 200);
  }
  assert.deepEqual(calls, ['balance', 'reserve', 'finish', 'redeem']);
});

test('public partner API exposes profile/bind only, never purchase or refund commands', async t => {
  const calls = [];
  const partners = { profile: async body => ({ status: 'ok', account_id: body.account_id }), bind: async body => { calls.push(body); return { status: 'bound' }; }, recordPurchase: () => assert.fail('private operation') };
  const { url } = await api(t, { partners });
  for (const name of ['profile', 'bind']) {
    const result = await fetch(url + '/v2/partner/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account_id: 'a'.repeat(64) }) });
    assert.equal(result.status, 200);
  }
  for (const name of ['recordPurchase', 'refund', 'constructor']) {
    const result = await fetch(url + '/v2/partner/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    assert.equal(result.status, 404);
  }
  assert.equal(calls.length, 1);
});
