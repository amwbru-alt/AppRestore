import json
from unittest.mock import MagicMock
import pytest
pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication
from apprevive_core.app_catalog import validate_catalog
from apprevive_gui.app_catalog import AppCatalog
from apprevive_gui.ui4b.history import history_view


def test_catalog_rejects_invalid_rows_and_insecure_icon_urls():
    rows = validate_catalog([
        dict(trackId='492224193', name='Сбер', iconUrl='https://example.org/icon.png'),
        dict(trackId='492224193', name='Duplicate'),
        dict(trackId='123', name='Bad ID'),
        dict(trackId='686449807', name='Telegram', iconUrl='http://example.org/icon.png'),
        dict(trackId='6448311069', name='ChatGPT', iconUrl='https://user:secret@example.org/x'),
    ])
    assert len(rows) == 3
    assert rows[0]['iconUrl'].startswith('https://')
    assert rows[1]['iconUrl'] == rows[2]['iconUrl'] == ''


def test_remote_catalog_falls_back_and_survives_restart(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('apprevive_gui.app_catalog.cache_dir', lambda: tmp_path)
    book = AppCatalog()
    assert len(book.items()) == 670
    remote = [dict(trackId='492224193', name='Curated', iconUrl='https://example.org/icon.png')]
    book._apply(remote)
    assert book.items() == remote
    another = AppCatalog()
    assert another.items() == remote
    monkeypatch.setattr('apprevive_gui.app_catalog.read_catalog', MagicMock(side_effect=OSError()))
    another._fetch()
    assert another.items() == remote
    app.processEvents()


def test_history_keeps_purchase_and_uses_database_icon():
    view = history_view([dict(trackId='492224193', name='Account title')], signed_in=True,
                        catalog=[dict(trackId='492224193', name='Curated', iconUrl='https://example.org/x.png')])
    assert len(view['rows']) == 1
    assert view['rows'][0]['name'] == 'Account title'
    assert view['rows'][0]['iconUrl'] == 'https://example.org/x.png'


def test_manual_icon_is_used_before_apple_lookup(tmp_path, monkeypatch):
    from PySide6.QtGui import QImage, QColor
    from apprevive_gui.icons_cache import ArtworkCache
    cache = ArtworkCache(tmp_path)
    image = QImage(128, 128, QImage.Format.Format_RGB32)
    image.fill(QColor('#3859bc'))
    path = tmp_path / 'manual.png'
    image.save(str(path))
    fetch = MagicMock(return_value=path)
    apple = MagicMock(side_effect=AssertionError('Apple should not override curator'))
    monkeypatch.setattr(cache, 'fetch_file', fetch)
    monkeypatch.setattr(cache, 'artwork_info', apple)
    assert cache.rounded_icon_file(store_id='492224193', icon_url='https://example.org/icon.png')
    fetch.assert_called_once_with('https://example.org/icon.png')
    apple.assert_not_called()


def test_catalog_seed_matches_bundled_catalog():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    items = json.loads((root / 'apprevive_gui/ui4b/data/standard_apps.json').read_text())
    seed = (root / 'server/promo/catalog-seed.sql').read_text()
    assert all("('" + item['trackId'] + "'," in seed for item in items)
    assert 'INSERT IGNORE' in seed
