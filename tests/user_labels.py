"""Человекочитаемые названия тестов для вкладки «Тесты» в настройках."""

from __future__ import annotations

MODULE_LABELS: dict[str, str] = {
    "tests/test_admin_routes.py": "Администрирование",
    "tests/test_auth_routes_login.py": "Авторизация",
    "tests/test_background_tasks_service.py": "Фоновые задачи",
    "tests/test_cidr_db_updater_service.py": "CIDR в базе данных",
    "tests/test_cidr_list_updater.py": "CIDR-списки и маршруты",
    "tests/test_db_migration_service.py": "Миграции БД",
    "tests/test_edit_files_page_context.py": "Редактор файлов",
    "tests/test_http_security.py": "HTTP и безопасность",
    "tests/test_index_page_context.py": "Главная страница",
    "tests/test_ip_restriction_scanner_block.py": "Ограничение IP",
    "tests/test_panel_publish_info.py": "Публикация панели",
    "tests/test_routing_page_context.py": "Маршрутизация",
    "tests/test_scanner_firewall_store.py": "Блокировка сканеров",
    "tests/test_session_security.py": "Безопасность сессий",
    "tests/test_site_diagnostics.py": "Диагностика запуска сайта",
    "tests/test_system_preflight.py": "Проверка окружения (preflight)",
    "tests/test_settings_page_context.py": "Страница настроек",
    "tests/test_settings_post_handlers.py": "Сохранение настроек",
    "tests/test_telegram_webapp_init_data.py": "Telegram WebApp",
    "tests/test_tg_mini_session.py": "Telegram Mini App",
}

# nodeid pytest → краткое описание (без префикса модуля)
TEST_TITLES: dict[str, str] = {
    "tests/test_admin_routes.py::AdminRoutesTests::test_api_task_status_returns_404_for_unknown_task": "Статус фоновой задачи: 404 для неизвестного ID",
    "tests/test_admin_routes.py::AdminRoutesTests::test_api_task_status_returns_payload_for_existing_task": "Статус фоновой задачи: данные для существующей задачи",
    "tests/test_admin_routes.py::AdminRoutesTests::test_update_system_returns_accepted_task_response": "Обновление системы: ответ «задача принята»",
    "tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_grant_allows_same_name_for_different_protocol": "Доступ viewer: одно имя для разных протоколов",
    "tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_non_json_request_returns_consistent_json_error": "Доступ viewer: ошибка при не-JSON запросе",
    "tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_revoke_removes_only_requested_protocol": "Доступ viewer: отзыв только выбранного протокола",
    "tests/test_admin_routes.py::AdminRoutesTests::test_viewer_access_validates_missing_json_payload": "Доступ viewer: проверка пустого JSON",
    "tests/test_auth_routes_login.py::AuthRoutesLoginTests::test_login_failure_increments_attempts": "Неудачный вход увеличивает счётчик попыток",
    "tests/test_auth_routes_login.py::AuthRoutesLoginTests::test_login_success_without_remember_me": "Успешный вход без «Запомнить меня»",
    "tests/test_auth_routes_login.py::AuthRoutesLoginTests::test_login_success_with_remember_me_uses_config_days": "Успешный вход с «Запомнить меня» и сроком из конфига",
    "tests/test_background_tasks_service.py::BackgroundTaskServiceTests::test_enqueue_background_task_creates_record_and_submits_executor": "Постановка задачи в очередь и запуск исполнителя",
    "tests/test_background_tasks_service.py::BackgroundTaskServiceTests::test_run_background_task_marks_completed_and_trims_output": "Завершение задачи и обрезка вывода",
    "tests/test_background_tasks_service.py::BackgroundTaskServiceTests::test_run_checked_command_raises_runtime_error_on_nonzero_exit": "Ошибка при ненулевом коде команды",
    "tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_compute_provider_anomaly_marks_critical_on_large_drop": "Аномалия провайдера: критично при большом падении",
    "tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_discover_provider_asns_combines_seed_source_and_scan": "Поиск ASN: объединение seed и сканирования",
    "tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_discover_provider_asns_skips_scan_when_limit_zero": "Поиск ASN: без скана при лимите 0",
    "tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_download_asn_cidrs_with_meta_uses_bgp_state_fallback": "Загрузка CIDR ASN: fallback из BGP state",
    "tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_helper_parsing_and_workers": "Разбор вспомогательных данных и воркеры",
    "tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_merge_cidr_items_prefers_richer_geo_metadata": "Слияние CIDR: приоритет расширенной geo-метаданной",
    "tests/test_cidr_db_updater_service.py::CidrDbUpdaterServiceHelperTests::test_should_preserve_previous_pool_on_hard_drop_without_errors": "Сохранение пула при резком падении без ошибок",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_analyze_dpi_log_builds_priority_files": "Разбор DPI-лога: приоритетные файлы",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_analyze_dpi_log_supports_dpi_detector_table_format": "Разбор DPI-лога: табличный формат детектора",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_apply_total_route_limit_keeps_mandatory_detected_file": "Лимит маршрутов: обязательный detected-файл",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_apply_total_route_limit_with_budget_smaller_than_file_count": "Лимит маршрутов: бюджет меньше числа файлов",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_apply_total_route_limit_with_dpi_priority_reserve": "Лимит маршрутов: резерв под DPI-приоритет",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_collect_cidrs_skips_geo_source_when_all_scope_has_non_geo_results": "Сбор CIDR: пропуск geo при non-geo в all",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_compress_cidrs_to_limit_does_not_overcompress_far_below_budget": "Сжатие CIDR: без пересжатия далеко ниже бюджета",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_compress_cidrs_to_limit_never_returns_default_route": "Сжатие CIDR: без default route",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_estimate_applies_route_optimization_for_large_geo_result": "Оценка: оптимизация маршрутов для большого geo",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_estimate_cidr_matches": "Оценка совпадений CIDR",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_estimate_excludes_ru_cidrs_for_all_scope": "Оценка: исключение RU CIDR для all",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_bgp_tools_raw_allocations_section": "Извлечение CIDR из BGP.tools (allocations)",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_google_json_strict_mode_excludes_ambiguous_scope": "Извлечение CIDR из Google JSON (strict)",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_ripe_geo_json": "Извлечение CIDR из RIPE geo JSON",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_ripe_geo_json_strict_mode_excludes_ambiguous": "Извлечение CIDR из RIPE geo JSON (strict)",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_extract_cidrs_from_ripe_json": "Извлечение CIDR из RIPE JSON",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_non_geo_provider_can_be_included_with_fallback": "Non-geo провайдер с fallback",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_prune_runtime_backups_removes_directories_older_than_12_hours": "Очистка runtime-бэкапов старше 12 часов",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_sync_game_hosts_filter_runs_without_cidr_update": "Синхронизация game hosts без обновления CIDR",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_sync_games_include_hosts_enable_and_disable": "Включение и отключение games include hosts",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_total_limit_reads_from_env_file_runtime": "Общий лимит читается из env/runtime",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_update_applies_global_total_route_limit": "Обновление применяет глобальный лимит маршрутов",
    "tests/test_cidr_list_updater.py::CidrListUpdaterTests::test_update_selected_and_rollback_to_baseline": "Обновление выбранных и откат к baseline",
    "tests/test_db_migration_service.py::DatabaseMigrationServiceTests::test_viewer_access_migration_recovers_from_stale_temp_table": "Миграция viewer_access: восстановление после temp-таблицы",
    "tests/test_db_migration_service.py::DatabaseMigrationServiceTests::test_viewer_access_migration_reenables_foreign_keys_after_error": "Миграция viewer_access: FK после ошибки",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_build_edit_files_get_context_first_item_active": "Контекст редактора: первый элемент активен",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_build_route_download_actions_without_public": "Ссылки скачивания маршрутов без public",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_build_route_download_actions_with_public": "Ссылки скачивания маршрутов с public",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_adblock": "Группа навигации: adblock",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_allow_ips": "Группа навигации: allow IPs",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_domains": "Группа навигации: domains",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_ip_routing": "Группа навигации: IP routing",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_resolve_file_nav_group_other": "Группа навигации: прочие файлы",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_validate_editor_content_null_byte": "Валидация: запрет null-byte в содержимом",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_validate_editor_content_too_large": "Валидация: слишком большой файл",
    "tests/test_edit_files_page_context.py::EditFilesPageContextTests::test_validate_editor_content_valid": "Валидация: корректное содержимое",
    "tests/test_http_security.py::test_apply_security_headers_sets_csp_and_noindex_for_login": "Заголовки безопасности: CSP и noindex на login",
    "tests/test_http_security.py::test_build_robots_txt_blocks_download_paths": "robots.txt блокирует пути скачивания",
    "tests/test_http_security.py::test_build_security_txt_has_no_vpn_wording": "security.txt без VPN-формулировок",
    "tests/test_http_security.py::test_get_panel_branding_uses_domain_only": "Брендинг панели: только домен",
    "tests/test_http_security.py::test_should_noindex_sensitive_paths": "noindex для чувствительных путей",
    "tests/test_index_page_context.py::IndexPageContextTests::test_build_client_table_rows_cert_state": "Таблица клиентов: статусы сертификатов",
    "tests/test_index_page_context.py::IndexPageContextTests::test_build_index_kpi_counts_expiring_and_expired": "KPI главной: истекающие и просроченные",
    "tests/test_index_page_context.py::IndexPageContextTests::test_collect_grouped_service_statuses_without_systemctl": "Статусы сервисов без systemctl",
    "tests/test_index_page_context.py::IndexPageContextTests::test_group_config_files_by_client_splits_antizapret_and_vpn": "Группировка конфигов VPN и antizapret",
    "tests/test_index_page_context.py::IndexPageContextTests::test_resolve_openvpn_group_and_files_filters_viewer_configs": "OpenVPN-группа и фильтр для viewer",
    "tests/test_ip_restriction_scanner_block.py::IPRestrictionScannerBlockTests::test_denied_ip_redirects_until_banned": "Отклонённый IP: редирект до бана",
    "tests/test_ip_restriction_scanner_block.py::IPRestrictionScannerBlockTests::test_ip_blocked_unavailable_when_restrictions_disabled": "Страница блокировки при выключенных ограничениях",
    "tests/test_ip_restriction_scanner_block.py::IPRestrictionScannerBlockTests::test_rate_limit_then_hard_deny": "Rate limit и жёсткий запрет",
    "tests/test_panel_publish_info.py::PanelPublishInfoTests::test_app_https_gunicorn": "Публикация: HTTPS через Gunicorn",
    "tests/test_panel_publish_info.py::PanelPublishInfoTests::test_direct_http": "Публикация: прямой HTTP",
    "tests/test_panel_publish_info.py::PanelPublishInfoTests::test_reverse_proxy_with_domain": "Публикация: reverse proxy с доменом",
    "tests/test_panel_publish_info.py::PanelPublishInfoTests::test_whitelist_firewall_applicable_without_nginx": "Whitelist firewall applicable without nginx",
    "tests/test_routing_page_context.py::RoutingPageContextTests::test_build_routing_page_context_keys": "Контекст страницы маршрутизации",
    "tests/test_routing_page_context.py::RoutingPageContextTests::test_clamp_openvpn_route_total_cidr_limit_boundaries": "Ограничение лимита CIDR-маршрутов OpenVPN",
    "tests/test_routing_page_context.py::RoutingPageContextTests::test_read_antizapret_settings_from_fixture": "Чтение настроек antizapret из фикстуры",
    "tests/test_routing_page_context.py::RoutingPageContextTests::test_resolve_openvpn_route_total_cidr_limit": "Разрешение общего лимита CIDR-маршрутов",
    "tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_clear_all_removes_entries": "Очистка всех записей блокировок",
    "tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_fifth_strike_is_year_ban": "Пятый strike — бан на год",
    "tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_persists_ban_and_strikes": "Сохранение бана и strikes",
    "tests/test_scanner_firewall_store.py::ScannerFirewallStoreTests::test_unban_sets_grace_without_active_ban": "Разбан: grace period без активного бана",
    "tests/test_session_security.py::SessionSecurityConfigTests::test_default_without_https_uses_insecure_cookie": "Без HTTPS: небезопасная cookie по умолчанию",
    "tests/test_session_security.py::SessionSecurityConfigTests::test_development_default_allows_insecure_cookie": "Development: разрешена небезопасная cookie",
    "tests/test_session_security.py::SessionSecurityConfigTests::test_remember_me_and_session_lifetime_are_clamped": "Remember me и lifetime в допустимых пределах",
    "tests/test_session_security.py::SessionSecurityConfigTests::test_samesite_none_falls_back_to_lax_without_secure": "SameSite=None → Lax без secure",
    "tests/test_session_security.py::SessionSecurityConfigTests::test_ssl_material_enables_secure_cookie": "SSL-материалы включают secure cookie",
    "tests/test_session_security.py::SessionSecurityConfigTests::test_use_https_enables_secure_cookie": "USE_HTTPS включает secure cookie",
    "tests/test_settings_page_context.py::SettingsPageContextTests::test_build_settings_page_context_keys": "Контекст страницы настроек",
    "tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_invalid_port_shows_error": "Некорректный порт — сообщение об ошибке",
    "tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_normalize_telegram_id_accepts_valid": "Нормализация Telegram ID: валидный",
    "tests/test_settings_post_handlers.py::SettingsPostHandlersTests::test_normalize_telegram_id_rejects_leading_zero": "Нормализация Telegram ID: ведущий ноль",
    "tests/test_telegram_webapp_init_data.py::test_verify_accepts_init_data_when_signature_in_signed_payload": "Проверка initData: подпись в signed payload",
    "tests/test_telegram_webapp_init_data.py::test_verify_accepts_valid_init_data": "Проверка валидного initData",
    "tests/test_telegram_webapp_init_data.py::test_verify_rejects_bad_hash": "Отклонение неверного hash",
    "tests/test_telegram_webapp_init_data.py::test_verify_rejects_empty[]": "Отклонение пустой строки",
    "tests/test_telegram_webapp_init_data.py::test_verify_rejects_empty[   ]": "Отклонение строки из пробелов",
    "tests/test_telegram_webapp_init_data.py::test_verify_rejects_stale_auth_date": "Отклонение устаревшего auth_date",
    "tests/test_tg_mini_session.py::TelegramMiniSessionTests::test_enforce_telegram_mini_session_api_denied": "Mini App: запрет API без сессии",
    "tests/test_tg_mini_session.py::TelegramMiniSessionTests::test_has_telegram_mini_session_requires_matching_username": "Mini App: сессия привязана к username",
    "tests/test_site_diagnostics.py::DecodeJournalLineTests::test_address_already_in_use": "Journal: порт занят (Address already in use)",
    "tests/test_site_diagnostics.py::DecodeJournalLineTests::test_import_error": "Journal: ImportError / ModuleNotFoundError",
    "tests/test_site_diagnostics.py::DecodeJournalLineTests::test_unknown_line_returns_none": "Journal: неизвестная строка без подсказки",
    "tests/test_site_diagnostics.py::DecodeJournalLineTests::test_status_203_exec": "Journal: status=203/EXEC (нет gunicorn)",
    "tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_missing_unit_reports_fail": "Диагностика: отсутствует systemd unit",
    "tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_active_service_and_files_ok": "Диагностика: сервис active и файлы на месте",
    "tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_https_missing_certificates": "Диагностика: HTTPS без сертификатов",
    "tests/test_site_diagnostics.py::RunSiteDiagnosticsTests::test_format_check_result_fields": "CheckResult: поля warn/detail/hint",
    "tests/test_system_preflight.py::SystemPreflightTests::test_missing_python_dependency_fails": "Preflight: ошибка при отсутствии pip-пакета",
    "tests/test_system_preflight.py::SystemPreflightTests::test_missing_script_module_fails": "Preflight: отсутствует модуль script_sh",
}


def _module_for_nodeid(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def _fallback_short_title(nodeid: str) -> str:
    func = nodeid.rsplit("::", 1)[-1]
    if func.startswith("test_"):
        func = func[5:]
    if "[" in func:
        func = func.split("[", 1)[0]
    return func.replace("_", " ").strip().capitalize()


def short_title_for_nodeid(nodeid: str) -> str:
    if nodeid in TEST_TITLES:
        return TEST_TITLES[nodeid]
    base = nodeid.split("[", 1)[0]
    if base in TEST_TITLES:
        return TEST_TITLES[base]
    return _fallback_short_title(nodeid)


def title_for_nodeid(nodeid: str) -> str:
    module = _module_for_nodeid(nodeid)
    group = MODULE_LABELS.get(module, module.replace("tests/test_", "").replace("_", " "))
    return f"{group}: {short_title_for_nodeid(nodeid)}"


def enrich_test_nodeids(nodeids: list[str]) -> list[dict[str, str]]:
    items = []
    for nodeid in nodeids:
        module = _module_for_nodeid(nodeid)
        items.append(
            {
                "id": nodeid,
                "title": short_title_for_nodeid(nodeid),
                "group": MODULE_LABELS.get(module, module),
            }
        )
    return items
