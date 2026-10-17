"""Account-scoped, batched availability checks; stale workers cannot leak rows."""
from __future__ import annotations
import threading
from PySide6.QtCore import QObject, Signal, Slot, Qt
from apprevive_core.region_probe import RegionStatus
from .region import to_status


class HistoryProbe(QObject):
    changed = Signal()
    _result = Signal(int, object)
    _finished = Signal(int)
    BATCH = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.identity = ''
        self.generation = 0
        self.statuses = {}
        self.ids = set()
        self.running = False
        self.online = True
        self._probe = None
        self._stopped = threading.Event()
        stop = self._stopped
        self.destroyed.connect(lambda *_: stop.set())
        self._result.connect(self._apply, Qt.ConnectionType.QueuedConnection)
        self._finished.connect(self._done, Qt.ConnectionType.QueuedConnection)

    def update(self, identity, ids, probe, *, online=True, force=False):
        ids = {str(sid) for sid in ids if str(sid).isdigit()}
        if identity != self.identity:
            self.identity = identity
            self.generation += 1
            self.statuses = {}
        if force or online != self.online:
            self.generation += 1
            self.statuses = {}
        self.online = online
        self.ids = ids if identity else set()
        self.statuses = {key: value for key, value in self.statuses.items() if key in self.ids}
        self._probe = probe
        self._start()

    @property
    def pending(self):
        return bool(self.ids - self.statuses.keys()) and self.online

    def _start(self):
        if self.running or not self.online or not self.identity:
            return
        pending = sorted(self.ids - self.statuses.keys())
        if not pending:
            return
        self.running = True
        generation, probe, stopped = self.generation, self._probe, self._stopped

        def emit(signal, *args):
            if stopped.is_set(): return False
            try: signal.emit(*args); return True
            except RuntimeError: return False

        def run():
            try:
                for offset in range(0, len(pending), self.BATCH):
                    if stopped.is_set() or generation != self.generation: break
                    batch = pending[offset:offset + self.BATCH]
                    try: values = dict(probe(batch))
                    except Exception: values = {}
                    result = {sid: to_status(values.get(sid, values.get(int(sid), RegionStatus.UNKNOWN))) for sid in batch}
                    if not emit(self._result, generation, result): break
                    if all(value is RegionStatus.UNKNOWN for value in result.values()):
                        remaining = {sid: RegionStatus.UNKNOWN for sid in pending[offset + self.BATCH:]}
                        if remaining: emit(self._result, generation, remaining)
                        break
            finally:
                emit(self._finished, generation)
        threading.Thread(target=run, name='apprevive-owned-history', daemon=True).start()

    @Slot(int, object)
    def _apply(self, generation, result):
        if generation == self.generation:
            self.statuses.update({key: value for key, value in result.items() if key in self.ids})
            self.changed.emit()

    @Slot(int)
    def _done(self, generation):
        self.running = False
        self._start()  # purchase pages/account can have changed while a batch ran
        self.changed.emit()
