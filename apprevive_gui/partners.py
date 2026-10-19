"""Partner code, immutable attribution and paid-order statistics on both platforms."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from apprevive_gui.workers import run_in_thread
from apprevive_gui.account_bindings import account_email
from apprevive_core.account_credits import account_id, api_call
from apprevive_core.restoration_codes import RestorationCodeError
from apprevive_gui.theme import load_fonts


class PartnerDialog(QDialog):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.account = ''
        self.busy = False
        self.setWindowTitle('AppRevive · Партнёрская программа')
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(500)
        font = self.font()
        font.setFamily(load_fonts())
        self.setFont(font)
        self.setStyleSheet('''QDialog { background: #EBEAE6; color: #121212; }
            QLabel { color: #121212; } QLineEdit { background: white; color: #121212; padding: 8px; border: 1px solid #D6D4CE; border-radius: 6px; }
            QPushButton { background: white; color: #61605C; padding: 8px 12px; border: 1px solid #D6D4CE; border-radius: 6px; }
            QPushButton:disabled { color: #999; }''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        note = QLabel('Поделитесь своим кодом. Приглашённый вводит его до первой покупки.\nПартнёрский код не даёт восстановлений. Условия вознаграждения пока не установлены.')
        note.setWordWrap(True)
        self.program_note = note
        layout.addWidget(note)
        layout.addWidget(QLabel('Ваш партнёрский код'))
        self.code = self.copy_field(layout, 'partnerCode')
        layout.addWidget(QLabel('ID покупателя — передайте администратору при покупке'))
        self.buyer = self.copy_field(layout, 'partnerBuyerId')
        self.stats = QLabel('')
        self.stats.setWordWrap(True)
        layout.addWidget(self.stats)
        self.binding = QLabel('')
        layout.addWidget(self.binding)
        self.referral = QLineEdit()
        self.referral.setObjectName('inviterCode')
        self.referral.setPlaceholderText('Код пригласившего · RVP-…')
        self.referral.setMaxLength(16)
        layout.addWidget(self.referral)
        self.bind_button = QPushButton('Закрепить пригласившего')
        self.bind_button.clicked.connect(self.bind)
        layout.addWidget(self.bind_button)
        self.message = QLabel('')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        row = QHBoxLayout()
        self.refresh_button = QPushButton('Обновить статистику')
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        close = QPushButton('Закрыть')
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()

    def copy_field(self, layout, name):
        row = QHBoxLayout()
        field = QLineEdit()
        field.setObjectName(name)
        field.setReadOnly(True)
        row.addWidget(field)
        copy = QPushButton('Копировать')
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(field.text()))
        row.addWidget(copy)
        layout.addLayout(row)
        return field

    def work(self, action):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.setEnabled(False)
        self.bind_button.setEnabled(False)
        self.message.setText('Загружаем…')
        run_in_thread(self, action, on_finished=self.loaded, on_failed=self.failed)

    def query(self, referral=None):
        if not self.session._acquire_account_change():
            raise RestorationCodeError('Дождитесь завершения текущей операции и повторите.')
        try:
            identity = account_id(account_email(self.session.service.core.tools.ipatool_auth_info()))
            if referral is not None:
                if identity != self.account:
                    raise RestorationCodeError('Apple ID изменился. Обновите статистику перед вводом кода.')
                api_call('bind', dict(account_id=identity, referral_code=referral), namespace='partner')
            return api_call('profile', dict(account_id=identity), namespace='partner')
        finally:
            self.session._tool_lock.release()

    def refresh(self):
        self.work(lambda: self.query())

    def bind(self):
        code = self.referral.text().strip()
        if not code:
            self.message.setText('Введите код пригласившего.')
            return
        self.work(lambda: self.query(code))

    def loaded(self, data):
        self.busy = False
        self.refresh_button.setEnabled(True)
        keys = ('invited', 'paid_buyers', 'paid_orders', 'purchased_codes', 'revenue_kopecks')
        if data.get('status') != 'ok' or any(type(data.get(k)) is not int or data[k] < 0 for k in keys):
            self.failed('Неверный ответ сервера статистики.')
            return
        if 'commission_rate_bps' in data:
            rate = data['commission_rate_bps'] / 100
            self.program_note.setText(f'Пригласивший закрепляется до первой покупки. Вознаграждение по новым заказам: {rate:g}%. Удержание: {data.get("hold_days", 0)} дней. Выплаты подтверждает администратор после фактического перевода.')
        self.account = data['account_id']
        self.code.setText(data['referral_code'])
        self.buyer.setText(self.account)
        self.stats.setText(f"Приглашено: {data['invited']} · Покупателей: {data['paid_buyers']}\n"
                           f"Оплаченных заказов: {data['paid_orders']} · Куплено кодов: {data['purchased_codes']}\n"
                           f"Оплачено приглашёнными: {data['revenue_kopecks'] / 100:.2f} ₽\n"
                           'Возвращённые заказы исключены. Сумма покупок — не ваш заработок.')
        if 'ledger' in data:
            ledger = data['ledger']
            self.stats.setText(self.stats.text() + f"\nДоступно к выплате: {ledger.get('available_kopecks',0)/100:.2f} ₽ · На удержании: {ledger.get('held_kopecks',0)/100:.2f} ₽")
        bound = data.get('invited_by', '')
        self.binding.setText('Вас пригласил: ' + bound if bound else 'Пригласивший не указан. Привязку нельзя изменить.')
        self.referral.setEnabled(not bound)
        self.bind_button.setEnabled(not bound)
        self.message.setText('')

    def failed(self, message):
        self.busy = False
        self.refresh_button.setEnabled(True)
        self.bind_button.setEnabled(bool(self.account))
        self.message.setText(message)

    def reject(self):
        if not self.busy:
            super().reject()
