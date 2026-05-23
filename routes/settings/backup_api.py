from flask import jsonify, request, session

from core.services.settings.post_handlers.maintenance import (
    handle_backup_create,
    handle_backup_delete,
    handle_backup_restore,
    handle_backup_settings,
)


class _FlashCollector:
    def __init__(self):
        self.messages = []

    def __call__(self, message, category="info"):
        self.messages.append({"message": str(message), "category": str(category)})


def _human_size(size_bytes):
    size = float(max(0, int(size_bytes or 0)))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def _api_result(collector, *, extra=None):
    payload = {"success": True, "messages": collector.messages}
    if collector.messages:
        last = collector.messages[-1]
        payload["message"] = last["message"]
        payload["category"] = last["category"]
        if last["category"] == "error":
            payload["success"] = False
    else:
        payload["message"] = ""
        payload["category"] = "info"
    if extra:
        payload.update(extra)
    return jsonify(payload), (200 if payload["success"] else 400)


def register_backup_api_routes(
    app,
    *,
    auth_manager,
    backup_manager_service,
    enqueue_background_task,
    get_backup_settings,
    set_backup_settings,
    set_env_value,
    to_bool,
    ensure_app_backup_cron,
    log_user_action_event,
):
    @app.route("/api/backups", methods=["GET"])
    @auth_manager.admin_required
    def api_backups_list():
        try:
            backups = backup_manager_service.list_backups()
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500
        for entry in backups:
            entry["size_human"] = _human_size(entry.get("size_bytes", 0))
        return jsonify({"success": True, "backups": backups})

    @app.route("/api/backups/settings", methods=["POST"])
    @auth_manager.admin_required
    def api_backups_settings():
        collector = _FlashCollector()
        form = request.form.copy()
        form["backup_settings_action"] = "save"
        handle_backup_settings(
            form,
            flash=collector,
            to_bool=to_bool,
            set_backup_settings=set_backup_settings,
            set_env_value=set_env_value,
            ensure_app_backup_cron=ensure_app_backup_cron,
            log_user_action_event=log_user_action_event,
        )
        return _api_result(collector)

    @app.route("/api/backups/create", methods=["POST"])
    @auth_manager.admin_required
    def api_backups_create():
        collector = _FlashCollector()
        form = {"backup_create_action": "create"}
        handle_backup_create(
            form,
            flash=collector,
            session=session,
            enqueue_background_task=enqueue_background_task,
            backup_manager_service=backup_manager_service,
            get_backup_settings=get_backup_settings,
            log_user_action_event=log_user_action_event,
        )
        return _api_result(collector)

    @app.route("/api/backups/restore", methods=["POST"])
    @auth_manager.admin_required
    def api_backups_restore():
        payload = request.get_json(silent=True) or {}
        file_name = (payload.get("file_name") or request.form.get("backup_file_name") or "").strip()
        collector = _FlashCollector()
        handle_backup_restore(
            {
                "backup_restore_action": "restore",
                "backup_file_name": file_name,
            },
            flash=collector,
            session=session,
            enqueue_background_task=enqueue_background_task,
            backup_manager_service=backup_manager_service,
            log_user_action_event=log_user_action_event,
        )
        return _api_result(collector, extra={"file_name": file_name})

    @app.route("/api/backups/delete", methods=["POST"])
    @auth_manager.admin_required
    def api_backups_delete():
        payload = request.get_json(silent=True) or {}
        file_name = (payload.get("file_name") or request.form.get("backup_file_name") or "").strip()
        collector = _FlashCollector()
        handle_backup_delete(
            {
                "backup_delete_action": "delete",
                "backup_file_name": file_name,
            },
            flash=collector,
            backup_manager_service=backup_manager_service,
            log_user_action_event=log_user_action_event,
        )
        extra = None
        if collector.messages and collector.messages[-1]["category"] == "success":
            try:
                backups = backup_manager_service.list_backups()
                for entry in backups:
                    entry["size_human"] = _human_size(entry.get("size_bytes", 0))
                extra = {"backups": backups}
            except Exception:
                pass
        return _api_result(collector, extra=extra)
