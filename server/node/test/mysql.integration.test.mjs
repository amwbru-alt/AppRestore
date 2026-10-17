import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createDatabase } from '../src/db.mjs';
import { PromoService } from '../src/service.mjs';

// Explicit opt-in and isolated database: never run against the user's live DB.
test('real MySQL 5.7 transaction contract', { skip: process.env.APPREVIVE_TEST_MYSQL !== '1' }, async t => {
  if (!/^apprevive_test(?:_[a-z0-9]+)?$/.test(process.env.DB_NAME || '')) throw new Error('Use a dedicated apprevive_test database');
  const pool = createDatabase();
  t.after(() => pool.end());
  const sql = await readFile(new URL('../../promo/schema.sql', import.meta.url), 'utf8');
  for (const statement of sql.split(';').filter(part => part.trim())) await pool.query(statement);
  const service = new PromoService(pool);
  const payload = (code, owner = 'a', request = 'b') => ({ code, installation_token: owner.repeat(64), request_id: request.repeat(32) });
  const add = code => pool.execute('INSERT INTO apprevive_promo_codes (code) VALUES (?)', [Buffer.from(code)]);
  await t.test('different installations race for the same code: exactly one succeeds', async () => {
    await add('CONCURRENT');
    const results = await Promise.allSettled([service.redeem(payload('CONCURRENT')), service.redeem(payload('CONCURRENT', 'c', 'd'))]);
    assert.equal(results.filter(item => item.status === 'fulfilled').length, 1);
    assert.equal(results.find(item => item.status === 'rejected').reason.status, 422);
  });
  await t.test('parallel same-request retries recover one committed receipt', async () => {
    await add('RETRY');
    const results = await Promise.all(Array.from({ length: 5 }, () => service.redeem(payload('RETRY', 'e', 'f'))));
    assert(results.every(item => item.credits === 1));
    const [rows] = await pool.execute('SELECT COUNT(*) AS count FROM apprevive_promo_redemptions WHERE owner_hash=? AND request_id=?', [(await import('../src/service.mjs')).hash('e'.repeat(64)), 'f'.repeat(32)]);
    assert.equal(Number(rows[0].count), 1);
  });
  await t.test('failed INSERT after DELETE rolls back the code', async () => {
    await add('ROLLBACK');
    await pool.query("CREATE TRIGGER apprevive_test_failure BEFORE INSERT ON apprevive_promo_redemptions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='forced isolated test failure'");
    try {
      await assert.rejects(service.redeem(payload('ROLLBACK', '1', '2')));
      const [rows] = await pool.execute('SELECT code FROM apprevive_promo_codes WHERE code=?', [Buffer.from('ROLLBACK')]);
      assert.equal(rows.length, 1);
    } finally { await pool.query('DROP TRIGGER apprevive_test_failure'); }
  });
});
