from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication
from apprevive_gui import partners
from apprevive_core.account_credits import account_id


def test_partner_profile_and_binding_in_native_dialog(monkeypatch):
    app = QApplication.instance() or QApplication([])
    email = 'person@example.com'
    calls = []
    bound = ['']
    released = []
    session = SimpleNamespace(_acquire_account_change=lambda: True,
        _tool_lock=SimpleNamespace(release=lambda: released.append(True)),
        service=SimpleNamespace(core=SimpleNamespace(tools=SimpleNamespace(ipatool_auth_info=lambda: {'email': email}))))
    def api(method, body, **kwargs):
        assert kwargs['namespace'] == 'partner'
        calls.append(method)
        if method == 'bind':
            bound[0] = body['referral_code']
            return {'status': 'bound'}
        return dict(status='ok', account_id=account_id(email), referral_code='RVP-ABCDEF123456', invited_by=bound[0],
                    invited=2, paid_buyers=1, paid_orders=2, purchased_codes=5, revenue_kopecks=50000)
    monkeypatch.setattr(partners, 'api_call', api)
    monkeypatch.setattr(partners, 'run_in_thread', lambda owner, work, on_finished, on_failed: on_finished(work()))
    dialog = partners.PartnerDialog(session)
    assert dialog.code.text() == 'RVP-ABCDEF123456'
    assert dialog.buyer.text() == account_id(email)
    assert 'Куплено кодов: 5' in dialog.stats.text()
    dialog.referral.setText('RVP-111111111111')
    dialog.bind()
    assert calls == ['profile', 'bind', 'profile']
    assert not dialog.referral.isEnabled()
    assert len(released) == 2
    dialog.close()
