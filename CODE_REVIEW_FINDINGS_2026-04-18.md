# Code Review Findings (2026-04-18, pass 3)

Источник: повторное ревью после правок installer/nginx-cookie и изменений в viewer-access/session-security.

## Обновление статуса (2026-04-18, pass 4)

- Finding 1 (High): закрыто.
- Finding 2 (Medium): закрыто.
- Finding 3 (Testing gap): закрыто (для migration + installer env-логики).

## Findings

### 1. High: риск «залипания» foreign_keys=OFF при исключении в миграции SQLite

Статус: закрыто.

- В ветке миграции таблицы viewer-access выполняется `PRAGMA foreign_keys=OFF`, но обратное включение идет только в happy-path.
- При исключении между OFF и ON срабатывает внешний `except` с логированием, без гарантированного восстановления PRAGMA в этом соединении.
- Риск: соединение может вернуться в пул с отключенной проверкой FK, что приведет к silent нарушению ссылочной целостности.

Ссылки:

- [core/services/db_migration.py](core/services/db_migration.py#L141)
- [core/services/db_migration.py](core/services/db_migration.py#L170)

### 2. Medium: миграция неидемпотентна при частичном падении на временной таблице

Статус: закрыто.

- Используется `CREATE TABLE IF NOT EXISTS viewer_config_access_new`, затем `INSERT ... SELECT ...` с сохранением исходных `id`.
- Если прошлый запуск упал после создания/частичного заполнения `viewer_config_access_new`, следующий запуск не пересоздаст таблицу, а повторная вставка может упасть на `PRIMARY KEY`.
- Риск: зацикленный сценарий «migration warning на каждом старте» до ручного вмешательства в БД.

Ссылки:

- [core/services/db_migration.py](core/services/db_migration.py#L148)
- [core/services/db_migration.py](core/services/db_migration.py#L151)
- [tests/test_db_migration_service.py](tests/test_db_migration_service.py#L67)

### 3. Testing gap: отсутствуют функциональные тесты миграции и сценариев installer-логики

Статус: закрыто.

- Нет тестов на `DatabaseMigrationService` для аварийных веток (между `foreign_keys=OFF/ON`, partial rerun, повторный старт после fail).
- Shell-проверка installer-скриптов покрывает только синтаксис/линт и не валидирует фактический результат записи env-переменных по режимам HTTP/HTTPS/nginx.

Ссылки:

- [tests/test_db_migration_service.py](tests/test_db_migration_service.py#L110)
- [script_sh/ssl_setup.sh](script_sh/ssl_setup.sh#L415)
- [tests/test_script_sh_all.sh](tests/test_script_sh_all.sh#L71)

## Краткий changelog

- Миграция `viewer_config_access` сделана fail-safe: `PRAGMA foreign_keys=ON` гарантированно восстанавливается в `finally` даже при ошибке внутри миграции.
- Для идемпотентности rerun добавлен `DROP TABLE IF EXISTS viewer_config_access_new` перед пересозданием временной таблицы.
- Добавлен unit-тест `tests/test_db_migration_service.py` с 2 сценариями:
 	- восстановление после stale `viewer_config_access_new`;
 	- проверка reenabling `foreign_keys` при принудительной ошибке и успешный повторный запуск.
- В `script_sh/ssl_setup.sh` выделен helper `apply_nginx_reverse_proxy_env` и применен в `setup_nginx_letsencrypt`.
- `tests/test_script_sh_all.sh` расширен функциональными env-проверками режимов HTTP/HTTPS/nginx (включая ожидания по `SESSION_COOKIE_SECURE`, `WTF_CSRF_SSL_STRICT`, `TRUSTED_PROXY_IPS`, очистке `SSL_CERT`/`SSL_KEY`).

## Проверки

- Прогнан таргетный модуль миграции: `/opt/AdminAntizapret/venv/bin/python -m unittest tests.test_db_migration_service -v` (успешно).
- Прогнан полный `unittest discover` по каталогу tests (успешно, 26 тестов).
- Прогнан shell-набор: `bash tests/test_script_sh_all.sh` (успешно).

## Статус закрытых замечаний

- Протокольная уникальность viewer-access и фильтрация `grant/revoke` по `config_type` выглядят исправленными.
- Обработка не-JSON payload в `/api/viewer-access` выглядит исправленной.
- Риск secure-cookie для nginx reverse proxy в installer смягчен: теперь явно выставляются `SESSION_COOKIE_SECURE=true` и `WTF_CSRF_SSL_STRICT=true` в nginx-режиме.
