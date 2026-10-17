from apprevive_core.region_probe import RegionStatus as S
from apprevive_gui.ui4b.standard_apps import standard_apps
from apprevive_gui.ui4b.history import history_view


def test_bundled_list_remains_available_as_metadata():
    items = standard_apps()
    assert len(items) == 670
    assert len({item['trackId'] for item in items}) == len(items)


def test_general_catalog_never_creates_ownership():
    for state in ({}, {'busy': True}, {'failed': True}):
        view = history_view([], signed_in=True, catalog=standard_apps(), **state)
        assert not view['rows']


def test_account_name_has_priority_over_catalog():
    purchase = dict(trackId='492224193', name='Мой Сбер')
    view = history_view([purchase], signed_in=True, catalog=standard_apps(), statuses={'492224193': S.DELISTED})
    assert len(view['rows']) == 1
    assert view['rows'][0]['name'] == 'Мой Сбер'
    assert not history_view([], signed_in=True, catalog=standard_apps(), query='Telegram')['rows']
