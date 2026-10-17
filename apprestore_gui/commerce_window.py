"""Native service pages inside the original Qt Widgets application."""
from __future__ import annotations

from pathlib import Path
import secrets
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QSizePolicy,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from apprestore_core.ipatool_api import IpatoolClient
from apprestore_core.paths import IPATOOL_MISSING_TEXT, resolve_tool
from appverni.desktop import DesktopLedger
from appverni.store import Problem
from .main_window import MainWindow
from .purchases import gui_runner
from .theme import ACCENT, ACCENT_SOFT, BAD, INK, LINE, MUTED, OK, PANEL
from .workers import run_in_thread

STATUS = {'awaiting_payment':'Ожидает оплаты', 'queued':'В очереди', 'running':'Устанавливается',
          'succeeded':'Установлено', 'failed':'Не установлено', 'uncertain':'Проверьте iPhone'}


def label(text='', *, title=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(True)
    item.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    item.setStyleSheet('border:none;background:transparent;' + ('font-size:20px;font-weight:700;' if title else ''))
    return item


def button(text, callback, *, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName('primary')
    item.clicked.connect(callback)
    return item


def notify(parent, title, text):
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(title)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(str(text))
    dialog.exec()


class ServiceAuthDialog(QDialog):
    """Separate native login and registration pages; never asks for Apple secrets."""
    def __init__(self, ledger: DesktopLedger, parent=None):
        super().__init__(parent)
        self.ledger, self.user = ledger, None
        self.setWindowTitle('АппВерни — аккаунт сервиса')
        self.setMinimumWidth(440)
        self.setObjectName('service_auth_dialog')
        self._owner_setup = ledger.store.one('SELECT 1 FROM users') is None
        self._busy = False
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.addWidget(label('АппВерни', title=True))
        root.addWidget(label('Войдите в сервис. Apple ID подключается отдельно внутри приложения.'))
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.fields = {}
        for key in ('login', 'register'):
            page = QWidget(); layout = QVBoxLayout(page)
            title = 'Создать владельца приложения' if self._owner_setup and key == 'register' else ('Регистрация' if key == 'register' else 'Вход в сервис')
            layout.addWidget(label(title, title=True))
            form = QFormLayout()
            email = QLineEdit(); email.setObjectName('service_' + key + '_email'); email.setMaxLength(254)
            email.setPlaceholderText('name@example.com')
            password = QLineEdit(); password.setEchoMode(QLineEdit.EchoMode.Password); password.setMaxLength(128)
            password.setObjectName('service_' + key + '_password')
            form.addRow('Email', email); form.addRow('Пароль', password)
            repeat = None
            if key == 'register':
                repeat = QLineEdit(); repeat.setEchoMode(QLineEdit.EchoMode.Password); repeat.setMaxLength(128)
                form.addRow('Повторите пароль', repeat)
            layout.addLayout(form)
            if key == 'register': layout.addWidget(label('Пароль — от 12 символов.'))
            submit = button('Создать аккаунт' if key == 'register' else 'Войти', lambda _=False, k=key:self.submit(k), primary=True)
            layout.addWidget(submit)
            if not self._owner_setup:
                switch = button('Уже есть аккаунт? Войти' if key == 'register' else 'Нет аккаунта? Зарегистрироваться', lambda _=False, k=key:self.stack.setCurrentIndex(0 if k == 'register' else 1))
                layout.addWidget(switch)
            password.returnPressed.connect(lambda k=key:self.submit(k))
            self.fields[key] = (email, password, repeat, submit)
            self.stack.addWidget(page)
        self.status = label(); self.status.setObjectName('service_auth_status')
        self.status.setStyleSheet(f'color:{BAD};border:none;')
        root.addWidget(self.status)
        if self._owner_setup: self.stack.setCurrentIndex(1)

    def submit(self, key):
        if self._busy: return
        email, password, repeat, submit = self.fields[key]
        if repeat and repeat.text() != password.text():
            self.status.setText('Пароли не совпадают.'); return
        value, secret = email.text(), password.text()
        self._busy = True
        self.stack.setEnabled(False)
        self.status.setText('Подождите…')
        def work():
            if key == 'register':
                return dict(self.ledger.register(value, secret, owner=self._owner_setup))
            return dict(self.ledger.authenticate(value, secret))
        def done(user):
            for _, p, r, _ in self.fields.values():
                p.clear()
                if r: r.clear()
            self._busy = False; self.user = user; self.accept()
        def failed(message):
            self._busy = False; self.stack.setEnabled(True); self.status.setText(message)
            password.clear()
            if repeat: repeat.clear()
        run_in_thread(self, work, on_finished=done, on_failed=failed)

    def reject(self):
        if not self._busy: super().reject()


class CommerceWindow(MainWindow):
    def __init__(self, service, artwork, ledger, user):
        self.ledger, self.user = ledger, dict(user)
        self._native_ready = False
        self._commerce_busy = False
        self._active_account = None
        self._editing_app = None
        self._app_image = ''
        super().__init__(service, artwork)
        self.setWindowTitle('АппВерни')
        self._native_pages = {'catalog':self._build_catalog(), 'orders':self._build_orders(),
                              'service_profile':self._build_profile(), 'admin':self._build_admin()}
        for key, page in self._native_pages.items():
            self.pages[key] = page; self.stack.addWidget(page)
        # Original phone, Apple ID, diagnostics and settings remain native.
        # Installation actions all enter the service catalog and tariff gate.
        for i in reversed(range(self.sidebar.nav.count())):
            item = self.sidebar.nav.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in ('offloaded','install','library'):
                self.sidebar.nav.takeItem(i)
        for index, (key, text) in enumerate((('catalog','Установить'),('orders','Мои установки'),('service_profile','Аккаунт сервиса'),('admin','Администрирование'))):
            item = QListWidgetItem(text); item.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar.nav.insertItem(index, item)
        self._native_ready = True
        self._update_role()
        self._show_page('catalog')

    @property
    def uid(self): return self.user['id']

    def _update_role(self):
        self.user = dict(self.ledger.user(self.uid))
        for i in range(self.sidebar.nav.count()):
            item = self.sidebar.nav.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == 'admin': item.setHidden(not self.user['admin'])
        self.profile_text.setText(self.user['email'] + ('\nАдминистратор' if self.user['admin'] else '\nПользователь сервиса'))

    def _show_page(self, key):
        if not self._native_ready:
            return super()._show_page(key)
        if key in ('offloaded','install','library'): key = 'catalog'
        if key in self._native_pages:
            if key == 'admin' and not self.user['admin']: return
            self.stack.setCurrentWidget(self.pages[key]); self.sidebar.select(key)
            if key == 'catalog':
                self._render_catalog()
                if self._active_account is None and self._apple_signed_in and not self._commerce_busy:
                    QTimer.singleShot(0, self._verify_history)
            elif key == 'orders': self._render_orders()
            elif key == 'admin': self._render_admin()
            return
        super()._show_page(key)

    def _build_catalog(self):
        page, layout, _ = self._page_shell('Установить приложения')
        intro = label('Приложения из истории вашего Apple ID. Первая успешная установка бесплатно, следующие — 100 ₽.')
        layout.addWidget(intro)
        self.offer = label(); self.offer.setStyleSheet(f'background:{ACCENT_SOFT};border:1px solid {LINE};border-radius:10px;padding:16px;font-size:15px;font-weight:650;')
        layout.addWidget(self.offer)
        actions = QHBoxLayout()
        actions.addWidget(button('Войти в Apple ID', lambda:self._show_page('account'), primary=True))
        self.verify_button = button('Проверить историю Apple ID', lambda:self._verify_history(force=True))
        actions.addWidget(self.verify_button); actions.addStretch(1)
        layout.addLayout(actions)
        self.catalog_note = label('Войдите в Apple ID в приложении, затем проверьте историю.')
        self.catalog_note.setObjectName('catalog_note'); layout.addWidget(self.catalog_note)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.catalog_body = QWidget(); self.catalog_grid = QGridLayout(self.catalog_body)
        self.catalog_grid.setAlignment(Qt.AlignmentFlag.AlignTop); self.catalog_grid.setSpacing(16)
        scroll.setWidget(self.catalog_body); layout.addWidget(scroll, 1)
        layout.addWidget(label('Наличие в истории подтверждает прежнее получение приложения. Apple может больше не выдавать его файл.'))
        return page

    def _client(self):
        binary = resolve_tool('ipatool')
        if not binary: raise Problem(IPATOOL_MISSING_TEXT)
        tools = self.service.core.tools
        return IpatoolClient(binary, keychain_passphrase='', runner=gui_runner(self.service.keychain_passphrase, tools._ipatool_env))

    def _set_busy(self, busy):
        self._commerce_busy = busy
        self.verify_button.setEnabled(not busy)
        self.logout_button.setEnabled(not busy)
        self._auth_login.setEnabled(not busy and self._auth_phase != 'running')
        self._render_catalog()

    def _verify_history(self, *, force=False):
        if self._commerce_busy or self._auth_job is not None: return
        self._set_busy(True)
        self.catalog_note.setText('Проверяем полную историю Apple ID. Это может занять несколько минут…')
        def work():
            return self.ledger.verify(self.uid, self._client(), force=force)
        def done(aid):
            self._active_account = aid
            self._set_busy(False)
            self._render_catalog()
        def failed(message):
            # A prior snapshot is still shown only for its own Apple ID;
            # actual identity is checked again before any install.
            self._set_busy(False); self.catalog_note.setText(message)
        run_in_thread(self, work, on_finished=done, on_failed=failed)

    def _render_catalog(self):
        if not hasattr(self, 'catalog_grid'): return
        while self.catalog_grid.count():
            item = self.catalog_grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        gift = self.ledger.gift_available(self.uid)
        self.offer.setText('Первая установка — в подарок · 0 ₽' if gift else 'Следующая установка — 100 ₽ · приём оплаты скоро появится')
        account = self.ledger.store.one('SELECT * FROM accounts WHERE id=? AND user_id=?', (self._active_account, self.uid)) if self._active_account else None
        known = bool(account and account['verified_at'])
        if account and not self._commerce_busy:
            self.catalog_note.setText(account['apple_id'] + ' · ' + ('История проверена ' + time.strftime('%d.%m.%Y %H:%M', time.localtime(account['verified_at'])) if known else 'Ожидает проверки'))
        apps = self.ledger.catalog(self.uid, self._active_account)
        if not apps:
            self.catalog_grid.addWidget(label('Каталог пока пуст. Администратор может добавить приложения в разделе «Администрирование».'), 0, 0)
        for index, app in enumerate(apps):
            card = QFrame(); card.setObjectName('catalog_card'); card.setStyleSheet(f'QFrame#catalog_card{{background:{PANEL};border:1px solid {LINE};border-radius:10px;}}')
            content = QVBoxLayout(card); content.setContentsMargins(18,18,18,18)
            photo = label('↺'); photo.setFixedSize(64,64)
            if app['image'].startswith('/media/'):
                path = self.ledger.images / Path(app['image']).name
                pix = QPixmap(str(path))
                if not pix.isNull(): photo.setPixmap(pix.scaled(64,64,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            content.addWidget(photo)
            content.addWidget(label(app['name'], title=True))
            content.addWidget(label(app['description']))
            available = known and bool(app['owned'])
            status = label('Есть в истории Apple ID' if available else ('Нет в истории этого Apple ID' if known else 'Сначала проверьте Apple ID'))
            status.setStyleSheet(f'color:{OK if available else MUTED};border:none;'); content.addWidget(status)
            go = button('Установить бесплатно' if gift else 'Установить · 100 ₽', lambda _=False, app_id=app['id']:self._install_catalog(app_id), primary=True)
            go.setObjectName('catalog_install_' + str(app['id']))
            go.setEnabled(available and not self._commerce_busy)
            content.addWidget(go); content.addWidget(label('App Store ID: ' + app['store_id']))
            self.catalog_grid.addWidget(card,index//2,index%2)

    def _install_catalog(self, app_id):
        if self._commerce_busy or self._auth_job is not None: return
        if not self._active_account:
            self.catalog_note.setText('Сначала войдите в Apple ID и проверьте историю.'); return
        if not self._device_udid:
            self.catalog_note.setText('Подключите iPhone кабелем, разблокируйте и нажмите «Доверять».'); return
        uid, aid, udid = self.uid, self._active_account, self._device_udid
        self._set_busy(True); self.catalog_note.setText('Готовим установку. Дождитесь подтверждения на iPhone…')
        def work():
            return self.ledger.install(uid, aid, app_id, self._client(), self.service.core, udid)
        def done(order):
            self._set_busy(False); self._render_orders(); self._show_page('orders')
            if order['state'] == 'awaiting_payment':
                notify(self,'Заказ создан','Стоимость — 100 ₽. Приём оплаты пока не подключён. Установка начнётся после подключения и подтверждения оплаты.')
        def failed(message):
            self._set_busy(False); self.catalog_note.setText(message)
        run_in_thread(self, work, on_finished=done, on_failed=failed)

    def _build_orders(self):
        page, layout, _ = self._page_shell('Мои установки')
        self.order_table = QTableWidget(0,5)
        self.order_table.setObjectName('service_order_table')
        self.order_table.setHorizontalHeaderLabels(['Приложение','Apple ID','Стоимость','Статус','Результат'])
        self.order_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.order_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.order_table,1)
        layout.addWidget(button('Обновить',self._render_orders))
        return page

    def _render_orders(self):
        rows = self.ledger.store.rows('SELECT o.*,a.apple_id FROM orders o JOIN accounts a ON a.id=o.account_id WHERE o.user_id=? ORDER BY o.created DESC,o.id DESC',(self.uid,))
        self.order_table.setRowCount(len(rows))
        for n, row in enumerate(rows):
            values = (row['app_name'],row['apple_id'],'Бесплатно' if not row['price'] else str(row['price']//100)+' ₽',STATUS[row['state']],row['detail'])
            for col,value in enumerate(values): self.order_table.setItem(n,col,QTableWidgetItem(value))

    def _build_profile(self):
        page, layout, _ = self._page_shell('Аккаунт АппВерни')
        self.profile_text = label('',title=True); layout.addWidget(self.profile_text)
        layout.addWidget(label('Пароль сервиса и пароль Apple ID — разные. Вход Apple ID и код 2FA вводятся в разделе «Apple ID».'))
        layout.addWidget(button('Открыть Apple ID', lambda:self._show_page('account'), primary=True))
        self.logout_button = button('Выйти из сервиса', self._logout_service)
        layout.addWidget(self.logout_button); layout.addStretch(1)
        return page

    def _logout_service(self):
        if self._commerce_busy or self._auth_job is not None: return
        self.service.clear_keychain_passphrase()
        self._active_account = None; self._apple_signed_in = False; self._apple_session = 'unknown'
        self.hide()
        dialog = ServiceAuthDialog(self.ledger,self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.close(); return
        self.user = dialog.user; self._update_role()
        self.catalog_note.setText('Войдите в Apple ID и проверьте историю.')
        self._show_page('catalog'); self.show()

    def _build_admin(self):
        page, layout, _ = self._page_shell('Администрирование')
        tabs = QTabWidget(); layout.addWidget(tabs)
        editor = QWidget(); form = QFormLayout(editor)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.admin_apps = QComboBox(); self.admin_apps.setObjectName('admin_app_picker')
        self.admin_apps.currentIndexChanged.connect(self._edit_app)
        form.addRow('Карточка',self.admin_apps)
        self.app_name = QLineEdit(); self.app_name.setMaxLength(100); self.app_name.setObjectName('admin_app_name')
        self.app_store_id = QLineEdit(); self.app_store_id.setMaxLength(12); self.app_store_id.setObjectName('admin_store_id')
        self.app_description = QTextEdit(); self.app_description.setAcceptRichText(False); self.app_description.setMaximumHeight(100)
        self.app_active = QCheckBox('Показывать в каталоге'); self.app_active.setChecked(True)
        self.photo_text = label('Фото не выбрано')
        form.addRow('Название',self.app_name); form.addRow('App Store ID',self.app_store_id)
        form.addRow('Описание',self.app_description); form.addRow(self.app_active)
        form.addRow('Фото PNG/JPEG',button('Выбрать фото',self._choose_photo)); form.addRow(self.photo_text)
        form.addRow(button('Сохранить приложение',self._save_app,primary=True))
        self.admin_status = label(); form.addRow(self.admin_status)
        tabs.addTab(editor,'Приложения')
        self.users_table = QTableWidget(0,3); self.users_table.setHorizontalHeaderLabels(['Пользователь','Роль','Зарегистрирован'])
        self.admin_orders = QTableWidget(0,5); self.admin_orders.setHorizontalHeaderLabels(['Заказ','Приложение','Пользователь','Стоимость','Статус'])
        for table in (self.users_table,self.admin_orders):
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabs.addTab(self.users_table,'Пользователи')
        orders = QWidget(); box = QVBoxLayout(orders); box.addWidget(self.admin_orders)
        box.addWidget(button('Подтвердить результат после проверки iPhone',self._resolve_selected))
        tabs.addTab(orders,'Заказы')
        layout.addWidget(button('Обновить данные',self._render_admin))
        return page

    def _render_admin(self):
        self.ledger.admin(self.uid)
        self.admin_apps.blockSignals(True); self.admin_apps.clear(); self.admin_apps.addItem('Новое приложение',None)
        for app in self.ledger.store.rows('SELECT * FROM apps ORDER BY name'):
            self.admin_apps.addItem(app['name'] + ('' if app['active'] else ' · скрыто'),app['id'])
        self.admin_apps.blockSignals(False); self._edit_app()
        users = self.ledger.store.rows('SELECT * FROM users ORDER BY id DESC')
        self.users_table.setRowCount(len(users))
        for i,user in enumerate(users):
            for c,value in enumerate((user['email'],'Администратор' if user['admin'] else 'Пользователь',time.strftime('%d.%m.%Y',time.localtime(user['created'])))):
                self.users_table.setItem(i,c,QTableWidgetItem(value))
        orders = self.ledger.store.rows('SELECT o.*,u.email FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.created DESC,o.id DESC LIMIT 500')
        self.admin_orders.setRowCount(len(orders))
        for i,order in enumerate(orders):
            for c,value in enumerate((order['id'],order['app_name'],order['email'],str(order['price']//100)+' ₽',STATUS[order['state']])):
                self.admin_orders.setItem(i,c,QTableWidgetItem(value))

    def _edit_app(self, *_):
        aid = self.admin_apps.currentData()
        self._editing_app = aid
        row = self.ledger.store.one('SELECT * FROM apps WHERE id=?',(aid,)) if aid else None
        self.app_name.setText(row['name'] if row else '')
        self.app_store_id.setText(row['store_id'] if row else ''); self.app_store_id.setReadOnly(bool(row))
        self.app_description.setPlainText(row['description'] if row else '')
        self.app_active.setChecked(bool(row['active']) if row else True)
        self._app_image = row['image'] if row else ''
        self.photo_text.setText('Фото сохранено' if self._app_image else 'Фото не выбрано')

    def _choose_photo(self):
        self.ledger.admin(self.uid)
        path,_ = QFileDialog.getOpenFileName(self,'Фото приложения','','Фото (*.png *.jpg *.jpeg)')
        if not path: return
        if Path(path).stat().st_size > 2_000_000:
            self.admin_status.setText('Фото должно быть не больше 2 МБ.'); return
        reader = QImageReader(path)
        size = reader.size()
        if bytes(reader.format()) not in (b'png', b'jpeg', b'jpg') or size.width() <= 0 or size.height() <= 0 or size.width()*size.height() > 16_000_000:
            self.admin_status.setText('Выберите PNG/JPEG до 16 мегапикселей.'); return
        image = reader.read()
        if image.isNull():
            self.admin_status.setText('Не удалось прочитать фото PNG/JPEG.'); return
        name = secrets.token_hex(20) + '.png'
        target = self.ledger.images / name
        if not image.scaled(512,512,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation).save(str(target),'PNG'):
            self.admin_status.setText('Не удалось сохранить фото.'); return
        target.chmod(0o600)
        self._app_image = '/media/' + name; self.photo_text.setText(Path(path).name)

    def _save_app(self):
        try:
            self.ledger.save_app(self.uid,app_id=self._editing_app,name=self.app_name.text(),store_id=self.app_store_id.text(),
                                 description=self.app_description.toPlainText(),image=self._app_image,active=self.app_active.isChecked())
        except Problem as exc:
            self.admin_status.setText(str(exc)); return
        self._render_admin(); self.admin_status.setText('Приложение сохранено.'); self._render_catalog()

    def _resolve_selected(self):
        self.ledger.admin(self.uid)
        row = self.admin_orders.currentRow()
        if row < 0: return
        oid = self.admin_orders.item(row,0).text()
        state,ok = QInputDialog.getItem(self,'Проверка iPhone','Результат:', ['Приложение установлено','Приложение не установлено'],0,False)
        if not ok: return
        reason,ok = QInputDialog.getText(self,'Основание проверки','Опишите проверку устройства (от 10 символов):')
        if not ok: return
        try:
            self.ledger.resolve_order(self.uid,oid,'succeeded' if state == 'Приложение установлено' else 'failed',reason)
        except Problem as exc:
            notify(self,'Проверка заказа',exc); return
        self._render_admin(); self._render_orders(); self._render_catalog()

    # Keep the original native Apple sign-in / 2FA / secure keychain driver.
    def _login(self):
        if self._commerce_busy: return
        self._active_account = None
        super()._login()

    def _on_auth_done(self, result):
        super()._on_auth_done(result)
        if getattr(result,'ok',False) and self._native_ready:
            QTimer.singleShot(0,self._verify_history)

    def _revoke(self):
        if self._commerce_busy: return
        self._active_account = None
        super()._revoke(); self._render_catalog()

    def check_updates(self):
        notify(self,'Обновление АппВерни','Используйте сборки и инструкцию обновления АппВерни. Обновление исходного AppRestore не содержит разделов этого сервиса.')

    def _restore_selected_offloaded(self): self._show_page('catalog')
    def _install_selected_missing(self): self._show_page('catalog')
    def _pick_ipa(self): self._show_page('catalog')
    def _start_offloaded_restore(self,*args,**kwargs): self._show_page('catalog')

    def closeEvent(self,event):
        if self._commerce_busy:
            event.ignore(); notify(self,'Операция выполняется','Дождитесь завершения проверки или установки перед закрытием приложения.'); return
        if self._auth_job is not None:
            self._auth_job.cancel()
            if not self._auth_job.wait(3000):
                event.ignore()
                return
        super().closeEvent(event)
