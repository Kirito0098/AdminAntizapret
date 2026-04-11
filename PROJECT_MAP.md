# Карта проекта AdminAntizapret

Документ описывает текущую структуру проекта, назначение файлов и практический порядок работы с кодовой базой.

## 1) Быстрый обзор архитектуры

- Точка входа приложения: `app.py`.
- Веб-слой (HTTP/WebSocket маршруты): папка `routes/`.
- Бизнес-логика и инфраструктурные сервисы: папка `core/services/`.
- SQLAlchemy-модели: `core/models.py`.
- HTML-шаблоны: `templates/`.
- Статические файлы (CSS/JS/изображения/шрифты): `static/assets/`.
- Системные shell-скрипты установки/обслуживания: `install.sh`, `client.sh`, `script_sh/*.sh`.
- Вспомогательные утилиты синхронизации/инициализации: `utils/*.py`.

Текущая схема: `app.py` выступает как composition root, а большая часть логики вынесена в сервисы и роут-модули.

---

## 2) Корневые файлы проекта

### `app.py`

- Назначение:
  - создаёт Flask/Sock приложение;
  - читает env и runtime-настройки;
  - инициализирует БД и сервисы;
  - связывает всё через `register_all_routes(...)`.
- Важно:
  - здесь оставлены совместимые обёртки (thin wrappers), чтобы не ломать существующие вызовы;
  - внешние утилиты могут импортировать символы из `app.py` (например, `db`, `User`).
- Как работать:
  - новые крупные блоки логики не добавлять сюда, а выносить в `core/services/` или `routes/`;
  - в `app.py` оставлять только инициализацию и wiring.

### `README.md`

- Пользовательская документация: установка, описание возможностей, разделы UI.

### `CHANGELOG.md`

- История релизов и изменений.

### `requirements.txt`

- Python-зависимости проекта.

### `gunicorn.conf.py`

- Конфигурация запуска Gunicorn (workers/threads/timeouts/bind/HTTPS-параметры).

### `install.sh`

- Bootstrap-установщик (режимы `--install`, `--check`, `--help`).

### `client.sh`

- Основной shell-инструмент управления клиентами VPN (добавление, удаление, сертификаты, генерация конфигов).

---

## 3) Папка `core/`

### `core/__init__.py`

- Маркер пакета `core`.

### `core/models.py`

- Единая точка SQLAlchemy-моделей и `db = SQLAlchemy()`.
- Содержит модели:
  - `User`, `ViewerConfigAccess`;
  - `QrDownloadToken`, `QrDownloadAuditLog`;
  - `UserTrafficStat`, `UserTrafficStatProtocol`, `UserTrafficSample`, `TrafficSessionState`;
  - `OpenVPNPeerInfoCache`, `OpenVPNPeerInfoHistory`, `WireGuardPeerCache`;
  - `ActiveWebSession`, `BackgroundTask`, `LogsDashboardCache`.
- Как работать:
  - новые таблицы добавлять здесь;
  - миграционные доработки схемы синхронизировать с `core/services/db_migration.py`.

---

## 4) Папка `core/services/`

### `core/services/__init__.py`

- Экспорт всех сервисов для централизованного импорта.

### `core/services/service_container.py`

- Фабрика `build_services(...)` для сборки контейнера сервисов и инъекций зависимостей.

### `core/services/runtime_settings.py`

- Загрузка и нормализация runtime/env-настроек (таймауты, cron, пути к логам, WireGuard/OpenVPN параметры).

### `core/services/env_file.py`

- Чтение/запись переменных в `.env` (`get_env_value`, `set_env_value`).

### `core/services/db_migration.py`

- Инкрементальные миграции БД поверх `create_all()`.

### `core/services/context_processors.py`

- Регистрация context-processor для `current_user` в шаблонах.

### `core/services/background_tasks.py`

- Инфраструктура фоновых задач:
  - очередь задач через `ThreadPoolExecutor`;
  - сериализация и обновление статуса (`queued/running/completed/failed`);
  - helpers выполнения команд;
  - готовые системные задачи (`task_run_doall`, `task_restart_service`, `task_update_system`).

### `core/services/openvpn_banlist.py`

- Работа с файлом заблокированных OpenVPN клиентов;
- вставка/проверка блока `banned_clients` в `client-connect.sh`.

### `core/services/auth_manager.py`

- Декораторы авторизации/роли (`login_required`, `admin_required`).

### `core/services/active_web_session.py`

- Учёт активных веб-сессий для безопасного ночного рестарта.

### `core/services/captcha_generator.py`

- Генерация текста и изображения captcha.

### `core/services/file_validator.py`

- Декоратор валидации файлов конфигов по типу и имени.

### `core/services/file_editor.py`

- Чтение/запись управляющих txt-файлов маршрутизации/фильтров.

### `core/services/config_file_handler.py`

- Поиск/сбор конфигов, получение срока сертификатов OpenVPN.

### `core/services/config_access.py`

- Нормализация и группировка конфигов для выдачи доступа (`openvpn/wg/amneziawg`),
- сбор интерфейсов для bw-графиков.

### `core/services/client_protocol_catalog.py`

- Каталог клиент↔протокол, агрегаты по существующим конфигам и трафик-сэмплам.

### `core/services/script_executor.py`

- Запуск `client.sh` с валидацией параметров.

### `core/services/server_monitor.py`

- CPU/RAM/disk/load/system info.

### `core/services/openvpn_socket_reader.py`

- Работа с OpenVPN management socket (status/log), парсинг payload.

### `core/services/network_status_collector.py`

- Парсинг OpenVPN/WireGuard статусов и событий;
- синхронизация peer cache WireGuard;
- формирование срезов активных клиентов.

### `core/services/peer_info_cache.py`

- Persist/load/prune peer metadata (версия клиента/платформа) с TTL/retention.

### `core/services/traffic_persistence.py`

- Сохранение дельты трафика, бэкфилл/агрегации, удаление статистики клиента.

### `core/services/traffic_maintenance.py`

- Операции сброса/пересборки статистики и baseline-состояний сессий.

### `core/services/logs_dashboard_collector.py`

- Самая объёмная агрегация данных dashboard: status/event/persisted data/сводки.

### `core/services/logs_dashboard_cache.py`

- Кэширование payload dashboard в БД + фоновые refresh-операции.

### `core/services/maintenance_scheduler.py`

- Планирование и управление cron-задачами (очистка логов, traffic sync, nightly restart).

### `core/services/qr_generator.py`

- Генерация QR из текста конфига/URL с fallback по уровню коррекции.

### `core/services/qr_download_token.py`

- Одноразовые ссылки на скачивание (TTL, PIN, лимиты, аудит).

---

## 5) Папка `routes/`

### `routes/route_wiring.py`

- Централизованная регистрация всех route-модулей в одном месте.

### `routes/auth_routes.py`

- Логин/логаут/captcha/heartbeat/блокировка по IP, before_request middleware.

### `routes/index_routes.py`

- Главная страница: отображение конфигов/карточек клиентов и выполнение операций через `client.sh`.

### `routes/config_routes.py`

- Скачивание/QR/one-time download, редактирование файлов, run-doall, блокировка OpenVPN клиента.

### `routes/admin_routes.py`

- Проверка обновлений, фоновые админ-задачи, статус задач, API выдачи доступа viewer.

### `routes/settings_routes.py`

- Страница настроек: порт/пользователи/роли/IP-ограничения/cron/безопасность/QR-параметры.

### `routes/monitoring_routes.py`

- Мониторинг сервера, logs dashboard, очистка/расписание логов, API bw/user-traffic, websocket монитор.

### `routes/settings_antizapret.py`

- Специализированные endpoints и схема для настроек AntiZapret.

### `routes/__init__.py`

- Маркер пакета `routes`.

---

## 6) Папка `utils/`

### `utils/ip_restriction.py`

- Логика allowlist IP для доступа к панели.

### `utils/traffic_sync.py`

- Внешний utility для cron/systemd синхронизации трафика.

### `utils/nightly_idle_restart.py`

- Внешний utility ночного перезапуска при простое.

### `utils/init_db.py`

- Инициализация БД/базовые операции для окружения.

### `utils/backfill_traffic_split.py`

- Вспомогательный backfill/пересчёт по данным трафика.

### `utils/__init__.py`

- Маркер пакета `utils`.

Примечание: скрипты из `utils/` могут вызываться извне (cron/systemd), поэтому при рефакторинге важно не ломать их импорт/контракты.

---

## 7) Папка `config/`

### `config/antizapret_params.py`

- Набор параметров и дефолтов для конфигурации AntiZapret.

### `config/__init__.py`

- Маркер пакета `config`.

---

## 8) Папка `ips/`

### `ips/ip_manager.py`

- Управление IP-списками и состоянием включения/выключения файлов.

### `ips/include_ips_header.py`

- Работа с заголовком include-файла для IP.

### `ips/include-ips.txt`

- Локальный include-список IP.

### `ips/list/*.txt`

- Готовые IP-списки по провайдерам:
  - `akamai-ips.txt`
  - `amazon-ips.txt`
  - `digitalocean-ips.txt`
  - `google-ips.txt`
  - `hetzner-ips.txt`
  - `ovh-ips.txt`

### `ips/__init__.py`

- Маркер пакета `ips`.

---

## 9) Папка `script_sh/`

### `script_sh/adminpanel.sh`

- Главный CLI-менеджер установки/обновления/обслуживания.

### `script_sh/service_functions.sh`

- Функции управления сервисом и процессами.

### `script_sh/user_management.sh`

- Функции управления пользователями/правами.

### `script_sh/backup_functions.sh`

- Резервные копии и восстановление.

### `script_sh/ssl_setup.sh`

- Настройка SSL/HTTPS.

### `script_sh/monitoring.sh`

- Консольный мониторинг.

### `script_sh/fix_vnstat.sh`

- Починка/настройка vnStat.

### `script_sh/uninstall.sh`

- Удаление панели и cleanup.

### `script_sh/utils.sh`

- Общие shell-утилиты и helper-функции для скриптов.

---

## 10) Шаблоны UI (`templates/`)

### `templates/base.html`

- Базовый layout и общие include-блоки.

### `templates/login.html`

- Страница входа/captcha.

### `templates/index.html`

- Главная страница управления клиентами.

### `templates/edit_files.html`

- Редактирование txt-файлов маршрутизации.

### `templates/server_monitor.html`

- Системный мониторинг (CPU/RAM/disk/network).

### `templates/logs_dashboard.html`

- Dashboard подключений/событий/истории трафика.

### `templates/settings.html`

- Настройки приложения/пользователей/безопасности.

### `templates/ip_settings.html`

- UI-блоки настроек IP-ограничений.

### `templates/ip_blocked.html`

- Страница отказа доступа по IP.

---

## 11) Статика (`static/assets/`)

### CSS (`static/assets/css/`)

- `login_styles.css` — стили логина.
- `styles_index.css` — стили главной.
- `styles_mobile.css` — mobile-адаптация.
- `edit_file.css` — стили страницы редактирования файлов.
- `server_monitor_styles.css` — мониторинг.
- `logs_dashboard.css` — dashboard подключений/логов.

### JS (`static/assets/js/`)

- `main.js` — общая клиентская логика.
- `main_index.js` / `main_index_new.js` — логика главной страницы (карточки/действия/интерактив).
- `edit_files.js` — взаимодействие на странице редактирования файлов.
- `server_monitor.js` — обновление данных мониторинга.
- `settings.js` — интерактив на странице настроек.

### Изображения и шрифты

- `static/assets/img/favicon.ico`, `qr.png`, `login-bg.png`, `login-bg.png.1`.
- `static/assets/fonts/SabirMono-Regular.ttf`.

---

## 12) Конфигурация окружения и runtime

### `.env`

- Хранит ключевые runtime-параметры:
  - `SECRET_KEY`, `APP_PORT`, `USE_HTTPS`, `SSL_CERT`, `SSL_KEY`;
  - настройки cron/синхронизации/ночного рестарта;
  - параметры QR токенов (`TTL`, `PIN`, лимиты);
  - и др. опции, читаемые через `EnvFileService` и `RuntimeSettingsService`.

### `instance/`

- Runtime-данные Flask/локальные служебные файлы.

### `venv/`

- Локальное Python-окружение проекта.

---

## 13) Как с этим работать (практика)

## 13.1 Локальный запуск/проверка

1. Активировать окружение:
   - `source /opt/AdminAntizapret/venv/bin/activate`
2. Проверить синтаксис после изменений:
   - `python3 -m py_compile app.py`
   - `python3 -m py_compile core/models.py`
   - `python3 -m py_compile routes/*.py core/services/*.py utils/*.py`
3. При необходимости запускать через Gunicorn с `gunicorn.conf.py`.

## 13.2 Правила безопасного рефакторинга

1. Не удалять публичные символы, которые могут импортироваться внешними утилитами (`app.py`, `utils/*.py`).
2. Большую логику выносить в `core/services/`, а в `app.py` оставлять wiring.
3. Для новых HTTP-endpoint:
   - добавить функцию в соответствующий `routes/*_routes.py`;
   - подключить её через `routes/route_wiring.py`;
   - прокинуть нужные зависимости из `app.py`.
4. Для новых таблиц БД:
   - добавить модель в `core/models.py`;
   - при необходимости дополнить миграционный код `core/services/db_migration.py`.
5. После изменений в task/cron/утилитах обязательно проверить сценарии фоновых задач и внешних запусков.

## 13.3 Где менять, если нужна конкретная функция

- Логин/доступ/сессии: `routes/auth_routes.py`, `core/services/auth_manager.py`, `core/services/active_web_session.py`.
- Управление клиентами и конфигами: `routes/index_routes.py`, `routes/config_routes.py`, `core/services/script_executor.py`, `core/services/config_*`.
- QR и одноразовые ссылки: `core/services/qr_generator.py`, `core/services/qr_download_token.py`, `routes/config_routes.py`.
- Мониторинг и трафик: `routes/monitoring_routes.py`, `core/services/network_status_collector.py`, `core/services/traffic_*`, `core/services/logs_dashboard_*`.
- Настройки и cron: `routes/settings_routes.py`, `core/services/runtime_settings.py`, `core/services/maintenance_scheduler.py`, `core/services/env_file.py`.
- Админ-задачи и обновление: `routes/admin_routes.py`, `core/services/background_tasks.py`.

---

## 14) Критические зависимости между частями

1. `routes/*` ожидают зависимости из `app.py` (через `register_all_routes(..., deps)`), поэтому имена передаваемых callbacks должны оставаться стабильными.
2. `BackgroundTask` модель и `BackgroundTaskService` должны быть синхронизированы по полям статуса.
3. Логика трафика зависит от согласованности моделей:
   - `TrafficSessionState`
   - `UserTrafficSample`
   - `UserTrafficStat`
   - `UserTrafficStatProtocol`
4. Логика peer-info кэша зависит от парсеров событий OpenVPN (`network_status_collector.py`) и retention-политик (`peer_info_cache.py`).

---

## 15) Рекомендуемый workflow разработки

1. Определить слой изменения:
   - роут,
   - сервис,
   - модель,
   - шаблон/статический фронтенд,
   - shell-скрипт.
2. Внести изменение в профильный модуль.
3. Проверить синтаксис `py_compile` и базовые сценарии страницы/API.
4. Обновить документацию (`README.md`, этот файл, changelog) при изменении поведения.

---

## 16) Что смотреть первым при инциденте

1. Ошибки импорта/инициализации:
   - `app.py`, `core/services/__init__.py`, `core/models.py`.
2. Ошибки endpoint:
   - соответствующий файл из `routes/`.
3. Ошибки фоновых задач:
   - `core/services/background_tasks.py` + таблица `BackgroundTask`.
4. Проблемы мониторинга/трафика:
   - `core/services/network_status_collector.py`, `core/services/traffic_persistence.py`, `core/services/logs_dashboard_collector.py`.
5. Проблемы доступа/авторизации:
   - `routes/auth_routes.py`, `core/services/auth_manager.py`, `utils/ip_restriction.py`.

---

## 17) Кратко: куда добавлять новый код

- Новый API/страница: в `routes/` + подключение в `routes/route_wiring.py`.
- Новая бизнес-логика: в `core/services/`.
- Новая таблица/сущность: в `core/models.py`.
- Новая shell-операция администрирования: в `script_sh/` (или `client.sh`, если это клиентские операции VPN).
- Новая фронтенд-логика: `templates/` + `static/assets/css|js`.

Документ актуален для состояния репозитория на 2026-04-11.
