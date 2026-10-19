"""Public API endpoint only. The desktop app never reads database credentials."""
from __future__ import annotations
import json
import os
from pathlib import Path
import urllib.parse


def api_base_url() -> str:
    value = os.environ.get('APPREVIVE_API_URL', '')
    if not value:
        local = Path.home() / '.apprevive' / 'api.json'
        path = local if local.exists() else Path(__file__).with_name('api_settings.json')
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            value = data.get('base_url', '') if isinstance(data, dict) else ''
        except (OSError, ValueError):
            raise ValueError('Не удалось прочитать настройки API AppRevive.') from None
    if not isinstance(value, str):
        raise ValueError('Некорректный адрес API AppRevive.')
    value = value.strip().rstrip('/')
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Укажите адрес API AppRevive в формате http://IP:3000 в настройках api.json.')
    try:
        parsed.port
    except ValueError:
        raise ValueError('Некорректный порт API AppRevive.') from None
    return value


def api_allows_http(url: str) -> bool:
    """Allow plaintext authentication only for an explicitly configured origin."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'http' or parsed.username or parsed.password:
        return False
    if parsed.hostname in ('127.0.0.1', 'localhost', '::1'):
        return True
    origin = os.environ.get('APPREVIVE_HTTP_AUTH_ORIGIN', '')
    if not origin:
        try:
            settings = json.loads(Path(__file__).with_name('api_settings.json').read_text(encoding='utf-8-sig'))
            origin = settings.get('http_auth_origin', '')
        except (OSError, ValueError, AttributeError):
            return False
    if not isinstance(origin, str):
        return False
    allowed = urllib.parse.urlsplit(origin)
    try:
        return (allowed.scheme == 'http' and not allowed.username and not allowed.password
                and allowed.path in ('', '/') and not allowed.query and not allowed.fragment
                and (parsed.hostname, parsed.port or 80) == (allowed.hostname, allowed.port or 80))
    except ValueError:
        return False
