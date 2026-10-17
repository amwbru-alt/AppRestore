from pathlib import Path
from types import SimpleNamespace
import time
from unittest.mock import patch

import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from apprestore_gui.commerce_window import CommerceWindow, ServiceAuthDialog
from apprestore_gui.icons_cache import ArtworkCache
from apprestore_gui.service_adapter import GuiService
from apprestore_gui.auth_pty import AuthResult
from apprestore_gui.theme import STYLESHEET
from appverni.desktop import DesktopLedger


@pytest.fixture(scope='module')
def application():
    app=QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    return app


@pytest.fixture
def native(application,tmp_path):
    ledger=DesktopLedger(tmp_path/'db.sqlite3')
    owner=ledger.register('owner@example.com','long-password-123',owner=True)
    with patch('apprestore_gui.main_window.MainWindow.refresh_device'),patch('apprestore_gui.main_window.MainWindow._watch_devices'):
        win=CommerceWindow(GuiService(demo_mode=True),ArtworkCache(),ledger,owner)
        yield win,ledger,owner
        win._commerce_busy=False;win._auth_job=None;win.close()
        application.processEvents()


def pump_until(application,predicate):
    deadline=time.monotonic()+3
    while not predicate() and time.monotonic()<deadline:
        application.processEvents()
    assert predicate()


def test_native_login_and_registration_are_separate(application,tmp_path):
    ledger=DesktopLedger(tmp_path/'db.sqlite3')
    dialog=ServiceAuthDialog(ledger)
    assert dialog.stack.currentIndex()==1
    assert dialog._owner_setup
    email,password,repeat,submit=dialog.fields['register']
    email.setText('owner@example.com');password.setText('long-password-123');repeat.setText('long-password-123')
    dialog.submit('register')
    pump_until(application,lambda:dialog.user is not None)
    assert dialog.user['admin']
    assert password.text()=='' and repeat.text()==''
    dialog.close()
    login=ServiceAuthDialog(ledger)
    assert login.stack.count()==2 and login.stack.currentIndex()==0
    assert not login._owner_setup
    login.close()


def test_original_native_apple_fields_and_2fa_preserved(native):
    win,_,_=native
    win._show_page('account')
    from PySide6.QtWidgets import QLineEdit
    assert win.pages['account'].findChild(QLineEdit,'auth_password') is not None
    code=win.pages['account'].findChild(QLineEdit,'auth_code')
    win._on_auth_need('code')
    assert win._auth_phase=='need_code'
    assert win._auth_login.text()=='Отправить код'
    assert not code.isHidden()
    win._auth_phase='idle'


def test_catalog_admin_and_paid_installation_gate(native,application):
    win,ledger,owner=native
    appid=ledger.save_app(owner['id'],name='Пример',store_id='10000000')
    win._render_catalog();application.processEvents()
    install=win.pages['catalog'].findChild(QPushButton,'catalog_install_'+str(appid))
    assert not install.isEnabled()
    win._show_page('admin')
    assert win.stack.currentWidget() is win.pages['admin']
    win._show_page('offloaded')
    assert win.stack.currentWidget() is win.pages['catalog']
    win._install_selected_missing()
    assert win.stack.currentWidget() is win.pages['catalog']


def test_regular_user_has_no_admin_page(native):
    win,ledger,_=native
    user=ledger.register('user@example.com','long-password-123')
    win.user=dict(user);win._update_role();win._show_page('catalog')
    before=win.stack.currentWidget()
    win._show_page('admin')
    assert win.stack.currentWidget() is before
    for i in range(win.sidebar.nav.count()):
        item=win.sidebar.nav.item(i)
        if item.text()=='Администрирование':assert item.isHidden()


def test_native_admin_saves_card_and_login_success_schedules_check(native,application):
    win,ledger,_=native
    win._show_page('admin');win.app_name.setText('Моё приложение');win.app_store_id.setText('20000000')
    win._save_app()
    assert ledger.store.one('SELECT name FROM apps')['name']=='Моё приложение'
    with patch.object(win,'_verify_history') as verify,patch('apprestore_gui.main_window.MainWindow._on_auth_done'):
        win._on_auth_done(AuthResult(True,'ok'))
        pump_until(application,lambda:verify.called)


def test_admin_photo_is_copied_and_shown_in_native_catalog(native,application,tmp_path):
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtWidgets import QLabel
    win,ledger,owner=native
    win._show_page('admin')
    photo=tmp_path/'photo.png'
    image=QImage(48,48,QImage.Format.Format_RGB32);image.fill(QColor('#098262'));assert image.save(str(photo))
    with patch('apprestore_gui.commerce_window.QFileDialog.getOpenFileName',return_value=(str(photo),'PNG')):
        win._choose_photo()
    assert win._app_image.startswith('/media/')
    assert (ledger.images/Path(win._app_image).name).is_file()
    win.app_name.setText('С фото');win.app_store_id.setText('30000000');win._save_app()
    card=ledger.store.one('SELECT * FROM apps')
    assert card['image'].startswith('/media/')
    win._show_page('catalog');application.processEvents()
    assert win.pages['catalog'].findChild(QPushButton,'catalog_install_'+str(card['id'])) is not None
