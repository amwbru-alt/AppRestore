import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createDatabase } from '../src/db.mjs';
import { PartnerService } from '../src/partners.mjs';
import { AccountService } from '../src/accounts.mjs';

test('MySQL partner attribution and paid-order ledger', { skip: process.env.APPREVIVE_TEST_MYSQL !== '1' }, async t => {
  if (!/^apprevive_test(?:_[a-z0-9]+)?$/.test(process.env.DB_NAME || '')) throw Error('Use isolated database');
  const pool = createDatabase();
  t.after(() => pool.end());
  for (const name of ['schema.sql', 'accounts-schema.sql', 'partners-schema.sql']) {
    const sql = await readFile(new URL('../../promo/' + name, import.meta.url), 'utf8');
    for (const statement of sql.split(';').filter(s => s.trim())) await pool.query(statement);
  }
  const service = new PartnerService(pool);
  const inviter = { account_id: 'ab'.repeat(32) }, buyer = { account_id: 'bc'.repeat(32) }, other = { account_id: 'cd'.repeat(32) };
  const first = await service.profile(inviter);
  assert.match(first.referral_code, /^RVP-[A-F0-9]{12}$/);
  assert.equal((await new PartnerService(pool).profile(inviter)).referral_code, first.referral_code);
  await assert.rejects(service.bind({ ...inviter, referral_code: first.referral_code }), e => e.code === 'self_referral');
  await service.bind({ ...buyer, referral_code: first.referral_code });
  await service.bind({ ...buyer, referral_code: first.referral_code });
  const second = await service.profile(other);
  await assert.rejects(service.bind({ ...buyer, referral_code: second.referral_code }), e => e.code === 'referral_locked');
  assert.equal((await service.profile(inviter)).invited, 1);
  const purchase = { buyer_id: buyer.account_id, quantity: 2, amount_kopecks: 20000, payment_reference: 'TEST-PAID-1' };
  const orders = await Promise.all([service.recordPurchase(purchase), service.recordPurchase(purchase)]);
  assert.equal(orders[0].order_id, orders[1].order_id);
  assert.deepEqual(orders[0].unused_codes.sort(), orders[1].unused_codes.sort());
  assert.equal(orders[0].unused_codes.length, 2);
  await assert.rejects(service.recordPurchase({ ...purchase, quantity: 3 }), e => e.code === 'payment_conflict');
  let stats = await service.profile(inviter);
  assert.equal(stats.paid_buyers, 1); assert.equal(stats.paid_orders, 1);
  assert.equal(stats.purchased_codes, 2); assert.equal(stats.revenue_kopecks, 20000);
  // Redemption of a purchased code is not a second purchase.
  await new AccountService(pool).redeem({ account_id: buyer.account_id, code: orders[0].unused_codes[0], request_id: 'af'.repeat(16) });
  assert.equal((await service.profile(inviter)).purchased_codes, 2);
  // Refunded orders cannot be reissued or counted twice.
  await service.refund(purchase.payment_reference);
  await service.refund(purchase.payment_reference);
  const replay = await service.recordPurchase(purchase);
  assert.equal(replay.state, 'refunded'); assert.equal(replay.unused_codes.length, 0);
  stats = await service.profile(inviter);
  assert.equal(stats.invited, 1); assert.equal(stats.paid_orders, 0); assert.equal(stats.revenue_kopecks, 0);
  await service.recordPurchase({ ...purchase, payment_reference: 'TEST-PAID-2', quantity: 1, amount_kopecks: 10000 });
  stats = await service.profile(inviter);
  assert.equal(stats.purchased_codes, 1);
  // No retroactive attribution after a paid order, even after its refund.
  const organic = 'ef'.repeat(32);
  await service.recordPurchase({ ...purchase, buyer_id: organic, payment_reference: 'TEST-ORGANIC' });
  await assert.rejects(service.bind({ account_id: organic, referral_code: first.referral_code }), e => e.code === 'purchase_already_recorded');
});
