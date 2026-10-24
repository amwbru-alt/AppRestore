import { readFile } from 'node:fs/promises';
import { createDatabase } from './db.mjs';
import { failureKind } from './diagnostics.mjs';
export const schemaFiles = ['schema.sql','catalog-schema.sql','accounts-schema.sql','partners-schema.sql','catalog-groups-schema.sql','platform-schema.sql','discoveries-schema.sql'];
// Read expected tables and columns from the same versioned DDL used by migration.
export async function expectedSchema() {
  const tables = [];
  for(const file of schemaFiles) {
    const ddl = await readFile(new URL('../../promo/'+file,import.meta.url),'utf8');
    for(const match of ddl.matchAll(/CREATE TABLE IF NOT EXISTS\s+(apprevive_[a-z_]+)\s*\(([\s\S]*?)\)\s*ENGINE/gi)) {
      const columns = [...match[2].matchAll(/^\s*([a-z_]+)\s+(?:CHAR|VARCHAR|TINYINT|SMALLINT|INT|BIGINT|TIMESTAMP|DATETIME|ENUM|TEXT|MEDIUMTEXT|JSON|DECIMAL|BINARY|VARBINARY)\b/gim)].map(m=>m[1]);
      if(!columns.length)throw new Error('Schema definition has no columns');
      tables.push({table:match[1],columns});
    }
  }
  return tables;
}
export async function checkDatabase(pool) {
  const failures=[];
  for(const {table,columns} of await expectedSchema()) {
    try {await pool.query(`SELECT ${columns.map(c=>'`'+c+'`').join(',')} FROM \`${table}\` LIMIT 0`);}
    catch(error) {const kind=failureKind(error);failures.push({table,kind});if(kind!=='database_schema_outdated')break;}
  }
  return failures;
}
export async function doctor() {
  let pool;
  try {
    pool=createDatabase();const failures=await checkDatabase(pool);
    if(!failures.length){console.log('AppRevive database: all required tables and columns are ready.');return 0;}
    for(const failure of failures)console.error(`${failure.kind}: ${failure.table}`);
    console.error('For schema errors run npm run migrate, then npm run doctor and restart Node. For connection errors check server DB settings and database availability.');return 1;
  }catch{console.error('Cannot check AppRevive database. Check server DB environment. No credentials are printed.');return 1;}
  finally{if(pool)await pool.end();}
}
