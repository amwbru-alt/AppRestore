import { randomBytes } from 'node:crypto';
import { ApiError } from './service.mjs';
export function commissionPolicy(env = process.env) {
  const rate = Number(env.PARTNER_COMMISSION_BPS ?? 0), days = Number(env.PARTNER_HOLD_DAYS ?? 14);
  if (!Number.isInteger(rate) || rate < 0 || rate > 10000 || !Number.isInteger(days) || days < 0 || days > 365) throw Error('Invalid commission policy');
  return { rate, days };
}
export async function readPolicy(db, fallback = commissionPolicy()) {
  const [rows] = await db.execute("SELECT value FROM apprevive_settings WHERE name='commission_policy'");
  if (!rows.length) return fallback;
  const value = JSON.parse(rows[0].value);
  return commissionPolicy({ PARTNER_COMMISSION_BPS: value.rate, PARTNER_HOLD_DAYS: value.days });
}
export async function accrueCommission(db, { order, partner, amount }, policy = commissionPolicy()) {
  if (!partner) return;
  const commission = Math.floor(amount * policy.rate / 10000);
  await db.execute("INSERT IGNORE INTO apprevive_commissions(order_id,partner_id,rate_bps,amount_kopecks,available_at) VALUES (?,?,?,?,DATE_ADD(UTC_TIMESTAMP(),INTERVAL ? DAY))", [order, partner, policy.rate, commission, policy.days]);
}
export async function ledgerBalance(db, partner) {
  const [c] = await db.execute("SELECT COALESCE(SUM(IF(state='active' AND available_at<=UTC_TIMESTAMP(),amount_kopecks,0)),0) AS earned, COALESCE(SUM(IF(state='active' AND available_at>UTC_TIMESTAMP(),amount_kopecks,0)),0) AS held FROM apprevive_commissions WHERE partner_id=?", [partner]);
  const [p] = await db.execute("SELECT COALESCE(SUM(IF(state='paid',amount_kopecks,0)),0) AS paid,COALESCE(SUM(IF(state='pending',amount_kopecks,0)),0) AS pending FROM apprevive_payouts WHERE partner_id=?", [partner]);
  const earned = Number(c[0].earned), held = Number(c[0].held), paid = Number(p[0].paid), pending = Number(p[0].pending);
  return { earned_kopecks: earned, held_kopecks: held, paid_kopecks: paid, pending_kopecks: pending, available_kopecks: earned - paid - pending };
}
export class PayoutService {
  constructor(pool, accounts) { this.pool = pool; this.accounts = accounts; }
  async balance(partner) { return ledgerBalance(this.pool, partner); }
  async create(body) {
    if (!/^[a-f0-9]{64}$/.test(body.partner_id || '') || !Number.isInteger(body.amount_kopecks) || body.amount_kopecks < 1 || body.amount_kopecks > 1000000000 || !/^[A-Za-z0-9._:-]{1,128}$/.test(body.reference || '')) throw new ApiError(400, 'invalid_payout');
    return this.accounts.transaction(body.partner_id, async db => {
      const [prior] = await db.execute('SELECT payout_id,partner_id,amount_kopecks,state FROM apprevive_payouts WHERE reference=?', [body.reference]);
      if (prior.length) {
        if (prior[0].partner_id !== body.partner_id || prior[0].amount_kopecks !== body.amount_kopecks) throw new ApiError(409, 'payout_conflict');
        return prior[0];
      }
      const balance = await ledgerBalance(db, body.partner_id);
      if (balance.available_kopecks < body.amount_kopecks) throw new ApiError(409, 'insufficient_commission');
      const id = randomBytes(16).toString('hex');
      await db.execute('INSERT INTO apprevive_payouts(payout_id,partner_id,amount_kopecks,reference) VALUES (?,?,?,?)', [id, body.partner_id, body.amount_kopecks, body.reference]);
      return { payout_id: id, state: 'pending' };
    });
  }
  async finish(body) {
    if (!/^[a-f0-9]{32}$/.test(body.payout_id || '') || !['paid','cancelled'].includes(body.state)) throw new ApiError(400, 'invalid_payout');
    const [rows] = await this.pool.execute('SELECT partner_id FROM apprevive_payouts WHERE payout_id=?', [body.payout_id]);
    if (!rows.length) throw new ApiError(404, 'unknown_payout');
    return this.accounts.transaction(rows[0].partner_id, async db => {
      const [p] = await db.execute('SELECT state FROM apprevive_payouts WHERE payout_id=? FOR UPDATE', [body.payout_id]);
      if (p[0].state !== 'pending' && p[0].state !== body.state) throw new ApiError(409, 'payout_conflict');
      await db.execute('UPDATE apprevive_payouts SET state=? WHERE payout_id=?', [body.state, body.payout_id]);
      return { payout_id: body.payout_id, state: body.state };
    });
  }
}
