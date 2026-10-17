from concurrent.futures import ThreadPoolExecutor
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apprestore_core.restoration_codes import (
    RestorationAccess, RestorationCredits, RestorationCodeError, fetch_promo_codes,
)


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


def test_exact_code_adds_one_credit_once_persistently(tmp_path):
    path = tmp_path / 'credits.sqlite3'
    store = RestorationCredits(path, fetch=lambda: {'ABC-123', 'OTHER'})
    for code in ('ABC', 'abc-123', 'xABC-123x'):
        with pytest.raises(RestorationCodeError, match='Код не найден'):
            store.redeem(code)
    assert store.remaining == 1
    assert store.redeem('  ABC-123  ') == 2
    other = RestorationCredits(path, fetch=lambda: pytest.fail('used code must not need network'))
    with pytest.raises(RestorationCodeError, match='уже использован'):
        other.redeem('ABC-123')
    assert other.remaining == 2
    assert 'ABC-123' not in path.read_bytes().decode('latin1')


def test_code_prompt_resumes_same_action_and_nested_install_is_charged_once(tmp_path):
    store = RestorationCredits(tmp_path / 'credits.sqlite3', fetch=lambda: {'NEXT'})
    calls = []
    def prompt():
        calls.append('prompt')
        store.redeem('NEXT')
        return True
    gate = RestorationAccess(store, prompt)
    assert gate.run(lambda: gate.run(lambda: 42)) == 42
    assert store.remaining == 0
    assert gate.run(lambda: calls.append('installed')) is None
    assert calls == ['prompt', 'installed']
    assert store.remaining == 0


def test_network_failure_does_not_consume_code_or_change_credits(tmp_path):
    def unavailable():
        raise RestorationCodeError('Не удалось проверить код')
    store = RestorationCredits(tmp_path / 'credits.sqlite3', fetch=unavailable)
    with pytest.raises(RestorationCodeError, match='Не удалось'):
        store.redeem('NEXT')
    assert store.remaining == 1
    store.fetch = lambda: {'NEXT'}
    assert store.redeem('NEXT') == 2


def test_two_instances_cannot_redeem_same_code_twice(tmp_path):
    path = tmp_path / 'credits.sqlite3'
    stores = [RestorationCredits(path, fetch=lambda: {'ONE'}) for _ in range(2)]
    def redeem(store):
        try:
            store.redeem('ONE')
            return True
        except RestorationCodeError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(redeem, stores)) == [False, True]
    assert stores[0].remaining == 2


def test_concurrent_installs_cannot_spend_one_gift_twice(tmp_path):
    path = tmp_path / 'credits.sqlite3'
    stores = [RestorationCredits(path) for _ in range(2)]
    calls = []
    def run(store):
        try:
            RestorationAccess(store, lambda: False).run(lambda: calls.append('installed'))
            return True
        except RestorationCodeError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, stores)) == [False, True]
    assert calls == ['installed']
    assert stores[0].remaining == 0


def test_remote_text_bom_blank_lines_and_exact_lines(monkeypatch):
    def response(*args, **kwargs):
        stream = io.BytesIO(b'\xef\xbb\xbfABC-123\r\n\r\n OTHER \n')
        stream.headers = {'Content-Type': 'text/plain'}
        return stream
    monkeypatch.setattr('urllib.request.urlopen', response)
    assert fetch_promo_codes() == {'ABC-123', 'OTHER'}


@pytest.mark.parametrize('content,content_type', [(b'<html>Bad gateway</html>', 'text/html'), (b'<html>error</html>', 'text/plain'), (b'\xff', 'text/plain')])
def test_bad_server_response_is_not_a_missing_code(monkeypatch, content, content_type):
    def response(*args, **kwargs):
        stream = io.BytesIO(content)
        stream.headers = {'Content-Type': content_type}
        return stream
    monkeypatch.setattr('urllib.request.urlopen', response)
    with pytest.raises(RestorationCodeError, match='файл|файла'):
        fetch_promo_codes()


def test_core_native_restore_is_gated_before_any_device_action(tmp_path, monkeypatch):
    from apprestore_core.service import AppRestoreService
    from apprestore_core.models import OffloadedApp, RedownloadRequestState
    tools = SimpleNamespace(device_request_redownload=Mock(return_value=RedownloadRequestState.COMPLETED))
    core = AppRestoreService(tools, cache=tmp_path / 'cache', library=tmp_path / 'ipas')
    monkeypatch.setattr(core, '_wait_for_native_redownload', lambda *args: None)
    monkeypatch.setattr(core, '_remember_app_best_effort', lambda **kwargs: None)
    credits = RestorationCredits(tmp_path / 'credits.sqlite3')
    core.restoration_access = RestorationAccess(credits, lambda: False)
    app = OffloadedApp('com.example.app', 'Example', '1')
    assert 'confirmed' in core.restore_offloaded('phone', app)
    with pytest.raises(RestorationCodeError):
        core.restore_offloaded('phone', app)
    assert tools.device_request_redownload.call_count == 1


def test_plain_text_is_accepted_even_if_hosting_uses_html_content_type(monkeypatch):
    def response(request, **kwargs):
        assert request.full_url == 'https://sv-bz.ru/uploads/promo.txt'
        import ssl
        assert kwargs['context'].check_hostname
        assert kwargs['context'].verify_mode == ssl.CERT_REQUIRED
        assert kwargs['context'].cert_store_stats()['x509_ca'] > 0
        stream = io.BytesIO(b'test1\r\nSECOND\n')
        stream.headers = {'Content-Type': 'text/html'}
        return stream
    monkeypatch.setattr('urllib.request.urlopen', response)
    assert fetch_promo_codes() == {'test1', 'SECOND'}


def test_utf16_bom_saved_by_text_editor_is_supported(monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: io.BytesIO('test1\r\nSECOND'.encode('utf-16')))
    assert fetch_promo_codes() == {'test1', 'SECOND'}


@pytest.mark.parametrize('status', [403, 404, 502])
def test_http_error_is_visible_and_never_reported_as_missing_code(monkeypatch, status):
    import urllib.error
    def fail(*a, **kw):
        raise urllib.error.HTTPError('https://sv-bz.ru/uploads/promo.txt', status, 'unavailable', {}, None)
    monkeypatch.setattr('urllib.request.urlopen', fail)
    with pytest.raises(RestorationCodeError, match='HTTP ' + str(status)) as error:
        fetch_promo_codes()
    assert 'Код не найден' not in str(error.value)


@pytest.mark.parametrize('kind,expected', [('certificate', 'сертификат'), ('timeout', '15 секунд'), ('dns', 'DNS')])
def test_transport_failures_explain_the_actual_stage(monkeypatch, kind, expected):
    import socket
    import ssl
    import urllib.error
    reasons = {'certificate': ssl.SSLCertVerificationError(1, 'certificate verify failed'), 'timeout': TimeoutError(), 'dns': socket.gaierror(-2, 'name not known')}
    def fail(*a, **kw):
        raise urllib.error.URLError(reasons[kind])
    monkeypatch.setattr('urllib.request.urlopen', fail)
    with pytest.raises(RestorationCodeError, match=expected):
        fetch_promo_codes()


def test_missing_default_ca_file_is_fixed_by_bundled_roots(monkeypatch):
    import ssl
    from apprestore_core.restoration_codes import promo_ssl_context
    def empty_default_context():
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(ssl, 'create_default_context', empty_default_context)
    context = promo_ssl_context()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert context.cert_store_stats()['x509_ca'] > 0


def test_real_html_is_not_accepted_as_a_code_list(monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: io.BytesIO(b'<!doctype html><html>test1</html>'))
    with pytest.raises(RestorationCodeError, match='вместо текстового файла'):
        fetch_promo_codes()
