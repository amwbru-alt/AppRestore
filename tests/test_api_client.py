import io
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from apprevive_core.api_config import api_base_url
from apprevive_core.restoration_codes import RestorationCredits, RestorationCodeError, activate_promo
from apprevive_core.app_catalog import read_catalog


def test_default_credits_use_api():
    assert RestorationCredits.__init__.__defaults__[0] is activate_promo


def test_config_contains_only_public_url(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('APPREVIVE_API_URL', raising=False)
    folder = tmp_path / '.apprevive'; folder.mkdir()
    (folder / 'mysql.json').write_text('{"password":"must-never-read"}')
    (folder / 'api.json').write_text('{"base_url":"http://192.0.2.1:3000"}', encoding='utf-8-sig')
    assert api_base_url() == 'http://192.0.2.1:3000'
    monkeypatch.setenv('APPREVIVE_API_URL', 'https://example.org/api/')
    assert api_base_url() == 'https://example.org/api'


@pytest.mark.parametrize('url', ['', 'file:///etc/passwd', 'http://user:secret@192.0.2.1', 'http://192.0.2.1:wrong', 'http://192.0.2.1?secret=1'])
def test_bad_endpoint_never_sends_request(monkeypatch, url):
    monkeypatch.setenv('APPREVIVE_API_URL', url)
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: pytest.fail('must not send'))
    with pytest.raises(RestorationCodeError):
        activate_promo('ONE', 'a' * 64, 'b' * 32)


def test_catalog_limits_response_and_requires_envelope(monkeypatch):
    monkeypatch.setenv('APPREVIVE_API_URL', 'http://192.0.2.1:3000')
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: io.BytesIO(b'{"password":"secret"}'))
    with pytest.raises(ValueError): read_catalog()


def test_python_client_redeems_through_real_node_http(tmp_path, monkeypatch):
    node = shutil.which('node')
    if not node: pytest.skip('Node.js not installed')
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen([node, str(root / 'server/node/test/fixtures/api-process.mjs')], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        endpoint = process.stdout.readline().strip()
        assert endpoint.startswith('http://127.0.0.1:')
        monkeypatch.setenv('APPREVIVE_API_URL', endpoint)
        store = RestorationCredits(tmp_path / 'credits.sqlite3')
        assert store.redeem('ONE') == 2
        with pytest.raises(RestorationCodeError): store.redeem('ONE')
        other = RestorationCredits(tmp_path / 'other.sqlite3')
        with pytest.raises(RestorationCodeError, match='Код не найден'): other.redeem('ONE')
        assert other.remaining == 1
        assert read_catalog()[0]['trackId'] == '686449807'
    finally:
        process.terminate()
        try: process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.communicate()


def test_client_packages_have_no_mysql_access():
    root = Path(__file__).resolve().parents[1]
    assert not (root / 'apprevive_core/mysql_promo.py').exists()
    for folder in ['apprevive_core', 'apprevive_gui']:
        for path in (root / folder).rglob('*.py'):
            text = path.read_text()
            assert 'import pymysql' not in text
            assert 'shuloquaticu.beget.app' not in text
    assert 'PyMySQL' not in (root / 'pyproject.toml').read_text()
