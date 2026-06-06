"""Settings-API эндпоинты для CIDR-БД, пресетов, провайдеров и antifilter.download.

Вынесено из routes/settings/api.py. URL-пути и поведение сохранены 1:1.
Эти обработчики не используют monkeypatch-цели (get_game_filter_route_limit_settings
и т.п.), поэтому безопасно вынесены в отдельный модуль.
"""

from flask import jsonify, request, session, url_for

from config.antizapret_params import IP_FILES as _IP_FILES_META
from core.services.cidr_list_updater import (
    estimate_cidr_matches_from_db,
    update_cidr_files_from_db,
)

from routes.settings._api_shared import parse_provider_filter_payload


def register_settings_cidr_db_api_routes(
    app,
    *,
    auth_manager,
    cidr_db_updater_service,
    ip_manager,
    log_user_action_event,
    create_cidr_task,
    find_active_cidr_task,
    start_cidr_task,
):
    # ── CIDR DB: статус, ручное обновление, история ──────────────────────────

    @app.route("/api/cidr-db/status", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_db_status():
        status = cidr_db_updater_service.get_db_status()
        history = cidr_db_updater_service.get_refresh_history(limit=5)
        provider_meta = {}
        for key, info in status.get("providers", {}).items():
            meta = _IP_FILES_META.get(key, {})
            provider_meta[key] = {
                **info,
                "name": meta.get("name", key),
                "as_numbers": info.get("active_asns") or [],
                "category": meta.get("category", ""),
                "what_hosts": meta.get("what_hosts", ""),
                "tags": meta.get("tags", []),
            }
        return jsonify({
            "success": True,
            "last_refresh_started": status.get("last_refresh_started"),
            "last_refresh_finished": status.get("last_refresh_finished"),
            "last_refresh_status": status.get("last_refresh_status"),
            "last_refresh_triggered_by": status.get("last_refresh_triggered_by"),
            "total_cidrs": status.get("total_cidrs"),
            "providers": provider_meta,
            "alerts": status.get("alerts", []),
            "history": history,
        })

    @app.route("/api/cidr-db/refresh", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_db_refresh():
        payload = request.get_json(silent=True) or {}
        selected_files = payload.get("selected_files") or None
        if isinstance(selected_files, list):
            selected_files = [str(f) for f in selected_files] or None
        retry_failed_mode = str(payload.get("retry_failed_mode") or "").strip().lower() or None
        dry_run = bool(payload.get("dry_run", False))

        if retry_failed_mode in {"last", "selected"}:
            failed_from_last = cidr_db_updater_service.get_last_failed_providers()
            if retry_failed_mode == "last":
                selected_files = failed_from_last or []
            elif retry_failed_mode == "selected":
                selected_set = set(selected_files or [])
                selected_files = [name for name in failed_from_last if name in selected_set]
            if not selected_files:
                return jsonify({
                    "success": False,
                    "message": "Нет failed-провайдеров для повтора в выбранном режиме",
                }), 400

        triggered_by = f"manual:{session.get('username', 'unknown')}"

        task_type = "cidr_db_refresh_dry_run" if dry_run else "cidr_db_refresh"
        task_message = "Dry-run CIDR БД запущен в фоне" if dry_run else "Обновление CIDR БД запущено в фоне"
        task_id = create_cidr_task(task_type, task_message)

        def _runner(progress_callback):
            return cidr_db_updater_service.refresh_all_providers(
                triggered_by=triggered_by,
                selected_files=selected_files,
                progress_callback=progress_callback,
                dry_run=dry_run,
            )

        start_cidr_task(task_id, _runner)

        _db_files_label = "все файлы" if not selected_files else ", ".join((selected_files or [])[:5]) + ("…" if len(selected_files or []) > 5 else "")
        log_user_action_event(
            "settings_cidr_db_refresh_queued",
            target_type="cidr_db",
            target_name="all" if not selected_files else ",".join((selected_files or [])[:10]),
            details=f"файлы: {_db_files_label}",
            status="info",
        )
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Dry-run CIDR БД запущен в фоне" if dry_run else "Обновление CIDR БД запущено в фоне",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

    @app.route("/api/cidr-db/clear", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_db_clear():
        payload = request.get_json(silent=True) or {}
        selected_files = payload.get("selected_files")
        if isinstance(selected_files, list):
            selected_files = [str(f) for f in selected_files] or None

        triggered_by = f"manual:{session.get('username', 'unknown')}"
        result = cidr_db_updater_service.clear_provider_data(
            selected_files=selected_files,
            triggered_by=triggered_by,
        )

        _clear_label = "все файлы" if not selected_files else ", ".join((selected_files or [])[:5]) + ("…" if len(selected_files or []) > 5 else "")
        log_user_action_event(
            "settings_cidr_db_clear",
            target_type="cidr_db",
            target_name="all" if not selected_files else ",".join((selected_files or [])[:10]),
            details=f"файлы: {_clear_label}; удалено CIDR: {result.get('deleted', {}).get('provider_cidr', 0)}",
            status="success" if result.get("success") else "error",
        )

        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/cidr-db/generate", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_db_generate():
        """Generate .txt route files from DB data (no download)."""
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "generate").strip().lower()
        dry_run = bool(payload.get("dry_run", False))
        selected = payload.get("regions")
        selected_files = [str(item) for item in selected] if isinstance(selected, list) else None
        region_scopes_raw = payload.get("region_scopes")
        if isinstance(region_scopes_raw, list):
            region_scopes = [str(item).strip().lower() for item in region_scopes_raw if str(item).strip()]
        else:
            region_scopes = [str(payload.get("region_scope") or "all").strip().lower() or "all"]
        include_non_geo_fallback = bool(payload.get("include_non_geo_fallback", False))
        exclude_ru_cidrs = bool(payload.get("exclude_ru_cidrs", False))
        include_game_hosts = bool(payload.get("include_game_hosts", False))
        db_provider_payload = parse_provider_filter_payload(payload)
        include_provider_keys = db_provider_payload["include_provider_keys"]
        invalid_provider_keys = db_provider_payload["invalid_keys"]
        include_game_keys = list(include_provider_keys)
        invalid_game_keys = list(invalid_provider_keys)
        if invalid_provider_keys:
            message = f"Найдены невалидные ключи провайдеров: {', '.join(invalid_provider_keys[:10])}"
            return jsonify(
                {
                    "success": False,
                    "message": message,
                    "invalid_provider_keys": invalid_provider_keys,
                    "invalid_game_keys": invalid_game_keys,
                }
            ), 400
        strict_geo_filter = bool(payload.get("strict_geo_filter", False))
        filter_by_antifilter = bool(payload.get("filter_by_antifilter", False))
        dpi_priority_files_raw = payload.get("dpi_priority_files")
        if isinstance(dpi_priority_files_raw, list):
            dpi_priority_files = [str(item).strip() for item in dpi_priority_files_raw if str(item).strip()]
        else:
            dpi_priority_files = []
        dpi_mandatory_files_raw = payload.get("dpi_mandatory_files")
        if isinstance(dpi_mandatory_files_raw, list):
            dpi_mandatory_files = [str(item).strip() for item in dpi_mandatory_files_raw if str(item).strip()]
        else:
            dpi_mandatory_files = []
        try:
            dpi_priority_min_budget = int(payload.get("dpi_priority_min_budget") or 0)
        except (TypeError, ValueError):
            dpi_priority_min_budget = 0
        # Use None so update_cidr_files_from_db reads OPENVPN_ROUTE_TOTAL_CIDR_LIMIT
        # from the .env file at runtime (respects the value saved via the UI).
        route_limit = None

        if action in {"estimate", "estimate_dry_run"} or dry_run:
            active_task = find_active_cidr_task("cidr_estimate_from_db")
            if active_task:
                return jsonify({
                    "success": True,
                    "queued": True,
                    "task_id": active_task.get("task_id"),
                    "message": "Оценка CIDR из БД уже выполняется",
                    "status_url": url_for("api_cidr_task_status", task_id=active_task.get("task_id")),
                }), 202

            task_id = create_cidr_task("cidr_estimate_from_db", "Dry-run генерации из БД запущен")

            def _estimate_runner(progress_callback):
                return estimate_cidr_matches_from_db(
                    selected_files,
                    region_scopes=region_scopes,
                    include_non_geo_fallback=include_non_geo_fallback,
                    exclude_ru_cidrs=exclude_ru_cidrs,
                    include_game_hosts=include_game_hosts,
                    include_game_keys=include_game_keys,
                    strict_geo_filter=strict_geo_filter,
                    filter_by_antifilter=filter_by_antifilter,
                    total_cidr_limit=route_limit,
                    dpi_priority_files=dpi_priority_files,
                    dpi_mandatory_files=dpi_mandatory_files,
                    dpi_priority_min_budget=dpi_priority_min_budget,
                    progress_callback=progress_callback,
                )

            start_cidr_task(task_id, _estimate_runner)

            return jsonify({
                "success": True,
                "queued": True,
                "task_id": task_id,
                "message": "Dry-run генерации из БД запущен",
                "status_url": url_for("api_cidr_task_status", task_id=task_id),
            }), 202

        task_id = create_cidr_task("cidr_generate_from_db", "Генерация CIDR-файлов из БД запущена")

        def _runner(progress_callback):
            result = update_cidr_files_from_db(
                selected_files,
                region_scopes=region_scopes,
                include_non_geo_fallback=include_non_geo_fallback,
                exclude_ru_cidrs=exclude_ru_cidrs,
                include_game_hosts=include_game_hosts,
                include_game_keys=include_game_keys,
                strict_geo_filter=strict_geo_filter,
                filter_by_antifilter=filter_by_antifilter,
                total_cidr_limit=route_limit,
                dpi_priority_files=dpi_priority_files,
                dpi_mandatory_files=dpi_mandatory_files,
                dpi_priority_min_budget=dpi_priority_min_budget,
                progress_callback=progress_callback,
            )
            # Sync newly generated ips/list/ files into antizapret/config/AP-* so
            # that the subsequent doall.sh call picks up the fresh data.
            # update.sh reads config/*include-ips.txt, not ips/list/ directly.
            if result.get("success") or result.get("updated"):
                ip_manager.sync_enabled_from_list()
            return result

        start_cidr_task(task_id, _runner)

        _gen_files_label = "все файлы" if not selected_files else ", ".join((selected_files or [])[:5]) + ("…" if len(selected_files or []) > 5 else "")
        log_user_action_event(
            "settings_cidr_generate_from_db",
            target_type="cidr",
            target_name="all" if not selected_files else ",".join((selected_files or [])[:10]),
            details=(
                f"файлы: {_gen_files_label}; регионы: {','.join(region_scopes)}"
                + ("; без РУ" if exclude_ru_cidrs else "")
            ),
            status="info",
        )
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Генерация CIDR-файлов из БД запущена",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

    # ── CIDR Presets ──────────────────────────────────────────────────────────

    @app.route("/api/cidr-presets", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_presets_list():
        presets = cidr_db_updater_service.get_presets()
        for preset in presets:
            for prov_key in preset.get("providers", []):
                meta = _IP_FILES_META.get(prov_key, {})
                preset.setdefault("providers_meta", {})[prov_key] = {
                    "name": meta.get("name", prov_key),
                    "category": meta.get("category", ""),
                    "tags": meta.get("tags", []),
                }
        return jsonify({"success": True, "presets": presets})

    @app.route("/api/cidr-presets", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_presets_create():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "message": "Необходимо указать имя пресета"}), 400
        providers = data.get("providers")
        if not isinstance(providers, list):
            return jsonify({"success": False, "message": "Необходимо указать список провайдеров"}), 400
        preset = cidr_db_updater_service.create_preset(
            name=name,
            description=str(data.get("description") or ""),
            providers=providers,
            settings=data.get("settings"),
        )
        log_user_action_event("settings_cidr_preset_create", target_type="cidr_preset", target_name=name, status="success")
        return jsonify({"success": True, "preset": preset}), 201

    @app.route("/api/cidr-presets/<int:preset_id>", methods=["PUT"])
    @auth_manager.admin_required
    def api_cidr_presets_update(preset_id):
        data = request.get_json(silent=True) or {}
        preset = cidr_db_updater_service.update_preset(
            preset_id,
            name=str(data["name"]).strip() if "name" in data else None,
            description=str(data.get("description") or "") if "description" in data else None,
            providers=data["providers"] if "providers" in data else None,
            settings=data.get("settings") if "settings" in data else None,
        )
        if not preset:
            return jsonify({"success": False, "message": "Пресет не найден"}), 404
        log_user_action_event("settings_cidr_preset_update", target_type="cidr_preset", target_name=str(preset_id), status="success")
        return jsonify({"success": True, "preset": preset})

    @app.route("/api/cidr-presets/<int:preset_id>", methods=["DELETE"])
    @auth_manager.admin_required
    def api_cidr_presets_delete(preset_id):
        ok, msg = cidr_db_updater_service.delete_preset(preset_id)
        if not ok:
            return jsonify({"success": False, "message": msg}), 400
        log_user_action_event("settings_cidr_preset_delete", target_type="cidr_preset", target_name=str(preset_id), status="success")
        return jsonify({"success": True, "message": msg})

    @app.route("/api/cidr-presets/<int:preset_id>/reset", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_presets_reset(preset_id):
        preset = cidr_db_updater_service.reset_builtin_preset(preset_id)
        if not preset:
            return jsonify({"success": False, "message": "Встроенный пресет не найден"}), 404
        log_user_action_event("settings_cidr_preset_reset", target_type="cidr_preset", target_name=str(preset_id), status="success")
        return jsonify({"success": True, "preset": preset})

    # ── Provider info ─────────────────────────────────────────────────────────

    @app.route("/api/cidr-providers/meta", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_providers_meta():
        db_status = cidr_db_updater_service.get_db_status()
        db_providers = db_status.get("providers") or {}
        result = {}
        for key, meta in _IP_FILES_META.items():
            db_info = db_providers.get(key) or {}
            result[key] = {
                "name": meta.get("name", key),
                "description": meta.get("description", ""),
                "as_numbers": db_info.get("active_asns") or [],
                "category": meta.get("category", ""),
                "what_hosts": meta.get("what_hosts", ""),
                "tags": meta.get("tags", []),
            }
        return jsonify({"success": True, "providers": result})

    # ── Antifilter.download ───────────────────────────────────────────────────

    @app.route("/api/antifilter/status", methods=["GET"])
    @auth_manager.admin_required
    def api_antifilter_status():
        status = cidr_db_updater_service.get_antifilter_status()
        return jsonify({"success": True, **status})

    @app.route("/api/antifilter/refresh", methods=["POST"])
    @auth_manager.admin_required
    def api_antifilter_refresh():
        task_id = create_cidr_task("antifilter_refresh", "Обновление антифильтра запущено в фоне")
        _triggered_by = f"manual:{session.get('username', 'unknown')}"

        def _runner(progress_callback):
            return cidr_db_updater_service.refresh_antifilter(
                triggered_by=_triggered_by,
                progress_callback=progress_callback,
            )

        start_cidr_task(task_id, _runner)
        log_user_action_event("settings_antifilter_refresh", target_type="antifilter", target_name="antifilter.download", status="info")
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Обновление антифильтра запущено в фоне (~1–2 минуты)",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202
