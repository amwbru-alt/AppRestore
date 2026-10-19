from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication
from apprevive_gui import service_account as gui
from apprevive_core.service_session import set_token


def test_service_dialog_reads_balance_without_saving_credentials(monkeypatch):
    app=QApplication.instance() or QApplication([])
    calls=[]
    def request(path,body=None):
        calls.append((path,body))
        if path=='/v3/auth/login':return {'token':'a'*64}
        if path=='/v3/me':return {'user':{'email':'user@example.test'}}
        if path.startswith('/v3/account?'):return {'credits':3,'installations':2,'history':[],'ledger':{'available_kopecks':1000}}
        if path=='/v3/orders':return {'orders':[],'codes':[{'code':'RV-TEST'}]}
        return {'status':'ok'}
    monkeypatch.setattr(gui,'request',request)
    monkeypatch.setattr(gui,'run_in_thread',lambda owner,action,on_finished,on_failed:on_finished(action()))
    set_token('')
    dialog=gui.ServiceDialog('user@example.test',True)
    dialog.password.setText('A service password')
    dialog.login()
    assert dialog.ready
    assert 'Осталось восстановлений: 3' in dialog.summary.toPlainText()
    assert 'RV-TEST' in dialog.summary.toPlainText()
    assert not dialog.password.text()
    dialog.close();set_token('')


def test_preflight_stops_disconnected_device_before_credit_reservation():
    service=SimpleNamespace(core=SimpleNamespace(tools=SimpleNamespace(list_udids=lambda:[])))
    with pytest.raises(Exception,match='не подключён'):
        gui.preflight(service,{'udid':'missing'})


def test_service_password_is_never_sent_over_public_http(monkeypatch):
    from apprevive_core import service_session
    monkeypatch.setattr(service_session,'api_base_url',lambda:'http://185.173.93.200:3000')
    monkeypatch.setattr(service_session.urllib.request,'urlopen',lambda *a,**k:pytest.fail('password transmitted'))
    with pytest.raises(Exception,match='Пароль не был отправлен'):
        service_session.request('/v3/auth/login',{'email':'user@example.test','password':'secret password'})
