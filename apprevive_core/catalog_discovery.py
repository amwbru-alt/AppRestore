"""Submit public app metadata as untrusted catalog candidates, never ownership.

No Apple account, device ID, session token, password or purchase date is sent.
A server failure is deliberately independent of restoration and its credits.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.request

from .api_config import api_base_url
from .restoration_codes import promo_ssl_context


def candidate_apps(rows):
    apps,seen=[],set()
    for row in rows:
        sid=str(row.get('trackId') or '')
        bundle=str(row.get('bundleId') or '')
        name=str(row.get('name') or '').strip()
        if (not re.fullmatch(r'[1-9][0-9]{7,11}',sid) or sid in seen
                or len(bundle)>255 or not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+',bundle)
                or not name or len(name)>255 or any(ord(c)<32 or ord(c)==127 for c in name)):
            continue
        seen.add(sid)
        apps.append({'trackId':sid,'bundleId':bundle,'name':name,'source':'apple_history'})
    return apps


def post_candidates(apps):
    url=api_base_url()+'/v3/catalog/discover'
    request=urllib.request.Request(url,data=json.dumps({'apps':apps}).encode('utf8'),method='POST',headers={'Content-Type':'application/json','User-Agent':'AppRevive-Catalog/1'})
    with urllib.request.urlopen(request,timeout=5,context=promo_ssl_context() if url.startswith('https:') else None) as response:
        if response.status!=200:
            return False
        raw=response.read(16385)
        return len(raw)<=16384 and json.loads(raw).get('status')=='ok'


class DiscoveryReporter:
    def __init__(self,post=None):
        self._post=post or post_candidates
        self._sent=set()
        self._lock=threading.Lock()

    def submit(self,rows):
        if not self._lock.acquire(blocking=False):
            return
        try:
            apps=[app for app in candidate_apps(rows) if app['trackId'] not in self._sent][:200]
            for start in range(0,len(apps),50):
                batch=apps[start:start+50]
                try:
                    if not self._post(batch):
                        return
                except Exception:
                    return  # next successful refresh retries, no restore failure
                self._sent.update(app['trackId'] for app in batch)
        finally:
            self._lock.release()
