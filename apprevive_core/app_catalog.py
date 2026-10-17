"""Read the public catalog through the Node.js API, never directly from MySQL."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
from .api_config import api_base_url
from .restoration_codes import promo_ssl_context

MAX_APPS = 5000


def read_catalog() -> list[dict[str, object]]:
    url = api_base_url() + '/v1/catalog'
    context = promo_ssl_context() if urllib.parse.urlsplit(url).scheme == 'https' else None
    request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'AppRevive/0.4'})
    with urllib.request.urlopen(request, timeout=10, context=context) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('Catalog response too large')
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('status') != 'ok' or not isinstance(data.get('apps'), list):
        raise ValueError('Invalid catalog response')
    return validate_catalog(data['apps'])


def validate_catalog(rows):
    if not isinstance(rows, list):
        raise ValueError('Invalid catalog')
    result = []
    seen = set()
    for row in rows[:MAX_APPS]:
        if not isinstance(row, dict):
            continue
        sid, name = str(row.get('trackId') or ''), str(row.get('name') or '').strip()
        if not sid.isdigit() or not 8 <= len(sid) <= 12 or not name or sid in seen:
            continue
        url = str(row.get('iconUrl') or '')
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            url = ''
        result.append(dict(trackId=sid, name=name[:255], iconUrl=url[:2048]))
        seen.add(sid)
    return result


