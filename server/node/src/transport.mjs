// Explicit temporary HTTP mode. HTTPS remains the default without this opt-in.
export function publicOrigin(env = process.env) {
  try {
    const url = new URL(env.PUBLIC_URL);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname)) return '';
    return url.origin;
  } catch { return ''; }
}
export function httpAuthOrigin(env = process.env) {
  const origin = publicOrigin(env);
  return env.ALLOW_HTTP === 'true' && env.ALLOW_HTTP_AUTH === 'true' && origin.startsWith('http://') ? origin : '';
}
export function publicLinksAllowed(env = process.env) {
  return publicOrigin(env).startsWith('https://') || Boolean(httpAuthOrigin(env));
}
