from __future__ import annotations

import urllib.error
import urllib.request
from unittest import mock

import pytest

from apprestore_core import network_policy as policy


@pytest.mark.parametrize("url", [
    "https://web.archive.org/cdx/search/cdx?q=private",
    "https://ipafilezone.com/api/search?q=private",
    "https://search.brave.com/search?q=private",
    "https://t0.gstatic.com/faviconV2?url=private",
    "https://itunes.apple.com.evil.test/lookup",
    "http://itunes.apple.com/lookup",
    "https://secret@itunes.apple.com/lookup",
    "https://itunes.apple.com:444/lookup",
    "file:///etc/passwd",
])
def test_disallowed_metadata_never_opens_connection(url):
    with mock.patch("urllib.request.build_opener") as opener:
        with pytest.raises(urllib.error.URLError):
            policy.urlopen(url)
        opener.assert_not_called()


def test_metadata_redirect_cannot_leak_query_to_other_host():
    req = urllib.request.Request("https://itunes.apple.com/lookup?id=42")
    with pytest.raises(urllib.error.URLError):
        policy._RedirectPolicy(False).redirect_request(
            req, None, 302, "Found", {}, "https://evil.test/collect?id=42"
        )


def test_apple_metadata_and_our_update_origins():
    assert policy.allowed_metadata("https://itunes.apple.com/lookup?id=42")
    assert policy.allowed_metadata("https://is1-ssl.mzstatic.com/image/thumb/x")
    assert policy.allowed_update("https://api.github.com/repos/amwbru-alt/AppRestore/releases/latest")
    assert not policy.allowed_update("https://api.github.com/repos/J3ckJ/AppRestore/releases/latest")
    assert not policy.allowed_update("https://github.com/amwbru-alt/AppRestore/releases/download-evil/x")
    assert not policy.allowed_update("https://objects.githubusercontent.com/x")
    assert policy.allowed_update("https://objects.githubusercontent.com/x", redirect=True)


def test_transport_only_allows_read_only_requests():
    with mock.patch("urllib.request.build_opener") as opener:
        with pytest.raises(urllib.error.URLError):
            policy.urlopen(urllib.request.Request("https://itunes.apple.com/lookup", data=b"secret"))
        opener.assert_not_called()
