import { publicLinksAllowed } from './transport.mjs';
import { randomBytes, scrypt as scryptCallback, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';
import { ApiError, hash } from './service.mjs';
const scrypt = promisify(scryptCallback);
export function normalizeEmail(value) {
  if (typeof value !== 'string') throw new ApiError(400, 'invalid_email');
  const email = value.trim().toLowerCase();
  if (email.length > 254 || !/^[a-z0-9.!#$%&'*+\/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}$/.test(email)) throw new ApiError(400, 'invalid_email');
  return email;
}
export const appleId = email => hash('apprevive-account-v1:' + normalizeEmail(email));
export async function passwordHash(password) {
  if (typeof password !== 'string' || password.length < 12 || Buffer.byteLength(password) > 256) throw new ApiError(400, 'password_min_12');
  const salt = randomBytes(16).toString('hex');
  const key = await scrypt(password, salt, 64, { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
  return `scrypt:${salt}:${key.toString('hex')}`;
}
export async function verifyPassword(password, stored) {
  const parts = String(stored || '').split(':');
  if (typeof password !== 'string' || Buffer.byteLength(password) > 256) return false;
  const salt = parts[0] === 'scrypt' && /^[a-f0-9]{32}$/.test(parts[1] || '') ? parts[1] : '0'.repeat(32);
  const key = await scrypt(password, salt, 64, { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
  return /^[a-f0-9]{128}$/.test(parts[2] || '') && timingSafeEqual(key, Buffer.from(parts[2], 'hex'));
}
export async function sendMail({ email, purpose, token }, env = process.env) {
  if (!env.RESEND_API_KEY || !env.MAIL_FROM || !publicLinksAllowed(env)) throw new ApiError(503, 'mail_not_configured');
  const url = new URL('/account', env.PUBLIC_URL); url.hash = new URLSearchParams({ token, purpose }).toString();
  const labels = { verify: 'Подтверждение почты AppRevive', reset: 'Сброс пароля AppRevive', apple: 'Привязка Apple ID к AppRevive' };
  const response = await fetch('https://api.resend.com/emails', { method: 'POST', signal: AbortSignal.timeout(15000), headers: { Authorization: 'Bearer ' + env.RESEND_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: env.MAIL_FROM, to: [email], subject: labels[purpose], text: `${labels[purpose]}\n\nОткройте ссылку в течение 15 минут:\n${url.href}\n\nЕсли вы не запрашивали это действие, проигнорируйте письмо. Не пересылайте ссылку другим людям.` }) });
  if (!response.ok) throw new ApiError(503, 'mail_unavailable');
}
export class AuthService {
  constructor(pool, { mail = sendMail } = {}) { this.pool = pool; this.mail = mail; }
  async issue(user, purpose, email) {
    const token = randomBytes(32).toString('hex');
    await this.pool.execute('INSERT INTO apprevive_email_tokens(token_hash,user_id,purpose,email,expires_at) VALUES (?,?,?,?,DATE_ADD(UTC_TIMESTAMP(),INTERVAL 15 MINUTE))', [hash(token), user, purpose, email]);
    try { await this.mail({ email, purpose, token }); }
    catch (error) { await this.pool.execute('DELETE FROM apprevive_email_tokens WHERE token_hash=?', [hash(token)]); throw error; }
    return { status: 'email_sent' };
  }
  async register(body) {
    const email = normalizeEmail(body?.email), encoded = await passwordHash(body?.password);
    const [existing] = await this.pool.execute('SELECT user_id FROM apprevive_users WHERE email=?', [email]);
    if (existing.length) return { status: 'email_sent' }; // Do not overwrite an unverified password.
    const id = randomBytes(16).toString('hex');
    await this.pool.execute('INSERT INTO apprevive_users(user_id,email,password_hash) VALUES (?,?,?)', [id, email, encoded]);
    return this.issue(id, 'verify', email);
  }
  async login(body) {
    const email = normalizeEmail(body?.email);
    const [rows] = await this.pool.execute('SELECT user_id,email,password_hash,verified,role FROM apprevive_users WHERE email=?', [email]);
    const row = rows[0];
    if (!await verifyPassword(body?.password, row?.password_hash) || !row?.verified) throw new ApiError(401, 'login_failed_or_unverified');
    await this.requireAccount(row, appleId(email));
    const token = randomBytes(32).toString('hex');
    await this.pool.execute('INSERT INTO apprevive_sessions(token_hash,user_id,expires_at) VALUES (?,?,DATE_ADD(UTC_TIMESTAMP(),INTERVAL 7 DAY))', [hash(token), row.user_id]);
    return { status: 'ok', token, user: { user_id: row.user_id, email: row.email, role: row.role } };
  }
  async session(req) {
    const bearer = /^Bearer ([a-f0-9]{64})$/.exec(String(req.headers.authorization || ''))?.[1];
    const cookie = /(?:^|;\s*)apprevive_session=([a-f0-9]{64})(?:;|$)/.exec(String(req.headers.cookie || ''))?.[1];
    const token = bearer || cookie;
    if (!token) throw new ApiError(401, 'service_login_required');
    const [rows] = await this.pool.execute('SELECT u.user_id,u.email,u.role FROM apprevive_sessions s JOIN apprevive_users u ON u.user_id=s.user_id WHERE s.token_hash=? AND s.expires_at>UTC_TIMESTAMP() AND u.verified=1', [hash(token)]);
    if (!rows.length) throw new ApiError(401, 'service_login_required');
    return { ...rows[0], session_hash: hash(token) };
  }
  async logout(user) { await this.pool.execute('DELETE FROM apprevive_sessions WHERE token_hash=?', [user.session_hash]); return { status: 'ok' }; }
  async requestReset(body) {
    const email = normalizeEmail(body?.email);
    const [rows] = await this.pool.execute('SELECT user_id FROM apprevive_users WHERE email=?', [email]);
    if (rows.length) await this.issue(rows[0].user_id, 'reset', email);
    return { status: 'email_sent' };
  }
  async resend(body) {
    const email = normalizeEmail(body?.email);
    const [rows] = await this.pool.execute('SELECT user_id,verified FROM apprevive_users WHERE email=?', [email]);
    if (rows.length && !rows[0].verified) await this.issue(rows[0].user_id, 'verify', email);
    return { status: 'email_sent' };
  }
  async requestApple(user, body) {
    const email = normalizeEmail(body?.email);
    return this.issue(user.user_id, 'apple', email);
  }
  async consume(body, user = null) {
    if (!/^[a-f0-9]{64}$/.test(body?.token || '')) throw new ApiError(400, 'invalid_token');
    const encoded = body.password === undefined ? null : await passwordHash(body.password);
    const db = await this.pool.getConnection();
    try {
      await db.beginTransaction();
      const [rows] = await db.execute('SELECT user_id,purpose,email FROM apprevive_email_tokens WHERE token_hash=? AND expires_at>UTC_TIMESTAMP() FOR UPDATE', [hash(body.token)]);
      const row = rows[0]; if (!row) throw new ApiError(422, 'invalid_or_expired_token');
      if (row.purpose === 'verify') {
        if (!encoded) throw new ApiError(400, 'password_min_12');
        await db.execute('UPDATE apprevive_users SET verified=1,password_hash=? WHERE user_id=?', [encoded, row.user_id]);
      }
      if (row.purpose === 'reset') {
        if (!encoded) throw new ApiError(400, 'password_min_12');
        await db.execute('UPDATE apprevive_users SET password_hash=? WHERE user_id=?', [encoded, row.user_id]);
        await db.execute('DELETE FROM apprevive_sessions WHERE user_id=?', [row.user_id]);
      }
      if (row.purpose === 'apple') {
        if (user?.user_id !== row.user_id) throw new ApiError(401, 'login_as_link_requester');
        const id = appleId(row.email);
        const [owners] = await db.execute('SELECT user_id FROM apprevive_user_accounts WHERE account_id=? FOR UPDATE', [id]);
        if (owners.length && owners[0].user_id !== row.user_id) throw new ApiError(409, 'apple_already_linked');
        await db.execute('INSERT IGNORE INTO apprevive_user_accounts(account_id,user_id,email) VALUES (?,?,?)', [id, row.user_id, row.email]);
        const [confirmed] = await db.execute('SELECT user_id FROM apprevive_user_accounts WHERE account_id=?', [id]);
        if (confirmed[0]?.user_id !== row.user_id) throw new ApiError(409, 'apple_already_linked');
      }
      await db.execute('DELETE FROM apprevive_email_tokens WHERE user_id=? AND purpose=? AND email=?', [row.user_id, row.purpose, row.email]);
      await db.commit(); return { status: 'verified', purpose: row.purpose };
    } catch (error) { await db.rollback(); throw error; } finally { db.release(); }
  }
  async requireAccount(user, account) {
    if (typeof account !== 'string' || !/^[a-f0-9]{64}$/.test(account)) throw new ApiError(400, 'invalid_account');
    if (account === appleId(user.email)) await this.pool.execute('INSERT IGNORE INTO apprevive_user_accounts(account_id,user_id,email) VALUES (?,?,?)', [account, user.user_id, user.email]);
    const [rows] = await this.pool.execute('SELECT account_id FROM apprevive_user_accounts WHERE account_id=? AND user_id=?', [account, user.user_id]);
    if (!rows.length) throw new ApiError(403, 'verify_apple_email_required');
  }
  async profile(user) {
    const [accounts] = await this.pool.execute('SELECT account_id,email FROM apprevive_user_accounts WHERE user_id=?', [user.user_id]);
    return { status: 'ok', user: { user_id: user.user_id, email: user.email, role: user.role }, accounts };
  }
  async createAdmin(email, password) {
    email = normalizeEmail(email); const encoded = await passwordHash(password);
    await this.pool.execute("INSERT INTO apprevive_users(user_id,email,password_hash,verified,role) VALUES (?,?,?,1,'admin') ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash),verified=1,role='admin'", [randomBytes(16).toString('hex'), email, encoded]);
    await this.pool.execute('DELETE s FROM apprevive_sessions s JOIN apprevive_users u ON u.user_id=s.user_id WHERE u.email=?', [email]);
  }
}
