from .antizapret import register_settings_antizapret_routes
from .api import register_settings_api_routes
from .routes import register_settings_page_routes


def register_settings_routes(app, **deps):
    register_settings_page_routes(
        app,
        auth_manager=deps["auth_manager"],
        db=deps["db"],
        user_model=deps["user_model"],
        active_web_session_model=deps["active_web_session_model"],
        qr_download_audit_log_model=deps["qr_download_audit_log_model"],
        telegram_mini_audit_log_model=deps["telegram_mini_audit_log_model"],
        user_action_log_model=deps["user_action_log_model"],
        ip_restriction=deps["ip_restriction"],
        collect_all_openvpn_files_for_access=deps["collect_all_openvpn_files_for_access"],
        build_openvpn_access_groups=deps["build_openvpn_access_groups"],
        config_file_handler=deps["config_file_handler"],
        group_folders=deps["group_folders"],
        build_conf_access_groups=deps["build_conf_access_groups"],
        enqueue_background_task=deps["enqueue_background_task"],
        task_restart_service=deps["task_restart_service"],
        set_env_value=deps["set_env_value"],
        get_env_value=deps["get_env_value"],
        to_bool=deps["to_bool"],
        is_valid_cron_expression=deps["is_valid_cron_expression"],
        ensure_nightly_idle_restart_cron=deps["ensure_nightly_idle_restart_cron"],
        get_nightly_idle_restart_settings=deps["get_nightly_idle_restart_settings"],
        set_nightly_idle_restart_settings=deps["set_nightly_idle_restart_settings"],
        get_active_web_session_settings=deps["get_active_web_session_settings"],
        set_active_web_session_settings=deps["set_active_web_session_settings"],
        get_public_download_enabled=deps["get_public_download_enabled"],
        log_user_action_event=deps["log_user_action_event"],
    )
    register_settings_api_routes(
        app,
        auth_manager=deps["auth_manager"],
        db=deps["db"],
        user_model=deps["user_model"],
        ip_manager=deps["ip_manager"],
        enqueue_background_task=deps["enqueue_background_task"],
        task_restart_service=deps["task_restart_service"],
        set_env_value=deps["set_env_value"],
        get_env_value=deps["get_env_value"],
        to_bool=deps["to_bool"],
        is_valid_cron_expression=deps["is_valid_cron_expression"],
        ensure_nightly_idle_restart_cron=deps["ensure_nightly_idle_restart_cron"],
        get_nightly_idle_restart_settings=deps["get_nightly_idle_restart_settings"],
        set_nightly_idle_restart_settings=deps["set_nightly_idle_restart_settings"],
        get_active_web_session_settings=deps["get_active_web_session_settings"],
        set_active_web_session_settings=deps["set_active_web_session_settings"],
        log_telegram_audit_event=deps["log_telegram_audit_event"],
        log_user_action_event=deps["log_user_action_event"],
        cidr_db_updater_service=deps["cidr_db_updater_service"],
    )
    register_settings_antizapret_routes(app, auth_manager=deps["auth_manager"])


__all__ = ["register_settings_routes"]
