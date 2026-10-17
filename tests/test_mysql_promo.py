import hashlib
from unittest.mock import MagicMock
import pytest
import pymysql
from apprestore_core import mysql_promo
from apprestore_core.restoration_codes import RestorationCodeError, RestorationCredits


def connection(receipts, deleted=1):
    db = MagicMock()
    cur = db.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = receipts
    cur.rowcount = deleted
    return db, cur


def test_success_deletes_and_records_before_commit():
    db, cur = connection([None])
    mysql_promo._redeem(db, 'ExactCase', 'owner', 'request')
    statements = cur.execute.call_args_list
    assert statements[2].args == ('DELETE FROM apprevive_promo_codes WHERE code=%s', (b'ExactCase',))
    assert statements[3].args[1] == (hashlib.sha256(b'ExactCase').hexdigest(), 'owner', 'request')
    db.commit.assert_called_once()


def test_lost_response_retry_does_not_delete_again():
    db, cur = connection([(hashlib.sha256(b'code').hexdigest(),)])
    mysql_promo._redeem(db, 'code', 'owner', 'request')
    assert not any('DELETE' in call.args[0] for call in cur.execute.call_args_list)
    db.commit.assert_called_once()


def test_concurrent_identical_request_recovers_receipt():
    db, cur = connection([None, (hashlib.sha256(b'code').hexdigest(),)], deleted=0)
    mysql_promo._redeem(db, 'code', 'owner', 'request')
    db.commit.assert_called_once()


def test_invalid_code_rolls_back_and_closes(monkeypatch):
    db, _ = connection([None, None], deleted=0)
    monkeypatch.setattr(mysql_promo, 'mysql_settings', lambda: {})
    monkeypatch.setattr(pymysql, 'connect', lambda **kwargs: db)
    with pytest.raises(RestorationCodeError, match='Код не найден'):
        mysql_promo.activate_mysql_promo('missing', 'token', 'request')
    db.rollback.assert_called_once()
    db.close.assert_called_once()
    db.commit.assert_not_called()


def test_database_failure_after_delete_rolls_back(monkeypatch):
    db, cur = connection([None])
    cur.execute.side_effect = [None, None, None, pymysql.OperationalError(2013, 'sensitive server details')]
    monkeypatch.setattr(mysql_promo, 'mysql_settings', lambda: {})
    monkeypatch.setattr(pymysql, 'connect', lambda **kwargs: db)
    with pytest.raises(RestorationCodeError) as error:
        mysql_promo.activate_mysql_promo('code', 'token', 'request')
    assert 'sensitive' not in str(error.value)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    db.close.assert_called_once()


def test_default_uses_direct_mysql():
    assert RestorationCredits.__init__.__defaults__[0] is mysql_promo.activate_mysql_promo


def test_local_config(tmp_path, monkeypatch):
    path = tmp_path / 'mysql.json'
    path.write_text('{"password": "local-secret"}')
    monkeypatch.setenv('APPREVIVE_MYSQL_CONFIG', str(path))
    monkeypatch.delenv('APPREVIVE_MYSQL_PASSWORD', raising=False)
    assert mysql_promo.mysql_settings()['password'] == 'local-secret'
    monkeypatch.setenv('APPREVIVE_MYSQL_PASSWORD', 'override')
    assert mysql_promo.mysql_settings()['password'] == 'override'
