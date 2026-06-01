"""Русские названия и описания автотестов (генерируется/поддерживается вручную)."""
from __future__ import annotations

MODULE_LABELS: dict[str, str] = {
    'tests/test_access_remaining.py': 'Остаток доступа клиента',
    'tests/test_admin_notify.py': 'Уведомления администратору',
    'tests/test_admin_routes.py': 'Администрирование',
    'tests/test_antizapret_backup.py': 'Резервное копирование Antizapret',
    'tests/test_app_auto_backup.py': 'Автоматический бэкап панели',
    'tests/test_audit_view_presenter_action_logs.py': 'Аудит: журнал действий',
    'tests/test_audit_view_presenter_tg.py': 'Аудит: Telegram-уведомления',
    'tests/test_auth_routes_login.py': 'Авторизация',
    'tests/test_background_tasks_service.py': 'Фоновые задачи',
    'tests/test_backup_manager_service.py': 'Менеджер резервных копий',
    'tests/test_backup_telegram_job.py': 'Отправка бэкапа в Telegram',
    'tests/test_cidr_db_updater_service.py': 'CIDR в базе данных',
    'tests/test_cidr_list_updater.py': 'CIDR-списки и маршрутизация',
    'tests/test_config_routes_openvpn_block.py': 'API блокировки OpenVPN',
    'tests/test_db_backup_export.py': 'Экспорт базы данных',
    'tests/test_db_migration_service.py': 'Миграции БД',
    'tests/test_edit_files_page_context.py': 'Редактор файлов',
    'tests/test_firewall_tools_check.py': 'Проверка firewall-инструментов',
    'tests/test_http_security.py': 'HTTP и безопасность',
    'tests/test_index_page_context.py': 'Главная страница',
    'tests/test_index_routes_wg_access.py': 'API доступа WireGuard',
    'tests/test_ip_restriction_scanner_block.py': 'Ограничение IP (сканеры)',
    'tests/test_ip_restriction_temporary.py': 'Временный whitelist IP',
    'tests/test_ip_restriction_whitelist_firewall_gating.py': 'Firewall whitelist порта',
    'tests/test_maintenance_scheduler_backup.py': 'Планировщик cron бэкапов',
    'tests/test_notify_time.py': 'Время в уведомлениях',
    'tests/test_openvpn_access_policy_service.py': 'Политика доступа OpenVPN',
    'tests/test_panel_port_firewall.py': 'Firewall порта панели',
    'tests/test_panel_publish_info.py': 'Публикация панели',
    'tests/test_routing_page_context.py': 'Маршрутизация',
    'tests/test_safe_browsing_status_cli.py': 'Safe Browsing CLI',
    'tests/test_scanner_firewall_store.py': 'Блокировка сканеров',
    'tests/test_session_security.py': 'Безопасность сессий',
    'tests/test_settings_api_action_logs_export.py': 'Экспорт журнала действий',
    'tests/test_settings_page_context.py': 'Страница настроек',
    'tests/test_settings_post_handlers.py': 'Сохранение настроек',
    'tests/test_site_diagnostics.py': 'Диагностика запуска сайта',
    'tests/test_system_preflight.py': 'Проверка окружения (preflight)',
    'tests/test_telegram_webapp_init_data.py': 'Telegram WebApp',
    'tests/test_temporary_whitelist_store.py': 'Хранилище временного whitelist',
    'tests/test_tg_mini_session.py': 'Telegram Mini App',
    'tests/test_wg_access_policy_service.py': 'Политика доступа WireGuard',
    'tests/test_wg_awg_runtime_enforcer.py': 'Runtime WireGuard/AWG',
    'tests/test_wg_runtime_subprocess.py': 'Подпроцессы WireGuard runtime',
}

MODULE_DESCRIPTIONS: dict[str, str] = {
    'tests/test_access_remaining.py': 'Форматирование оставшегося срока доступа VPN-клиента для отображения в таблице.',
    'tests/test_admin_notify.py': 'Тексты Telegram-уведомлений администратору о действиях в панели.',
    'tests/test_admin_routes.py': 'Маршруты администрирования: фоновые задачи, viewer-доступ и обновление системы.',
    'tests/test_antizapret_backup.py': 'Создание архива Antizapret через client.sh и определение пути к архиву.',
    'tests/test_app_auto_backup.py': 'Скрипт автоматического бэкапа панели и отправки архивов в Telegram.',
    'tests/test_audit_view_presenter_action_logs.py': 'Представление журнала действий пользователей для UI и CSV-экспорта.',
    'tests/test_audit_view_presenter_tg.py': 'Человекочитаемые строки действий для Telegram-аудита.',
    'tests/test_auth_routes_login.py': 'Вход в панель, счётчик попыток и параметры «Запомнить меня».',
    'tests/test_background_tasks_service.py': 'Очередь фоновых задач, выполнение команд и обработка ошибок.',
    'tests/test_backup_manager_service.py': 'Создание, ротация, восстановление и описание резервных копий панели.',
    'tests/test_backup_telegram_job.py': 'Подготовка архива для отправки в Telegram с учётом лимита 50 МБ.',
    'tests/test_cidr_db_updater_service.py': 'Обновление CIDR-провайдеров в SQLite: загрузка, аномалии, очистка.',
    'tests/test_cidr_list_updater.py': 'Формирование CIDR-списков, лимиты маршрутов OpenVPN и разбор DPI-логов.',
    'tests/test_config_routes_openvpn_block.py': 'HTTP API временной и постоянной блокировки клиентов OpenVPN.',
    'tests/test_db_backup_export.py': 'Экспорт SQLite без CIDR-таблиц и подготовка файлов для бэкапа.',
    'tests/test_db_migration_service.py': 'Миграции схемы БД, в том числе viewer_access и foreign keys.',
    'tests/test_edit_files_page_context.py': 'Контекст редактора конфигов: навигация, скачивание и валидация.',
    'tests/test_firewall_tools_check.py': 'Наличие iptables/ipset и диагностика готовности firewall-инструментов.',
    'tests/test_http_security.py': 'Заголовки безопасности, robots.txt, security.txt и noindex чувствительных путей.',
    'tests/test_index_page_context.py': 'Данные главной страницы: KPI, таблица клиентов, статусы сервисов.',
    'tests/test_index_routes_wg_access.py': 'HTTP API блокировки и разблокировки клиентов WireGuard.',
    'tests/test_ip_restriction_scanner_block.py': 'Rate limit, редирект и жёсткий бан IP при сканировании панели.',
    'tests/test_ip_restriction_temporary.py': 'Временное добавление IP в whitelist и синхронизация с firewall.',
    'tests/test_ip_restriction_whitelist_firewall_gating.py': 'Когда включать whitelist-firewall в зависимости от режима публикации.',
    'tests/test_maintenance_scheduler_backup.py': 'Строки crontab для автоматического бэкапа панели.',
    'tests/test_notify_time.py': 'Форматирование времени уведомлений с учётом часового пояса клиента.',
    'tests/test_openvpn_access_policy_service.py': 'Блокировка, разблокировка и смена режима доступа OpenVPN-клиентов.',
    'tests/test_panel_port_firewall.py': 'ipset/iptables для ограничения доступа к порту панели по whitelist.',
    'tests/test_panel_publish_info.py': 'Режим публикации панели: reverse proxy, HTTPS, прямой HTTP.',
    'tests/test_routing_page_context.py': 'Контекст страницы маршрутизации и лимиты CIDR OpenVPN.',
    'tests/test_safe_browsing_status_cli.py': 'Разбор ответа Google Safe Browsing для CLI-проверки домена.',
    'tests/test_scanner_firewall_store.py': 'Хранение strikes и банов IP сканеров с нарастающими сроками.',
    'tests/test_session_security.py': 'Параметры Flask-сессии: secure cookie, SameSite, remember me.',
    'tests/test_settings_api_action_logs_export.py': 'API выгрузки журнала действий в CSV.',
    'tests/test_settings_page_context.py': 'Ключи контекста страницы настроек панели.',
    'tests/test_settings_post_handlers.py': 'Обработка POST-форм настроек: порт, Telegram ID, бэкапы.',
    'tests/test_site_diagnostics.py': 'Диагностика systemd-сервиса, сертификатов и journalctl-подсказок.',
    'tests/test_system_preflight.py': 'Проверка зависимостей Python, модулей и iptables перед запуском.',
    'tests/test_telegram_webapp_init_data.py': 'Проверка подписи initData Telegram WebApp.',
    'tests/test_temporary_whitelist_store.py': 'JSON-хранилище временных IP с TTL и продлением.',
    'tests/test_tg_mini_session.py': 'Сессия Telegram Mini App и ограничение API без неё.',
    'tests/test_wg_access_policy_service.py': 'Политика блокировки WireGuard: temp, permanent, extend после expiry.',
    'tests/test_wg_awg_runtime_enforcer.py': 'Снятие и восстановление peer WireGuard/AWG в runtime без перезапуска.',
    'tests/test_wg_runtime_subprocess.py': 'Вызов wg_awg_policy_sync.py и обработка JSON-ответа subprocess.',
}

TEST_ENTRIES: dict[str, dict[str, str]] = {
    'tests/test_access_remaining.py::AccessRemainingTests::test_23_hours_59_minutes': {
        "title": 'Остаток доступа: граница суток',
        "description": 'При 23 ч. 59 мин. до истечения формат остаётся почасовым, без преждевременного перехода к дням.',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_expired_two_hours_ago': {
        "title": 'Остаток доступа: срок истёк',
        "description": 'Для прошедшей даты истечения возвращается фиксированная строка «срок истёк».',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_less_than_24_hours_shows_hours_and_minutes': {
        "title": 'Остаток доступа: часы и минуты',
        "description": 'Если до истечения меньше суток, отображаются часы и минуты (например «5 ч. 30 мин.»).',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_minutes_only': {
        "title": 'Остаток доступа: только минуты',
        "description": 'Если до истечения меньше часа, показываются только минуты («45 мин.»).',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_none_returns_none': {
        "title": 'Остаток доступа: None → None',
        "description": 'Проверяет, что при отсутствии даты истечения функция format_access_remaining возвращает None.',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_one_hour_only': {
        "title": 'Остаток доступа: ровно 1 час',
        "description": 'Для ровно одного часа выводится «1 ч.» без минут.',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_parses_openvpn_utc_string': {
        "title": 'Остаток доступа: OpenVPN UTC',
        "description": 'Корректно разбирает формат OpenVPN с суффиксом UTC и форматирует остаток в часах.',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_parses_string_expires_at': {
        "title": 'Остаток доступа: строка datetime',
        "description": 'Парсит expires_at в виде строки «YYYY-MM-DD HH:MM:SS» и корректно считает оставшееся время.',
    },
    'tests/test_access_remaining.py::AccessRemainingTests::test_ten_days_left': {
        "title": 'Остаток доступа: 10 дней',
        "description": 'При сроке больше суток возвращается краткая строка в днях («10 дн.»), без часов и минут.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_client_ban_legacy_blocked_flags': {
        "title": 'Уведомление: legacy blocked=0/1',
        "description": 'Старые details blocked=1 интерпретируются как постоянная блокировка; blocked=0 — как разблокировка.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_client_ban_temp_permanent_and_unblock': {
        "title": 'Уведомление: блокировки WireGuard',
        "description": 'client_ban для temp/permanent/unblock: русские формулировки, срок 7 дн., дата block_until, протокол WireGuard.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_config_create_openvpn_narrative': {
        "title": 'Уведомление: создание OpenVPN',
        "description": 'config_create для OpenVPN: 4 строки, «Создал», тип протокола и имя клиента в code.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_config_delete_four_line_layout': {
        "title": 'Уведомление: удаление конфига',
        "description": 'Текст config_delete — 4 строки с эмодзи, HTML-кодом имени и временем без слова «удалил» в строке админа.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_login_success_four_line_layout': {
        "title": 'Уведомление: успешный вход',
        "description": 'login_success: 4 строки, «Вошёл» и IP удалённого адреса в code.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_settings_change_nightly_russian': {
        "title": 'Уведомление: ночной рестарт',
        "description": 'settings_nightly_update человекочитаемо: включён, 04:00, TTL/touch без сырых enabled=/cron=.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_settings_change_port_russian': {
        "title": 'Уведомление: смена порта',
        "description": 'settings_port_update: «Порт панели» и «с 5050 на 8080» в тексте действия.',
    },
    'tests/test_admin_notify.py::AdminNotifyTextTests::test_settings_change_uses_client_timezone': {
        "title": 'Уведомление: часовой пояс клиента',
        "description": 'При settings_change и Europe/Moscow метка времени формируется без суффикса UTC.',
    },
    'tests/test_admin_routes.py::AdminRoutesTests::test_api_task_status_returns_404_for_unknown_task': {
        "title": 'Статус фоновой задачи: 404 для неизвестного ID',
        "description": 'API /api/task-status/<id> возвращает 404 и JSON-ошибку, если задача с таким ID не найдена.',
    },
    'tests/test_admin_routes.py::AdminRoutesTests::test_api_task_status_returns_payload_for_existing_task': {
        "title": 'Статус фоновой задачи: данные для существующей задачи',
        "description": 'Для существующей фоновой задачи API возвращает статус, прогресс и вывод команды в JSON.',
    },
    'tests/test_admin_routes.py::AdminRoutesTests::test_update_system_returns_accepted_task_response': {
        "title": 'Обновление системы: ответ «задача принята»',
        "description": 'POST /admin/update-system ставит задачу в очередь и отвечает 202 с task_id для отслеживания.',
    },
    'tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_grant_allows_same_name_for_different_protocol': {
        "title": 'Доступ viewer: одно имя для разных протоколов',
        "description": 'Выдача viewer-доступа разрешает одно имя клиента для OpenVPN и WireGuard одновременно.',
    },
    'tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_non_json_request_returns_consistent_json_error': {
        "title": 'Доступ viewer: ошибка при не-JSON запросе',
        "description": 'Запрос viewer_access без Content-Type: application/json возвращает JSON-ошибку, а не HTML.',
    },
    'tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_revoke_removes_only_requested_protocol': {
        "title": 'Доступ viewer: отзыв только выбранного протокола',
        "description": 'Отзыв viewer-доступа удаляет только указанный протокол, не затрагивая другие.',
    },
    'tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_validates_missing_json_payload': {
        "title": 'Доступ viewer: проверка пустого JSON',
        "description": 'Пустое или отсутствующее JSON-тело запроса viewer_access отклоняется с понятной ошибкой.',
    },
    'tests/test_antizapret_backup.py::AntizapretBackupTests::test_create_backup_missing_client_sh': {
        "title": 'Antizapret: нет client.sh',
        "description": 'Отсутствие client.sh вызывает FileNotFoundError — бэкап невозможен без скрипта установки.',
    },
    'tests/test_antizapret_backup.py::AntizapretBackupTests::test_create_backup_raises_on_script_failure': {
        "title": 'Antizapret: ошибка скрипта',
        "description": 'Ненулевой exit code client.sh приводит к RuntimeError с текстом ошибки.',
    },
    'tests/test_antizapret_backup.py::AntizapretBackupTests::test_create_backup_runs_client_sh': {
        "title": 'Antizapret: create_backup',
        "description": 'create_backup запускает client.sh и возвращает существующий archive_path и имя файла.',
    },
    'tests/test_antizapret_backup.py::AntizapretBackupTests::test_resolve_archive_from_stdout': {
        "title": 'Antizapret: путь из stdout',
        "description": 'Из вывода client.sh извлекается абсолютный путь к созданному tar.gz.',
    },
    'tests/test_antizapret_backup.py::AntizapretBackupTests::test_resolve_archive_newest_glob': {
        "title": 'Antizapret: новейший архив',
        "description": 'При пустом stdout выбирается самый новый backup-*.tar.gz в каталоге установки.',
    },
    'tests/test_app_auto_backup.py::AppAutoBackupTests::test_load_admin_chat_ids_filters_selected_admins': {
        "title": 'Авто-бэкап: chat_id админов',
        "description": 'load_admin_chat_ids возвращает telegram_id только выбранных admin user id.',
    },
    'tests/test_app_auto_backup.py::AppAutoBackupTests::test_main_sends_panel_and_az_documents': {
        "title": 'Авто-бэкап: main → Telegram',
        "description": 'app_auto_backup.main при включённых флагах отправляет 4 документа (панель + antizapret) через send_tg_document.',
    },
    'tests/test_app_auto_backup.py::AppAutoBackupTests::test_run_backup_job_test_mode_forces_telegram': {
        "title": 'Ручной бэкап: принудительная отправка в Telegram',
        "description": 'Проверяет, что тестовый запуск бэкапа отправляет архив в Telegram даже при выключенной авто-отправке в .env; в подписи файла указано «Ручной бэкап».',
    },
    'tests/test_audit_view_presenter_action_logs.py::AuditViewPresenterActionLogsTests::test_build_user_action_audit_view_adds_normalized_columns': {
        "title": 'Аудит: нормализация login_failed',
        "description": 'Добавляет actor_display, status warning, search_blob, csv_row с русским действием для login_failed.',
    },
    'tests/test_audit_view_presenter_action_logs.py::AuditViewPresenterActionLogsTests::test_build_user_action_audit_view_humanizes_monitor_details': {
        "title": 'Аудит: мониторинг',
        "description": 'details_display для settings_monitor_update содержит «интервал проверки» и «пауза уведомлений».',
    },
    'tests/test_audit_view_presenter_action_logs.py::AuditViewPresenterActionLogsTests::test_build_user_action_audit_view_humanizes_viewer_access_details': {
        "title": 'Аудит: доступ viewer',
        "description": 'settings_viewer_access_grant → «Выдан доступ» и число конфигов в details_display.',
    },
    'tests/test_audit_view_presenter_tg.py::AuditViewPresenterTgTests::test_nightly_details_humanized': {
        "title": 'TG-аудит: ночной рестарт',
        "description": '_format_nightly_update_details переводит cron/TTL в русский текст с 04:00.',
    },
    'tests/test_audit_view_presenter_tg.py::AuditViewPresenterTgTests::test_tg_action_line_backup_restore': {
        "title": 'TG-аудит: восстановление',
        "description": 'settings_backup_restore упоминает имя архива и «Восстановление».',
    },
    'tests/test_audit_view_presenter_tg.py::AuditViewPresenterTgTests::test_tg_action_line_backup_send_telegram': {
        "title": 'TG-аудит: отправка бэкапа',
        "description": 'settings_backup_test_telegram — про создание бэкапа, без слова «тестов».',
    },
    'tests/test_audit_view_presenter_tg.py::AuditViewPresenterTgTests::test_tg_action_line_backup_settings_russian': {
        "title": 'TG-аудит: настройки бэкапа',
        "description": 'settings_backup_update без enabled=; русские интервал, компоненты и Telegram.',
    },
    'tests/test_audit_view_presenter_tg.py::AuditViewPresenterTgTests::test_tg_action_line_port_arrow': {
        "title": 'TG-аудит: порт',
        "description": 'user_action_tg_action_line для settings_port_update: «Порт панели: с 5050 на 8080».',
    },
    'tests/test_auth_routes_login.py::AuthRoutesLoginTests::test_login_failure_increments_attempts': {
        "title": 'Неудачный вход увеличивает счётчик попыток',
        "description": 'При неверном пароле счётчик неудачных попыток входа увеличивается для rate limiting.',
    },
    'tests/test_auth_routes_login.py::AuthRoutesLoginTests::test_login_success_with_remember_me_uses_config_days': {
        "title": 'Успешный вход с «Запомнить меня» и сроком из конфига',
        "description": 'При включённом «Запомнить меня» срок сессии берётся из REMEMBER_ME_DAYS конфигурации.',
    },
    'tests/test_auth_routes_login.py::AuthRoutesLoginTests::test_login_success_without_remember_me': {
        "title": 'Успешный вход без «Запомнить меня»',
        "description": 'Успешный вход без галочки «Запомнить меня» создаёт обычную сессию без extended lifetime.',
    },
    'tests/test_background_tasks_service.py::BackgroundTaskServiceTests::test_enqueue_background_task_creates_record_and_submits_executor': {
        "title": 'Постановка задачи в очередь и запуск исполнителя',
        "description": 'enqueue_background_task создаёт запись в хранилище и отправляет задачу в ThreadPoolExecutor.',
    },
    'tests/test_background_tasks_service.py::BackgroundTaskServiceTests::test_run_background_task_marks_completed_and_trims_output': {
        "title": 'Завершение задачи и обрезка вывода',
        "description": 'run_background_task помечает задачу completed и обрезает длинный stdout до лимита.',
    },
    'tests/test_background_tasks_service.py::BackgroundTaskServiceTests::test_run_checked_command_raises_runtime_error_on_nonzero_exit': {
        "title": 'Ошибка при ненулевом коде команды',
        "description": 'run_checked_command бросает RuntimeError, если subprocess завершился с ненулевым кодом.',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_create_backup_archive_db_has_no_cidr_tables': {
        "title": 'Бэкап-менеджер: без CIDR в SQLite',
        "description": 'В выгруженной users.db есть user, но нет provider_cidr — CIDR не попадает в архив.',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_create_backup_includes_db_env_data': {
        "title": 'Бэкап-менеджер: db+env+data',
        "description": 'Архив содержит компоненты db/env/data, summary с DATA и пометкой «без CIDR».',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_db_candidates_globs_all_sqlite_files': {
        "title": 'Бэкап-менеджер: кандидаты SQLite',
        "description": '_db_candidates находит users.db и site.db в instance.',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_default_components': {
        "title": 'Бэкап-менеджер: компоненты по умолчанию',
        "description": 'default_components() возвращает ["db", "env", "data"].',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_delete_backup_removes_archive_and_meta': {
        "title": 'Бэкап-менеджер: удаление',
        "description": 'delete_backup удаляет и .tar.gz, и .meta.json.',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_enrich_backup_list_entry_full_panel': {
        "title": 'Бэкап-менеджер: полный бэкап',
        "description": 'enrich помечает полный бэкап панели для переустановки.',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_enrich_backup_list_entry_legacy': {
        "title": 'Бэкап-менеджер: legacy',
        "description": 'Старый data-only бэкап описывается как «старый скриптовый».',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_enrich_backup_list_entry_without_cidr': {
        "title": 'Бэкап-менеджер: без базы CIDR',
        "description": 'При db_without_cidr описание содержит «без базы CIDR».',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_normalize_components_drops_unknown_and_configs': {
        "title": 'Бэкап-менеджер: нормализация компонентов',
        "description": 'configs и дубликаты отбрасываются; остаются db и data.',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_prune_old_backups_keeps_max_five': {
        "title": 'Бэкап-менеджер: ротация',
        "description": 'После 6 созданий остаётся не более 5 архивов (retention_count=5).',
    },
    'tests/test_backup_manager_service.py::BackupManagerServiceTests::test_restore_backup_runs_service_control': {
        "title": 'Бэкап-менеджер: restore',
        "description": 'restore_backup дважды вызывает _service_control (stop/start).',
    },
    'tests/test_backup_telegram_job.py::BackupTelegramJobTests::test_build_panel_uses_fallback_when_full_too_large': {
        "title": 'TG-бэкап: fallback >50 МБ',
        "description": 'Слишком большой архив заменяется урезанным; notice про 50 МБ и cleanup_dirs.',
    },
    'tests/test_backup_telegram_job.py::BackupTelegramJobTests::test_file_fits_telegram': {
        "title": 'TG-бэкап: лимит размера',
        "description": 'file_fits_telegram true для 1 КБ и false для ~51 МБ.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_build_degradation_alerts_keeps_global_drop_without_cleared_baseline': {
        "title": 'CIDR DB: global alert',
        "description": 'Без cleared baseline создаётся global degradation alert с числами CIDR до и после падения.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_build_degradation_alerts_skips_global_drop_after_cleared_baseline': {
        "title": 'CIDR DB: без alert после clear',
        "description": 'Глобальное падение CIDR не алертит, если предыдущий лог refresh имеет status=cleared.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_clear_provider_data_deletes_selected_provider_rows': {
        "title": 'CIDR DB: clear провайдера',
        "description": 'Удаляет CIDR/ASN/snapshot/meta для выбранного провайдера и делает commit.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_clear_provider_data_full_clear_removes_refresh_history': {
        "title": 'CIDR DB: полный clear',
        "description": 'Полная очистка удаляет cidr_db_refresh_log и все записи провайдеров.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_clear_provider_data_rejects_invalid_targets': {
        "title": 'CIDR DB: clear — неверный файл',
        "description": 'unknown-provider.txt → success=false, providers_cleared=0.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_compute_provider_anomaly_marks_critical_on_large_drop': {
        "title": 'Аномалия провайдера: критично при большом падении',
        "description": 'При резком падении числа CIDR без ошибок загрузки аномалия помечается как critical.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_compute_provider_anomaly_softens_asn_errors_for_healthy_pool_after_clear': {
        "title": 'CIDR DB: смягчение ASN-ошибок',
        "description": 'При большом healthy pool после clear аномалия info, не critical, с текстом про ошибки ASN.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_discover_provider_asns_combines_seed_source_and_scan': {
        "title": 'Поиск ASN: объединение seed и сканирования',
        "description": 'discover_provider_asns объединяет ASN из seed-файлов, источников и BGP-сканирования.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_discover_provider_asns_skips_scan_when_limit_zero': {
        "title": 'Поиск ASN: без скана при лимите 0',
        "description": 'При scan_limit=0 BGP-сканирование не выполняется, используются только seed и sources.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_download_asn_cidrs_with_meta_retries_after_transient_failure': {
        "title": 'CIDR DB: retry ASN',
        "description": 'Третья попытка после двух RuntimeError успешна; sleep вызывается между попытками.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_download_asn_cidrs_with_meta_uses_bgp_state_fallback': {
        "title": 'Загрузка CIDR ASN: fallback из BGP state',
        "description": 'При недоступности основного источника CIDR ASN берутся из BGP state fallback.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_download_cidrs_with_meta_parallel_keeps_source_order': {
        "title": 'CIDR DB: порядок источников',
        "description": 'Параллельная загрузка сохраняет source_used «source-a, source-b» и оба CIDR.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_download_cidrs_with_meta_uses_ttl_cache_for_repeated_calls': {
        "title": 'CIDR DB: TTL-кэш источников',
        "description": 'Второй вызов — cache_hit=true, _download_text только один раз.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_extract_asns_from_sources_akamai_ripe_only': {
        "title": 'CIDR DB: ASN Akamai RIPE',
        "description": 'Из akamai-ips.txt извлекается AS20940; источники без bgp-tools в имени.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_extract_asns_from_sources_empty_for_json_and_official_cidr_providers': {
        "title": 'CIDR DB: пустые ASN у JSON/official',
        "description": 'amazon/google/cloudflare — пустое множество ASN из sources (официальные CIDR без ASN-скана).',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_extract_asns_from_sources_reads_hetzner_ripe_urls': {
        "title": 'CIDR DB: ASN Hetzner',
        "description": 'Из hetzner-ips.txt извлекаются ASN 24940, 213230, 212317, 215859.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_helper_parsing_and_workers': {
        "title": 'Разбор вспомогательных данных и воркеры',
        "description": 'Проверяет парсинг CIDR/ASN, нормализацию worker count и базовые helper-функции сервиса.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_merge_cidr_items_prefers_richer_geo_metadata': {
        "title": 'Слияние CIDR: приоритет расширенной geo-метаданной',
        "description": 'При слиянии дубликатов CIDR сохраняется запись с более полными geo-полями.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_provider_sources_do_not_use_bgp_tools': {
        "title": 'CIDR DB: без bgp-tools',
        "description": 'Ни один PROVIDER_SOURCES не использует bgp-tools/cidr_text_scan.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_refresh_akamai_ripe_only_keeps_status_ok_without_discovery_errors': {
        "title": 'CIDR DB: refresh Akamai',
        "description": 'Akamai через RIPE: ok, expected_asn_min=1, пустые asn_errors.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_refresh_all_providers_dry_run_skips_db_writes': {
        "title": 'CIDR DB: dry_run refresh',
        "description": 'dry_run=true: success, без upsert/update_meta в БД.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_refresh_cloudflare_official_only_keeps_status_ok_without_asn': {
        "title": 'CIDR DB: refresh Cloudflare',
        "description": 'Cloudflare-only refresh: success, ok, 0 ASN, без asn_errors.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_refresh_digitalocean_ripe_only_keeps_status_ok': {
        "title": 'CIDR DB: refresh DigitalOcean',
        "description": 'DO с двумя ASN: ok, expected_asn_min=2.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_should_not_preserve_previous_pool_for_stable_small_provider_without_errors': {
        "title": 'CIDR DB: малый стабильный провайдер',
        "description": '15→15 CIDR без ошибок — предыдущий пул не сохраняется (false).',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_should_preserve_previous_pool_accepts_large_healthy_candidate': {
        "title": 'CIDR DB: принять большой пул',
        "description": 'Без ошибок большой кандидат не сохраняет старый пул — принимается новый (false).',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_should_preserve_previous_pool_on_hard_drop_without_errors': {
        "title": 'Сохранение пула при резком падении без ошибок',
        "description": 'При резком падении CIDR без ошибок загрузки предыдущий пул сохраняется.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_should_preserve_previous_pool_when_candidate_empty': {
        "title": 'CIDR DB: сохранить при пустом кандидате',
        "description": '_should_preserve_previous_pool true при candidate_cidr_count=0.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_should_preserve_previous_pool_when_candidate_too_small': {
        "title": 'CIDR DB: кандидат слишком мал',
        "description": '70 из 1000 CIDR — сохранение предыдущего пула как защита от деградации.',
    },
    'tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_should_preserve_previous_pool_when_errors_and_large_drop': {
        "title": 'CIDR DB: сохранить при ошибках',
        "description": 'При asn_errors и большом падении — preserve true, чтобы не потерять рабочий пул.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_analyze_dpi_log_builds_priority_files': {
        "title": 'Разбор DPI-лога: приоритетные файлы',
        "description": 'analyze_dpi_log формирует список приоритетных CIDR-файлов по частоте блокировок в логе.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_analyze_dpi_log_supports_dpi_detector_table_format': {
        "title": 'Разбор DPI-лога: табличный формат детектора',
        "description": 'Поддерживается табличный формат dpi_detector, не только построчный лог.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_apply_total_route_limit_keeps_mandatory_detected_file': {
        "title": 'Лимит маршрутов: обязательный detected-файл',
        "description": 'При урезании бюджета обязательный detected-файл всегда остаётся в списке.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_apply_total_route_limit_with_budget_smaller_than_file_count': {
        "title": 'Лимит маршрутов: бюджет меньше числа файлов',
        "description": 'Если бюджет меньше числа файлов, выбираются наиболее приоритетные до лимита.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_apply_total_route_limit_with_dpi_priority_reserve': {
        "title": 'Лимит маршрутов: резерв под DPI-приоритет',
        "description": 'Часть бюджета резервируется под DPI-приоритетные файлы перед остальными.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_collect_cidrs_skips_geo_source_when_all_scope_has_non_geo_results': {
        "title": 'Сбор CIDR: пропуск geo при non-geo в all',
        "description": 'Для scope=all geo-источник пропускается, если уже есть non-geo результаты.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_compress_cidrs_to_limit_does_not_overcompress_far_below_budget': {
        "title": 'Сжатие CIDR: без пересжатия далеко ниже бюджета',
        "description": 'compress_cidrs_to_limit не сжимает агрессивно, если результат уже далеко ниже бюджета.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_compress_cidrs_to_limit_never_returns_default_route': {
        "title": 'Сжатие CIDR: без default route',
        "description": 'Сжатие CIDR никогда не возвращает маршрут 0.0.0.0/0.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_estimate_applies_route_optimization_for_large_geo_result': {
        "title": 'Оценка: оптимизация маршрутов для большого geo',
        "description": 'estimate для большого geo-результата применяет оптимизацию числа маршрутов.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_estimate_cidr_matches': {
        "title": 'Оценка совпадений CIDR',
        "description": 'estimate_cidr_matches корректно считает пересечения CIDR-списков.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_estimate_excludes_ru_cidrs_for_all_scope': {
        "title": 'Оценка: исключение RU CIDR для all',
        "description": 'Для scope=all российские CIDR исключаются из оценки маршрутов.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_bgp_tools_raw_allocations_section': {
        "title": 'Извлечение CIDR из BGP.tools (allocations)',
        "description": 'Парсит секцию allocations из сырого ответа BGP.tools.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_google_json_strict_mode_excludes_ambiguous_scope': {
        "title": 'Извлечение CIDR из Google JSON (strict)',
        "description": 'strict mode исключает CIDR с неоднозначным scope из Google JSON.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_ripe_geo_json': {
        "title": 'Извлечение CIDR из RIPE geo JSON',
        "description": 'extract_cidrs_from_ripe_geo_json извлекает CIDR с geo-метаданными.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_ripe_geo_json_strict_mode_excludes_ambiguous': {
        "title": 'Извлечение CIDR из RIPE geo JSON (strict)',
        "description": 'strict mode исключает CIDR с неоднозначным scope из RIPE geo JSON.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_ripe_json': {
        "title": 'Извлечение CIDR из RIPE JSON',
        "description": 'extract_cidrs_from_ripe_json парсит стандартный RIPE JSON-формат.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_non_geo_provider_can_be_included_with_fallback': {
        "title": 'Non-geo провайдер с резервным источником',
        "description": 'Non-geo провайдер включается через fallback-источник, если основной недоступен.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_prune_runtime_backups_removes_directories_older_than_12_hours': {
        "title": 'Очистка runtime-бэкапов старше 12 часов',
        "description": 'prune_runtime_backups удаляет каталоги runtime-бэкапов старше 12 часов.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_sync_game_hosts_filter_runs_without_cidr_update': {
        "title": 'Синхронизация game hosts без обновления CIDR',
        "description": 'sync_game_hosts_filter выполняется без полного обновления CIDR-списков.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_sync_games_include_hosts_enable_and_disable': {
        "title": 'Включение и отключение games include hosts',
        "description": 'sync_games_include_hosts корректно включает и отключает фильтр game hosts.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_total_limit_reads_from_env_file_runtime': {
        "title": 'Общий лимит читается из env/runtime',
        "description": 'total_limit берётся из env-файла или runtime-конфигурации antizapret.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_update_applies_global_total_route_limit': {
        "title": 'Обновление применяет глобальный лимит маршрутов',
        "description": 'update применяет глобальный total_route_limit ко всем провайдерам.',
    },
    'tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_update_selected_and_rollback_to_baseline': {
        "title": 'Обновление выбранных и откат к baseline',
        "description": 'update_selected обновляет выбранные провайдеры; rollback восстанавливает baseline.',
    },
    'tests/test_config_routes_openvpn_block.py::ConfigRoutesOpenVpnBlockTests::test_legacy_blocked_flag_maps_to_permanent_block': {
        "title": 'API OpenVPN: blocked=1',
        "description": 'Устаревший параметр blocked=1 мапится на permanent_block.',
    },
    'tests/test_config_routes_openvpn_block.py::ConfigRoutesOpenVpnBlockTests::test_temp_block_action': {
        "title": 'API OpenVPN: temp_block',
        "description": 'POST /api/openvpn/client-block с action=temp_block вызывает openvpn_set_temp_block_days и 200 JSON success.',
    },
    'tests/test_db_backup_export.py::DbBackupExportTests::test_export_excludes_cidr_tables': {
        "title": 'Экспорт БД: без CIDR',
        "description": 'export_sqlite_excluding_tables не копирует provider_cidr и таблицы из BACKUP_EXCLUDED_TABLES.',
    },
    'tests/test_db_backup_export.py::DbBackupExportTests::test_prepare_skips_wal_shm_when_main_exported': {
        "title": 'Экспорт БД: без WAL/SHM',
        "description": 'prepare_db_files_for_backup отдаёт один экспортированный файл, db_without_cidr=true, данные user на месте.',
    },
    'tests/test_db_migration_service.py::DatabaseMigrationServiceTests::test_viewer_access_migration_recovers_from_stale_temp_table': {
        "title": 'Миграция viewer_access: восстановление после temp-таблицы',
        "description": 'Миграция viewer_access восстанавливается, если осталась устаревшая temp-таблица.',
    },
    'tests/test_db_migration_service.py::DatabaseMigrationServiceTests::test_viewer_access_migration_reenables_foreign_keys_after_error': {
        "title": 'Миграция viewer_access: FK после ошибки',
        "description": 'После ошибки миграции foreign keys снова включаются.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_build_edit_files_get_context_first_item_active': {
        "title": 'Контекст редактора: первый элемент активен',
        "description": 'build_edit_files_get_context помечает первый файл в группе как active.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_build_route_download_actions_with_public': {
        "title": 'Ссылки скачивания маршрутов с public',
        "description": 'build_route_download_actions с public URL добавляет публичные ссылки скачивания.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_build_route_download_actions_without_public': {
        "title": 'Ссылки скачивания маршрутов без public',
        "description": 'build_route_download_actions без public URL формирует только внутренние ссылки.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_adblock': {
        "title": 'Группа навигации: adblock',
        "description": 'resolve_file_nav_group относит adblock-файлы к группе adblock.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_allow_ips': {
        "title": 'Группа навигации: allow IPs',
        "description": 'resolve_file_nav_group относит allow-ips файлы к соответствующей группе.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_domains': {
        "title": 'Группа навигации: domains',
        "description": 'resolve_file_nav_group относит domains-файлы к группе domains.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_ip_routing': {
        "title": 'Группа навигации: IP routing',
        "description": 'resolve_file_nav_group относит ip-routing файлы к группе IP routing.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_other': {
        "title": 'Группа навигации: прочие файлы',
        "description": 'resolve_file_nav_group относит неизвестные файлы к группе «прочие».',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_validate_editor_content_null_byte': {
        "title": 'Валидация: запрет null-byte в содержимом',
        "description": 'validate_editor_content отклоняет содержимое с null-byte (\\x00).',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_validate_editor_content_too_large': {
        "title": 'Валидация: слишком большой файл',
        "description": 'validate_editor_content отклоняет файл, превышающий лимит размера.',
    },
    'tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_validate_editor_content_valid': {
        "title": 'Валидация: корректное содержимое',
        "description": 'validate_editor_content принимает корректное содержимое без ошибок.',
    },
    'tests/test_firewall_tools_check.py::FirewallToolsCheckTests::test_apt_install_hint': {
        "title": 'Firewall tools: apt hint',
        "description": 'apt_install_hint формирует корректные команды apt install для iptables/ipset.',
    },
    'tests/test_firewall_tools_check.py::FirewallToolsCheckTests::test_check_fully_ready': {
        "title": 'Firewall tools: fully_ready',
        "description": 'check_firewall_tools.fully_ready true при установленных пакетах и успешном probe.',
    },
    'tests/test_firewall_tools_check.py::FirewallToolsCheckTests::test_missing_commands': {
        "title": 'Firewall tools: нет бинарников',
        "description": 'missing_firewall_commands возвращает iptables и ipset, если which их не находит.',
    },
    'tests/test_firewall_tools_check.py::FirewallToolsCheckTests::test_probe_iptables_fails': {
        "title": 'Firewall tools: probe fail',
        "description": 'При ошибке iptables probe возвращает ok=false и detail с «iptables».',
    },
    'tests/test_firewall_tools_check.py::FirewallToolsCheckTests::test_probe_ok': {
        "title": 'Firewall tools: probe OK',
        "description": 'probe_firewall_tools успешен при рабочих iptables -L и ipset version.',
    },
    'tests/test_http_security.py::test_apply_security_headers_sets_csp_and_noindex_for_login': {
        "title": 'Заголовки безопасности: CSP и noindex на login',
        "description": 'apply_security_headers добавляет CSP и X-Robots-Tag noindex на странице login.',
    },
    'tests/test_http_security.py::test_build_robots_txt_blocks_download_paths': {
        "title": 'robots.txt блокирует пути скачивания',
        "description": 'build_robots_txt содержит Disallow для путей скачивания конфигов.',
    },
    'tests/test_http_security.py::test_build_security_txt_has_no_vpn_wording': {
        "title": 'security.txt без VPN-формулировок',
        "description": 'build_security_txt не содержит упоминаний VPN в тексте политики.',
    },
    'tests/test_http_security.py::test_get_panel_branding_uses_domain_only': {
        "title": 'Брендинг панели: только домен',
        "description": 'get_panel_branding использует только домен, без лишних префиксов.',
    },
    'tests/test_http_security.py::test_should_noindex_sensitive_paths': {
        "title": 'noindex для чувствительных путей',
        "description": 'should_noindex возвращает true для login, settings и других чувствительных путей.',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_build_client_table_rows_cert_state': {
        "title": 'Таблица клиентов: статусы сертификатов',
        "description": 'build_client_table_rows корректно отображает статусы сертификатов OpenVPN.',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_build_client_table_rows_wireguard_policy_block_state': {
        "title": 'Таблица WG: policy state',
        "description": 'Строка wireguard: не blocked, wg_days_left ~10, block_mode none, expires_at заполнен.',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_build_client_table_rows_wireguard_shows_hours_when_less_than_day': {
        "title": 'Таблица WG: часы до истечения',
        "description": 'При <24 ч access_remaining_text содержит «ч.», access_days_left=0, без «сегодня».',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_build_index_get_context_counts_wg_awg_block_once_per_client': {
        "title": 'Главная: блокировка по клиенту',
        "description": 'WG+AWG блок считается один раз на клиента; blocked_total=2 при двух заблокированных.',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_build_index_kpi_counts_expiring_and_expired': {
        "title": 'KPI главной: истекающие и просроченные',
        "description": 'build_index_kpi считает клиентов с истекающим и просроченным доступом.',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_collect_grouped_service_statuses_without_systemctl': {
        "title": 'Статусы сервисов без systemctl',
        "description": 'collect_grouped_service_statuses работает без systemctl через fallback.',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_group_config_files_by_client_splits_antizapret_and_vpn': {
        "title": 'Группировка конфигов VPN и antizapret',
        "description": 'group_config_files_by_client разделяет antizapret и VPN-конфиги по клиентам.',
    },
    'tests/test_index_page_context.py::IndexPageContextTests::test_resolve_openvpn_group_and_files_filters_viewer_configs': {
        "title": 'OpenVPN-группа и фильтр для viewer',
        "description": 'resolve_openvpn_group_and_files скрывает конфиги, недоступные viewer-пользователю.',
    },
    'tests/test_index_routes_wg_access.py::IndexRoutesWgAccessTests::test_wg_api_rejects_invalid_action': {
        "title": 'API WG: неверный action',
        "description": 'Неизвестный action даёт 400 и success=false.',
    },
    'tests/test_index_routes_wg_access.py::IndexRoutesWgAccessTests::test_wg_permanent_block_api_success': {
        "title": 'API WG: permanent_block',
        "description": 'permanent_block вызывает wg_set_permanent_block и возвращает success.',
    },
    'tests/test_index_routes_wg_access.py::IndexRoutesWgAccessTests::test_wg_temp_block_api_success': {
        "title": 'API WG: temp_block',
        "description": 'POST /api/wg/client-access temp_block → 200, success, block_mode и access_days_left в JSON.',
    },
    'tests/test_index_routes_wg_access.py::IndexRoutesWgAccessTests::test_wg_unblock_expired_returns_409': {
        "title": 'API WG: expired 409',
        "description": 'ExpiredRequiresExtendError при unblock → 409, error_code expired_requires_extend.',
    },
    'tests/test_ip_restriction_scanner_block.py::IPRestrictionScannerBlockTests::test_denied_ip_redirects_until_banned': {
        "title": 'Отклонённый IP: редирект до бана',
        "description": 'Отклонённый IP получает редирект на /ip-blocked до накопления strikes и бана.',
    },
    'tests/test_ip_restriction_scanner_block.py::IPRestrictionScannerBlockTests::test_ip_blocked_unavailable_when_restrictions_disabled': {
        "title": 'Страница блокировки при выключенных ограничениях',
        "description": 'Страница /ip-blocked недоступна (404), когда IP-ограничения выключены.',
    },
    'tests/test_ip_restriction_scanner_block.py::IPRestrictionScannerBlockTests::test_rate_limit_then_hard_deny': {
        "title": 'Rate limit и жёсткий запрет',
        "description": 'После превышения rate limit IP получает жёсткий deny через firewall.',
    },
    'tests/test_ip_restriction_temporary.py::IPRestrictionTemporaryTests::test_clear_all_removes_temporary': {
        "title": 'Временный whitelist: clear_all',
        "description": 'clear_all очищает временный список (пустой display).',
    },
    'tests/test_ip_restriction_temporary.py::IPRestrictionTemporaryTests::test_firewall_sync_includes_temporary': {
        "title": 'Временный whitelist: sync firewall',
        "description": 'sync_whitelist_port_firewall передаёт в panel_fw и постоянные, и временные IP.',
    },
    'tests/test_ip_restriction_temporary.py::IPRestrictionTemporaryTests::test_temporary_allowed_when_enabled': {
        "title": 'Временный whitelist: добавление',
        "description": 'add_temporary_ip разрешает IP при включённых ограничениях; is_ip_allowed true.',
    },
    'tests/test_ip_restriction_temporary.py::IPRestrictionTemporaryTests::test_temporary_rejected_when_disabled': {
        "title": 'Временный whitelist: disabled',
        "description": 'Без ALLOWED_IPS add_temporary_ip возвращает (False, "disabled").',
    },
    'tests/test_ip_restriction_whitelist_firewall_gating.py::IPRestrictionWhitelistFirewallGatingTests::test_is_whitelist_port_firewall_active': {
        "title": 'Whitelist FW: active flag',
        "description": 'is_whitelist_port_firewall_active true при включённом флаге и false после выключения.',
    },
    'tests/test_ip_restriction_whitelist_firewall_gating.py::IPRestrictionWhitelistFirewallGatingTests::test_sync_applies_when_app_https': {
        "title": 'Whitelist FW: app HTTPS',
        "description": 'USE_HTTPS + SSL — firewall sync применяется как при прямом HTTP.',
    },
    'tests/test_ip_restriction_whitelist_firewall_gating.py::IPRestrictionWhitelistFirewallGatingTests::test_sync_applies_when_direct_http': {
        "title": 'Whitelist FW: прямой HTTP',
        "description": 'BIND=0.0.0.0 без HTTPS — sync с allowed_ips, disable не вызывается.',
    },
    'tests/test_ip_restriction_whitelist_firewall_gating.py::IPRestrictionWhitelistFirewallGatingTests::test_sync_disables_when_reverse_proxy': {
        "title": 'Whitelist FW: reverse proxy',
        "description": 'При BIND=127.0.0.1 sync отключает whitelist_firewall и вызывает disable, без sync.',
    },
    'tests/test_maintenance_scheduler_backup.py::MaintenanceSchedulerBackupTests::test_ensure_app_backup_cron_adds_line': {
        "title": 'Cron: добавить app-backup',
        "description": 'ensure_app_backup_cron записывает строку с маркером # app-backup при enabled=true.',
    },
    'tests/test_maintenance_scheduler_backup.py::MaintenanceSchedulerBackupTests::test_ensure_app_backup_cron_removes_when_disabled': {
        "title": 'Cron: убрать app-backup',
        "description": 'При enabled=false строки с # app-backup удаляются из crontab.',
    },
    'tests/test_notify_time.py::NotifyTimeTests::test_format_notify_when_client_zone': {
        "title": 'Время уведомлений: зона клиента',
        "description": 'С Europe/Moscow время форматируется без « UTC» в конце.',
    },
    'tests/test_notify_time.py::NotifyTimeTests::test_format_notify_when_utc_fallback': {
        "title": 'Время уведомлений: UTC',
        "description": 'format_notify_when(None) даёт метку с суффиксом UTC.',
    },
    'tests/test_notify_time.py::NotifyTimeTests::test_normalize_timezone_invalid': {
        "title": 'Время уведомлений: невалидная TZ',
        "description": 'Несуществующая зона → None.',
    },
    'tests/test_notify_time.py::NotifyTimeTests::test_normalize_timezone_valid': {
        "title": 'Время уведомлений: валидная TZ',
        "description": '_normalize_timezone_name принимает Europe/Moscow.',
    },
    'tests/test_openvpn_access_policy_service.py::OpenVpnAccessPolicyServiceTests::test_permanent_to_temp_switch': {
        "title": 'OpenVPN policy: permanent→temp',
        "description": 'После permanent temp_block ставит is_temp_blocked, снимает permanent, reason manual_temp.',
    },
    'tests/test_openvpn_access_policy_service.py::OpenVpnAccessPolicyServiceTests::test_temp_block_reapplies_from_now': {
        "title": 'OpenVPN policy: повтор temp',
        "description": 'Повторный set_temp_block_days сдвигает block_until вперёд и держит клиента в banlist.',
    },
    'tests/test_openvpn_access_policy_service.py::OpenVpnAccessPolicyServiceTests::test_unblock_clears_banlist': {
        "title": 'OpenVPN policy: unblock',
        "description": 'clear_block снимает флаги блокировки и удаляет клиента из banlist.',
    },
    'tests/test_panel_port_firewall.py::PanelPortFirewallTests::test_disable_dry_run': {
        "title": 'Порт FW: dry-run disable',
        "description": 'disable в dry_run возвращает true после sync.',
    },
    'tests/test_panel_port_firewall.py::PanelPortFirewallTests::test_ipv6_entries_ignored': {
        "title": 'Порт FW: игнор IPv6',
        "description": '_ipv4_entries оставляет только IPv4 (/32).',
    },
    'tests/test_panel_port_firewall.py::PanelPortFirewallTests::test_sync_calls_ipset_and_jump': {
        "title": 'Порт FW: ipset и jump',
        "description": 'Реальный sync вызывает команды ipset, цепочку INPUT и --dport 5050.',
    },
    'tests/test_panel_port_firewall.py::PanelPortFirewallTests::test_sync_does_not_create_ipv6_chain': {
        "title": 'Порт FW: без ip6tables',
        "description": 'IPv6 в списке не создаёт ip6tables-цепочку aa-panel-port-jump-v6.',
    },
    'tests/test_panel_port_firewall.py::PanelPortFirewallTests::test_sync_dry_run_accepts_entries': {
        "title": 'Порт FW: dry-run sync',
        "description": 'dry_run sync принимает IPv4/CIDR и запоминает active port 5050.',
    },
    'tests/test_panel_publish_info.py::PanelPublishInfoTests::test_app_https_gunicorn': {
        "title": 'Публикация: HTTPS через Gunicorn',
        "description": 'При USE_HTTPS=true mode_key=app_https, primary URL содержит https и порт.',
    },
    'tests/test_panel_publish_info.py::PanelPublishInfoTests::test_direct_http': {
        "title": 'Публикация: прямой HTTP',
        "description": 'При BIND=0.0.0.0 без HTTPS mode_key=direct_http, internal_url корректен.',
    },
    'tests/test_panel_publish_info.py::PanelPublishInfoTests::test_resolve_panel_publish_mode': {
        "title": 'Публикация: определение режима',
        "description": 'resolve_panel_publish_mode возвращает корректный mode_key для каждой комбинации env.',
    },
    'tests/test_panel_publish_info.py::PanelPublishInfoTests::test_reverse_proxy_with_domain': {
        "title": 'Публикация: reverse proxy с доменом',
        "description": 'При BIND=127.0.0.1 и DOMAIN mode_key=reverse_proxy, primary URL через домен.',
    },
    'tests/test_panel_publish_info.py::PanelPublishInfoTests::test_whitelist_firewall_applicable_without_nginx': {
        "title": 'Whitelist-firewall без nginx',
        "description": 'is_whitelist_port_firewall_applicable true для app_https и direct_http без nginx.',
    },
    'tests/test_routing_page_context.py::RoutingPageContextTests::test_build_routing_page_context_keys': {
        "title": 'Контекст страницы маршрутизации',
        "description": 'build_routing_page_context содержит все обязательные ключи для шаблона.',
    },
    'tests/test_routing_page_context.py::RoutingPageContextTests::test_clamp_openvpn_route_total_cidr_limit_boundaries': {
        "title": 'Ограничение лимита CIDR-маршрутов OpenVPN',
        "description": 'clamp_openvpn_route_total_cidr_limit ограничивает значение min/max границами.',
    },
    'tests/test_routing_page_context.py::RoutingPageContextTests::test_read_antizapret_settings_from_fixture': {
        "title": 'Чтение настроек antizapret из фикстуры',
        "description": 'read_antizapret_settings корректно читает настройки из тестовой фикстуры.',
    },
    'tests/test_routing_page_context.py::RoutingPageContextTests::test_resolve_openvpn_route_total_cidr_limit': {
        "title": 'Разрешение общего лимита CIDR-маршрутов',
        "description": 'resolve_openvpn_route_total_cidr_limit берёт лимит из env с fallback на default.',
    },
    'tests/test_safe_browsing_status_cli.py::test_parse_status_payload_extracts_threat_flag': {
        "title": 'Safe Browsing: угроза',
        "description": 'parse_status_payload из SSR JSON: site, status_code=2, threat_flag=true.',
    },
    'tests/test_safe_browsing_status_cli.py::test_parse_status_payload_for_safe_site': {
        "title": 'Safe Browsing: безопасный',
        "description": 'Для google.com status_code=4 и threat_flag=false.',
    },
    'tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_clear_all_removes_entries': {
        "title": 'Очистка всех записей блокировок',
        "description": 'clear_all удаляет все записи strikes и банов из хранилища.',
    },
    'tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_fifth_strike_is_year_ban': {
        "title": 'Пятый strike — бан на год',
        "description": 'Пятый strike назначает бан на год (365 дней).',
    },
    'tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_persists_ban_and_strikes': {
        "title": 'Сохранение бана и strikes',
        "description": 'Бан и strikes сохраняются между вызовами store.',
    },
    'tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_unban_sets_grace_without_active_ban': {
        "title": 'Разбан: grace period без активного бана',
        "description": 'unban устанавливает grace period даже без активного бана.',
    },
    'tests/test_session_security.py::SessionSecurityConfigTests::test_default_without_https_uses_insecure_cookie': {
        "title": 'Без HTTPS: небезопасная cookie по умолчанию',
        "description": 'Без USE_HTTPS SESSION_COOKIE_SECURE=false по умолчанию.',
    },
    'tests/test_session_security.py::SessionSecurityConfigTests::test_development_default_allows_insecure_cookie': {
        "title": 'Development: разрешена небезопасная cookie',
        "description": 'В development-режиме insecure cookie разрешена.',
    },
    'tests/test_session_security.py::SessionSecurityConfigTests::test_remember_me_and_session_lifetime_are_clamped': {
        "title": 'Remember me и lifetime в допустимых пределах',
        "description": 'REMEMBER_ME_DAYS и PERMANENT_SESSION_LIFETIME ограничиваются min/max.',
    },
    'tests/test_session_security.py::SessionSecurityConfigTests::test_samesite_none_falls_back_to_lax_without_secure': {
        "title": 'SameSite=None → Lax без secure',
        "description": 'SameSite=None без secure cookie откатывается к Lax.',
    },
    'tests/test_session_security.py::SessionSecurityConfigTests::test_ssl_material_enables_secure_cookie': {
        "title": 'SSL-материалы включают secure cookie',
        "description": 'Наличие SSL_CERT и SSL_KEY включает SESSION_COOKIE_SECURE.',
    },
    'tests/test_session_security.py::SessionSecurityConfigTests::test_use_https_enables_secure_cookie': {
        "title": 'USE_HTTPS включает secure cookie',
        "description": 'USE_HTTPS=true включает SESSION_COOKIE_SECURE.',
    },
    'tests/test_settings_api_action_logs_export.py::SettingsApiActionLogsExportTests::test_action_logs_export_returns_csv': {
        "title": 'API: экспорт action-logs CSV',
        "description": 'GET /api/settings/action-logs/export — 200, text/csv, UTF-8 BOM, заголовки и данные admin/IP.',
    },
    'tests/test_settings_page_context.py::SettingsPageContextTests::test_build_settings_page_context_keys': {
        "title": 'Контекст страницы настроек',
        "description": 'build_settings_page_context содержит все обязательные ключи для шаблона настроек.',
    },
    'tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_backup_delete_success': {
        "title": 'Настройки: удаление бэкапа',
        "description": 'handle_backup_delete вызывает delete_backup и success flash с именем файла.',
    },
    'tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_backup_settings_reject_invalid_interval': {
        "title": 'Настройки: неверный интервал бэкапа',
        "description": 'interval_days=2 → flash с ошибкой про допустимые 1/7/30 дней.',
    },
    'tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_backup_settings_save_success': {
        "title": 'Настройки: сохранение бэкапа',
        "description": 'Валидные настройки: set_backup_settings, ensure_app_backup_cron, env, success flash и audit log.',
    },
    'tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_invalid_port_shows_error': {
        "title": 'Некорректный порт — сообщение об ошибке',
        "description": 'Невалидный APP_PORT показывает flash-сообщение об ошибке.',
    },
    'tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_normalize_telegram_id_accepts_valid': {
        "title": 'Нормализация Telegram ID: валидный',
        "description": 'normalize_telegram_id принимает корректный числовой Telegram ID.',
    },
    'tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_normalize_telegram_id_rejects_leading_zero': {
        "title": 'Нормализация Telegram ID: ведущий ноль',
        "description": 'normalize_telegram_id отклоняет ID с ведущим нулём.',
    },
    'tests/test_site_diagnostics.py::DecodeJournalLineTests::test_address_already_in_use': {
        "title": 'Journal: порт занят (Address already in use)',
        "description": 'decode_journal_line распознаёт «Address already in use» и возвращает подсказку про занятый порт.',
    },
    'tests/test_site_diagnostics.py::DecodeJournalLineTests::test_import_error': {
        "title": 'Journal: ImportError / ModuleNotFoundError',
        "description": 'decode_journal_line распознаёт ImportError/ModuleNotFoundError с hint про pip-зависимость.',
    },
    'tests/test_site_diagnostics.py::DecodeJournalLineTests::test_status_203_exec': {
        "title": 'Journal: status=203/EXEC (нет gunicorn)',
        "description": 'decode_journal_line распознаёт status=203/EXEC как отсутствие gunicorn в PATH.',
    },
    'tests/test_site_diagnostics.py::DecodeJournalLineTests::test_unknown_line_returns_none': {
        "title": 'Journal: неизвестная строка без подсказки',
        "description": 'decode_journal_line возвращает None для нераспознанной строки journalctl.',
    },
    'tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_active_service_and_files_ok': {
        "title": 'Диагностика: сервис active и файлы на месте',
        "description": 'run_site_diagnostics ok, когда systemd unit active и файлы приложения на месте.',
    },
    'tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_format_check_result_fields': {
        "title": 'CheckResult: поля warn/detail/hint',
        "description": 'CheckResult содержит поля status, detail, hint_ru для отображения в UI.',
    },
    'tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_https_missing_certificates': {
        "title": 'Диагностика: HTTPS без сертификатов',
        "description": 'При USE_HTTPS без SSL_CERT/SSL_KEY диагностика сообщает fail/warn про сертификаты.',
    },
    'tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_missing_firewall_tools_warns': {
        "title": 'Диагностика: нет firewall tools',
        "description": 'При which=None — warn по iptables и hint_ru с apt install.',
    },
    'tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_missing_unit_reports_fail': {
        "title": 'Диагностика: отсутствует systemd unit',
        "description": 'run_site_diagnostics fail, если systemd unit панели не найден.',
    },
    'tests/test_system_preflight.py::SystemPreflightTests::test_missing_iptables_warns': {
        "title": 'Preflight: нет iptables — warn',
        "description": 'Без iptables/ipset в which preflight даёт warn с «iptables» в detail.',
    },
    'tests/test_system_preflight.py::SystemPreflightTests::test_missing_python_dependency_fails': {
        "title": 'Preflight: ошибка при отсутствии pip-пакета',
        "description": 'Preflight fail, если обязательный pip-пакет не установлен.',
    },
    'tests/test_system_preflight.py::SystemPreflightTests::test_missing_script_module_fails': {
        "title": 'Preflight: отсутствует модуль script_sh',
        "description": 'Preflight fail, если модуль script_sh недоступен.',
    },
    'tests/test_telegram_webapp_init_data.py::test_verify_accepts_init_data_when_signature_in_signed_payload': {
        "title": 'Проверка initData: подпись в signed payload',
        "description": 'verify принимает initData, когда signature включён в signed payload (новый формат Telegram).',
    },
    'tests/test_telegram_webapp_init_data.py::test_verify_accepts_valid_init_data': {
        "title": 'Проверка валидного initData',
        "description": 'verify принимает корректно подписанный initData с актуальным auth_date.',
    },
    'tests/test_telegram_webapp_init_data.py::test_verify_rejects_bad_hash': {
        "title": 'Отклонение неверного hash',
        "description": 'verify отклоняет initData с неверной HMAC-подписью.',
    },
    'tests/test_telegram_webapp_init_data.py::test_verify_rejects_empty[   ]': {
        "title": 'Отклонение строки из пробелов',
        "description": 'verify отклоняет initData, состоящий только из пробелов.',
    },
    'tests/test_telegram_webapp_init_data.py::test_verify_rejects_empty[]': {
        "title": 'Отклонение пустой строки',
        "description": 'verify отклоняет пустую строку initData.',
    },
    'tests/test_telegram_webapp_init_data.py::test_verify_rejects_stale_auth_date': {
        "title": 'Отклонение устаревшего auth_date',
        "description": 'verify отклоняет initData с auth_date старше допустимого TTL.',
    },
    'tests/test_temporary_whitelist_store.py::TemporaryWhitelistStoreTests::test_add_and_is_allowed': {
        "title": 'Временный whitelist: добавление и проверка',
        "description": 'add добавляет IP; is_allowed true до истечения TTL и false после.',
    },
    'tests/test_temporary_whitelist_store.py::TemporaryWhitelistStoreTests::test_duration_labels': {
        "title": 'Временный whitelist: метки длительности',
        "description": 'duration_seconds_from_label переводит 1h→3600, 12h→43200; неизвестные → None.',
    },
    'tests/test_temporary_whitelist_store.py::TemporaryWhitelistStoreTests::test_extend_on_readd': {
        "title": 'Временный whitelist: продление при повторе',
        "description": 'Повторный add того же IP продлевает expires_at на новый срок.',
    },
    'tests/test_temporary_whitelist_store.py::TemporaryWhitelistStoreTests::test_normalize_rejects_cidr': {
        "title": 'Временный whitelist: отклонение CIDR',
        "description": 'normalize_host_ip отклоняет CIDR (/24) и принимает одиночный IPv4.',
    },
    'tests/test_temporary_whitelist_store.py::TemporaryWhitelistStoreTests::test_purge_expired': {
        "title": 'Временный whitelist: очистка просроченных',
        "description": 'purge_expired удаляет истёкшие записи и возвращает их список.',
    },
    'tests/test_temporary_whitelist_store.py::TemporaryWhitelistStoreTests::test_remove': {
        "title": 'Временный whitelist: удаление IP',
        "description": 'remove удаляет IP из whitelist; is_allowed false после удаления.',
    },
    'tests/test_tg_mini_session.py::TelegramMiniSessionTests::test_enforce_telegram_mini_session_api_denied': {
        "title": 'Mini App: запрет API без сессии',
        "description": 'enforce_telegram_mini_session возвращает 403 для API без mini app сессии.',
    },
    'tests/test_tg_mini_session.py::TelegramMiniSessionTests::test_has_telegram_mini_session_requires_matching_username': {
        "title": 'Mini App: сессия привязана к username',
        "description": 'has_telegram_mini_session true только при совпадении username в сессии и запросе.',
    },
    'tests/test_wg_access_policy_service.py::WgAccessPolicyServiceTests::test_clear_block_rejects_expired_access': {
        "title": 'WG policy: unblock expired',
        "description": 'clear_block для просроченного expires_at бросает ExpiredRequiresExtendError с нужным error_code.',
    },
    'tests/test_wg_access_policy_service.py::WgAccessPolicyServiceTests::test_extend_after_expiry_unblocks_client': {
        "title": 'WG policy: extend после expiry',
        "description": 'set_expiry_days(..., extend=True) снимает блокировку; reconcile → is_blocked false, block_mode none.',
    },
    'tests/test_wg_awg_runtime_enforcer.py::WgAwgRuntimeEnforcerTests::test_block_client_runtime_removes_all_client_peers': {
        "title": 'WG runtime: block peers',
        "description": 'block_client_runtime удаляет peer на antizapret и vpn (removed_count=2).',
    },
    'tests/test_wg_awg_runtime_enforcer.py::WgAwgRuntimeEnforcerTests::test_unblock_client_runtime_restores_only_client_peers': {
        "title": 'WG runtime: restore peers',
        "description": 'unblock восстанавливает peer с allowed-ips и preshared-key; без wg-quick strip.',
    },
    'tests/test_wg_awg_runtime_enforcer.py::WgAwgRuntimeEnforcerTests::test_unblock_client_runtime_skips_syncconf_when_strip_fails': {
        "title": 'WG runtime: strip fail',
        "description": 'При падении wg-quick strip — synced_count=0, error_count=2, wg syncconf не вызывается.',
    },
    'tests/test_wg_runtime_subprocess.py::WgRuntimeSubprocessTests::test_apply_wg_client_runtime_block_action': {
        "title": 'WG subprocess: block',
        "description": 'При is_blocked=true последний аргумент команды wg_awg_policy_sync — block.',
    },
    'tests/test_wg_runtime_subprocess.py::WgRuntimeSubprocessTests::test_apply_wg_client_runtime_raises_on_fatal_exit': {
        "title": 'WG subprocess: fatal exit',
        "description": 'returncode=2 subprocess → RuntimeError.',
    },
    'tests/test_wg_runtime_subprocess.py::WgRuntimeSubprocessTests::test_apply_wg_client_runtime_returns_payload_with_runtime_errors': {
        "title": 'WG subprocess: частичные ошибки',
        "description": 'returncode=1 не бросает исключение; возвращает error_count из JSON.',
    },
    'tests/test_wg_runtime_subprocess.py::WgRuntimeSubprocessTests::test_apply_wg_client_runtime_unblock_parses_json': {
        "title": 'WG subprocess: unblock JSON',
        "description": 'apply_wg_client_runtime парсит stdout JSON и передаёт action unblock в CLI.',
    },
    'tests/test_wg_runtime_subprocess.py::WgRuntimeSubprocessTests::test_trigger_wg_policy_sync_background_starts_process': {
        "title": 'WG subprocess: фоновый sync',
        "description": 'trigger_wg_policy_sync_background запускает wg_awg_policy_sync.py через Popen.',
    },
}
