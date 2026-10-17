"""Direct MySQL redemption; credentials are configured on the user's machine."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import time
import pymysql


def mysql_settings():
    path = Path(os.environ.get("APPREVIVE_MYSQL_CONFIG", str(Path.home() / ".apprevive" / "mysql.json")))
    settings = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError("Настройки MySQL должны быть JSON-объектом.")
    password = os.environ.get("APPREVIVE_MYSQL_PASSWORD", settings.get("password", ""))
    if not password:
        raise ValueError("Укажите пароль MySQL в ~/.apprevive/mysql.json или APPREVIVE_MYSQL_PASSWORD.")
    options = dict(host=settings.get("host", "shuloquaticu.beget.app"), port=int(settings.get("port", 3306)),
                   user=settings.get("user", "apple"), database=settings.get("database", "apple"),
                   password=password, charset="utf8mb4", autocommit=False,
                   connect_timeout=10, read_timeout=15, write_timeout=15)
    if settings.get("ssl_ca"):
        options.update(ssl_ca=settings["ssl_ca"], ssl_verify_cert=True, ssl_verify_identity=True)
    return options


def _redeem(db, code, owner, request_id):
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    with db.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        db.begin()
        cur.execute("SELECT code_hash FROM apprevive_promo_redemptions WHERE owner_hash=%s AND request_id=%s FOR UPDATE", (owner, request_id))
        receipt = cur.fetchone()
        if receipt:
            if receipt[0] != digest:
                raise ValueError("Запрос активации уже связан с другим кодом.")
            db.commit()
            return
        cur.execute("DELETE FROM apprevive_promo_codes WHERE code=%s", (code.encode("utf-8"),))
        if cur.rowcount != 1:
            # A concurrent identical request can have committed while DELETE waited.
            cur.execute("SELECT code_hash FROM apprevive_promo_redemptions WHERE owner_hash=%s AND request_id=%s FOR UPDATE", (owner, request_id))
            receipt = cur.fetchone()
            if receipt and receipt[0] == digest:
                db.commit()
                return
            raise ValueError("Код не найден или уже использован.")
        cur.execute("INSERT INTO apprevive_promo_redemptions (code_hash, owner_hash, request_id) VALUES (%s,%s,%s)", (digest, owner, request_id))
    db.commit()


def activate_mysql_promo(code, installation_token, request_id):
    from .restoration_codes import RestorationCodeError
    owner = hashlib.sha256(installation_token.encode("utf-8")).hexdigest()
    try:
        options = mysql_settings()
        for attempt in range(3):
            db = pymysql.connect(**options)
            try:
                _redeem(db, code, owner, request_id)
                return
            except pymysql.MySQLError as exc:
                db.rollback()
                if exc.args[0] in (1205, 1213) and attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()
    except (ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "Не удалось прочитать настройки MySQL. Проверьте файл mysql.json."
        raise RestorationCodeError(message) from exc
    except pymysql.MySQLError as exc:
        number = exc.args[0] if exc.args else 0
        messages = {1045: "MySQL: доступ запрещён. Проверьте пользователя и пароль.",
                    1049: "MySQL: база данных не найдена.",
                    1146: "MySQL: таблицы кодов не созданы. Выполните schema.sql.",
                    1062: "Этот код уже использован."}
        raise RestorationCodeError(messages.get(number, "Не удалось проверить код в MySQL. Проверьте соединение и повторите запрос; код не будет списан повторно.")) from exc
