from core.services.settings.post_handlers.feature_toggles import handle_feature_toggles_settings
from core.services.settings.post_handlers.maintenance import (
    handle_backup_create,
    handle_backup_delete,
    handle_backup_restore,
    handle_backup_settings,
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
        get_env_value=deps["get_env_value"],
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
        get_env_value=deps["get_env_value"],
    )
    handle_backup_settings(
        form,
        flash=flash,
        to_bool=deps["to_bool"],
        set_backup_settings=deps["set_backup_settings"],
        set_env_value=deps["set_env_value"],
        ensure_app_backup_cron=deps["ensure_app_backup_cron"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_backup_create(
        form,
        flash=flash,
        session=session,
        enqueue_background_task=deps["enqueue_background_task"],
        backup_manager_service=deps["backup_manager_service"],
        get_backup_settings=deps["get_backup_settings"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_backup_restore(
        form,
        flash=flash,
        session=session,
        enqueue_background_task=deps["enqueue_background_task"],
        backup_manager_service=deps["backup_manager_service"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_backup_delete(
        form,
        flash=flash,
        backup_manager_service=deps["backup_manager_service"],
        log_user_action_event=deps["log_user_action_event"],
    )
    handle_telegram_auth_settings(
        form,
        flash=flash,
        get_env_value=deps["get_env_value"],
        set_env_value=deps["set_env_value"],
        log_user_action_event=deps["log_user_action_event"],
        log_telegram_audit_event=deps["log_telegram_audit_event"],
    )
    handle_security_settings(
        form,
        flash=flash,
        ip_restriction=deps["ip_restriction"],
        log_user_action_event=deps["log_user_action_event"],
        get_env_value=deps["get_env_value"],
    )
    feature_toggles_redirect = handle_feature_toggles_settings(
        form,
        flash=flash,
        to_bool=deps["to_bool"],
        set_env_value=deps["set_env_value"],
        runtime_set=deps["runtime_set"],
        maintenance_scheduler_service=deps["maintenance_scheduler_service"],
        ensure_traffic_sync_cron=deps["ensure_traffic_sync_cron"],
        ensure_wg_policy_sync_cron=deps["ensure_wg_policy_sync_cron"],
        ensure_runtime_backup_cleanup_cron=deps["ensure_runtime_backup_cleanup_cron"],
        ensure_app_backup_cron=deps["ensure_app_backup_cron"],
        get_backup_settings=deps.get("get_backup_settings"),
        log_user_action_event=deps["log_user_action_event"],
        redirect_url=redirect_url,
    )
    if feature_toggles_redirect:
        return feature_toggles_redirect
    handle_restart_service(
        form,
        flash=flash,
        session=session,
        enqueue_background_task=deps["enqueue_background_task"],
        task_restart_service=deps["task_restart_service"],
        log_user_action_event=deps["log_user_action_event"],
        get_env_value=deps["get_env_value"],
    )

    return redirect_url
