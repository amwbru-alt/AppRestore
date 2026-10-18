import { ApiError, hash } from './service.mjs';

function input(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body) || typeof body.account_id !== 'string' || !/^[a-f0-9]{64}$/.test(body.account_id)) throw new ApiError(400, 'invalid_account');
  return body.account_id;
}
function request(body) {
  if (typeof body.request_id !== 'string' || !/^[a-f0-9]{32}$/.test(body.request_id)) throw new ApiError(400, 'invalid_request');
  return body.request_id;
}
export class AccountService {
  constructor(pool) { this.pool = pool; }
  async transaction(account, work) {
    for (let retry = 0; retry < 3; retry++) {
      const db = await this.pool.getConnection();
      try {
        await db.query('SET SESSION innodb_lock_wait_timeout=5');
        await db.beginTransaction();
        await db.execute('INSERT IGNORE INTO apprevive_accounts (account_id) VALUES (?)', [account]);
        const [rows] = await db.execute('SELECT credits, installations FROM apprevive_accounts WHERE account_id=? FOR UPDATE', [account]);
        const result = await work(db, rows[0]);
        await db.commit();
        return result;
      } catch (error) {
        try { await db.rollback(); } catch {}
        if (['ER_LOCK_DEADLOCK', 'ER_LOCK_WAIT_TIMEOUT'].includes(error.code) && retry < 2) continue;
        throw error;
      } finally { db.release(); }
    }
  }
  async balance(body) {
    const account = input(body);
    return this.transaction(account, async (_db, row) => ({ status: 'ok', account_id: account, credits: row.credits, installations: row.installations }));
  }
  async redeem(body) {
    const account = input(body), id = request(body);
    const code = typeof body.code === 'string' ? body.code.trim() : '';
    if (!code || Buffer.byteLength(code) > 256 || /[\r\n\x00]/.test(code)) throw new ApiError(400, 'invalid_request');
    const digest = hash(code);
    return this.transaction(account, async (db, row) => {
      const [receipts] = await db.execute('SELECT owner_hash FROM apprevive_promo_redemptions WHERE code_hash=? FOR UPDATE', [digest]);
      if (receipts.length) {
        if (receipts[0].owner_hash !== account) throw new ApiError(422, 'invalid_code');
        // Same account may recover a timed-out redemption after reinstalling.
        return { status: 'activated', account_id: account, code_hash: digest, credits: row.credits };
      }
      const [deleted] = await db.execute('DELETE FROM apprevive_promo_codes WHERE code=?', [Buffer.from(code)]);
      if (deleted.affectedRows !== 1) throw new ApiError(422, 'invalid_code');
      await db.execute('INSERT INTO apprevive_promo_redemptions (code_hash,owner_hash,request_id) VALUES (?,?,?)', [digest, account, id]);
      await db.execute('UPDATE apprevive_accounts SET credits=credits+1 WHERE account_id=?', [account]);
      return { status: 'activated', account_id: account, code_hash: digest, credits: row.credits + 1 };
    });
  }
  async reserve(body) {
    const account = input(body), id = request(body);
    return this.transaction(account, async (db, row) => {
      const [prior] = await db.execute('SELECT state FROM apprevive_restorations WHERE account_id=? AND request_id=?', [account, id]);
      if (prior.length) return { status: prior[0].state, account_id: account, request_id: id };
      // One in-flight installation per account, including on other computers.
      const [pending] = await db.execute("SELECT request_id FROM apprevive_restorations WHERE account_id=? AND state='reserved' LIMIT 1", [account]);
      if (pending.length) throw new ApiError(409, 'pending_restoration');
      if (row.credits < 1) throw new ApiError(402, 'code_required');
      await db.execute('UPDATE apprevive_accounts SET credits=credits-1 WHERE account_id=?', [account]);
      await db.execute("INSERT INTO apprevive_restorations (account_id,request_id,state) VALUES (?,?,'reserved')", [account, id]);
      return { status: 'reserved', account_id: account, request_id: id };
    });
  }
  async finish(body) {
    const account = input(body), id = request(body);
    if (typeof body.success !== 'boolean') throw new ApiError(400, 'invalid_request');
    return this.transaction(account, async (db) => {
      const [prior] = await db.execute('SELECT state FROM apprevive_restorations WHERE account_id=? AND request_id=?', [account, id]);
      if (!prior.length) throw new ApiError(404, 'unknown_restoration');
      const state = body.success ? 'completed' : 'failed';
      if (prior[0].state !== 'reserved' && prior[0].state !== state) throw new ApiError(409, 'request_conflict');
      if (prior[0].state === 'reserved') {
        await db.execute('UPDATE apprevive_restorations SET state=? WHERE account_id=? AND request_id=?', [state, account, id]);
        await db.execute(body.success
          ? 'UPDATE apprevive_accounts SET installations=installations+1 WHERE account_id=?'
          : 'UPDATE apprevive_accounts SET credits=credits+1 WHERE account_id=?', [account]);
      }
      return { status: state, account_id: account, request_id: id };
    });
  }
}
