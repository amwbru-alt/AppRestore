import { accrueCommission, commissionPolicy, readPolicy, ledgerBalance } from './ledger.mjs';
import { randomBytes } from 'node:crypto';
import { AccountService } from './accounts.mjs';
import { ApiError, hash } from './service.mjs';

const account = value => {
  if (typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value)) throw new ApiError(400, 'invalid_account');
  return value;
};
export class PartnerService {
  constructor(pool, policy = commissionPolicy()) { this.pool = pool; this.accounts = new AccountService(pool); this.policy = policy; }
  async profile(body) {
    const id = account(body?.account_id);
    return this.accounts.transaction(id, async db => {
      let [own] = await db.execute('SELECT referral_code FROM apprevive_partners WHERE account_id=?', [id]);
      if (!own.length) {
        const code = 'RVP-' + randomBytes(6).toString('hex').toUpperCase();
        await db.execute('INSERT INTO apprevive_partners (account_id,referral_code) VALUES (?,?)', [id, code]);
        own = [{ referral_code: code }];
      }
      const [binding] = await db.execute('SELECT p.referral_code FROM apprevive_referrals r JOIN apprevive_partners p ON p.account_id=r.partner_id WHERE r.buyer_id=?', [id]);
      const [invited] = await db.execute('SELECT COUNT(*) AS total FROM apprevive_referrals WHERE partner_id=?', [id]);
      const [paid] = await db.execute("SELECT COUNT(*) AS orders, COUNT(DISTINCT buyer_id) AS buyers, COALESCE(SUM(quantity),0) AS codes, COALESCE(SUM(amount_kopecks),0) AS revenue FROM apprevive_orders WHERE partner_id=? AND state='paid'", [id]);
      const [referrals] = await db.execute("SELECT r.buyer_id,r.created_at,COUNT(o.order_id) AS paid_orders,COALESCE(SUM(o.quantity),0) AS purchased_codes,COALESCE(SUM(o.amount_kopecks),0) AS revenue_kopecks FROM apprevive_referrals r LEFT JOIN apprevive_orders o ON o.buyer_id=r.buyer_id AND o.partner_id=r.partner_id AND o.state='paid' WHERE r.partner_id=? GROUP BY r.buyer_id,r.created_at ORDER BY r.created_at DESC LIMIT 100", [id]);
      const policy = await readPolicy(db, this.policy);
      const ledger = await ledgerBalance(db, id);
      return { status: 'ok', referrals: referrals.map(r => ({ buyer: r.buyer_id.slice(0,12), created_at: r.created_at, paid_orders: Number(r.paid_orders), purchased_codes: Number(r.purchased_codes), revenue_kopecks: Number(r.revenue_kopecks) })), ledger, commission_rate_bps: policy.rate, hold_days: policy.days, account_id: id, referral_code: own[0].referral_code, invited_by: binding[0]?.referral_code || '',
        invited: Number(invited[0].total), paid_buyers: Number(paid[0].buyers), paid_orders: Number(paid[0].orders),
        purchased_codes: Number(paid[0].codes), revenue_kopecks: Number(paid[0].revenue) };
    });
  }
  async bind(body) {
    const buyer = account(body?.account_id);
    const code = typeof body.referral_code === 'string' ? body.referral_code.trim().toUpperCase() : '';
    if (!/^RVP-[A-F0-9]{12}$/.test(code)) throw new ApiError(422, 'unknown_referral');
    return this.accounts.transaction(buyer, async db => {
      const [partner] = await db.execute('SELECT account_id FROM apprevive_partners WHERE referral_code=?', [code]);
      if (!partner.length) throw new ApiError(422, 'unknown_referral');
      if (partner[0].account_id === buyer) throw new ApiError(409, 'self_referral');
      const [prior] = await db.execute('SELECT partner_id FROM apprevive_referrals WHERE buyer_id=?', [buyer]);
      if (prior.length) {
        if (prior[0].partner_id !== partner[0].account_id) throw new ApiError(409, 'referral_locked');
        return { status: 'bound', account_id: buyer, referral_code: code };
      }
      const [orders] = await db.execute('SELECT order_id FROM apprevive_orders WHERE buyer_id=? LIMIT 1', [buyer]);
      if (orders.length) throw new ApiError(409, 'purchase_already_recorded');
      await db.execute('INSERT INTO apprevive_referrals (buyer_id,partner_id) VALUES (?,?)', [buyer, partner[0].account_id]);
      return { status: 'bound', account_id: buyer, referral_code: code };
    });
  }
  // Server-admin only. No public HTTP route may call this method.
  async recordPurchase({ buyer_id, quantity, amount_kopecks, payment_reference }) {
    const buyer = account(buyer_id);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 1000 || !Number.isInteger(amount_kopecks)
      || amount_kopecks < 1 || amount_kopecks > 1000000000 || typeof payment_reference !== 'string'
      || !/^[a-zA-Z0-9._:-]{1,128}$/.test(payment_reference)) throw new ApiError(400, 'invalid_purchase');
    return this.accounts.transaction(buyer, async db => {
      const [previous] = await db.execute('SELECT order_id,buyer_id,quantity,amount_kopecks,state FROM apprevive_orders WHERE payment_reference=? FOR UPDATE', [payment_reference]);
      let order;
      if (previous.length) {
        order = previous[0];
        if (order.buyer_id !== buyer || order.quantity !== quantity || order.amount_kopecks !== amount_kopecks) throw new ApiError(409, 'payment_conflict');
      } else {
        const [referral] = await db.execute('SELECT partner_id FROM apprevive_referrals WHERE buyer_id=?', [buyer]);
        order = { order_id: randomBytes(16).toString('hex'), state: 'paid' };
        await db.execute('INSERT INTO apprevive_orders (order_id,payment_reference,buyer_id,partner_id,quantity,amount_kopecks) VALUES (?,?,?,?,?,?)',
          [order.order_id, payment_reference, buyer, referral[0]?.partner_id || null, quantity, amount_kopecks]);
        await accrueCommission(db, { order: order.order_id, partner: referral[0]?.partner_id || null, amount: amount_kopecks }, await readPolicy(db, this.policy));
        for (let i = 0; i < quantity; i++) {
          const code = 'RV-' + randomBytes(12).toString('hex').toUpperCase();
          await db.execute('INSERT INTO apprevive_promo_codes (code) VALUES (?)', [Buffer.from(code)]);
          await db.execute('INSERT INTO apprevive_order_codes (code_hash,order_id) VALUES (?,?)', [hash(code), order.order_id]);
        }
      }
      const [codes] = await db.execute('SELECT p.code FROM apprevive_order_codes c JOIN apprevive_promo_codes p ON SHA2(p.code,256)=c.code_hash WHERE c.order_id=?', [order.order_id]);
      return { order_id: order.order_id, state: order.state, unused_codes: codes.map(row => Buffer.isBuffer(row.code) ? row.code.toString() : row.code) };
    });
  }
  async refund(payment_reference) {
    const [orders] = await this.pool.execute('SELECT buyer_id FROM apprevive_orders WHERE payment_reference=?', [payment_reference]);
    if (!orders.length) throw new ApiError(404, 'unknown_payment');
    return this.accounts.transaction(orders[0].buyer_id, async db => {
      const [rows] = await db.execute('SELECT order_id FROM apprevive_orders WHERE payment_reference=? FOR UPDATE', [payment_reference]);
      await db.execute("UPDATE apprevive_orders SET state='refunded' WHERE payment_reference=?", [payment_reference]);
      await db.execute("UPDATE apprevive_commissions SET state='void' WHERE order_id=?", [rows[0].order_id]);
      await db.execute('DELETE p FROM apprevive_promo_codes p JOIN apprevive_order_codes c ON SHA2(p.code,256)=c.code_hash WHERE c.order_id=?', [rows[0].order_id]);
      return { order_id: rows[0].order_id, state: 'refunded' };
    });
  }
}
