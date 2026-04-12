from routes.admin_routes import register_admin_routes
from routes.auth_routes import register_auth_routes
from routes.config_routes import register_config_routes
from routes.index_routes import register_index_routes
from routes.monitoring_routes import register_monitoring_routes
from routes.settings_routes import register_settings_routes


def register_all_routes(app, sock, deps):
    g = deps.__getitem__

    register_auth_routes(
        app,
        auth_manager=g("auth_manager"),
        captcha_generator=g("captcha_generator"),
        ip_restriction=g("ip_restriction"),
        db=g("db"),
        user_model=g("User"),
        touch_active_web_session=g("_touch_active_web_session"),
        remove_active_web_session=g("_remove_active_web_session"),
        log_telegram_audit_event=g("_log_telegram_audit_event"),
    )

    register_config_routes(
        app,
        auth_manager=g("auth_manager"),
        file_validator=g("file_validator"),
        db=g("db"),
        user_model=g("User"),
        viewer_config_access_model=g("ViewerConfigAccess"),
        qr_download_token_model=g("QrDownloadToken"),
        client_name_pattern=g("CLIENT_NAME_PATTERN"),
        group_folders=g("GROUP_FOLDERS"),
        result_dir_files=g("RESULT_DIR_FILES"),
        ensure_client_connect_ban_check_block=g("_ensure_client_connect_ban_check_block"),
        read_banned_clients=g("_read_banned_clients"),
        write_banned_clients=g("_write_banned_clients"),
        get_config_type=g("_get_config_type"),
        resolve_config_file=g("_resolve_config_file"),
        create_one_time_download_url=g("_create_one_time_download_url"),
        log_qr_event=g("_log_qr_event"),
        qr_generator=g("qr_generator"),
        file_editor=g("file_editor"),
        enqueue_background_task=g("_enqueue_background_task"),
        task_run_doall=g("_task_run_doall"),
        task_accepted_response=g("_task_accepted_response"),
        set_env_value=g("_set_env_value"),
        get_public_download_enabled=g("_get_public_download_enabled"),
        set_public_download_enabled=g("_set_public_download_enabled"),
        log_telegram_audit_event=g("_log_telegram_audit_event"),
    )

    register_admin_routes(
        app,
        auth_manager=g("auth_manager"),
        db=g("db"),
        app_root=g("APP_ROOT"),
        background_task_model=g("BackgroundTask"),
        user_model=g("User"),
        viewer_config_access_model=g("ViewerConfigAccess"),
        collect_all_configs_for_access=g("collect_all_configs_for_access"),
        normalize_openvpn_group_key=g("normalize_openvpn_group_key"),
        normalize_conf_group_key=g("normalize_conf_group_key"),
        serialize_background_task=g("_serialize_background_task"),
        run_checked_command=g("_run_checked_command"),
        enqueue_background_task=g("_enqueue_background_task"),
        task_update_system=g("_task_update_system"),
        task_restart_service=g("_task_restart_service"),
        task_accepted_response=g("_task_accepted_response"),
    )

    register_settings_routes(
        app,
        auth_manager=g("auth_manager"),
        db=g("db"),
        user_model=g("User"),
        active_web_session_model=g("ActiveWebSession"),
        qr_download_audit_log_model=g("QrDownloadAuditLog"),
        telegram_mini_audit_log_model=g("TelegramMiniAuditLog"),
        ip_restriction=g("ip_restriction"),
        ip_manager=g("ip_manager"),
        collect_all_openvpn_files_for_access=g("collect_all_openvpn_files_for_access"),
        build_openvpn_access_groups=g("build_openvpn_access_groups"),
        config_file_handler=g("config_file_handler"),
        group_folders=g("GROUP_FOLDERS"),
        build_conf_access_groups=g("build_conf_access_groups"),
        enqueue_background_task=g("_enqueue_background_task"),
        task_restart_service=g("_task_restart_service"),
        set_env_value=g("_set_env_value"),
        get_env_value=g("_get_env_value"),
        to_bool=g("_to_bool"),
        is_valid_cron_expression=g("_is_valid_cron_expression"),
        ensure_nightly_idle_restart_cron=g("_ensure_nightly_idle_restart_cron"),
        get_nightly_idle_restart_settings=g("_get_nightly_idle_restart_settings"),
        set_nightly_idle_restart_settings=g("_set_nightly_idle_restart_settings"),
        get_active_web_session_settings=g("_get_active_web_session_settings"),
        set_active_web_session_settings=g("_set_active_web_session_settings"),
        get_public_download_enabled=g("_get_public_download_enabled"),
        log_telegram_audit_event=g("_log_telegram_audit_event"),
    )

    register_index_routes(
        app,
        auth_manager=g("auth_manager"),
        db=g("db"),
        user_model=g("User"),
        config_file_handler=g("config_file_handler"),
        file_validator=g("file_validator"),
        group_folders=g("GROUP_FOLDERS"),
        read_banned_clients=g("_read_banned_clients"),
        extract_client_name_from_config_file=g("_extract_client_name_from_config_file"),
        get_logs_dashboard_data_cached=g("_get_logs_dashboard_data_cached"),
        human_bytes=g("_human_bytes"),
        script_executor=g("script_executor"),
        sync_wireguard_peer_cache_from_configs=g("_sync_wireguard_peer_cache_from_configs"),
        log_telegram_audit_event=g("_log_telegram_audit_event"),
    )

    register_monitoring_routes(
        app,
        sock,
        auth_manager=g("auth_manager"),
        server_monitor_proc=g("server_monitor_proc"),
        collect_bw_interface_groups=g("_collect_bw_interface_groups"),
        get_logs_dashboard_data_cached=g("_get_logs_dashboard_data_cached"),
        cleanup_status_logs_now=g("_cleanup_status_logs_now"),
        set_status_cleanup_schedule=g("_set_status_cleanup_schedule"),
        normalize_traffic_protocol_scope=g("_normalize_traffic_protocol_scope"),
        reset_persisted_traffic_data=g("_reset_persisted_traffic_data"),
        collect_existing_config_client_names=g("_collect_existing_config_client_names"),
        delete_client_traffic_stats=g("_delete_client_traffic_stats"),
        openvpn_log_tail_lines=g("OPENVPN_LOG_TAIL_LINES"),
        collect_config_protocols_by_client=g("_collect_config_protocols_by_client"),
        user_traffic_sample_model=g("UserTrafficSample"),
        human_bytes=g("_human_bytes"),
    )
