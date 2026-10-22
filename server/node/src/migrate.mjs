import { readFile } from 'node:fs/promises';
import { createDatabase } from './db.mjs';
const pool = createDatabase();
try {
  for (const file of ['schema.sql','catalog-schema.sql','accounts-schema.sql','partners-schema.sql','catalog-groups-schema.sql','platform-schema.sql','discoveries-schema.sql']) {
    const text = await readFile(new URL('../../promo/' + file, import.meta.url), 'utf8');
    for (const statement of text.replace(/^\s*--.*$/gm, '').split(';').filter(s => s.trim())) await pool.query(statement);
  }
  console.log('AppRevive schema is ready. Existing records preserved.');
} catch { console.error('Migration failed. Check database and retry after fixing access.'); process.exitCode = 1; }
finally { await pool.end(); }
