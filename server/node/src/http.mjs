import http from 'node:http';
import { ApiError } from './service.mjs';
const loopback = address => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(address);

function reply(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}
async function jsonBody(req) {
  if (String(req.headers['content-type'] || '').split(';')[0].trim().toLowerCase() !== 'application/json') throw new ApiError(415, 'json_required');
  let size = 0;
  const parts = [];
  for await (const part of req) {
    size += part.length;
    if (size > 4096) throw new ApiError(413, 'request_too_large');
    parts.push(part);
  }
  try { return JSON.parse(Buffer.concat(parts).toString('utf8')); }
  catch { throw new ApiError(400, 'invalid_json'); }
}
export function createApi(service, { requireHttps = true, redemptionLimit = 20, now = Date.now, accounts = null, partners = null } = {}) {
  const attempts = new Map();
  let lastPrune = 0;
  const server = http.createServer(async (req, res) => {
    try {
      const path = new URL(req.url, 'http://internal').pathname;
      if (path === '/health' && req.method === 'GET') return reply(res, 200, { status: 'ok' });
      if (requireHttps && !(req.socket.encrypted || loopback(req.socket.remoteAddress) && req.headers['x-forwarded-proto'] === 'https')) throw new ApiError(426, 'https_required');
      if (path === '/v1/catalog' && req.method === 'GET') return reply(res, 200, await service.catalog());
      if ((path === '/v1/redeem' || path.startsWith('/v2/account/') || path.startsWith('/v2/partner/')) && req.method === 'POST') {
        const time = now();
        if (time - lastPrune > 60000) {
          for (const [key, value] of attempts) if (value.until <= time) attempts.delete(key);
          lastPrune = time;
        }
        const ip = loopback(req.socket.remoteAddress) ? String(req.headers['x-real-ip'] || req.socket.remoteAddress) : req.socket.remoteAddress;
        let entry = attempts.get(ip);
        if (!entry || entry.until <= time) {
          if (attempts.size >= 10000 && !entry) throw new ApiError(429, 'rate_limited');
          entry = { count: 0, until: time + 60000 }; attempts.set(ip, entry);
        }
        if (++entry.count > redemptionLimit) throw new ApiError(429, 'rate_limited');
        if (path.startsWith('/v2/partner/')) {
          const name = path.slice('/v2/partner/'.length);
          if (!partners || !['profile', 'bind'].includes(name)) throw new ApiError(404, 'not_found');
          return reply(res, 200, await partners[name](await jsonBody(req)));
        }
        if (path.startsWith('/v2/account/')) {
          const methods = { balance: 'balance', redeem: 'redeem', reserve: 'reserve', finish: 'finish' };
          const key = path.slice('/v2/account/'.length);
          const method = Object.hasOwn(methods, key) ? methods[key] : null;
          if (!accounts || !method) throw new ApiError(404, 'not_found');
          return reply(res, 200, await accounts[method](await jsonBody(req)));
        }
        return reply(res, 200, await service.redeem(await jsonBody(req)));
      }
      throw new ApiError(['/v1/catalog', '/v1/redeem'].includes(path) ? 405 : 404, 'not_found');
    } catch (error) {
      // Never return or log SQL, passwords, submitted codes, tokens or account data.
      reply(res, error instanceof ApiError ? error.status : 503, { status: error instanceof ApiError ? error.code : 'unavailable' });
    }
  });
  server.requestTimeout = 20000;
  server.headersTimeout = 10000;
  return server;
}
