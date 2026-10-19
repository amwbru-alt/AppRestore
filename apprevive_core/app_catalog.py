"""Read the public catalog through the Node.js API, never directly from MySQL."""
from __future__ import annotations
import json
import re
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
        item = dict(trackId=sid, name=name[:255], iconUrl=url[:2048])
        group_id, group_name = row.get('groupId'), row.get('groupName')
        if isinstance(group_id, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', group_id) and isinstance(group_name, str) and group_name.strip():
            icon = str(row.get('groupIconUrl') or '')
            parsed_icon = urllib.parse.urlsplit(icon)
            if parsed_icon.scheme != 'https' or not parsed_icon.hostname or parsed_icon.username or parsed_icon.password:
                icon = ''
            item.update(groupId=group_id, groupName=group_name.strip()[:255], groupIconUrl=icon[:2048])
        result.append(item)
        seen.add(sid)
    return result


