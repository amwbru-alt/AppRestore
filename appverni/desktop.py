"""Application-side service ledger; no HTTP server or separate worker needed."""
from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import time

from apprestore_core.ipatool_api import IpatoolError
from .store import Problem, Store, password_matches
from .worker import Executor


def database_path():
    configured = os.environ.get('APPVERNI_DATABASE')
    if configured:
        return Path(configured).expanduser().resolve()
    # Reuse the database from an earlier local web launch if present.
    existing = Path(__file__).resolve().parent.parent / 'data' / 'appverni.sqlite3'
    if existing.is_file():
        return existing
    from apprestore_core.paths import cache_dir
    return cache_dir() / 'appverni.sqlite3'


class DesktopLedger:
    def __init__(self, database):
        self.store = Store(database)
        self.images = Path(database).resolve().parent / 'images'
        self.images.mkdir(mode=0o700, parents=True, exist_ok=True)

    def user(self, uid):
        user = self.store.one('SELECT id,email,admin FROM users WHERE id=?', (uid,))
        if not user:
            raise Problem('Войдите в аккаунт АппВерни.', 401)
        return user

    def admin(self, uid):
        user = self.user(uid)
        if not user['admin']:
            raise Problem('Требуются права администратора.', 403)
        return user

    def authenticate(self, email, password):
        self.store.throttle('desktop-login:' + email.strip().casefold())
        if not 1 <= len(password) <= 128:
            raise Problem('Неверный email или пароль.')
        row = self.store.one('SELECT * FROM users WHERE email=?', (email.strip().casefold(),))
        # Use a fixed-cost password check even for an unknown email.
        if row:
            valid = password_matches(password, row['password'])
        else:
            password_matches(password, '00' * 16 + ':' + '00' * 64)
            valid = False
        if not valid:
            raise Problem('Неверный email или пароль.')
        return self.user(row['id'])

    def register(self, email, password, *, owner=False):
        self.store.throttle('desktop-register:' + email.strip().casefold())
        uid = self.store.register(email, password, admin=owner, require_empty=owner)
        return self.user(uid)

    def account(self, uid, client):
        self.user(uid)
        try:
            email = client.account_info().email.strip().casefold()
        except IpatoolError as exc:
            raise Problem(exc.message_ru) from None
        if '@' not in email:
            raise Problem('Apple не подтвердила email аккаунта. Войдите в Apple ID в приложении.')
        return self.store.account(uid, email), email

    @staticmethod
    def assert_account(client, expected):
        try:
            current = client.account_info().email.strip().casefold()
        except IpatoolError as exc:
            raise Problem(exc.message_ru) from None
        if current != expected:
            raise Problem('Apple ID изменился. Повторите проверку для текущего аккаунта.', 409)

    def verify(self, uid, client, *, force=False):
        aid, email = self.account(uid, client)
        account = self.store.one('SELECT * FROM accounts WHERE id=?', (aid,))
        if account['verified_at'] is not None and not force:
            return aid
        try:
            ids, last, expected = set(), False, 0
            for page in client.iter_purchases(platform='iphone'):
                ids.update(str(p.track_id) for p in page.items)
                expected = max(expected, page.total or 0)
                last = page.is_last
            if not last or len(ids) < expected:
                raise Problem('История Apple получена не полностью. Повторите проверку.')
            self.assert_account(client, email)
            now = int(time.time())
            with self.store.transaction() as db:
                db.execute('DELETE FROM purchases WHERE account_id=?', (aid,))
                db.executemany('INSERT INTO purchases VALUES(?,?)', ((aid, app_id) for app_id in ids))
                db.execute("UPDATE accounts SET verified_at=?,check_state='verified' WHERE id=?", (now, aid))
                db.execute("UPDATE checks SET state='succeeded',detail='' WHERE account_id=? AND state IN ('queued','running')", (aid,))
                self.store.audit(db, uid, 'desktop.history.verified', aid)
            return aid
        except Exception as exc:
            with self.store.transaction() as db:
                db.execute("UPDATE accounts SET check_state='failed' WHERE id=?", (aid,))
                db.execute("UPDATE checks SET state='failed' WHERE account_id=? AND state IN ('queued','running')", (aid,))
            if isinstance(exc, Problem):
                raise
            if isinstance(exc, IpatoolError):
                raise Problem(exc.message_ru) from None
            raise Problem('Не удалось проверить историю Apple. Проверьте вход и подключение к интернету.') from None

    def catalog(self, uid, aid=None):
        self.user(uid)
        if aid:
            return self.store.catalog(uid, aid)[1]
        return self.store.rows('SELECT *,0 AS owned FROM apps WHERE active=1 ORDER BY name')

    def gift_available(self, uid):
        return not self.store.one("SELECT 1 FROM orders WHERE user_id=? AND price=0 AND state IN ('queued','running','succeeded','uncertain')", (uid,))

    def save_app(self, uid, *, app_id=None, name, store_id, description='', image='', active=True):
        self.admin(uid)
        name, store_id = name.strip(), store_id.strip()
        if not 1 <= len(name) <= 100 or not re.fullmatch(r'[1-9][0-9]{7,11}', store_id) or len(description) > 1000:
            raise Problem('Укажите название (до 100 символов), App Store ID (8–12 цифр) и описание (до 1000 символов).')
        if image and not re.fullmatch(r'/media/[a-f0-9]{40}\.(png|jpg)', image):
            raise Problem('Выберите фото приложения через кнопку «Фото».')
        with self.store.transaction() as db:
            if db.execute('SELECT 1 FROM apps WHERE store_id=? AND id!=?', (store_id, app_id or 0)).fetchone():
                raise Problem('Этот App Store ID уже добавлен.')
            if app_id:
                old = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
                if not old:
                    raise Problem('Карточка не найдена.')
                if old['store_id'] != store_id:
                    raise Problem('Для другого App Store ID создайте новую карточку.')
                db.execute('UPDATE apps SET name=?,description=?,image=?,active=? WHERE id=?', (name, description, image, int(active), app_id))
            else:
                app_id = db.execute('INSERT INTO apps(store_id,name,description,image,active) VALUES(?,?,?,?,?)', (store_id, name, description, image, int(active))).lastrowid
            self.store.audit(db, uid, 'desktop.app.save', app_id)
        return app_id

    def install(self, uid, aid, app_id, client, core, udid):
        account = self.store.one('SELECT * FROM accounts WHERE id=? AND user_id=?', (aid, uid))
        if not account:
            raise Problem('Сначала проверьте текущий Apple ID.')
        if not udid:
            raise Problem('Подключите и выберите iPhone в приложении.')
        self.assert_account(client, account['apple_id'])
        oid = self.store.order(uid, aid, app_id)
        with self.store.transaction() as db:
            order = db.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (oid, uid)).fetchone()
            if order['state'] != 'queued':
                return dict(order)
            db.execute("UPDATE orders SET state='running',updated=? WHERE id=?", (int(time.time()), oid))
            db.execute('INSERT OR IGNORE INTO desktop_inflight VALUES(?)', (oid,))
        job = dict(kind='install', id=oid, store_id=order['store_id'], apple_id=account['apple_id'])
        # Executor uses the original verified-IPA/device-confirmation pipeline.
        result = Executor(client, core, account['apple_id'], udid).execute(job)
        detail = {'succeeded':'Установка подтверждена на iPhone.', 'failed':'Установка не началась. Бесплатная попытка сохранена.', 'uncertain':'Результат установки не подтверждён. Проверьте iPhone.'}[result['state']]
        with self.store.transaction() as db:
            db.execute('UPDATE orders SET state=?,detail=?,updated=? WHERE id=? AND user_id=?', (result['state'], detail, int(time.time()), oid, uid))
            db.execute('DELETE FROM desktop_inflight WHERE order_id=?', (oid,))
            self.store.audit(db, uid, 'desktop.install.' + result['state'], oid)
        return dict(self.store.one('SELECT * FROM orders WHERE id=?', (oid,)))

    def recover_interrupted(self):
        # Called only after acquiring the desktop application's database lock.
        with self.store.transaction() as db:
            db.execute("UPDATE orders SET state='uncertain',detail='Приложение закрылось во время установки. Требуется проверка iPhone.',updated=? WHERE state='running' AND id IN (SELECT order_id FROM desktop_inflight)", (int(time.time()),))
            db.execute('DELETE FROM desktop_inflight')

    def resolve_order(self, uid, order_id, state, reason):
        self.admin(uid)
        if state not in ('succeeded', 'failed') or not 10 <= len(reason.strip()) <= 500:
            raise Problem('Укажите результат и основание проверки (10–500 символов).')
        with self.store.transaction() as db:
            result = db.execute("UPDATE orders SET state=?,detail=?,updated=? WHERE id=? AND state='uncertain'", (state, reason.strip(), int(time.time()), order_id))
            if result.rowcount != 1:
                raise Problem('Заказ уже завершён или не требует проверки.')
            self.store.audit(db, uid, 'desktop.order.resolve.' + state, order_id)
