"""Shared application catalog in MySQL; no network during UI rendering."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request
import ssl
import certifi
import pymysql
from .mysql_promo import mysql_settings

MAX_APPS = 5000


def read_catalog() -> list[dict[str, object]]:
    options = mysql_settings()
    options.update(connect_timeout=5, read_timeout=10)
    with pymysql.connect(**options) as db, db.cursor() as cur:
        cur.execute("SELECT store_id, name, icon_url FROM apprevive_app_catalog WHERE enabled=1 ORDER BY name LIMIT %s", (MAX_APPS,))
        rows = cur.fetchall()
    return validate_catalog([dict(trackId=str(sid), name=name, iconUrl=url or '') for sid, name, url in rows])


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


def sync_icons() -> tuple[int, int]:
    """Administrator command: discover public artwork; never overwrite manual URLs."""
    context = ssl.create_default_context(cafile=certifi.where())
    updated = failed = 0
    with pymysql.connect(**mysql_settings()) as db:
        with db.cursor() as cur:
            cur.execute("SELECT store_id FROM apprevive_app_catalog WHERE icon_url='' AND enabled=1")
            ids = [str(row[0]) for row in cur.fetchall()]
        for start in range(0, len(ids), 40):
            missing = set(ids[start:start + 40])
            for country in ('ru', 'us'):
                if not missing:
                    break
                query = urllib.parse.urlencode(dict(id=','.join(sorted(missing)), country=country))
                try:
                    with urllib.request.urlopen('https://itunes.apple.com/lookup?' + query, timeout=15, context=context) as response:
                        raw = response.read(4 * 1024 * 1024 + 1)
                    if len(raw) > 4 * 1024 * 1024:
                        raise ValueError('Response too large')
                    data = json.loads(raw)
                    rows = validate_catalog([dict(trackId=str(item.get('trackId') or ''), name=item.get('trackName'), iconUrl=item.get('artworkUrl512') or item.get('artworkUrl100')) for item in data.get('results', []) if isinstance(item, dict)])
                    with db.cursor() as cur:
                        for row in rows:
                            if row['trackId'] not in missing or not row['iconUrl']:
                                continue
                            cur.execute("UPDATE apprevive_app_catalog SET icon_url=%s WHERE store_id=%s AND icon_url=''", (row['iconUrl'], row['trackId']))
                            updated += cur.rowcount
                            missing.discard(row['trackId'])
                    db.commit()
                except (OSError, ValueError):
                    failed += 1
    return updated, failed


def main():
    parser = argparse.ArgumentParser(description='AppRevive MySQL application catalog')
    parser.add_argument('command', choices=['sync-icons'])
    parser.parse_args()
    try:
        count, failed = sync_icons()
    except (pymysql.MySQLError, OSError, ValueError):
        parser.exit(1, 'Не удалось обновить каталог. Проверьте MySQL и настройки; реквизиты не выводятся.\n')
    print(f'Иконок добавлено: {count}; неудачных запросов к Apple: {failed}. Для остальных используется стандартная картинка.')


if __name__ == '__main__':
    main()
