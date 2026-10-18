import { createDatabase } from './db.mjs';
import { PromoService } from './service.mjs';
import { AccountService } from './accounts.mjs';
import { createApi } from './http.mjs';

let pool;
try {
  pool = createDatabase();
  await pool.query('SELECT 1');
  const port = Number(process.env.PORT || 3000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid port');
  const server = createApi(new PromoService(pool), { accounts: new AccountService(pool), requireHttps: process.env.ALLOW_HTTP === 'false' });
  server.listen(port, process.env.HOST || '0.0.0.0', () => console.log('AppRevive API started'));
  server.on('error', () => { console.error('AppRevive API listen failed'); process.exitCode = 1; pool.end(); });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => {
    server.close(async () => { await pool.end(); process.exit(0); });
    setTimeout(() => process.exit(1), 10000).unref();
  });
} catch {
  console.error('AppRevive API startup failed. Check server environment and database access.');
  if (pool) await pool.end();
  process.exitCode = 1;
}
