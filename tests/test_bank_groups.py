import pytest
from apprevive_core.app_catalog import validate_catalog
from apprevive_gui.ui4b.history import history_view
from apprevive_gui.ui4b.standard_apps import standard_apps


def test_exact_id_not_bank_name_decides_ownership():
    catalog = standard_apps()
    tbank = [r for r in catalog if r.get('groupId') == 't-bank']
    assert len(tbank) > 1
    actual = tbank[2]['trackId']
    purchases = [{'trackId': actual, 'name': 'My old app'}, {'trackId': '111111111', 'name': 'Т-Банк'}]
    view = history_view(purchases, signed_in=True, catalog=catalog, banks_only=True)
    assert [r['storeId'] for r in view['rows']] == [actual]
    assert 'Т-Банк' in view['rows'][0]['name']
    assert 'My old app' in view['rows'][0]['name']
    assert all(r['storeId'] not in {a['trackId'] for a in tbank if a['trackId'] != actual} for r in view['rows'])
    assert len(history_view(purchases, signed_in=True, catalog=catalog, banks_only=False)['rows']) == 2


def test_multiple_owned_variants_all_remain_choices_not_silent_replacement():
    variants = [r for r in standard_apps() if r.get('groupId') == 't-bank'][:2]
    purchases = [dict(trackId=v['trackId'], name=f'Previous {i}') for i, v in enumerate(variants)]
    view = history_view(purchases, signed_in=True, catalog=standard_apps(), banks_only=True)
    assert {r['storeId'] for r in view['rows']} == {v['trackId'] for v in variants}
    assert len(view['rows']) == 2
    assert len(history_view(purchases, signed_in=True, catalog=standard_apps(), banks_only=True, query='Т-Банк')['rows']) == 2


def test_empty_partial_failed_and_signed_out_history_never_reveal_unowned_variants():
    for state in ({}, {'busy': True}, {'failed': True}):
        assert not history_view([], signed_in=True, catalog=standard_apps(), banks_only=True, **state)['rows']
    assert not history_view([{'trackId': '455652438', 'name': 'Private'}], signed_in=False, catalog=standard_apps(), banks_only=True)['rows']


def test_validator_preserves_only_valid_group_metadata():
    row = dict(trackId='455652438', name='Variant', groupId='t-bank', groupName='Т-Банк', groupIconUrl='https://example.org/bank.png')
    assert validate_catalog([row])[0]['groupId'] == 't-bank'
    assert 'groupId' not in validate_catalog([dict(row, groupId='../../bad')])[0]
    assert validate_catalog([dict(row, groupIconUrl='javascript:bad')])[0]['groupIconUrl'] == ''


def test_old_account_ids_and_direct_bank_install_are_rejected():
    pytest.importorskip('PySide6.QtWidgets')
    from PySide6.QtWidgets import QApplication
    from apprevive_gui.ui4b.fake_data import FakeSource
    from apprevive_gui.ui4b.qt_bridge import Restore4b
    app = QApplication.instance() or QApplication([])
    source = FakeSource('empty')
    source.signed_in = True
    source.purchase_rows = lambda: []
    controller = Restore4b(source)
    calls = []
    controller._start = lambda items: calls.append(items)
    controller.installFound('455652438', 'Т-Банк')
    controller.restoreFromHistory('455652438', 'Т-Банк')
    assert calls == []
    assert 'не найден' in controller.history['lead']
