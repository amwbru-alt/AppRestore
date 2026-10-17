# Сборка AppRevive для macOS и Windows с Mac

В этой инструкции все действия выполняются с Mac. Для macOS приложение
собирается локально. Для Windows сборку запускают на GitHub: Windows-сборщик
создаёт `.exe`, а готовый архив скачивается через браузер на ваш Mac.

PyInstaller не создаёт Windows-программу при запуске на macOS. Обычная
команда PyInstaller на Mac создаёт только macOS-сборку. Windows устанавливать
на ваш Mac для способа с GitHub Actions не требуется.

Текущая ветка: `codex/apprevive-icons`. В ней используются новые имена:
`apprevive_core`, `apprevive_gui`, `packaging/apprevive-gui.spec`,
`AppRevive.app`, `AppRevive.exe`. Команды со старыми именами из прежних
инструкций к этой версии не подходят.

## 1. Подготовьте Mac

Локальная инструкция ниже рассчитана на Mac с Apple Silicon: M1, M2, M3 и
более новые. Необходимы интернет, Python 3.12 и Xcode Command Line Tools.
Apple ID и подключённый iPhone для компиляции не нужны.

Откройте приложение «Терминал». Выполните:

```bash
uname -m
python3.12 --version
xcode-select -p
```

Ожидается `arm64`, `Python 3.12.x` и путь к инструментам Xcode.
Если Python 3.12 не найден, установите версию 3.12 с python.org и заново
откройте Терминал. Системный Python 3.9.6 не подходит. Команда `py -3.12`
относится к Windows: на Mac используйте `python3.12`.

Если инструментов Xcode нет:

```bash
xcode-select --install
```

Завершите установку в появившемся окне, затем повторите `xcode-select -p`.
Полный Xcode для этих команд не требуется. Если на Mac с Apple Silicon
выводится `x86_64`, проверьте, что Терминал и Python не запущены через Rosetta;
не продолжайте сборку ARM-версии с Python другой архитектуры.

Не копируйте в команды приглашение Терминала: имя пользователя, символ `%`
и надпись `(.venv)` — это не часть команд. Не вставляйте Markdown-скобки
вокруг URL.

## 2. Скачайте нужные исходники

### Через ZIP

1. Скачайте [исходники текущей ветки](https://github.com/amwbru-alt/AppRestore/archive/refs/heads/codex/apprevive-icons.zip).
2. Распакуйте архив двойным щелчком в Finder.
3. Перейдите в распакованную папку:

```bash
cd ~/Downloads/AppRestore-codex-apprevive-icons
```

Название папки определяется именем GitHub-репозитория, поэтому оно может
содержать старое имя. Готовое приложение называется AppRevive.

Если Finder добавил к папке суффикс `2`, путь будет другим. В Терминале
напечатайте `cd ` с пробелом, перетащите нужную папку из Finder в окно
Терминала и нажмите Enter. Это также правильно экранирует пробелы в пути.

Убедитесь, что это обновлённый проект:

```bash
ls pyproject.toml packaging/apprevive-gui.spec
```

Оба файла должны существовать. Если spec-файл не найден, вы открыли прежнюю
версию либо другую папку. В ZIP нет каталога Git: ошибка `not a git repository`
при запуске `git branch` в таком случае ожидаема и сборке не мешает.

### Альтернатива: через Git

Выберите новое имя папки, которое ещё не занято:

```bash
cd ~/Downloads
git clone --branch codex/apprevive-icons https://github.com/amwbru-alt/AppRestore.git AppRevive-build
cd AppRevive-build
```

Если `AppRevive-build` уже существует, не удаляйте её автоматически.
Используйте другое свободное имя либо откройте ранее клонированную папку.
Все последующие команды выполняются из корня проекта, где лежит
`pyproject.toml`.

## 3. Соберите приложение для Mac

### 3.1. Создайте отдельное окружение

```bash
python3.12 -m venv .venv-build
.venv-build/bin/python -m pip install --upgrade pip
.venv-build/bin/python -m pip install . -r requirements/gui-build.txt
```

Активировать окружение командой `source` не обязательно: в инструкции явно
указан его Python. Поэтому команды работают независимо от другого активного
окружения. Важно не переносить `.venv-build` из другой папки проекта:
создавайте окружение в текущей папке.

### 3.2. Соберите ipatool с патчами проекта

```bash
bash packaging/bootstrap-ipatool.sh --asset macos-arm64 --force
```

Скрипт сам найдёт Go 1.25.0 либо скачает его в каталог сборки проекта,
проверит контрольную сумму, соберёт ipatool и создаст архив:

```text
build/ipatool-bootstrap/out-macos-arm64/ipatool-2.6.0-macos-arm64.tar.gz
```

Этот шаг может долго скачивать зависимости. Дождитесь возврата приглашения
Терминала и сообщения `patched ipatool ready`. Не запускайте следующий шаг
после ошибки. Случайный ipatool из Homebrew не заменяет сборку с патчами.

### 3.3. Соберите графическое приложение

```bash
.venv-build/bin/python -m PyInstaller packaging/apprevive-gui.spec --noconfirm --clean
```

После успешного завершения появляется `dist/AppRevive.app`. Сборку нужно
дополнить ipatool и проверить следующим шагом: одного PyInstaller недостаточно
для готового распространяемого архива.

### 3.4. Добавьте ipatool и создайте проверенный ZIP

```bash
.venv-build/bin/python packaging/package_gui.py \
  --out gui-dist \
  --ipatool-archive build/ipatool-bootstrap/out-macos-arm64/ipatool-2.6.0-macos-arm64.tar.gz
```

Упаковщик добавляет ipatool, выполняет локальную ad-hoc-подпись macOS,
запускает самопроверку и проверяет извлечение архива.

Результаты:

| Файл | Назначение |
|---|---|
| `dist/AppRevive.app` | Готовое приложение для запуска |
| `gui-dist/AppRevive-GUI-macOS.zip` | Архив для передачи пользователю |
| `gui-dist/AppRevive-GUI-macOS.zip.sha256` | Контрольная сумма архива |
| `gui-dist/selftest-macos.json` | Отчёт самопроверки |

### 3.5. Запустите приложение

```bash
open dist/AppRevive.app
```

Либо откройте папку сборки:

```bash
open dist
```

Перенесите `AppRevive.app` в «Программы» через Finder. Для повседневного
запуска Терминал и Python пользователю не нужны. Закройте старую запущенную
копию перед проверкой новой. Эта сборка не является нотарифицированной
Developer ID-сборкой; если macOS блокирует известную вам сборку, используйте
разрешение для конкретного приложения в «Системные настройки →
Конфиденциальность и безопасность», не отключая защиту всей системы.

## 4. Соберите Windows-приложение с Mac через GitHub

Это также удобный способ получить сразу обе платформы без установки
сборочных зависимостей на Mac.

### 4.1. Откройте сборку

1. Войдите в GitHub под аккаунтом с правом записи в репозиторий.
2. Откройте [GUI build](https://github.com/amwbru-alt/AppRestore/actions/workflows/gui-build.yml).
3. Если Actions выключены, включите их на странице репозитория.
4. Нажмите **Run workflow**.
5. В списке **Branch** выберите **codex/apprevive-icons**.
6. Нажмите зелёную кнопку **Run workflow**.

Не выбирайте `main`, пока изменения AppRevive туда не объединены: иначе
соберётся другая версия. Если кнопка Run workflow отсутствует, проверьте
права записи, включённые Actions и наличие `workflow_dispatch` у workflow
в основной ветке. В исходном проекте этот workflow уже предусмотрен.

### 4.2. Дождитесь двух сборок

Откройте новый запуск. В нём выполняются две независимые задачи:

- **Windows GUI artifact** — Windows x64: Python 3.12, PyInstaller и ipatool
  собираются на Windows-сервере GitHub.
- **macOS GUI artifact** — отдельная сборка на macOS-сервере GitHub.

Дождитесь зелёной отметки у нужной задачи. Вкладку можно закрыть и позже
вернуться к тому же запуску. Учётная запись Apple, пароль и промокоды для
сборки не требуются: тесты используют фикстуры, самопроверка не должна
устанавливать приложения на настоящий телефон.

### 4.3. Скачайте Windows-результат на Mac

1. На странице завершённого запуска прокрутите до раздела **Artifacts**.
2. Нажмите **AppRevive-GUI-Windows**.
3. Распакуйте скачанный GitHub-архив.
4. Внутри будет `AppRevive-GUI-Windows.zip` и его файл `.sha256`.
5. Этот внутренний ZIP можно передать пользователю Windows целиком.

В нём находится папка `AppRevive` с `AppRevive.exe` и зависимостями.
На Windows распакуйте весь архив в обычную папку и запускайте
`AppRevive.exe`. Нельзя передавать один `.exe`, удаляя соседние файлы:
это сборка с каталогом зависимостей, а не один автономный файл.

Для связи с iPhone на Windows дополнительно нужны Apple Devices либо
подходящие драйверы Apple/iTunes, как описано в основном README.
Запуск `.exe` на Mac не проверяет его работоспособность на Windows.

### 4.4. Скачайте macOS-результат при необходимости

В том же запуске выберите артефакт **AppRevive-GUI-macOS**.
Внутри находится `AppRevive-GUI-macOS.zip` и контрольная сумма.
Это сборка под архитектуру использованного macOS-сервера GitHub; текущий
workflow выбирает ipatool по `uname -m`. Она не является universal-сборкой
для всех Intel и Apple Silicon одновременно. Для гарантированной сборки
под свой Apple Silicon используйте локальные шаги раздела 3.

## 5. Повторная сборка после изменения кода

Сначала получите обновлённые исходники. Для ZIP скачайте новый архив
ветки; команда `git pull` в распакованном ZIP не работает. В настоящем
Git-клоне перейдите на нужную ветку и обновите её обычным способом.

В текущей папке обновите Python-пакет:

```bash
.venv-build/bin/python -m pip install . -r requirements/gui-build.txt
```

Повторите шаги 3.2–3.4. `--force` пересобирает ipatool с текущими патчами,
а `--clean` убирает кэш PyInstaller для сборки. Они не удаляют пользовательскую
библиотеку IPA или базу использованных кодов.

Для Windows запустите **GUI build** ещё раз на обновлённой ветке.
Скачивайте артефакт именно нового успешного запуска.

## 6. Если что-то не получилось

| Ошибка | Что проверить |
|---|---|
| `zsh: command not found: py` | На Mac используйте `python3.12`, не Windows-команду `py` |
| `python3.12: command not found` | Установлен ли Python 3.12 и открыт ли новый Терминал |
| `No module named apprevive_gui` | Верная ли папка проекта и выполнена ли установка `pip install . -r requirements/gui-build.txt` |
| `No module named PyInstaller` | Используйте `.venv-build/bin/python`, которым установлены зависимости |
| `packaging/apprevive-gui.spec` не найден | Скачана ли свежая ветка AppRevive; проверьте текущую папку |
| `fatal: not a git repository` | Это ZIP, либо вы находитесь вне Git-клона; для ZIP команды Git не нужны |
| `destination path ... already exists` | Выберите новое имя каталога для клонирования; не удаляйте прежнюю работу автоматически |
| `unexpected archive layout` | Используйте свежий bootstrap из этой ветки и повторите шаг 3.2; не смешивайте старые скрипты и архивы |
| `missing locally built ipatool archive` | Успешно ли завершён шаг 3.2 и указан ли именно его архив |
| Actions красный | Откройте провалившийся шаг; скачайте доступный `selftest-windows`/`selftest-macos`, если ошибка на упаковке |
| Нет артефакта приложения | Задача могла завершиться до шага загрузки; проверьте журнал, не выбирайте только selftest-артефакт |

При обращении за помощью приложите название шага, последние строки ошибки
и версию Python. Перед отправкой журнала проверьте отсутствие паролей,
кодов 2FA и данных Apple ID. Сборка приложения и вход в Apple ID — разные
операции; повторный вход не исправляет ошибку компиляции.

## Источники

- [PyInstaller: результат зависит от ОС сборки](https://pyinstaller.org/en/stable/operating-mode.html).
- [GitHub: ручной запуск workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
- [GitHub: скачивание артефактов](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts).
- Команды и имена файлов сверены с `packaging/apprevive-gui.spec`,
  `packaging/bootstrap-ipatool.sh`, `packaging/package_gui.py` и
  `.github/workflows/gui-build.yml` этой ветки. Саму сборку `.app`/`.exe`
  из текущего Linux-окружения не выполняли; конечный результат нужно
  проверить запуском на соответствующей ОС.

## MySQL и каталог

Доступ к базе задаётся в отдельном файле `~/.apprevive/mysql.json`, не в исходниках. Настройка — [MYSQL.md](MYSQL.md). Таблица каталога, импорт 670 приложений и загрузка иконок — [CATALOG.md](CATALOG.md).
