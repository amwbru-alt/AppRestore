"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fake_ipatools_count_as_patched(request, monkeypatch):
    """Fake ipatool scripts in tests stand for AppRevive's patched build; the
    preflight itself is tested with its own tools (test_license_gate)."""

    if "real_ipatool_caps" in request.keywords:
        return
    from apprevive_core.tools import AppReviveTools

    monkeypatch.setattr(AppReviveTools, "license_preflight", lambda self: None)
