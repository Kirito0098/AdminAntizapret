import os
import re
import urllib.request
from typing import Any

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
    log_user_action_event,
) -> None:
    def _error_response(message: str, status_code: int = 400):
        return jsonify({"success": False, "message": message}), status_code

    @app.route("/check_updates", methods=["GET"])
    @auth_manager.admin_required
    def check_updates() -> tuple[dict[str, Any], int]:
        try:
            run_checked_command(["git", "fetch", "origin", "main", "--quiet"], cwd=app_root, timeout=30)
            local_commit, _ = run_checked_command(["git", "rev-parse", "HEAD"], cwd=app_root, timeout=10)
            remote_commit, _ = run_checked_command(["git", "rev-parse", "origin/main"], cwd=app_root, timeout=10)

            local_short = local_commit.strip()[:7]
            remote_short = remote_commit.strip()[:7]

            branch_out, _ = run_checked_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=app_root, timeout=10)
            branch = branch_out.strip()

            local_date_out, _ = run_checked_command(
                ["git", "log", "-1", "--format=%ci", "HEAD"], cwd=app_root, timeout=10
            )

            pending_commits: list[dict[str, str]] = []
            if local_commit.strip() != remote_commit.strip():
                log_out, _ = run_checked_command(
                    ["git", "log", "--oneline", "--format=%h|%s|%ci|%an", f"HEAD..origin/main"],
                    cwd=app_root,
                    timeout=10,
                )
                for line in log_out.strip().splitlines():
                    parts = line.split("|", 3)
                    if len(parts) == 4:
                        pending_commits.append(
                            {"hash": parts[0], "subject": parts[1], "date": parts[2][:10], "author": parts[3]}
                        )

                return {
                    "update_available": True,
                    "message": f"Доступно обновление! ({len(pending_commits)} коммит(ов))",
                    "local_commit": local_short,
                    "remote_commit": remote_short,
                    "branch": branch,
                    "local_date": local_date_out.strip()[:10],
                    "pending_count": len(pending_commits),
                    "pending_commits": pending_commits,
                }, 200

            return {
                "update_available": False,
                "message": "У вас последняя версия",
                "local_commit": local_short,
                "remote_commit": remote_short,
                "branch": branch,
                "local_date": local_date_out.strip()[:10],
                "pending_count": 0,
                "pending_commits": [],
            }, 200

        except (RuntimeError, OSError, ValueError):
            return {
                "update_available": False,
                "message": "Не удалось проверить обновления",
                "local_commit": "—",
                "remote_commit": "—",
                "branch": "—",
                "local_date": "—",
                "pending_count": 0,
                "pending_commits": [],
            }, 200

    @app.route("/api/latest-changelog", methods=["GET"])
    @auth_manager.login_required
    def api_latest_changelog():
        _CHANGELOG_URL = (
            "https://raw.githubusercontent.com/Kirito0098/AdminAntizapret/main/CHANGELOG.md"
        )
        try:
            req = urllib.request.Request(_CHANGELOG_URL, headers={"User-Agent": "AdminAntizapret/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")

            version_pattern = re.compile(r"^## \[(.+?)\]\s*[–\-]\s*(.+)$", re.MULTILINE)
            matches = list(version_pattern.finditer(content))
            if not matches:
                return jsonify({"success": False, "message": "CHANGELOG не содержит версий"}), 200

            first = matches[0]
            end = matches[1].start() if len(matches) > 1 else len(content)
            block = content[first.start():end].strip()

            version = first.group(1).strip()
            date = first.group(2).strip()

            sections = []
            section_pattern = re.compile(r"^#{3,4}\s+(.+)$", re.MULTILINE)
            sec_matches = list(section_pattern.finditer(block))

            for i, sm in enumerate(sec_matches):
                sec_end = sec_matches[i + 1].start() if i + 1 < len(sec_matches) else len(block)
                sec_text = block[sm.end():sec_end].strip()
                items = [
                    line.lstrip("-* \t").strip()
                    for line in sec_text.splitlines()
                    if line.strip().startswith(("-", "*"))
                ]
                if items:
                    sections.append({"title": sm.group(1).strip(), "items": items})

            resp = jsonify({
                "success": True,
                "version": version,
                "date": date,
                "sections": sections,
            })
            resp.headers["Cache-Control"] = "no-store"
            return resp, 200

        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 200

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
        except (RuntimeError, OSError, ValueError):
            return _error_response("Не удалось запустить фоновое обновление", 500)

    @app.route("/api/tasks/<task_id>", methods=["GET"])
    @auth_manager.admin_required
    def api_task_status(task_id: str):
        task = db.session.get(background_task_model, task_id)
        if not task:
            return _error_response("Задача не найдена", 404)

        payload = serialize_background_task(task)
        payload["success"] = True
        return jsonify(payload)

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
        except (RuntimeError, OSError, ValueError) as e:
            app.logger.error("Ошибка: %s", e)
            return _error_response(f"Ошибка: {str(e)}", 500)

    @app.route("/api/viewer-access", methods=["POST"])
    @auth_manager.admin_required
    def api_viewer_access():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not data:
            return _error_response("Неверный запрос", 400)

        user_id = data.get("user_id")
        config_name = data.get("config_name")
        config_type = data.get("config_type")
        action = data.get("action")

        if not all([user_id, config_name, config_type, action]):
            return _error_response("Неверные параметры", 400)

        allowed_config_types = {"openvpn", "wg", "amneziawg"}
        if config_type not in allowed_config_types:
            return _error_response("Неверный тип конфигурации", 400)

        target_user = db.session.get(user_model, user_id)
        if not target_user or target_user.role != "viewer":
            return _error_response("Пользователь не найден или не является viewer", 404)

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
                for row in viewer_config_access_model.query.filter_by(
                    user_id=user_id,
                    config_type=config_type,
                ).all()
                if row.config_name in target_config_names
            }
            for target_name in target_config_names:
                if target_name in existing_names:
                    continue
                access = viewer_config_access_model(
                    user_id=user_id, config_type=config_type, config_name=target_name
                )
                db.session.add(access)
            db.session.commit()
            log_user_action_event(
                "settings_viewer_access_grant",
                target_type=config_type,
                target_name=str(target_user.username),
                details=f"configs={len(target_config_names)} group={config_name}",
            )
        elif action == "revoke":
            for target_name in target_config_names:
                viewer_config_access_model.query.filter_by(
                    user_id=user_id,
                    config_type=config_type,
                    config_name=target_name,
                ).delete(synchronize_session=False)
            db.session.commit()
            log_user_action_event(
                "settings_viewer_access_revoke",
                target_type=config_type,
                target_name=str(target_user.username),
                details=f"configs={len(target_config_names)} group={config_name}",
            )
        else:
            return _error_response("Неверное действие", 400)

        return jsonify({"success": True})
