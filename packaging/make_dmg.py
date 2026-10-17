"""Create a drag-to-Applications disk image. DMG does not bypass Gatekeeper."""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

DMG_NAME = "ReVivo-macOS.dmg"
INSTALL_HELP = """ReVivo — установка на macOS

1. Перетащите ReVivo.app в папку Applications (Программы).
2. Извлеките этот диск и запускайте ReVivo из Программ.

Эта сборка не подписана Developer ID и не прошла notarization Apple.
DMG упрощает установку, но не отключает Gatekeeper.
Если macOS не может проверить разработчика, попробуйте запустить установленное
приложение, затем откройте Системные настройки → Конфиденциальность и безопасность
и нажмите «Всё равно открыть», если macOS предлагает эту возможность.
Разрешение может потребовать пароль администратора. На управляемом компьютере
политика организации может запрещать запуск непроверенных приложений.
Если система сообщает об обнаруженном вредоносном ПО или повреждении, не
игнорируйте это: проверьте источник, SHA-256 и обратитесь к разработчику.

Запуск без подтверждения Gatekeeper требует Developer ID и notarization Apple.
Поддерживаемая архитектура этой сборки: {architecture}.
Исходники: https://github.com/amwbru-alt/AppRestore
"""


def make_dmg(app: Path, target: Path) -> None:
    app, target = app.resolve(), target.resolve()
    if app.name != "ReVivo.app" or not (app / "Contents" / "MacOS" / "ReVivo").is_file():
        raise ValueError("Expected a complete ReVivo.app bundle")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="revivo-dmg-") as tmp:
        stage = Path(tmp) / "image"
        stage.mkdir()
        # ditto preserves bundle symlinks, permissions and resource metadata.
        subprocess.run(["/usr/bin/ditto", str(app), str(stage / app.name)], check=True)
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        (stage / "INSTALL-RU.txt").write_text(
            INSTALL_HELP.format(architecture=platform.machine()), encoding="utf-8"
        )
        subprocess.run(["hdiutil", "create", "-volname", "ReVivo", "-srcfolder", str(stage),
                        "-format", "UDZO", "-ov", str(target)], check=True)
        subprocess.run(["hdiutil", "verify", str(target)], check=True)
        mount = Path(tmp) / "mounted"
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint",
                        str(mount), str(target)], check=True)
        try:
            installed = mount / app.name
            if not (installed / "Contents" / "MacOS" / "ReVivo").is_file():
                raise RuntimeError("DMG is missing the application executable")
            if not (mount / "Applications").is_symlink() or (mount / "Applications").readlink() != Path("/Applications"):
                raise RuntimeError("DMG is missing its Applications shortcut")
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(installed)], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("dist/ReVivo.app"))
    parser.add_argument("--out", type=Path, default=Path("gui-dist") / DMG_NAME)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("DMG creation requires macOS and Apple's hdiutil/ditto/codesign")
    make_dmg(args.app, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
