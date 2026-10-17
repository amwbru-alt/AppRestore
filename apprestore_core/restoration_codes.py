"""Local restoration credits. The public promo file is a list, not a redemption API."""
from __future__ import annotations

from contextlib import closing
from functools import wraps
import hashlib
from pathlib import Path
import sqlite3
import threading
from typing import Callable, TypeVar
import urllib.error
import urllib.request

PROMO_URL = "https://sv-bz.ru/uploads/promo.txt"
TELEGRAM_URL = "https://t.me/llifegoldll"
_T = TypeVar("_T")


class RestorationCodeError(RuntimeError):
    pass


def fetch_promo_codes() -> set[str]:
    request = urllib.request.Request(PROMO_URL, headers={"User-Agent": "AppRevive/0.4", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            content_type = response.headers.get("Content-Type", "").lower()
        if len(data) > 2 * 1024 * 1024 or "text/html" in content_type:
            raise ValueError("unexpected promo response")
        text = data.decode("utf-8-sig")
        if text.lstrip().startswith("<"):
            raise ValueError("unexpected HTML response")
    except (OSError, urllib.error.URLError, UnicodeError, ValueError) as exc:
        raise RestorationCodeError("Не удалось проверить код. Проверьте интернет или повторите позже.") from exc
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
