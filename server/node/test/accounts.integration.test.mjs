import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createDatabase } from '../src/db.mjs';
import { AccountService } from '../src/accounts.mjs';

test('MySQL account ledger survives reinstall and serializes concurrent spending', { skip: process.env.APPREVIVE_TEST_MYSQL !== '1' }, async t => {
  if (!/^apprevive_test(?:_[a-z0-9]+)?$/.test(process.env.DB_NAME || '')) throw Error('Use isolated test database');
  const pool = createDatabase();
  t.after(() => pool.end());
  for (const file of ['schema.sql', 'accounts-schema.sql']) {
    const sql = await readFile(new URL('../../promo/' + file, import.meta.url), 'utf8');
    for (const statement of sql.split(';').filter(part => part.trim())) await pool.query(statement);
  }
  const service = new AccountService(pool);
  const body = { account_id: '9'.repeat(64) };
  const op = id => ({ ...body, request_id: id.repeat(32) });
  assert.equal((await service.balance(body)).credits, 1);
  assert.equal((await new AccountService(pool).balance(body)).credits, 1);
  const race = await Promise.allSettled([service.reserve(op('1')), service.reserve(op('2'))]);
  assert.equal(race.filter(r => r.status === 'fulfilled').length, 1);
  const winner = race.find(r => r.status === 'fulfilled').value;
  assert.equal((await service.balance(body)).credits, 0);
  assert.equal((await service.reserve({ ...body, request_id: winner.request_id })).status, 'reserved');
  const completed = { ...body, request_id: winner.request_id, success: true };
  await Promise.all([service.finish(completed), service.finish(completed)]);
  assert.equal((await service.balance(body)).installations, 1);
  assert.equal((await service.balance(body)).credits, 0);
  await assert.rejects(service.finish({ ...completed, success: false }), error => error.status === 409);
  await assert.rejects(service.reserve(op('3')), error => error.status === 402);
  await pool.execute('INSERT INTO apprevive_promo_codes (code) VALUES (?)', [Buffer.from('ACCOUNT-CREDIT')]);
  const code = { ...op('4'), code: 'ACCOUNT-CREDIT' };
  await Promise.all([service.redeem(code), service.redeem({ ...code, request_id: '5'.repeat(32) })]);
  assert.equal((await service.balance(body)).credits, 1);
  await service.reserve(op('6'));
  await Promise.all([service.finish({ ...op('6'), success: false }), service.finish({ ...op('6'), success: false })]);
  assert.equal((await service.balance(body)).credits, 1);
  assert.equal((await service.balance(body)).installations, 1);
  const other = { account_id: '8'.repeat(64) };
  assert.equal((await service.balance(other)).credits, 1);
  await assert.rejects(service.redeem({ ...other, code: 'ACCOUNT-CREDIT', request_id: '7'.repeat(32) }), error => error.status === 422);
});
