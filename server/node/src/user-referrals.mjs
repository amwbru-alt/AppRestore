import { ApiError } from './service.mjs';

export function referralCode(value) {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value !== 'string' || !/^RVP-[A-F0-9]{12}$/.test(value.trim().toUpperCase())) throw new ApiError(422, 'unknown_referral');
  return value.trim().toUpperCase();
}

// Called inside the same transaction as user creation. Invalid codes create no user.
export async function registerReferred(pool, {id,email,encoded,code}) {
  const db=await pool.getConnection();
  try {
    await db.beginTransaction();
    const [partners]=await db.execute('SELECT account_id FROM apprevive_partners WHERE referral_code=?',[code]);
    if(!partners.length)throw new ApiError(422,'unknown_referral');
    await db.execute('INSERT INTO apprevive_users(user_id,email,password_hash) VALUES (?,?,?)',[id,email,encoded]);
    await db.execute('INSERT INTO apprevive_user_referrals(user_id,partner_id) VALUES (?,?)',[id,partners[0].account_id]);
    await db.commit();
  } catch(error){await db.rollback();throw error;} finally{db.release();}
}

// Resolve the immutable registration attribution using the verified Apple ID link.
export async function registrationPartner(db,buyer) {
  const [rows]=await db.execute('SELECT r.partner_id FROM apprevive_user_accounts a JOIN apprevive_user_referrals r ON r.user_id=a.user_id WHERE a.account_id=?',[buyer]);
  return rows[0]?.partner_id || null;
}

export async function registrationSummary(db,partner) {
  const [counts]=await db.execute('SELECT COUNT(*) AS total FROM apprevive_user_referrals WHERE partner_id=?',[partner]);
  const [rows]=await db.execute("SELECT r.user_id,r.created_at,COUNT(o.order_id) AS paid_orders,COALESCE(SUM(o.quantity),0) AS purchased_codes,COALESCE(SUM(o.amount_kopecks),0) AS revenue_kopecks,COALESCE(SUM(c.amount_kopecks),0) AS commission_kopecks FROM apprevive_user_referrals r LEFT JOIN apprevive_user_accounts a ON a.user_id=r.user_id LEFT JOIN apprevive_orders o ON o.buyer_id=a.account_id AND o.partner_id=r.partner_id AND o.state='paid' LEFT JOIN apprevive_commissions c ON c.order_id=o.order_id AND c.partner_id=r.partner_id AND c.state='active' WHERE r.partner_id=? GROUP BY r.user_id,r.created_at ORDER BY r.created_at DESC,r.user_id LIMIT 100",[partner]);
  const [legacy]=await db.execute('SELECT COUNT(*) AS total FROM apprevive_referrals f WHERE f.partner_id=? AND NOT EXISTS (SELECT 1 FROM apprevive_user_accounts a JOIN apprevive_user_referrals r ON r.user_id=a.user_id WHERE a.account_id=f.buyer_id AND r.partner_id=f.partner_id)',[partner]);
  const [buyers]=await db.execute("SELECT COUNT(DISTINCT COALESCE(a.user_id,o.buyer_id)) AS total FROM apprevive_orders o LEFT JOIN apprevive_user_accounts a ON a.account_id=o.buyer_id WHERE o.partner_id=? AND o.state='paid'",[partner]);
  return {paid_buyers:Number(buyers[0].total),registered:Number(counts[0].total),invited:Number(counts[0].total)+Number(legacy[0].total),registrations:rows.map(r=>({buyer:r.user_id.slice(0,12),created_at:r.created_at,paid_orders:Number(r.paid_orders),purchased_codes:Number(r.purchased_codes),revenue_kopecks:Number(r.revenue_kopecks),commission_kopecks:Number(r.commission_kopecks)}))};
}
