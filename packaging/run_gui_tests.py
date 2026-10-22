"""Run each GUI test module in its own Qt process on all build platforms.

Some modules own QApplication fixtures and launch background workers. Keeping
those modules in a single interpreter can leave Qt callbacks crossing application
teardown boundaries. Process isolation retains every test and its failure code.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TEST_MODULES = (
    'tests/test_gui_icons.py',
    'tests/test_gui_adapter.py',
    'tests/test_gui_smoke.py',
    'tests/test_gui_errors.py',
    'tests/test_frozen_runtime.py',
    'tests/test_gui_updater.py',
    'tests/test_gui_update_ui.py',
    'tests/test_gui_packaging.py',
    'tests/test_auth_pty_posix.py',
    'tests/test_quick_session.py',
    'tests/test_history_filter.py',
    'tests/test_catalog_discovery.py',
    'tests/test_purchases_loader.py',
    'tests/test_quick_session_purchases.py',
    'tests/test_ui4b_history.py',
    'tests/test_restore_progress.py',
    'tests/test_ui4b_names_icons.py',
    'tests/test_ui4b_logic.py',
    'tests/test_ui4b_passphrase.py',
    'tests/test_branding.py',
    'tests/test_restoration_codes.py',
    'tests/test_restoration_codes_gui.py',
    'tests/test_apprevive_artwork.py',
    'tests/test_account_credits.py',
    'tests/test_service_account.py',
    'tests/test_http_transport.py',
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    for module in sys.argv[1:] or TEST_MODULES:
        print(f"Testing {module} in an isolated process", flush=True)
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", module], cwd=root)
        if result.returncode:
            print(f"Failed: {module} (exit {result.returncode})", flush=True)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
