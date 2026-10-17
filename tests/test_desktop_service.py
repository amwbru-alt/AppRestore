from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from appverni.desktop import DesktopLedger
from appverni.store import Problem


class FakeClient:
    def __init__(self, email='apple@example.com', ids=('10000000','20000000')):
        self.email, self.ids = email, ids
        self.calls = 0
        self.partial = False
    def account_info(self): return SimpleNamespace(email=self.email)
    def iter_purchases(self, **kwargs):
        self.calls += 1
        yield SimpleNamespace(items=[SimpleNamespace(track_id=int(x)) for x in self.ids],is_last=not self.partial,total=len(self.ids))


class FakeCore:
    on_device_install = None
    def __init__(self): self.installs = []; self.fail = False
    def devices(self): return [SimpleNamespace(udid='device')]
    def download_by_store_id(self, store_id, acquire_license):
        assert acquire_license is False
        self.installs.append(store_id)
        return Path('verified.ipa')
    def install(self, udid, path):
        self.on_device_install()
        if self.fail: raise RuntimeError('result unknown')


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ledger=DesktopLedger(Path(self.tmp.name)/'db.sqlite3')
        self.owner=self.ledger.register('owner@example.com','long-password-123',owner=True)
        self.user=self.ledger.register('user@example.com','long-password-123')
        self.uid=self.user['id'];self.client=FakeClient();self.core=FakeCore()
        self.app=self.ledger.save_app(self.owner['id'],name='Первое',store_id='10000000')
        self.second=self.ledger.save_app(self.owner['id'],name='Второе',store_id='20000000')

    def test_native_owner_setup_is_explicit_and_only_once(self):
        with self.assertRaises(Problem): self.ledger.register('evil@example.com','long-password-123',owner=True)
        self.assertFalse(self.ledger.authenticate('user@example.com','long-password-123')['admin'])
        with self.assertRaises(Problem): self.ledger.admin(self.uid)
        with self.assertRaises(Problem): self.ledger.authenticate('user@example.com','bad')

    def test_native_cache_separates_apple_ids_and_refresh_is_explicit(self):
        aid=self.ledger.verify(self.uid,self.client)
        self.assertEqual(self.client.calls,1)
        self.assertEqual(self.ledger.verify(self.uid,self.client),aid)
        self.assertEqual(self.client.calls,1)
        self.ledger.verify(self.uid,self.client,force=True)
        self.assertEqual(self.client.calls,2)
        self.client.email='different@example.com';self.client.ids=()
        other=self.ledger.verify(self.uid,self.client)
        self.assertNotEqual(aid,other)
        self.assertTrue(self.ledger.catalog(self.uid,aid)[0]['owned'])
        self.assertFalse(any(app['owned'] for app in self.ledger.catalog(self.uid,other)))

    def test_partial_refresh_does_not_remove_known_history(self):
        aid=self.ledger.verify(self.uid,self.client)
        self.client.partial=True
        with self.assertRaises(Problem):self.ledger.verify(self.uid,self.client,force=True)
        self.assertTrue(self.ledger.catalog(self.uid,aid)[0]['owned'])
        fresh=FakeClient('fresh@example.com');fresh.partial=True
        with self.assertRaises(Problem):self.ledger.verify(self.uid,fresh)
        account=self.ledger.store.one('SELECT * FROM accounts WHERE apple_id=?',('fresh@example.com',))
        self.assertIsNone(account['verified_at'])

    def test_native_install_uses_existing_core_without_http_or_worker(self):
        aid=self.ledger.verify(self.uid,self.client)
        order=self.ledger.install(self.uid,aid,self.app,self.client,self.core,'device')
        self.assertEqual((order['price'],order['state']),(0,'succeeded'))
        self.assertEqual(self.core.installs,['10000000'])
        self.assertFalse(self.ledger.gift_available(self.uid))
        paid=self.ledger.install(self.uid,aid,self.second,self.client,self.core,'device')
        self.assertEqual((paid['price'],paid['state']),(10000,'awaiting_payment'))
        self.assertEqual(self.core.installs,['10000000'])
        self.assertIsNone(self.ledger.store.one('SELECT 1 FROM workers'))

    def test_changed_identity_is_rejected_before_reserving_gift(self):
        aid=self.ledger.verify(self.uid,self.client)
        self.client.email='different@example.com'
        with self.assertRaises(Problem):self.ledger.install(self.uid,aid,self.app,self.client,self.core,'device')
        self.assertTrue(self.ledger.gift_available(self.uid));self.assertFalse(self.core.installs)

    def test_uncertain_result_and_admin_resolution(self):
        aid=self.ledger.verify(self.uid,self.client);self.core.fail=True
        order=self.ledger.install(self.uid,aid,self.app,self.client,self.core,'device')
        self.assertEqual(order['state'],'uncertain')
        self.assertFalse(self.ledger.gift_available(self.uid))
        with self.assertRaises(Problem):self.ledger.resolve_order(self.uid,order['id'],'failed','Проверено на устройстве')
        self.ledger.resolve_order(self.owner['id'],order['id'],'failed','Проверено на iPhone: приложение отсутствует')
        self.assertTrue(self.ledger.gift_available(self.uid))

    def test_restart_recovers_only_desktop_jobs(self):
        aid=self.ledger.verify(self.uid,self.client)
        desktop=self.ledger.store.order(self.uid,aid,self.app)
        remote=self.ledger.store.order(self.uid,aid,self.second)
        with self.ledger.store.transaction() as db:
            db.execute("UPDATE orders SET state='running' WHERE id IN (?,?)",(desktop,remote))
            db.execute('INSERT INTO desktop_inflight VALUES(?)',(desktop,))
        self.ledger.recover_interrupted()
        self.assertEqual(self.ledger.store.one('SELECT state FROM orders WHERE id=?',(desktop,))['state'],'uncertain')
        self.assertEqual(self.ledger.store.one('SELECT state FROM orders WHERE id=?',(remote,))['state'],'running')

    def test_admin_card_identity_and_user_bound_history(self):
        with self.assertRaises(Problem):self.ledger.save_app(self.uid,name='Evil',store_id='30000000')
        with self.assertRaises(Problem):self.ledger.save_app(self.owner['id'],app_id=self.app,name='Rename',store_id='30000000')
        self.ledger.save_app(self.owner['id'],app_id=self.app,name='Новое название',store_id='10000000',active=False)
        self.assertEqual(len(self.ledger.catalog(self.uid)),1)
        aid=self.ledger.verify(self.uid,self.client)
        with self.assertRaises(Problem):self.ledger.catalog(self.owner['id'],aid)


if __name__=='__main__':unittest.main()
