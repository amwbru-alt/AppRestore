import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,readFile,writeFile,rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { parseEnv } from 'node:util';
import { configureText,configureFile } from '../src/configure-http.mjs';
test('HTTP setup preserves database/mail credentials, removes conflicting duplicate flags and is repeatable',async t=>{
 const text='DB_HOST=mysql.example\nDB_PASSWORD="isolated test secret/#"\nRESEND_API_KEY="fake-test-key"\nALLOW_HTTP=false\nexport ALLOW_HTTP_AUTH=false\nALLOW_HTTP_AUTH=false\nPUBLIC_URL=https://YOUR_DOMAIN\n';
 const updated=configureText(text),env=parseEnv(updated);
 assert.equal(env.DB_PASSWORD,parseEnv(text).DB_PASSWORD);assert.equal(env.RESEND_API_KEY,'fake-test-key');
 assert.equal(env.ALLOW_HTTP,'true');assert.equal(env.ALLOW_HTTP_AUTH,'true');assert.equal(env.PUBLIC_URL,'http://185.173.93.200:3000');
 assert.equal(configureText(updated),updated);
 const dir=await mkdtemp(join(tmpdir(),'apprevive-env-'));t.after(()=>rm(dir,{recursive:true,force:true}));
 const file=join(dir,'.env');await writeFile(file,text);await configureFile(file);await configureFile(file);
 assert.equal(await readFile(file+'.before-http','utf8'),text);assert.equal(await readFile(file,'utf8'),updated);
});
