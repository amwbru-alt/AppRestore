"""Local restoration credits. The public promo file is a list, not a redemption API."""
from __future__ import annotations

from contextlib import closing
from functools import wraps
import codecs
import hashlib
import socket
import ssl
from pathlib import Path
import sqlite3
import threading
from typing import Callable, TypeVar
import urllib.error
import urllib.request

import certifi

PROMO_URL = "https://sv-bz.ru/uploads/promo.txt"
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
        return "HTTPS: не удалось проверить сертификат sv-bz.ru. Проверьте дату компьютера и обновите приложение."
    if isinstance(reason, ssl.SSLError):
        return "Не удалось установить защищённое HTTPS-соединение с sv-bz.ru."
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "Сервер кодов не ответил за 15 секунд. Повторите проверку."
    if isinstance(reason, socket.gaierror):
        return "Не удалось найти сервер sv-bz.ru. Проверьте DNS и подключение к интернету."
    return "Не удалось соединиться с sv-bz.ru. Проверьте подключение, VPN или прокси и повторите проверку."


def fetch_promo_codes() -> set[str]:
    request = urllib.request.Request(PROMO_URL, headers={"User-Agent": "AppRevive/0.4", "Cache-Control": "no-cache"})
    try:
        context = promo_ssl_context()
        with urllib.request.urlopen(request, timeout=15, context=context) as response:
            data = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            message = "Файл promo.txt не найден на сервере (HTTP 404)."
        elif exc.code in (401, 403):
            message = f"Сервер кодов отклонил запрос приложения (HTTP {exc.code})."
        else:
            message = f"Сервер кодов вернул HTTP {exc.code}. Повторите проверку позже."
        raise RestorationCodeError(message) from exc
    except urllib.error.URLError as exc:
        raise RestorationCodeError(_network_error(exc.reason)) from exc
    except OSError as exc:
        raise RestorationCodeError(_network_error(exc)) from exc
    if len(data) > 2 * 1024 * 1024:
        raise RestorationCodeError("Файл кодов слишком большой (более 2 МБ).")
    try:
        # Text editors may save a .txt as UTF-16. A BOM is required to select
        # it; never guess an arbitrary encoding or reinterpret binary data.
        encoding = "utf-16" if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig"
        text = data.decode(encoding)
    except UnicodeError as exc:
        raise RestorationCodeError("Не удалось прочитать файл кодов. Сохраните promo.txt в UTF-8.") from exc
    # Some hosting servers label plain .txt files as text/html. Inspect the
    # actual body instead of rejecting a valid code list based on that header.
    if text.lstrip().startswith("<") or "\x00" in text:
        raise RestorationCodeError("Сервер вернул страницу или неверный формат вместо текстового файла promo.txt.")
    return {line.strip() for line in text.splitlines() if line.strip()}


class RestorationCredits:
    """SQLite transactions serialize installs across windows/processes.

    One initial gift per local database. A code can be redeemed once in that
    database. Never claim global one-time use: the remote file cannot enforce it.
    """
    def __init__(self, path: Path, fetch: Callable[[], set[str]] = fetch_promo_codes) -> None:
        self.path = path
        self.fetch = fetch
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS balance (id INTEGER PRIMARY KEY CHECK(id=1), credits INTEGER NOT NULL CHECK(credits>=0))")
            db.execute("INSERT OR IGNORE INTO balance VALUES (1,1)")
            db.execute("CREATE TABLE IF NOT EXISTS redeemed (digest TEXT PRIMARY KEY)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=1, isolation_level=None)

    @property
    def remaining(self) -> int:
        with closing(self._connect()) as db:
            return int(db.execute("SELECT credits FROM balance WHERE id=1").fetchone()[0])

    def redeem(self, code: str) -> int:
        code = code.strip()
        if not code or len(code) > 256 or "\n" in code or "\r" in code:
            raise RestorationCodeError("Введите код одной строкой.")
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        with closing(self._connect()) as db:
            if db.execute("SELECT 1 FROM redeemed WHERE digest=?", (digest,)).fetchone():
                raise RestorationCodeError("Этот код уже использован на этом компьютере.")
        if code not in self.fetch():
            raise RestorationCodeError("Код не найден.")
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO redeemed VALUES (?)", (digest,))
                db.execute("UPDATE balance SET credits=credits+1 WHERE id=1")
                db.commit()
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise RestorationCodeError("Этот код уже использован на этом компьютере.") from exc
            except sqlite3.OperationalError as exc:
                db.rollback()
                raise RestorationCodeError("Дождитесь завершения текущего восстановления и повторите.") from exc
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
