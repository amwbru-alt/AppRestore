from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
from socketserver import ThreadingMixIn
import sys
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

from .store import Problem, Store
from .web import Application


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        # Request paths can contain account/order selections. Keep access
        # logging at the reverse proxy with its own data-retention policy.
        pass


def main():
    parser = argparse.ArgumentParser(prog='appverni')
    parser.add_argument('--database', default=os.environ.get('APPVERNI_DATABASE', 'data/appverni.sqlite3'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('desktop', help='открыть исходное Qt-приложение с аккаунтами и каталогом')
    serve = sub.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8080)
    serve.add_argument('--dev-http', action='store_true', help='local HTTP only; disables Secure cookies')
    admin = sub.add_parser('create-admin')
    admin.add_argument('--email', required=True)
    promote = sub.add_parser('promote-admin')
    promote.add_argument('--email', required=True)
    provision = sub.add_parser('provision-worker')
    provision.add_argument('--account', type=int, required=True)
    provision.add_argument('--token-file', type=Path, required=True)
    resolve = sub.add_parser('resolve-order')
    resolve.add_argument('--id', required=True)
    resolve.add_argument('--result', choices=('succeeded', 'failed'), required=True)
    resolve.add_argument('--reason', required=True, help='результат ручной проверки устройства')
    worker = sub.add_parser('worker')
    worker.add_argument('--url', required=True)
    worker.add_argument('--token-file', type=Path, required=True)
    worker.add_argument('--apple-id', required=True)
    worker.add_argument('--udid', required=True)
    worker.add_argument('--state-file', type=Path, default=Path('data/worker-state.json'))
    worker.add_argument('--once', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'desktop':
            os.environ['APPVERNI_DATABASE'] = str(Path(args.database).resolve())
            from apprestore_gui.app import main as gui_main
            return gui_main(['--ui', 'widgets'])
        if args.command == 'worker':
            from .worker import run
            passphrase = getpass.getpass('Пароль локальной связки ключей ipatool (не пароль Apple ID, Enter если нет): ')
            run(args.url, args.token_file, args.apple_id, args.udid, args.state_file, once=args.once, passphrase=passphrase)
            return 0
        store = Store(args.database)
        if args.command == 'create-admin':
            password = getpass.getpass('Пароль администратора (от 12 символов): ')
            if password != getpass.getpass('Повторите пароль: '):
                raise Problem('Пароли не совпадают.')
            store.register(args.email, password, admin=True)
            print('Администратор создан.')
        elif args.command == 'promote-admin':
            with store.transaction() as db:
                user = db.execute('SELECT * FROM users WHERE email=?', (args.email.strip().casefold(),)).fetchone()
                if not user:
                    raise Problem('Пользователь не найден.')
                db.execute('UPDATE users SET admin=1 WHERE id=?', (user['id'],))
                store.audit(db, None, 'user.promote', user['id'])
            print('Роль администратора назначена.')
        elif args.command == 'resolve-order':
            if not 10 <= len(args.reason) <= 500:
                raise Problem('Укажите основание проверки (10–500 символов).')
            with store.transaction() as db:
                result = db.execute("UPDATE orders SET state=?,detail=?,updated=strftime('%s','now') WHERE id=? AND state='uncertain'", (args.result, args.reason, args.id))
                if result.rowcount != 1:
                    raise Problem('Заказ не найден или его статус не требует проверки.')
                store.audit(db, None, 'order.resolve.' + args.result, args.id)
            print('Результат ручной проверки сохранён.')
        elif args.command == 'provision-worker':
            # File creation is exclusive: never overwrite another worker secret.
            args.token_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(args.token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, 'w') as out:
                    token = store.provision_worker(args.account)
                    out.write(token + '\n')
            except BaseException:
                args.token_file.unlink(missing_ok=True)
                raise
            print('Секрет исполнителя записан в файл. Не передавайте его пользователям сервиса.')
        elif args.command == 'serve':
            if args.dev_http and args.host not in ('127.0.0.1', 'localhost', '::1'):
                raise Problem('--dev-http разрешён только на localhost.')
            app = Application(args.database, secure=not args.dev_http)
            print(f'АппВерни: http://{args.host}:{args.port}', flush=True)
            with make_server(args.host, args.port, app, server_class=ThreadedServer, handler_class=QuietHandler) as server:
                server.serve_forever()
    except (Problem, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
