import threading
import pytest

pytest.importorskip('PySide6')
from apprevive_core.restoration_codes import RestorationAccess, RestorationCredits
from apprevive_gui.restoration_codes import PromoDialog, PromoController


def test_dialog_rejects_missing_code_then_redeems_in_background(qtbot, tmp_path):
    network_threads = []
    def activate(code, token, request_id):
        network_threads.append(threading.get_ident())
        if code != 'GOOD':
            from apprevive_core.restoration_codes import RestorationCodeError
            raise RestorationCodeError('Код не найден или уже использован.')
    credits = RestorationCredits(tmp_path / 'credits.sqlite3', activate=activate)
    dialog = PromoDialog(credits)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.code.setText('BAD')
    dialog._activate()
    qtbot.waitUntil(lambda: not dialog._checking)
    assert dialog.message.text() == 'Код не найден или уже использован.'
    assert credits.remaining == 1
    dialog.code.setText('GOOD')
    with qtbot.waitSignal(dialog.accepted):
        dialog._activate()
    assert credits.remaining == 2
    assert all(t != threading.get_ident() for t in network_threads)


def test_worker_waits_for_code_and_continues_original_restore(qtbot, tmp_path):
    store = RestorationCredits(tmp_path / 'credits.sqlite3', activate=lambda *args: None)
    controller = PromoController(store)
    access = RestorationAccess(store, controller.request_code)
    access.run(lambda: None)  # initial gift
    finished = threading.Event()
    installed = []
    def worker():
        try:
            access.run(lambda: installed.append('same app'))
        finally:
            finished.set()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    qtbot.waitUntil(lambda: controller.dialog is not None)
    assert not installed
    dialog = controller.dialog
    qtbot.addWidget(dialog)
    dialog.code.setText('NEXT')
    dialog._activate()
    qtbot.waitUntil(finished.is_set)
    assert installed == ['same app']
    assert store.remaining == 0
    controller.close()
    thread.join(1)


def test_cancel_does_not_install_and_shutdown_unblocks_waiter(qtbot, tmp_path):
    store = RestorationCredits(tmp_path / 'credits.sqlite3')
    controller = PromoController(store)
    result = []
    thread = threading.Thread(target=lambda: result.append(controller.request_code()), daemon=True)
    thread.start()
    qtbot.waitUntil(lambda: controller.dialog is not None)
    qtbot.addWidget(controller.dialog)
    controller.dialog.reject()
    qtbot.waitUntil(lambda: bool(result))
    assert result == [False]
    assert store.remaining == 1
    thread.join(1)
    controller.close()
    assert not controller.request_code()
