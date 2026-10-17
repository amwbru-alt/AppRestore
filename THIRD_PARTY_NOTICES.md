# Сторонние компоненты

AppRevive использует или устанавливает следующие сторонние проекты. Их собственные лицензии и уведомления сохраняют силу.

## pymobiledevice3 10.1.0

- Назначение: обнаружение iOS-устройств и установка IPA через протоколы Apple Mobile Device.
- Проект: <https://github.com/doronz88/pymobiledevice3>
- Лицензия upstream: GNU General Public License 3.0.
- Текст лицензии: <https://github.com/doronz88/pymobiledevice3/blob/v10.1.0/LICENSE>

Пакет и его транзитивные зависимости устанавливаются по hash-locked файлу
`requirements/runtime.lock`.

## hexdump 3.3

- Назначение: транзитивная зависимость `pymobiledevice3`;
- Проект: <https://bitbucket.org/techtonik/hexdump/>;
- Лицензия upstream: Public Domain.

PyPI публикует только source ZIP, поэтому репозиторий содержит его проверенную
копию `requirements/sources/hexdump-3.3.zip` и воспроизводимо собранный
universal wheel `requirements/wheels/hexdump-3.3-py3-none-any.whl`. Их SHA-256
и рецепт зафиксированы в `requirements/README.md` и
`requirements/runtime.lock`.

## ipatool 2.6.0

- Назначение: авторизация и загрузка IPA, доступных учётной записи App Store.
- Проект: <https://github.com/majd/ipatool>
- Лицензия upstream: MIT.
- Текст лицензии: <https://github.com/majd/ipatool/blob/cde7d00355e152714377b953ec57438626d3cb5a/LICENSE>
- Сборка: коммит `cde7d00355e152714377b953ec57438626d3cb5a`. Официальный архив v2.6.0 не принимает перенаправление HTTP 301 при входе в Apple ID. Установщики берут архивы этой сборки и принимают их только при SHA-256 ниже.

Windows:

```text
639d9cd7f22cea2975fd8263b0a8cbd7a36e7ee742e4c3e3a910b85f05b4df14
```

macOS:

```text
576bde4baf04365fcdea46eb7f3e5bb6ea143d0d9e53d6e2711136cc608aac84  macos-amd64
faf98ef8067f1ef4783123d00561b4ece10dc7419631eb9555d88a1da2f61f3f  macos-arm64
```

## Unicorn Engine 2.1.4

- Назначение: `ipatool` 2.4+ подписывает авторизацию App Store через SAP, и
  подписчик исполняется в эмуляторе Unicorn.
- Проект: <https://github.com/unicorn-engine/unicorn>
- Лицензия upstream: GNU General Public License 2.0.

AppRevive не распространяет Unicorn. Библиотеку скачивает сам `ipatool` при
первом входе в Apple ID, сверяет по своим SHA-256 и кладёт в пользовательский
кэш (`%LOCALAPPDATA%\ipatool\unicorn` / `~/Library/Caches/ipatool/unicorn`).

## Apple

Apple, iPhone, iOS, App Store и iTunes — товарные знаки Apple Inc. AppRevive не является продуктом Apple и не аффилирован с Apple Inc.


## Standard application ID list — ipatool-webGUI

Source: https://github.com/pdx15/ipatool-webGUI/blob/main/resources/Apps_ID_List.txt

Bundled snapshot: 2026-10-17. Repeated IDs are merged; names and IDs are provided by the source and do not imply availability for any Apple ID.

MIT License

Copyright (c) 2021 Majd Alfhaily

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
