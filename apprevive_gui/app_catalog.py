"""A cached catalog refreshed in a worker; offline bundled list stays available."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import threading
from PySide6.QtCore import QObject, Signal, Slot, Qt
from apprevive_core.app_catalog import read_catalog, validate_catalog
from apprevive_core.paths import cache_dir
from apprevive_gui.ui4b.standard_apps import standard_apps


class AppCatalog(QObject):
    changed = Signal()
    _loaded = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = cache_dir() / 'app-catalog.json'
        self._rows = []
        self._requested = False
        self._worker = None
        try:
            self._rows = validate_catalog(json.loads(self._path.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
        self._loaded.connect(self._apply, Qt.ConnectionType.QueuedConnection)

    def items(self):
        # A nonempty database snapshot overrides the bundled list. Empty DB uses the bundled list.
        return [dict(row) for row in self._rows] if self._rows else standard_apps()

    def refresh(self):
        if self._requested:
            return
        self._requested = True
        self._worker = threading.Thread(target=self._fetch, name='apprevive-catalog', daemon=True)
        self._worker.start()

    def _fetch(self):
        try:
            rows = read_catalog()
        except Exception:
            # Missing config/table or unreachable database never hides the offline list.
            return
        try:
            self._loaded.emit(rows)
        except RuntimeError:
            pass  # Window was closed while the catalog request was in flight.

    @Slot(object)
    def _apply(self, rows):
        self._rows = validate_catalog(rows)
        temporary = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self._path.parent, delete=False) as file:
                temporary = Path(file.name)
                json.dump(self._rows, file, ensure_ascii=False)
            os.replace(temporary, self._path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.changed.emit()
