"""Settings-API эндпоинты запуска pytest из веб-панели.

Вынесено из routes/settings/api.py. URL-пути и поведение сохранены 1:1.
"""

import os
import re
import subprocess

from flask import jsonify, request, url_for

from routes.settings._api_shared import tests_subprocess_env
from tests.user_labels import description_for_nodeid, enrich_test_nodeids, short_title_for_nodeid


def register_settings_tests_api_routes(
    app,
    *,
    auth_manager,
    log_user_action_event,
    create_cidr_task,
    find_active_cidr_task,
    start_cidr_task,
):
    @app.route("/api/tests/collect", methods=["GET"])
    @auth_manager.admin_required
    def api_tests_collect():
        app_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        venv_pytest = os.path.join(app_root_dir, "venv", "bin", "pytest")
        if not os.path.isfile(venv_pytest):
            venv_pytest = "pytest"
        tests_dir = os.path.join(app_root_dir, "tests")
        try:
            proc = subprocess.run(
                [venv_pytest, "--collect-only", "-q", "--no-header", tests_dir],
                capture_output=True, text=True, timeout=30, cwd=app_root_dir,
                env=tests_subprocess_env(app_root_dir),
            )
            lines = (proc.stdout + proc.stderr).strip().splitlines()
            tests = []
            seen = set()
            for line in lines:
                stripped = line.strip()
                if "::" not in stripped or stripped.startswith("="):
                    continue
                if stripped not in seen:
                    seen.add(stripped)
                    tests.append(stripped)
            if proc.returncode != 0 and not tests:
                err = (proc.stderr or proc.stdout or "").strip() or f"pytest exit {proc.returncode}"
                return jsonify({"success": False, "message": err}), 500
            tests.sort()
            return jsonify({
                "success": True,
                "tests": enrich_test_nodeids(tests),
                "count": len(tests),
                "collect_warnings": proc.returncode != 0,
            })
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    @app.route("/api/tests/run", methods=["POST"])
    @auth_manager.admin_required
    def api_tests_run():
        payload = request.get_json(silent=True) or {}
        test_ids = [str(t) for t in (payload.get("test_ids") or []) if t]

        # Whitelist: принимаем только валидные pytest nodeid внутри tests/.
        # Запрещаем любые значения, начинающиеся с '-', чтобы их нельзя было
        # интерпретировать как флаги pytest (например, "--pdb" или "-p").
        nodeid_re = re.compile(r"^tests/[\w./-]+(::[\w\[\].\-]+)*$")
        for tid in test_ids:
            if tid.startswith("-") or ".." in tid or not nodeid_re.fullmatch(tid):
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"Недопустимый идентификатор теста: {tid}",
                        }
                    ),
                    400,
                )

        app_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        venv_pytest = os.path.join(app_root_dir, "venv", "bin", "pytest")
        if not os.path.isfile(venv_pytest):
            venv_pytest = "pytest"
        tests_dir = os.path.join(app_root_dir, "tests")

        active = find_active_cidr_task("pytest_run")
        if active:
            return jsonify({
                "success": True,
                "queued": True,
                "task_id": active.get("task_id"),
                "message": "Тесты уже выполняются",
                "status_url": url_for("api_cidr_task_status", task_id=active.get("task_id")),
            }), 202

        task_id = create_cidr_task("pytest_run", "Запуск тестов...")

        def _runner(progress_callback):
            progress_callback(5, "Запуск pytest...")
            cmd = [
                venv_pytest,
                "-v",
                "--tb=short",
                "--no-header",
                "--color=no",
            ]
            if test_ids:
                cmd.extend(test_ids)
            else:
                cmd.append(tests_dir)

            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300, cwd=app_root_dir,
                    env=tests_subprocess_env(app_root_dir),
                )
                output = proc.stdout + (proc.stderr or "")
                progress_callback(90, "Разбор результатов...")

                tests_result = []
                passed = failed = errors = skipped = 0
                for line in output.splitlines():
                    stripped = line.strip()
                    if "::" not in stripped:
                        continue
                    if " PASSED" in stripped:
                        test_id = stripped.split(" PASSED")[0].strip()
                        tests_result.append({
                            "id": test_id,
                            "title": short_title_for_nodeid(test_id),
                            "description": description_for_nodeid(test_id),
                            "status": "passed",
                        })
                        passed += 1
                    elif " FAILED" in stripped:
                        test_id = stripped.split(" FAILED")[0].strip()
                        tests_result.append({
                            "id": test_id,
                            "title": short_title_for_nodeid(test_id),
                            "description": description_for_nodeid(test_id),
                            "status": "failed",
                        })
                        failed += 1
                    elif " ERROR" in stripped:
                        test_id = stripped.split(" ERROR")[0].strip()
                        tests_result.append({
                            "id": test_id,
                            "title": short_title_for_nodeid(test_id),
                            "description": description_for_nodeid(test_id),
                            "status": "error",
                        })
                        errors += 1
                    elif " SKIPPED" in stripped:
                        test_id = stripped.split(" SKIPPED")[0].strip()
                        tests_result.append({
                            "id": test_id,
                            "title": short_title_for_nodeid(test_id),
                            "description": description_for_nodeid(test_id),
                            "status": "skipped",
                        })
                        skipped += 1

                total = passed + failed + errors + skipped
                success = proc.returncode == 0
                problems = failed + errors
                return {
                    "success": success,
                    "message": (
                        f"Выполнено {total}: {passed} прошло"
                        + (f", {problems} с ошибками" if problems else "")
                        + (f", {skipped} пропущено" if skipped else "")
                    ),
                    "summary": {
                        "passed": passed,
                        "failed": failed,
                        "error": errors,
                        "skipped": skipped,
                        "total": total,
                    },
                    "tests": tests_result,
                    "raw_output": output,
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "Таймаут выполнения тестов (300 сек)"}
            except Exception as exc:
                return {"success": False, "message": str(exc)}

        start_cidr_task(task_id, _runner)
        log_user_action_event(
            "settings_tests_run",
            target_type="tests",
            target_name="pytest",
            details=f"count={'all' if not test_ids else len(test_ids)}",
        )
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Тесты запущены в фоне",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202
