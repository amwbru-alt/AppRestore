#!/usr/bin/env bash
# AppRevive launcher for macOS.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SUPPORT_DIR="$HOME/Library/Application Support/AppRevive"
VENV_DIR="$APP_SUPPORT_DIR/venv"
export APPREVIVE_IPA_DIR="${APPREVIVE_IPA_DIR:-$APP_SUPPORT_DIR/ipas}"
export APPREVIVE_CACHE_DIR="${APPREVIVE_CACHE_DIR:-$HOME/Library/Caches/AppRevive}"
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

die() {
  printf "%b\n" "${RED}Ошибка:${NC} $*" >&2
  exit 1
}

python_is_supported() {
  "$1" -I -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] < (3, 14)))' \
    >/dev/null 2>&1
}

find_python() {
  local candidate
  for candidate in \
    "$VENV_DIR/bin/python" \
    "$(command -v python3.12 2>/dev/null || true)" \
    "$(command -v python3 2>/dev/null || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if python_is_supported "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

run_core() {
  local python
  python=$(find_python) || die \
    "нужен Python 3.10–3.13. Запусти: $(basename "$0") setup"
  mkdir -p "$APPREVIVE_IPA_DIR" "$APPREVIVE_CACHE_DIR"
  chmod 700 "$APP_SUPPORT_DIR" "$APPREVIVE_IPA_DIR" \
    "$APPREVIVE_CACHE_DIR" 2>/dev/null || true
  if [[ -d "$VENV_DIR/bin" ]]; then
    export PATH="$VENV_DIR/bin:$PATH"
  fi
  if [[ "$python" == "$VENV_DIR/bin/python" ]]; then
    exec "$python" -X utf8 -I -m apprevive_core.cli "$@"
  fi
  exec "$python" "$SCRIPT_DIR/apprevive.py" "$@"
}

setup() {
  [[ -x "$SCRIPT_DIR/install-macos.sh" ]] || die \
    "не найден install-macos.sh рядом с launcher"
  exec "$SCRIPT_DIR/install-macos.sh"
}

show_header() {
  if [[ -t 1 ]]; then
    printf '\033[2J\033[H'
  fi
  printf "%b" "${BOLD}${CYAN}"
  cat <<'EOF'
  AppRevive
EOF
  printf "%b\n" "${NC}${DIM}Телефон → сгруженные приложения → скачать IPA → вернуть${NC}"
  printf '%s\n' "────────────────────────────────────────────"
}

pause_menu() {
  printf '\n'
  read -r -p "Enter, чтобы продолжить…" _ || true
}

menu() {
  while true; do
    show_header
    cat <<'EOF'
  1) Сгруженные — список и восстановление
  2) Удалённые — список, ID/URL/поиск и восстановление
  3) Локальные IPA — найти / скачать / установить
  4) Устройства и диагностика
  A) Войти в Apple ID
  B) Настроить зависимости
  0) Выход
EOF
    printf '\n'
    read -r -p "Выбор: " choice || return 0
    case "$choice" in
      1) "$0" restore || true; pause_menu ;;
      2) "$0" restore-missing || true; pause_menu ;;
      3)
        cat <<'EOF'
  1) Сканировать локальные IPA
  2) Скачать IPA
  3) Установить IPA
  0) Назад
EOF
        read -r -p "Выбор: " ipa_choice || true
        case "$ipa_choice" in
          1) "$0" scan || true ;;
          2)
            read -r -p "Bundle ID или App Store ID/URL: " value
            [[ -n "$value" ]] && "$0" download "$value" || true
            ;;
          3)
            read -r -p "Путь к IPA: " ipa_path
            [[ -n "$ipa_path" ]] && "$0" install "$ipa_path" || true
            ;;
          0) ;;
          *) printf "%b\n" "${RED}Неверный пункт.${NC}" ;;
        esac
        pause_menu
        ;;
      4)
        "$0" devices || true
        printf '%s\n' "Диагностика (кратко):"
        "$0" doctor || true
        pause_menu
        ;;
      [Aa]) "$0" auth || true; pause_menu ;;
      [Bb]) "$0" setup || true; pause_menu ;;
      0) return 0 ;;
      *) printf "%b\n" "${RED}Неверный пункт.${NC}"; pause_menu ;;
    esac
  done
}

case "${1:-}" in
  "") menu ;;
  setup) setup ;;
  wizard)
    shift
    run_core restore "$@"
    ;;
  -h|--help|help)
    if python=$(find_python); then
      if [[ "$python" == "$VENV_DIR/bin/python" ]]; then
        exec "$python" -X utf8 -I -m apprevive_core.cli --help
      fi
      exec "$python" "$SCRIPT_DIR/apprevive.py" --help
    fi
    cat <<EOF
AppRevive

  $(basename "$0") setup       установить зависимости
  $(basename "$0") restore     мастер восстановления
  $(basename "$0") doctor      проверить окружение

Для остальных команд нужен Python 3.10–3.13.
EOF
    ;;
  *) run_core "$@" ;;
esac
