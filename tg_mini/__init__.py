from tg_mini.blueprint import bp
from tg_mini.routes.api_config import register_tg_mini_config_api_routes
from tg_mini.routes.api_dashboard import register_tg_mini_dashboard_api_routes
from tg_mini.routes.api_settings import register_tg_mini_settings_api_routes
from tg_mini.routes.pages import register_tg_mini_page_routes


def register_tg_mini_routes(app, sock=None, **deps):
    app.register_blueprint(bp)

    register_tg_mini_page_routes(app, auth_manager=deps["auth_manager"])
    register_tg_mini_dashboard_api_routes(
        app,
        auth_manager=deps["auth_manager"],
        get_logs_dashboard_data_cached=deps["get_logs_dashboard_data_cached"],
        user_traffic_sample_model=deps["user_traffic_sample_model"],
        human_bytes=deps["human_bytes"],
    )
    register_tg_mini_config_api_routes(
        app,
        auth_manager=deps["auth_manager"],
        user_model=deps["user_model"],
        viewer_config_access_model=deps["viewer_config_access_model"],
        resolve_config_file=deps["resolve_config_file"],
        get_config_type=deps["get_config_type"],
        io_executor=deps.get("io_executor"),
        log_telegram_audit_event=deps["log_telegram_audit_event"],
        log_user_action_event=deps["log_user_action_event"],
    )
    register_tg_mini_settings_api_routes(
        app,
        auth_manager=deps["auth_manager"],
        enqueue_background_task=deps["enqueue_background_task"],
        task_restart_service=deps["task_restart_service"],
        set_env_value=deps["set_env_value"],
        get_env_value=deps["get_env_value"],
        is_valid_cron_expression=deps["is_valid_cron_expression"],
        ensure_nightly_idle_restart_cron=deps["ensure_nightly_idle_restart_cron"],
        get_nightly_idle_restart_settings=deps["get_nightly_idle_restart_settings"],
        set_nightly_idle_restart_settings=deps["set_nightly_idle_restart_settings"],
        get_active_web_session_settings=deps["get_active_web_session_settings"],
        set_active_web_session_settings=deps["set_active_web_session_settings"],
        log_telegram_audit_event=deps["log_telegram_audit_event"],
        log_user_action_event=deps["log_user_action_event"],
    )


__all__ = ["register_tg_mini_routes", "bp"]
