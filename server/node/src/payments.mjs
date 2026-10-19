import { randomBytes } from 'node:crypto';
import { ApiError } from './service.mjs';
export function money(value) { if (typeof value !== 'string' || !/^\d{1,9}\.\d{2}$/.test(value)) throw new ApiError(502, 'invalid_payment_amount'); return Number(value.replace('.', '')); }
export class YooKassa {
  constructor(env = process.env, http = fetch) { this.env = env; this.http = http; }
  get allowTest() { return this.env.PAYMENTS_TEST_MODE === 'true' && this.env.APP_ENV === 'staging'; }
  get configured() { const e = this.env; return (e.PAYMENTS_TEST_MODE !== 'true' || this.allowTest) && e.PAYMENTS_ENABLED === 'true' && Boolean(e.YOOKASSA_SHOP_ID && e.YOOKASSA_SECRET_KEY && /^https:\/\//.test(e.PUBLIC_URL || '') && /^[1-9]\d?$/.test(e.PAYMENT_VAT_CODE || '')); }
  async call(path, { body, key } = {}) {
    if (!this.configured) throw new ApiError(503, 'payments_not_configured');
    const response = await this.http('https://api.yookassa.ru/v3/' + path, { method: body ? 'POST' : 'GET', signal: AbortSignal.timeout(15000), headers: {
      Authorization: 'Basic ' + Buffer.from(`${this.env.YOOKASSA_SHOP_ID}:${this.env.YOOKASSA_SECRET_KEY}`).toString('base64'), 'Content-Type': 'application/json', ...(key ? { 'Idempotence-Key': key } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
    if (!response.ok) throw new ApiError(503, 'payment_provider_unavailable');
    return response.json();
  }
  create(row, email) {
    return this.call('payments', { key: row.checkout_id, body: { amount: { value: (row.amount_kopecks / 100).toFixed(2), currency: 'RUB' }, capture: true,
      confirmation: { type: 'redirect', return_url: new URL('/account?payment=' + row.checkout_id, this.env.PUBLIC_URL).href }, description: `AppRevive: ${row.quantity} код(ов) восстановления`, metadata: { checkout_id: row.checkout_id },
      receipt: { customer: { email }, items: [{ description: 'Код восстановления AppRevive', quantity: String(row.quantity), amount: { value: '100.00', currency: 'RUB' }, vat_code: Number(this.env.PAYMENT_VAT_CODE), payment_mode: 'full_payment', payment_subject: 'service' }], ...(this.env.PAYMENT_TAX_SYSTEM_CODE ? { tax_system_code: Number(this.env.PAYMENT_TAX_SYSTEM_CODE) } : {}) } } });
  }
  payment(id) { if (!/^[a-zA-Z0-9-]{1,64}$/.test(id)) throw new ApiError(400, 'invalid_payment'); return this.call('payments/' + id); }
  refund(row) { return this.call('refunds', { key: 'refund-' + row.checkout_id, body: { payment_id: row.provider_id, amount: { value: (row.amount_kopecks / 100).toFixed(2), currency: 'RUB' }, description: 'Полный возврат AppRevive', receipt: { customer: { email: row.email }, items: [{ description: 'Код восстановления AppRevive', quantity: String(row.quantity), amount: { value: '100.00', currency: 'RUB' }, vat_code: Number(this.env.PAYMENT_VAT_CODE), payment_mode: 'full_payment', payment_subject: 'service' }], ...(this.env.PAYMENT_TAX_SYSTEM_CODE ? { tax_system_code: Number(this.env.PAYMENT_TAX_SYSTEM_CODE) } : {}) } } }); }
  refundInfo(id) { if (!/^[a-zA-Z0-9-]{1,64}$/.test(id)) throw new ApiError(400, 'invalid_refund'); return this.call('refunds/' + id); }
}
export class PaymentService {
  constructor(pool, partners, provider = new YooKassa()) { this.pool = pool; this.partners = partners; this.provider = provider; }
  async row(id) {
    if (!/^[a-f0-9]{32}$/.test(id || '')) throw new ApiError(400, 'invalid_checkout');
    const [rows] = await this.pool.execute('SELECT c.*,u.email,(c.created_at>DATE_SUB(NOW(),INTERVAL 23 HOUR)) AS recent FROM apprevive_checkouts c JOIN apprevive_users u ON u.user_id=c.user_id WHERE c.checkout_id=?', [id]);
    if (!rows.length) throw new ApiError(404, 'unknown_checkout'); return rows[0];
  }
  async create(user, body) {
    if (!this.provider.configured) throw new ApiError(503, 'payments_not_configured');
    if (!/^[a-f0-9]{32}$/.test(body.request_id || '') || !Number.isInteger(body.quantity) || body.quantity < 1 || body.quantity > 100) throw new ApiError(400, 'invalid_checkout');
    const [prior] = await this.pool.execute('SELECT checkout_id,account_id,quantity FROM apprevive_checkouts WHERE user_id=? AND request_id=?', [user.user_id, body.request_id]);
    let id = prior[0]?.checkout_id;
    if (id && (prior[0].account_id !== body.account_id || prior[0].quantity !== body.quantity)) throw new ApiError(409, 'checkout_conflict');
    if (!id) {
      id = randomBytes(16).toString('hex');
      try { await this.pool.execute('INSERT INTO apprevive_checkouts(checkout_id,user_id,account_id,request_id,quantity,amount_kopecks) VALUES (?,?,?,?,?,?)', [id, user.user_id, body.account_id, body.request_id, body.quantity, body.quantity * 10000]); }
      catch (error) { if (error.code !== 'ER_DUP_ENTRY') throw error; return this.create(user, body); }
    }
    const row = await this.row(id); await this.ensure(row);
    return this.sync(id, user);
  }
  async ensure(row) {
    if (row.provider_id) return;
    if (!row.recent) throw new ApiError(409, 'payment_needs_review');
    const payment = await this.provider.create(row, row.email);
    this.verify(row, payment);
    if (payment.status === 'pending' && !payment.confirmation?.confirmation_url) throw new ApiError(502, 'invalid_confirmation_url');
    const url = new URL(payment.confirmation?.confirmation_url || 'https://yookassa.ru');
    if (url.protocol !== 'https:' || !/(^|\.)(yoomoney\.ru|yookassa\.ru)$/.test(url.hostname)) throw new ApiError(502, 'invalid_confirmation_url');
    await this.pool.execute('UPDATE apprevive_checkouts SET provider_id=?,confirmation_url=? WHERE checkout_id=? AND provider_id IS NULL', [payment.id, url.href, row.checkout_id]);
  }
  verify(row, payment) {
    if (payment.test === true && !this.provider.allowTest) throw new ApiError(409, 'test_payment_rejected');
    if (!/^[a-zA-Z0-9-]{1,64}$/.test(payment.id || '') || (row.provider_id && row.provider_id !== payment.id) || payment.metadata?.checkout_id !== row.checkout_id || payment.amount?.currency !== 'RUB' || money(payment.amount?.value) !== row.amount_kopecks) throw new ApiError(409, 'payment_mismatch');
  }
  async sync(id, user = null) {
    let row = await this.row(id);
    if (user && row.user_id !== user.user_id && user.role !== 'admin') throw new ApiError(403, 'forbidden');
    await this.ensure(row); row = await this.row(id);
    const payment = await this.provider.payment(row.provider_id); this.verify(row, payment);
    if (payment.status === 'succeeded' && payment.paid === true && row.state !== 'refunded') {
      await this.partners.recordPurchase({ buyer_id: row.account_id, quantity: row.quantity, amount_kopecks: row.amount_kopecks, payment_reference: 'yk_' + row.provider_id });
      await this.pool.execute("UPDATE apprevive_checkouts SET state='paid' WHERE checkout_id=? AND state='pending'", [id]);
    } else if (payment.status === 'canceled') await this.pool.execute("UPDATE apprevive_checkouts SET state='cancelled' WHERE checkout_id=? AND state='pending'", [id]);
    row = await this.row(id);
    return { status: 'ok', checkout_id: id, state: row.state, confirmation_url: row.state === 'pending' ? row.confirmation_url : '' };
  }
  async webhook(body) {
    const event = body?.event, object = body?.object;
    if (!object || typeof object.id !== 'string') throw new ApiError(400, 'invalid_notification');
    if (event === 'refund.succeeded') {
      const refund = await this.provider.refundInfo(object.id);
      if (refund.status !== 'succeeded') return { status: 'ok' };
      const [rows] = await this.pool.execute('SELECT checkout_id FROM apprevive_checkouts WHERE provider_id=?', [refund.payment_id]);
      if (!rows.length) return { status: 'ok' };
      const row = await this.row(rows[0].checkout_id);
      if (refund.amount?.currency !== 'RUB' || money(refund.amount?.value) !== row.amount_kopecks) throw new ApiError(409, 'partial_refund_needs_review');
      await this.partners.refund('yk_' + row.provider_id);
      await this.pool.execute("UPDATE apprevive_checkouts SET state='refunded' WHERE checkout_id=?", [row.checkout_id]);
    } else if (['payment.succeeded', 'payment.canceled'].includes(event)) {
      const [rows] = await this.pool.execute('SELECT checkout_id FROM apprevive_checkouts WHERE provider_id=?', [object.id]);
      if (rows.length) await this.sync(rows[0].checkout_id);
    }
    return { status: 'ok' };
  }
  async refund(id) {
    const row = await this.row(id);
    if (!['paid','refunded'].includes(row.state)) throw new ApiError(409, 'payment_not_paid');
    if (row.state === 'refunded') return { status: 'ok', state: 'refunded' };
    const refund = await this.provider.refund(row);
    if (refund.status === 'succeeded') return this.webhook({ event: 'refund.succeeded', object: { id: refund.id } });
    return { status: 'pending' };
  }
}
