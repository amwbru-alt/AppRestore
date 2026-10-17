# AppRevive: прямое подключение к MySQL

Приложение по умолчанию активирует коды напрямую в MySQL. PHP и браузер не требуются.
Пароль не включён в исходники и сборку. В распространяемом приложении прямой доступ позволяет извлечь реквизиты и обойти проверку; настройка рассчитана на доверенные компьютеры.

## 1. Таблицы

В клиенте mysql выберите базу apple и выполните `source /полный/путь/server/promo/schema.sql;`.
SQL находится в [schema.sql](server/promo/schema.sql). Совместим с MySQL 5.7 / InnoDB.

`apprevive_promo_codes`: code — точный код с учётом регистра, created_at — дата добавления.
`apprevive_promo_redemptions`: code_hash — SHA256 кода, owner_hash — SHA256 идентификатора установки, request_id — идентификатор запроса, activated_at — время активации.

Добавить коды:

```sql
USE apple;
INSERT INTO apprevive_promo_codes (code) VALUES ('RV-EXAMPLE-001'), ('RV-EXAMPLE-002');
SELECT code, created_at FROM apprevive_promo_codes;
```

DELETE активного кода и INSERT квитанции выполняются одной транзакцией. При ошибке оба откатываются. Квитанции сохраняйте: при потере ответа повторный запрос начислит восстановление без повторного списания кода. Код нельзя выдавать повторно даже после удаления его активной строки.

## 2. Локальные настройки Mac

В корне скачанного проекта:

```bash
mkdir -p ~/.apprevive
cp server/promo/mysql.example.json ~/.apprevive/mysql.json
chmod 600 ~/.apprevive/mysql.json
open -e ~/.apprevive/mysql.json
```

Замените REPLACE_LOCALLY на пароль базы, сохраните файл. JSON требует экранировать двойные кавычки и обратные слеши внутри пароля. Приложение читает этот файл при каждой активации. Не публикуйте его.

Windows: создайте `%USERPROFILE%\.apprevive\mysql.json` с тем же содержимым.
Другой путь можно указать в APPREVIVE_MYSQL_CONFIG; пароль можно задать через APPREVIVE_MYSQL_PASSWORD.
Для TLS с проверкой сертификата добавьте `"ssl_ca": "/absolute/path/ca.pem"`, полученный у хостинга. Без ssl_ca принудительная проверка TLS не включается.

## 3. Сборка

Перед обычной сборкой обновите зависимости в окружении сборки:

```bash
.venv-build/bin/python -m pip install . -r requirements/gui-build.txt
.venv-build/bin/python -m PyInstaller packaging/apprestore-gui.spec --noconfirm --clean
```

Настройки лежат вне .app/.exe и сохраняются при обновлении. Первое восстановление бесплатно; активация одного кода добавляет одно восстановление. Баланс и первоначальный подарок хранятся локально, не привязаны к Apple ID. Реальное соединение с вашим MySQL необходимо проверить с Mac: среда разработки не имеет доступного DNS до вашего сервера.
