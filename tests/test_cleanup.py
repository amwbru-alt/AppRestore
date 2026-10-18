from pathlib import Path
import pytest

from apprevive_gui import cleanup


def test_downloads_keep_imports_documents_and_link_targets(tmp_path):
    library = tmp_path / 'library'
    library.mkdir()
    (library / 'one.ipa').write_bytes(b'ipa')
    (library / 'nested').mkdir()
    (library / 'nested' / 'two.IPA').write_bytes(b'ipa')
    (library / 'readme.txt').write_text('keep')
    external = tmp_path / 'imports'
    external.mkdir()
    (external / 'keep.ipa').write_bytes(b'imported')
    try:
        (library / 'outside').symlink_to(external, target_is_directory=True)
    except OSError:
        pass  # Windows runners may not allow creating symbolic links.
    assert cleanup.clear_downloads(library) == 2
    assert cleanup.clear_downloads(library) == 0
    assert (library / 'readme.txt').exists()
    assert (external / 'keep.ipa').exists()


def test_accounts_remove_all_sessions_but_keep_balance_and_config(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: home)
    root = home / '.apprevive'
    vault = root / 'keychains' / 'apple@example.com'
    vault.mkdir(parents=True)
    (vault / 'account').write_text('encrypted')
    (root / 'device-accounts.json').write_text('{}')
    (root / 'api.json').write_text('{}')
    (root / 'credits.sqlite3').write_bytes(b'balance')
    live = home / '.ipatool'
    live.mkdir()
    for name in cleanup._FILES:
        (live / name).write_text('encrypted')
    (live / 'config.json').write_text('keep')
    forgotten = []
    monkeypatch.setattr(cleanup, 'forget_purchases_cache', lambda: forgotten.append(True))
    cleanup.clear_accounts()
    assert not (root / 'keychains').exists()
    assert not (root / 'device-accounts.json').exists()
    assert all(not (live / name).exists() for name in cleanup._FILES)
    assert (live / 'config.json').exists()
    assert (root / 'api.json').exists()
    assert (root / 'credits.sqlite3').exists()
    assert forgotten == [True]


def test_cleanup_refuses_busy_session():
    from types import SimpleNamespace
    from apprevive_gui.quick_session import QuickSession
    session = SimpleNamespace(_acquire_account_change=lambda: False)
    with pytest.raises(RuntimeError):
        QuickSession.clear_local_data(session, 'downloads')
    with pytest.raises(ValueError):
        QuickSession.clear_local_data(session, 'unknown')
