import { discover, discoveries, reviewDiscovery } from './discoveries.mjs';
import { shopOrders } from './shop-orders.mjs';
import { SecurityService } from './security.mjs';
import { records,metrics } from './admin-data.mjs';
import { registrationSummary } from './user-referrals.mjs';
import { httpAuthOrigin } from './transport.mjs';
import { isIP } from 'node:net';
import { ApiError } from './service.mjs';
import { AuthService } from './auth.mjs';
import { AccountService } from './accounts.mjs';
import { PartnerService } from './partners.mjs';
import { PayoutService, readPolicy, commissionPolicy } from './ledger.mjs';
import { PaymentService } from './payments.mjs';
import { importGroups } from './catalog-groups.mjs';
import { safeIcon } from './service.mjs';
const loopback = ip => ['127.0.0.1','::1','::ffff:127.0.0.1'].includes(ip);
export class Platform {
  constructor(pool, { auth = new AuthService(pool), accounts = new AccountService(pool), partners = new PartnerService(pool), payments, env = process.env } = {}) {
    this.pool = pool; this.security = new SecurityService(pool); this.auth = auth; this.accounts = accounts; this.partners = partners;
    this.payments = payments || new PaymentService(pool, partners); this.payouts = new PayoutService(pool, accounts); this.env = env; this.limits = new Map();
  }
  secure(req) {
    if (this.env.DEV_ALLOW_INSECURE_AUTH !== 'true' && !(httpAuthOrigin(this.env) && req.headers.host === new URL(httpAuthOrigin(this.env)).host) && !(req.socket.encrypted || loopback(req.socket.remoteAddress) && req.headers['x-forwarded-proto'] === 'https')) throw new ApiError(426, 'https_required');
    if (req.method !== 'GET' && req.method !== 'HEAD' && req.headers.origin) {
      let origin; try { origin = new URL(this.env.PUBLIC_URL).origin; } catch { throw new ApiError(503, 'public_url_not_configured'); }
      if (req.headers.origin !== origin) throw new ApiError(403, 'origin_rejected');
    }
  }
  limit(key, max, seconds) {
    const time = Date.now();
    if (this.limits.size > 5000) for (const [k,v] of this.limits) if (v.until < time) this.limits.delete(k);
    let entry = this.limits.get(key);
    if (!entry || entry.until < time) {
      if (this.limits.size >= 10000) throw new ApiError(429, 'rate_limited');
      entry = { n: 0, until: time + seconds * 1000 }; this.limits.set(key, entry);
    }
    if (++entry.n > max) throw new ApiError(429, 'rate_limited');
  }
  async authorize(req, path, body) {
    this.secure(req);
    if (path === '/v1/redeem') throw new ApiError(410, 'update_desktop_required');
    const user = await this.auth.session(req);
    await this.auth.requireAccount(user, body.account_id);
    if (path === '/v2/partner/bind') {
      const code = typeof body.referral_code === 'string' ? body.referral_code.trim().toUpperCase() : '';
      const [own] = await this.pool.execute('SELECT p.account_id FROM apprevive_partners p LEFT JOIN apprevive_user_partners u ON u.partner_id=p.account_id LEFT JOIN apprevive_user_accounts a ON a.account_id=p.account_id WHERE p.referral_code=? AND (u.user_id=? OR a.user_id=?)', [code, user.user_id, user.user_id]);
      if (own.length) throw new ApiError(409, 'self_referral');
    }
  }
  async audit(user, action, target) { await this.pool.execute('INSERT INTO apprevive_admin_audit(user_id,action,target) VALUES (?,?,?)', [user.user_id, action, String(target || '').slice(0,128)]); }
  async route(req, res, path, { json, reply }) {
    if (!path.startsWith('/v3/')) return false;
    if (path === '/v3/status' && req.method === 'GET') {
      reply(res, 200, { status: 'ok', payments_enabled: this.payments.provider.configured, secure_login_required: this.env.DEV_ALLOW_INSECURE_AUTH !== 'true' && !httpAuthOrigin(this.env), commission_policy: await readPolicy(this.pool) }); return true;
    }
    this.secure(req);
    const forwarded = String(req.headers['x-real-ip'] || '');
    const ip = loopback(req.socket.remoteAddress) && isIP(forwarded) ? forwarded : req.socket.remoteAddress;
    this.limit('api:' + ip, 180, 60);
    if (path === '/v3/payment/webhook' && req.method === 'POST') {
      this.limit('webhook:' + ip, 60, 60);
      reply(res, 200, await this.payments.webhook(await json(req, 32768))); return true;
    }
    const authActions = { register: 'register', login: 'login', reset: 'requestReset', resend: 'resend', consume: 'consume' };
    const action = path.slice('/v3/auth/'.length);
    if (path.startsWith('/v3/auth/') && Object.hasOwn(authActions, action) && req.method === 'POST') {
      this.limit('auth:' + ip, 20, 60);
      const body = await json(req);
      if (body.email) this.limit('email:' + String(body.email).trim().toLowerCase(), 8, 3600);
      let optionalUser = null;
      if (action === 'consume') { try { optionalUser = await this.auth.session(req); } catch (error) { if (error.status !== 401) throw error; } }
      const result = await this.auth[authActions[action]](body, optionalUser);
      if (action === 'login') res.setHeader('Set-Cookie', `apprevive_session=${result.token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800${this.env.DEV_ALLOW_INSECURE_AUTH === 'true' || httpAuthOrigin(this.env) ? '' : '; Secure'}`);
      reply(res, 200, result); return true;
    }
    if(path==='/v3/catalog/discover'&&req.method==='POST'){this.limit('discover:'+ip,10,60);reply(res,200,await discover(this.pool,await json(req,65536)));return true;}
    const user = await this.auth.session(req);
    const query = new URL(req.url, 'http://internal').searchParams;
    if(path==='/v3/security/sessions'&&req.method==='GET'){reply(res,200,await this.security.sessions(user));return true;}
    if(path==='/v3/security/revoke'&&req.method==='POST'){reply(res,200,await this.security.revoke(user,await json(req)));return true;}
    if(path==='/v3/security/password'&&req.method==='POST'){this.limit('password:'+user.user_id,5,3600);reply(res,200,await this.security.password(user,await json(req)));return true;}
    if (path === '/v3/me' && req.method === 'GET') { reply(res, 200, await this.auth.profile(user)); return true; }
    if (path === '/v3/auth/logout' && req.method === 'POST') {
      res.setHeader('Set-Cookie', 'apprevive_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');
      reply(res, 200, await this.auth.logout(user)); return true;
    }
    if (path === '/v3/auth/apple' && req.method === 'POST') { this.limit('link:' + user.user_id, 5, 3600); reply(res, 200, await this.auth.requestApple(user, await json(req))); return true; }
    if (path === '/v3/partner' && req.method === 'GET') {
      const id = await this.auth.partnerAccount(user);
      const partner = await this.partners.profile({ account_id: id });
      Object.assign(partner,await registrationSummary(this.pool,id));
      const [payouts] = await this.pool.execute('SELECT payout_id,amount_kopecks,state,created_at FROM apprevive_payouts WHERE partner_id=? ORDER BY created_at DESC LIMIT 100', [id]);
      reply(res, 200, { partner, ledger: partner.ledger, payouts }); return true;
    }
    if (path === '/v3/account' && req.method === 'GET') {
      const id = query.get('account_id'); await this.auth.requireAccount(user, id);
      const balance = await this.accounts.balance({ account_id: id });
      const [history] = await this.pool.execute('SELECT r.request_id,r.state,r.created_at,d.store_id,d.name FROM apprevive_restorations r LEFT JOIN apprevive_restoration_details d ON d.account_id=r.account_id AND d.request_id=r.request_id WHERE r.account_id=? ORDER BY r.created_at DESC LIMIT 100', [id]);
      const partner = await this.partners.profile({ account_id: id }); const ledger = await this.payouts.balance(id);
      const [payouts] = await this.pool.execute('SELECT payout_id,amount_kopecks,state,created_at FROM apprevive_payouts WHERE partner_id=? ORDER BY created_at DESC LIMIT 100', [id]);
      reply(res, 200, { ...balance, history, partner, ledger, payouts }); return true;
    }
    if(path==='/v3/shop/orders'&&req.method==='GET'){reply(res,200,await shopOrders(this.pool,user,query));return true;}
    if (path === '/v3/orders' && req.method === 'GET') {
      const [orders] = await this.pool.execute('SELECT checkout_id,quantity,amount_kopecks,state,created_at FROM apprevive_checkouts WHERE user_id=? ORDER BY created_at DESC LIMIT 100', [user.user_id]);
      const [codes] = await this.pool.execute("SELECT c.checkout_id,oc.code_hash,COALESCE(v.code,p.code) AS code,r.activated_at,CASE WHEN r.code_hash IS NOT NULL THEN 'activated' WHEN o.state='refunded' THEN 'invalidated' WHEN p.code IS NOT NULL THEN 'unused' ELSE 'unavailable' END AS activation_status FROM apprevive_checkouts c JOIN apprevive_orders o ON o.payment_reference=CONCAT('yk_',c.provider_id) JOIN apprevive_order_codes oc ON oc.order_id=o.order_id LEFT JOIN apprevive_issued_codes v ON v.code_hash=oc.code_hash LEFT JOIN apprevive_promo_codes p ON SHA2(p.code,256)=oc.code_hash LEFT JOIN apprevive_promo_redemptions r ON r.code_hash=oc.code_hash WHERE c.user_id=? AND c.state IN ('paid','refunded')", [user.user_id]);
      reply(res, 200, { status: 'ok', orders, codes: codes.map(row => ({ checkout_id: row.checkout_id, code: row.code?Buffer.from(row.code).toString():null, code_id:row.code_hash.slice(0,12), activation_status:row.activation_status,activated_at:row.activated_at })) }); return true;
    }
    if (path === '/v3/checkout' && req.method === 'POST') {
      this.limit('purchase:' + user.user_id, 10, 60); const body = await json(req); body.account_id=await this.auth.buyingAccount(user);
      reply(res, 200, await this.payments.create(user, body)); return true;
    }
    if (path === '/v3/checkout/sync' && req.method === 'POST') { const body = await json(req); reply(res, 200, await this.payments.sync(body.checkout_id, user)); return true; }
    if (path.startsWith('/v3/admin/')) {
      if (user.role !== 'admin') throw new ApiError(403, 'admin_required');
      if(path==='/v3/admin/discoveries'&&req.method==='GET'){reply(res,200,await discoveries(this.pool,query));return true;}
      if(path==='/v3/admin/metrics'&&req.method==='GET'){reply(res,200,await metrics(this.pool));return true;}
      if(['/v3/admin/users','/v3/admin/orders'].includes(path)&&req.method==='GET'){reply(res,200,await records(this.pool,path.split('/').at(-1),query));return true;}
      if (path === '/v3/admin/snapshot' && req.method === 'GET') {
        const [users] = await this.pool.execute('SELECT u.user_id,u.email,u.verified,u.role,u.created_at,p.referral_code AS invited_by FROM apprevive_users u LEFT JOIN apprevive_user_referrals r ON r.user_id=u.user_id LEFT JOIN apprevive_partners p ON p.account_id=r.partner_id ORDER BY u.created_at DESC LIMIT 200');
        const [orders] = await this.pool.execute('SELECT * FROM apprevive_orders ORDER BY created_at DESC LIMIT 200');
        const [restorations] = await this.pool.execute("SELECT * FROM apprevive_restorations WHERE state='reserved' ORDER BY created_at LIMIT 200");
        const [payouts] = await this.pool.execute('SELECT * FROM apprevive_payouts ORDER BY created_at DESC LIMIT 200');
        const [commissions] = await this.pool.execute('SELECT * FROM apprevive_commissions ORDER BY available_at DESC LIMIT 200');
        const [checkouts] = await this.pool.execute('SELECT * FROM apprevive_checkouts ORDER BY created_at DESC LIMIT 200');
        const [audit] = await this.pool.execute('SELECT * FROM apprevive_admin_audit ORDER BY audit_id DESC LIMIT 200');
        const [partners] = await this.pool.execute("SELECT p.account_id,p.referral_code,u.email,COALESCE(g.registered,0) AS registered,COALESCE(r.invited,0) AS invited,COALESCE(o.paid_orders,0) AS paid_orders,COALESCE(o.purchased_codes,0) AS purchased_codes,COALESCE(o.revenue_kopecks,0) AS revenue_kopecks FROM apprevive_partners p LEFT JOIN (SELECT partner_id,COUNT(*) AS registered FROM apprevive_user_referrals GROUP BY partner_id) g ON g.partner_id=p.account_id LEFT JOIN apprevive_user_partners m ON m.partner_id=p.account_id LEFT JOIN apprevive_users u ON u.user_id=m.user_id LEFT JOIN (SELECT partner_id,COUNT(*) AS invited FROM apprevive_referrals GROUP BY partner_id) r ON r.partner_id=p.account_id LEFT JOIN (SELECT partner_id,COUNT(*) AS paid_orders,SUM(quantity) AS purchased_codes,SUM(amount_kopecks) AS revenue_kopecks FROM apprevive_orders WHERE state='paid' GROUP BY partner_id) o ON o.partner_id=p.account_id ORDER BY p.created_at DESC,p.account_id LIMIT 200");
        reply(res, 200, { status: 'ok', partners, users, orders, restorations, payouts, commissions, checkouts, audit }); return true;
      }
      if (path === '/v3/admin/groups' && req.method === 'GET') {
        const [groups] = await this.pool.execute('SELECT group_id AS id,name,icon_url AS iconUrl FROM apprevive_catalog_groups WHERE enabled=1 ORDER BY name');
        const [apps] = await this.pool.execute('SELECT v.group_id,c.store_id AS trackId,c.name,c.icon_url AS iconUrl FROM apprevive_catalog_variants v JOIN apprevive_app_catalog c ON c.store_id=v.store_id');
        reply(res, 200, { status: 'ok', groups: groups.map(g => ({ ...g, apps: apps.filter(a => a.group_id === g.id).map(({ group_id, ...rest }) => rest) })) }); return true;
      }
      if (req.method !== 'POST') throw new ApiError(405, 'method_not_allowed');
      const body = await json(req, path.endsWith('/groups') ? 1024 * 1024 : 8192);
      const target = body.checkout_id || body.account_id || body.partner_id || body.payment_reference || body.store_id || 'catalog';
      await this.audit(user, 'begin:' + path.slice('/v3/admin/'.length), target);
      let result;
      if(path==='/v3/admin/discoveries/review')result=await reviewDiscovery(this.pool,body);
      else if (path === '/v3/admin/policy') {
        const policy = commissionPolicy({ PARTNER_COMMISSION_BPS: body.rate, PARTNER_HOLD_DAYS: body.days });
        await this.pool.execute("INSERT INTO apprevive_settings(name,value) VALUES ('commission_policy',?) ON DUPLICATE KEY UPDATE value=VALUES(value)", [JSON.stringify(policy)]);
        result = { status: 'ok', policy };
      } else if (path === '/v3/admin/groups') result = { status: 'ok', groups: await importGroups(this.pool, body.groups) };
      else if (path === '/v3/admin/catalog') {
        if (!/^[1-9][0-9]{7,11}$/.test(body.store_id || '') || typeof body.name !== 'string' || !body.name.trim() || body.name.length > 255 || typeof body.enabled !== 'boolean') throw new ApiError(400, 'invalid_catalog_app');
        const icon = safeIcon(body.icon_url || ''); if (body.icon_url && !icon) throw new ApiError(400, 'https_icon_required');
        await this.pool.execute('INSERT INTO apprevive_app_catalog(store_id,name,icon_url,enabled) VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE name=VALUES(name),icon_url=VALUES(icon_url),enabled=VALUES(enabled)', [body.store_id, body.name.trim(), icon, Number(body.enabled)]); result = { status: 'ok' };
      } else if (path === '/v3/admin/purchase') {
        if (body.confirmed !== true) throw new ApiError(400, 'payment_confirmation_required');
        result = await this.partners.recordPurchase(body);
      } else if (path === '/v3/admin/manual-refund') {
        if (body.confirmed !== true || String(body.payment_reference || '').startsWith('yk_')) throw new ApiError(400, 'use_gateway_refund');
        result = await this.partners.refund(body.payment_reference);
      } else if (path === '/v3/admin/refund') result = await this.payments.refund(body.checkout_id);
      else if (path === '/v3/admin/sync') result = await this.payments.sync(body.checkout_id, user);
      else if (path === '/v3/admin/resolve') result = await this.accounts.finish(body);
      else if (path === '/v3/admin/payout/create') result = await this.payouts.create(body);
      else if (path === '/v3/admin/payout/finish') result = await this.payouts.finish(body);
      else throw new ApiError(404, 'not_found');
      await this.audit(user, 'done:' + path.slice('/v3/admin/'.length), target);
      reply(res, 200, result); return true;
    }
    throw new ApiError(404, 'not_found');
  }
}
