> **Текущий временный режим — HTTP:** [запуск на IP и сборка Mac/Windows](HTTP-TEMP.md). Эта инструкция заменяет прежнее обязательное требование HTTPS.

> **Версия 0.5.0:** сначала выполните [инструкцию перехода](PLATFORM.md). Она заменяет приведённые ниже старые указания про HTTP, вход и ручную оплату. Для нового входа требуется HTTPS и миграция базы.

# AppRevive: установка и сборка через Git с Mac

**`revive.example.com` в командах — пример. Замените его настоящим доменом из PLATFORM.md и задайте `APPREVIVE_PUBLIC_API_URL` до сборки.**

Текущая ветка — `codex/apprevive-icons`. Mac и Windows используют один
HTTPS API, адрес которого вы задаёте перед сборкой (ниже пример): **https://revive.example.com**. Пользователю приложения не
нужны MySQL, пароль базы, Node.js или mysql.json. Node.js работает отдельно
на сервере; эта инструкция не запускает его на компьютерах пользователей.

## 1. Получить свежий код

Если у вас уже есть Git-клон `~/Downloads/AppRevive-build`:

```bash
cd ~/Downloads/AppRevive-build
git status --short
git switch codex/apprevive-icons
git pull --ff-only
```

Если Git сообщает о локальных изменениях и не даёт обновиться, сохраните их;
не используйте `reset --hard`. Можно клонировать код в другую свободную папку.

Для нового клонирования:

```bash
cd ~/Downloads
git clone --branch codex/apprevive-icons https://github.com/amwbru-alt/AppRestore.git AppRevive-API
cd AppRevive-API
```

Выберите свободное имя папки, если `AppRevive-API` уже существует. ZIP-папка
не является Git-клоном. Все команды локальной сборки ниже выполняются из
корня выбранного Git-клона.

Проверьте обновление:

```bash
git branch --show-current
cat apprevive_core/api_settings.json
```

Ожидается ветка `codex/apprevive-icons`. Перед локальной сборкой замените старый адрес в файле на ваш HTTPS-домен. Для Actions задайте переменную, как описано в PLATFORM.md.

## 2. Проверить API

```bash
curl --max-time 10 https://revive.example.com/health
curl --max-time 10 https://revive.example.com/v1/catalog
```

`/health` возвращает `{"status":"ok"}`, `/v1/catalog` — JSON с приложениями.
Если подключения нет, сначала запустите сервер по [этой инструкции](server/node/README.md)
и откройте входящий TCP-порт 3000. Скомпилировать приложение можно без
запущенного API, но активировать код без него нельзя. Стандартный список
приложений и резервные картинки работают без API.

Старые уже скачанные сборки автоматически не меняются. Используйте новые
артефакты, собранные после этого обновления, вместо запусков
`39074502170` и `39075421625`.

## 3. Собрать Mac локально (Apple Silicon)

Проверьте инструменты:

```bash
uname -m
python3.12 --version
xcode-select -p
```

Ожидается `arm64`. При отсутствии Python 3.12 и установленном Homebrew:

```bash
brew install python@3.12
```

При отсутствии Xcode Command Line Tools выполните `xcode-select --install`
и завершите установку перед продолжением.

В корне Git-клона:

```bash
python3.12 -m venv .venv-build
.venv-build/bin/python -m pip install --upgrade pip
.venv-build/bin/python -m pip install . -r requirements/gui-build.txt
```

Соберите вспомогательный ipatool:

```bash
bash packaging/bootstrap-ipatool.sh --asset macos-arm64 --force
```

После сообщения `patched ipatool ready`:

```bash
.venv-build/bin/python -m PyInstaller packaging/apprevive-gui.spec --noconfirm --clean
```

**Обязательный шаг** — добавить ipatool в `.app` и проверить упаковку:

```bash
.venv-build/bin/python packaging/package_gui.py \
  --out gui-dist \
  --ipatool-archive build/ipatool-bootstrap/out-macos-arm64/ipatool-2.6.0-macos-arm64.tar.gz
```

Не запускайте `.tar.gz` как команду: это входной архив упаковщика.
После успешного завершения:

```bash
open dist/AppRevive.app
```

Готовый архив для передачи — `gui-dist/AppRevive-GUI-macOS.zip`.
Закройте старую копию и перенесите новую `AppRevive.app` в «Программы».
Реквизиты MySQL в неё не входят.

## 4. Собрать Windows и Mac через Терминал на Mac

Сборка `.exe` выполняется на Windows-сервере GitHub. Mac запускает задачу и
скачивает результат. Локально PyInstaller на Mac создаёт только `.app`.

При установленном Homebrew:

```bash
brew install gh
gh auth login
```

Если уже вошли в GitHub CLI, повторная авторизация не нужна.
Запустите новую сборку опубликованной ветки:

```bash
gh workflow run gui-build.yml --repo amwbru-alt/AppRestore --ref codex/apprevive-icons
```

Команда выводит ссылку вида `.../actions/runs/НОМЕР`. Скопируйте именно
номер запуска; номер отдельной Windows/macOS-задачи не подходит.
Найти запуск можно и так:

```bash
gh run list --repo amwbru-alt/AppRestore --workflow gui-build.yml --branch codex/apprevive-icons --limit 5
```

Подставьте реальный новый номер вместо примера:

```bash
APPREVIVE_RUN_ID=123456789
```

Дождитесь результата:

```bash
gh run watch "$APPREVIVE_RUN_ID" --repo amwbru-alt/AppRestore --exit-status
```

После успешной загрузки артефактов скачайте Windows:

```bash
gh run download "$APPREVIVE_RUN_ID" \
  --repo amwbru-alt/AppRestore \
  --name AppRevive-GUI-Windows \
  --dir "$HOME/Downloads/AppRevive-Windows-$APPREVIVE_RUN_ID"
```

И Mac:

```bash
gh run download "$APPREVIVE_RUN_ID" \
  --repo amwbru-alt/AppRestore \
  --name AppRevive-GUI-macOS \
  --dir "$HOME/Downloads/AppRevive-macOS-$APPREVIVE_RUN_ID"
```

Откройте результаты:

```bash
open "$HOME/Downloads/AppRevive-Windows-$APPREVIVE_RUN_ID"
open "$HOME/Downloads/AppRevive-macOS-$APPREVIVE_RUN_ID"
```

Файлы в этих папках — внутренние ZIP приложения и контрольная сумма.
Распакуйте внутренний `AppRevive-GUI-macOS.zip`, чтобы получить `.app`.
Windows-архив передавайте целиком: внутри папка `AppRevive`, `.exe` и его
зависимости. macOS-артефакт собирается под архитектуру сервера GitHub,
которая указана в журнале сборки; это не универсальный Intel/ARM-архив.

## 5. Установка на Windows

1. Распакуйте **весь** `AppRevive-GUI-Windows.zip` в обычную папку.
2. Установите Apple Devices или драйверы Apple/iTunes для USB-связи с iPhone.
3. Запустите `AppRevive.exe` из распакованной папки.
4. Подключите iPhone, разблокируйте его и подтвердите доверие компьютеру.

Не переносите один `.exe` без соседних файлов. MySQL-клиент, Node.js,
mysql.json и пароль базы пользователю не нужны. Адрес API уже встроен.

## 6. Если приложение использует старый адрес

Проверьте необязательные переопределения: `APPREVIVE_API_URL` и файл
`~/.apprevive/api.json` на Mac либо `%USERPROFILE%\.apprevive\api.json`
на Windows. Они имеют приоритет над встроенным адресом. Если такой файл
создавался раньше, измените в нём только base_url на
`https://revive.example.com` либо переименуйте его, сохранив резервную копию.
Старый mysql.json новая версия не читает.

## 7. Ошибки сборки и скачивания

- `no space left on device`: освободите место на Mac, включая Корзину;
  проверьте `df -h /System/Volumes/Data`. Скачайте и распакуйте архив заново
  в новую папку: старая копия могла распаковаться не полностью.
- `no artifact matches`: проверьте, прошли ли упаковка и upload для нужной
  платформы; артефакт `selftest` содержит отчёт, а не приложение.
- `HTTP 404` с длинным числом задачи: используйте ID всего запуска из
  `gh run list`, не job ID.
- Красный шаг сборки: `gh run view "$APPREVIVE_RUN_ID" --repo amwbru-alt/AppRestore --log-failed`.
- `ipatool не найден`: выполните обязательный шаг `package_gui.py` и
  запускайте новую сборку из `dist`, а не прежнюю копию в «Программах».
- API недоступен: проверьте `/health`, затем `/v1/catalog`; пароль MySQL
  исправляется на сервере Node.js, а не в приложении пользователя.

HTTP не шифрует промокоды. Пароль MySQL остаётся на сервере и не передаётся
между приложением и API.

## Обновление учёта восстановлений по Apple ID

Перед сборкой новых клиентов обновите Node.js API и импортируйте
[`server/promo/accounts-schema.sql`](server/promo/accounts-schema.sql) в ту же
базу MySQL. Подробные команды и порядок обновления:
[`server/node/README.md`](server/node/README.md#серверный-баланс-apple-id-обязательное-обновление-api).
Без этого новые клиенты остановятся перед установкой и попросят обновить API.
Секреты подключения остаются только в серверном `.env`; клиентам дополнительные
настройки не нужны.
