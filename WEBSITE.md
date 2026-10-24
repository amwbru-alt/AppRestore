> `revive.example.com` — пример адреса. Замените его своим доменом; настройка HTTPS описана в PLATFORM.md.

> **Версия 0.5.0:** сначала выполните [инструкцию перехода](PLATFORM.md). Она заменяет приведённые ниже старые указания про HTTP, вход и ручную оплату. Для нового входа требуется HTTPS и миграция базы.

# Сайт AppRevive внутри Node.js API

Публичная страница работает на том же Node.js-процессе и порту, что и API:
**https://revive.example.com/**. Отдельный frontend-сервер, React, сборщик и новая
база не нужны. Существующие `.env`, API-маршруты, баланс и партнёрский учёт
сохраняются. Новых SQL-таблиц для самого сайта нет.

## Обновление сервера

Команды из корня установленного Git-клона (путь из нашего systemd-примера):

```bash
cd /opt/apprevive
git switch codex/apprevive-icons
git pull --ff-only
cd server/node
npm ci --ignore-scripts
sudo systemctl restart apprevive-api
curl -I http://127.0.0.1:3000/
```

Если репозиторий установлен в другом каталоге, замените `/opt/apprevive`.
Если Node запускался вручную, остановите старый процесс и выполните `npm start`
в `server/node`. Не запускайте второй экземпляр на том же порту. Порт 3000
должен быть доступен посетителям. Настройки подключения к MySQL остаются
только в серверном `.env`, копировать их в `public/` не нужно.

## Установщики для кнопок скачивания

Сам сайт не включает бинарные установщики. До их загрузки кнопка покажет
страницу «Архив пока не опубликован» со ссылкой на поддержку. Наличие архивов
отображается и на главной. Не переименовывайте отдельный `.exe` или `.app` в ZIP:
нужны готовые архивы из успешной GUI-сборки.

### 1. Скачать готовые архивы на Mac

Например, сборка с партнёрской программой:

```bash
gh run watch 39166668519 --repo amwbru-alt/AppRestore --exit-status
gh run download 39166668519 --repo amwbru-alt/AppRestore --name AppRevive-GUI-macOS --dir "$HOME/Downloads/AppRevive-site-mac"
gh run download 39166668519 --repo amwbru-alt/AppRestore --name AppRevive-GUI-Windows --dir "$HOME/Downloads/AppRevive-site-windows"
```

GitHub CLI распакует внешний архив артефакта. Внутри останутся готовые ZIP:
`AppRevive-GUI-macOS.zip` и `AppRevive-GUI-Windows.zip`. Их и нужно загрузить.

### 2. Передать с Mac на сервер

```bash
scp "$HOME/Downloads/AppRevive-site-mac/AppRevive-GUI-macOS.zip" root@185.173.93.200:/tmp/AppRevive-macOS.zip
scp "$HOME/Downloads/AppRevive-site-windows/AppRevive-GUI-Windows.zip" root@185.173.93.200:/tmp/AppRevive-Windows.zip
```

Если используете другой SSH-логин, замените `root` своим. Сами пароли SSH
не добавляйте в команды или исходники.

### 3. На сервере положить архивы в каталог скачивания

Для systemd-службы из `server/node/deploy/apprevive-api.service`:

```bash
sudo install -d -o apprevive -g apprevive -m 0755 /opt/apprevive/server/node/downloads
sudo install -o apprevive -g apprevive -m 0644 /tmp/AppRevive-macOS.zip /opt/apprevive/server/node/downloads/AppRevive-macOS.zip
sudo install -o apprevive -g apprevive -m 0644 /tmp/AppRevive-Windows.zip /opt/apprevive/server/node/downloads/AppRevive-Windows.zip
```

Пути и пользователя службы замените, если у вас они другие. Для замены
установщиков перезапуск Node не нужен. Не копируйте в эту папку `.env`, исходники
или архив репозитория. Каталог `downloads/` исключён из Git.

Проверьте:

```bash
curl http://127.0.0.1:3000/site-config
curl -I http://127.0.0.1:3000/download/macos
curl -I http://127.0.0.1:3000/download/windows
```

У опубликованных архивов должен быть HTTP 200 и `Content-Type: application/zip`.
Поддержаны HEAD и Range для возобновления больших скачиваний.

### Вариант: файлы уже лежат на другом сервере

Укажите в серверном `.env` постоянные прямые URL:

```dotenv
DOWNLOAD_MAC_URL=https://your-download-host.example/AppRevive-macOS.zip
DOWNLOAD_WINDOWS_URL=https://your-download-host.example/AppRevive-Windows.zip
```

Перезапустите Node после изменения `.env`. Непустой корректный URL имеет приоритет
над локальным ZIP. Оставьте переменные пустыми для локальной раздачи. GitHub
Actions artifact URL с требованием входа и временные истекающие ссылки не
подходят для общедоступной кнопки скачивания. Логины и пароли в URL запрещены.

## Содержимое и поведение

- `server/node/public/index.html` — оригинальная страница AppRevive: описание,
  порядок действий, поиск по каталогу, скачивание, стоимость, партнёры, FAQ.
- `server/node/public/assets/site.css` — адаптивное оформление для компьютера
  и телефона, в цветах приложения. Иллюстрация процесса не выдаётся за скриншот.
- `server/node/public/assets/site.js` — поиск через существующий `/v1/catalog`,
  статус архивов и копирование кода приглашения.
- `server/node/src/website.mjs` — только разрешённые публичные файлы и скачивание
  по фиксированным именам. Произвольные файлы сервера не публикуются.

Сайт не запрашивает Apple ID или его пароль, не обещает восстановление любого
приложения и не имитирует подключённый приём платежей. Кнопка получения кода
открывает поддержку в Telegram. Название в каталоге не подтверждает доступность
установки. Полную проверку выполняет настольное приложение.

Можно передать приглашение ссылкой вида
`https://revive.example.com/?ref=RVP-ABCDEF123456#partners`.
Сайт покажет код и кнопку копирования. Пример нужно заменить реальным личным
кодом из AppRevive. **Привязка не происходит просто при открытии ссылки**:
приглашённый должен ввести код в AppRevive до первой покупки. Cookie или
автоматического отслеживания посетителей на сайте нет.

На HTTP браузер может не разрешить доступ к буферу обмена. В этом случае код
выделится и его можно скопировать вручную. Шрифт Onest и изображение AppRevive
поставляются локально; лицензия шрифта — `assets/FONT-LICENSE.txt`.

## Проверки

```bash
cd server/node
npm ci --ignore-scripts
npm test
```

Проверяются главная страница, публичные ресурсы, сохранность API, отсутствие
доступа к конфигурации/исходникам, корректность URL скачивания, отсутствующие
архивы, потоковая раздача ZIP и частичные запросы. Для визуальной приёмки после
запуска откройте главную на компьютере и телефоне.
