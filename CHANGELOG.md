# CHANGELOG

## [Unreleased]

### Telegram Mini App

- **Mobile UX/UI**: улучшена мобильная вёрстка mini app — sticky tab bar, safe-area insets для Telegram WebView, collapsible шапка и фильтры, компактные карточки клиентов с «Ещё действия», bottom-sheet модалки, touch targets ≥44px, empty/loading states (`app.html`, `base.html`, `tg_mini_app.css`, `tg_mini_app.js`).
- **OpenVPN — управление доступом**: на вкладке «Главная» для клиентов OpenVPN добавлены действия как в веб-панели — временная и бессрочная блокировка, снятие блокировки, установка/снятие лимита трафика (с выбором периода 1/7/30 дней) и продление сертификата; используются существующие API `/api/openvpn/client-block` и `POST /` (`tg_mini_app.js`, `tg_mini_app.css`).
- **WG/AWG — управление доступом**: те же действия для WireGuard и AmneziaWG — блокировка, снятие блокировки, лимит трафика и продление срока (`extend`); API `/api/wg/client-access`, бейджи blocked/лимит/срок в карточках (`tg_mini_app.js`).

## [1.8.2] – 06.06.2026

### Модули и фоновые задачи

- **Настройки → «Модули и задачи»**: новая вкладка с двумя группами — **«Фоновые задачи»** (синхронизация трафика, WG/AWG, мониторинг CPU/RAM, учёт сессий, очистка runtime-бэкапов) и **«Разделы приложения»** (полное отключение модулей панели). Значения в `.env` (`FEATURE_*_ENABLED`, `TRAFFIC_SYNC_ENABLED` и др.), cron обновляется при сохранении; по умолчанию всё включено (`feature_toggles.py`, `feature_guards.py`, `post_handlers/feature_toggles.py`, `feature_disabled.html`, `.env.example`).
- **Полное отключение разделов**: при выключении модуля скрываются пункты меню и вкладки настроек, блокируются маршруты/API (страница «модуль отключён» или JSON 403), POST-обработчики настроек и кнопки скачивания/QR на главной; для отключённых протоколов на главной не выполняется reconcile (`base.html`, `settings.html`, post-handlers, `page_context.py`, `route_wiring.py`).
- **Разделы приложения — расширение**: 8 новых переключателей — пользователи и доступ, безопасность, логи действий, обновления системы, тесты и диагностика, скачивание и QR, порт/HTTPS/Nginx, обслуживание (ночной рестарт и перезапуск службы; бэкапы — отдельный модуль). `api_cidr_task_status` доступен при включённой маршрутизации или тестах.
- **UI «Модули и задачи»**: KPI (всего / включено / выключено), две группы с цветовым акцентом, карточки модулей в адаптивной сетке с иконками, бейджами типа, ключом `.env`, статус-индикатором, блоком «При отключении» (усиленное предупреждение для синхронизации трафика), сегментированным переключателем «Включён / Выключен», callout в шапке и live-обновлением карточки при выборе (`_tab_feature_toggles.html`, `settings_maintenance.css`, `settings-page-extra.js`).
- **Оценки нагрузки**: на карточках модулей блок «Нагрузка при включении» с бейджем уровня (минимальная / низкая / средняя / высокая) и описанием экономии ресурсов при отключении; под KPI — примечание, что оценки приблизительные.

### Ограничения трафика клиентов

- **Блокировка по объёму трафика** для OpenVPN и WG/AWG: лимит в БД (`traffic_limit_bytes` в `wg_access_policy` / `openvpn_access_policy`), учёт потреблённого трафика из `user_traffic_stat_protocol`, автоматическая блокировка при превышении (`block_reason=traffic_limit`, `block_mode=traffic_limit`; `traffic_limit.py`, `wg_access_policy.py`, `openvpn_access_policy.py`).
- **Периодические лимиты (1 / 7 / 30 дней)**: поле `traffic_limit_period_days`; потребление по **календарным** периодам (UTC): сутки 00:00–23:59:59, неделя пн–вс, месяц с 1-го по последний день. Блокировка **временная** — при наступлении нового периода reconcile снимает её; для legacy-лимитов без периода — all-time из `user_traffic_stat_protocol`.
- **API**: `POST /api/wg/client-access` и `POST /api/openvpn/client-block` — `set_traffic_limit` (`limit_value`, `limit_unit`: MB/GB/TB, `limit_period_days`: 1/7/30) и `clear_traffic_limit`; при разблокировке без снятия лимита — `409` с `error_code=traffic_limit_exceeded`.
- **UI главной**: в модалке лимита — выбор периода; в карточке — лимит, период, использовано и остаток; на графике «Трафик клиента (БД)» — линия накопленного трафика и пунктирная линия лимита.
- **Автосверка после sync трафика**: hook `on_after_persist` в `TrafficPersistenceService` вызывает reconcile для клиентов с активным лимитом (cron `utils/traffic_sync.py`).
- **Telegram-уведомления**: при автоблокировке (`traffic_limit_block`) и авторазблокировке в новом периоде (`traffic_limit_unblock`); событие `traffic_limit` в настройках TG-уведомлений; дедупликация по периоду в памяти процесса (`traffic_limit_notify.py`, `admin_notify.py`).

### UI главной — карточки и модалки клиентов

- **Карточки клиентов**: переработан layout — имя и статус в одной строке, stat-пилюли онлайн/7д/30д из `client_details_payload`, бейдж срока сертификата, блокировка и лимит трафика с mini-bar, цветной акцент статуса, кнопка «Открыть действия и график» внизу; сетка **5 колонок** на широких экранах (≥1500px), независимая высота карточек в ряду (`_macros.html`, `styles_index.css`, `page-core.js`, `page_context.py`).
- **Компактный layout (v3)**: бейджи статуса и сертификата в одной строке, статистика 2×2 (онлайн с пульсирующей точкой, трафик 7д/30д), «Был» из `last_seen_at`, подписи «Сертификат»/«Срок» по протоколу, компактный алерт блокировки, усиленный hover.
- **Типографика и переносы**: увеличены шрифты (имя, бейджи, трафик, сертификат, блокировка); дата сертификата и «· N дн.» в одной группе, алерт блокировки в две строки, «Превышен» на отдельной строке, подпись «БЫЛ» единообразно; полное имя с переносом вместо обрезки.
- **Модалка «Открыть действия и график»**: липкий заголовок со статус-чипами, сводка и трафик в stat-pills, ограничения в отдельной секции, сегментированные кнопки диапазона графика, заметнее линия лимита, спиннер загрузки (`_client_details_modal.html`, `client-details.js`).

### Редактор файлов

- **`deny-ips.txt` в веб-редакторе**: файл добавлен в каталог редактора и группу «Безопасность» (`file_editor.py`, `editor_metadata.py`, `file_groups.py`).

### Установка и обновление

- **script_sh/env_defaults.sh**: общий модуль `ensure_env_defaults` — единый список значений по умолчанию из `.env.example` (пути, сессии, IP, бэкапы, фоновые задачи, `FEATURE_*_ENABLED`, мониторинг, CIDR); существующие ключи не перезаписываются.
- **install.sh**: bootstrap подключает `env_defaults.sh` вместо дублирования логики.
- **adminpanel.sh**: при `--install` и `--update` вызывает `ensure_env_defaults` (раньше задавались только `ALLOWED_IPS`, `IP_RESTRICTION_MODE` и `OPENVPN_ROUTE_TOTAL_CIDR_LIMIT`, причём первые два перезаписывались). `SECRET_KEY`, порт и HTTPS по-прежнему задаёт `ssl_setup.sh`.

### Исправлено

- **Страница входа**: при автозаполнении логина/пароля браузером текст читаем на тёмной теме — тёмный фон вместо жёлтой подсветки, светлый текст, подпись поля поднимается вверх (`login_styles.css`, `main.js`).
- **Настройки (500)**: `tab_state` объявляется до `{% block content %}`, чтобы Jinja видела переменную в `{% block scripts %}` при активации первой доступной вкладки (`settings.html`).
- **Главная (500)**: исправлена ошибка Jinja `round` на списке в расчёте процента progress-bar при клиентах с лимитом трафика (`_macros.html`).
- **Карточки клиентов**: блок статистики (онлайн, 7д/30д, «Был») всегда отображается — при отсутствии данных «—» / «нет данных»; сопоставление имён без учёта регистра; у активных клиентов без лимита — строка «Трафик · Лимит не задан».
- **OpenVPN — авторазблокировка**: `reconcile_all` больше не превращает устаревшие banlist-записи от `traffic_limit` в `is_permanent_blocked`; при `set_traffic_limit` / `clear_traffic_limit` reconcile снимает ошибочную permanent-блокировку, если потребление ниже нового лимита.
- **Бейдж сертификата**: «Сертификат истёк» не показывается для свежих 1-дневных сертификатов — `days_left=0` при остатке <24 ч считается «истекающим» (`access_remaining.py`).

### Тесты

- **`tests/test_feature_toggles.py`**: реестр переключателей, guards, POST-сохранение, cron/scheduler, рендер вкладки, метаданные нагрузки, `tab_state` в `settings.html`.
- **`tests/test_traffic_limit.py`**, **`tests/test_traffic_limit_notify.py`**: календарные периоды, reconcile, API, TG-уведомления.
- Обновлены **`tests/test_openvpn_access_policy_service.py`**, **`tests/test_wg_access_policy_service.py`**, **`tests/test_admin_notify.py`**, **`tests/test_index_page_context.py`**, **`tests/test_access_remaining.py`**, **`tests/test_settings_page_context.py`**, **`tests/test_edit_files_page_context.py`**, **`tests/test_catalog_data.py`**.

## [1.8.1] – 03.06.2026

### Безопасность

- **Валидация имени клиента** перед вызовом `client.sh`: на `POST /` и `POST /api/wg/client-access` проверка `CLIENT_NAME_PATTERN` (`^[A-Za-z0-9_-]{1,64}$`); при несовпадении — `400`, скрипт не запускается (`routes/index/routes.py`, проброс паттерна из `routes/route_wiring.py`).
- **`ScriptExecutor`**: убран лишний `shlex.quote()` при передаче имени в argv-list (`subprocess` без `shell=True`) — кавычки больше не попадают в аргумент (`core/services/script_executor.py`).
- **Rate limiting и IP клиента**: ключ Flask-Limiter строится через единый `_get_client_ip()` с учётом `TRUSTED_PROXY_IPS` (как в `IPRestriction.get_client_ip()`), а не из первого значения `X-Forwarded-For` без проверки — закрыт обход лимитов подменой заголовка (`core/bootstrap.py`, `app.py`).
- **`POST /api/tests/run`**: whitelist pytest nodeid (`^tests/[\w./-]+(::[\w\[\].\-]+)*$`); отклоняются значения с `-` в начале (флаги pytest) и с `..` (path traversal); вынесено в `routes/settings/api_tests.py`.
- **RBAC**: страницы **«Мониторинг сервера»** и **«Журнал логов»**, API `/api/bw`, `/api/system-info` и WebSocket `/ws/monitor` — только для **admin** (`@admin_required`); в WS дополнительно `auth_manager.is_current_user_admin()` (`routes/server_monitor/routes.py`, `routes/logs_dashboard/routes.py`, `core/services/auth_manager.py`).
- **`GET /public_download/<router>`**: отдельный лимит **30/min** по IP (через унифицированный client IP), логирование обращений (IP, router) при отказе и успехе; поведение при `PUBLIC_DOWNLOAD_ENABLED=false` без изменений (`routes/config_routes.py`).
- **Восстановление бэкапа**: распаковка во **staging** (`tempfile.mkdtemp` в `/var/tmp`) с контролируемым копированием на места вместо `tar.extractall("/")`; до распаковки отклоняются symlink/hardlink, device-файлы, абсолютные пути и `..` (`core/services/backup_manager.py`).

### Устойчивость и эксплуатация

- **Rate limiter backend**: `RATELIMIT_STORAGE_URI` (по умолчанию `memory://`); предупреждение в лог при in-memory storage и при отсутствии Flask-Limiter — для production рекомендуется Redis (`core/bootstrap.py`).
- **Главная страница**: тяжёлый reconcile политик OpenVPN/WG на `GET /` — не чаще **45 с** (debounce в памяти процесса); мутирующие `POST` синхронизируют политики без ограничения TTL (`routes/index/routes.py`, константа `INDEX_RECONCILE_TTL_SECONDS`).
- **Время в UTC**: отказ от `datetime.utcnow()` — везде `datetime.now(timezone.utc)`; хелпер **`core/services/time_utils.py::as_utc()`** для сравнения naive-значений из БД с aware-метками (политики доступа, QR-токены, трафик, кэши, модели).
- **Сессии**: `SESSION_REFRESH_EACH_REQUEST = True` — продление cookie при активности в пределах `PERMANENT_SESSION_LIFETIME` (`core/services/session_security.py`).
- **Логирование**: `app.logger.exception` / `warning` в широких `except` при старте reconcile, фоновых задачах и `POST /` на главной (`app.py`, `core/services/background_tasks.py`, `routes/index/routes.py`).
- **Фоновая задача doall**: после успешного `doall.sh` автоматически вызывается **`client.sh 7`** (пересоздание файлов профилей клиентов); каталог AntiZapret — `APP_BACKUP_AZ_INSTALL_DIR` / `ANTIZAPRET_INSTALL_DIR` или `/root/antizapret`; stdout/stderr обоих шагов объединяются в вывод задачи (`core/services/background_tasks.py`).

### Архитектура приложения

- **Application factory**: создание Flask-приложения вынесено в **`create_app()`** (`core/bootstrap.py`) — конфиг сессий, CSRF, WebSocket, SQLite WAL, rate limiter; **`config/app_paths.py`** — пути AntiZapret, `CONFIG_PATHS`, `CLIENT_NAME_PATTERN` и связанные константы; `app.py` сокращён и по-прежнему экспортирует **`app`** для Gunicorn (`app:app`).
- **CIDR — модули**: каталог игровых фильтров — **`core/services/cidr/games_catalog.py`**; парсинг CIDR/ASN из ответов провайдеров — **`core/services/cidr/db_extract.py`**; публичные имена сохранены через реэкспорт из `games.py` и `db_service.py`.
- **`BASE_DIR` CIDR-пайплайна**: корень репозитория через `ADMIN_ANTIZAPRET_ROOT` или автоопределение от расположения пакета — dev-клоны и CI вне `/opt/AdminAntizapret` (`core/services/cidr/constants.py`).
- **Settings API**: обработчики разнесены по доменам — **`routes/settings/api_misc.py`**, **`api_cidr_db.py`**, **`api_tests.py`**, общие хелперы **`_api_shared.py`**; точка входа **`routes/settings/api.py`** и сигнатура `register_settings_api_routes` без изменений (совместимость с тестами, патчащими `routes.settings.api.*`).

### CSP (Content-Security-Policy)

- **script-src** без `'unsafe-inline'`: per-request **nonce** в заголовке и шаблонах (`core/services/http_security.py`, context processor).
- Inline-обработчики `on*` заменены на **`data-*`** и делегирование в **`static/assets/js/csp_handlers.js`** (`data-confirm-submit`, `data-confirm-click` и др.).
- Обновлены шаблоны: `base.html`, `login.html`, `index.html`, partials настроек, мониторинга, журнала, tg-mini (`open.html`, `blocked.html`).
- **style-src** по-прежнему с `'unsafe-inline'` (широкое использование inline `style=""` в шаблонах; перевод на nonce/hash отложен).

### CI и разработка

- **GitHub Actions** (`.github/workflows/ci.yml`): на push/PR — `ruff check .`, **`pytest tests/`** (297 тестов), **bandit** (совещательно, `continue-on-error`); на runner доустанавливаются `iptables` и `ipset` для `test_site_diagnostics`.
- **`requirements-dev.txt`**: pytest, ruff, bandit; **`pytest` убран** из production `requirements.txt`.
- **`ruff.toml`**: правила E/F/I, мягкий старт с ignore легаси-шума; исключены `venv`, `static`, кэши.
- **`.env.example`**: шаблон всех переменных окружения (секреты, Telegram, rate limit, CIDR, бэкапы, Gunicorn и др.) с комментариями.
- **Pytest на чистом runner**: suite не зависит от фиксированного `/opt/AdminAntizapret`, локального `.env` и `/root/antizapret` — временные пути игровых `AZ-Game-*`, сброс `AZ_GAME_*` env между тестами (`tests/conftest.py`, `tests/test_cidr_list_updater.py`, `tests/test_settings_api_cidr_games.py`, `tests/test_app_auto_backup.py`).

### Тесты

- Полный прогон: **297 passed**; обновлены **`tests/test_session_security.py`** (дефолт `SESSION_REFRESH_EACH_REQUEST`) и **`tests/test_settings_page_context.py`** (timezone-aware сравнение в моке).
- **`CidrListUpdaterTests`**: в `setUpClass` — временные файлы игровых фильтров и заглушка `sync_game_hosts_filter` в `file_pipeline` / `db_pipeline`, чтобы `update_cidr_files` не падал с `PermissionError` на GitHub Actions.
- **`tests/test_background_tasks_service.py`**: сценарий doall → вызов `client.sh 7` после успешного `doall.sh`.

## [1.8.0] – 02.06.2026

### Игровые фильтры маршрутизации

- CIDR для игровых фильтров строятся из **игровых IP и ASN** (`server_ips`, RIPE), а не из DNS маркетинговых доменов (Cloudflare/CDN сайтов).
- Новый модуль **`core/services/cidr/game_server_data.py`**: curated IP шардов и URL источников (LoL Wiki, FFXIV datacenter IPs, Roblox и др.).
- Приоритет резолва в **`_render_games_ips_block`**: `server_ips` → `asns` → DNS (только fallback с `# WARNING`).
- Каталог переведён на **провайдеров** (~48 карточек вместо ~75 игр): один переключатель на издателя/платформу, CIDR всех его игр объединяются автоматически.
- Ключи провайдеров (`riot_games`, `steam`, …) пишутся в `# Keys:` блока `AZ-Game-*-ips.txt`; секции в файле — по провайдеру с комментарием `# Games: …`.
- **Миграция legacy-ключей**: старые game keys (`lol`, `valorant`, …) при чтении/сохранении автоматически приводятся к provider keys; API принимает оба формата (`include_provider_keys` / `include_game_keys`).
- Конфликт include+exclude на уровне **провайдера** (например, `lol` + `valorant` → `riot_games`).
- API: `provider_filters`, `saved_provider_keys`, `source_type: servers`, `server_ip_count`, `game_count`; batch **`preview_games_batch_stats`** — одна проверка выбранных провайдеров; кэш RIPE ASN и параллельная загрузка префиксов.
- **Лимит OpenVPN / iOS (900 маршрутов)**: сумма CIDR во всех `config/*include-ips.txt` (регионы `AP-*`, базовый include, игровой блок); счётчик «Маршруты config» в UI.
- При нехватке бюджета провайдера: сначала **supernet** без пересечений (`collapse_addresses`, `netaddr.cidr_merge`), затем принудительное **сжатие** до остатка (`_compress_cidrs_to_limit`) — в preview предупреждения о неполном покрытии.
- **Отключение лимита** (опционально): переключатели в блоке «Каталог игровых провайдеров» + подтверждение рисков; настройки в `.env` (`AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT`, `AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK`); без обоих флагов сжатие по бюджету остаётся включённым.
- **Telegram и журнал**: одно уведомление при «Применить» (`sync_games_routes`); события только при реальном изменении файлов; текст `VPN: N игр, M CIDR · DIRECT: …` без ложных «игр: 0»; детали в **`audit_view_presenter`**.

### Интерфейс вкладки «Игровые серверы»

- Переработан каталог: **карточки провайдеров** с режимами **VPN / DIRECT / Не выбрано**, счётчики выбранных и видимых, кнопка «Сбросить все».
- Блок **«Каталог игровых провайдеров»**: пояснения по режимам VPN/DIRECT, файлам config, лимиту 900, сжатию при нехватке бюджета и ограничениям **include punch** (DIRECT + широкий include).
- Шапка каталога на **всю ширину**: заголовок и счётчики в одной строке; блоки лимита OpenVPN и **include punch** — в две колонки (без пустой области справа).
- Статистика в шапке: **«Маршруты config»** (`текущее / лимит` или `∞` при отключённом лимите), выбрано, видимо, домены; подсветка при приближении и превышении лимита.
- Два переключателя в блоке лимита: **отключить лимит 900** и **принятие рисков** (OpenVPN/iOS, неполное покрытие, ответственность администратора); сохранение через `POST /api/cidr-lists` (`action: set_game_filter_route_limit`).
- Поиск по названию провайдера и ключу; переключатель **«Только назначенные»**.
- Опция **«Добавлять домены (опционально)»** — по умолчанию только IP/CIDR в `AZ-Game-include-ips.txt`; домены — в `AZ-Game-include-hosts.txt`.
- На карточках: список игр провайдера, тип сети, CIDR, пересечения, число доменов; кэш статистики карточек в `localStorage` (12 ч).
- **«Проверить перед применением»**: панель с итогами (провайдеры, CIDR, неразрешённые, пересечения, бюджет маршрутов, списки конфликтов и доменов).
- Прогресс-бар с этапами, оверлей на сетке каталога и спиннер на активной кнопке; логика в **`routing-game-filters.js`**.
- **Обрезка по VPN-маршрутам**: при записи в `AZ-Game-include-ips.txt` CIDR, уже покрытые существующими `include-ips` списками, не дублируются — в файле комментарий «уже идёт через VPN»; при частичном пересечении добавляется только непокрытая часть (netaddr).
- **EXCLUDE и include punch**: при записи в `AZ-Game-exclude-ips.txt` пересекающиеся include-сети **разбиваются in-place** в исходных `include-ips` файлах (`I → I − E`); в exclude попадает непересекающаяся часть или весь CIDR при полном покрытии include. Повторное обновление CIDR БД может перезаписать разбиение; откат include при снятии DIRECT не автоматизируется.
- **Hotfix exclude preview**: безопасное вычитание CIDR через `ipaddress` (без `list(netaddr.IPSet)` на широких маршрутах); include шире `/16` не патчатся in-place — в preview предупреждение «punch пропущен»; предохранитель **64 CIDR** на операцию split.

### Исправлено

- **Dry-run генерации из БД**: исправлен вызов `estimate_cidr_matches_from_db()` — передаётся `include_game_keys` вместо несуществующего `include_provider_keys` (ошибка на шаге «Dry-run генерации из БД»).
- **Обновление CIDR-файлов** (`action: update`): тот же параметр `include_game_keys` вместо `include_provider_keys` в `update_cidr_files()`.

### Тесты

- **`tests/test_game_catalog_coverage.py`**: каждая игра в каталоге имеет `server_ips` или `asns`; LoL preview без DNS fallback.
- **`tests/test_settings_api_cidr_games.py`**, **`tests/test_cidr_list_updater.py`**, **`tests/test_routing_page_context.py`** — провайдерский каталог, миграция ключей, бюджет маршрутов, отключение лимита, batch preview и sync маршрутов.

## [1.7.8] – 01.06.2026

### База CIDR и обновление провайдеров

- Переработан пайплайн **`CidrDbUpdaterService`** (`core/services/cidr/db_service.py`): ASN берутся из URL/имён источников и сканирования, а не из статического `as_numbers` в `IP_FILES`; после загрузки префиксов пул ASN записывается в БД (`provider_asn`).
- Из **`IP_FILES`** удалены жёстко заданные `as_numbers`; **активные ASN** хранятся в БД и отражаются в API (`/api/cidr-db/status`, `/api/cidr-providers/meta`).
- Источники **`PROVIDER_SOURCES`**: убраны нестабильные **bgp.tools**; для Akamai, DigitalOcean, Hetzner, OVH — RIPE (geo + announced); Cloudflare — только официальный список `ips-v4`.
- Параллельная загрузка источников провайдера (`CIDR_DB_SOURCE_FETCH_WORKERS`, по умолчанию 4) с сохранением порядка слияния результатов; in-memory кэш ответов (`CIDR_DB_SOURCE_CACHE_TTL_SECONDS`, по умолчанию 900 с).
- Параллельная обработка провайдеров (`CIDR_DB_PROVIDER_WORKERS`) и выборка префиксов по ASN (`CIDR_DB_ASN_FETCH_WORKERS`, по умолчанию 4) без предварительного upsert в БД.
- Загрузка префиксов по ASN: таймаут **`CIDR_DB_ASN_FETCH_TIMEOUT`** (по умолчанию 30 с), до **3 повторов** при сбое, fallback через RIPE **bgp-state**; лимиты discovery — **`CIDR_DB_ASN_DISCOVERY_MAX_PER_PROVIDER`** / **`CIDR_DB_ASN_DISCOVERY_SCAN_EXTRA_LIMIT`**.
- Защита от «обнуления» пула: при сбоях ASN и малом кандидате сохраняется предыдущий набор CIDR; порог «здорового» пула — **`CIDR_DB_FALLBACK_MIN_CANDIDATE`** (по умолчанию 500), вместо жёсткого отсечения по 80% падения.
- Статус **`partial`**: в API и UI — **`partial_reasons_by_source`** (ошибки источников, ASN, fallback).
- **Dry-run refresh**: `POST /api/cidr-db/refresh` с `dry_run: true` — расчёт без записи в БД, предпросмотр `previous → final` по провайдерам.
- **Повтор failed**: `retry_failed_mode` (`last` / `selected`) — кнопки «Повторить ошибочные (последний запуск)» и «Повторить ошибочные (выбранные)».
- Деградация после **очистки БД**: ошибки ASN при большом пуле — уровень `info`; глобальное предупреждение о падении суммарного CIDR не сравнивается с записью журнала со статусом `cleared`.

### Очистка базы CIDR

- **`POST /api/cidr-db/clear`** — удаление CIDR, ASN, метаданных и снимков ASN для всех провайдеров или выбранных файлов; при полной очистке — журнал `cidr_db_refresh_log`.
- На вкладке **«Обновление IP-списков»**: кнопки **«Очистить всю БД CIDR»** и **«Очистить выбранных в БД»** с подтверждением и обновлением статуса таблицы.
- События **`settings_cidr_db_clear`** в журнале, Telegram-оповещениях и **`audit_view_presenter`**.

### Маршрутизация (интерфейс)

- Таблица **«База данных CIDR»**: убрана колонка AS; для статуса **partial** — раскрывающийся список причин по источникам.
- Баннер предупреждений скрывает уровни `info`/`none`; dry-run refresh показывает блок предпросмотра изменений.
- Статусы операций CIDR и антифильтра: **успех/ошибка** — toast (`showNotification`), **прогресс** — inline-блок без залипания классов уведомлений (`routing-page-extra.js`, `routing.js`); скрытие через атрибут `hidden`, без «залипания» `settings-inline-hidden`.
- Кнопки операций CIDR БД: **подсказки при наведении** (`data-hint`, `#cidr-db-action-hint`) с позиционированием над/под кнопкой; подписи на русском — «Повторить ошибочные», «Пробный запуск обновления».
- Поле **DPI-лога**: моноширинный шрифт, увеличенная высота, корректная ширина на узких экранах (`routing_styles.css`).

### Вёрстка страниц

- Единая ширина контейнера **как на «Мониторинг сервера»** для **маршрутизации**, **настроек** и **журнала логов** (`routing_styles.css`, `settings_page_shared.css`, `logs_dashboard/base.css`): адаптивные отступы, `safe-area`, без горизонтального overflow на мобильных.
- Удалён дублирующий блок стилей в **`logs_dashboard/base.css`**.

### Вкладка «Тесты»

- Информационный блок **«Для кого и зачем»**: pytest — инструмент разработки, не ежедневная операция на продакшене.
- У каждого теста — **русское название и описание**; технический ID pytest — во всплывающей подсказке; обновлены **`unit_tests_cli.py`** и **`_tab_tests.html`**.

### Тесты

- Расширены **`tests/test_cidr_db_updater_service.py`**: параллельные источники, retry ASN, fallback-пул, RIPE-only провайдеры (Akamai, DigitalOcean, Cloudflare), отсутствие bgp.tools, dry-run, очистка БД и алерты после `cleared`.
- **`tests/test_catalog_data.py`**: каталог метаданных pytest-тестов с русскими подписями.

## [1.7.7] – 24.05.2026

### Обслуживание и бэкапы

- Бэкап компонента **БД** создаёт снимок SQLite **без таблиц CIDR/провайдеров** (`core/services/db_backup_export.py`): архив меньше, чаще проходит лимит Telegram 50 МБ.
- В метаданных архива: `db_without_cidr`, список исключённых таблиц; в UI — «без базы CIDR провайдеров».
- После restore полного бэкапа CIDR нужно **обновить вручную** в настройках маршрутизации.
- **Авто-бэкап AntiZapret**: при включённом `APP_BACKUP_AZ_ENABLED` (по умолчанию да) cron вызывает `/root/antizapret/client.sh 8` через **`AntizapretBackupService`** после бэкапа панели.
- **Telegram**: при авто-бэкапе и `APP_BACKUP_TG_ENABLED` администраторам отправляются **два** файла — архив панели и `backup-<IP>.tar.gz` (OpenVPN, WireGuard, конфиги AZ).
- Кнопка **«Создать бэкап и отправить в TG»** — ручной прогон бэкапов панели + AZ и отправка архивов выбранным админам (`POST /api/backups/test-telegram`), без включения авто-бэкапа по расписанию.

## [1.7.6] – 23.05.2026

### Блокировка WireGuard и AmneziaWG

- На **главной** у клиентов WG/AWG: **временная** блокировка (1–3650 дней), **бессрочная** до ручной разблокировки и **снятие блокировки**; состояние хранится в БД (`wg_access_policy`).
- Блокировка применяется на уровне runtime (отключение peer в конфиге/интерфейсе): отдельный процесс через `utils/wg_awg_runtime_apply.py`, сервис **`WgAccessPolicyService`** и **`WgAwgRuntimeEnforcer`**.
- **Cron** `utils/wg_awg_policy_sync.py` (по умолчанию каждые 2 мин, `WG_POLICY_SYNC_ENABLED`, `WG_POLICY_SYNC_CRON`) — автоматическая сверка политик и повторное применение блокировок после перезапуска; задача регистрируется при старте панели через **`MaintenanceSchedulerService`**.
- Улучшена логика **разблокировки** и истечения срока: продление доступа, reconcile при истечении `expires_at`, фоновый sync после изменений с главной.
- Отображение **оставшегося срока** доступа (`format_access_remaining`) в карточке клиента.

### Блокировка OpenVPN

- Единая политика доступа **`OpenVpnAccessPolicyService`** и таблица `openvpn_access_policy` — те же сценарии, что у WG: временная/постоянная блокировка и разблокировка с главной.
- Синхронизация с существующим списком забаненных клиентов (`banned_clients`) и проверкой `client-connect`.

### Главная страница

- KPI и панель операций: счётчики заблокированных клиентов (**OpenVPN** / **WG·AWG**), сводный список блокировок.
- API `/api/wg/client-access` и `/api/openvpn/client-access`; расширены **`client-details.js`** и **`page-core.js`**.

### Уведомления в Telegram

- Оповещения администраторам переписаны в виде **связных предложений** (кто, что сделал, протокол конфига, время); для WG/AWG указывается **WireGuard/AmneziaWG**; сообщения оформлены **эмодзи** (заголовок, роль, протокол, конфиг, время).
- Вёрстка TG: **4 строки** — заголовок, актор, действие, время; эмодзи протокола и 📁 у имени конфига на строке действия.
- Блокировка клиента в TG: **временная** (срок и дата окончания) или **постоянная** / **разблокировка**; уведомления для действий WG/AWG с главной.
- Изменения настроек в TG: **полностью на русском**, без сырых ключей (`enabled=`, `cron=`); ночной рестарт, порт, QR и др. описываются понятными фразами.

### Telegram-авторизация и журнал

- Исправления и доработка сохранения настроек **Telegram Login** (вкладка «Telegram» в настройках): нормализация токена и username, единый формат записи в аудит (**`telegram_audit_details`**).
- События настроек Telegram дублируются в Telegram-аудит (`mini_settings_telegram_auth`); обновлён шаблон **`_tab_telegram_auth.html`**.
- Вкладка **«Журнал действий»**: переработанная структура (группировка по дням и сессиям), фильтры/сортировка/поиск, экспорт CSV и улучшенное представление событий в **`audit_view_presenter`**.
- Доработана адаптивность журнала для телефонов (`audit_log_mobile.css`, `settings_styles.css`); добавлены тесты по выдаче/экспорту и контексту страницы (`test_audit_view_presenter_action_logs`, `test_settings_api_action_logs_export`, `test_settings_page_context`).

### Вкладка «Пользователи»

- Редизайн блока управления пользователями: карточки с раскрывающимися секциями для роли/пароля/Telegram ID, более удобная компоновка уведомлений и улучшенные стили (`_tab_user_management.html`, `settings_styles.css`, `settings_page_shared.css`).

### Safe Browsing и безопасность HTTP

- CLI **`script_sh/safe_browsing_status_cli.py`** — проверка статуса домена в Google Safe Browsing (JSON/текст, коды выхода для мониторинга).
- Чеклист **`script_sh/safe_browsing_reclassification.md`** для снятия предупреждения Chrome после исправлений.
- Уточнены заголовки **`http_security`**: CSP, `noindex` для служебных путей (`/login`, `/tg-mini`, `/auth/` и др.).

### Белый список IP (консоль и временный доступ)

- **`adminpanel.sh`**: пункт меню **«9. Белый список IP»** и флаги `--ip-add`, `--ip-remove`, `--ip-add-temp`, `--ip-list` (модуль [`script_sh/ip_whitelist.sh`](script_sh/ip_whitelist.sh), CLI [`script_sh/ip_whitelist_cli.py`](script_sh/ip_whitelist_cli.py)).
- Вкладка **«Безопасность»**: добавление IP **на 1 ч / 12 ч / 24 ч** (только при включённых IP-ограничениях); постоянные записи — как раньше.
- Хранение временных адресов в [`data/temporary_whitelist.json`](data/temporary_whitelist.json); учёт в проверке доступа и синхронизации iptables whitelist порта.

### Обслуживание и бэкапы

- В **`Настройки` → «Обслуживание системы»** — полноценное управление резервными копиями через **`BackupManagerService`**: ручное создание, **восстановление** (остановка/запуск `admin-antizapret`), **удаление** архива, таблица существующих бэкапов.
- Состав архива на выбор: **SQLite** в `instance/`, **`.env`**, файлы **`data/`** (временный whitelist, баны сканера); метаданные `.meta.json`, понятное описание состава в списке (в т.ч. для старых скриптовых бэкапов только БД).
- **Авто-бэкап** по расписанию: интервал **1 / 7 / 30** дней и время запуска; cron через **`utils/app_auto_backup.py`**, регистрация в **`MaintenanceSchedulerService`**; настройки в `.env` (`APP_BACKUP_*`).
- **Telegram**: опциональная отправка файла архива выбранным администраторам (только при авто-бэкапе, `APP_BACKUP_TG_ENABLED`, `APP_BACKUP_TG_ADMIN_IDS`).
- Хранение не более **5** последних `.tar.gz` в каталоге по умолчанию `/var/backups/antizapret` (`APP_BACKUP_ROOT`); устаревшие удаляются автоматически.
- REST API **`/api/backups`** (список, настройки, создание, восстановление, удаление) и фронтенд **`settings-maintenance-backup.js`** — обновление таблицы без полной перезагрузки страницы.
- События бэкапов в **журнале** и **TG-оповещениях** администраторам на русском (`settings_backup_*`, форматирование в **`audit_view_presenter`**).

### Вкладка «Обслуживание системы» (интерфейс)

- Переработанный дизайн вкладки: KPI-полоса (активные сессии, ночной рестарт, авто-бэкап, число архивов), секции с иконками и отдельными стилями **`settings_maintenance.css`**.
- Ночной рестарт: слайдеры TTL и heartbeat сессии, сворачиваемый блок cron; блок перезапуска службы с оверлеем ожидания.
- Бэкапы: карточки выбора компонентов, **чипы** получателей Telegram, таблица архивов с бейджами `db` / `env` / `data` и кнопками «Восстановить» / «Удалить».

### Прочее

- Удалён фоновый **`login-bg.png`** (~315 KB): фон панели и входа — CSS-градиент (как у `index-page-dark`), без лишней загрузки изображения.
- В **Telegram Mini App** инструкции по импорту WG/AWG переведены на русские формулировки кнопок и меню.
- Миграции БД для таблиц политик WG/OpenVPN; unit-тесты политик доступа, бэкапов и обслуживания (`test_backup_manager_service`, `test_app_auto_backup`, `test_maintenance_scheduler_backup`, `test_wg_access_policy_service`, `test_openvpn_access_policy_service`, `test_wg_awg_runtime_enforcer`, `test_index_routes_wg_access` и др.).

## [1.7.5] – 18.05.2026

### Блокировка порта панели на уровне сервера (iptables)

- Во вкладке **«Безопасность»** — переключатель **«Блок на порту панели (iptables)»**: с разрешённых IP из белого списка пускает на порт приложения (`APP_PORT`), остальных режет **до HTTP** (аналог ufw только для порта панели). Только **IPv4**.
- Доступно при **прямом** доступе к панели: HTTP или HTTPS на Gunicorn (`BIND` не `127.0.0.1`). Если панель за **Nginx** (`BIND=127.0.0.1`) — опция недоступна (серый блок): снаружи гости идут на 80/443, достаточно whitelist в приложении.
- Модуль **`utils/panel_port_firewall.py`**, синхронизация из **`IPRestriction.sync_whitelist_port_firewall()`** при старте, сохранении whitelist и настроек защиты.
- Установка и проверки окружения: обязательные пакеты **`iptables`** и **`ipset`**, проверка в `install.sh`, `adminpanel.sh verify`, общем тесте (`system_preflight`) и диагностике сайта (`site_diagnostics`).

## [1.7.4] – 17.05.2026

### Рефакторинг и модульная структура

Крупное разбиение страниц и сервисов на отдельные пакеты — поведение для пользователя сохранено, код проще сопровождать и тестировать.

### Страницы панели

- **Главная** (`/`): логика в `core/services/index/`, маршруты в `routes/index/`, шаблон разбит на `templates/partials/index/`, фронтенд — `page-core.js` и `client-details.js`.
- **Редактор файлов**: сервисы в `core/services/edit_files/`, маршруты в `routes/edit_files/`, partials для боковой панели и редактора, отдельный модуль сравнения `diff.js`.
- **Монитор сервера**: `core/services/server_monitor/` (метрики системы и трафик по интерфейсам), `routes/server_monitor/`, JS-модули `bandwidth.js`, `system-metrics.js`, `chart-theme.js`.
- **Журнал / дашборд логов**: пакет `core/services/logs_dashboard/` с подмодулем `collector/` (события, сводка, трафик), API и страница в `routes/logs_dashboard/`, стили разнесены по `static/assets/css/logs_dashboard/`.
- **Маршрутизация**: контекст страницы в `core/services/routing/`, маршруты в `routes/routing/`; стили и скрипты маршрутизации отделены от настроек (`routing_styles.css`, `routing.js`, `routing-page-extra.js`).
- **Настройки**: `core/services/settings/` с обработчиками POST по вкладкам (пользователи, безопасность, Telegram, QR, VPN/сеть, обслуживание); маршруты в `routes/settings/` (`routes.py`, `api.py`, `antizapret.py`); убрана устаревшая страница `ip_settings.html`.

### Telegram Mini App и блокировка IP

- Mini App вынесен в отдельный пакет **`tg_mini/`** (Blueprint, `routes/`, `services/`, статика и шаблоны); код убран из общих `config_routes` и `monitoring_routes`.
- Страница **«IP заблокирован»** — пакет **`ip_blocked/`** со своими шаблоном, CSS и JS; монолитный `templates/ip_blocked.html` удалён.

### Сервис CIDR и уведомления

- Обновление IP-списков разбито на модули **`core/services/cidr/`**: база и пайплайны (`db_service`, `db_pipeline`, `file_pipeline`), провайдеры, гео, игры, DPI, antifilter, лимиты маршрутов; совместимость через `facade_compat`.
- Единый модуль всплывающих уведомлений **`notifications.js`** и обновлённые стили; страницы панели и входа подключены к общему механизму.

## [1.7.3] – 16.05.2026

### Защита от IP-сканеров

- Панель запоминает подозрительные адреса и может надолго их блокировать. Список банов сохраняется между перезапусками (файл `data/scanner_blocks.json`).
- При желании блокировки можно дублировать на уровне firewall (ipset/iptables) — включается в настройках окружения.
- Вкладка **«Безопасность»** обновлена: наглядная сводка (белый список, число банов, пауза после разбана), быстрый вкл/выкл IP-ограничений, формы для настройки антискана и разбана одного адреса.
- Страница **«IP заблокирован»** оформлена единообразно и подсказывает, что делать дальше.

### Telegram Mini App

- Вход через Mini App проверяется по официальным правилам Telegram — подделать данные авторизации сложнее.
- Обновлён внешний вид и поведение Mini App под современные клиенты Telegram.

### Уведомления в Telegram

- Если настроен бот авторизации, в Telegram можно получать сообщения о **входе в панель** — и при успехе, и при ошибке.
- Во вкладке **«Пользователи»** для каждого пользователя: настройки уведомлений, интервал между сообщениями и кнопка **«Тест уведомлений»**.

### Удобнее на телефоне

- Улучшено отображение **журнала аудита**, **логов**, **монитора сервера**, **настроек** и **меню** на узких экранах.
- Всплывающие уведомления в интерфейсе оформлены единообразно на всех страницах.

### Маршрутизация

- На странице **«Маршрутизация»** понятнее показана сводка по AntiZapret и спискам IP.
- Исправлены ошибки при сборке IP-списков и объединении диапазонов (CIDR).

### Вкладка «Тесты»

- Видно, сколько тестов запланировано и как идёт выполнение.
- Кратко описано, что проверяется (ядро, IP-диапазоны, защита, авторизация).
- После прогона можно посмотреть полный текстовый отчёт.

### Безопасность сайта и меньше ложных тревог

- На все страницы панели добавлены стандартные заголовки защиты браузера.
- Страницы входа, скачивания и блокировки не предлагаются поисковикам для индексации.
- Добавлены **`/robots.txt`** и **`/.well-known/security.txt`**: закрыта индексация чувствительных путей; в текстах нет указания на тип сервиса (нейтральная «панель администрирования»).
- Экран **входа** и страница **PIN для QR-скачивания** выглядят одинаково; название панели берётся из настроек (`PANEL_BRAND_NAME`, `DOMAIN`).
- В мастере HTTPS — отдельный рекомендуемый вариант: **Nginx + Let's Encrypt**; в конфиг Nginx добавлены те же заголовки безопасности, что и в приложении.

### Настройки: как открыта панель

- На вкладке **«VPN / сеть»** блок **«Порт, HTTPS и Nginx»**: панель сама определяет, как вы к ней подключаетесь (HTTP, HTTPS напрямую, через Nginx и т.д.), показывает адрес, ссылки для входа и подсказку по переменным в `.env`.

### Установка

- **`install.sh`**: проверка, что репозиторий целый; предупреждение, если рядом нет **AntiZapret-VPN**; можно указать свой URL репозитория; установлены пакеты, нужные для сборки Python-зависимостей.
- **`adminpanel.sh`**: больше проверок перед установкой; блок про **AntiZapret-VPN**; повторный запуск не ломает уже созданное виртуальное окружение; в конце выводится правильная ссылка (HTTP или HTTPS, с портом или без).

### Прочее

- С главной убран переключатель **«Режим экрана»**.
- Добавлены и обновлены автотесты под новые функции.

## [1.7.2] – 09.05.2026

### Новая страница «Маршрутизация»

- Добавлен отдельный раздел **«Маршрутизация»** в боковом меню — теперь всё управление тем, какой трафик идёт через AntiZapret, вынесено в одно место.
- Три вкладки: **Фильтры и сервисы** (переключатели маршрутизации по сервисам), **Обновление IP-списков** (база CIDR, выбор провайдеров и гео-регионов), **Игровые серверы** (игровые издательства и платформы).

### Вкладка «Фильтры и сервисы»

- Переключатели для включения маршрутизации конкретных сервисов через AntiZapret: Discord, Cloudflare, Telegram, WhatsApp, Roblox, а также крупных провайдеров (Google, Amazon, Akamai, DigitalOcean, Hetzner, OVH).
- Управление защитными фильтрами: SSH-защита, Torrent Guard, антискан, ограничение форвардинга, WARP и другие.
- Все изменения применяются кнопкой **«Применить»** без ручной правки файлов.

### Вкладка «Обновление IP-списков» и CIDR-база

- Новый сервис `cidr_list_updater`: загружает актуальные IP-диапазоны из официальных ASN через RIPE API и кэширует их в локальной базе.
- Таблица провайдеров с количеством CIDR, датой обновления и статусом: Cloudflare, Google, Amazon, Akamai, DigitalOcean, Hetzner, OVH и другие.
- Гео-фильтр по регионам: выбор страны/региона при генерации маршрутов с готовыми пресетами (Только Европа, Европа + Азия, Европа + Сев. Америка, Обе Америки).
- Генерация файлов маршрутизации выполняется локально из базы — без обращения к интернету в момент применения.
- Добавлена зависимость `netaddr` для CIDR-агрегации.

### Умное ограничение маршрутов для iPhone и iPad

- Защита от переполнения таблицы маршрутов на устройствах Apple (iOS/OpenVPN поддерживает не более 900 CIDR-маршрутов).
- При генерации панель автоматически агрегирует и обрезает суммарное число маршрутов до лимита `OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS` (по умолчанию 900).
- Приоритизация: при нехватке бюджета менее важные провайдеры обрезаются первыми; обязательные диапазоны защищены.

### Вкладка «Игровые серверы»

- Выбор игровых издательств и платформ (Valve/Steam, Epic Games, Riot Games и другие) для маршрутизации через AntiZapret.
- IP-диапазоны загружаются автоматически из официальных ASN через RIPE API или DNS-резолвом доменов при каждом применении.
- Поиск по издательству или игре прямо в интерфейсе.

### Вкладка «Обновления» в настройках

- В разделе **Настройки** появилась вкладка **«Обновления»**: показывает, актуальна ли сейчас версия панели.
- Отображается текущая версия и дата последнего обновления.
- Если есть новая версия — кнопка «Обновить» подсвечивается, одним нажатием панель обновляется и перезагружается.
- Прямо в интерфейсе отображается список изменений последней версии.

### Вкладка «Тесты» в настройках

- В разделе **Настройки** появилась вкладка **«Тесты»**: запускает автотесты системы (pytest) прямо из веб-интерфейса.
- Отображается сводка: сколько тестов прошло, упало и всего.
- Тесты покрывают логику CIDR-агрегации и ограничения маршрутов.

### Улучшения на мобильных устройствах

- Боковое меню, страница маршрутизации, редактор файлов и монитор сервера теперь корректно работают на телефонах и планшетах: убраны переполнения текста, улучшена прокрутка и отступы.

### Улучшенный редактор файлов

- Навигация между файлами стала плавнее — переключение без перезагрузки страницы.
- Улучшен внешний вид боковой панели и области редактирования.

### Архитектурные улучшения фронтенда

- Шаблоны `settings.html`, `routing.html` и `logs_dashboard.html` разбиты на частичные файлы (partials): каждая вкладка — отдельный файл, что упрощает поддержку.
- JavaScript вынесен в отдельные модули: `settings-page-extra.js`, `routing-page-extra.js`, `logs_dashboard-page-extra.js`.

### Обновлённые списки IP-адресов

- Обновлены эталонные базовые диапазоны (baseline) для Cloudflare, Google, DigitalOcean, Hetzner, OVH, Amazon, Akamai до актуальных значений.

## [1.7.1] – 01.05.2026

### Ключевые улучшения

- Обновлен пользовательский интерфейс на основных страницах: главная, настройки, мониторинг, дашборд логов, вход и Telegram Mini App.
- На главной странице добавлены операционные KPI и улучшено отображение статусов сервисов, чтобы быстрее оценивать состояние системы.
- В настройках улучшена структура разделов и сценарии управления безопасностью и IP-ограничениями.

### Безопасность и доступ

- Усилена защита входа и сессий: более строгие правила для cookie и сессий, а также ограничение частоты запросов на auth-эндпоинты.
- Поведение под HTTPS и reverse proxy стало более предсказуемым: security-параметры синхронизируются автоматически.
- Доступ viewer к конфигам стал точнее: права разграничиваются с учетом типа протокола, что устраняет конфликты для одноименных конфигов.

### Стабильность и производительность

- Улучшена устойчивость фоновых и внешних I/O операций (включая обращения к Telegram API).
- Усилены миграции БД и индексация ключевых таблиц для более стабильной работы на растущих данных.
- Runtime-настройки переведены на более безопасную модель обновления в процессе работы сервиса.

### Исправлено

- Исправлен расчет активности в протокольной статистике трафика: статусы клиентов теперь определяются корректнее.
- Исправлена обработка массового включения IP-ограничений: сначала полная валидация списка, затем применение.
- Улучшена диагностируемость ошибок в служебных скриптах и сервисах за счет унифицированного logging.

## [1.7.0] – 12.04.2026

### Рефакторинг архитектуры (break-monolith)

### Разделение монолита

- **`app.py` сокращён с ~6,700 до ~1,060 строк** (~84% уменьшение)
- Бизнес-логика извлечена в **27 независимых сервисных модулей** в `core/services/`
- Маршруты вынесены в **6 отдельных модулей** в `routes/`
- Все модели SQLAlchemy централизованы в `core/models.py` (14 моделей)
- Добавлена документация архитектуры: `PROJECT_MAP.md`

### Архитектурные паттерны

- **Composition Root**: `app.py` создаёт приложение, инициализирует сервисы и регистрирует маршруты
- **Dependency Injection**: фабрика `build_services()` в `service_container.py` собирает все сервисы с инъекцией зависимостей через callbacks
- **Route Wiring**: `register_all_routes()` распределяет зависимости по модулям маршрутов через `deps` словарь
- **Thin Wrappers**: хелперы в `app.py` (`_get_env_value`, `_log_telegram_audit_event`, `_enqueue_background_task`) передаются как callback'и

### Извлечённые сервисы

| Сервис | Назначение |
| --- | --- |
| `ActiveWebSessionService` | Отслеживание активных веб-сессий |
| `AuthenticationManager` | Декораторы `login_required`, `admin_required` |
| `BackgroundTaskService` | Очередь фоновых задач на ThreadPoolExecutor |
| `CaptchaGenerator` | Генерация CAPTCHA-изображений |
| `ClientProtocolCatalogService` | Маппинг клиент → протокол |
| `ConfigAccessService` | Управление доступом viewer к конфигам |
| `ConfigFileHandler` | Поиск конфигов, проверка сроков сертификатов |
| `DatabaseMigrationService` | Инкрементальные миграции БД |
| `EnvFileService` | Чтение/запись `.env` файла |
| `FileEditor` | CRUD текстовых файлов маршрутов |
| `FileValidator` | Decorator для валидации файлов |
| `LogsDashboardCacheService` | Кэширование данных dashboard с TTL |
| `LogsDashboardCollector` | Агрегация статусов/событий OpenVPN/WireGuard |
| `MaintenanceSchedulerService` | Управление cron-задачами |
| `NetworkStatusCollectorService` | Парсинг статусов OpenVPN/WireGuard |
| `OpenVPNBanlistService` | Управление списком заблокированных клиентов |
| `OpenVPNSocketReaderService` | Чтение из Unix-сокетов OpenVPN management |
| `PeerInfoCacheService` | Кэш версий/платформ OpenVPN-клиентов |
| `QrDownloadTokenService` | Одноразовые ссылки с PIN/audit |
| `QRGenerator` | Генерация QR-кодов |
| `RuntimeSettingsService` | Загрузка runtime/env настроек |
| `ScriptExecutor` | Обёртка над `client.sh` |
| `ServerMonitor` | Мониторинг CPU/RAM/диска |
| `TrafficMaintenanceService` | Сброс/пересборка статистики трафика |
| `TrafficPersistenceService` | Сохранение/агрегация дельт трафика |


### Добавлено

### Telegram Mini App

- Полноценное Telegram Web App для управления VPN через встроенный браузер Telegram
- **Новые файлы**: `templates/tg_mini_app.html` (269 строк), `static/assets/css/tg_mini_app.css` (833 строки), `static/assets/js/tg_mini_app.js` (1,606 строк)
- Управление конфигами VPN (OpenVPN, WireGuard, AmneziaWG) прямо из Telegram
- Модель `TelegramMiniAuditLog` — отдельный журнал аудита событий Mini App
- Модель `TelegramMiniAuditLog` + `UserActionLog` для единого журнала действий
- API `/api/tg-mini/settings` (GET/POST) — чтение/запись настроек порта, ночного рестарта, Telegram auth
- API `/api/tg-mini/dashboard` — данные дашборда для Mini App
- API `/api/tg-mini/openvpn` — список OpenVPN-клиентов для Mini App
- API `/api/tg-mini/send-config` — отправка конфига через Telegram бот
- Эндпоинт `/auth/telegram-mini` — аутентификация через WebAppData (проверка HMAC-подписи)
- Эндпоинт `/tg-mini` — основной интерфейс Mini App

### Telegram авторизация

- Авторизация через **Telegram Login Widget** с HMAC-верификацией (`hash` field)
- Тайминг-безопасное сравнение через `hmac.compare_digest`
- Новые переменные окружения:
  - `TELEGRAM_AUTH_BOT_USERNAME` — username бота для виджета
  - `TELEGRAM_AUTH_BOT_TOKEN` — токен бота для верификации
  - `TELEGRAM_AUTH_MAX_AGE_SECONDS` — максимальный возраст данных
  - `REMEMBER_ME_DAYS` — срок remembers сессии

### WARP интеграция

- Разделение единого флага `WARP_OUTBOUND` на два независимых:
  - `ANTIZAPRET_WARP` — маршрутизация трафика AntiZapret через Cloudflare WARP
  - `VPN_WARP` — маршрутизация всего исходящего VPN-трафика через WARP
- Поддержка включения/отключения каждого флага отдельно через настройки AntiZapret
- Исправлена маршрутизация WARP для всех VPN-протоколов

### Расширенный аудит-лог

- Модель `UserActionLog` — журнал действий пользователей с тегами источника
- Источники событий: `web`, `miniapp`, `qr`, `public`, `api`
- 30+ типов событий с русскоязычными лейблами и деталями
- Отображение аудита в настройках (`_build_telegram_mini_audit_view`, `_build_user_action_audit_view`)
- Вкладка **«Все логи»** в настройках с объединённым представлением

### Документация

- **`Telegram.md`** (230 строк) — полная документация интеграции с Telegram
- **`PROJECT_MAP.md`** — техническая карта архитектуры (+30 строк обновлений)
- Обновлён `README.md` с инструкциями по Telegram Mini App


### Новые API endpoints

| Метод | Путь | Описание |
| --- | --- |---------|
| `GET` | `/auth/telegram` | Callback Telegram Login Widget |
| `GET` | `/auth/telegram-mini` | Аутентификация Telegram Mini App (WebAppData) |
| `GET` | `/api/session-heartbeat` | Обновление метки активной сессии |
| `GET/POST` | `/api/tg-mini/settings` | Чтение/запись настроек для Mini App |
| `GET` | `/api/tg-mini/dashboard` | Данные дашборда для Mini App |
| `GET` | `/api/tg-mini/openvpn` | Список OpenVPN-клиентов |
| `POST` | `/api/tg-mini/send-config` | Отправка конфига через бот |
| `GET` | `/api/bw` | Данные vnStat bandwidth (JSON) |
| `GET` | `/api/user-traffic-chart` | Временной ряд трафика клиента |


### Новые таблицы БД

| Таблица | Назначение |
| --- | --- |
| `telegram_mini_audit_log` | Журнал событий Telegram Mini App |
| `user_action_log` | Общий журнал действий пользователей |


### Новые переменные окружения

| Переменная | Описание |
| --- | --- |
| `TELEGRAM_AUTH_BOT_USERNAME` | Username бота для Login Widget |
| `TELEGRAM_AUTH_BOT_TOKEN` | Токен бота для HMAC-верификации |
| `TELEGRAM_AUTH_MAX_AGE_SECONDS` | Максимальный возраст данных авторизации |
| `REMEMBER_ME_DAYS` | Срок сохранения сессии |
| `ANTIZAPRET_WARP` | Флаг WARP для AntiZapret трафика |
| `VPN_WARP` | Флаг WARP для всего VPN-трафика |

## [1.6.1] – 09.04.2026

### Добавлено

- `install.sh`: новый режим `--check` (preflight-проверка окружения без установки) и справка `--help`.
- `install.sh`: в модалке помощи задокументированы режимы `--install`, `--check`, `--help`.
- Главная страница (`index`): в диалоге продления сертификата OpenVPN добавлен альтернативный ввод через дату окончания с автопересчётом в дни.

### Изменено

- `install.sh`: унифицированы списки обязательных команд/пакетов (`REQUIRED_COMMANDS`, `REQUIRED_PACKAGES`) и их использование между preflight и установкой.
- `install.sh`: добавлена явная проверка поддерживаемой ОС перед установкой (Ubuntu 24.x, Debian 13.x).
- `README.md`: обновлены требования по ОС (Ubuntu 24.04 / Debian 13) и добавлена инструкция по быстрому запуску проверки окружения через `./install.sh --check`.
- `styles_index.css`: добавлены стили подсказок и мета-блока для нового сценария продления сертификата по дате.

### Исправлено

- `script_sh/adminpanel.sh` и `script_sh/fix_vnstat.sh`: поиск unit-файла `vnstat.service` теперь выполняется через `systemctl show -P FragmentPath` с fallback на `/lib/systemd/system` и `/usr/lib/systemd/system`.
- `script_sh/adminpanel.sh` и `script_sh/fix_vnstat.sh`: устранена жёсткая привязка к одному пути unit-файла, повышена совместимость между дистрибутивами.
- `main_index_new.js`: добавлена защитная проверка доступности кнопки перед выполнением действия продления сертификата.
- `requirements.txt`: обновлены зависимости для совместимости установки на Debian/Ubuntu (`Pillow 11.0.0`, `SQLAlchemy 2.0.36`, `Flask-SQLAlchemy 3.1.1`).

## [1.6.0] – 04.04.2026

### Добавлено

### Поддержка WireGuard/AmneziaWG в мониторинге трафика

- Сбор трафика расширен на WireGuard/AWG через `wg show all dump`; новая таблица `wireguard_peer_cache` хранит соответствие `interface+peer_public_key → имя клиента`.
- Автоматическая синхронизация `wireguard_peer_cache` из `/etc/wireguard/{antizapret,vpn}.conf` при запуске и после операций add/delete/recreate.
- Новая таблица `user_traffic_stat_protocol` (ключ `common_name + protocol_type`) для раздельного учёта трафика OpenVPN и WireGuard у одного клиента.
- Новое поле `user_traffic_sample.protocol_type` (`openvpn | wireguard`); миграция добавляет колонку с `DEFAULT 'openvpn'`.
- Действие `logs_rebase_wireguard_baseline` — безопасная перебазировка счётчиков WG без сброса накопленной статистики.
- Фильтр протокола в таблицах `Трафик (БД)`: приоритет строится по фактическим сэмплам, конфиги используются как fallback.

### Поддержка OpenVPN management socket

- Статус и события клиентов теперь читаются из Unix-сокетов OpenVPN management (`status 3`, `log N`) вместо файлов логов.
- Автоопределение пути сокета через `_openvpn_socket_path(profile_key)`; при недоступности сокета — fallback на файл.
- Настраиваемый лимит объёма ответа (`OPENVPN_EVENT_MAX_RESPONSE_BYTES`, по умолчанию 1 MiB) для защиты от утечки памяти при `log all`.
- Управление режимом хвоста: `OPENVPN_LOG_TAIL_LINES > 0` → `log N`; `= 0` → `log all` (полный буфер процесса).
- Нормализация форматов адресов клиентов: поддержка `IP:PORT` и `udp4:IP:PORT`/`tcp4-server:IP:PORT`.
- Парсер `status 3` поддерживает табличный формат (пробелы/табы) и CSV-формат одновременно.

### Кэширование и фоновые задачи

- Новая модель `BackgroundTask` и очередь задач: `/run-doall`, `/edit-files` (POST), `/update_system`, `/api/restart-service` возвращают `202` с `task_id`.
- Новый endpoint `GET /api/tasks/<task_id>` — получение статуса фоновой задачи.
- Новая модель `LogsDashboardCache` и ленивое фоновое обновление dashboard через `BackgroundTask` (`task_type=logs_dashboard_refresh`).
- Новый endpoint `GET /api/logs_dashboard_refresh_status/<task_id>` — отслеживание статуса обновления кэша.
- TTL кэша регулируется через `LOGS_DASHBOARD_CACHE_TTL_SECONDS` (минимум 5 с, по умолчанию 45 с).
- Кэш `OpenVPNPeerInfoCache` (последняя версия/платформа клиента) и `OpenVPNPeerInfoHistory` (история за несколько дней) для fallback-подстановки при отсутствии peer info в текущем хвосте.

### Ночной автоматический перезапуск

- Новый скрипт `utils/nightly_idle_restart.py` — перезапускает сервис в настроенное время, только если нет активных веб-сессий.
- Новая модель `ActiveWebSession` — таблица активных аутентифицированных пользователей.
- Heartbeat-скрипт в `base.html`: каждую минуту отправляет запрос на `GET /api/session-heartbeat` при активной вкладке браузера.
- Новый endpoint `GET /api/session-heartbeat` — обновляет метку активности текущей сессии.
- Настройки в разделе **Settings → Ночной рестарт**: включение/выключение, время срабатывания, TTL бездействия сессии, интервал heartbeat, расширенный ввод cron-выражения.
- После сохранения настроек cron обновляется сразу через `_ensure_nightly_idle_restart_cron()`.
- Переменные окружения: `NIGHTLY_IDLE_RESTART_ENABLED`, `NIGHTLY_IDLE_RESTART_CRON`, `ACTIVE_WEB_SESSION_TTL_SECONDS`, `ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS`.

### Обновлённый UX — Dashboard подключённых клиентов

- Трёхвкладочный layout: **Обзор**, **Клиенты**, **Трафик (БД)** с сохранением активной вкладки.
- Вкладка **Обзор**: сводная карточка с `total_openvpn_sessions` / `total_wireguard_sessions`, три мини-графика (сети, устройства, протоколы), таблица по сетям с колонкой `protocol_split`.
- Вкладка **Клиенты**: карточки клиентов, фильтр по протоколу (`OpenVPN` / `WireGuard`), переключатель скрытия неактивных/возможно зависших сессий. Кастомный combobox вместо нативного `datalist` для поиска клиента.
- Детальная модалка клиента: трафик по диапазонам `1h / 24h / 7d / 30d / all`, список подключений (IP, устройство, версия). Для WG/AWG-клиентов поля устройства/версии скрыты отдельно через `show_client_meta`.
- Вкладка **Трафик (БД)**: две отдельные таблицы — активные клиенты и удалённые клиенты. Удалена лишняя колонка `Updated`. Очистка статистики по scope: `WG/AWG`, `OpenVPN`, `all`. Новый endpoint `POST /logs_dashboard/delete_deleted_client_traffic` для удаления записей по удалённым клиентам.
- Графики Chart.js инициализируются лениво при активации вкладки во избежание некорректной отрисовки на скрытых панелях.
- Авто-refresh только для активной вкладки браузера (`visibilityState`) не чаще 60 с.

### Обновлённый UX — Главная страница (`index`)

- Полный редизайн: таблицы клиентов переведены в карточки с единой модалкой **«Подробнее»**.
- В модалке `#clientDetailsActionsMain` объединены все действия: скачивание VPN/AZ конфига, генерация QR/одноразовой ссылки, блокировка/разблокировка, удаление профиля, продление сертификата OpenVPN.
- Данные передаются через `data-атрибуты` строки `.client-row` (`data-download-*`, `data-one-time-*`, `data-qr-*`, `data-delete-option`, `data-blocked`, `data-can-manage`).
- Кастомный диалог `requestRenewDays` (замена `window.prompt`) для ввода срока продления сертификата (1–3650 дней) с валидацией и закрытием по Esc/бекдропу.
- Модалка «Добавить клиента» (`#addClientModal`) вынесена в отдельный слой вместо side-drawer.
- Авто-обнаружение групп интерфейсов `_collect_bw_interface_groups()`: WireGuard-интерфейсы определяются через `ip -o link show type wireguard`.

### Обновлённый UX — Страница настроек (`settings`)

- Полный редизайн layout вкладок: унифицированные карточки, сетки, кнопки действий.
- Viewer-профили переведены в компактную сетку плиток `viewer-profile-tile`; детальное управление (доступ к конфигам, роль, пароль, удаление) открывается в полноэкранных модалках `.viewer-profile-modal`.
- Доступы к конфигам в viewer-модалке сгруппированы по протоколам (сворачиваемые секции `.viewer-config-group`), добавлены поиск и фильтр «Только выданные».
- Управление пользователями переведено на карточки `<details>` (`.user-card`) без отдельных подвкладок.
- Confirm-попап действий (`#userActionModal`) имеет `z-index` выше viewer-модалки для корректного отображения подтверждений.
- Счётчик viewer на плитке отражает число выданных групп доступа (не общее число файлов).
- Вкладка `qr-settings` переименована для пользователя в **«Одноразовые ссылки»**; журнал ссылок рендерится в адаптивном контейнере с горизонтальным скроллом.
- Блок «Публичный доступ к файлам маршрутов» удалён из вкладки viewer-access.

### Переработанная страница IP-ограничений (`ip_settings`)

- Шаблон переведён на `{% extends "base.html" %}` с унифицированным layout.
- Полностью переработаны стили: новый `.ip-settings-wrapper`, статусные бейджи `.ip-status.enabled/.disabled`, карточки секций.

### Улучшения установки и обслуживания

- `install.sh`: добавлен fail-fast с проверкой обязательных команд (`require_command`), явный список pre-required пакетов с проверкой через `dpkg-query` до запуска `apt-get install`.
- `script_sh/adminpanel.sh`: функция `generate_secret_key` с тремя fallback-источниками (`openssl` → `python3 secrets` → `/dev/urandom`).
- `script_sh/backup_functions.sh`: режим **data-only** backup — архивирует только БД (`*.db`, `*.db-wal`, `*.db-shm`) без инфраструктуры. Формирует `*.meta.txt` с метаданными бэкапа. Вспомогательная функция `append_if_exists` для безопасного формирования списка файлов.
- `script_sh/ssl_setup.sh`: функции `set_env_value` / `unset_env_value` для upsert/delete ключей в `.env` вместо append — устраняет проблему дублирования ключей (`USE_HTTPS`, `SSL_*`, `DOMAIN`).
- `script_sh/uninstall.sh`: очистка cron-маркера `adminantizapret-nightly-idle-restart` при удалении.
- `gunicorn.conf.py`: обновлены параметры конфигурации воркеров.

### Изменено

- **Таблицы трафика (Трафик (БД))**: переработаны ширины колонок, выравнивание, компактность строк; удалена колонка `Updated`.
- **Сервер-монитор (`server_monitor`)**: группы интерфейсов vnStat/WireGuard формируются динамически через `_collect_bw_interface_groups()` вместо жёстко прошитых имён.
- **Страница редактирования файлов (`edit_files`)**: исправлена инициализация активного `.nav-item` на старте через `defaultNavItem.click()`.
- **`main.js`**: обновлена логика взаимодействий для совместимости с новым layout.
- **`settings.js`**: инициализация вкладки по `.menu-item.active` вместо первого пункта меню.
- **`server_monitor.js`**: обновлена обработка динамических групп интерфейсов.
- **Стили и адаптивность**: существенно переработаны `styles_index.css`, `logs_dashboard.css`, `server_monitor_styles.css`.

### Исправлено

- **`ssl_setup.sh`**: дублирование ключей в `.env` при повторном запуске setup (старое поведение — append нового значения без удаления существующего).
- **Логика определения протоколов клиента** в фильтре dashboard: метка `row.protocols` строится по фактическим ненулевым `user_traffic_sample`, конфигурационный маппинг используется только как fallback.
- **WireGuard legacy-семплы**: семплы до миграции (`protocol_type DEFAULT 'openvpn'`) для WG-only клиентов корректно интерпретируются как `wireguard` в графиках.
- **Settings bugfixes**: исправлены ошибки отображения и взаимодействия после переработки layout вкладок.
- **Logs dashboard bugfixes**: исправлены смещения в таблицах, несогласованность размеров элементов, проблемы фильтрации.

### Новые API endpoints

| Метод | Путь | Описание |
| --- | --- |---------|
| `GET` | `/api/session-heartbeat` | Обновление метки активной веб-сессии |
| `GET` | `/api/tasks/<task_id>` | Статус фоновой задачи |
| `GET` | `/api/logs_dashboard_refresh_status/<task_id>` | Статус обновления кэша dashboard |
| `POST` | `/logs_dashboard/delete_deleted_client_traffic` | Удаление статистики по удалённым клиентам |

### Новые таблицы БД

| Таблица | Назначение |
| --- | --- |
| `user_traffic_stat_protocol` | Раздельная статистика трафика по `common_name + protocol_type` |
| `wireguard_peer_cache` | Соответствие WireGuard `peer_public_key → client_name` |
| `openvpn_peer_info_cache` | Кэш последней версии/платформы OpenVPN-клиента |
| `openvpn_peer_info_history` | История peer info за несколько дней для fallback-подстановки |
| `active_web_session` | Активные аутентифицированные веб-сессии для ночного рестарта |
| `background_task` | Очередь и статусы фоновых задач |
| `logs_dashboard_cache` | Кэш данных dashboard с TTL |

## [1.5.0] – 15.03.2026

### Добавлено

- **Расширенное управление одноразовыми QR-ссылками**:
  - Настраиваемый лимит скачиваний для новых ссылок: `1`, `3` или `5`.
  - Опциональная PIN-защита для ссылок `/qr_download/<token>`.
  - Журнал событий QR-ссылок (генерация, успешные/неуспешные попытки скачивания) с отображением в настройках.
  - Новая таблица аудита `qr_download_audit_log` в БД.

### Изменено

- **Страница "Настройки" → "QR"**:
  - Добавлены поля управления лимитом скачиваний и PIN.
  - Добавлена заметная индикация статуса PIN-защиты (активна/выключена).

- **Логика генерации одноразовых ссылок**:
  - Для токенов сохраняются `max_downloads`, `download_count`, `pin_hash`.
  - Проверка доступности ссылки теперь учитывает одновременно TTL и лимит скачиваний.

### Исправлено

- **Навигация вкладок в настройках**:
  - При загрузке страницы открывается текущая активная вкладка (`.menu-item.active`), а не всегда первый пункт меню.

- **Структура разделов настроек**:
  - Блок `Публичный доступ к файлам маршрутов` перенесен из `Ограничения по IP` в `Доступ к конфигам`.

## [1.4.1] – 15.03.2026

### Добавлено

- **Одноразовые ссылки для OpenVPN-конфигов на главной странице**:
  - Добавлен маршрут `/generate_one_time_download/<file_type>/<filename>` для генерации одноразовой ссылки скачивания.
  - В таблице OpenVPN добавлены кнопки для генерации и копирования одноразовой ссылки для `VPN` и `AZ` конфигов.
  - Реализовано копирование ссылки в буфер обмена из интерфейса без перехода на отдельную страницу.

### Изменено

- **Ограничения интерфейса для роли Viewer (главная страница OpenVPN)**:
  - Скрыта колонка `Одноразовая ссылка`.
  - Скрыта колонка `Блокировка`.
  - Скрыта информация о сертификате под именем клиента.

- **Ужесточение доступа к генерации одноразовых ссылок**:
  - Endpoint `/generate_one_time_download/<file_type>/<filename>` ограничен только ролью `admin`.

## [1.4.0] – 15.03.2026

### Добавлено

- **Одноразовые short-lived ссылки для больших конфигов WireGuard/AmneziaWG**:
  - Добавлена таблица `qr_download_token` для токенов выдачи конфигов.
  - Новый маршрут `/qr_download/<token>` для одноразового скачивания.
  - Для каждого токена поддерживаются TTL и однократное использование.
  - Время жизни настраивается через `QR_DOWNLOAD_TOKEN_TTL_SECONDS` (по умолчанию 600 сек, диапазон 60..3600).

### Изменено

- **Логика QR на главной странице**:
  - Если конфиг помещается и ожидается стабильное чтение, отображается обычный QR с содержимым.
  - Если конфиг слишком большой/плотный для стабильного сканирования, используется fallback: вместо QR показывается предупреждение и кнопка «Скопировать одноразовую ссылку».
  - Кнопка в модальном окне копирует одноразовый URL в буфер обмена.

## [1.3.0] – 09.03.2026

### Добавлено

- **Система управления IP-списками провайдеров** для AntiZapret:
  - Новый модуль `ips/ip_manager.py` для управления включением/отключением IP-диапазонов провайдеров
  - Предварительно подготовленные списки IP для популярных провайдеров:
    - Akamai (`akamai-ips.txt`) — перенаправление трафика Akamai через AntiZapret
    - Amazon (`amazon-ips.txt`) — перенаправление трафика Amazon через AntiZapret
    - DigitalOcean (`digitalocean-ips.txt`) — перенаправление трафика DigitalOcean через AntiZapret
    - Google (`google-ips.txt`) — перенаправление трафика Google через AntiZapret
    - Hetzner (`hetzner-ips.txt`) — перенаправление трафика Hetzner через AntiZapret
    - OVH (`ovh-ips.txt`) — перенаправление трафика OVH через AntiZapret
  - Веб-интерфейс в настройках AntiZapret для включения/отключения списков с помощью переключателей
  - Автоматическая синхронизация включённых списков с файлом `/root/antizapret/config/include-ips.txt`
  - Сохранение состояния включённых файлов в маркерных файлах (`.added`)
  - Интеграция с существующей системой параметров AntiZapret в `config/antizapret_params.py`

- **Расширенная поддержка файлов конфигурации AntiZapret** в веб-редакторе:
  - Добавлены новые файлы в интерфейс редактирования:
    - `allow-ips.txt`
    - `exclude-ips.txt`
    - `forward-ips.txt`
    - `include-adblock-hosts.txt`
    - `exclude-adblock-hosts.txt`
    - `remove-hosts.txt`

## [1.2.12] – 21.02.2026

### Добавлено

- **Расширенная поддержка файлов конфигурации AntiZapret** в веб-редакторе:
  - Добавлены новые файлы в интерфейс редактирования:
    - `allow-ips.txt`
    - `exclude-ips.txt`
    - `forward-ips.txt`
    - `include-adblock-hosts.txt`
    - `exclude-adblock-hosts.txt`
    - `remove-hosts.txt`

- **Полный редизайн страницы редактирования файлов** (`/edit-files`):
  - Переход на боковую навигацию (sidebar) с переключением между файлами
  - Каждая вкладка показывает понятное человеко-читаемое название и назначение файла
  - Улучшенные описания и примеры использования прямо в заголовке редактора
  - Единый стиль карточки редактора с современной подсветкой синтаксиса (моноширинный шрифт, удобные отступы)
  - Кнопка «Обновить список» (`doall.sh`) перенесена в нижнюю часть боковой панели

### Изменено

- **Рефакторинг класса `FileEditor`** в `app.py`:
  - Расширен словарь `self.files` до всех актуальных конфигурационных файлов AntiZapret
  - Теперь редактор поддерживает все 9 основных пользовательских списков

- **Полное вынесение стилей страницы редактирования**:
  - Все CSS-правила перемещены в отдельный файл `static/assets/css/edit_file.css`
  - Убрано дублирование и inline-стилей → улучшена поддерживаемость и скорость загрузки

- **Обновлён шаблон `edit_files.html`**:
  - Современная двухколоночная раскладка (sidebar + основная область)
  - Адаптивное поведение на мобильных устройствах
  - Улучшена семантика и доступность (aria-labels, правильные заголовки)
  - Текстовое поле увеличено до 22 строк по умолчанию
  - Добавлен placeholder с примерами и пояснениями формата

## [1.2.11] – 20.02.2026

### Добавлено

- **Резервные порты для OpenVPN, WireGuard и AmneziaWG**:
  - Отредактирован с `OPENVPN_80_443_TCP` на `OPENVPN_BACKUP_TCP` — включает резервные TCP-порты OpenVPN (80, 443, 504, 508).
  - Отредактирован с `OPENVPN_80_443_UDP` на `OPENVPN_BACKUP_UDP` — включает резервные UDP-порты OpenVPN (80, 443, 504, 508).
  - Новый параметр `WIREGUARD_BACKUP` — включает резервные порты WireGuard / AmneziaWG (540, 580).
  - Все параметры добавлены в `antizapret_params.py` и полностью интегрированы в веб-интерфейс настроек.

- **Поддержка Cloudflare WARP для исходящего VPN-трафика**:
  - Новый параметр `WARP_OUTBOUND` — перенаправляет весь исходящий VPN-трафик через Cloudflare WARP (улучшает устойчивость к блокировкам и может маскировать серверный трафик).

### Изменено

- **Улучшена безопасность сессий**:
  - В `app.py` установлено кастомное имя куки сессии:

    ```python
    app.config['SESSION_COOKIE_NAME'] = 'AdminAntizapretSession'

## [1.2.10] – 30.12.2025

### Добавлено

- **Отображение оставшегося срока действия сертификата OpenVPN** под именем клиента в таблице на главной странице
  - Реализован расчёт дней до истечения сертификата на основе `openssl x509 -enddate`
  - Сертификаты ищутся в директории `/etc/openvpn/client/keys/`
  - Цветовая индикация: зелёный (>90 дней), оранжевый (≤90 дней), красный (≤0 дней)
  - Поддержка формата отображения: «осталось N дн.», «истекает сегодня», «истёк N дн. назад»

### Изменено

- **Оптимизация поиска сертификатов** в методе `get_openvpn_cert_expiry` класса `ConfigFileHandler`

### Автор идеи

**@depositaire** — спасибо за крутую задумку! 🙌

## [1.2.9] – 28.12.2025

### Добавлено

- **Полный рефакторинг веб-интерфейса управления настройками AntiZapret**:
  - Централизованный конфиг всех параметров в файле `config/antizapret_params.py` (одно место для добавления/изменения параметров).
  - Роуты `/get_antizapret_settings`, `/update_antizapret_settings` и `/antizapret_settings_schema` вынесены в отдельный модуль `routes/settings_antizapret.py`.
  - Динамическая регистрация роутов через функцию `init_antizapret(app)`.
  - Новый эндпоинт `/antizapret_settings_schema` — отдаёт схему параметров (key, html_id, type) для динамической работы фронтенда.
  - Улучшена обработка значений: нормализация флагов, поддержка строковых полей (хосты), добавление новых параметров в конец файла.
  - Защита всех antizapret-роутов через `auth_manager.login_required` (применяется после полной инициализации приложения).

### Изменено

- **Структура backend-кода**:
  - Упрощена поддержка новых параметров — достаточно добавить одну запись в `antizapret_params.py`.
  - Логика чтения/записи файла `/root/antizapret/setup` стала более надёжной и читаемой.
  - Теперь фронтенд может загружать схему параметров один раз и работать с любым количеством полей без правки JavaScript.

## [1.2.8] – 15.12.2025

### Добавлено

- **Поддержка Nginx как reverse proxy с автоматической настройкой Let's Encrypt**:
  - Новый вариант установки: «Использовать Nginx как reverse proxy с сертификатами Let's Encrypt».
  - Автоматическая установка и настройка Nginx в роли терминального прокси для HTTPS.
  - Получение и применение бесплатных сертификатов Let's Encrypt (standalone-режим для надёжности).
  - Автоматический редирект с HTTP (порт 80) на HTTPS (порт 443).
  - Доступ к панели по чистому адресу `https://ваш-домен` (без указания порта).
- **Улучшенная обработка доменных имён и конфигов Nginx**:
  - Имя конфига Nginx генерируется автоматически на основе введённого домена.
  - Поддержка повторной установки/переустановки без конфликтов.
  - Автоматическая проверка существующих сертификатов — повторное получение не требуется.
- **Расширенная совместимость с iptables и портами**:
  - Временное освобождение порта 80 (удаление правил перенаправления) для получения сертификата.
  - Автоматическое восстановление всех правил после завершения.
- **Защита внутреннего порта приложения при использовании Nginx**:
  - Новая переменная `BIND=127.0.0.1` в `.env` (применяется только в режиме Nginx reverse proxy).
  - Gunicorn теперь привязывается исключительно к localhost (`127.0.0.1:$APP_PORT`).
  - Прямой доступ к панели по IP-адресу и внутреннему порту (`http://IP:PORT`) полностью закрыт извне.
  - Улучшена безопасность: приложение доступно только через Nginx (HTTPS на стандартных портах).

### Изменено

- **Финальное сообщение об успешной установке**:
  - При использовании Nginx теперь отображается адрес `https://ваш-домен` (без порта).
- **Конфигурация SSL в Nginx**:
  - Добавлены современные и безопасные параметры TLS (TLSv1.2/TLSv1.3, сильные шифры, HTTP/2, HSTS).
  - Убрана зависимость от отсутствующего в snap-версии Certbot файла `options-ssl-nginx.conf`.
- **Конфигурация Gunicorn (`gunicorn.conf.py`)**:
  - По умолчанию `0.0.0.0`, в режиме Nginx — автоматически `127.0.0.1` для защиты от прямого доступа.

## [1.2.7] – 06.12.2025

### Добавлено

- **Система ограничения доступа по IP (Whitelist)**:
  - Полноценная система белого списка IP-адресов.
  - Режимы работы:
    - `strict` (строгий) — ограничение для всего веб-интерфейса.
    - `login_only` (только для логина) — ограничение доступа только к странице авторизации.
  - Поддержка CIDR нотаций (например, `192.168.1.0/24`).
  - Автоматическое сохранение настроек в `.env` файл.
  - Страница блокировки с анимацией и обратным отсчетом (`/ip-blocked`).
- **Веб-интерфейс управления IP ограничениями**:
  - Новая вкладка «Ограничения по IP» в настройках.
  - Удобный список разрешенных IP с возможностью удаления.
  - Форма для добавления отдельных IP и подсетей.
  - Быстрая настройка несколькими IP через запятую.
  - Визуальные индикаторы статуса (включено/выключено).
  - Примеры использования с пояснениями.
- **Механизм перезапуска службы для применения IP-изменений**:
  - Кнопка «Перезапустить службу» для мгновенного применения новых IP ограничений.
  - Визуальный оверлей с обратным отсчетом (5 секунд) во время перезапуска.
  - Полная блокировка страницы во время процесса.
  - Интеграция с существующим скриптом `adminpanel.sh --restart`.

### Изменено

- **Страница настроек**:
  - Реорганизована структура вкладок: добавлена новая вкладка «Ограничения по IP».
  - Улучшена навигация и визуальный дизайн элементов управления.
- **Аутентификация**:
  - Дополнен декоратор `login_required` проверкой IP для авторизованных пользователей.
  - Обновлен роут `/login` с учетом новых IP ограничений.
  - Добавлена автоматическая очистка сессии при смене IP.
- **Безопасность**:
  - Middleware для проверки IP перед каждым запросом для обеспечения безопасности.
  - Внедрена CSRF защита для всех форм управления IP.

### Исправлено

- **Обработка ошибок и валидация**:
  - Улучшена валидация IP-адресов и корректная обработка CIDR нотаций.
  - Устранены проблемы с отображением элементов интерфейса на странице настроек.
- **Производительность**:
  - Оптимизирована проверка IP адресов для минимизации задержек.
  - Минимизировано количество обращений к файловой системе за счет кэширования настроек.

## [1.2.6] – 06.12.2025

### Добавлено

- **Умная кнопка обновления системы** в веб-интерфейсе:
  - Автоматическая проверка наличия обновлений при загрузке страницы и каждые 10 минут.
  - Два состояния кнопки:
    - **Красная** «Доступно обновление!» — если есть новые коммиты в репозитории (кнопка активна).
    - **Зелёная** «У вас последняя версия» — если панель актуальна (кнопка отключена).
  - Новый эндпоинт `/check_updates` (GET) для быстрой проверки версии.
- **Принудительное обновление системы**:
  - Новый эндпоинт `/update_system` (POST).
  - Полный сброс изменений: `git reset --hard origin/main` + `git clean -fd`.
  - Автоматическая установка зависимостей и попытка перезапуска сервиса `admin-antizapret.service`.
  - Все локальные изменения безвозвратно удаляются (с двойным подтверждением в интерфейсе).
  - После успешного обновления страница автоматически перезагружается через 3 секунды.
- **Новые параметры маршрутизации в Antizapret**:
  - `ROBLOX_INCLUDE` — перенаправление Roblox через Antizapret.
  - `WHATSAPP_INCLUDE` — перенаправление WhatsApp через Antizapret.

### Исправлено

- **Проблема с ошибками при обновлении системы**:
  - Ранее обновление падало с ошибкой, если сервис не перезапускался или возникали любые проблемы.
  - Теперь роут `/update_system` использует `check=False` и `|| true` — обновление считается успешным в любом случае (главное — файлы обновляются).
  - Даже при падении `systemctl restart` или таймаута — пользователь видит сообщение «Панель успешно обновлена!» и может просто обновить страницу.

### Изменено

- Заголовок приложения переименован с "AdminVPN Claymore" на **"AdminPanel Claymore"**.
- Кнопка обновления теперь динамически меняет цвет и состояние в зависимости от актуальности версии.

## [1.2.5] – 26.10.2025

### Исправлено

- **Проблема с завершением воркеров Gunicorn при выполнении /root/antizapret/doall.sh**:
  - Воркеры Gunicorn завершались по таймауту при длительном выполнении скрипта `/root/antizapret/doall.sh`, что приводило к ошибке `500` на эндпоинте `/run-doall` и `/edit-files`.
  - В конфигурации `gunicorn.conf.py`:
    - Увеличен параметр `timeout` до `300` секунд (ранее `60`).
    - Изменён `worker_class` с `'sync'` на `'gthread'` для возможности параллельной обработки запросов.
    - Добавлен параметр `threads` (6 по умолчанию) для многопоточной работы одного воркера.
    - Настроены параметры `graceful_timeout` и `keepalive` для устойчивой работы при долгих запросах.
  - Благодаря изменению долгие операции теперь выполняются корректно, не блокируя остальные запросы и без перезапуска воркеров.

## [1.2.4] – 13.10.2025

### Добавлено

- **Кнопка обновления системы в веб-интерфейсе**:
  - Добавлена кнопка «Обновить систему» в раздел «Конфигурирование Antizapret» на странице настроек (`settings.html`).
  - Реализован новый роут `/update_system` (метод POST) для запуска скрипта `/opt/AdminAntizapret/script_sh/adminpanel.sh --update`.

## [1.2.3] – 13.10.2025

### Исправлено

- Исправлено дублирование переменной VNSTAT_IFACE в файле .env:
- Добавлена проверка существующей переменной VNSTAT_IFACE перед записью нового значения.
- При наличии переменной пользователю предлагается обновить её или сохранить текущее значение.
- Реализована очистка дубликатов VNSTAT_IFACE в .env для предотвращения множественных записей.
- Улучшена логика обработки для обеспечения единственного экземпляра переменной в файле.
- В `vnstat.service` добавлен таймер отложенного запуска (`ExecStartPre=/bin/sleep 10`) для корректной инициализации интерфейса после загрузки системы.

## [1.2.2] – 08.10.2025

### Добавлено

- **Виртуальные интерфейсы** для агрегирования трафика:
  - `vpn` теперь суммирует: `vpn` + `vpn-udp` + `vpn-tcp`.
  - `antizapret` теперь суммирует: `antizapret` + `antizapret-upd` + `antizapret-tcp`.
- Поддержка параллельной загрузки и **комбинирования рядов** (labels, rx/tx) с выравниванием меток времени.
- **Totals** за периоды (`1d`, `7d`, `30d`) также суммируются для групп.
- Добавлены **кнопки переключения единиц измерения трафика** между мегабайтами (MB) и мегабитами (Mb).

## [1.2.1] – 08.10.2025

### Добавлено

- **Автоопределение сетевого интерфейса при установке**:

  - Получение списка доступных интерфейсов через `ip link show` с фильтрацией (`lo`, `docker`, `veth`, `br-`, `vpn`, `antizapret`, `tun`, `tap`).
  - Определение интерфейса по умолчанию из `ip route | grep default`; при отсутствии — используется `eth0`.
  - Автоматический выбор интерфейса, если найден ровно один.
  - Интерактивный выбор интерфейса при наличии нескольких (с проверкой существования через `ip link show`).
  - Сохранение выбранного интерфейса в `.env`:

    ```
    VNSTAT_IFACE=<iface>
    ```

- **Интеграция с веб-интерфейсом**:
  - В шаблон `server_monitor.html` теперь передаётся переменная `iface` (значение из `.env` или `ens3` по умолчанию).

### Изменено

- Обновлена логика установки — теперь интерфейс определяется и сохраняется автоматически для корректной работы `vnstat` и веб-интерфейса.

### Примечание

- После обновления обязательно запустить:

  ```bash
  /opt/AdminAntizapret/script_sh/fix_vnstat.sh
  ```

  для корректного применения изменений и обновления конфигурации vnstat.

## [1.2.0] – 07.10.2025

### Добавлено

- Добавлен раздел **«Загрузка канала»** в `server_monitor.html`.
  Теперь можно:
  - Переключать сетевые интерфейсы: `ens3`, `vpn`, `antizapret`;
  - Выбирать период: `1 день`, `7 дней`, `30 дней`;
  - Смотреть график скорости и объёма трафика (на основе **Chart.js**);
  - Видеть текущую нагрузку (Rx / Tx) и суммарные данные за периоды.
- Выбранный интерфейс и диапазон теперь сохраняются в браузере (через `localStorage`).

### Изменения

- Весь JavaScript и CSS для мониторинга вынесен из `server_monitor.html`
  в отдельные файлы:
  - `server_monitor.js`
  - `server_monitor.css`
- Кнопки выбора диапазона и интерфейса стали удобнее — активная подсвечивается, остальные недоступны.

## [1.1.9] – 04.10.2025

### Добавлено

- **Поддержка указания хостов для VPN**:

  - `OPENVPN_HOST` — ввод доменного имени для OpenVPN сервера (требует пересоздания конфигураций).
  - `WIREGUARD_HOST` — ввод доменного имени для WireGuard сервера (требует пересоздания конфигураций).

- **Управление дополнительными параметрами через веб-интерфейс**:

  - **Новый переключатель фильтрации доменов казино**:
    - `CLEAR_HOSTS` — опция в интерфейсе, позволяющая включить/отключить удаление ~170 000 доменов азартных игр при автообновлении списков.
  - Заголовок секции обновлён: теперь «Дополнительные фильтры для Antizapret».

- **Улучшения интерфейса Antizapret**:

  - Обновлённые описания параметров (Cloudflare, Google, Telegram, Amazon и др.).
  - Единый стиль блоков (`AZ`, `OVPN`, `WG`, `Server`) для удобства восприятия.

- **Расширенные сетевые защиты**:

  - Визуальное разделение на колонки (SSH защита, Torrent Guard, Антискан, Ограничение форвардинга).

- **Улучшения UX**:
  - Подсказки и пояснения вынесены в отдельные тултипы.
  - Блоки настроек получили группировку и иконки для удобной навигации.

## [1.1.8] – 29.09.2025

### Добавлено

- **Управление дополнительными параметрами через веб-интерфейс**:
  - Новый раздел **«Резервные OpenVPN-порты (80/443)»**:
    - `OPENVPN_80_443_TCP` — включение резервного подключения OpenVPN через TCP 80/443
    - `OPENVPN_80_443_UDP` — включение резервного подключения OpenVPN через UDP 80/443
  - Новый блок **«Сетевые защиты»**:
    - `SSH_PROTECTION` — защита от брутфорса SSH (ограничение 3 новых подключений в час с одного IP)
    - `ATTACK_PROTECTION` — антискан и защита от сетевых атак (может блокировать VPN или сторонние приложения)
    - `TORRENT_GUARD` — блокировка VPN на 1 минуту при обнаружении торрентов (для хостеров, запрещающих торрент-трафик)
    - `RESTRICT_FORWARD` — ограничение форвардинга: через AntiZapret VPN идут только IP из `forward-ips.txt` и `route-ips.txt`

## [1.1.7] – 27.09.2025

### Добавлено

- **Поддержка новых форматов имён конфигурационных файлов**:
  - Для файлов с суффиксом `-wg.conf` при скачивании автоматически добавляется префикс `WG-`.
  - Для файлов с суффиксом `-am.conf` при скачивании автоматически добавляется префикс `AWG-`.

### Изменено

- **Логика генерации имён файлов при скачивании**:
  - Теперь `.conf` и `.ovpn` файлы обрабатываются единообразно: имя клиента + опциональный суффикс `-AZ` для `antizapret`.
  - Обновлена регулярка для корректной работы с доменами, содержащими дефисы.
  - Регулярное выражение перенесено непосредственно в роут для упрощения кода.

### Исправлено

- **Проблемы со скачиванием .conf файлов**:
  - Ранее файлы `.conf` скачивались с полным исходным именем, теперь формируется корректное сокращённое имя клиента, как и для `.ovpn`.

## [1.1.6] – 27.09.2025

### Исправлено

- Переписана логика разбора файлов:
  - Теперь имя клиента определяется более надёжно (через stem и проверку префиксов).
  - Определение типа файла (antizapret / vpn) вынесено в отдельную переменную `kind`.
- Изменён вывод кнопки скачивания: (by [glebsoluyanov](https://github.com/glebsoluyanov))
  - Вместо тега `<a>` с вложенной кнопкой теперь используется один `<button>` с `onclick`.
  - Ссылка на скачивание формируется через `url_for` напрямую.
- Обновлены стили:
  - Значение `padding` у таблицы (`td`) уменьшено с `0.75rem` до `0.5rem`.

## [1.1.5] – 21.06.2025

### Добавлено

- **Веб-интерфейс для конфигурирования Antizapret**:
  - Новый раздел в настройках для управления параметрами маршрутизации
  - 8 переключаемых параметров с подсказками:
    - `ROUTE_ALL` - весь трафик кроме .ru/.рф
    - `DISCORD_INCLUDE` - трафик Discord
    - `CLOUDFLARE_INCLUDE` - трафик Cloudflare
    - `AMAZON_INCLUDE` - трафик Amazon
    - `HETZNER_INCLUDE` - трафик Hetzner
    - `DIGITALOCEAN_INCLUDE` - трафик DigitalOcean
    - `OVH_INCLUDE` - трафик OVH
    - `TELEGRAM_INCLUDE` - трафик Telegram
  - Кнопка сохранения настроек с отображением статуса
  - Интеграция с JavaScript для обработки изменений

### Изменено

- **Структура страницы настроек**:
  - Добавлена новая вкладка "Конфигурирование Antizapret" в боковое меню
  - Оптимизировано расположение элементов управления

### Исправлено

- Исправлено отображение подсказок на мобильных устройствах

## [1.1.4] – 08.05.2025

### Добавлено

- **Интеграция Gunicorn** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Flask теперь работает за полноценным встроенным веб-сервером Gunicorn
  - Gunicorn слушает порт, декодирует SSL-трафик и запускает приложение в 4 потоках по умолчанию
  - Возможность настройки количества воркеров через переменную `GUNICORN_WORKERS` в `.env`
  - Добавлен пункт настройки воркеров на странице изменения порта в веб-интерфейсе

### Исправлено

- **Проблемы с SSL-сертификатами** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Исправлена ошибка при указании существующего, но не привязанного к IP домена
  - Добавлена проверка фактического получения сертификата перед продолжением установки
- **Ошибки в JavaScript** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Исправлено обновление выпадающего списка при удалении клиента в `main_index.js`
  - Удалены неиспользуемые функции `updateConfigTables()` и `updateClientSelect(option)`
- **Обновление client.sh** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Исправлена работа с доменными именами при установке Antizapret
  - Добавлена возможность указать срок действия клиента OpenVPN до 3650 дней
  - Ограничено поле ввода срока действия 4 символами

## [1.1.3] – 26.04.2025

### Добавлено

- **Оптимизированный интерфейс настроек**:
  - Полностью переработанный адаптивный интерфейс страницы настроек
  - Боковое меню с возможностью раскрытия разделов
  - Улучшенное отображение на мобильных устройствах
  - Разделение управления пользователями на вкладки (добавление/список/удаление)

### Исправлено

- **Проблемы с отображением на мобильных устройствах**:
  - Исправлено переполнение текста в меню
  - Оптимизированы размеры элементов для touch-устройств
  - Улучшена прокрутка контента
- **Интерактивность**:
  - Исправлена работа аккордеона в мобильной версии
  - Улучшена реакция на касания

## [1.1.2] – 25.04.2025

### Добавлено

- **Проверка зависимостей при установке** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Добавлена проверка отсутствующих библиотек и утилит (например, `git`, текстовые и сетевые утилиты).
  - Автоматическая установка недостающих зависимостей.
- **Улучшенная проверка портов** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Определение и отображение сервиса, занимающего порт.
  - Проверка наличия перенаправлений в таблице маршрутизации с отображением правил.
- **Изменения в работе с Let's Encrypt** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Таблица маршрутизации временно очищается от 80 TCP порта при получении сертификата, затем восстанавливается.
  - Добавлено предупреждение при попытке использовать стандартные порты 80 и 443 с предложением отключить их резервирование в OpenVPN.
  - Возможность отменить подписку на рассылку Let's Encrypt, оставив поле ввода почты пустым.
  - Установка Let's Encrypt теперь минимальна, без лишних библиотек и заданий в `cron`.
  - Создано собственное задание для обновления сертификатов с временным изменением таблицы маршрутизации и остановкой сервисов, занимающих порт 80.
  - Перезапуск службы AdminAntizapret после обновления сертификатов.

### Исправлено

- **Удаление Let's Encrypt** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Удаление теперь корректно очищает зависимости через `autoremove`.
  - Удаление возможно даже при повторном запуске скрипта, домен берется из сертификата.
  - Удаляются кеши ключей и задания, файл задания остается для ручного использования.
- **Отображение таблиц** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Исправлены проблемы с правой границей таблиц при динамической длине адресов.
- **Функция `press_any_key`** (by [CarolusFuchs](https://github.com/CarolusFuchs)):
  - Теперь корректно реагирует на любую клавишу, а не только на Enter.

### Протестировано

- Протестировано на различных сборках Ubuntu 22.04 и 24.04 (PQ, AEZA, Kyonix, Waicore) (by [CarolusFuchs](https://github.com/CarolusFuchs)).
- Проверены сценарии с занятыми портами и перенаправлениями — все работает корректно.

## [1.1.1] – 20.04.2025

### Добавлено

- **Проверка настроек OpenVPN для HTTPS**:
  - Добавлена автоматическая проверка параметра `OPENVPN_80_443_TCP` в файле `/root/antizapret/setup`
  - Интерактивное предложение изменить значение с `y` на `n` при настройке HTTPS
  - Автоматический перезапуск сервиса antizapret при изменении настроек
- **Улучшенная модульность**:

  - Вынесена проверка OpenVPN в отдельную функцию `check_openvpn_tcp_setting()`
  - Улучшена обработка пользовательского ввода при настройке HTTPS

  ### Изменено

- **Логика выбора портов для HTTPS**:
  - Для всех вариантов HTTPS (Let's Encrypt, собственные сертификаты, самоподписанные) теперь по умолчанию предлагается порт 443
  - Для HTTP сохраняется исходный DEFAULT_PORT (обычно 80)
  - Запрос порта теперь происходит после выбора конкретного типа соединения
- **Улучшения пользовательского интерфейса**:
  - Более логичная последовательность запросов при настройке SSL/TLS
  - Улучшены подсказки при выборе портов

### Исправлено

- Исправлена проверка доступности портов для HTTPS-соединений
- Улучшены сообщения об ошибках при конфликте портов

## [1.1.0] – 19.04.2025

### Архитектурные изменения

- **Полная модуляризация кода**:
  - `backup_functions.sh` — управление резервными копиями
  - `monitoring.sh` — мониторинг ресурсов системы
  - `service_functions.sh` — управление сервисами
  - `ssl_setup.sh` — настройка SSL/TLS сертификатов
  - `uninstall.sh` — полное удаление системы
  - `user_management.sh` — управление пользователями
  - `utils.sh` — вспомогательные утилиты
- **Динамическая загрузка модулей**:
  - Поддержка директории `/opt/AdminAntizapret/script_sh/` для хранения модулей
  - Автоматическое подключение зависимостей
- **Гибкая настройка портов**:
  - Поддержка произвольных портов для HTTP/HTTPS с автоматической проверкой доступности
- **Кастомные домены**:
  - Возможность использования пользовательских доменов и SSL-сертификатов

### Добавлено

- **Система логирования**:
  - Централизованный лог `/var/log/adminpanel.log`
  - Функции `init_logging` и `log` для системного аудита
- **Новые возможности**:
  - Меню **"Мониторинг системы"** (реализовано в `monitoring.sh`)
  - Меню **"Проверить конфигурацию"** (валидация настроек)
- **Безопасная работа сессий**:
  - Автоматическая генерация `SECRET_KEY` при первом запуске:
    - Ключ сохраняется в `.env` для постоянного использования
    - Исключает разлогин пользователей после перезапуска сервиса
    - Гарантирует стабильность сессий при обновлениях системы
- **Безопасность**:
  - Строгая проверка прав root с записью в лог
  - Улучшенная обработка ошибок через `check_error`
- **Автоматическое обновление SSL-сертификатов**:
  - Настроен `cron` для продления сертификатов Let's Encrypt (каждые 60 дней)

### Изменено

- **Локализация**:
  - Переход с `en_US.UTF-8` на `C.UTF-8` для совместимости
- **Зависимости**:
  - Добавлен пакет `cron` в обязательные зависимости
  - Поддержка тихого режима установки (`--quiet`)
- **Проверка AntiZapret**:
  - Детальная проверка через `systemctl`
  - Проверка наличия директории `/root/antizapret`
  - Четкие инструкции при отсутствии модуля

### Улучшения

- **Надежность**:
  - Изоляция компонентов повышает стабильность
  - Автоматическое обновление SSL-сертификатов (каждые 60 дней)
- **Безопасность**:
  - Гарантированное HTTPS-соединение
  - Улучшенная проверка прав доступа
- **Удобство**:
  - Единая точка входа (`/root/AdminPanel/adminpanel.sh`)
  - Подробная документация по модулям
- **Совместимость**:
  - Поддержка различных окружений через `C.UTF-8`
  - Сохранение обратной совместимости

### Примечания

После установки доступны два пути к скрипту:

1. Оригинальное расположение
2. `/root/AdminPanel/adminpanel.sh`

## [1.0.9] – 16.04.2025

### Добавлено

- **Поддержка HTTPS**:

  - Добавлена возможность выбора между Nginx + Let's Encrypt и самоподписанными сертификатами.
  - Автоматическая настройка SSL параметров для Nginx.

- **Улучшенная проверка портов**:
  - Добавлена поддержка нескольких методов проверки занятости портов (ss, netstat, lsof, /proc/net/tcp).
  - Улучшена обработка ошибок при проверке портов.
- **Логирование действий**:
  - Добавлена функция init_logging для записи логов в /var/log/adminpanel.log.
  - Все ключевые действия теперь логируются с временными метками.
- **Мониторинг системы**:
  - Добавлено новое меню мониторинга с возможностью проверки CPU, памяти, диска и сетевых соединений.
- **Валидация конфигурации**:
  - Добавлена функция validate_config для проверки корректности конфигурации.

### Изменено

- Добавлена проверка использования портов 80/443 перед установкой Nginx + Let's Encrypt.
- Улучшена обработка ошибок при установке.
- Добавлена проверка целостности архива после создания резервной копии.
- Включены дополнительные файлы в резервную копию (SSL сертификаты, конфигурации Nginx).
- Улучшена модульность и читаемость кода.
- Добавлены дополнительные проверки ошибок.

### Исправлено

- Улучшена обработка прав доступа к файлам .env и конфигурационным файлам.
- Добавлена валидация доменных имен и проверка DNS записей.

## [1.0.8] – 11.04.2025

### Добавлено

- **Страница настроек**:
  - Возможность изменения порта через веб-интерфейс.
  - Добавление и удаление пользователей.
  - Проверка длины пароля (минимум 8 символов).

## [1.0.7] – 10.04.2025

### Добавлено

- **Мониторинг ресурсов сервера** (by [MagicRaven01](https://github.com/MagicRaven01)):
  - Отображение текущей нагрузки процессора (%)
  - Информация о загруженности диска
  - Время работы сервера (uptime)
  - Кнопки перехода в монитор ресурсов с главной страницы и редактора файлов
  - Реализовано в общей стилистике интерфейса

### Изменено

- **Обновлен роут для скачивания файлов**:
  - Полная поддержка нового формата имен файлов из client.sh
  - Корректная обработка спецсимволов (скобки, дефисы)
  - Автоматическое преобразование имен для скачивания
  - Поддержка обратной совместимости со старыми конфигами
- Оптимизировано расположение элементов навигации
- Обновлены стили для мобильных устройств

## [1.0.6] – 07.04.2025

### Добавлено

- Хранение порта сервиса в `.env` файле (APP_PORT)
- Функция изменения порта через `adminpanel.sh`
- Автоматическое создание `.env` с SECRET_KEY и APP_PORT при установке
- Проверка существующего SECRET_KEY при изменении порта

### Изменено

- Обновлен `adminpanel.sh` для корректной работы с `.env`:
  - Сохранение SECRET_KEY при изменении порта
  - Добавлен пункт меню для изменения порта

## [1.0.5] – 06.04.2025

### Добавлено

- **CSRF-защита** для всех форм (Flask-WTF).
- Автоматическая генерация `SECRET_KEY` при установке и хранение в `.env`.
- Поддержка файла `.env` для конфиденциальных настроек (порт, ключи, БД).
- Добавлен `python-dotenv` в зависимости.
- Блокировка доступа к `.env` через веб-сервер.

### Изменено

- Рефакторинг `app.py` для работы с переменными окружения.
- Обновлён `adminpanel.sh` для создания `.env` и настройки прав.

## [1.0.4] – 05.04.2025

### Изменено

- Возвращена функция удаления клиента в `adminpanel.sh`.
- Исправлена выдача прав на файлы.
- Клиенты теперь отображаются в таблице в алфавитном порядке (by [CarolusFuchs](https://github.com/CarolusFuchs)).
- Откорректированы масштабы модального окна QR для правильного отображения на мобильных устройствах и мониторах (by [CarolusFuchs](https://github.com/CarolusFuchs)).
- Откорректирована высота ячеек клиентов WG и Amneziya (теперь совпадает с OpenVPN) (by [CarolusFuchs](https://github.com/CarolusFuchs)).
- Проверка существования файла в роутах app.py вынесена в отдельный декоратор (оптимизация кода) (by [CarolusFuchs](https://github.com/CarolusFuchs)).

## [1.0.3] – 03.04.2025

### Добавлено

- Добавлена генерация QR-кодов для конфигурационных файлов Amnezia и WireGuard (by [CarolusFuchs](https://github.com/CarolusFuchs)).
- Добавлена функция удаления администратора с предварительным выводом списка администраторов в `adminpanel.sh`.
- Добавлена поддержка аргумента `--list-users` в `init_db.py` для вывода списка пользователей.
- Добавлена проверка на пустой ввод при удалении администратора.
- Обновлен client.sh до последней версии убрана ошибка с удаление конфигураций OpenVPN

### Изменено

- Обновлено главное меню в `adminpanel.sh` для включения нового пункта "Удалить администратора".
- Улучшена обработка ошибок при удалении администратора.

## [1.0.2] – 02.04.2025

### Исправлено

- Исправлен ввод имени файла с использованием символа `-` и ограничением имени в 15 символов.
- Добавлено скачивание конфигурации с коротким именем (by [CarolusFuchs](https://github.com/CarolusFuchs)).
- Рефакторинг: введен конфиг-объект, устранено дублирование кода, вынесены константы для сроков сертификатов. (by [MagicRaven01](https://github.com/MagicRaven01))

## [1.0.1] – 01.03.2025

### Добавлено

- Поддержка WireGuard.
- Функционал редактирования файлов конфигурации AntiZapret через веб-интерфейс.
- Авторизация с использованием SQLite и Flask-SQLAlchemy.
- Стилизация интерфейса с использованием CSS и адаптивного дизайна.
- Скрипты для проверки обновлений и перезапуска сервиса.
- Скрипт `adminpanel.sh` для установки, управления и удаления AdminAntizapret.

## [1.0.0] – 01.03.2025

### Добавлено

- Веб-приложение на Flask для управления VPN-клиентами.
- Поддержка OpenVPN и AmneziaWG.
- Возможность добавления, удаления и скачивания конфигурационных файлов клиентов.
- Панель управления через веб-интерфейс.
- Система резервного копирования и восстановления данных.
