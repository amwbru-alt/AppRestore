from __future__ import annotations

from apprestore_core import license_guard as guard


def test_operator_mode_removes_only_local_quota(tmp_path, monkeypatch):
    journal = tmp_path / "licenses.jsonl"
    monkeypatch.setenv("REVIVO_UNLIMITED_LICENSES", "1")
    verdict = guard.check_can_acquire("123456789", 0, journal_path=journal, daily_limit=0, total_limit=0)
    assert verdict.allowed
    # Paid apps and unconfirmed prices still fail even in operator mode.
    assert not guard.check_can_acquire("123456789", 1.99, journal_path=journal).allowed
    assert not guard.check_can_acquire("123456789", None, journal_path=journal).allowed
    monkeypatch.delenv("REVIVO_UNLIMITED_LICENSES")
    assert not guard.check_can_acquire("123456789", 0, journal_path=journal, daily_limit=0, total_limit=0).allowed
