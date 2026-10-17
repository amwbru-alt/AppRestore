from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("revivo_make_dmg", ROOT / "packaging/make_dmg.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("broken", [False, True])
def test_dmg_checks_mounted_bundle_and_always_detaches(tmp_path, monkeypatch, broken):
    app = tmp_path / "dist/ReVivo.app"
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/MacOS/ReVivo").write_bytes(b"test executable")
    calls = []
    stage = None

    def fake_run(args, **kwargs):
        nonlocal stage
        calls.append(args)
        if args[0] == "/usr/bin/ditto":
            shutil.copytree(args[1], args[2], symlinks=True)
        elif args[:2] == ["hdiutil", "create"]:
            stage = Path(args[args.index("-srcfolder") + 1])
            assert (stage / "Applications").readlink() == Path("/Applications")
            help_text = (stage / "INSTALL-RU.txt").read_text()
            assert "не отключает Gatekeeper" in help_text
            assert "Всё равно открыть" in help_text
            Path(args[-1]).write_bytes(b"mock DMG")
        elif args[:2] == ["hdiutil", "attach"]:
            mount = Path(args[args.index("-mountpoint") + 1])
            shutil.copytree(stage, mount, symlinks=True, dirs_exist_ok=True)
            if broken:
                (mount / "ReVivo.app/Contents/MacOS/ReVivo").unlink()
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    target = tmp_path / "out/ReVivo-macOS.dmg"
    if broken:
        with pytest.raises(RuntimeError, match="missing the application"):
            module.make_dmg(app, target)
    else:
        module.make_dmg(app, target)
        assert any(args[:2] == ["codesign", "--verify"] for args in calls)
    assert calls[-1][:2] == ["hdiutil", "detach"]
    assert any(args[:2] == ["hdiutil", "verify"] for args in calls)


def test_dmg_refuses_incomplete_bundle(tmp_path):
    with pytest.raises(ValueError, match="complete ReVivo.app"):
        module.make_dmg(tmp_path / "ReVivo.app", tmp_path / "out.dmg")


def test_dmg_is_uploaded_and_covered_by_release_checksums():
    release = (ROOT / ".github/workflows/release.yml").read_text()
    manual = (ROOT / ".github/workflows/gui-build.yml").read_text()
    assert 'gui_dmg="ReVivo-macOS.dmg"' in release
    assert 'sha256sum "$gui_windows" "$gui_macos" "$gui_dmg" >> SHA256SUMS.txt' in release
    assert '"${ASSET_DIR}/${gui_dmg}"' in release
    assert "gui-dist/ReVivo-macOS.dmg.sha256" in manual
