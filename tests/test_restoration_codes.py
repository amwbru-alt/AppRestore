from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from apprevive_core.restoration_codes import RestorationAccess, RestorationCredits, RestorationCodeError, activate_promo


def allow(*codes):
    def activate(code, token, request_id):
        if code not in codes:
            raise RestorationCodeError('Код не найден или уже использован.')
    return activate


def test_first_success_is_free_failure_keeps_gift_and_restart_does_not_reset(tmp_path):
    path = tmp_path / 'credits.sqlite3'
    store = RestorationCredits(path)
    gate = RestorationAccess(store, lambda: False)
    def failure():
        raise RuntimeError('USB disconnected')
    with pytest.raises(RuntimeError, match='USB'):
        gate.run(failure)
    assert store.remaining == 1
    assert gate.run(lambda: 'installed') == 'installed'
    assert RestorationCredits(path).remaining == 0
    action = Mock()
    with pytest.raises(RestorationCodeError, match='отменено'):
        gate.run(action)
    action.assert_not_called()


def test_valid_code_adds_one_credit_once_persistently(tmp_path):
    path = tmp_path / 'credits.sqlite3'
    store = RestorationCredits(path, activate=allow('ABC-123','OTHER'))
    for code in ('ABC', 'abc-123', 'xABC-123x'):
        with pytest.raises(RestorationCodeError, match='Код не найден'):
            store.redeem(code)
    assert store.remaining == 1
    assert store.redeem('  ABC-123  ') == 2
    other = RestorationCredits(path, activate=lambda *a: pytest.fail('used code must not need network'))
    with pytest.raises(RestorationCodeError, match='уже использован'):
        other.redeem('ABC-123')
    assert other.remaining == 2
    assert 'ABC-123' not in path.read_bytes().decode('latin1')


def test_code_prompt_resumes_same_action_and_nested_install_is_charged_once(tmp_path):
    store = RestorationCredits(tmp_path / 'credits.sqlite3', activate=allow('NEXT'))
    calls = []
    def prompt():
        calls.append('prompt')
        store.redeem('NEXT')
        return True
    gate = RestorationAccess(store, prompt)
    assert gate.run(lambda: gate.run(lambda: 42)) == 42
    assert store.remaining == 0
    gate.run(lambda: calls.append('installed'))
    assert calls == ['prompt', 'installed'] and store.remaining == 0


def test_lost_server_response_reuses_persistent_request_after_restart(tmp_path):
    path = tmp_path / 'credits.sqlite3'
    calls = []
    def unavailable(code, token, request):
        calls.append((code, token, request))
        raise RestorationCodeError('Ответ потерян')
    store = RestorationCredits(path, activate=unavailable)
    with pytest.raises(RestorationCodeError):
        store.redeem('NEXT')
    assert store.remaining == 1
    restored = RestorationCredits(path, activate=lambda *args: calls.append(args))
    assert restored.redeem('NEXT') == 2
    assert len(calls) == 2 and calls[0] == calls[1]


def test_parallel_local_replies_only_credit_once(tmp_path):
    import threading
    path = tmp_path / 'credits.sqlite3'
    barrier = threading.Barrier(2)
    calls=[]
    def activate(*args):
        calls.append(args)
        barrier.wait(3)
    stores = [RestorationCredits(path, activate=activate) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda store: store.redeem('ONE'), stores))
    assert results == [2,2]
    assert stores[0].remaining == 2
    assert calls[0] == calls[1]


def test_concurrent_installs_cannot_spend_one_gift_twice(tmp_path):
    path = tmp_path / 'credits.sqlite3'
    stores = [RestorationCredits(path) for _ in range(2)]
    calls=[]
    def run(store):
        try:
            RestorationAccess(store,lambda:False).run(lambda:calls.append('installed'))
            return True
        except RestorationCodeError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run,stores)) == [False,True]
    assert calls == ['installed'] and stores[0].remaining == 0


def test_api_uses_https_post_and_validates_receipt(monkeypatch):
    import ssl
    def respond(request, **kwargs):
        assert request.full_url == 'https://sv-bz.ru/apprevive/redeem.php'
        assert request.get_method() == 'POST'
        assert kwargs['context'].check_hostname and kwargs['context'].verify_mode == ssl.CERT_REQUIRED
        assert kwargs['context'].cert_store_stats()['x509_ca'] > 0
        body=json.loads(request.data)
        assert body == {'code':'ONE','installation_token':'a'*64,'request_id':'b'*32}
        assert 'password' not in body
        return io.BytesIO(json.dumps({'status':'activated','credits':1,'code_hash':hashlib.sha256(b'ONE').hexdigest(),'request_id':'b'*32}).encode())
    monkeypatch.setattr('urllib.request.urlopen',respond)
    activate_promo('ONE','a'*64,'b'*32)


@pytest.mark.parametrize('field,value',[('credits',2),('credits',True),('request_id','wrong'),('code_hash','wrong'),('status','invalid_code')])
def test_wrong_receipt_never_adds_credit(tmp_path,monkeypatch,field,value):
    receipt={'status':'activated','credits':1,'code_hash':hashlib.sha256(b'ONE').hexdigest(),'request_id':'irrelevant'}
    def respond(request,**kwargs):
        receipt['request_id']=json.loads(request.data)['request_id']
        receipt[field]=value
        return io.BytesIO(json.dumps(receipt).encode())
    monkeypatch.setattr('urllib.request.urlopen',respond)
    store=RestorationCredits(tmp_path/'credits.sqlite3', activate=activate_promo)
    with pytest.raises(RestorationCodeError,match='неверный ответ'):
        store.redeem('ONE')
    assert store.remaining == 1


@pytest.mark.parametrize('status',[403,404,422,503])
def test_http_errors_do_not_add_credit(tmp_path,monkeypatch,status):
    import urllib.error
    def fail(*a,**kw):
        raise urllib.error.HTTPError('https://sv-bz.ru/apprevive/redeem.php',status,'unavailable',{},None)
    monkeypatch.setattr('urllib.request.urlopen',fail)
    store=RestorationCredits(tmp_path/'credits.sqlite3')
    with pytest.raises(RestorationCodeError):store.redeem('ONE')
    assert store.remaining == 1


def test_insecure_api_url_is_rejected_before_sending_code(monkeypatch):
    monkeypatch.setenv('APPREVIVE_PROMO_API_URL','http://example.invalid/redeem')
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**kw:pytest.fail('must not send'))
    with pytest.raises(RestorationCodeError,match='HTTPS'):
        activate_promo('ONE','a'*64,'b'*32)


def test_default_ssl_context_gets_bundled_roots(monkeypatch):
    import ssl
    from apprevive_core.restoration_codes import promo_ssl_context
    monkeypatch.setattr(ssl,'create_default_context',lambda:ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    context=promo_ssl_context()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert context.cert_store_stats()['x509_ca'] > 0


def test_core_native_restore_is_gated_before_any_device_action(tmp_path,monkeypatch):
    from apprevive_core.service import AppReviveService
    from apprevive_core.models import OffloadedApp,RedownloadRequestState
    tools=SimpleNamespace(device_request_redownload=Mock(return_value=RedownloadRequestState.COMPLETED))
    core=AppReviveService(tools,cache=tmp_path/'cache',library=tmp_path/'ipas')
    monkeypatch.setattr(core,'_wait_for_native_redownload',lambda *a:None)
    monkeypatch.setattr(core,'_remember_app_best_effort',lambda **kw:None)
    store=RestorationCredits(tmp_path/'credits.sqlite3')
    core.restoration_access=RestorationAccess(store,lambda:False)
    app=OffloadedApp('com.example.app','Example','1')
    assert 'confirmed' in core.restore_offloaded('phone',app)
    with pytest.raises(RestorationCodeError):core.restore_offloaded('phone',app)
    assert tools.device_request_redownload.call_count == 1


def test_old_balance_and_used_codes_are_preserved_by_migration(tmp_path):
    import sqlite3
    path=tmp_path/'credits.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE balance (id INTEGER PRIMARY KEY, credits INTEGER NOT NULL)')
        db.execute('INSERT INTO balance VALUES (1,0)')
        db.execute('CREATE TABLE redeemed (digest TEXT PRIMARY KEY)')
        db.execute('INSERT INTO redeemed VALUES (?)',(hashlib.sha256(b'OLD').hexdigest(),))
    store=RestorationCredits(path,activate=lambda *a:pytest.fail('old used code must not be sent'))
    assert store.remaining == 0
    with pytest.raises(RestorationCodeError,match='уже использован'):
        store.redeem('OLD')


def test_local_commit_failure_can_recover_server_receipt(tmp_path):
    import sqlite3
    path=tmp_path/'credits.sqlite3'
    calls=[]
    lock=[]
    def claim(*args):
        calls.append(args)
        connection=sqlite3.connect(path,isolation_level=None)
        connection.execute('BEGIN IMMEDIATE')
        lock.append(connection)
    store=RestorationCredits(path,activate=claim)
    try:
        with pytest.raises(RestorationCodeError,match='Код активирован на сервере'):
            store.redeem('ONE')
    finally:
        for connection in lock:
            connection.rollback();connection.close()
    restored=RestorationCredits(path,activate=lambda *args:calls.append(args))
    assert restored.redeem('ONE') == 2
    assert calls[0] == calls[1]
