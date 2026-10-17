"""Dependency-free WSGI app. Run behind an HTTPS reverse proxy in production."""
from __future__ import annotations

import base64
import binascii
from html import escape
from http.cookies import SimpleCookie
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from . import BRAND
from .store import Problem, Store, digest, password_matches

ROOT = Path(__file__).resolve().parent
STATES = {'awaiting_payment': 'Ожидает оплаты', 'queued': 'В очереди', 'running': 'Устанавливается',
          'succeeded': 'Установлено', 'failed': 'Не установлено', 'uncertain': 'Нужна проверка'}


def e(value):
    return escape(str(value), quote=True)


def money(kopeks):
    return f'{kopeks // 100} ₽'


def stamp(ts):
    return time.strftime('%d.%m.%Y %H:%M UTC', time.gmtime(ts)) if ts else 'Ещё не проверен'


class Request:
    def __init__(self, app, env):
        self.app, self.env = app, env
        self.path = env.get('PATH_INFO', '/')
        self.method = env.get('REQUEST_METHOD', 'GET').upper()
        self.query = {k: v[-1] for k, v in parse_qs(env.get('QUERY_STRING', '')).items()}
        self.data = {}
        if self.method == 'POST':
            try:
                size = int(env.get('CONTENT_LENGTH') or 0)
            except ValueError:
                raise Problem('Неверный размер запроса.') from None
            if size < 0 or size > 3_000_000:
                raise Problem('Файл слишком большой. Максимум — 2 МБ.', 413)
            raw = env['wsgi.input'].read(size)
            try:
                if env.get('CONTENT_TYPE', '').split(';')[0] == 'application/json':
                    self.data = json.loads(raw)
                    if not isinstance(self.data, dict):
                        raise ValueError()
                else:
                    self.data = {k: v[-1] for k, v in parse_qs(raw.decode(), keep_blank_values=True).items()}
            except (ValueError, UnicodeError):
                raise Problem('Не удалось прочитать форму.') from None
        self.token, self.session, self.user = '', None, None

    def login(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.env.get('HTTP_COOKIE', ''))
            token = cookie['appverni_session'].value if 'appverni_session' in cookie else None
        except Exception:
            token = None
        self.token, self.session = self.app.store.session(token)
        if self.session['user_id']:
            self.user = self.app.store.one('SELECT id,email,admin FROM users WHERE id=?', (self.session['user_id'],))

    def require_user(self, admin=False):
        if not self.user:
            raise Problem('Войдите в аккаунт сервиса.', 401)
        if admin and not self.user['admin']:
            raise Problem('Раздел доступен только администратору.', 403)
        return self.user['id']

    def csrf(self):
        supplied = self.data.get('csrf', '')
        if not isinstance(supplied, str) or not secrets.compare_digest(supplied, self.session['csrf']):
            raise Problem('Форма устарела. Обновите страницу и повторите.', 403)

    def field(self):
        return f'<input type="hidden" name="csrf" value="{e(self.session["csrf"])}">'


class Application:
    def __init__(self, database, *, secure=True):
        self.store = Store(database)
        self.secure = secure
        self.media = Path(database).resolve().parent / 'images'
        self.media.mkdir(mode=0o700, parents=True, exist_ok=True)

    def __call__(self, env, start_response):
        req = None
        headers = []
        status = 200
        mime = 'text/html; charset=utf-8'
        try:
            req = Request(self, env)
            if req.path.startswith('/worker/'):
                body, status = self.worker_route(req)
                mime = 'application/json; charset=utf-8'
            elif req.path.startswith('/static/') or req.path.startswith('/media/'):
                body, mime = self.asset(req.path)
            else:
                req.login()
                if req.method == 'POST':
                    req.csrf()
                body, status, extra = self.route(req)
                headers += extra
        except Problem as exc:
            status = exc.status
            if req and req.path.startswith('/worker/'):
                body = json.dumps({'error': str(exc)}, ensure_ascii=False)
                mime = 'application/json; charset=utf-8'
            elif req and req.session:
                body = self.page(req, 'Не удалось выполнить действие', f'<section class="card"><p class="error">{e(exc)}</p><a class="button" href="/install">К установке</a></section>')
            else:
                body = e(exc)
        except Exception:
            # Do not disclose SQL, paths, account data or tool output in HTML.
            status, body = 500, 'Внутренняя ошибка. Повторите позже.'
        if req and req.token:
            value = f'appverni_session={req.token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200'
            if self.secure:
                value += '; Secure'
            headers.append(('Set-Cookie', value))
        body = body.encode('utf-8') if isinstance(body, str) else body
        headers += [('Content-Type', mime), ('Content-Length', str(len(body))),
                    ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                    ('Referrer-Policy', 'same-origin'), ('X-Frame-Options', 'DENY'),
                    ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")]
        if self.secure:
            headers.append(('Strict-Transport-Security', 'max-age=31536000'))
        reasons = {200:'OK', 303:'See Other', 400:'Bad Request', 401:'Unauthorized', 403:'Forbidden', 404:'Not Found', 405:'Method Not Allowed', 409:'Conflict', 413:'Content Too Large', 429:'Too Many Requests', 500:'Internal Server Error'}
        start_response(f'{status} {reasons.get(status, "Error")}', headers)
        return [body]

    def asset(self, path):
        if path in ('/static/style.css', '/static/app.js'):
            filename = ROOT / 'static' / path.rsplit('/', 1)[-1]
            return filename.read_bytes(), mimetypes.guess_type(str(filename))[0]
        if re.fullmatch(r'/media/[a-f0-9]{40}\.(png|jpg)', path):
            filename = self.media / path.rsplit('/', 1)[-1]
            if filename.is_file():
                return filename.read_bytes(), 'image/png' if filename.suffix == '.png' else 'image/jpeg'
        raise Problem('Файл не найден.', 404)

    def image(self, data):
        image = str(data.get('image', '')).strip()
        if image and (len(image) > 2048 or urlsplit(image).scheme != 'https' or not urlsplit(image).hostname):
            if not re.fullmatch(r'/media/[a-f0-9]{40}\.(png|jpg)', image):
                raise Problem('Для фото используйте HTTPS-ссылку или загрузите PNG/JPEG.')
        upload = data.get('image_data', '')
        if upload:
            try:
                raw = base64.b64decode(upload, validate=True)
            except (ValueError, binascii.Error):
                raise Problem('Не удалось прочитать фото.') from None
            if not 0 < len(raw) <= 2_000_000:
                raise Problem('Размер фото — до 2 МБ.')
            if raw.startswith(b'\x89PNG\r\n\x1a\n'):
                suffix = '.png'
            elif raw.startswith(b'\xff\xd8\xff'):
                suffix = '.jpg'
            else:
                raise Problem('Фото должно быть PNG или JPEG.')
            name = secrets.token_hex(20) + suffix
            with (self.media / name).open('xb') as out:
                out.write(raw)
            image = '/media/' + name
        return image

    def redirect(self, path):
        return '', 303, [('Location', path)]

    def page(self, r, title, body, *, active='', refresh=False):
        csrf = r.field()
        nav = '<a href="/install" class="' + ('selected' if active == 'install' else '') + '">▦ Установить</a><a href="/orders">↗ Мои установки</a>'
        if r.user and r.user['admin']:
            nav += '<a href="/admin" class="' + ('selected' if active == 'admin' else '') + '">⚙ Админ-панель</a>'
        if r.user:
            account = f'<span class="account">{e(r.user["email"])}</span><form method="post" action="/logout">{csrf}<button class="text-button">Выйти</button></form>'
        else:
            account = '<a href="/login">Войти</a><a class="button small" href="/register">Регистрация</a>'
        return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} — {BRAND}</title><link rel="stylesheet" href="/static/style.css"><script src="/static/app.js" defer></script></head><body {'data-refresh="true"' if refresh else ''}>
<header><a class="brand" href="/"><span class="brand-icon">↺</span>{BRAND}</a><div class="header-right">{account}</div></header>
<div class="layout"><aside><div class="nav-label">ВАШИ ПРИЛОЖЕНИЯ</div><nav>{nav}</nav><div class="aside-note"><span class="gift-icon">✦</span><b>Начните с подарка</b><p>Первая установка бесплатно.<br>Следующие — по 100 ₽.</p></div><span class="aside-footer">Снова на вашем iPhone.</span></aside><main><div class="eyebrow">АППВЕРНИ / ВАШ КАБИНЕТ</div><h1>{e(title)}</h1>{body}</main></div><footer>Устанавливаем приложения из истории вашего Apple ID. Наличие в истории не гарантирует доступность файла у Apple.</footer></body></html>'''

    def auth_page(self, r, register=False, error=''):
        title = 'Создать аккаунт' if register else 'С возвращением'
        target = '/register' if register else '/login'
        body = f'''<div class="auth-grid"><section class="card auth-card"><span class="tag">АККАУНТ СЕРВИСА</span><h2>{'Зарегистрируйтесь в АппВерни' if register else 'Войдите в АппВерни'}</h2><p class="muted">Это отдельный аккаунт сервиса. Apple ID подключается после входа.</p>{f'<p class="error" role="alert">{e(error)}</p>' if error else ''}<form method="post" action="{target}">{r.field()}<label>Email<input name="email" type="email" autocomplete="email" required maxlength="254"></label><label>Пароль<input name="password" type="password" autocomplete="{'new-password' if register else 'current-password'}" required minlength="12" maxlength="128"></label><p class="muted">{'Не менее 12 символов.' if register else ''}</p><button class="button full">{'Создать аккаунт' if register else 'Войти'}</button></form><p>{'<a href="/login">Уже есть аккаунт? Войти</a>' if register else '<a href="/register">Нет аккаунта? Зарегистрироваться</a>'}</p></section><section class="auth-story"><span class="big-symbol">↺</span><h2>Любимые приложения.<br>Снова под рукой.</h2><p>Подключите Apple ID, посмотрите доступные приложения и верните нужное на iPhone.</p><span class="tag">1 УСТАНОВКА В ПОДАРОК</span></section></div>'''
        return self.page(r, title, body)

    def route(self, r):
        s, p, method = self.store, r.path, r.method
        if method not in ('GET', 'POST'):
            raise Problem('Метод не поддерживается.', 405)
        if p == '/':
            return self.redirect('/install' if r.user else '/login')
        if p in ('/login', '/register'):
            if r.user:
                return self.redirect('/install')
            if method == 'GET':
                return self.auth_page(r, p == '/register'), 200, []
            try:
                s.throttle('auth-ip:' + r.env.get('REMOTE_ADDR', 'unknown'), limit=100)
                s.throttle('auth-email:' + str(r.data.get('email', '')).strip().casefold())
                password = str(r.data.get('password', ''))
                email = str(r.data.get('email', '')).strip().casefold()
                if p == '/register':
                    uid = s.register(email, password)
                else:
                    if not 1 <= len(password) <= 128:
                        raise Problem('Неверный email или пароль.', 401)
                    user = s.one('SELECT * FROM users WHERE email=?', (email,))
                    # Equal work for unknown emails to reduce account enumeration.
                    stored = user['password'] if user else self.dummy_password
                    if not password_matches(password, stored) or not user:
                        raise Problem('Неверный email или пароль.', 401)
                    uid = user['id']
                with s.transaction() as db:
                    db.execute('DELETE FROM sessions WHERE token=?', (digest(r.token),))
                r.token, r.session = s.session(user_id=uid)
                return self.redirect('/install')
            except Problem as exc:
                return self.auth_page(r, p == '/register', str(exc)), exc.status, []
        if p == '/logout' and method == 'POST':
            with s.transaction() as db:
                db.execute('DELETE FROM sessions WHERE token=?', (digest(r.token),))
            r.token, r.session = s.session()
            return self.redirect('/login')
        if not r.user:
            return self.redirect('/login')
        uid = r.require_user()
        if p == '/accounts' and method == 'POST':
            aid = s.account(uid, str(r.data.get('apple_id', '')))
            return self.redirect('/install?' + urlencode({'account': aid}))
        if p == '/install' and method == 'GET':
            return self.install_page(r), 200, []
        if p == '/install' and method == 'POST':
            aid, app_id = self.integer(r.data, 'account_id'), self.integer(r.data, 'app_id')
            oid = s.order(uid, aid, app_id)
            return self.redirect('/orders/' + oid)
        if p == '/accounts/refresh' and method == 'POST':
            aid = self.integer(r.data, 'account_id')
            with s.transaction() as db:
                account = db.execute('SELECT * FROM accounts WHERE id=? AND user_id=?', (aid, uid)).fetchone()
                if not account:
                    raise Problem('Apple ID не найден.', 404)
                # Refresh keeps the old verified snapshot until a new complete
                # one is available. A failed request never deletes entitlements.
                recent = db.execute('SELECT created FROM checks WHERE account_id=? ORDER BY id DESC LIMIT 1', (aid,)).fetchone()
                if recent and recent['created'] > int(time.time())-60:
                    raise Problem('Повторить проверку можно через минуту.', 429)
                db.execute('INSERT OR IGNORE INTO checks(account_id,created) VALUES(?,?)', (aid, int(time.time())))
            return self.redirect('/install?' + urlencode({'account': aid}))
        if p == '/orders' and method == 'GET':
            return self.orders_page(r), 200, []
        if re.fullmatch(r'/orders/[a-f0-9]{32}', p) and method == 'GET':
            return self.orders_page(r, p.rsplit('/', 1)[-1]), 200, []
        if p.startswith('/admin'):
            r.require_user(admin=True)
            return self.admin_route(r)
        raise Problem('Страница не найдена.', 404)

    @property
    def dummy_password(self):
        if not hasattr(self, '_dummy_password'):
            from .store import hash_password
            self._dummy_password = hash_password(secrets.token_urlsafe(32))
        return self._dummy_password

    @staticmethod
    def integer(data, key):
        try:
            value = int(data.get(key, ''))
            if value <= 0:
                raise ValueError()
            return value
        except (ValueError, TypeError):
            raise Problem('Не указан корректный идентификатор.') from None

    def install_page(self, r):
        s, uid = self.store, r.user['id']
        accounts = s.rows('SELECT * FROM accounts WHERE user_id=? ORDER BY id', (uid,))
        gift = not s.one("SELECT 1 FROM orders WHERE user_id=? AND price=0 AND state IN ('queued','running','succeeded','uncertain')", (uid,))
        body = f'<p class="lead">Верните приложения, которые уже были на вашем Apple ID.</p><div class="offer"><span class="gift-icon">✦</span><div><b>{"Первая установка — за наш счёт" if gift else "Установка любого доступного приложения — 100 ₽"}</b><p>{"Выберите приложение ниже. Следующие установки — по 100 ₽." if gift else "Приём оплаты скоро появится. Заказ можно создать уже сейчас."}</p></div><span class="price">{"0 ₽" if gift else "100 ₽"}</span></div>'
        body += f'<details class="card compact" {"open" if not accounts else ""}><summary>Подключить Apple ID</summary><p class="muted">Пароль Apple ID здесь не нужен. Историю проверяет исполнитель сервиса в отдельной авторизованной сессии Apple.</p><form class="inline-form" method="post" action="/accounts">{r.field()}<label>Email Apple ID<input name="apple_id" type="email" required maxlength="254" placeholder="you@icloud.com"></label><button class="button">Подключить</button></form></details>'
        if not accounts:
            return self.page(r, 'Установить приложения', body + '<section class="empty"><h2>Начнём с вашего Apple ID</h2><p>Подключите аккаунт, чтобы проверить доступные приложения.</p></section>', active='install')
        aid = self.integer(r.query, 'account') if r.query.get('account') else accounts[0]['id']
        account, apps = s.catalog(uid, aid)
        options = ''.join(f'<option value="{a["id"]}" {"selected" if a["id"] == aid else ""}>{e(a["apple_id"])}</option>' for a in accounts)
        body += f'<section class="catalog-heading"><div><h2>Ваш каталог</h2><p class="muted">Проверено: {e(stamp(account["verified_at"]))}</p></div><form method="get" action="/install" class="inline-form"><label>Apple ID<select name="account">{options}</select></label><button class="button secondary">Выбрать</button></form></section>'
        checking = s.one("SELECT 1 FROM checks WHERE account_id=? AND state IN ('queued','running')", (aid,))
        if checking:
            body += '<p class="notice" role="status">Проверяем полную историю Apple ID. Подключённый исполнитель должен быть запущен. Страница обновится автоматически.</p>'
        elif account['check_state'] == 'failed':
            body += '<p class="error">Проверка Apple не завершилась. Данные об отсутствии приложений не сохранены. Повторите проверку.</p>'
        body += f'<form method="post" action="/accounts/refresh" class="refresh-form">{r.field()}<input type="hidden" name="account_id" value="{aid}"><button class="text-button">Обновить историю Apple</button></form><div class="cards">'
        for app in apps:
            known, owned = account['verified_at'] is not None, app['owned']
            status = 'Есть в истории Apple ID' if known and owned else ('Нет в истории этого Apple ID' if known else 'Ожидает проверки Apple ID')
            art = f'<img src="{e(app["image"])}" alt="{e(app["name"])}" loading="lazy">' if app['image'] else '<span class="app-placeholder">↺</span>'
            body += f'<article class="app-card"><div class="app-top">{art}<span class="tag">iOS</span></div><h3>{e(app["name"])}</h3><p class="description">{e(app["description"])}</p><p class="availability {"available" if known and owned else ""}">{e(status)}</p><form method="post" action="/install">{r.field()}<input type="hidden" name="account_id" value="{aid}"><input type="hidden" name="app_id" value="{app["id"]}"><button class="button full" {"disabled" if not known or not owned else ""}>{"Установить бесплатно" if gift else "Установить · 100 ₽"}</button></form><p class="store-id">App Store ID: {e(app["store_id"])}</p></article>'
        body += '</div>'
        if not apps:
            body += '<section class="empty"><h2>Каталог скоро появится</h2><p>Администратор ещё не добавил приложения.</p></section>'
        body += '<p class="muted footnote">В истории Apple видны ранее полученные приложения, включая бесплатные. Это подтверждает право на повторную загрузку, но не дату фактической установки на устройстве.</p>'
        return self.page(r, 'Установить приложения', body, active='install', refresh=bool(checking))

    def orders_page(self, r, order_id=None):
        args = (r.user['id'], order_id) if order_id else (r.user['id'],)
        orders = self.store.rows('SELECT o.*,a.apple_id FROM orders o JOIN accounts a ON a.id=o.account_id WHERE o.user_id=?' + (' AND o.id=?' if order_id else '') + ' ORDER BY o.created DESC,o.id DESC', args)
        if order_id and not orders:
            raise Problem('Заказ не найден.', 404)
        body = '<p class="lead">Статусы и стоимость ваших установок.</p>'
        for o in orders:
            body += f'<section class="card order"><div><span class="tag">{e(STATES[o["state"]])}</span><h2>{e(o["app_name"])}</h2><p class="muted">{e(o["apple_id"])} · {e(stamp(o["created"]))}</p></div><strong class="price">{money(o["price"])}</strong><p>{e(o["detail"])}</p>'
            if o['state'] == 'awaiting_payment':
                body += '<p class="notice">Приём оплаты пока не подключён. Заказ на 100 ₽ создан; списания и установка не выполняются.</p>'
            if o['state'] == 'queued':
                body += '<p>Ожидаем исполнителя сервиса и подключённый iPhone.</p>'
            body += f'<span class="muted store-id">Заказ {e(o["id"])}</span></section>'
        if not orders:
            body += '<section class="empty"><h2>Установок пока нет</h2><a class="button" href="/install">Открыть каталог</a></section>'
        return self.page(r, 'Мои установки', body, refresh=any(o['state'] in ('queued','running') for o in orders))

    def admin_route(self, r):
        s, uid = self.store, r.user['id']
        if r.path == '/admin/apps' and r.method == 'POST':
            name = str(r.data.get('name', '')).strip()
            store_id = str(r.data.get('store_id', '')).strip()
            description = str(r.data.get('description', '')).strip()
            if not 1 <= len(name) <= 100 or not re.fullmatch(r'[1-9][0-9]{7,11}', store_id) or len(description) > 1000:
                raise Problem('Укажите название (до 100 символов), App Store ID (8–12 цифр), описание (до 1000 символов).')
            app_id = self.integer(r.data, 'id') if r.data.get('id') else None
            image = self.image(r.data)
            with s.transaction() as db:
                if db.execute('SELECT 1 FROM apps WHERE store_id=? AND id!=?', (store_id, app_id or 0)).fetchone():
                    raise Problem('Приложение с этим App Store ID уже есть.')
                if app_id:
                    old = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
                    if not old:
                        raise Problem('Приложение не найдено.', 404)
                    # Store ID is an identity, not editable metadata. New ID
                    # requires a new app; old orders retain their snapshot.
                    if old['store_id'] != store_id:
                        raise Problem('ID существующего приложения менять нельзя. Создайте новую карточку.')
                    db.execute('UPDATE apps SET name=?,image=?,description=?,active=? WHERE id=?', (name, image, description, int(r.data.get('active') == '1'), app_id))
                else:
                    app_id = db.execute('INSERT INTO apps(store_id,name,image,description,active) VALUES(?,?,?,?,?)', (store_id, name, image, description, int(r.data.get('active') == '1'))).lastrowid
                s.audit(db, uid, 'app.save', app_id)
            return self.redirect('/admin')
        if r.path != '/admin' or r.method != 'GET':
            raise Problem('Страница не найдена.', 404)
        apps = s.rows('SELECT * FROM apps ORDER BY id DESC')
        edit = None
        if r.query.get('edit'):
            edit = s.one('SELECT * FROM apps WHERE id=?', (self.integer(r.query, 'edit'),))
            if not edit:
                raise Problem('Приложение не найдено.', 404)
        current = dict(edit) if edit else dict(id='', name='', store_id='', image='', description='', active=1)
        total_users = s.one('SELECT count(*) AS n FROM users')['n']
        body = f'<p class="lead">Управляйте каталогом и следите за установками.</p><div class="stats"><section class="card"><span class="muted">Пользователей</span><strong>{total_users}</strong></section><section class="card"><span class="muted">Приложений</span><strong>{len(apps)}</strong></section><section class="card"><span class="muted">Цена установки</span><strong>100 ₽</strong></section></div>'
        body += f'''<section class="card"><h2>{'Изменить приложение' if edit else 'Добавить приложение'}</h2><form method="post" action="/admin/apps" data-image-form>{r.field()}<input type="hidden" name="id" value="{current['id']}"><div class="form-grid"><label>Название<input name="name" required maxlength="100" value="{e(current['name'])}"></label><label>App Store ID<input name="store_id" required pattern="[1-9][0-9]{{7,11}}" value="{e(current['store_id'])}" {'readonly' if edit else ''}></label><label>HTTPS-ссылка на фото<input name="image" value="{e(current['image'])}" maxlength="2048"></label><label>Или загрузите PNG/JPEG до 2 МБ<input type="file" accept="image/png,image/jpeg" data-image-file></label></div><input type="hidden" name="image_data" value=""><label>Описание<textarea name="description" maxlength="1000">{e(current['description'])}</textarea></label><label class="checkbox"><input type="checkbox" name="active" value="1" {'checked' if current['active'] else ''}>Показывать в каталоге</label><p role="alert" data-upload-error></p><button class="button">Сохранить приложение</button> <a href="/admin">Новая карточка</a></form></section>'''
        body += '<h2>Каталог</h2><div class="table-wrap"><table><thead><tr><th>Приложение</th><th>App Store ID</th><th>Видимость</th><th></th></tr></thead><tbody>'
        for a in apps:
            body += f'<tr><td>{e(a["name"])}</td><td>{e(a["store_id"])}</td><td>{"Опубликовано" if a["active"] else "Скрыто"}</td><td><a href="/admin?edit={a["id"]}">Изменить</a></td></tr>'
        body += '</tbody></table></div><h2>Пользователи и проверка Apple ID</h2><div class="table-wrap"><table><thead><tr><th>Аккаунт сервиса</th><th>Apple ID / ID связи</th><th>Проверка</th><th>Исполнитель</th></tr></thead><tbody>'
        accounts = s.rows('SELECT a.*,u.email,w.seen FROM accounts a JOIN users u ON u.id=a.user_id LEFT JOIN workers w ON w.account_id=a.id ORDER BY a.id DESC LIMIT 200')
        for a in accounts:
            body += f'<tr><td>{e(a["email"])}</td><td>{e(a["apple_id"])} · #{a["id"]}</td><td>{e(stamp(a["verified_at"]))}</td><td>{e(stamp(a["seen"]))}</td></tr>'
        body += '</tbody></table></div><h2>Последние заказы</h2><div class="table-wrap"><table><thead><tr><th>Приложение</th><th>Пользователь</th><th>Цена</th><th>Статус</th></tr></thead><tbody>'
        for o in s.rows('SELECT o.*,u.email FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.created DESC,o.id DESC LIMIT 200'):
            body += f'<tr><td>{e(o["app_name"])}</td><td>{e(o["email"])}</td><td>{money(o["price"])}</td><td>{e(STATES[o["state"]])}</td></tr>'
        body += '</tbody></table></div>'
        return self.page(r, 'Админ-панель', body, active='admin'), 200, []

    def worker_route(self, r):
        if r.method != 'POST':
            raise Problem('Нужен POST.', 405)
        token = r.env.get('HTTP_AUTHORIZATION', '').removeprefix('Bearer ')
        if not self.store.worker(token):
            raise Problem('Исполнитель не авторизован.', 401)
        if r.path == '/worker/claim':
            return json.dumps({'job': self.store.claim(token)}, ensure_ascii=False), 200
        if r.path == '/worker/complete':
            self.store.complete(token, r.data)
            return '{"ok":true}', 200
        raise Problem('Маршрут не найден.', 404)
