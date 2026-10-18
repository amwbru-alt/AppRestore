"""Server balances by normalized Apple ID; local state is retry metadata only."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import uuid
import urllib.request
import urllib.error
from urllib.parse import urlsplit

from .api_config import api_base_url
from .restoration_codes import RestorationCodeError, promo_ssl_context


class CodeRequired(RestorationCodeError):
    pass


def account_id(email: str) -> str:
    email = email.strip().casefold()
    if '@' not in email or len(email) > 320:
        raise RestorationCodeError('Войдите в Apple ID перед восстановлением.')
    return hashlib.sha256(('apprevive-account-v1:' + email).encode()).hexdigest()


def api_call(method: str, body: dict, *, namespace="account") -> dict:
    if namespace not in ("account", "partner"):
        raise ValueError("Unknown API namespace")
    url = api_base_url() + "/v2/" + namespace + "/" + method
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'AppRevive/0.4',
    }, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=15, context=promo_ssl_context() if urlsplit(url).scheme == 'https' else None) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('large response')
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get('account_id') != body['account_id']:
            raise ValueError('wrong account')
        return result
    except urllib.error.HTTPError as exc:
        if exc.code == 402:
            raise CodeRequired('Для продолжения нужен код.') from exc
        messages = {409: 'Есть незавершённое восстановление. Повторите на прежнем компьютере или обратитесь в Telegram.',
                    422: 'Код не найден или уже использован другим аккаунтом.',
                    404: 'Обновите Node.js API на сервере: учёт Apple ID пока недоступен.',
                    429: 'Слишком много запросов. Подождите минуту.'}
        if namespace == "partner":
            messages.update({409: 'Пригласивший уже закреплён, покупка уже записана или указан собственный код.',
                             422: 'Партнёрский код не найден.', 404: 'Обновите API и импортируйте таблицы партнёрской программы.'})
        raise RestorationCodeError(messages.get(exc.code, 'Не удалось проверить серверный баланс. Повторите позже.')) from exc
    except (OSError, ValueError) as exc:
        raise RestorationCodeError('Не удалось проверить серверный баланс. Проверьте интернет и повторите.') from exc


class AccountCredits:
    def __init__(self, path: Path, identity, call=api_call):
        self.path, self.identity, self.call = path, identity, call
        self._lock = threading.RLock()
        self.current = ''
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.execute('CREATE TABLE IF NOT EXISTS server_operations (account TEXT PRIMARY KEY, request TEXT NOT NULL, outcome INTEGER)')
            db.commit()

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def select(self):
        self.current = account_id(self.identity())
        return self.current

    def invoke(self, method, account, **body):
        result = self.call(method, dict(account_id=account, **body))
        if result.get('account_id') != account:
            raise RestorationCodeError('Сервер вернул другой аккаунт.')
        return result

    @property
    def remaining(self):
        with self._lock:
            result = self.invoke('balance', self.select())
            if result.get('status') != 'ok' or type(result.get('credits')) is not int or result['credits'] < 0:
                raise RestorationCodeError('Неверный ответ сервера баланса.')
            return result['credits']

    def redeem(self, code):
        # The worker captured the verified account before opening the code dialog.
        account = self.current
        if not account:
            raise RestorationCodeError('Войдите в Apple ID.')
        code = code.strip()
        if not code or len(code.encode()) > 256 or '\n' in code or '\r' in code:
            raise RestorationCodeError('Введите код одной строкой.')
        result = self.invoke('redeem', account, code=code, request_id=uuid.uuid4().hex)
        if result.get('status') != 'activated' or result.get('code_hash') != hashlib.sha256(code.encode()).hexdigest() or type(result.get('credits')) is not int:
            raise RestorationCodeError('Неверный ответ сервера активации.')
        return result['credits']

    def pending(self, account):
        with closing(self.connect()) as db:
            return db.execute('SELECT request,outcome FROM server_operations WHERE account=?', (account,)).fetchone()

    def remember(self, account, request, outcome):
        with closing(self.connect()) as db:
            db.execute('INSERT OR REPLACE INTO server_operations VALUES (?,?,?)', (account, request, outcome))
            db.commit()

    def settle(self, account, request, success):
        result = self.invoke('finish', account, request_id=request, success=success)
        if result.get('status') != ('completed' if success else 'failed') or result.get('request_id') != request:
            raise RestorationCodeError('Не удалось подтвердить итог восстановления.')
        with closing(self.connect()) as db:
            db.execute('DELETE FROM server_operations WHERE account=? AND request=?', (account, request))
            db.commit()


class AccountAccess:
    def __init__(self, credits, prompt, changed=lambda: None):
        self.credits, self.prompt, self.changed = credits, prompt, changed
        self.local = threading.local()

    def run(self, action):
        if getattr(self.local, 'active', False):
            return action()
        with self.credits._lock:
            account = self.credits.select()
            prior = self.credits.pending(account)
            request = uuid.uuid4().hex
            if prior:
                request, outcome = prior
                if outcome is None:
                    # The previous process may have installed the app. Never retry
                    # installation or refund an ambiguous operation automatically.
                    raise RestorationCodeError('Предыдущее восстановление прервано. Обратитесь в Telegram для проверки результата.')
                if outcome != -1:
                    self.credits.settle(account, request, bool(outcome))
                    if outcome == 1:
                        raise RestorationCodeError('Предыдущее успешное восстановление подтверждено сервером. Повторная установка не запускалась.')
                    request = uuid.uuid4().hex
            self.credits.remember(account, request, -1)
            while True:
                try:
                    result = self.credits.invoke('reserve', account, request_id=request)
                    break
                except CodeRequired:
                    if not self.prompt():
                        raise RestorationCodeError('Восстановление отменено.')
            if result.get('status') != 'reserved' or result.get('request_id') != request:
                raise RestorationCodeError('Не удалось зарезервировать восстановление.')
            self.credits.remember(account, request, None)
            try:
                self.local.active = True
                value = action()
            except BaseException:
                self.credits.remember(account, request, 0)
                self.credits.settle(account, request, False)
                raise
            finally:
                self.local.active = False
            self.credits.remember(account, request, 1)
            self.credits.settle(account, request, True)
            self.changed()
            return value
