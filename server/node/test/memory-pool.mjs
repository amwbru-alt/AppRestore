// Transactional test double; production SQL still runs through mysql2.
export class MemoryPool {
  constructor(codes = ['ONE']) { this.codes = new Set(codes); this.receipts = []; this.tail = Promise.resolve(); this.failInsert = false; }
  async getConnection() {
    const previous = this.tail; let unlock;
    this.tail = new Promise(resolve => { unlock = resolve; }); await previous;
    const pool = this;
    let codes, receipts;
    return {
      async query() {},
      async beginTransaction() { codes = new Set(pool.codes); receipts = pool.receipts.map(row => ({ ...row })); },
      async execute(sql, params) {
        if (sql.startsWith('SELECT code_hash')) return [receipts.filter(row => row.owner_hash === params[0] && row.request_id === params[1])];
        if (sql.startsWith('SELECT owner_hash')) return [receipts.filter(row => row.code_hash === params[0])];
        if (sql.startsWith('DELETE')) return [{ affectedRows: codes.delete(params[0].toString('utf8')) ? 1 : 0 }];
        if (sql.startsWith('INSERT')) {
          if (pool.failInsert) throw new Error('private SQL and secret password');
          if (receipts.some(row => row.code_hash === params[0] || row.owner_hash === params[1] && row.request_id === params[2])) throw Object.assign(new Error('duplicate'), { code: 'ER_DUP_ENTRY' });
          receipts.push({ code_hash: params[0], owner_hash: params[1], request_id: params[2] }); return [{}];
        }
        throw new Error('Unexpected SQL');
      },
      async commit() { pool.codes = codes; pool.receipts = receipts; },
      async rollback() {},
      release() { unlock(); },
    };
  }
  async execute() { return [[{ store_id: '686449807', name: 'Telegram', icon_url: 'https://example.org/icon.png' }]]; }
}
