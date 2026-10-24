import { AuthService } from './auth.mjs';
import { readFile } from 'node:fs/promises';
import { importGroups } from './catalog-groups.mjs';
import { PartnerService } from './partners.mjs';
import { randomBytes } from 'node:crypto';
import { createDatabase } from './db.mjs';
import { safeIcon, ApiError } from './service.mjs';

async function syncIcons(pool) {
  const [rows] = await pool.execute("SELECT store_id FROM apprevive_app_catalog WHERE icon_url='' AND enabled=1");
  let updated = 0, failed = 0;
  for (let offset = 0; offset < rows.length; offset += 40) {
    const missing = new Set(rows.slice(offset, offset + 40).map(row => String(row.store_id)));
    for (const country of ['ru', 'us']) {
      if (!missing.size) break;
      try {
        const query = new URLSearchParams({ id: [...missing].join(','), country });
        const response = await fetch(`https://itunes.apple.com/lookup?${query}`, { signal: AbortSignal.timeout(15000) });
        if (!response.ok) throw new Error('Apple unavailable');
        const reader = response.body.getReader();
        const chunks = []; let length = 0;
        while (true) {
          const { done, value } = await reader.read(); if (done) break;
          length += value.length;
          if (length > 4 * 1024 * 1024) { await reader.cancel(); throw new Error('Response too large'); }
          chunks.push(value);
        }
        const result = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        for (const item of result.results || []) {
          const id = String(item.trackId), url = safeIcon(item.artworkUrl512 || item.artworkUrl100 || '');
          if (!missing.has(id) || !url) continue;
          const [changed] = await pool.execute("UPDATE apprevive_app_catalog SET icon_url=? WHERE store_id=? AND icon_url=''", [url, id]);
          updated += changed.affectedRows; missing.delete(id);
        }
      } catch { failed++; }
    }
  }
  console.log(`Icons updated: ${updated}; failed Apple requests: ${failed}`);
}
let pool;
try {
  pool = createDatabase();
  if (process.argv[2] === 'create-admin') {
    let input = ''; for await (const part of process.stdin) input += part;
    if (input.length > 512) throw new Error('Invalid password input');
    await new AuthService(pool).createAdmin(process.argv[3], input.replace(/[\r\n]+$/, ''));
    console.log('Administrator ready. Password is never printed.');
  } else if (process.argv[2] === 'import-groups') {
    const raw = JSON.parse(await readFile(process.argv[3] || 'catalog-groups.json', 'utf8'));
    console.log('Bank groups imported:', await importGroups(pool, raw));
  } else if (process.argv[2] === 'record-purchase') {
    const [buyer_id, count, amount, payment_reference] = process.argv.slice(3);
    const result = await new PartnerService(pool).recordPurchase({ buyer_id, quantity: Number(count), amount_kopecks: Number(amount), payment_reference });
    console.log(JSON.stringify(result, null, 2));
  } else if (process.argv[2] === 'refund-order') {
    console.log(JSON.stringify(await new PartnerService(pool).refund(process.argv[3]), null, 2));
  } else if (process.argv[2] === 'sync-icons') await syncIcons(pool);
  else if (process.argv[2] === 'add-codes') {
    const count = Number(process.argv[3] || 1);
    if (!Number.isInteger(count) || count < 1 || count > 1000) throw new Error('Invalid count');
    for (let i = 0; i < count; i++) {
      const code = `RV-${randomBytes(12).toString('hex').toUpperCase()}`;
      await pool.execute('INSERT INTO apprevive_promo_codes (code) VALUES (?)', [Buffer.from(code)]);
      console.log(code); // Administrator terminal only; never exposed through HTTP.
    }
  } else throw new Error('Use import-groups [FILE], sync-icons, add-codes [1..1000], record-purchase BUYER_ID COUNT KOPECKS PAYMENT_ID, or refund-order PAYMENT_ID');
} catch (error) { console.error(error instanceof ApiError ? 'Operation rejected: ' + error.code : 'Catalog/code operation failed. Check command, environment and database.'); process.exitCode = 1; }
finally { if (pool) await pool.end(); }
