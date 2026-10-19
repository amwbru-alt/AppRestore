import test from 'node:test';
import assert from 'node:assert/strict';
import { validateGroups } from '../src/catalog-groups.mjs';
const group = { id: 't-bank', name: 'Т-Банк', apps: [{ trackId: '455652438', name: 'Old app' }] };
test('bank manifest validates IDs, rejects ambiguous assignments and unsafe artwork', () => {
  assert.equal(validateGroups([group])[0].apps[0].trackId, '455652438');
  assert.throws(() => validateGroups([group, { ...group, id: 'other' }]));
  assert.throws(() => validateGroups([{ ...group, apps: [{ trackId: 'bad', name: 'App' }] }]));
  assert.throws(() => validateGroups([{ ...group, id: '../path' }]));
  assert.equal(validateGroups([{ ...group, iconUrl: 'javascript:alert(1)' }])[0].iconUrl, '');
});
