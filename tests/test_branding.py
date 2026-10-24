from pathlib import Path
import importlib.util

from apprevive_core.branding import copy_legacy_environment
from apprevive_core.paths import cache_dir, data_dir, ipa_library_dir
from apprevive_core.restoration_codes import RestorationCredits, RestorationAccess


def test_branding_in_commands_modules_and_build_assets():
    root = Path(__file__).resolve().parents[1]
    project = (root / 'pyproject.toml').read_text()
    assert 'name = "apprevive"' in project
    assert 'apprevive = "apprevive_core.cli:main"' in project
    assert 'apprevive-gui = "apprevive_gui.app:main"' in project
    assert importlib.util.find_spec('apprevive_core')
    assert importlib.util.find_spec('apprevive_gui')
    spec = (root / 'packaging/apprevive-gui.spec').read_text()
    assert 'name="AppRevive.app"' in spec and 'name="AppRevive"' in spec
    assert (root / 'packaging/icons/AppRevive.icns').is_file()
    from apprevive_gui.updater import ASSET_BY_PLATFORM, REPO
    assert ASSET_BY_PLATFORM['darwin'] == 'AppRevive-GUI-macOS.zip'
    assert ASSET_BY_PLATFORM['win32'] == 'AppRevive-GUI-Windows.zip'
    assert REPO == 'amwbru-alt/AppRestore'


def test_legacy_storage_preserves_ipa_and_used_free_gift(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr('platform.system', lambda: 'Darwin')
    for name in ('APPREVIVE_DATA_DIR','APPREVIVE_CACHE_DIR','APPREVIVE_IPA_DIR','XDG_CACHE_HOME'):
        monkeypatch.delenv(name, raising=False)
    old = tmp_path / 'Library/Application Support/AppRestore'
    credits = RestorationCredits(old / 'restoration-credits.sqlite3', activate=lambda *a: None)
    access = RestorationAccess(credits, lambda: False)
    access.run(lambda: None)
    credits.redeem('USED')
    access.run(lambda: None)
    (old / 'ipas').mkdir()
    (old / 'ipas/example.ipa').write_bytes(b'IPA')
    assert data_dir() == old
    assert ipa_library_dir() == old / 'ipas'
    existing = RestorationCredits(data_dir() / 'restoration-credits.sqlite3')
    assert existing.remaining == 0
    import pytest
    from apprevive_core.restoration_codes import RestorationCodeError
    with pytest.raises(RestorationCodeError, match='уже использован'):
        existing.redeem('USED')
    old_cache = tmp_path / 'Library/Caches/AppRestore'
    old_cache.mkdir(parents=True)
    assert cache_dir() == old_cache


def test_fresh_install_uses_new_directories_and_respects_override(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr('platform.system', lambda: 'Darwin')
    for name in ('APPREVIVE_DATA_DIR','APPREVIVE_IPA_DIR','APPREVIVE_CACHE_DIR','XDG_CACHE_HOME'):
        monkeypatch.delenv(name, raising=False)
    assert data_dir() == tmp_path / 'Library/Application Support/AppRevive'
    assert ipa_library_dir() == data_dir() / 'ipas'
    assert cache_dir() == tmp_path / 'Library/Caches/AppRevive'
    monkeypatch.setenv('APPRESTORE_IPA_DIR', str(tmp_path / 'existing-library'))
    copy_legacy_environment()
    assert ipa_library_dir() == tmp_path / 'existing-library'
    monkeypatch.setenv('APPREVIVE_IPA_DIR', str(tmp_path / 'override'))
    copy_legacy_environment()
    assert ipa_library_dir() == tmp_path / 'override'


def test_old_window_settings_are_copied_without_overwriting_current(tmp_path):
    import pytest
    pytest.importorskip('PySide6')
    from PySide6.QtCore import QSettings
    from apprevive_gui.ui4b.window import migrate_settings
    old = QSettings(str(tmp_path / 'old.ini'), QSettings.Format.IniFormat)
    current = QSettings(str(tmp_path / 'new.ini'), QSettings.Format.IniFormat)
    old.setValue('ui4b/onboarded', True)
    old.setValue('ui4b/archiveSearch', True)
    current.setValue('ui4b/archiveSearch', False)
    migrate_settings(current, old)
    assert current.value('ui4b/onboarded', type=bool)
    assert not current.value('ui4b/archiveSearch', type=bool)
