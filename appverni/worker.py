"""Trusted worker. One isolated OS user/keychain and one device per Apple ID."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from apprestore_core.ipatool_api import IpatoolClient
from apprestore_core.paths import IPATOOL_MISSING_TEXT, resolve_tool
from apprestore_core.service import AppRestoreService
from apprestore_core.tools import AppRestoreTools, ToolUnavailable

from .store import digest


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Исполнитель не следует перенаправлениям. Укажите конечный HTTPS-адрес сервиса.')


class Transport:
    def __init__(self, url, token):
        parts = urlsplit(url)
        if parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('Нужен HTTPS; HTTP разрешён только для localhost.')
        if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
            raise ValueError('Укажите корневой URL сервиса без учётных данных.')
        self.url, self.token = url.rstrip('/'), token
        self.opener = urllib.request.build_opener(NoRedirect)

    def post(self, path, data):
        request = urllib.request.Request(self.url + path, data=json.dumps(data).encode(),
                    headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}, method='POST')
        with self.opener.open(request, timeout=30) as response:
            return json.load(response)


class WorkerTools(AppRestoreTools):
    def __init__(self, client, passphrase, apple_id):
        super().__init__()
        self.client, self.passphrase, self.apple_id = client, passphrase, apple_id.casefold()

    def assert_identity(self):
        if self.client.account_info().email.strip().casefold() != self.apple_id:
            raise ToolUnavailable('В связке ключей открыт другой Apple ID. Задача остановлена.')

    def ipatool_authenticated(self):
        self.assert_identity()
        return True

    def download_ipa(self, output, *, store_id=None, bundle_id=None, purchase=False):
        if purchase or not store_id or not re.fullmatch(r'[1-9][0-9]{7,11}', store_id):
            raise ToolUnavailable('Исполнитель разрешает только повторную загрузку по App Store ID.')
        self.assert_identity()
        command = [self.client.binary, '--keychain-passphrase-stdin', '--non-interactive',
                   '--format', 'json', 'download', '--app-id', store_id,
                   '--platform', 'iphone', '--output', str(output)]
        # The secret only reaches stdin; output never reaches logs/web clients.
        env = dict(os.environ)
        env.pop('IPATOOL_KEYCHAIN_PASSPHRASE', None)
        env.update(self._ipatool_env())
        result = subprocess.run(command, input=self.passphrase + '\n', text=True,
                                capture_output=True, timeout=1800, env=env)
        if result.returncode:
            raise ToolUnavailable('Apple не подтвердила загрузку приложения.')
        self.assert_identity()
        return True


class Executor:
    def __init__(self, client, service, apple_id, udid):
        self.client, self.service = client, service
        self.apple_id, self.udid = apple_id.strip().casefold(), udid

    def identity(self, job):
        if str(job.get('apple_id', '')).strip().casefold() != self.apple_id:
            raise ValueError('Задача предназначена для другого Apple ID.')
        if self.client.account_info().email.strip().casefold() != self.apple_id:
            raise ValueError('Открыта сессия другого Apple ID.')

    def execute(self, job):
        result = {'kind': job['kind'], 'id': job['id'], 'state': 'failed'}
        started = False
        def on_install():
            nonlocal started
            started = True
        try:
            self.identity(job)
            if job['kind'] == 'check':
                ids, last, expected = set(), False, 0
                # No cancelled/partial list is ever accepted as a snapshot.
                for page in self.client.iter_purchases(platform='iphone'):
                    ids.update(str(p.track_id) for p in page.items)
                    last = page.is_last
                    expected = max(expected, page.total or 0)
                if not last or len(ids) < expected:
                    raise ValueError('История покупок получена не полностью.')
                self.identity(job)
                result.update(state='succeeded', complete=True, store_ids=sorted(ids))
            elif job['kind'] == 'install':
                store_id = str(job.get('store_id', ''))
                if not re.fullmatch(r'[1-9][0-9]{7,11}', store_id):
                    raise ValueError('Неверный App Store ID.')
                # Confirm the intended device exists before downloading an IPA.
                if self.udid not in {device.udid for device in self.service.devices()}:
                    raise ValueError('Назначенный iPhone не подключён.')
                path = self.service.download_by_store_id(store_id, acquire_license=False)
                self.identity(job)
                self.service.on_device_install = on_install
                self.service.install(self.udid, path)
                result['state'] = 'succeeded'
            else:
                raise ValueError('Неизвестная задача.')
        except Exception:
            result['state'] = 'uncertain' if started else 'failed'
        finally:
            self.service.on_device_install = None
        return result


def run(url, token_file, apple_id, udid, state_file, *, once=False, passphrase=''):
    binary = resolve_tool('ipatool')
    if not binary:
        raise RuntimeError(IPATOOL_MISSING_TEXT)
    token = Path(token_file).read_text().strip()
    transport = Transport(url, token)
    client = IpatoolClient(binary, keychain_passphrase=passphrase)
    if not client.capabilities().passphrase_stdin:
        raise RuntimeError('Нужен ipatool с патчем безопасной передачи пароля (0003). См. docs/RUN-FROM-SOURCE.md.')
    tools = WorkerTools(client, passphrase, apple_id)
    tools.assert_identity()
    executor = Executor(client, AppRestoreService(tools=tools), apple_id, udid)
    spool = Path(state_file).resolve()
    spool.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    while True:
        try:
            if spool.exists():
                saved = json.loads(spool.read_text())
                if saved['worker'] != digest(token):
                    raise RuntimeError('Незавершённый результат относится к другому исполнителю.')
                try:
                    transport.post('/worker/complete', saved['result'])
                except urllib.error.HTTPError as exc:
                    if exc.code != 409:
                        raise
                    # Server already persisted the result; do not run it twice.
                spool.unlink()
            job = transport.post('/worker/claim', {})['job']
            if job:
                # Persist an uncertain install result BEFORE touching a device.
                # After a process crash, recovery reports it, never retries it.
                fallback = {'kind': job['kind'], 'id': job['id'], 'state': 'uncertain' if job['kind'] == 'install' else 'failed'}
                write_result(spool, token, fallback)
                result = executor.execute(job)
                write_result(spool, token, result)
                transport.post('/worker/complete', result)
                spool.unlink()
            if once:
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            print('Сервис недоступен. Результат сохранён; повторим отправку.')
            if once:
                raise RuntimeError('Не удалось связаться с сервисом. Повторите запуск с тем же state-файлом.') from None
        time.sleep(3)


def write_result(path, token, result):
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump({'worker': digest(token), 'result': result}, out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)
