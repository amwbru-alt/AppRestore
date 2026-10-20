from types import SimpleNamespace
import pytest
from apprevive_core.service import AppReviveService, AppReviveError
from apprevive_core.tools import InstallRequestState
from tests.helpers import make_ipa
from tests.test_service import FakeTools


def service(tmp_path, tools):
    core=AppReviveService(tools=tools,library=tmp_path/'library',cache=tmp_path/'cache')
    core._remember_app_best_effort=lambda **kwargs:None
    return core


def test_store_restore_reports_phases_at_real_boundaries(tmp_path):
    ipa=tmp_path/'source.ipa';make_ipa(ipa)
    tools=FakeTools([ipa]);core=service(tmp_path,tools);seen=[]
    core.on_restore_stage=lambda phase:seen.append((phase,len(tools.download_calls),len(tools.install_calls)))
    core.restore_by_store_id('UDID','123456789')
    assert [s[0] for s in seen]==['check','download','prepare','prepare','install','confirm']
    assert seen[0][1:]==(0,0)
    assert next(s for s in seen if s[0]=='install')[2]==0
    assert seen[-1][2]==1


def test_local_ipa_skips_download_and_failed_submission_never_reports_confirmation(tmp_path):
    ipa=tmp_path/'source.ipa';make_ipa(ipa)
    class Failed(FakeTools):
        def install_ipa(self,*args):return InstallRequestState.FAILED_BEFORE_REQUEST
    core=service(tmp_path,Failed());seen=[];core.on_restore_stage=seen.append
    with pytest.raises(AppReviveError):core.install('UDID',ipa)
    assert seen==['prepare','install']


def test_display_callback_failure_does_not_change_installation(tmp_path):
    ipa=tmp_path/'source.ipa';make_ipa(ipa)
    core=service(tmp_path,FakeTools());core.on_restore_stage=lambda phase:(_ for _ in ()).throw(RuntimeError('closed display'))
    assert core.install('UDID',ipa).bundle_id=='com.example.alpha'


def test_progress_context_restores_previous_callback(tmp_path):
    core=service(tmp_path,FakeTools());outer=[];inner=[];core.on_restore_stage=outer.append
    with core.progress_stages(inner.append):core._stage('check')
    core._stage('confirm');assert outer==['confirm'];assert inner==['check']


def test_measured_download_percentage_does_not_become_install_percentage():
    pytest.importorskip('PySide6')
    from apprevive_gui.quick_session import QuickSession
    emitted=[];fake=SimpleNamespace(_files_mode=False,_restore_phase='download',_output_tail='',installProgress=SimpleNamespace(emit=lambda *args:emitted.append(args)))
    QuickSession._on_tool_output(fake,'downloading 4');QuickSession._on_tool_output(fake,'2%')
    assert emitted==[(42,'Загрузка 42%')]
    QuickSession._on_tool_output(fake,'\n');assert len(emitted)==1
    QuickSession._on_tool_output(fake,'downloading 100%');assert emitted[-1]==(100,'Загрузка 100%')
    QuickSession._note_restore_stage(fake,'prepare');assert emitted[-1]==(-1,'Подготовка')
    count=len(emitted);QuickSession._on_tool_output(fake,'downloading 99%');assert len(emitted)==count
    QuickSession._note_restore_stage(fake,'confirm');assert emitted[-1]==(-1,'Подтверждение результата')


def test_queue_clears_percent_and_records_only_observed_stages():
    from apprevive_gui.ui4b.queue import RestoreQueue, QueueEntry, CURRENT
    item=SimpleNamespace(key='a',label='App',store_id='123456789',bundle_id='com.example.a',ipa_path='',size_bytes=0)
    queue=RestoreQueue();queue.entries=[QueueEntry(item,state=CURRENT)]
    queue.progress(42,'Загрузка 42%');assert queue.rows()[0]['percent']==42
    queue.progress(-1,'Подготовка');row=queue.rows()[0];assert row['percent']==-1;assert row['detail']=='Подготовка'
    queue.progress(-1,'Подтверждение результата');assert queue.rows()[0]['stage']==4;assert queue.rows()[0]['percent']==-1
    local=RestoreQueue();local.entries=[QueueEntry(item,state=CURRENT)];local.progress(-1,'Подготовка')
    assert 1 not in local.rows()[0]['visited']
