"""Fail-closed destinations for Python runtime HTTP (not native Apple tools).

Public metadata stays on Apple. Optional search/archive/favicon providers are
blocked before DNS, including redirects. Updates are restricted to our fork.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

OWNER_REPO = "amwbru-alt/AppRestore"


def _parts(url: str) -> urllib.parse.SplitResult:
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise urllib.error.URLError("ReVivo: разрешены только доверенные HTTPS-адреса")
    return p


def allowed_metadata(url: str) -> bool:
    try:
        p = _parts(url)
    except (ValueError, urllib.error.URLError):
        return False
    host = p.hostname or ""
    return host == "itunes.apple.com" or host == "mzstatic.com" or host.endswith(".mzstatic.com")


def allowed_update(url: str, *, redirect: bool = False) -> bool:
    try:
        p = _parts(url)
    except (ValueError, urllib.error.URLError):
        return False
    if p.hostname == "api.github.com":
        return p.path.startswith(f"/repos/{OWNER_REPO}/releases/")
    if p.hostname == "github.com":
        return p.path.startswith(f"/{OWNER_REPO}/releases/download/")
    return redirect and p.hostname in {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}


class _RedirectPolicy(urllib.request.HTTPRedirectHandler):
    def __init__(self, updates: bool) -> None:
        self.updates = updates

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        allowed = allowed_update(target, redirect=True) if self.updates else allowed_metadata(target)
        if not allowed:
            raise urllib.error.URLError("ReVivo: стороннее перенаправление заблокировано")
        return super().redirect_request(req, fp, code, msg, headers, target)


def urlopen(request: urllib.request.Request | str, *, timeout: float = 20, updates: bool = False):
    """Open a public, read-only request with a destination-aware redirect handler."""
    req = urllib.request.Request(request) if isinstance(request, str) else request
    allowed = allowed_update(req.full_url) if updates else allowed_metadata(req.full_url)
    if not allowed or req.get_method() != "GET" or req.data is not None:
        raise urllib.error.URLError("ReVivo: необязательный сторонний сервис отключён")
    # Build our own opener: a global opener may contain cookies or auth handlers.
    opener = urllib.request.build_opener(_RedirectPolicy(updates))
    opener.addheaders = []
    return opener.open(req, timeout=timeout)
