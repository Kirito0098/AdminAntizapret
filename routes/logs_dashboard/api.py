from flask import jsonify, request, session

from core.services.logs_dashboard import fetch_user_traffic_chart


def register_logs_dashboard_api_routes(
    app,
    *,
    auth_manager,
    db,
    background_task_model,
    collect_config_protocols_by_client,
    user_traffic_sample_model,
    human_bytes,
):
    def _error_response(message, status_code=400):
        return jsonify({"success": False, "error": message}), status_code

    @app.route("/api/user-traffic-chart")
    @auth_manager.login_required
    def api_user_traffic_chart():
        payload, status = fetch_user_traffic_chart(
            client=request.args.get("client"),
            range_key=request.args.get("range"),
            protocol_filter=request.args.get("protocol"),
            collect_config_protocols_by_client=collect_config_protocols_by_client,
            user_traffic_sample_model=user_traffic_sample_model,
            human_bytes=human_bytes,
        )
        return jsonify(payload), status

    @app.route("/api/logs_dashboard_refresh_status/<task_id>", methods=["GET"])
    @auth_manager.login_required
    def api_logs_dashboard_refresh_status(task_id: str):
        task = db.session.get(background_task_model, task_id)
        if not task or task.task_type != "logs_dashboard_refresh":
            return _error_response("Задача обновления dashboard не найдена", 404)

        return jsonify(
            {
                "success": True,
                "task_id": task.id,
                "status": task.status,
                "message": task.message,
                "error": task.error,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            }
        )
