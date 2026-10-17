from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from appverni.store import Problem, Store, digest, password_matches
from appverni.web import Application
from appverni.worker import Executor, Transport, write_result
from apprestore_core.paths import resolve_tool


class Client:
    def __init__(self, app):
        self.app, self.cookie = app, ''

    def request(self, path, method='GET', data=None, token=None):
        env = {}
        setup_testing_defaults(env)
        pathname, _, query = path.partition('?')
        raw = json.dumps(data or {}).encode() if token else urlencode(data or {}).encode()
        env.update(PATH_INFO=pathname, QUERY_STRING=query, REQUEST_METHOD=method,
                   CONTENT_LENGTH=str(len(raw)), CONTENT_TYPE='application/json' if token else 'application/x-www-form-urlencoded',
                   HTTP_COOKIE=self.cookie, REMOTE_ADDR='127.0.0.1')
        env['wsgi.input'] = BytesIO(raw)
        if token:
            env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        result = {}
        def start(status, headers):
            result['status'], result['headers'] = int(status.split()[0]), dict(headers)
            if 'Set-Cookie' in result['headers']:
                self.cookie = result['headers']['Set-Cookie'].split(';')[0]
        result['body'] = b''.join(self.app(env, start)).decode(errors='replace')
        return result

    def csrf(self, page='/login'):
        html = self.request(page)['body']
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def register(self, email='user@example.com', password='test-password-123'):
        return self.request('/register', 'POST', {'csrf': self.csrf('/register'), 'email': email, 'password': password, 'admin': '1'})

    def login(self, email, password='test-password-123'):
        return self.request('/login', 'POST', {'csrf': self.csrf(), 'email': email, 'password': password})

    def post(self, path, data=None, page='/install'):
        return self.request(path, 'POST', dict(data or {}, csrf=self.csrf(page)))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Application(Path(self.temp.name) / 'service.sqlite3', secure=False)
        self.s = self.app.store
        self.client = Client(self.app)
        self.uid = self.s.register('user@example.com', 'test-password-123')
        self.other = self.s.register('other@example.com', 'test-password-123')
        self.admin = self.s.register('admin@example.com', 'test-password-123', admin=True)
        self.aid = self.s.account(self.uid, 'apple@example.com')
        self.token = self.s.provision_worker(self.aid)
        with self.s.transaction() as db:
            self.ids = [db.execute('INSERT INTO apps(store_id,name) VALUES(?,?)', (str(10000000 + i), 'Приложение ' + str(i))).lastrowid for i in range(8)]

    def verify(self, ids=None):
        job = self.s.claim(self.token)
        self.assertEqual(job['kind'], 'check')
        self.s.complete(self.token, dict(job, state='succeeded', complete=True, store_ids=ids if ids is not None else [str(10000000 + i) for i in range(8)]))

    def test_registration_hashes_password_and_never_grants_admin(self):
        response = self.client.register('new@example.com')
        self.assertEqual(response['status'], 303)
        user = self.s.one('SELECT * FROM users WHERE email=?', ('new@example.com',))
        self.assertEqual(user['admin'], 0)
        self.assertNotIn('test-password', user['password'])
        self.assertTrue(password_matches('test-password-123', user['password']))

    def test_csrf_and_session_rotation(self):
        before = self.client.csrf()
        cookie = self.client.cookie
        self.assertEqual(self.client.request('/login', 'POST', {'email':'user@example.com','password':'test-password-123'})['status'], 403)
        self.assertEqual(self.client.login('user@example.com')['status'], 303)
        self.assertNotEqual(cookie, self.client.cookie)
        self.assertEqual(self.client.request('/logout', 'POST', {'csrf':before})['status'], 403)
        self.assertEqual(self.client.post('/logout')['status'], 303)
        self.assertEqual(self.client.request('/install')['headers']['Location'], '/login')

    def test_anonymous_and_regular_users_cannot_access_admin(self):
        self.assertEqual(self.client.request('/admin')['headers']['Location'], '/login')
        self.client.login('user@example.com')
        self.assertEqual(self.client.request('/admin')['status'], 403)
        response = self.client.post('/admin/apps', {'name':'x','store_id':'10000001'})
        self.assertEqual(response['status'], 403)

    def test_worker_routes_need_a_bound_token(self):
        self.assertEqual(self.client.request('/worker/claim','POST',{},'bad')['status'], 401)
        job = self.client.request('/worker/claim','POST',{},self.token)
        self.assertEqual(job['status'], 200)
        other_aid = self.s.account(self.other, 'other-apple@example.com')
        other_token = self.s.provision_worker(other_aid)
        data = dict(json.loads(job['body'])['job'],state='succeeded',complete=True,store_ids=[])
        self.assertEqual(self.client.request('/worker/complete','POST',data,other_token)['status'], 409)

    def test_initial_history_checked_once_and_new_apps_use_full_snapshot(self):
        self.verify(['10000000','99999999'])
        for _ in range(3):
            account, apps = self.s.catalog(self.uid, self.aid)
            self.assertIsNotNone(account['verified_at'])
        self.assertIsNone(self.s.claim(self.token))
        self.assertEqual(self.s.one('SELECT count(*) n FROM checks')['n'], 1)
        with self.s.transaction() as db:
            new = db.execute('INSERT INTO apps(store_id,name) VALUES(?,?)',('99999999','Новое')).lastrowid
        _, apps = self.s.catalog(self.uid, self.aid)
        self.assertTrue(next(a for a in apps if a['id']==new)['owned'])
        self.assertFalse(next(a for a in apps if a['id']==self.ids[1])['owned'])

    def test_failed_or_partial_history_never_becomes_a_negative_snapshot(self):
        job = self.s.claim(self.token)
        with self.assertRaises(Problem):
            self.s.complete(self.token,dict(job,state='succeeded',complete=False,store_ids=[]))
        self.s.complete(self.token,dict(job,state='failed'))
        account, _ = self.s.catalog(self.uid,self.aid)
        self.assertIsNone(account['verified_at'])
        self.assertIsNone(self.s.claim(self.token))
        with self.assertRaises(Problem):
            self.s.order(self.uid,self.aid,self.ids[0])

    def test_history_isolation_and_unowned_or_hidden_app_rejected(self):
        self.verify(['10000000'])
        with self.assertRaises(Problem): self.s.catalog(self.other,self.aid)
        with self.assertRaises(Problem): self.s.order(self.other,self.aid,self.ids[0])
        with self.assertRaises(Problem): self.s.order(self.uid,self.aid,self.ids[1])
        with self.s.transaction() as db: db.execute('UPDATE apps SET active=0 WHERE id=?',(self.ids[0],))
        with self.assertRaises(Problem): self.s.order(self.uid,self.aid,self.ids[0])

    def test_one_gift_under_concurrent_requests_and_paid_jobs_never_claimed(self):
        self.verify()
        with ThreadPoolExecutor(max_workers=8) as pool:
            orders = list(pool.map(lambda app_id:self.s.order(self.uid,self.aid,app_id),self.ids))
        free = self.s.rows('SELECT * FROM orders WHERE price=0')
        self.assertEqual(len(free),1)
        self.assertEqual(self.s.one("SELECT count(*) n FROM orders WHERE state='awaiting_payment' AND price=10000")['n'],7)
        job = self.s.claim(self.token)
        self.assertEqual(job['id'],free[0]['id'])
        self.assertEqual(job['store_id'],free[0]['store_id'])
        self.assertIsNone(self.s.claim(self.token))
        self.s.complete(self.token,dict(job,state='succeeded'))
        self.assertIsNone(self.s.claim(self.token))
        next_order = self.s.order(self.uid,self.aid,free[0]['app_id'])
        self.assertEqual(self.s.one('SELECT price FROM orders WHERE id=?',(next_order,))['price'],10000)

    def test_idempotent_clicks_and_failed_install_preserves_gift(self):
        self.verify()
        oid = self.s.order(self.uid,self.aid,self.ids[0])
        self.assertEqual(oid,self.s.order(self.uid,self.aid,self.ids[0]))
        paid = self.s.order(self.uid,self.aid,self.ids[1])
        job = self.s.claim(self.token)
        self.s.complete(self.token,dict(job,state='failed'))
        self.assertEqual(self.s.order(self.uid,self.aid,self.ids[1]),paid)
        order = self.s.one('SELECT * FROM orders WHERE id=?',(paid,))
        self.assertEqual((order['state'],order['price']),('queued',0))

    def test_uncertain_install_does_not_release_gift_or_requeue(self):
        self.verify()
        self.s.order(self.uid,self.aid,self.ids[0])
        job = self.s.claim(self.token)
        self.s.complete(self.token,dict(job,state='uncertain'))
        oid = self.s.order(self.uid,self.aid,self.ids[1])
        self.assertEqual(self.s.one('SELECT price FROM orders WHERE id=?',(oid,))['price'],10000)
        self.assertIsNone(self.s.claim(self.token))
        self.s.complete(self.token,dict(job,state='succeeded'))
        with self.assertRaises(Problem): self.s.complete(self.token,dict(job,state='failed'))

    def test_refresh_error_preserves_existing_verified_snapshot(self):
        self.verify(['10000000'])
        with self.s.transaction() as db:
            db.execute('INSERT INTO checks(account_id,created) VALUES(?,0)',(self.aid,))
        job = self.s.claim(self.token)
        self.s.complete(self.token,dict(job,state='failed'))
        account,apps=self.s.catalog(self.uid,self.aid)
        self.assertIsNotNone(account['verified_at'])
        self.assertTrue(apps[0]['owned'])

    def test_catalog_install_order_and_owner_only_history(self):
        self.verify()
        self.client.login('user@example.com')
        page=self.client.request('/install')
        self.assertIn('Установить бесплатно',page['body'])
        response=self.client.post('/install',{'account_id':self.aid,'app_id':self.ids[0],'price':0,'state':'succeeded'})
        self.assertEqual(response['status'],303)
        path=response['headers']['Location']
        self.assertIn('В очереди',self.client.request(path)['body'])
        other=Client(self.app);other.login('other@example.com')
        self.assertEqual(other.request(path)['status'],404)

    def test_admin_can_upload_edit_and_hide_without_overwriting_identity(self):
        self.client.login('admin@example.com')
        data={'name':'Тест <script>','store_id':'20000000','image_data':'iVBORw0KGgo=','active':'1','description':'Тест'}
        self.assertEqual(self.client.post('/admin/apps',data,page='/admin')['status'],303)
        row=self.s.one('SELECT * FROM apps WHERE store_id=?',('20000000',))
        self.assertTrue(row['image'].startswith('/media/'))
        self.assertEqual(self.client.request(row['image'])['status'],200)
        html=self.client.request('/admin')['body']
        self.assertNotIn('Тест <script>',html)
        self.assertIn('Тест &lt;script&gt;',html)
        data.update(id=row['id'],store_id='30000000',image_data='')
        self.assertEqual(self.client.post('/admin/apps',data,page='/admin')['status'],400)
        data.update(store_id='20000000',image=row['image'],active='')
        self.assertEqual(self.client.post('/admin/apps',data,page='/admin')['status'],303)
        self.assertEqual(self.s.one('SELECT active FROM apps WHERE id=?',(row['id'],))['active'],0)

    def test_untrusted_photo_urls_and_traversal_rejected(self):
        self.client.login('admin@example.com')
        for image in ('javascript:alert(1)','http://insecure.test/a.png','data:text/html,test'):
            response=self.client.post('/admin/apps',{'name':'app','store_id':'20000000','image':image},page='/admin')
            self.assertEqual(response['status'],400)
        self.assertEqual(self.client.request('/media/../../service.sqlite3')['status'],404)

    def test_secure_cookies_and_throttle(self):
        self.app.secure=True
        response=self.client.request('/login')
        self.assertIn('Secure',response['headers']['Set-Cookie'])
        self.assertIn('HttpOnly',response['headers']['Set-Cookie'])
        for _ in range(10): self.s.throttle('user-limit')
        with self.assertRaises(Problem) as raised: self.s.throttle('user-limit')
        self.assertEqual(raised.exception.status,429)


class ExecutorTests(unittest.TestCase):
    def setup_executor(self, pages=(), email='apple@example.com', error=None):
        client=SimpleNamespace(account_info=lambda:SimpleNamespace(email=email),iter_purchases=lambda **_:iter(pages))
        events=[]
        class Service:
            on_device_install=None
            def devices(self): return [SimpleNamespace(udid='device')]
            def download_by_store_id(self,store_id,acquire_license):
                events.append(('download',store_id,acquire_license))
                return Path('verified.ipa')
            def install(self,udid,path):
                self.on_device_install()
                events.append(('install',udid))
                if error: raise RuntimeError(error)
        return Executor(client,Service(),'apple@example.com','device'),events

    def test_full_history_and_missing_completion(self):
        page=SimpleNamespace(items=[SimpleNamespace(track_id=10000000)],is_last=True,total=1)
        ex,_=self.setup_executor([page])
        result=ex.execute(dict(kind='check',id=1,apple_id='apple@example.com'))
        self.assertEqual(result['store_ids'],['10000000'])
        page.total=2
        self.assertEqual(ex.execute(dict(kind='check',id=1,apple_id='apple@example.com'))['state'],'failed')
        page.total=1;page.is_last=False
        self.assertEqual(ex.execute(dict(kind='check',id=1,apple_id='apple@example.com'))['state'],'failed')

    def test_exact_app_id_and_device_confirmed_before_success(self):
        ex,events=self.setup_executor()
        job=dict(kind='install',id='order',apple_id='apple@example.com',store_id='10000000')
        self.assertEqual(ex.execute(job)['state'],'succeeded')
        self.assertEqual(events,[('download','10000000',False),('install','device')])
        ex,_=self.setup_executor(error='unconfirmed')
        self.assertEqual(ex.execute(job)['state'],'uncertain')
        ex,events=self.setup_executor(email='wrong@example.com')
        self.assertEqual(ex.execute(job)['state'],'failed')
        self.assertEqual(events,[])

    def test_transport_rejects_plaintext_remote_urls_and_spool_has_no_token(self):
        for url in ('http://example.com','https://user:pass@example.com','https://example.com/path'):
            with self.assertRaises(ValueError): Transport(url,'token')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.json'
            write_result(path,'top-secret',{'id':1,'state':'succeeded'})
            self.assertNotIn('top-secret',path.read_text())
            self.assertEqual(json.loads(path.read_text())['worker'],digest('top-secret'))


class IpatoolPathTests(unittest.TestCase):
    def test_frozen_app_finds_bin_beside_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bin').mkdir();tool=root/'bin'/'ipatool.exe';tool.touch()
            with patch('apprestore_core.paths.platform.system',return_value='Windows'), patch('apprestore_core.paths.sys.executable',str(root/'AppRestore.exe')),patch('apprestore_core.paths.sys.frozen',True,create=True),patch('apprestore_core.paths.project_root',return_value=root/'_internal'),patch.dict('os.environ',{'LOCALAPPDATA':'','APPRESTORE_IPATOOL_PATH':''}):
                self.assertEqual(resolve_tool('ipatool'),str(tool))

    def test_explicit_path_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool=Path(tmp)/'custom-ipatool';tool.touch()
            with patch.dict('os.environ',{'APPRESTORE_IPATOOL_PATH':str(tool)}):
                self.assertEqual(resolve_tool('ipatool'),str(tool))
            with patch.dict('os.environ',{'APPRESTORE_IPATOOL_PATH':str(tool)+'-missing'}),patch('apprestore_core.paths.shutil.which',return_value='/another/tool'):
                self.assertIsNone(resolve_tool('ipatool'))


if __name__=='__main__': unittest.main()
