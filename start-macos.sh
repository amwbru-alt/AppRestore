#!/bin/bash
# Prepare and launch the native app, including its Apple login, in one terminal.
set -euo pipefail
appverni_root="$(cd "$(dirname "$0")" && pwd)"
cd "$appverni_root"
if [[ "$(uname -s)" != Darwin ]]; then
  echo "Этот файл предназначен для macOS. Windows: python -m apprestore_gui.app" >&2
  exit 1
fi
appverni_python=""
for candidate in python3.12 python3.11 python3.10 python3.13; do
  if command -v "$candidate" >/dev/null 2>&1; then
    appverni_python="$candidate"
    break
  fi
done
if [[ -z "$appverni_python" ]]; then
  echo "Установите Python 3.12 с python.org. Системный Python 3.9 не подходит." >&2
  exit 1
fi
# Do not overwrite the user's other .venv. Keep the application's runtime separate.
if [[ ! -x .venv-appverni/bin/python ]]; then
  "$appverni_python" -m venv .venv-appverni
fi
appverni_venv="$appverni_root/.venv-appverni/bin/python"
"$appverni_venv" -c 'import sys; assert (3,10) <= sys.version_info < (3,14), "Нужен Python 3.10–3.13"'
appverni_fingerprint="$(cat requirements/build.lock requirements/runtime.lock requirements/gui-build.txt pyproject.toml | shasum -a 256 | cut -d' ' -f1)"
appverni_stamp="$appverni_root/.venv-appverni/.dependencies-sha256"
if [[ ! -f "$appverni_stamp" ]] || [[ "$(cat "$appverni_stamp")" != "$appverni_fingerprint" ]]; then
  echo "Подготавливаем компоненты приложения (при первом запуске)…"
  "$appverni_venv" -m pip install --require-hashes --only-binary=:all: --no-deps --find-links requirements/wheels -r requirements/build.lock
  "$appverni_venv" -m pip install --require-hashes --only-binary=:all: --no-deps --find-links requirements/wheels -r requirements/runtime.lock
  "$appverni_venv" -m pip install --no-deps --no-build-isolation -e .
  "$appverni_venv" -m pip install -r requirements/gui-build.txt
  printf '%s\n' "$appverni_fingerprint" > "$appverni_stamp"
fi
# Bootstrap checks pinned hashes and patches, and skips an existing patched tool.
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Нужны инструменты Apple. В открывшемся окне нажмите «Установить», затем повторите запуск."
  xcode-select --install || true
  exit 1
fi
export PATH="$appverni_root/.venv-appverni/bin:$PATH"
bash packaging/bootstrap-ipatool.sh
exec "$appverni_venv" -m apprestore_gui.app --ui widgets
