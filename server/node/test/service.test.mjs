import test from 'node:test';
import assert from 'node:assert/strict';
import { PromoService, activationInput, hash } from '../src/service.mjs';
import { MemoryPool } from './memory-pool.mjs';
const request = (code = 'ONE', owner = 'a', id = 'b') => ({ code, installation_token: owner.repeat(64), request_id: id.repeat(32) });

test('activation deletes code and creates a hashed receipt', async () => {
  const pool = new MemoryPool();
  const result = await new PromoService(pool).redeem(request());
  assert.equal(pool.codes.size, 0); assert.equal(pool.receipts.length, 1);
  assert.equal(result.code_hash, hash('ONE')); assert.equal(result.credits, 1);
  assert(!JSON.stringify(pool.receipts).includes('ONE'));
});
test('lost response retry returns the same receipt', async () => {
  const pool = new MemoryPool(), service = new PromoService(pool);
  const first = await service.redeem(request());
  assert.deepEqual(await service.redeem(request()), first);
  assert.equal(pool.receipts.length, 1);
});
test('simultaneous clients cannot consume one code twice', async () => {
  const pool = new MemoryPool(), service = new PromoService(pool);
  const results = await Promise.allSettled([service.redeem(request()), service.redeem(request('ONE', 'c', 'd'))]);
  assert.equal(results.filter(item => item.status === 'fulfilled').length, 1);
  assert.equal(pool.receipts.length, 1);
});
test('simultaneous retries with same identity are idempotent', async () => {
  const pool = new MemoryPool(), service = new PromoService(pool);
  const results = await Promise.all(Array.from({ length: 5 }, () => service.redeem(request())));
  assert(results.every(item => item.code_hash === hash('ONE')));
  assert.equal(pool.receipts.length, 1);
});
test('failure between DELETE and INSERT rolls back the code', async () => {
  const pool = new MemoryPool(); pool.failInsert = true;
  await assert.rejects(new PromoService(pool).redeem(request()));
  assert(pool.codes.has('ONE')); assert.equal(pool.receipts.length, 0);
});
test('reuse of request ID for another code does not delete it', async () => {
  const pool = new MemoryPool(['ONE', 'TWO']), service = new PromoService(pool);
  await service.redeem(request());
  await assert.rejects(service.redeem(request('TWO')), { status: 409 });
  assert(pool.codes.has('TWO'));
});
test('reinserted used code cannot be activated by another installation', async () => {
  const pool = new MemoryPool(), service = new PromoService(pool);
  await service.redeem(request()); pool.codes.add('ONE');
  await assert.rejects(service.redeem(request('ONE', 'c', 'd')), { status: 422 });
});
test('code comparison is exact and SQL injection remains data', async () => {
  const service = new PromoService(new MemoryPool());
  await assert.rejects(service.redeem(request('one')), { status: 422 });
  await assert.rejects(service.redeem(request("' OR 1=1 --")), { status: 422 });
});
test('invalid inputs rejected before database access', () => {
  for (const value of [null, [], {}, request(''), request('A\nB'), request('x'.repeat(257)), { ...request(), installation_token: 'invalid' }]) assert.throws(() => activationInput(value), { status: 400 });
});
