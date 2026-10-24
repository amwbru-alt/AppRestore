import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createDatabase } from '../src/db.mjs';
import { PromoService } from '../src/service.mjs';
import { importGroups } from '../src/catalog-groups.mjs';
test('MySQL bank group import and public catalog metadata', { skip: process.env.APPREVIVE_TEST_MYSQL !== '1' }, async t => {
  if (!/^apprevive_test(?:_[a-z0-9]+)?$/.test(process.env.DB_NAME || '')) throw Error('Use isolated database');
  const pool = createDatabase(); t.after(() => pool.end());
  for (const file of ['catalog-schema.sql', 'catalog-groups-schema.sql']) {
    const sql = await readFile(new URL('../../promo/' + file, import.meta.url), 'utf8');
    for (const statement of sql.split(';').filter(s => s.trim())) await pool.query(statement);
  }
  const manifest = [{ id: 't-bank', name: 'Т-Банк', apps: [{ trackId: '455652438', name: 'Original' }, { trackId: '6476151601', name: 'Alternate' }] }];
  await importGroups(pool, manifest);
  let rows = (await new PromoService(pool).catalog()).apps;
  assert.equal(rows.filter(r => r.groupId === 't-bank').length, 2);
  await assert.rejects(importGroups(pool, [...manifest, { ...manifest[0], id: 'duplicate' }]));
  assert.equal((await new PromoService(pool).catalog()).apps.filter(r => r.groupId === 't-bank').length, 2);
  await pool.query("CREATE TRIGGER apprevive_group_failure BEFORE INSERT ON apprevive_catalog_variants FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated test failure'");
  try {
    await assert.rejects(importGroups(pool, [{ id: 'new-bank', name: 'Replacement', apps: [{ trackId: '111111111', name: 'New' }] }]));
    assert.equal((await new PromoService(pool).catalog()).apps.filter(r => r.groupId === 't-bank').length, 2);
  } finally { await pool.query('DROP TRIGGER apprevive_group_failure'); }
  await importGroups(pool, [{ ...manifest[0], apps: [manifest[0].apps[0]] }]);
  rows = (await new PromoService(pool).catalog()).apps;
  assert.equal(rows.filter(r => r.groupId === 't-bank').length, 1);
  assert.equal(rows.find(r => r.trackId === '6476151601').groupId, undefined);
});
