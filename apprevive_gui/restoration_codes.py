"""Native promo dialog shared by the Widgets and both Quick windows."""
from __future__ import annotations

import threading
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from apprevive_core.paths import data_dir
from apprevive_core.restoration_codes import RestorationAccess, RestorationCredits, TELEGRAM_URL
from apprevive_gui.theme import load_fonts
from apprevive_gui.workers import run_in_thread


class PromoDialog(QDialog):
    def __init__(self, credits: RestorationCredits, parent=None) -> None:
        super().__init__(parent)
        self.credits = credits
        self._checking = False
        self.setObjectName("restorationCodeDialog")
        self.setWindowTitle("AppRevive · Код восстановления")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(540)
        font = self.font()
        font.setFamily(load_fonts())
        font.setPixelSize(14)
        self.setFont(font)
        self.setStyleSheet("""
            QDialog { background: #EBEAE6; color: #121212; }
            QLabel { color: #121212; background: transparent; }
            QLabel#promoTitle { font-size: 24px; font-weight: 600; }
            QLabel#promoError { color: #A04824; }
            QLineEdit { background: white; color: #121212; border: 1px solid #D6D4CE;
                border-radius: 8px; padding: 12px; selection-background-color: #B35128; }
            QLineEdit:focus { border-color: #B35128; }
            QPushButton { background: white; color: #61605C; border: 1px solid #D6D4CE;
                border-radius: 8px; padding: 10px 18px; }
            QPushButton#promoActivate { background: #B35128; color: white; border: none; }
            QPushButton#promoActivate:hover { background: #A34A24; }
            QPushButton:disabled { background: #D9D7D1; color: #77756F; }
            QPushButton#promoTelegram { color: #B35128; background: transparent; border: none; padding-left: 0; text-align: left; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(16)
        title = QLabel("Введите код")
        title.setObjectName("promoTitle")
        layout.addWidget(title)
        description = QLabel("Бесплатное восстановление использовано.\nОдин код даёт ещё одно восстановление одного приложения.\nПри ошибке установки восстановление не списывается.")
        description.setWordWrap(True)
        layout.addWidget(description)
        telegram = QPushButton("Получить код в Telegram · @llifegoldll")
        telegram.setObjectName("promoTelegram")
        telegram.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TELEGRAM_URL)))
        layout.addWidget(telegram)
        buy = QPushButton("Купить код онлайн / открыть кабинет")
        def open_service():
            from apprevive_gui.service_account import ServiceDialog
            self._service_dialog = ServiceDialog(getattr(self.credits, 'email', ''))
            self._service_dialog.show()
        buy.clicked.connect(open_service)
        layout.addWidget(buy)
        self.code = QLineEdit()
        self.code.setObjectName("restorationCodeInput")
        self.code.setMaxLength(256)
        self.code.setPlaceholderText("Код восстановления")
        self.code.setAccessibleName("Код восстановления")
        layout.addWidget(self.code)
        self.message = QLabel("")
        self.message.setObjectName("promoError")
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(40)
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        buttons.addStretch()
        self.activate = QPushButton("Активировать код")
        self.activate.setObjectName("promoActivate")
        self.activate.setDefault(True)
        self.activate.clicked.connect(self._activate)
        self.code.returnPressed.connect(self._activate)
        buttons.addWidget(self.activate)
        layout.addLayout(buttons)
        self.code.setFocus()

    def _activate(self) -> None:
        if self._checking:
            return
        code = self.code.text().strip()
        if not code:
            self.message.setText("Введите код.")
            self.code.setFocus()
            return
        self._checking = True
        self.activate.setEnabled(False)
        self.code.setEnabled(False)
        self.message.setText("Проверяем код…")
        run_in_thread(self, lambda: self.credits.redeem(code), on_finished=self._accepted, on_failed=self._failed)

    def _accepted(self, _remaining: int) -> None:
        self._checking = False
        self.accept()

    def _failed(self, message: str) -> None:
        self._checking = False
        self.activate.setEnabled(True)
        self.code.setEnabled(True)
        self.message.setText(message)
        self.code.setFocus()
        self.code.selectAll()

    def reject(self) -> None:
        # A request already sent may redeem the code: wait for its result so
        # closing cannot silently spend a code or start an unexpected install.
        if not self._checking:
            super().reject()


class PromoController(QObject):
    requested = Signal(object)
    changed = Signal()

    def __init__(self, credits: RestorationCredits, parent=None) -> None:
        super().__init__(parent)
        self.credits = credits
        self.dialog = None
        self._waiters = []
        self._closed = threading.Event()
        self.requested.connect(self._show, Qt.ConnectionType.QueuedConnection)
        QApplication.instance().aboutToQuit.connect(self.close)

    def request_code(self) -> bool:
        if self._closed.is_set():
            return False
        # Installation runs in a worker; never block the GUI event loop.
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError("Восстановление должно выполняться в фоновом потоке.")
        request = {"event": threading.Event(), "accepted": False}
        self.requested.emit(request)
        while not request["event"].wait(0.2):
            if self._closed.is_set():
                return False
        return bool(request["accepted"])

    @Slot(object)
    def _show(self, request) -> None:
        if self._closed.is_set():
            request["event"].set()
            return
        self._waiters.append(request)
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.dialog = PromoDialog(self.credits, QApplication.activeWindow())
        self.dialog.finished.connect(self._finish)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    @Slot(int)
    def _finish(self, result: int) -> None:
        dialog, self.dialog = self.dialog, None
        waiters, self._waiters = self._waiters, []
        for request in waiters:
            request["accepted"] = result == QDialog.DialogCode.Accepted
            request["event"].set()
        if dialog is not None:
            dialog.deleteLater()
        self.changed.emit()

    def notify(self) -> None:
        if not self._closed.is_set():
            self.changed.emit()

    @Slot()
    def close(self) -> None:
        self._closed.set()
        for request in self._waiters:
            request["event"].set()
        self._waiters.clear()


def enable_restoration_codes(service, parent=None) -> PromoController:
    from apprevive_core.account_credits import AccountCredits, AccountAccess
    from apprevive_gui.account_bindings import account_email

    def verified_email():
        # Read the active authenticated ipatool session, not editable UI text.
        return account_email(service.core.tools.ipatool_auth_info())

    from apprevive_gui.service_account import ServiceController, preflight
    service_controller = ServiceController(parent)
    service.service_account_controller = service_controller
    controller = PromoController(AccountCredits(data_dir() / "server-operations.sqlite3", verified_email, authenticate=service_controller.authenticate), parent)
    access = AccountAccess(controller.credits, controller.request_code, controller.notify,
                           review=service_controller.review, preflight=lambda details: preflight(service, details))
    service.restoration_access = access
    service.core.restoration_access = access
    return controller
