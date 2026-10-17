"""Execute production PHP transaction logic against an isolated SQLite ledger."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest

PHP = os.environ.get('APPREVIVE_TEST_PHP') or shutil.which('php')
ROOT = Path(__file__).resolve().parents[1]


def command():
    if not PHP:
        pytest.skip('PHP CLI and PDO SQLite are needed for backend tests')
    args = [PHP, '-n']
    extension_dir = os.environ.get('APPREVIVE_TEST_PHP_EXT_DIR')
    if extension_dir:
        args += ['-d', f'extension={extension_dir}/pdo.so', '-d', f'extension={extension_dir}/pdo_sqlite.so']
    else:
        # Use the normal configuration on a developer machine.
        args = [PHP]
    return args


def invoke(path, mode, *args):
    result = subprocess.run(command() + [str(ROOT / 'tests/test_promo_server_driver.php'), str(path), mode, *args], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout)


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / 'server.sqlite3'
    invoke(path, 'init')
    return path


def counts(path):
    with sqlite3.connect(path) as db:
        return tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('apprevive_promo_codes', 'apprevive_promo_redemptions'))


def test_activated_code_is_deleted_and_retry_returns_same_receipt(ledger):
    invoke(ledger, 'add', 'ONE')
    result = invoke(ledger, 'activate', 'ONE', 'a'*64, 'b'*32)
    assert result['status'] == 'activated' and result['credits'] == 1
    assert counts(ledger) == (0, 1)
    assert invoke(ledger, 'activate', 'ONE', 'a'*64, 'b'*32) == result
    assert counts(ledger) == (0, 1)
    assert invoke(ledger, 'activate', 'ONE', 'c'*64, 'd'*32)['status'] == 'invalid_code'


def test_two_computers_can_only_activate_one_shared_code_once(ledger):
    invoke(ledger, 'add', 'SHARED')
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(invoke, ledger, 'activate', 'SHARED', owner*64, request*32) for owner,request in [('a','b'),('c','d')]]
        results = [f.result() for f in futures]
    assert sorted(r['status'] for r in results) == ['activated', 'invalid_code']
    assert counts(ledger) == (0, 1)


@pytest.mark.parametrize("iteration",range(5))
def test_simultaneous_retries_are_idempotent(ledger,iteration):
    invoke(ledger, 'add', 'RETRY')
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: invoke(ledger, 'activate', 'RETRY', 'a'*64, 'b'*32), range(2)))
    assert [r['status'] for r in results] == ['activated', 'activated'], results
    assert results[0] == results[1]
    assert counts(ledger) == (0, 1)


def test_failure_after_delete_rolls_back_the_code(ledger):
    invoke(ledger, 'add', 'ROLLBACK')
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON apprevive_promo_redemptions BEGIN SELECT RAISE(ABORT,'test failure'); END")
    assert invoke(ledger, 'activate', 'ROLLBACK', 'a'*64, 'b'*32)['status'] == 'backend_error'
    assert counts(ledger) == (1, 0)


def test_request_id_cannot_be_reused_to_spend_another_code(ledger):
    for code in ('FIRST','SECOND'):
        invoke(ledger, 'add', code)
    assert invoke(ledger, 'activate', 'FIRST', 'a'*64, 'b'*32)['status'] == 'activated'
    assert invoke(ledger, 'activate', 'SECOND', 'a'*64, 'b'*32)['status'] == 'request_conflict'
    assert counts(ledger) == (1, 1)


def test_code_comparison_is_exact_and_input_is_not_sql(ledger):
    invoke(ledger, 'add', 'ABC-123')
    for code in ('ABC','abc-123', "' OR 1=1 --"):
        assert invoke(ledger, 'activate', code, 'a'*64, 'b'*32)['status'] == 'invalid_code'
    assert counts(ledger) == (1, 0)
