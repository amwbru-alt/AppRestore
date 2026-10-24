import { constants } from 'node:fs';
import { readFile,writeFile,copyFile,chmod,rename,lstat,unlink } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { randomUUID } from 'node:crypto';
const settings={HOST:'0.0.0.0',PORT:'3000',ALLOW_HTTP:'true',ALLOW_HTTP_AUTH:'true',DEV_ALLOW_INSECURE_AUTH:'false',PUBLIC_URL:'http://185.173.93.200:3000'};
export function configureText(text){
 const before=parseEnv(text);
 const lines=text.split(/\r?\n/).filter(line=>!Object.keys(settings).some(key=>new RegExp('^\\s*(?:export\\s+)?'+key+'\\s*=').test(line)));
 const result=lines.join('\n').trimEnd()+'\n'+Object.entries(settings).map(([k,v])=>k+'='+v).join('\n')+'\n';
 const after=parseEnv(result);
 if(Object.keys(before).some(key=>!(key in settings)&&before[key]!==after[key]))throw Error('Unrelated settings would change; no file was written.');
 return result;
}
export async function configureFile(file='.env'){
 const info=await lstat(file);if(!info.isFile()||info.isSymbolicLink())throw Error('Use a regular server .env file.');
 const text=configureText(await readFile(file,'utf8'));
 const backup=file+'.before-http';
 try{await copyFile(file,backup,constants.COPYFILE_EXCL);await chmod(backup,0o600);}catch(error){if(error.code!=='EEXIST')throw error;}
 const temporary=file+'.http-'+randomUUID();
 try{await writeFile(temporary,text,{mode:0o600,flag:'wx'});await rename(temporary,file);}finally{await unlink(temporary).catch(()=>{});}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 try{await configureFile();console.log('HTTP configured for http://185.173.93.200:3000. Other settings preserved. Restart your existing Node/PM2/systemd service, then check /site-config and /v3/status.');}
 catch{console.error('Cannot configure HTTP. Run from server/node with an existing regular .env file. No database credentials are printed.');process.exitCode=1;}
}
