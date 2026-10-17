import threading
import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from apprevive_core.region_probe import RegionStatus as S
from apprevive_gui.ui4b.history_probe import HistoryProbe
from apprevive_gui.ui4b.fake_data import FakeSource
from apprevive_gui.ui4b.qt_bridge import Restore4b
from apprevive_gui.ui4b.home import PhoneApp
from apprevive_gui.ui4b.catalog import RestoreItem, GROUP_OFFLOADED, ACTION_STORE


@pytest.fixture(scope='module')
def qapp(): return QApplication.instance() or QApplication([])


def wait(app, condition):
    limit = time.monotonic() + 4
    while not condition() and time.monotonic() < limit:
        app.processEvents(); QTest.qWait(5)
    assert condition()


def source():
    src = FakeSource('empty'); src.signed_in = True; src.account_email = 'owner@example.com'
    src.purchase_rows = lambda: [dict(trackId='10000001', name='Removed'), dict(trackId='10000002', name='Available')]
    src.find_statuses = {'10000001': S.DELISTED, '10000002': S.AVAILABLE}
    return src


def test_opens_automatically_and_shows_only_delisted_owned_rows(qapp):
    src = source(); controller = Restore4b(src, onboarded=True)
    wait(qapp, lambda: not controller.history_probe.running)
    assert controller.history['open']
    assert [row['storeId'] for row in controller.history['rows']] == ['10000001']
    controller.closeHistory(); src.changed.emit()
    assert not controller.history['open']


def test_account_switch_discards_in_flight_results(qapp):
    src = source(); started = threading.Event(); release = threading.Event()
    def check(ids):
        if '10000001' in ids:
            started.set(); release.wait(2)
            return {'10000001': S.DELISTED}
        return {'10000003': S.AVAILABLE}
    src.store_statuses = check
    controller = Restore4b(src, onboarded=True)
    assert started.wait(1)
    src.account_email = 'another@example.com'
    src.purchase_rows = lambda: [dict(trackId='10000003', name='Other account')]
    src.changed.emit()
    assert not controller.history['rows']
    release.set(); wait(qapp, lambda: not controller.history_probe.running)
    assert not controller.history['rows']
    assert set(controller.history_probe.statuses) == {'10000003'}


def test_sign_out_clears_results_and_rejects_late_worker(qapp):
    src = source(); release = threading.Event(); started = threading.Event()
    def check(ids): started.set(); release.wait(2); return {sid: S.DELISTED for sid in ids}
    src.store_statuses = check
    controller = Restore4b(src, onboarded=True); assert started.wait(1)
    src.signed_in = False; src.account_email = ''; src.changed.emit()
    assert not controller.history['rows']
    release.set(); wait(qapp, lambda: not controller.history_probe.running)
    assert not controller.history_probe.statuses
    assert controller.history['emptyLink'] == 'Войти'


def test_network_failure_never_becomes_a_removed_app_and_refresh_recovers(qapp):
    src = source()
    src.store_statuses = lambda ids: (_ for _ in ()).throw(OSError('offline'))
    controller = Restore4b(src, onboarded=True)
    wait(qapp, lambda: not controller.history_probe.running)
    assert not controller.history['rows']
    assert 'Не удалось проверить' in controller.history['lead']
    src.store_statuses = lambda ids: {sid: S.DELISTED for sid in ids}
    controller.refreshHistory(); wait(qapp, lambda: not controller.history_probe.running)
    assert len(controller.history['rows']) == 2


def test_installed_hidden_offloaded_kept_and_button_cannot_restore_unowned(qapp):
    src = source()
    src.store_statuses = lambda ids: {sid: S.DELISTED for sid in ids}
    src.phone_apps = lambda: [PhoneApp('Offloaded', store_id='10000001', bundle_id='com.example.offloaded'), PhoneApp('Installed', store_id='10000002', bundle_id='com.example.installed')]
    src.items = lambda: [RestoreItem(key='one', name='Offloaded', group=GROUP_OFFLOADED, action=ACTION_STORE, store_id='10000001', bundle_id='com.example.offloaded')]
    controller = Restore4b(src, onboarded=True); wait(qapp, lambda: not controller.history_probe.running)
    assert [row['storeId'] for row in controller.history['rows']] == ['10000001']
    assert all(tile['kind'] != 'app' for tile in controller.home['tiles'])
    calls = []; controller.installFound = lambda sid, name: calls.append((sid, name))
    controller.restoreFromHistory('99999999', 'Not owned'); assert not calls
    controller.restoreFromHistory('10000002', 'Installed'); assert not calls
    controller.restoreFromHistory('10000001', 'Forged title')
    assert calls == [('10000001', 'Removed')]


def test_unknown_stops_further_batches_instead_of_request_storm(qapp):
    calls = []; probe = HistoryProbe()
    probe.update('owner', [str(10000000 + i) for i in range(100)], lambda ids: calls.append(ids) or {})
    wait(qapp, lambda: not probe.running)
    assert len(calls) == 1 and len(probe.statuses) == 100
    assert all(value is S.UNKNOWN for value in probe.statuses.values())
