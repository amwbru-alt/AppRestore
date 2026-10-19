import { httpAuthOrigin } from './transport.mjs';
import { open, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const root = fileURLToPath(new URL('../public/', import.meta.url));
const assets = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/account', ['account.html', 'text/html; charset=utf-8']],
  ['/admin', ['admin.html', 'text/html; charset=utf-8']],
  ['/assets/transport.js', ['assets/transport.js', 'text/javascript; charset=utf-8']],
  ['/assets/portal.css', ['assets/portal.css', 'text/css; charset=utf-8']],
  ['/assets/account.js', ['assets/account.js', 'text/javascript; charset=utf-8']],
  ['/assets/admin.js', ['assets/admin.js', 'text/javascript; charset=utf-8']],
  ['/assets/site.css', ['assets/site.css', 'text/css; charset=utf-8']],
  ['/assets/site.js', ['assets/site.js', 'text/javascript; charset=utf-8']],
  ['/assets/apprevive.png', ['assets/apprevive.png', 'image/png']],
  ['/assets/onest.ttf', ['assets/onest.ttf', 'font/ttf']],
  ['/assets/FONT-LICENSE.txt', ['assets/FONT-LICENSE.txt', 'text/plain; charset=utf-8']],
]);
const csp = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";
function headers(res, type) {
  res.setHeader('Content-Type', type); res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer'); res.setHeader('Content-Security-Policy', csp);
}
function external(value) {
  if (!value || /[\r\n]/.test(value) || value.length > 2048) return null;
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}
async function ready(file) { try { const info = await stat(file); return info.isFile() && info.size > 0; } catch { return false; } }
async function sendFile(req, res, file, type, filename) {
  let handle;
  try { handle = await open(file, 'r'); } catch (error) { if (error.code === 'ENOENT') return false; throw error; }
  const info = await handle.stat();
  if (!info.isFile() || info.size === 0) { await handle.close(); return false; }
  headers(res, type);
  if (filename) {
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    res.setHeader('Accept-Ranges', 'bytes');
  }
  res.setHeader('Cache-Control', filename || type.startsWith('text/html') ? 'no-store' : 'public, max-age=3600');
  let start = 0, end = info.size - 1;
  if (filename && req.headers.range && req.method === 'GET') {
    const match = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
    if (match && (match[1] || match[2])) {
      if (!match[1]) { start = Math.max(0, info.size - Number(match[2])); }
      else { start = Number(match[1]); end = match[2] ? Math.min(Number(match[2]), end) : end; }
    }
    if (!match || !(match[1] || match[2]) || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || start > end || start >= info.size || (!match[1] && Number(match[2]) === 0)) {
      await handle.close(); res.writeHead(416, { 'Content-Range': `bytes */${info.size}` }); res.end(); return true;
    }
    res.statusCode = 206; res.setHeader('Content-Range', `bytes ${start}-${end}/${info.size}`);
  }
  res.setHeader('Content-Length', end - start + 1);
  if (req.method === 'HEAD') { await handle.close(); res.end(); return true; }
  const stream = handle.createReadStream({ start, end, autoClose: true });
  stream.on('error', () => res.destroy()); res.on('close', () => stream.destroy()); stream.pipe(res);
  return true;
}
export function createWebsite({ env = process.env, downloadsDir = fileURLToPath(new URL('../downloads/', import.meta.url)), macUrl = process.env.DOWNLOAD_MAC_URL, windowsUrl = process.env.DOWNLOAD_WINDOWS_URL } = {}) {
  const platforms = { macos: { file: 'AppRevive-macOS.zip', url: external(macUrl) }, windows: { file: 'AppRevive-Windows.zip', url: external(windowsUrl) } };
  return async (req, res, path) => {
    const key = path.startsWith('/download/') ? path.slice('/download/'.length) : '';
    const platform = Object.hasOwn(platforms, key) ? platforms[key] : null;
    const asset = assets.get(path);
    if (!asset && !platform && path !== '/site-config' && path !== '/robots.txt') return false;
    if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }); res.end(); return true; }
    if (path === '/site-config') {
      const downloads = {};
      for (const [key, config] of Object.entries(platforms)) downloads[key] = Boolean(config.url) || await ready(join(downloadsDir, config.file));
      headers(res, 'application/json; charset=utf-8'); res.setHeader('Cache-Control', 'no-store');
      res.end(req.method === 'HEAD' ? '' : JSON.stringify({ downloads, transport: { http_auth_origin: httpAuthOrigin(env) } })); return true;
    }
    if (path === '/robots.txt') { headers(res, 'text/plain; charset=utf-8'); res.end(req.method === 'HEAD' ? '' : 'User-agent: *\nAllow: /\nDisallow: /v1/\nDisallow: /v2/\nDisallow: /site-config\n'); return true; }
    if (platform) {
      if (platform.url) { res.writeHead(302, { Location: platform.url, 'Cache-Control': 'no-store' }); res.end(); return true; }
      if (await sendFile(req, res, join(downloadsDir, platform.file), 'application/zip', platform.file)) return true;
      headers(res, 'text/html; charset=utf-8'); res.statusCode = 503; res.setHeader('Cache-Control', 'no-store');
      res.end(req.method === 'HEAD' ? '' : '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Скачивание AppRevive</title><link rel="stylesheet" href="/assets/site.css"><main class="section wrap"><a class="brand" href="/">AppRevive.</a><br><h1>Архив пока<br>не опубликован.</h1><br><p>Свяжитесь с поддержкой, чтобы получить актуальную сборку для вашего компьютера.</p><br><a class="button primary" href="https://t.me/llifegoldll">Написать в Telegram ↗</a><br><br><a class="text-link" href="/">← На главную</a></main></html>'); return true;
    }
    if (await sendFile(req, res, join(root, asset[0]), asset[1])) return true;
    res.writeHead(404); res.end(); return true;
  };
}
