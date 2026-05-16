from flask import flash, redirect, render_template, request, session, url_for

from core.services.settings.page_context import build_settings_page_context
from core.services.settings.post import process_settings_post


def register_settings_page_routes(
    app,
    *,
    auth_manager,
    db,
    user_model,
    active_web_session_model,
    qr_download_audit_log_model,
    telegram_mini_audit_log_model,
    user_action_log_model,
    ip_restriction,
    collect_all_openvpn_files_for_access,
    build_openvpn_access_groups,
    config_file_handler,
    group_folders,
    build_conf_access_groups,
    enqueue_background_task,
    task_restart_service,
    set_env_value,
    get_env_value,
    to_bool,
    is_valid_cron_expression,
    ensure_nightly_idle_restart_cron,
    get_nightly_idle_restart_settings,
    set_nightly_idle_restart_settings,
    get_active_web_session_settings,
    set_active_web_session_settings,
    get_public_download_enabled,
    log_user_action_event,
):
    @app.route("/settings", methods=["GET", "POST"])
    @auth_manager.admin_required
    def settings():
        if request.method == "POST":
            redirect_target = process_settings_post(
                request.form,
                session=session,
                flash=flash,
                redirect_url=url_for("settings"),
                db=db,
                user_model=user_model,
                ip_restriction=ip_restriction,
                get_env_value=get_env_value,
                set_env_value=set_env_value,
                to_bool=to_bool,
                is_valid_cron_expression=is_valid_cron_expression,
                ensure_nightly_idle_restart_cron=ensure_nightly_idle_restart_cron,
                get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
                set_nightly_idle_restart_settings=set_nightly_idle_restart_settings,
                get_active_web_session_settings=get_active_web_session_settings,
                set_active_web_session_settings=set_active_web_session_settings,
                enqueue_background_task=enqueue_background_task,
                task_restart_service=task_restart_service,
                log_user_action_event=log_user_action_event,
            )
            return redirect(redirect_target)

        return render_template(
            "settings.html",
            **build_settings_page_context(
                user_model=user_model,
                active_web_session_model=active_web_session_model,
                qr_download_audit_log_model=qr_download_audit_log_model,
                telegram_mini_audit_log_model=telegram_mini_audit_log_model,
                user_action_log_model=user_action_log_model,
                ip_restriction=ip_restriction,
                config_file_handler=config_file_handler,
                group_folders=group_folders,
                get_env_value=get_env_value,
                get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
                get_active_web_session_settings=get_active_web_session_settings,
                get_public_download_enabled=get_public_download_enabled,
                collect_all_openvpn_files_for_access=collect_all_openvpn_files_for_access,
                build_openvpn_access_groups=build_openvpn_access_groups,
                build_conf_access_groups=build_conf_access_groups,
                request_url_root=getattr(request, "url_root", None),
            ),
        )
