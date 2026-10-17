"""Only delisted applications with actual ownership evidence are offered."""
from apprevive_core.region_probe import RegionStatus as S
from apprevive_gui.ui4b.history import history_view, parse_store_id, name_for_store_id


def test_history_requires_both_ownership_and_delisted_status():
    purchases = [dict(trackId='10000001', name='Removed'), dict(trackId='10000002', name='Available'), dict(trackId='10000003', name='Region'), dict(trackId='10000004', name='Unknown')]
    view = history_view(purchases, signed_in=True, statuses={'10000001': S.DELISTED, '10000002': S.AVAILABLE, '10000003': S.NOT_IN_REGION, '10000004': S.UNKNOWN, '99999999': S.DELISTED}, catalog=[dict(trackId='99999999', name='Not owned')])
    assert [row['storeId'] for row in view['rows']] == ['10000001']
    assert not view['allowManualId']


def test_unknown_or_unsigned_history_never_becomes_a_candidate():
    item = dict(trackId='10000001', name='Private')
    assert not history_view([item], signed_in=True)['rows']
    assert not history_view([item], signed_in=False, statuses={'10000001': S.DELISTED})['rows']
    assert history_view([item], signed_in=False)['emptyLink'] == 'Войти'


def test_fully_installed_app_is_excluded():
    view = history_view([dict(trackId='10000001', name='Installed')], signed_in=True, statuses={'10000001': S.DELISTED}, installed_ids={'10000001'})
    assert not view['rows']


def test_search_by_name_or_id_and_newest_first():
    items = [dict(trackId='10000001', name='Почта', date='2020-01-01'), dict(trackId='10000002', name='Карты', date='2024-01-01')]
    statuses = {item['trackId']: S.DELISTED for item in items}
    assert [row['name'] for row in history_view(items, signed_in=True, statuses=statuses)['rows']] == ['Карты', 'Почта']
    assert [row['name'] for row in history_view(items, signed_in=True, statuses=statuses, query='поч')['rows']] == ['Почта']
    assert [row['name'] for row in history_view(items, signed_in=True, statuses=statuses, query='10000002')['rows']] == ['Карты']


def test_loading_and_failed_checks_are_explicit():
    item = dict(trackId='10000001', name='App')
    assert history_view([item], signed_in=True, checking=True)['spinner']
    view = history_view([item], signed_in=True, statuses={'10000001': S.UNKNOWN})
    assert not view['rows'] and 'Не удалось проверить: 1' in view['lead']
    assert 'не удалось' in history_view([], signed_in=True, failed=True)['lead']


def test_id_and_name_helpers():
    assert parse_store_id('https://apps.apple.com/app/id492224193') == '492224193'
    assert parse_store_id('492 224 193') == '492224193'
    assert parse_store_id('не число') == ''
    assert name_for_store_id([dict(trackId='492224193', name='Сбер')], '492224193') == 'Сбер'
