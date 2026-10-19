import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
import { httpAuthOrigin, publicLinksAllowed } from '../src/transport.mjs';
import { Platform } from '../src/platform.mjs';
const origin='http://185.173.93.200:3000';
const env={PUBLIC_URL:origin,ALLOW_HTTP:'true',ALLOW_HTTP_AUTH:'true'};
test('public HTTP authentication is opt-in and bound to the configured origin',()=>{
 assert.equal(httpAuthOrigin(env),origin);
 assert.equal(publicLinksAllowed(env),true);
 assert.equal(httpAuthOrigin({...env,ALLOW_HTTP_AUTH:'false'}),'');
 assert.equal(httpAuthOrigin({...env,ALLOW_HTTP:'false'}),'');
 assert.equal(httpAuthOrigin({...env,PUBLIC_URL:'http://user:password@example.test'}),'');
 const p=Object.create(Platform.prototype);p.env=env;
 const req={method:'POST',socket:{remoteAddress:'203.0.113.5'},headers:{host:'185.173.93.200:3000',origin}};
 assert.doesNotThrow(()=>p.secure(req));
 assert.throws(()=>p.secure({...req,headers:{...req.headers,host:'another.example'}}),e=>e.status===426);
 assert.throws(()=>p.secure({...req,headers:{...req.headers,origin:'http://another.example'}}),e=>e.status===403);
 p.env={PUBLIC_URL:origin};assert.throws(()=>p.secure(req),e=>e.status===426);
});
test('browser HTTP login and request IDs work without secure-context randomUUID',async()=>{
 const source=await readFile(new URL('../public/assets/transport.js',import.meta.url),'utf8');
 function browser(config){const context={window:{},location:{protocol:'http:',hostname:'185.173.93.200',origin},fetch:async()=>({ok:true,json:async()=>config}),crypto:{getRandomValues:a=>webcrypto.getRandomValues(a)},Uint8Array,AbortController,setTimeout,clearTimeout};vm.runInNewContext(source,context);return context.window.AppReviveTransport;}
 const allowed=browser({transport:{http_auth_origin:origin}});await allowed.requireAllowed();
 const ids=new Set(Array.from({length:200},()=>allowed.requestId()));assert.equal(ids.size,200);assert([...ids].every(x=>/^[a-f0-9]{32}$/.test(x)));
 await assert.rejects(browser({transport:{http_auth_origin:'http://another.example'}}).requireAllowed());
 await assert.rejects(browser({}).requireAllowed());
});
