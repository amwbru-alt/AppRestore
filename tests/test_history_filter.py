from apprevive_core.history_filter import device_inventory, missing_history
import pytest

ROWS = [
    {'trackId':'12345678','bundleId':'bank.old','name':'Bank'},
    {'trackId':'22345678','bundleId':'bank.current','name':'Bank'},
    {'trackId':'32345678','bundleId':'bank.offloaded','name':'Bank'},
]

def test_only_exact_history_rows_missing_from_device_are_kept():
    inventory = device_inventory({
        'bank.current': {'CFBundleIdentifier':'bank.current'},
        'bank.offloaded': {'CFBundleIdentifier':'bank.offloaded','IsPlaceholder':True},
    })
    assert [r['trackId'] for r in missing_history(ROWS,inventory)] == ['12345678','32345678']
    assert missing_history([],inventory) == []
    assert missing_history(ROWS,None) == []


def test_unknown_identity_and_duplicate_ids_are_never_guessed_from_names():
    rows = ROWS + [dict(ROWS[0]), {'trackId':'42345678','name':'Bank'}, {'trackId':'bad','bundleId':'bank.foo'}]
    assert len(missing_history(rows,device_inventory({}))) == 3


def test_store_id_blocks_installed_app_even_if_bundle_id_has_changed():
    inventory = device_inventory({'bank.new':{'CFBundleIdentifier':'bank.new','iTunesMetadata':{'itemId':12345678}}})
    assert '12345678' in inventory.installed_ids
    assert [r['trackId'] for r in missing_history(ROWS,inventory)] == ['22345678','32345678']


@pytest.mark.parametrize('payload',[None,'error',42,{'error':'device locked'},[{'CFBundleIdentifier':42}]])
def test_failed_or_malformed_device_list_is_not_an_empty_phone(payload):
    with pytest.raises(Exception):
        device_inventory(payload)


def test_another_device_has_a_separate_inventory():
    phone_a=device_inventory({'bank.old':{'CFBundleIdentifier':'bank.old'}})
    phone_b=device_inventory({'bank.current':{'CFBundleIdentifier':'bank.current'}})
    assert missing_history(ROWS,phone_a)[0]['trackId']=='22345678'
    assert missing_history(ROWS,phone_b)[0]['trackId']=='12345678'
