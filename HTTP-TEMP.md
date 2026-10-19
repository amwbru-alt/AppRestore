# Временный запуск AppRevive по HTTP и сборка Mac/Windows

Текущий адрес: **http://185.173.93.200:3000**. Эта инструкция временно заменяет требование HTTPS в PLATFORM.md. Пароль AppRevive, токен входа и коды передаются по HTTP без шифрования. Пароль Apple ID по-прежнему обрабатывается локальным ipatool; MySQL и платёжные ключи остаются только на сервере.

## 1. Обновить сервер

В Git-клоне **на сервере**, сохранив свой существующий `.env`:

```bash
git switch codex/apprevive-icons
git pull --ff-only
cd server/node
npm ci
```

Если сервер новый — скопируйте `.env.example` в `.env`, заполните свои DB_HOST, DB_PORT, DB_USER, DB_NAME, DB_PASSWORD. Новую базу вместо существующей создавать не нужно. `.env` не отправляется в Git и не входит в приложение.

Следующая команда меняет только настройки HTTP и сохраняет остальные значения, включая MySQL и почту:

```bash
node --input-type=module <<'JS'
import {readFileSync,writeFileSync} from 'node:fs';
const file='.env';
let text=readFileSync(file,'utf8');
const settings={HOST:'0.0.0.0',PORT:'3000',ALLOW_HTTP:'true',ALLOW_HTTP_AUTH:'true',DEV_ALLOW_INSECURE_AUTH:'false',PUBLIC_URL:'http://185.173.93.200:3000'};
for(const [name,value] of Object.entries(settings)){
  const line=new RegExp('^'+name+'=.*$','m');
  text=line.test(text)?text.replace(line,name+'='+value):text+'\n'+name+'='+value;
}
writeFileSync(file,text.trimEnd()+'\n',{mode:0o600});
console.log('HTTP settings updated; other settings preserved.');
JS
chmod 600 .env
```

Остановите старый процесс Node через используемый вами systemd/PM2 или Ctrl+C. Перед миграцией сделайте резервную копию базы:

```bash
node --env-file=.env src/migrate.mjs
npm start
```

Если используете PM2/systemd, перезапустите существующий сервис вместо запуска второго процесса. Откройте TCP-порт 3000 в firewall сервера/хостинга. Не меняйте порт MySQL на 3000.

Проверка с Mac:

```bash
curl --fail http://185.173.93.200:3000/health
curl --fail http://185.173.93.200:3000/site-config
curl --fail http://185.173.93.200:3000/v3/status
```

В `/site-config` ожидается `transport.http_auth_origin` со значением `http://185.173.93.200:3000`, в `/v3/status` — `secure_login_required:false`. Без `ALLOW_HTTP_AUTH=true` вход по публичному HTTP останется закрыт.

Кабинет: **http://185.173.93.200:3000/account**. Админка: **http://185.173.93.200:3000/admin**. Для регистрации/подтверждения Apple ID и сброса пароля по-прежнему нужны RESEND_API_KEY и подтверждённый MAIL_FROM на сервере; HTTP не отменяет проверку почты. Создание администратора и настройки MySQL/почты описаны в PLATFORM.md.

## 2. Сборка обеих версий

Изменение кода в `codex/apprevive-icons` теперь автоматически запускает GUI build для **Mac и Windows** с HTTP-адресом выше. На компьютере пользователя MySQL и Node не нужны.

С Mac можно найти текущую сборку:

```bash
gh run list --repo amwbru-alt/AppRestore --workflow gui-build.yml --branch codex/apprevive-icons --limit 3
```

Либо запустить новую вручную с точным адресом:

```bash
gh workflow run gui-build.yml --repo amwbru-alt/AppRestore --ref codex/apprevive-icons -f service_api_url=http://185.173.93.200:3000
```

Дождитесь завершения **обоих** jobs. Подставьте ID нового run вместо НОВЫЙ_ID:

```bash
APPREVIVE_RUN_ID=НОВЫЙ_ID
gh run watch "$APPREVIVE_RUN_ID" --repo amwbru-alt/AppRestore --exit-status
gh run download "$APPREVIVE_RUN_ID" --repo amwbru-alt/AppRestore --name AppRevive-GUI-macOS --dir "$HOME/Downloads/AppRevive-macOS-$APPREVIVE_RUN_ID"
gh run download "$APPREVIVE_RUN_ID" --repo amwbru-alt/AppRestore --name AppRevive-GUI-Windows --dir "$HOME/Downloads/AppRevive-Windows-$APPREVIVE_RUN_ID"
```

В каждой папке распакуйте внутренний ZIP целиком. На Mac откройте AppRevive.app; на Windows — AppRevive/AppRevive.exe вместе со всеми соседними файлами. Это обычные тестовые сборки; подпись доверенным сертификатом и notarization — отдельный процесс, описанный в PLATFORM.md.

Если старый `~/.apprevive/api.json` на Mac или `%USERPROFILE%\.apprevive\api.json` на Windows переопределяет URL, замените в нём `base_url` на `http://185.173.93.200:3000`. Проверьте также переменную APPREVIVE_API_URL. В новую сборку уже включено разрешение HTTP именно для этого адреса и порта; к другим публичным HTTP-серверам пароль автоматически не отправляется.

## 3. Оплата в HTTP-режиме

До настройки магазина PAYMENTS_ENABLED оставьте false; выдавайте оплаченные коды через администратора как прежде. После настройки ЮKassa страница оплаты самого провайдера открывается по HTTPS, а статус заказа проверяется через его HTTPS API при возврате в кабинет и по кнопке «Проверить оплату»/обновлению GUI. Сама HTTP-страница возврата не подтверждает платёж.

ЮKassa требует HTTPS для входящих webhook: https://yookassa.ru/developers/using-api/webhooks. На `http://IP:3000` автоматические уведомления провайдера не подключаются. Пока нет HTTPS, проверяйте статусы через кабинет/админку; внешние возвраты тоже требуют повторной проверки заказа. Частичные возвраты остаются ручным разбором. Реальный приём оплаты включайте только после тестов отдельного staging-магазина.

## 4. Возврат к HTTPS позже

Настройте TLS, затем задайте PUBLIC_URL=https://ВАШ-ДОМЕН, HOST=127.0.0.1 (если Caddy на этом же сервере), ALLOW_HTTP=false, ALLOW_HTTP_AUTH=false. Пересоберите GUI с `-f service_api_url=https://ВАШ-ДОМЕН`. Новая HTTPS-сборка больше не содержит разрешения публичного HTTP.
