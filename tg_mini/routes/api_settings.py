from flask import jsonify, request, session

from tg_mini.services.settings import build_tg_mini_settings_payload, update_tg_mini_settings
from tg_mini.session import has_telegram_mini_session


def register_tg_mini_settings_api_routes(
    app,
    *,
    auth_manager,
    enqueue_background_task,
    task_restart_service,
    set_env_value,
    get_env_value,
    is_valid_cron_expression,
    ensure_nightly_idle_restart_cron,
    get_nightly_idle_restart_settings,
    set_nightly_idle_restart_settings,
    get_active_web_session_settings,
    set_active_web_session_settings,
    log_telegram_audit_event,
    log_user_action_event,
):
    def _has_telegram_mini_session() -> bool:
        return has_telegram_mini_session(session)

    def _build_tg_mini_settings_payload():
        return build_tg_mini_settings_payload(
            get_env_value=get_env_value,
            get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
            get_active_web_session_settings=get_active_web_session_settings,
        )

    @app.route("/api/tg-mini/settings", methods=["GET"], endpoint="api_tg_mini_settings_get")
    @auth_manager.admin_required
    def api_tg_mini_settings_get():
        if not _has_telegram_mini_session():
            return jsonify({"success": False, "message": "Доступ разрешён только из Telegram Mini App."}), 403
        return jsonify({"success": True, "settings": _build_tg_mini_settings_payload()})

    @app.route("/api/tg-mini/settings", methods=["POST"], endpoint="api_tg_mini_settings_update")
    @auth_manager.admin_required
    def api_tg_mini_settings_update():
        if not _has_telegram_mini_session():
            return jsonify({"success": False, "message": "Доступ разрешён только из Telegram Mini App."}), 403

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        try:
            body, status = update_tg_mini_settings(
                data=data,
                set_env_value=set_env_value,
                get_env_value=get_env_value,
                get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
                get_active_web_session_settings=get_active_web_session_settings,
                set_nightly_idle_restart_settings=set_nightly_idle_restart_settings,
                set_active_web_session_settings=set_active_web_session_settings,
                is_valid_cron_expression=is_valid_cron_expression,
                ensure_nightly_idle_restart_cron=ensure_nightly_idle_restart_cron,
                enqueue_background_task=enqueue_background_task,
                task_restart_service=task_restart_service,
                session_username=session.get("username"),
                log_telegram_audit_event=log_telegram_audit_event,
                log_user_action_event=log_user_action_event,
            )
            return jsonify(body), status
        except Exception as e:
            app.logger.error("Ошибка API tg-mini settings: %s", e)
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
