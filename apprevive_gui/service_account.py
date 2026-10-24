"""AppRevive login, linked Apple IDs, balances and pre-install review."""
import threading
from PySide6.QtCore import QObject, Signal, Slot, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QSpinBox
from apprevive_core.api_config import api_base_url
from apprevive_core.account_credits import account_id
from apprevive_core.service_session import request, token, set_token
from apprevive_core.restoration_codes import RestorationCodeError
from apprevive_gui.workers import run_in_thread
from apprevive_gui.theme import load_fonts

STYLE='''QDialog {background:#EBEAE6;color:#121212;} QLabel {color:#121212;} QLineEdit,QPlainTextEdit,QSpinBox {background:white;color:#121212;border:1px solid #D6D4CE;border-radius:6px;padding:8px;} QPushButton {background:white;color:#61605C;border:1px solid #D6D4CE;border-radius:6px;padding:9px 14px;} QPushButton:disabled {color:#999;}'''
class ServiceDialog(QDialog):
    def __init__(self, email='', require_access=False):
        super().__init__()
        self.apple_email=email; self.require_access=require_access; self.busy=False
        self.setWindowTitle('AppRevive · Аккаунт сервиса')
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(580,650)
        font=self.font();font.setFamily(load_fonts());self.setFont(font);self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,24,24,24);layout.setSpacing(10)
        title=QLabel('Вход в AppRevive — отдельно от Apple ID.\nНе используйте здесь пароль Apple.');title.setWordWrap(True);layout.addWidget(title)
        if api_base_url().startswith('http://'):
            warning=QLabel('Временный режим HTTP: пароль AppRevive и сессия передаются без шифрования.');warning.setWordWrap(True);layout.addWidget(warning)
        self.email=QLineEdit();self.email.setPlaceholderText('Почта аккаунта AppRevive');self.email.setText(email);layout.addWidget(self.email)
        self.password=QLineEdit();self.password.setEchoMode(QLineEdit.EchoMode.Password);self.password.setPlaceholderText('Пароль AppRevive · минимум 12 символов');layout.addWidget(self.password)
        row=QHBoxLayout();layout.addLayout(row)
        login=QPushButton('Войти');login.clicked.connect(self.login);row.addWidget(login)
        signup=QPushButton('Регистрация');signup.clicked.connect(self.register);row.addWidget(signup)
        browser=QPushButton('Кабинет в браузере');browser.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(api_base_url()+'/account')));row.addWidget(browser)
        self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.summary=QPlainTextEdit();self.summary.setReadOnly(True);layout.addWidget(self.summary)
        row=QHBoxLayout();layout.addLayout(row)
        link=QPushButton('Подтвердить почту Apple ID');link.clicked.connect(self.link);link.setEnabled(bool(email));row.addWidget(link)
        refresh=QPushButton('Проверить / обновить');refresh.clicked.connect(self.refresh);row.addWidget(refresh)
        pay=QHBoxLayout();layout.addLayout(pay);self.quantity=QSpinBox();self.quantity.setRange(1,100);pay.addWidget(self.quantity)
        buy=QPushButton('Купить коды · 100 ₽ за код');buy.clicked.connect(self.buy);pay.addWidget(buy)
        row=QHBoxLayout();layout.addLayout(row)
        logout=QPushButton('Выйти из AppRevive');logout.clicked.connect(self.logout);row.addWidget(logout)
        self.continue_button=QPushButton('Продолжить' if require_access else 'Закрыть');self.continue_button.clicked.connect(self.accept_checked);row.addWidget(self.continue_button)
        self.ready=False;self.checkout_request=None
        if token(): self.refresh()
    def work(self, action, success):
        if self.busy:return
        self.busy=True;self.status.setText('Запрос к сервису…')
        def done(value):self.busy=False;success(value)
        def failed(message):self.busy=False;self.status.setText(message)
        run_in_thread(self,action,on_finished=done,on_failed=failed)
    def login(self):
        body=dict(email=self.email.text().strip(),password=self.password.text())
        def action():
            result=request('/v3/auth/login',body);set_token(result['token']);return result
        def done(_):self.password.clear();self.status.setText('Вход выполнен.');self.refresh()
        self.work(action,done)
    def register(self):
        body=dict(email=self.email.text().strip(),password=self.password.text())
        def done(_):self.password.clear();self.status.setText('Аккаунт создан. Подтверждать почту не нужно. Нажмите «Войти» и введите свой пароль AppRevive.')
        self.work(lambda:request('/v3/auth/register',body),done)
    def link(self):
        self.work(lambda:request('/v3/auth/apple',dict(email=self.apple_email)),lambda _:self.status.setText('На почту Apple ID отправлена ссылка. Откройте её, войдите в тот же аккаунт AppRevive и подтвердите привязку. Затем нажмите «Проверить».'))
    def refresh(self):
        def action():
            me=request('/v3/me')
            account=request('/v3/account?account_id='+account_id(self.apple_email)) if self.apple_email else None
            orders=request('/v3/orders')
            for order in [o for o in orders['orders'] if o['state']=='pending'][:3]:
                try:request('/v3/checkout/sync',{'checkout_id':order['checkout_id']})
                except RestorationCodeError:pass
            orders=request('/v3/orders')
            return me,account,orders
        def done(value):
            me,data,orders=value;self.ready=True
            lines=['Аккаунт AppRevive: '+me['user']['email']]
            if data:
                lines += ['Apple ID: '+self.apple_email,f"Осталось восстановлений: {data['credits']}",f"Успешных установок: {data['installations']}",'','Последние восстановления:']
                names={'reserved':'Ожидает подтверждения','completed':'Завершено','failed':'Ошибка · попытка возвращена'}
                lines += [f"{names.get(r['state'],r['state'])} · {r.get('name') or r.get('store_id') or r['request_id']}" for r in data['history'][:20]]
                ledger=data.get('ledger',{});lines += ['',f"Партнёрский баланс: {ledger.get('available_kopecks',0)/100:.2f} ₽",f"На удержании: {ledger.get('held_kopecks',0)/100:.2f} ₽"]
            lines += ['','Купленные неиспользованные коды:']+[c['code'] for c in orders['codes']]
            self.summary.setPlainText('\n'.join(lines));self.status.setText('Обновлено. Для покупки и восстановления используется выбранный Apple ID.')
        self.ready=False;self.work(action,done)
    def buy(self):
        if self.busy:return
        if not self.apple_email:self.status.setText('Сначала войдите в Apple ID в приложении.');return
        import uuid
        quantity=self.quantity.value();aid=account_id(self.apple_email)
        if not self.checkout_request or self.checkout_request['quantity']!=quantity:self.checkout_request=dict(account_id=aid,quantity=quantity,request_id=uuid.uuid4().hex)
        def done(data):
            if data.get('confirmation_url'):QDesktopServices.openUrl(QUrl(data['confirmation_url']));self.status.setText('Завершите оплату в браузере. Затем обновите заказы в кабинете или приложении.')
            else:self.checkout_request=None;self.refresh()
        payload=dict(self.checkout_request)
        self.work(lambda:request('/v3/checkout',payload),done)
    def logout(self):
        def action():
            try:request('/v3/auth/logout',{})
            finally:set_token('')
        def done(_):self.ready=False;self.summary.clear();self.status.setText('Вы вышли из аккаунта AppRevive.')
        self.work(action,done)
    def accept_checked(self):
        if self.busy:return
        if self.require_access and not self.ready:self.status.setText('Сначала войдите и проверьте привязку Apple ID.');return
        self.accept()
    def reject(self):
        if not self.busy:super().reject()

class ReviewDialog(QDialog):
    def __init__(self,data):
        super().__init__();self.setWindowTitle('AppRevive · Перед установкой');self.setStyleSheet(STYLE);self.setMinimumWidth(510)
        self.setWindowModality(Qt.WindowModality.ApplicationModal);layout=QVBoxLayout(self)
        info=QLabel('Приложение: '+str(data['details'].get('name') or 'Выбранное приложение')+'\nApple ID: '+data['email']);info.setWordWrap(True);layout.addWidget(info)
        checks=QLabel('\n'.join(data.get('checks',[])));checks.setWordWrap(True);layout.addWidget(checks)
        count=data['balance']['credits'];price=QLabel(f'Остаток: {count} восстановлений.\n'+('Будет использовано 1 восстановление из баланса.' if count else 'Нужен код восстановления. Стоимость нового кода — 100 ₽.')+'\nПри подтверждённой ошибке попытка возвращается.');price.setWordWrap(True);layout.addWidget(price)
        row=QHBoxLayout();layout.addLayout(row);cancel=QPushButton('Отмена');cancel.clicked.connect(self.reject);row.addWidget(cancel);yes=QPushButton('Продолжить установку');yes.clicked.connect(self.accept);row.addWidget(yes)

class ServiceController(QObject):
    requested=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.requested.connect(self.show_request,Qt.ConnectionType.QueuedConnection);self.closed=threading.Event();self.waiters=[];self.dialogs=[]
        QApplication.instance().aboutToQuit.connect(self.close)
    def wait(self,kind,payload):
        if self.closed.is_set():return False
        if threading.current_thread() is threading.main_thread():raise RuntimeError('Проверка выполняется в фоновом потоке.')
        item=dict(kind=kind,payload=payload,event=threading.Event(),accepted=False);self.requested.emit(item)
        while not item['event'].wait(.2):
            if self.closed.is_set():return False
        return item['accepted']
    def authenticate(self,email):return self.wait('login',email)
    def review(self,data):return self.wait('review',data)
    @Slot(object)
    def show_request(self,item):
        if self.closed.is_set():item['event'].set();return
        self.waiters.append(item);dialog=ServiceDialog(item['payload'],True) if item['kind']=='login' else ReviewDialog(item['payload']);self.dialogs.append(dialog)
        def finish(result):
            item['accepted']=result==QDialog.DialogCode.Accepted;item['event'].set()
            if item in self.waiters:self.waiters.remove(item)
            if dialog in self.dialogs:self.dialogs.remove(dialog)
            dialog.deleteLater()
        dialog.finished.connect(finish);dialog.show()
    def open_profile(self,email=''):
        dialog=ServiceDialog(email);self.dialogs.append(dialog)
        def finish(_):
            if dialog in self.dialogs:self.dialogs.remove(dialog)
            dialog.deleteLater()
        dialog.finished.connect(finish);dialog.show()
    @Slot()
    def close(self):
        self.closed.set()
        for item in self.waiters:item['event'].set()
        self.waiters.clear();set_token('')


def preflight(service, details):
    tools=service.core.tools;udid=details.get('udid','')
    if not udid or udid not in tools.list_udids():raise RestorationCodeError('Выбранный iPhone не подключён. Подключите его до начала установки.')
    checks=tools.doctor();required={'Python runtime','pymobiledevice3','ipatool','Apple Mobile Device Service','Apple usbmux (127.0.0.1:27015)'}
    missing=[c.name for c in checks if c.name in required and not c.ok]
    if missing:raise RestorationCodeError('Не готовы компоненты: '+', '.join(missing))
    from apprevive_gui.ui4b.space import query_device_space,format_size
    space=query_device_space(tools,udid,timeout=15)
    rows=['✓ iPhone виден по USB','✓ Компоненты установки найдены']
    rows.append('Свободно на устройстве: '+format_size(space.free_bytes) if space.free_bytes is not None else 'Свободное место пока неизвестно. Проверка продолжится при установке.')
    rows.append('Доступность загрузки и совместимость окончательно проверяются при установке.')
    return rows
