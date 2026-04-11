import os

from flask import jsonify, request, session


def register_admin_routes(
    app,
    *,
    auth_manager,
    db,
    app_root,
    background_task_model,
    user_model,
    viewer_config_access_model,
    collect_all_configs_for_access,
    normalize_openvpn_group_key,
    normalize_conf_group_key,
    serialize_background_task,
    run_checked_command,
    enqueue_background_task,
    task_update_system,
    task_restart_service,
    task_accepted_response,
):
    @app.route("/check_updates", methods=["GET"])
    @auth_manager.admin_required
    def check_updates():
        try:
            run_checked_command(["git", "fetch", "origin", "main", "--quiet"], cwd=app_root, timeout=30)
            local_commit, _ = run_checked_command(["git", "rev-parse", "HEAD"], cwd=app_root, timeout=10)
            remote_commit, _ = run_checked_command(["git", "rev-parse", "origin/main"], cwd=app_root, timeout=10)

            if local_commit.strip() != remote_commit.strip():
                return {"update_available": True, "message": "Доступно обновление!"}, 200
            return {"update_available": False, "message": "У вас последняя версия"}, 200

        except Exception:
            return {
                "update_available": False,
                "message": "Не удалось проверить обновления",
            }, 200

    @app.route("/update_system", methods=["POST"])
    @auth_manager.admin_required
    def update_system():
        try:
            task = enqueue_background_task(
                "update_system",
                task_update_system,
                created_by_username=session.get("username"),
                queued_message="Обновление системы поставлено в очередь",
            )
            return task_accepted_response(task, "Обновление системы запущено в фоне.")
        except Exception:
            return {
                "success": False,
                "message": "Не удалось запустить фоновое обновление",
            }, 500

    @app.route("/api/tasks/<task_id>", methods=["GET"])
    @auth_manager.admin_required
    def api_task_status(task_id):
        task = db.session.get(background_task_model, task_id)
        if not task:
            return jsonify({"success": False, "message": "Задача не найдена"}), 404

        payload = serialize_background_task(task)
        payload["success"] = True
        return jsonify(payload)

    @app.route("/api/logs_dashboard_refresh_status/<task_id>", methods=["GET"])
    @auth_manager.login_required
    def api_logs_dashboard_refresh_status(task_id):
        task = db.session.get(background_task_model, task_id)
        if not task or task.task_type != "logs_dashboard_refresh":
            return jsonify({"success": False, "message": "Задача обновления dashboard не найдена"}), 404

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

    @app.route("/api/restart-service", methods=["POST"])
    @auth_manager.admin_required
    def api_restart_service():
        try:
            task = enqueue_background_task(
                "restart_service",
                task_restart_service,
                created_by_username=session.get("username"),
                queued_message="Перезапуск службы поставлен в очередь",
            )
            return task_accepted_response(task, "Перезапуск службы запущен в фоне.")
        except Exception as e:
            app.logger.error("Ошибка: %s", e)
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

    @app.route("/api/viewer-access", methods=["POST"])
    @auth_manager.admin_required
    def api_viewer_access():
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Неверный запрос"}), 400

        user_id = data.get("user_id")
        config_name = data.get("config_name")
        config_type = data.get("config_type")
        action = data.get("action")

        if not all([user_id, config_name, config_type, action]):
            return jsonify({"success": False, "message": "Неверные параметры"}), 400

        allowed_config_types = {"openvpn", "wg", "amneziawg"}
        if config_type not in allowed_config_types:
            return jsonify({"success": False, "message": "Неверный тип конфигурации"}), 400

        target_user = db.session.get(user_model, user_id)
        if not target_user or target_user.role != "viewer":
            return jsonify({"success": False, "message": "Пользователь не найден или не является viewer"}), 404

        target_config_names = [config_name]
        if config_type in allowed_config_types:
            all_configs = collect_all_configs_for_access(config_type)
            grouped_names = {
                os.path.basename(path)
                for path in all_configs
                if (
                    normalize_openvpn_group_key(os.path.basename(path)) == config_name
                    if config_type == "openvpn"
                    else normalize_conf_group_key(os.path.basename(path), config_type) == config_name
                )
            }
            if grouped_names:
                target_config_names = sorted(grouped_names, key=str.lower)

        if action == "grant":
            existing_names = {
                row.config_name
                for row in viewer_config_access_model.query.filter(
                    viewer_config_access_model.user_id == user_id,
                    viewer_config_access_model.config_name.in_(target_config_names),
                ).all()
            }
            for target_name in target_config_names:
                if target_name in existing_names:
                    continue
                access = viewer_config_access_model(
                    user_id=user_id, config_type=config_type, config_name=target_name
                )
                db.session.add(access)
            db.session.commit()
        elif action == "revoke":
            viewer_config_access_model.query.filter(
                viewer_config_access_model.user_id == user_id,
                viewer_config_access_model.config_name.in_(target_config_names),
            ).delete(synchronize_session=False)
            db.session.commit()
        else:
            return jsonify({"success": False, "message": "Неверное действие"}), 400

        return jsonify({"success": True})
