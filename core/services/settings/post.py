from core.services.settings.post_handlers.maintenance import (
    handle_maintenance_settings,
    handle_restart_service,
)
from core.services.settings.post_handlers.qr import handle_qr_settings
from core.services.settings.post_handlers.security import handle_security_settings
from core.services.settings.post_handlers.telegram_auth import handle_telegram_auth_settings
from core.services.settings.post_handlers.users import handle_users_settings
from core.services.settings.post_handlers.vpn_network import handle_vpn_network_port


def process_settings_post(form, *, session, flash, redirect_url, **deps):
    early_redirect = handle_users_settings(
        form,
        flash=flash,
        session=session,
        db=deps["db"],
        user_model=deps["user_model"],
        log_user_action_event=deps["log_user_action_event"],
        redirect_url=redirect_url,
    )
    if early_redirect:
        return early_redirect

    handle_vpn_network_port(
        form,
        flash=flash,
        get_env_value=deps["get_env_value"],
        set_env_value=deps["set_env_value"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_qr_settings(
        form,
        flash=flash,
        get_env_value=deps["get_env_value"],
        set_env_value=deps["set_env_value"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_maintenance_settings(
        form,
        flash=flash,
        to_bool=deps["to_bool"],
        is_valid_cron_expression=deps["is_valid_cron_expression"],
        ensure_nightly_idle_restart_cron=deps["ensure_nightly_idle_restart_cron"],
        get_active_web_session_settings=deps["get_active_web_session_settings"],
        set_nightly_idle_restart_settings=deps["set_nightly_idle_restart_settings"],
        set_active_web_session_settings=deps["set_active_web_session_settings"],
        set_env_value=deps["set_env_value"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_telegram_auth_settings(
        form,
        flash=flash,
        get_env_value=deps["get_env_value"],
        set_env_value=deps["set_env_value"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_security_settings(
        form,
        flash=flash,
        ip_restriction=deps["ip_restriction"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_restart_service(
        form,
        flash=flash,
        session=session,
        enqueue_background_task=deps["enqueue_background_task"],
        task_restart_service=deps["task_restart_service"],
        log_user_action_event=deps["log_user_action_event"],
    )

    return redirect_url
