"""The product opens account purchases, never a phone-derived substitute."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from apprestore_gui.ui4b.fake_data import FakeSource
from apprestore_gui.ui4b.qt_bridge import Restore4b
from apprestore_gui.ui4b.history import history_view, FAILED


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def source_with_purchases():
    source = FakeSource("missing")  # device has its own, different list
    source.connected = False
    source.signed_in = True
    source.auth_phase = "in"
    source.account_email = "owner@example.com"
    source.purchase_rows = lambda: [
        {"trackId": "492224193", "name": "Куплено на старом iPhone", "date": "2021-01-01"},
        {"trackId": "111222333", "name": "Никогда не было на этом телефоне", "date": "2020-01-01"},
    ]
    source.session = SimpleNamespace(purchasesBusy=False, purchasesNote="", loadPurchases=Mock())
    return source


def test_product_opens_all_account_purchases_without_a_phone(qapp):
    source = source_with_purchases()
    controller = Restore4b(source, onboarded=False, purchase_first=True)
    assert controller.screen == "home"  # no mandatory connect-phone onboarding
    assert controller.history["open"]
    assert {r["storeId"] for r in controller.history["rows"]} == {"492224193", "111222333"}
    assert controller.history["scope"].endswith("owner@example.com")
    assert not controller.history["canRestore"]
    assert all(not r["enabled"] for r in controller.history["rows"])
    source.session.loadPurchases.assert_called_once()
    controller.refreshHistory()
    assert source.session.loadPurchases.call_count == 2


def test_close_history_keeps_purchases_as_primary_action(qapp):
    source = source_with_purchases()
    controller = Restore4b(source, purchase_first=True)
    controller.closeHistory()
    assert controller.home["state"] == "purchases"
    assert controller.home["cta"] == "Открыть покупки"
    controller.primaryAction()
    assert controller.history["open"]
    controller.closeHistory()
    controller.link("Приложения на телефоне")
    assert controller.home["state"] != "purchases"
    controller.link("Покупки Apple ID")
    assert controller.history["open"]


def test_install_requires_device_but_keeps_history_and_uses_selected_purchase(qapp, monkeypatch):
    source = source_with_purchases()
    controller = Restore4b(source, purchase_first=True)
    install = Mock()
    monkeypatch.setattr(controller, "installFound", install)
    controller.restoreFromHistory("111222333", "Старое приложение")
    assert controller.history["open"] and controller.history["idNote"]
    install.assert_not_called()
    source.connected = True
    source.changed.emit()
    assert controller.history["canRestore"]
    controller.restoreFromHistory("111222333", "Старое приложение")
    install.assert_called_once_with("111222333", "Старое приложение")


def test_failed_purchase_request_is_not_presented_as_empty_account():
    view = history_view([], signed_in=True, failed=True, error_note="Нет связи с Apple")
    assert view["empty"] == FAILED
    assert "нет покупок" not in view["empty"].lower()
    assert view["lead"] == "Нет связи с Apple"


def test_signed_out_purchase_landing_does_not_expose_previous_rows(qapp):
    source = source_with_purchases()
    source.signed_in = False
    controller = Restore4b(source, onboarded=False, purchase_first=True)
    assert controller.history["rows"] == []
    controller.closeHistory()
    assert controller.home["cta"] == "Войти в Apple ID"


def test_purchase_first_qml_loads_without_warnings(qapp):
    from tests.test_ui4b_qml import open_window
    from PySide6.QtQuick import QQuickItem
    controller = Restore4b(source_with_purchases(), onboarded=False, purchase_first=True)
    engine, icons, warnings = open_window(qapp, controller)
    window = engine.rootObjects()[0]
    listing = window.findChild(QQuickItem, "historyList")
    assert listing is not None and listing.property("count") == 2
    assert window.findChild(QQuickItem, "historyRefresh") is not None
    window.close()
    del window, engine
    qapp.processEvents()
    assert warnings == []
