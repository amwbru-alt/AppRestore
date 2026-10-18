import hashlib
import pytest
from apprevive_core.account_credits import AccountAccess, AccountCredits, CodeRequired, account_id
from apprevive_core.restoration_codes import RestorationCodeError


class Server:
    def __init__(self):
        self.accounts = {}
        self.operations = {}
        self.codes = set()
        self.offline_finish = False
        self.drop_reserve = False

    def __call__(self, method, body):
        account = body['account_id']
        row = self.accounts.setdefault(account, [1, 0])
        request = body.get('request_id')
        result = dict(account_id=account, request_id=request)
        if method == 'reserve':
            key = account, request
            if key not in self.operations:
                if row[0] == 0:
                    raise CodeRequired()
                row[0] -= 1
                self.operations[key] = 'reserved'
            if self.drop_reserve:
                self.drop_reserve = False
                raise RestorationCodeError('timeout')
            return dict(result, status=self.operations[key])
        if method == 'finish':
            if self.offline_finish:
                raise RestorationCodeError('offline')
            state = 'completed' if body['success'] else 'failed'
            if self.operations[account, request] == 'reserved':
                row[1 if body['success'] else 0] += 1
                self.operations[account, request] = state
            return dict(result, status=state)
        if method == 'redeem':
            if body['code'] not in self.codes:
                self.codes.add(body['code'])
                row[0] += 1
            return dict(result, status='activated', credits=row[0], code_hash=hashlib.sha256(body['code'].encode()).hexdigest())
        return dict(result, status='ok', credits=row[0], installations=row[1])


def test_reinstall_and_different_computer_do_not_reset_gift(tmp_path):
    server = Server()
    def instance(name):
        credits = AccountCredits(tmp_path / name, lambda: 'Owner@Example.com', server)
        return credits, AccountAccess(credits, lambda: False)
    credits, access = instance('first.db')
    access.run(lambda: 'installed')
    assert credits.remaining == 0
    credits2, access2 = instance('reinstalled.db')
    assert credits2.remaining == 0
    with pytest.raises(RestorationCodeError):
        access2.run(lambda: pytest.fail('must not install'))
    assert server.accounts[account_id('owner@example.com')] == [0, 1]


def test_accounts_are_independent_failure_refunds_and_nested_counts_once(tmp_path):
    server = Server()
    email = ['first@example.com']
    credits = AccountCredits(tmp_path / 'state.db', lambda: email[0], server)
    access = AccountAccess(credits, lambda: False)
    with pytest.raises(ValueError):
        access.run(lambda: (_ for _ in ()).throw(ValueError()))
    assert credits.remaining == 1
    access.run(lambda: access.run(lambda: None))
    assert server.accounts[account_id(email[0])] == [0, 1]
    email[0] = 'other@example.com'
    assert credits.remaining == 1


def test_reserve_timeout_reuses_id_without_second_charge(tmp_path):
    server = Server()
    credits = AccountCredits(tmp_path / 'state.db', lambda: 'owner@example.com', server)
    access = AccountAccess(credits, lambda: False)
    server.drop_reserve = True
    with pytest.raises(RestorationCodeError):
        access.run(lambda: pytest.fail('no response'))
    access.run(lambda: None)
    assert len(server.operations) == 1
    assert credits.remaining == 0


def test_finish_timeout_recovers_without_running_install_again(tmp_path):
    server = Server()
    credits = AccountCredits(tmp_path / 'state.db', lambda: 'owner@example.com', server)
    access = AccountAccess(credits, lambda: False)
    server.offline_finish = True
    installed = []
    with pytest.raises(RestorationCodeError):
        access.run(lambda: installed.append(True))
    server.offline_finish = False
    with pytest.raises(RestorationCodeError, match='подтверждено'):
        access.run(lambda: installed.append(True))
    assert installed == [True]
    assert server.accounts[account_id('owner@example.com')] == [0, 1]


def test_code_is_credited_on_server_and_retries_are_idempotent(tmp_path):
    server = Server()
    credits = AccountCredits(tmp_path / 'state.db', lambda: 'owner@example.com', server)
    access = AccountAccess(credits, lambda: False)
    access.run(lambda: None)
    credits.redeem('ONE')
    credits.redeem('ONE')
    assert credits.remaining == 1


def test_no_install_when_server_is_unavailable(tmp_path):
    def offline(*args):
        raise RestorationCodeError('offline')
    credits = AccountCredits(tmp_path / 'state.db', lambda: 'owner@example.com', offline)
    access = AccountAccess(credits, lambda: pytest.fail('network failure is not an empty balance'))
    with pytest.raises(RestorationCodeError):
        access.run(lambda: pytest.fail('offline must not install'))


def test_ambiguous_crash_never_refunds_or_reinstalls(tmp_path):
    server = Server()
    credits = AccountCredits(tmp_path / 'state.db', lambda: 'owner@example.com', server)
    account = credits.select()
    request = 'a' * 32
    server('reserve', dict(account_id=account, request_id=request))
    credits.remember(account, request, None)
    access = AccountAccess(credits, lambda: False)
    with pytest.raises(RestorationCodeError, match='прервано'):
        access.run(lambda: pytest.fail('ambiguous operation'))
    assert credits.remaining == 0
