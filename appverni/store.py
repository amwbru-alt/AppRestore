from __future__ import annotations

from contextlib import closing, contextmanager
import hashlib
import secrets
import sqlite3
import time
from pathlib import Path

from . import PRICE_KOPEKS

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL,
 admin INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
 token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), csrf TEXT NOT NULL,
 expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS apps (
 id INTEGER PRIMARY KEY, store_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 image TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
 active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 apple_id TEXT NOT NULL, verified_at INTEGER, check_state TEXT NOT NULL DEFAULT 'pending',
 UNIQUE(user_id,apple_id));
CREATE TABLE IF NOT EXISTS purchases (
 account_id INTEGER NOT NULL REFERENCES accounts(id), store_id TEXT NOT NULL,
 PRIMARY KEY(account_id,store_id));
CREATE TABLE IF NOT EXISTS workers (
 token TEXT PRIMARY KEY, account_id INTEGER NOT NULL UNIQUE REFERENCES accounts(id),
 seen INTEGER, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS checks (
 id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
 state TEXT NOT NULL DEFAULT 'queued', created INTEGER NOT NULL, claimed INTEGER,
 detail TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS one_check ON checks(account_id)
 WHERE state IN ('queued','running');
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 account_id INTEGER NOT NULL REFERENCES accounts(id), app_id INTEGER NOT NULL REFERENCES apps(id),
 store_id TEXT NOT NULL, app_name TEXT NOT NULL, price INTEGER NOT NULL,
 state TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL,
 detail TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS one_free_installation ON orders(user_id)
 WHERE price=0 AND state IN ('queued','running','succeeded','uncertain');
CREATE UNIQUE INDEX IF NOT EXISTS one_active_installation ON orders(account_id,app_id)
 WHERE state IN ('awaiting_payment','queued','running','uncertain');
CREATE TABLE IF NOT EXISTS desktop_inflight (
 order_id TEXT PRIMARY KEY REFERENCES orders(id));
CREATE TABLE IF NOT EXISTS auth_attempts (
 key TEXT PRIMARY KEY, count INTEGER NOT NULL, started INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, actor INTEGER REFERENCES users(id), action TEXT NOT NULL,
 target TEXT NOT NULL, created INTEGER NOT NULL);
PRAGMA user_version=1;
'''


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ':' + hashed.hex()


def password_matches(password, stored):
    salt, expected = stored.split(':')
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return secrets.compare_digest(actual.hex(), expected)


class Store:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript(SCHEMA)
        Path(self.path).chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, query, args=()):
        with closing(self.connect()) as db:
            return db.execute(query, args).fetchall()

    def one(self, query, args=()):
        rows = self.rows(query, args)
        return rows[0] if rows else None

    @staticmethod
    def audit(db, actor, action, target):
        db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',
                   (actor, action, str(target), int(time.time())))

    def register(self, email, password, *, admin=False, require_empty=False):
        email = email.strip().casefold()
        if not (3 <= len(email) <= 254 and '@' in email and '.' in email.rsplit('@', 1)[1]) or any(c.isspace() for c in email):
            raise Problem('Укажите корректный email.')
        if not 12 <= len(password) <= 128:
            raise Problem('Пароль должен содержать от 12 до 128 символов.')
        hashed = hash_password(password)
        with self.transaction() as db:
            if require_empty and db.execute('SELECT 1 FROM users').fetchone():
                raise Problem('Первичная настройка уже выполнена. Войдите в существующий аккаунт.', 409)
            try:
                user_id = db.execute('INSERT INTO users(email,password,admin,created) VALUES(?,?,?,?)',
                                     (email, hashed, int(admin), int(time.time()))).lastrowid
            except sqlite3.IntegrityError:
                raise Problem('Регистрация недоступна для этого email. Попробуйте войти.') from None
            self.audit(db, user_id, 'register', user_id)
            return user_id

    def throttle(self, key, limit=10):
        now = int(time.time())
        key = digest(key)
        with self.transaction() as db:
            db.execute('DELETE FROM auth_attempts WHERE started<?', (now - 900,))
            row = db.execute('SELECT * FROM auth_attempts WHERE key=?', (key,)).fetchone()
            if row and row['count'] >= limit:
                raise Problem('Слишком много попыток. Повторите через 15 минут.', 429)
            db.execute('INSERT INTO auth_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now))

    def session(self, token=None, user_id=None):
        now = int(time.time())
        if token and user_id is None:
            found = self.one('SELECT * FROM sessions WHERE token=? AND expires>?', (digest(token), now))
            if found:
                return token, found
        token = secrets.token_urlsafe(32)
        with self.transaction() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (now,))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                       (digest(token), user_id, secrets.token_urlsafe(32), now + 43200))
        return token, self.one('SELECT * FROM sessions WHERE token=?', (digest(token),))

    def account(self, user_id, apple_id):
        apple_id = apple_id.strip().casefold()
        if not 3 <= len(apple_id) <= 254 or '@' not in apple_id or any(c.isspace() for c in apple_id):
            raise Problem('Укажите email Apple ID.')
        with self.transaction() as db:
            db.execute('INSERT OR IGNORE INTO accounts(user_id,apple_id) VALUES(?,?)', (user_id, apple_id))
            account = db.execute('SELECT * FROM accounts WHERE user_id=? AND apple_id=?', (user_id, apple_id)).fetchone()
            self.enqueue_check(db, account['id'])
            return account['id']

    @staticmethod
    def enqueue_check(db, account_id):
        account = db.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()
        # A successful full snapshot is immutable until explicit refresh.
        previous = db.execute('SELECT 1 FROM checks WHERE account_id=?', (account_id,)).fetchone()
        if account['verified_at'] is None and not previous:
            db.execute('INSERT OR IGNORE INTO checks(account_id,created) VALUES(?,?)', (account_id, int(time.time())))

    def catalog(self, user_id, account_id):
        with self.transaction() as db:
            account = db.execute('SELECT * FROM accounts WHERE id=? AND user_id=?', (account_id, user_id)).fetchone()
            if account is None:
                raise Problem('Выберите свой Apple ID.', 404)
            self.enqueue_check(db, account_id)
            apps = db.execute('''SELECT a.*, EXISTS(SELECT 1 FROM purchases p
                 WHERE p.account_id=? AND p.store_id=a.store_id) AS owned
                 FROM apps a WHERE active=1 ORDER BY a.name''', (account_id,)).fetchall()
        return account, apps

    def order(self, user_id, account_id, app_id):
        now = int(time.time())
        with self.transaction() as db:
            account = db.execute('SELECT * FROM accounts WHERE id=? AND user_id=?', (account_id, user_id)).fetchone()
            if not account or account['verified_at'] is None:
                raise Problem('Сначала дождитесь проверки этого Apple ID.', 409)
            app = db.execute('SELECT * FROM apps WHERE id=? AND active=1', (app_id,)).fetchone()
            if not app:
                raise Problem('Приложение не найдено.', 404)
            if not db.execute('SELECT 1 FROM purchases WHERE account_id=? AND store_id=?', (account_id, app['store_id'])).fetchone():
                raise Problem('Приложение отсутствует в истории покупок этого Apple ID.', 403)
            old = db.execute("SELECT id,state FROM orders WHERE account_id=? AND app_id=? AND state IN ('awaiting_payment','queued','running','uncertain')", (account_id, app_id)).fetchone()
            used = db.execute("SELECT 1 FROM orders WHERE user_id=? AND price=0 AND state IN ('queued','running','succeeded','uncertain')", (user_id,)).fetchone()
            if old:
                if old['state'] == 'awaiting_payment' and not used:
                    db.execute("UPDATE orders SET price=0,state='queued',updated=? WHERE id=?", (now, old['id']))
                return old['id']
            price = PRICE_KOPEKS if used else 0
            state = 'awaiting_payment' if price else 'queued'
            order_id = secrets.token_hex(16)
            db.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (order_id, user_id, account_id, app_id, app['store_id'], app['name'], price, state, now, now, ''))
            self.audit(db, user_id, 'order.create', order_id)
            return order_id

    def provision_worker(self, account_id):
        token = secrets.token_urlsafe(48)
        with self.transaction() as db:
            if not db.execute('SELECT 1 FROM accounts WHERE id=?', (account_id,)).fetchone():
                raise Problem('Apple ID не найден.', 404)
            busy = db.execute("SELECT 1 FROM checks WHERE account_id=? AND state='running' UNION ALL SELECT 1 FROM orders WHERE account_id=? AND state='running'", (account_id, account_id)).fetchone()
            if busy:
                raise Problem('Сначала завершите текущую задачу исполнителя.', 409)
            db.execute('INSERT INTO workers(token,account_id) VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET token=excluded.token,revoked=0', (digest(token), account_id))
            self.audit(db, None, 'worker.provision', account_id)
        return token

    def worker(self, token):
        return self.one('SELECT w.*,a.apple_id FROM workers w JOIN accounts a ON a.id=w.account_id WHERE token=? AND revoked=0', (digest(token),))

    def claim(self, token):
        now = int(time.time())
        with self.transaction() as db:
            worker = db.execute('SELECT w.*,a.apple_id FROM workers w JOIN accounts a ON a.id=w.account_id WHERE token=? AND revoked=0', (digest(token),)).fetchone()
            if not worker:
                raise Problem('Исполнитель не авторизован.', 401)
            aid = worker['account_id']
            db.execute('UPDATE workers SET seen=? WHERE token=?', (now, digest(token)))
            # Never retry an install automatically: its device-side result may
            # be unknown after a disconnect. The gift remains reserved.
            db.execute("UPDATE orders SET state='uncertain',updated=?,detail='Исполнитель отключился. Требуется проверка устройства.' WHERE account_id=? AND state='running' AND updated<?", (now, aid, now-3600))
            db.execute("UPDATE checks SET state='failed',detail='Проверка прервана.' WHERE account_id=? AND state='running' AND claimed<?", (aid, now-900))
            if db.execute("SELECT 1 FROM checks WHERE account_id=? AND state='running' UNION ALL SELECT 1 FROM orders WHERE account_id=? AND state='running'", (aid, aid)).fetchone():
                return None
            check = db.execute("SELECT * FROM checks WHERE account_id=? AND state='queued' ORDER BY id LIMIT 1", (aid,)).fetchone()
            if check:
                db.execute("UPDATE checks SET state='running',claimed=? WHERE id=?", (now, check['id']))
                return dict(kind='check', id=check['id'], apple_id=worker['apple_id'])
            order = db.execute("SELECT * FROM orders WHERE account_id=? AND state='queued' ORDER BY created,id LIMIT 1", (aid,)).fetchone()
            if order:
                db.execute("UPDATE orders SET state='running',updated=? WHERE id=?", (now, order['id']))
                return dict(kind='install', id=order['id'], store_id=order['store_id'], apple_id=worker['apple_id'])
            return None

    def complete(self, token, data):
        now = int(time.time())
        with self.transaction() as db:
            worker = db.execute('SELECT * FROM workers WHERE token=? AND revoked=0', (digest(token),)).fetchone()
            if not worker:
                raise Problem('Исполнитель не авторизован.', 401)
            aid = worker['account_id']
            if data.get('kind') == 'check':
                job = db.execute('SELECT * FROM checks WHERE id=? AND account_id=?', (data.get('id'), aid)).fetchone()
                if not job or job['state'] != 'running':
                    raise Problem('Проверка уже завершена или не принадлежит исполнителю.', 409)
                if data.get('state') == 'succeeded':
                    ids = data.get('store_ids')
                    if data.get('complete') is not True or not isinstance(ids, list) or len(ids) > 100000 or any(not isinstance(x, str) or not x.isdigit() or not 1 <= len(x) <= 12 for x in ids):
                        raise Problem('Нужен полный результат проверки истории Apple.')
                    db.execute('DELETE FROM purchases WHERE account_id=?', (aid,))
                    db.executemany('INSERT OR IGNORE INTO purchases VALUES(?,?)', ((aid, x) for x in ids))
                    db.execute("UPDATE accounts SET verified_at=?,check_state='verified' WHERE id=?", (now, aid))
                    state = 'succeeded'
                else:
                    db.execute("UPDATE accounts SET check_state='failed' WHERE id=?", (aid,))
                    state = 'failed'
                db.execute('UPDATE checks SET state=?,detail=? WHERE id=?', (state, '' if state == 'succeeded' else 'Не удалось проверить историю Apple. Повторите проверку.', job['id']))
            elif data.get('kind') == 'install':
                state = data.get('state')
                if state not in ('succeeded', 'failed', 'uncertain'):
                    raise Problem('Неизвестный результат установки.')
                detail = {'succeeded': 'Установка подтверждена на устройстве.', 'failed': 'Установка не началась. Подарок сохранён.', 'uncertain': 'Результат не подтверждён. Нужна проверка устройства.'}[state]
                result = db.execute("UPDATE orders SET state=?,detail=?,updated=? WHERE id=? AND account_id=? AND state IN ('running','uncertain')", (state, detail, now, data.get('id'), aid))
                if result.rowcount != 1:
                    raise Problem('Заказ уже завершен или не принадлежит исполнителю.', 409)
            else:
                raise Problem('Неизвестная задача.')
            self.audit(db, None, 'worker.' + data['kind'] + '.' + state, data.get('id'))
