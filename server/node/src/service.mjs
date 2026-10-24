import { createHash } from 'node:crypto';
import { setTimeout as pause } from 'node:timers/promises';

export class ApiError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}
export const hash = value => createHash('sha256').update(value).digest('hex');
export function activationInput(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)
      || typeof body.code !== 'string' || typeof body.installation_token !== 'string'
      || typeof body.request_id !== 'string') throw new ApiError(400, 'invalid_request');
  const code = body.code.trim();
  if (!code || Buffer.byteLength(code) > 256 || /[\r\n\x00]/.test(code)
      || !/^[a-f0-9]{64}$/.test(body.installation_token)
      || !/^[a-f0-9]{32}$/.test(body.request_id)) throw new ApiError(400, 'invalid_request');
  return { code, owner: hash(body.installation_token), request: body.request_id, digest: hash(code) };
}
const receipt = input => ({ status: 'activated', credits: 1, code_hash: input.digest, request_id: input.request });

export class PromoService {
  constructor(pool) { this.pool = pool; }
  async redeem(body) {
    const input = activationInput(body);
    for (let attempt = 0; attempt < 3; attempt++) {
      const db = await this.pool.getConnection();
      try {
        await db.query('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED');
        await db.query('SET SESSION innodb_lock_wait_timeout=5');
        await db.beginTransaction();
        let [rows] = await db.execute('SELECT code_hash FROM apprevive_promo_redemptions WHERE owner_hash=? AND request_id=? FOR UPDATE', [input.owner, input.request]);
        if (rows.length) {
          if (rows[0].code_hash !== input.digest) throw new ApiError(409, 'request_conflict');
          await db.commit();
          return receipt(input);
        }
        [rows] = await db.execute('SELECT owner_hash, request_id FROM apprevive_promo_redemptions WHERE code_hash=? FOR UPDATE', [input.digest]);
        if (rows.length) {
          if (rows[0].owner_hash !== input.owner || rows[0].request_id !== input.request) throw new ApiError(422, 'invalid_code');
          await db.commit();
          return receipt(input);
        }
        const [deleted] = await db.execute('DELETE FROM apprevive_promo_codes WHERE code=?', [Buffer.from(input.code, 'utf8')]);
        if (deleted.affectedRows !== 1) {
          // The same request may have committed while DELETE waited on its row.
          [rows] = await db.execute('SELECT code_hash FROM apprevive_promo_redemptions WHERE owner_hash=? AND request_id=? FOR UPDATE', [input.owner, input.request]);
          if (!rows.length || rows[0].code_hash !== input.digest) throw new ApiError(422, 'invalid_code');
          await db.commit();
          return receipt(input);
        }
        await db.execute('INSERT INTO apprevive_promo_redemptions (code_hash, owner_hash, request_id) VALUES (?,?,?)', [input.digest, input.owner, input.request]);
        await db.commit();
        return receipt(input);
      } catch (error) {
        try { await db.rollback(); } catch { /* original error wins */ }
        if (['ER_LOCK_DEADLOCK', 'ER_LOCK_WAIT_TIMEOUT', 'ER_DUP_ENTRY'].includes(error.code) && attempt < 2) {
          await pause(30 * (attempt + 1));
          continue;
        }
        if (error.code === 'ER_DUP_ENTRY') throw new ApiError(422, 'invalid_code');
        throw error;
      } finally { db.release(); }
    }
    throw new ApiError(503, 'unavailable');
  }
  async catalog() {
    let rows;
    try {
      [rows] = await this.pool.execute('SELECT c.store_id,c.name,c.icon_url,g.group_id,g.name AS group_name,g.icon_url AS group_icon FROM apprevive_app_catalog c LEFT JOIN apprevive_catalog_variants v ON v.store_id=c.store_id LEFT JOIN apprevive_catalog_groups g ON g.group_id=v.group_id AND g.enabled=1 WHERE c.enabled=1 ORDER BY c.name LIMIT 5000');
    } catch (error) {
      if (error.code !== 'ER_NO_SUCH_TABLE') throw error;
      [rows] = await this.pool.execute('SELECT store_id, name, icon_url FROM apprevive_app_catalog WHERE enabled=1 ORDER BY name LIMIT 5000');
    }
    return { status: 'ok', apps: rows.map(row => ({ trackId: String(row.store_id), name: row.name, iconUrl: safeIcon(row.icon_url),
      ...(row.group_id ? { groupId: row.group_id, groupName: row.group_name, groupIconUrl: safeIcon(row.group_icon) } : {}) })) };
  }
}
export function safeIcon(value) {
  try {
    const url = new URL(value);
    if (url.protocol === 'https:' && !url.username && !url.password && value.length <= 2048) return value;
  } catch { /* missing artwork falls back in the desktop app */ }
  return '';
}
