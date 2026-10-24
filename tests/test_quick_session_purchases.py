"""QuickSession wiring: session check states, sign-out deletes the cache."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

import apprevive_core.ipatool_api as api  # noqa: E402
from apprevive_core.purchases_cache import CachedPurchase, PurchasesCache, account_key  # noqa: E402
from apprevive_gui import quick_session as qs  # noqa: E402
from apprevive_gui.purchases import PurchasesLoader, SessionChecker  # noqa: E402

EMAIL = "person@example.com"


class FakeService:
    def __init__(self) -> None:
        self.revoked = 0
        self.core = SimpleNamespace(tools=SimpleNamespace(_ipatool_env=lambda: {}))

    def keychain_passphrase(self) -> str:
        return ""

    def revoke(self) -> None:
        self.revoked += 1

    def clear_keychain_passphrase(self) -> None:
        pass


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication

    return QCoreApplication.instance() or QCoreApplication([])


def _drain(app) -> None:
    # loginPrompt is emitted from the worker thread; Qt delivers it queued.
    for _ in range(5):
        app.processEvents()


@pytest.fixture()
def session(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(qs, "DiscoveryReporter", lambda: SimpleNamespace(submit=lambda rows: None))
    monkeypatch.setattr(qs, "GuiService", lambda demo_mode=False: FakeService())
    monkeypatch.setattr(qs, "load_bindings", lambda: {})
    monkeypatch.setattr(qs, "forget_session", lambda email: None)
    monkeypatch.setattr(qs, "PurchasesCache", lambda: PurchasesCache(tmp_path))
    s = qs.QuickSession()
    s._signed = True
    s._phase = "in"
    s._account_email = EMAIL
    prompts: list[str] = []
    s.loginPrompt.connect(prompts.append)
    s._drain = lambda: _drain(qapp)
    return s, prompts, PurchasesCache(tmp_path)


def _probe(s, answer) -> None:
    class Client:
        def session_alive(self, timeout):
            if isinstance(answer, BaseException):
                raise answer
            return answer

    s._session_checker = SessionChecker(lambda: Client(), s._on_session_view)
    s.checkSession()
    s._session_checker.join(5)
    s._drain()


def _check(state, code=None):
    error = api.IpatoolError(code) if code else None
    return api.SessionCheck(state, 0.1, error)


def test_alive(session) -> None:
    s, prompts, _ = session
    _probe(s, _check(api.SessionState.ALIVE))
    assert s.sessionState == "alive" and not s.sessionRelogin
    assert prompts == [] and s.signedIn


def test_unlocked_keychain_resolves_account_and_starts_purchases_without_passwordless_probe(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, _prompts, _cache = session
    s._account_email = ""  # opening a saved keychain, not a new Apple ID login
    s._auth_status = "Сессия открыта."
    s.service.keychain_ready = lambda: True
    calls = []
    s.service.core.tools.ipatool_auth_info = lambda: {"success": True, "email": EMAIL}
    s._purchases = SimpleNamespace(
        set_account=lambda email: calls.append(("account", email)),
        start=lambda: calls.append(("purchases",)),
    )
    s._session_checker = SimpleNamespace(start=lambda: calls.append(("session",)))
    monkeypatch.setattr(qs, "save_session", lambda email: calls.append(("save", email)))
    monkeypatch.setattr(qs, "probe_keychain", lambda: pytest.fail("must use secure auth info after unlock"))
    s._refresh_auth()
    assert s.signedIn and s.accountEmail == EMAIL
    assert calls == [("save", EMAIL), ("account", EMAIL), ("purchases",), ("session",)]


def test_locked_startup_does_not_fetch_purchases_or_try_to_guess_an_account(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, _prompts, _cache = session
    s._signed = False
    s._phase = "checking"
    s._account_email = ""
    s.service.keychain_ready = lambda: False
    s.service.core.tools.ipatool_auth_info = lambda: pytest.fail("no passphrase provided")
    s._purchases = SimpleNamespace(start=lambda: pytest.fail("no account yet"))
    monkeypatch.setattr(qs, "probe_keychain", lambda: "locked")
    prompted = []
    s.keychainPrompt.connect(prompted.append)
    s._refresh_auth()
    assert not s.signedIn and s.accountEmail == "" and s.authPhase == "locked"
    assert prompted == [""]


def test_failed_secure_info_does_not_drop_an_already_open_session(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, _prompts, _cache = session
    s.service.keychain_ready = lambda: True
    s.service.core.tools.ipatool_auth_info = lambda: None
    monkeypatch.setattr(qs, "probe_keychain", lambda: "locked")
    s._purchases = SimpleNamespace(start=lambda: pytest.fail("unverified account"))
    s._refresh_auth()
    assert s.signedIn and s.accountEmail == EMAIL


def test_expired_offers_sign_in_again(session) -> None:
    s, prompts, _ = session
    _probe(s, _check(api.SessionState.EXPIRED, api.ErrorCode.TOKEN_EXPIRED))
    assert s.sessionState == "expired" and s.sessionRelogin
    assert prompts == [EMAIL]
    assert s.sessionNote == api.MESSAGES_RU[api.ErrorCode.TOKEN_EXPIRED]


def test_no_network_keeps_the_account(session) -> None:
    s, prompts, _ = session
    _probe(s, _check(api.SessionState.NO_NETWORK, api.ErrorCode.TIMEOUT))
    assert s.sessionState == "offline" and "Нет связи" in s.sessionNote
    assert prompts == []
    assert s.signedIn and s.accountEmail == EMAIL


def test_sign_out_deletes_purchases_cache(session) -> None:
    s, _prompts, cache = session
    s._purchases.set_account(EMAIL)
    cache.save(cache.account_key(EMAIL), [CachedPurchase(1, "com.example.a", "A", "")])
    s._purchases.show_cached()
    assert len(s.purchases) == 1
    s.signOut()
    assert s.service.revoked == 1  # core sign_out (revoke + cache delete) via GuiService
    assert not cache.path.exists()
    assert s.purchases == [] and s.sessionState == "unknown"


def test_purchases_session_problem_routes_to_relogin(session, tmp_path: Path) -> None:
    s, prompts, _ = session

    class Client:
        def iter_purchases(self, cancel_event=None, *, prefer_all=True):
            raise api.IpatoolError(api.ErrorCode.AUTH_CODE_REQUIRED, "x")
            yield  # pragma: no cover

    s._purchases = PurchasesLoader(PurchasesCache(tmp_path), lambda: Client(), s._on_purchases_view)
    s._purchases.set_account(EMAIL)
    s.loadPurchases()
    s._purchases.join(5)
    s._drain()
    assert s.purchasesNote == api.MESSAGES_RU[api.ErrorCode.AUTH_CODE_REQUIRED]
    assert s.sessionState == "expired" and prompts == [EMAIL]


APPLE_128 = "failed to purchase item with param 'STDQ': Account Not In This Store"


def _failing_install(s, exc: BaseException) -> list[tuple]:
    settled: list[tuple] = []
    s.installSettled.connect(lambda *args: settled.append(args))
    s.service.core = SimpleNamespace(tools=SimpleNamespace(runner=SimpleNamespace()))
    s._ensure_keychain = lambda: True

    def boom(*_args, **_kwargs):
        raise exc

    s._restore_store_gated = boom
    s._busy = True
    s._install_store("UDID", "389801252", True)
    s._drain()
    return settled


def test_store_mismatch_offers_sign_in_again_like_expired(session) -> None:
    from apprevive_core.license_gate import STORE_MISMATCH_TEXT
    from apprevive_core.tools import ToolUnavailable

    s, prompts, _ = session
    settled = _failing_install(s, ToolUnavailable(APPLE_128))
    assert settled == [("389801252", False, STORE_MISMATCH_TEXT)]
    assert s.sessionState == "expired" and s.sessionRelogin  # the "Войти заново" button
    assert s.sessionNote == STORE_MISMATCH_TEXT
    assert prompts == [EMAIL]
    assert s.signedIn  # offered, not signed out


def test_other_install_errors_do_not_offer_relogin(session) -> None:
    from apprevive_core.tools import ToolUnavailable

    s, prompts, _ = session
    _failing_install(s, ToolUnavailable("failed to purchase item: something else"))
    assert not s.sessionRelogin and prompts == []


def test_restoration_history_requires_fresh_account_and_matching_phone(session):
    from apprevive_gui.purchases import PurchasesView
    from apprevive_core.history_filter import device_inventory
    s, _, _ = session
    rows = ({'trackId':'12345678','bundleId':'bank.old','name':'Old'},
            {'trackId':'22345678','bundleId':'bank.current','name':'Current'})
    s._purchases._account = account_key(EMAIL)
    s._udid = 'phone-a'
    s._history_inventory_udid = 'phone-a'
    s._history_inventory = device_inventory({'bank.current':{'CFBundleIdentifier':'bank.current'}})
    s._purchases_view = PurchasesView(rows=rows, from_cache=True)
    assert s.restorationPurchases == []
    s._purchases_view = PurchasesView(rows=rows, confirmed=True, account=account_key(EMAIL))
    assert [r['trackId'] for r in s.restorationPurchases] == ['12345678']
    s._purchases._account = account_key('other@example.test')
    assert s.restorationPurchases == []
    s._purchases._account = account_key(EMAIL)
    s._udid = 'phone-b'
    assert s.restorationPurchases == []
    s._udid = ''
    assert s.restorationPurchases == []
    assert 'Подключите' in s.restorationHistoryNote


def test_history_device_read_failure_hides_previous_inventory(session):
    import time
    from apprevive_gui.purchases import PurchasesView
    from apprevive_core.history_filter import device_inventory
    s, _, _ = session
    s._purchases._account = account_key(EMAIL)
    s._udid = 'phone-a'
    s._history_inventory_udid = 'phone-a'
    s._history_inventory = device_inventory({})
    s._purchases_view = PurchasesView(rows=({'trackId':'12345678','bundleId':'bank.old'},), confirmed=True, account=account_key(EMAIL))
    def fail(_):
        raise RuntimeError('device locked')
    s.service.core.tools.list_apps = fail
    s._ensure_history_inventory(force=True)
    deadline = time.monotonic()+2
    while s._history_scan_running and time.monotonic()<deadline:
        time.sleep(.005)
    assert not s._history_scan_running
    assert s.restorationPurchases == []
    assert 'Не удалось проверить' in s.restorationHistoryNote


def test_device_switch_discards_inflight_inventory(session):
    import threading
    import time
    from apprevive_gui.purchases import PurchasesView
    s, _, _ = session
    entered, release = threading.Event(), threading.Event()
    s._purchases._account = account_key(EMAIL)
    s._udid = 'phone-a'
    s._purchases_view = PurchasesView(rows=({'trackId':'12345678','bundleId':'bank.old'},), confirmed=True, account=account_key(EMAIL))
    def scan(udid):
        if udid=='phone-a':
            entered.set()
            release.wait(2)
            return {}
        return {'bank.old':{'CFBundleIdentifier':'bank.old'}}
    s.service.core.tools.list_apps = scan
    s._ensure_history_inventory()
    assert entered.wait(1)
    s._udid = 'phone-b'
    s._ensure_history_inventory(force=True)
    assert s.restorationPurchases == []
    release.set()
    deadline=time.monotonic()+2
    while (s._history_scan_running or s._history_inventory_udid!='phone-b') and time.monotonic()<deadline:
        time.sleep(.005)
    assert s._history_inventory_udid=='phone-b'
    assert s.restorationPurchases == []


def test_confirmed_missing_history_triggers_candidate_reporting(session):
    import threading
    from apprevive_gui.purchases import PurchasesView
    from apprevive_core.history_filter import device_inventory
    s, _, _ = session
    s._udid='phone-a'
    s._history_inventory_udid='phone-a'
    s._history_inventory=device_inventory({})
    s._purchases._account=account_key(EMAIL)
    reported,done=[],threading.Event()
    def submit(rows):
        reported.extend(rows)
        done.set()
    s._discovery_reporter=SimpleNamespace(submit=submit)
    row={'trackId':'12345678','bundleId':'bank.old','name':'Old'}
    s._on_purchases_view(PurchasesView(rows=(row,),confirmed=True,account=account_key(EMAIL)))
    assert done.wait(1)
    assert reported==[row]
