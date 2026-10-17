from apprestore_gui.ui4b.standard_apps import standard_apps
from apprestore_gui.ui4b.history import history_view


def test_bundled_list_has_valid_unique_ids_and_names():
    items = standard_apps()
    assert len(items) == 670
    assert len({item['trackId'] for item in items}) == len(items)
    assert all(item['trackId'].isdigit() and item['name'] for item in items)
    assert any(item['trackId'] == '492224193' for item in items)


def test_catalog_is_visible_with_empty_history_during_loading_or_failure():
    for state in ({}, {'busy': True}, {'failed': True}):
        view = history_view([], signed_in=True, catalog=standard_apps(), **state)
        assert len(view['rows']) == 670
        assert view['rows'][0]['action'] == 'Восстановить'
        assert 'Стандартный список' in view['rows'][0]['developer']
        assert '670' in view['lead']


def test_search_by_id_and_name_and_no_duplicate_purchase():
    purchase = {'trackId': '492224193', 'name': 'Мой Сбер', 'date': '2024-01-02'}
    view = history_view([purchase], signed_in=True, catalog=standard_apps(), query='492224193')
    assert len(view['rows']) == 1
    assert view['rows'][0]['name'] == 'Мой Сбер'
    assert view['rows'][0]['developer'] == 'куплено 02.01.2024'
    view = history_view([], signed_in=True, catalog=standard_apps(), query='Telegram')
    assert [row['storeId'] for row in view['rows']] == ['686449807']


def test_signed_out_does_not_show_previous_account_or_catalog():
    view = history_view([{'trackId': '492224193', 'name': 'Private'}], signed_in=False, catalog=standard_apps())
    assert not view['rows']
    assert view['emptyLink'] == 'Войти'


def test_standard_restore_forwards_exact_id_and_name(qapp=None):
    from PySide6.QtWidgets import QApplication
    from apprestore_gui.ui4b.fake_data import FakeSource
    from apprestore_gui.ui4b.qt_bridge import Restore4b
    app = QApplication.instance() or QApplication([])
    source = FakeSource('empty')
    source.signed_in = True
    source.purchase_rows = lambda: []
    controller = Restore4b(source, onboarded=True)
    controller.openHistory()
    calls = []
    controller.installFound = lambda store_id, name: calls.append((store_id, name))
    row = next(row for row in controller.history['rows'] if row['storeId'] == '686449807')
    controller.restoreFromHistory(row['storeId'], row['name'])
    assert calls == [('686449807', 'Telegram')]
    assert controller.history['open'] is False
    app.processEvents()
