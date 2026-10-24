"""Real PNGs + deterministic transport: widget and Quick caches recover and repaint."""
from pathlib import Path
import json
import threading
import time
from unittest.mock import patch

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QBuffer,QIODevice
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QTableWidget
from apprevive_gui.icons_cache import ArtworkCache, ArtworkLoader
from apprevive_gui.main_window import MainWindow,AppCell
from apprevive_gui.service_adapter import GuiService


@pytest.fixture(scope='module')
def qapp(): return QApplication.instance() or QApplication([])


def png():
    image=QImage(64,64,QImage.Format.Format_RGB32);image.fill(QColor('#1c9a70'))
    buf=QBuffer();buf.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buf,'PNG')
    return bytes(buf.data())


def response(ids=('10000000',)):
    return json.dumps({'results':[dict(trackId=int(sid),bundleId='com.example.app',trackName='Пример',artworkUrl100='https://images.invalid/'+sid+'.png') for sid in ids]}).encode()


def wait(qapp,condition):
    deadline=time.monotonic()+4
    while not condition() and time.monotonic()<deadline:qapp.processEvents()
    assert condition()


def test_negative_lookup_expires_and_old_permanent_miss_is_retried(tmp_path,monkeypatch):
    cache=ArtworkCache(tmp_path)
    calls=[];clock=[1000.0]
    monkeypatch.setattr('apprevive_gui.icons_cache.time.time',lambda:clock[0])
    def get(url):
        calls.append(url)
        return b'{"results":[]}' if len(calls)==1 else response()
    monkeypatch.setattr(cache,'_http_get',get)
    assert cache.lookup(store_id='10000000')['artwork'] is None
    assert cache.lookup(store_id='10000000')['artwork'] is None
    assert len(calls)==1
    clock[0]+=cache.MISS_TTL+1
    assert cache.lookup(store_id='10000000')['artwork'].endswith('.png')
    assert len(calls)==2
    cache._index['id:20000000:us']={'artwork':None}
    assert cache.lookup(store_id='20000000')['artwork']
    assert len(calls)==3


def test_corrupt_file_and_html_response_are_not_cached_as_icons(tmp_path,monkeypatch,qapp):
    cache=ArtworkCache(tmp_path)
    url='https://images.invalid/app.png';path=cache.local_path_for(url)
    path.write_bytes(b'<html>temporary failure</html>'*10)
    monkeypatch.setattr(cache,'_http_get',lambda _:png())
    assert cache.fetch_file(url)==path
    assert not QImage(str(path)).isNull()
    bad='https://images.invalid/bad.png'
    monkeypatch.setattr(cache,'_http_get',lambda _:b'<html>error</html>'*20)
    assert cache.fetch_file(bad) is None
    assert not cache.local_path_for(bad).exists()


def test_widget_loader_downloads_off_thread_and_emits_on_gui_thread(tmp_path,monkeypatch,qapp):
    cache=ArtworkCache(tmp_path);main=threading.get_ident();calls=[];notified=[]
    def get(url):
        calls.append(threading.get_ident())
        return response() if 'lookup?' in url else png()
    monkeypatch.setattr(cache,'_http_get',get)
    loader=ArtworkLoader(cache)
    loader.changed.connect(lambda:notified.append(threading.get_ident()))
    initial=loader.pixmap(store_id='10000000',bundle_id='com.example.app',name='Example',size=36)
    assert not initial.isNull()
    wait(qapp,lambda:bool(notified))
    assert all(t!=main for t in calls)
    assert notified==[main]
    picture=loader.peek(store_id='10000000',size=36).toImage()
    assert picture.pixelColor(18,18).name()=='#1c9a70'
    loader._retry.stop()


def test_widget_cell_repaints_after_download_without_resetting_selection(tmp_path,monkeypatch,qapp):
    cache=ArtworkCache(tmp_path)
    event=threading.Event()
    def get(url):
        event.wait(2)
        return response(('10000000',)) if 'lookup?' in url else png()
    monkeypatch.setattr(cache,'_http_get',get)
    with patch.object(MainWindow,'refresh_device'):
        win=MainWindow(GuiService(demo_mode=True),cache)
    from apprevive_core.models import MissingApp
    from PySide6.QtCore import Qt
    app=MissingApp('com.example.app','Пример',store_id='10000000')
    table=win.pages['install'].findChild(QTableWidget,'install_table')
    win._fill_app_table(table,[(app,app.name,'1',app.bundle_id,app.store_id)])
    check=table.item(0,0);check.setCheckState(Qt.CheckState.Checked)
    cell=table.cellWidget(0,1)
    event.set()
    wait(qapp,lambda:cell.icon_label.pixmap().toImage().pixelColor(18,18).name()=='#1c9a70')
    assert table.item(0,0) is check and check.checkState()==Qt.CheckState.Checked
    assert win.windowTitle()=='AppRevive'
    win.close()


def test_cached_russian_artwork_is_visible_when_us_store_misses(tmp_path,monkeypatch,qapp):
    cache=ArtworkCache(tmp_path);url='https://images.invalid/ru.png'
    monkeypatch.setattr(cache,'_http_get',lambda _:png())
    cache.fetch_file(url)
    cache._index['id:10000000:us']={'artwork':None}
    cache._index['id:10000000:ru']={'artwork':url}
    monkeypatch.setattr(cache,'_http_get',lambda _:pytest.fail('cached painting must not use network'))
    assert cache.cached_pixmap(store_id='10000000',size=36).toImage().pixelColor(18,18).name()=='#1c9a70'


def test_finished_download_does_not_emit_into_deleted_window(tmp_path,qapp):
    from shiboken6 import delete
    loader=ArtworkLoader(ArtworkCache(tmp_path))
    book=loader.book
    delete(loader)
    # A worker may finish after its window has been destroyed. Qt must
    # disconnect the forwarded signal instead of invoking a dead emitter.
    book.changed.emit()
    qapp.processEvents()
