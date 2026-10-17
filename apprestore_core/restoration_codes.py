"""Local credits backed by atomic, single-use server activations."""
from __future__ import annotations

from contextlib import closing
from functools import wraps
import hashlib
import json
import os
import secrets
import uuid
import socket
import ssl
from pathlib import Path
import sqlite3
import threading
from typing import Callable, TypeVar
import urllib.error
import urllib.request
import urllib.parse

import certifi
from .mysql_promo import activate_mysql_promo

PROMO_API_URL = "https://sv-bz.ru/apprevive/redeem.php"
TELEGRAM_URL = "https://t.me/llifegoldll"
_T = TypeVar("_T")


class RestorationCodeError(RuntimeError):
    pass


def promo_ssl_context() -> ssl.SSLContext:
    # Keep platform/custom roots, then add the bundled Mozilla roots. Python
    # installed from python.org may not have a usable default CA file on Mac.
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def _network_error(reason: object) -> str:
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "HTTPS: не удалось проверить сертификат сервера активации. Проверьте дату компьютера и обновите приложение."
    if isinstance(reason, ssl.SSLError):
        return "Не удалось установить защищённое HTTPS-соединение с сервером активации."
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "Сервер кодов не ответил за 15 секунд. Повторите проверку."
    if isinstance(reason, socket.gaierror):
        return "Не удалось найти сервер активации. Проверьте DNS и подключение к интернету."
    return "Не удалось соединиться с сервером активации. Проверьте подключение, VPN или прокси и повторите проверку."


def activate_promo(code: str, installation_token: str, request_id: str) -> None:
    url = os.environ.get("APPREVIVE_PROMO_API_URL", PROMO_API_URL)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RestorationCodeError("Для сервера активации нужен HTTPS-адрес API без логина и пароля.")
    body = json.dumps({"code": code, "installation_token": installation_token, "request_id": request_id}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "User-Agent": "AppRevive/0.4", "Content-Type": "application/json", "Accept": "application/json", "Cache-Control": "no-store",
    })
    try:
        with urllib.request.urlopen(request, timeout=15, context=promo_ssl_context()) as response:
            data = response.read(65537)
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            message = "Код не найден или уже использован."
        elif exc.code == 404:
            message = "API активации ещё не размещён на сервере (HTTP 404)."
        elif exc.code == 409:
            message = "Не удалось подтвердить запрос активации. Обратитесь за помощью в Telegram."
        else:
            message = f"Сервер активации вернул HTTP {exc.code}. Повторите проверку позже."
        raise RestorationCodeError(message) from exc
    except urllib.error.URLError as exc:
        raise RestorationCodeError(_network_error(exc.reason)) from exc
    except OSError as exc:
        raise RestorationCodeError(_network_error(exc)) from exc
    try:
        if len(data) > 65536:
            raise ValueError("response too large")
        receipt = json.loads(data.decode("utf-8"))
        if not isinstance(receipt, dict) or receipt.get("status") != "activated" or type(receipt.get("credits")) is not int or receipt["credits"] != 1:
            raise ValueError("not an activation receipt")
        if receipt.get("request_id") != request_id or receipt.get("code_hash") != hashlib.sha256(code.encode("utf-8")).hexdigest():
            raise ValueError("receipt does not match this activation")
    except (UnicodeError, ValueError, KeyError) as exc:
        raise RestorationCodeError("Сервер активации вернул неверный ответ. Повторите запрос; тот же код не будет списан повторно.") from exc


class RestorationCredits:
    """One initial local gift, persistent server receipts and safe retry IDs."""
    def __init__(self, path: Path, activate: Callable[[str, str, str], None] = activate_mysql_promo) -> None:
        self.path = path
        self.activate = activate
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        with closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS balance (id INTEGER PRIMARY KEY CHECK(id=1), credits INTEGER NOT NULL CHECK(credits>=0))")
            db.execute("INSERT OR IGNORE INTO balance VALUES (1,1)")
            db.execute("CREATE TABLE IF NOT EXISTS redeemed (digest TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE IF NOT EXISTS promo_identity (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO promo_identity VALUES (1,?)", (secrets.token_hex(32),))
            db.execute("CREATE TABLE IF NOT EXISTS promo_pending (digest TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=1, isolation_level=None)

    @property
    def remaining(self) -> int:
        with closing(self._connect()) as db:
            return int(db.execute("SELECT credits FROM balance WHERE id=1").fetchone()[0])

    def redeem(self, code: str) -> int:
        code = code.strip()
        if not code or len(code.encode("utf-8")) > 256 or "\n" in code or "\r" in code:
            raise RestorationCodeError("Введите код одной строкой (не более 256 байт).")
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        try:
            with closing(self._connect()) as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM redeemed WHERE digest=?", (digest,)).fetchone():
                    db.rollback()
                    raise RestorationCodeError("Этот код уже использован на этом компьютере.")
                db.execute("INSERT OR IGNORE INTO promo_pending VALUES (?,?)", (digest, uuid.uuid4().hex))
                request_id = db.execute("SELECT request_id FROM promo_pending WHERE digest=?", (digest,)).fetchone()[0]
                token = db.execute("SELECT token FROM promo_identity WHERE id=1").fetchone()[0]
                db.commit()
        except sqlite3.OperationalError as exc:
            raise RestorationCodeError("Дождитесь завершения текущего восстановления и повторите.") from exc
        # No local SQL lock during network I/O. Pending ID and token survive
        # a timeout/crash, so a retry recovers the already committed receipt.
        self.activate(code, token, request_id)
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                inserted = db.execute("INSERT OR IGNORE INTO redeemed VALUES (?)", (digest,)).rowcount
                if inserted:
                    db.execute("UPDATE balance SET credits=credits+1 WHERE id=1")
                db.execute("DELETE FROM promo_pending WHERE digest=?", (digest,))
                db.commit()
            except sqlite3.OperationalError as exc:
                db.rollback()
                raise RestorationCodeError("Код активирован на сервере. Повторите запрос для начисления восстановления; повторного списания не будет.") from exc
        return self.remaining


class RestorationAccess:
    def __init__(self, credits: RestorationCredits, prompt: Callable[[], bool], changed: Callable[[], None] = lambda: None) -> None:
        self.credits = credits
        self.prompt = prompt
        self.changed = changed
        self._local = threading.local()

    def run(self, action: Callable[[], _T]) -> _T:
        # restore_* may call install(): nested operations consume only one credit.
        if getattr(self._local, "active", False):
            return action()
        while True:
            with closing(self.credits._connect()) as db:
                try:
                    db.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError as exc:
                    raise RestorationCodeError("Дождитесь завершения текущего восстановления и повторите.") from exc
                if db.execute("SELECT credits FROM balance WHERE id=1").fetchone()[0] > 0:
                    try:
                        self._local.active = True
                        result = action()
                        db.execute("UPDATE balance SET credits=credits-1 WHERE id=1")
                        db.commit()
                    except BaseException:
                        db.rollback()
                        raise
                    finally:
                        self._local.active = False
                    self.changed()
                    return result
                db.rollback()
            if not self.prompt():
                raise RestorationCodeError("Восстановление отменено. Для продолжения нужен код.")


def metered_restoration(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        access = getattr(self, "restoration_access", None)
        action = lambda: method(self, *args, **kwargs)
        return access.run(action) if access is not None else action()
    return wrapped
