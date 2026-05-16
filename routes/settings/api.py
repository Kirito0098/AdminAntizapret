import os
import platform
import re
import subprocess

from flask import jsonify, request, session, url_for

from config.antizapret_params import IP_FILES as _IP_FILES_META
from core.services.cidr_list_updater import (
    analyze_dpi_log,
    estimate_cidr_matches,
    estimate_cidr_matches_from_db,
    get_available_game_filters,
    get_available_regions,
    rollback_to_baseline,
    sync_game_hosts_filter,
    update_cidr_files,
    update_cidr_files_from_db,
)
from core.services.openvpn_route_limits import (
    OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS,
    clamp_openvpn_route_total_cidr_limit,
)
from core.services.settings.cidr_tasks import (
    create_cidr_task,
    find_active_cidr_task,
    get_cidr_task,
    make_start_cidr_task,
    serialize_cidr_task,
)
from core.services.tg_notify import send_tg_message


def register_settings_api_routes(
    app,
    *,
    auth_manager,
    db,
    user_model,
    ip_manager,
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
    log_telegram_audit_event,
    log_user_action_event,
    cidr_db_updater_service,
):
    _start_cidr_task = make_start_cidr_task(app)

    @app.route("/api/antizapret/ip-files", methods=["GET", "POST"])
    @auth_manager.admin_required
    def api_antizapret_ip_files():
        if request.method == "GET":
            ip_manager.sync_enabled()
            return jsonify(
                {
                    "success": True,
                    "states": {k: bool(v) for k, v in ip_manager.get_file_states().items()},
                    "source_states": {k: bool(v) for k, v in ip_manager.get_source_states().items()},
                }
            )

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "").strip().lower()
        if action == "sync_with_list":
            ip_manager.sync_enabled()
            sync_result = ip_manager.sync_enabled_from_list()
            refreshed_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

            synced_files = int(sync_result.get("synced_files", 0))
            updated_files = int(sync_result.get("updated_files", 0))
            missing_sources = [str(item) for item in (sync_result.get("missing_sources") or [])]

            details_parts = [f"synced={synced_files}", f"updated={updated_files}"]
            if missing_sources:
                details_parts.append(f"missing={','.join(missing_sources[:5])}")

            log_user_action_event(
                "settings_ip_files_sync",
                target_type="ip_file",
                target_name="all_enabled",
                details=" ".join(details_parts),
            )

            if missing_sources:
                message = (
                    f"Сверка завершена: синхронизировано {synced_files}, обновлено {updated_files}. "
                    f"Не найдены исходные файлы: {', '.join(missing_sources)}"
                )
            else:
                message = (
                    f"Сверка завершена: синхронизировано {synced_files}, обновлено {updated_files}."
                )

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "synced_files": synced_files,
                    "updated_files": updated_files,
                    "missing_sources": missing_sources,
                    "states": refreshed_states,
                }
            )

        states = payload.get("states")
        if not isinstance(states, dict):
            return jsonify({"success": False, "message": "Ожидается поле states в формате объекта"}), 400

        ip_manager.sync_enabled()
        all_ip_files_meta = ip_manager.list_ip_files()
        available_files = set(all_ip_files_meta.keys())
        current_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

        changes_count = 0
        details = []

        for ip_file, raw_state in states.items():
            if ip_file not in available_files:
                continue

            desired_enabled = bool(raw_state)
            current_enabled = bool(current_states.get(ip_file, False))
            if desired_enabled == current_enabled:
                continue

            if desired_enabled:
                affected_count = ip_manager.enable_file(ip_file)
            else:
                affected_count = ip_manager.disable_file(ip_file)

            _meta = all_ip_files_meta.get(ip_file, {})
            _display = (_meta.get("name") if isinstance(_meta, dict) else None) \
                       or ip_file.replace(".txt", "").replace("-ips", "").replace("-", " ").title()

            changes_count += 1
            details.append(ip_file)

            log_user_action_event(
                "settings_ip_file_toggle",
                target_type="ip_file",
                target_name=ip_file,
                details=f"{'вкл' if desired_enabled else 'выкл'}|{_display}|{affected_count} IP",
            )

        refreshed_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

        return jsonify(
            {
                "success": True,
                "message": "Состояние IP-файлов сохранено" if changes_count else "Изменений в IP-файлах нет",
                "changes": changes_count,
                "states": refreshed_states,
                "details": details,
            }
        )

    @app.route("/api/cidr-lists", methods=["GET", "POST"])
    @auth_manager.admin_required
    def api_cidr_lists():
        if request.method == "GET":
            current_total_limit = str(get_env_value("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)) or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)).strip()
            current_total_limit = str(clamp_openvpn_route_total_cidr_limit(current_total_limit))
            return jsonify(
                {
                    "success": True,
                    "regions": get_available_regions(),
                    "game_filters": get_available_game_filters(),
                    "settings": {
                        "openvpn_route_total_cidr_limit": int(current_total_limit),
                        "openvpn_route_total_cidr_limit_max": OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS,
                    },
                }
            )

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "").strip().lower()
        selected = payload.get("regions")
        selected_files = [str(item) for item in selected] if isinstance(selected, list) else None
        region_scopes_raw = payload.get("region_scopes")
        if isinstance(region_scopes_raw, list):
            region_scopes = [str(item).strip().lower() for item in region_scopes_raw if str(item).strip()]
        else:
            legacy_scope = str(payload.get("region_scope") or "all").strip().lower() or "all"
            region_scopes = [legacy_scope]

        include_non_geo_fallback = bool(payload.get("include_non_geo_fallback", False))
        exclude_ru_cidrs = bool(payload.get("exclude_ru_cidrs", False))
        include_game_hosts = bool(payload.get("include_game_hosts", False))
        include_game_keys_raw = payload.get("include_game_keys")
        if isinstance(include_game_keys_raw, list):
            include_game_keys = [str(item).strip().lower() for item in include_game_keys_raw if str(item).strip()]
        else:
            include_game_keys = []
        strict_geo_filter = bool(payload.get("strict_geo_filter", False))
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

        if action == "analyze_dpi_log":
            dpi_log_text = str(payload.get("dpi_log_text") or "")
            result = analyze_dpi_log(dpi_log_text)
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "set_total_limit":
            raw_limit = str(payload.get("openvpn_route_total_cidr_limit") or "").strip()
            if not raw_limit.isdigit():
                return jsonify({"success": False, "message": "Лимит CIDR должен быть целым числом"}), 400

            limit_value = int(raw_limit)
            if limit_value <= 0 or limit_value > OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS:
                return jsonify({"success": False, "message": f"Лимит CIDR должен быть в диапазоне 1..{OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS} (ограничение iOS)"}), 400

            old_cidr_limit = (get_env_value("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)) or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)).strip()
            set_env_value("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", str(limit_value))
            os.environ["OPENVPN_ROUTE_TOTAL_CIDR_LIMIT"] = str(limit_value)

            log_user_action_event(
                "settings_cidr_total_limit_update",
                target_type="cidr",
                target_name="OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
                details=f"{old_cidr_limit} → {limit_value}",
                status="success",
            )

            return jsonify(
                {
                    "success": True,
                    "message": f"Общий лимит CIDR сохранен: {limit_value}",
                    "openvpn_route_total_cidr_limit": limit_value,
                }
            )

        if action == "sync_games_hosts":
            result = sync_game_hosts_filter(
                include_game_hosts=include_game_hosts,
                include_game_keys=include_game_keys,
            )
            if result.get("success"):
                game_hosts_filter = result.get("game_hosts_filter") or {}
                game_ips_filter = result.get("game_ips_filter") or {}
                log_user_action_event(
                    "settings_cidr_games_sync",
                    target_type="cidr",
                    target_name="include-hosts",
                    details=(
                        f"enabled={1 if game_hosts_filter.get('enabled') else 0} "
                        f"selected_games={int(game_hosts_filter.get('selected_game_count') or 0)} "
                        f"domains={int(game_hosts_filter.get('domain_count') or 0)} "
                        f"cidrs={int(game_ips_filter.get('cidr_count') or 0)}"
                    ),
                    status="success",
                )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "update":
            scopes_text = ",".join(region_scopes or ["all"])

            task_id = create_cidr_task(
                "cidr_update",
                "Обновление CIDR-файлов поставлено в очередь",
            )

            def _runner(progress_callback):
                result = update_cidr_files(
                    selected_files,
                    region_scopes=region_scopes,
                    include_non_geo_fallback=include_non_geo_fallback,
                    exclude_ru_cidrs=exclude_ru_cidrs,
                    include_game_hosts=include_game_hosts,
                    include_game_keys=include_game_keys,
                    strict_geo_filter=strict_geo_filter,
                    dpi_priority_files=dpi_priority_files,
                    dpi_mandatory_files=dpi_mandatory_files,
                    dpi_priority_min_budget=dpi_priority_min_budget,
                    progress_callback=progress_callback,
                )
                # Keep AP-* files in antizapret/config in sync with freshly generated
                # ips/list/ files so that doall.sh (run separately) reads current data.
                if result.get("success") or result.get("updated"):
                    ip_manager.sync_enabled_from_list()
                return result

            _start_cidr_task(task_id, _runner)

            _files_label = "все файлы" if not selected_files else ", ".join(selected_files[:5]) + ("…" if len(selected_files) > 5 else "")
            log_user_action_event(
                "settings_cidr_update_queued",
                target_type="cidr",
                target_name="all" if not selected_files else ",".join(selected_files[:10]),
                details=(
                    f"файлы: {_files_label}; "
                    f"регионы: {scopes_text}; "
                    + (f"игры: {len(include_game_keys)}; " if include_game_hosts else "")
                    + (f"exclude_ru; " if exclude_ru_cidrs else "")
                    + (f"strict_geo" if strict_geo_filter else "")
                ).rstrip("; "),
                status="info",
            )
            return (
                jsonify(
                    {
                        "success": True,
                        "queued": True,
                        "task_id": task_id,
                        "message": "Обновление CIDR-файлов запущено в фоне",
                        "status_url": url_for("api_cidr_task_status", task_id=task_id),
                    }
                ),
                202,
            )

        if action == "estimate":
            result = estimate_cidr_matches(
                selected_files,
                region_scopes=region_scopes,
                include_non_geo_fallback=include_non_geo_fallback,
                exclude_ru_cidrs=exclude_ru_cidrs,
                include_game_hosts=include_game_hosts,
                include_game_keys=include_game_keys,
                strict_geo_filter=strict_geo_filter,
                dpi_priority_files=dpi_priority_files,
                dpi_mandatory_files=dpi_mandatory_files,
                dpi_priority_min_budget=dpi_priority_min_budget,
            )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "rollback":
            task_id = create_cidr_task(
                "cidr_rollback",
                "Откат CIDR-файлов поставлен в очередь",
            )

            def _runner(progress_callback):
                return rollback_to_baseline(selected_files, progress_callback=progress_callback)

            _start_cidr_task(task_id, _runner)

            _rollback_files_label = "все файлы" if not selected_files else ", ".join(selected_files[:5]) + ("…" if len(selected_files) > 5 else "")
            log_user_action_event(
                "settings_cidr_rollback_queued",
                target_type="cidr",
                target_name="all" if not selected_files else ",".join(selected_files[:10]),
                details=f"файлы: {_rollback_files_label}",
                status="info",
            )
            return (
                jsonify(
                    {
                        "success": True,
                        "queued": True,
                        "task_id": task_id,
                        "message": "Откат CIDR-файлов запущен в фоне",
                        "status_url": url_for("api_cidr_task_status", task_id=task_id),
                    }
                ),
                202,
            )

        return jsonify({"success": False, "message": "Неизвестное действие"}), 400

    @app.route("/api/cidr-lists/task/<task_id>", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_task_status(task_id):
        task = get_cidr_task(task_id)
        if not task:
            return jsonify({"success": False, "message": "Задача CIDR не найдена"}), 404

        payload = serialize_cidr_task(task)
        payload["success"] = True
        return jsonify(payload)

    # ── CIDR DB: статус, ручное обновление, история ──────────────────────────

    @app.route("/api/cidr-db/status", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_db_status():
        status = cidr_db_updater_service.get_db_status()
        history = cidr_db_updater_service.get_refresh_history(limit=5)
        provider_meta = {}
        for key, info in status.get("providers", {}).items():
            meta = _IP_FILES_META.get(key, {})
            dynamic_asns = info.get("active_asns") or []
            provider_meta[key] = {
                **info,
                "name": meta.get("name", key),
                "as_numbers": dynamic_asns or meta.get("as_numbers", []),
                "configured_as_numbers": meta.get("as_numbers", []),
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

        triggered_by = f"manual:{session.get('username', 'unknown')}"

        task_id = create_cidr_task("cidr_db_refresh", "Обновление CIDR БД запущено в фоне")

        def _runner(progress_callback):
            return cidr_db_updater_service.refresh_all_providers(
                triggered_by=triggered_by,
                selected_files=selected_files,
                progress_callback=progress_callback,
            )

        _start_cidr_task(task_id, _runner)

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
            "message": "Обновление CIDR БД запущено в фоне",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

    @app.route("/api/cidr-db/generate", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_db_generate():
        """Generate .txt route files from DB data (no download)."""
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "generate").strip().lower()
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
        include_game_keys_raw = payload.get("include_game_keys")
        include_game_keys = [str(k).strip().lower() for k in include_game_keys_raw if str(k).strip()] if isinstance(include_game_keys_raw, list) else []
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

        if action == "estimate":
            active_task = find_active_cidr_task("cidr_estimate_from_db")
            if active_task:
                return jsonify({
                    "success": True,
                    "queued": True,
                    "task_id": active_task.get("task_id"),
                    "message": "Оценка CIDR из БД уже выполняется",
                    "status_url": url_for("api_cidr_task_status", task_id=active_task.get("task_id")),
                }), 202

            task_id = create_cidr_task("cidr_estimate_from_db", "Оценка CIDR из БД запущена")

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

            _start_cidr_task(task_id, _estimate_runner)

            return jsonify({
                "success": True,
                "queued": True,
                "task_id": task_id,
                "message": "Оценка CIDR из БД запущена",
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

        _start_cidr_task(task_id, _runner)

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
        result = {}
        for key, meta in _IP_FILES_META.items():
            result[key] = {
                "name": meta.get("name", key),
                "description": meta.get("description", ""),
                "as_numbers": meta.get("as_numbers", []),
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

        _start_cidr_task(task_id, _runner)
        log_user_action_event("settings_antifilter_refresh", target_type="antifilter", target_name="antifilter.download", status="info")
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Обновление антифильтра запущено в фоне (~1–2 минуты)",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

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
                env=_tests_subprocess_env(app_root_dir),
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
                "tests": tests,
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
                    env=_tests_subprocess_env(app_root_dir),
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
                        tests_result.append({"id": test_id, "status": "passed"})
                        passed += 1
                    elif " FAILED" in stripped:
                        test_id = stripped.split(" FAILED")[0].strip()
                        tests_result.append({"id": test_id, "status": "failed"})
                        failed += 1
                    elif " ERROR" in stripped:
                        test_id = stripped.split(" ERROR")[0].strip()
                        tests_result.append({"id": test_id, "status": "error"})
                        errors += 1
                    elif " SKIPPED" in stripped:
                        test_id = stripped.split(" SKIPPED")[0].strip()
                        tests_result.append({"id": test_id, "status": "skipped"})
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

        _start_cidr_task(task_id, _runner)
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

    @app.route("/api/monitor-settings", methods=["POST"])
    @auth_manager.admin_required
    def api_monitor_settings():
        data = request.get_json(silent=True) or {}

        def _int_clamp(val, lo, hi, default):
            try:
                v = int(str(val).strip())
                return max(lo, min(hi, v))
            except (TypeError, ValueError):
                return default

        cpu_threshold = _int_clamp(data.get("cpu_threshold"), 1, 100, 90)
        ram_threshold = _int_clamp(data.get("ram_threshold"), 1, 100, 90)
        interval_sec  = _int_clamp(data.get("interval_seconds"), 10, 3600, 60)
        cooldown_min  = _int_clamp(data.get("cooldown_minutes"), 1, 1440, 30)

        set_env_value("MONITOR_CPU_THRESHOLD", str(cpu_threshold))
        set_env_value("MONITOR_RAM_THRESHOLD", str(ram_threshold))
        set_env_value("MONITOR_CHECK_INTERVAL_SECONDS", str(interval_sec))
        set_env_value("MONITOR_COOLDOWN_MINUTES", str(cooldown_min))
        os.environ["MONITOR_CPU_THRESHOLD"] = str(cpu_threshold)
        os.environ["MONITOR_RAM_THRESHOLD"] = str(ram_threshold)
        os.environ["MONITOR_CHECK_INTERVAL_SECONDS"] = str(interval_sec)
        os.environ["MONITOR_COOLDOWN_MINUTES"] = str(cooldown_min)

        log_user_action_event(
            "settings_monitor_update",
            target_type="monitor",
            target_name="resource_monitor",
            details=f"cpu={cpu_threshold}% ram={ram_threshold}% interval={interval_sec}с cooldown={cooldown_min}мин",
        )
        return jsonify({"success": True, "message": "Настройки мониторинга сохранены"})

    @app.route("/api/tg-notify-test", methods=["POST"])
    @auth_manager.admin_required
    def api_tg_notify_test():
        data = request.get_json(silent=True) or {}
        target_username = (data.get("username") or "").strip()
        current_username = session.get("username", "")
        if not target_username or target_username != current_username:
            return jsonify({"success": False, "message": "Тест разрешён только для собственного аккаунта"}), 403

        user = user_model.query.filter_by(username=target_username).first()
        if not user or not user.telegram_id:
            return jsonify({"success": False, "message": "Telegram ID не привязан"}), 400

        bot_token = (get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
        if not bot_token:
            return jsonify({"success": False, "message": "Бот не настроен"}), 400

        _ev_labels = [
            ("login_success",   "Успешный вход"),
            ("login_failed",    "Неверный пароль"),
            ("tg_unlinked",     "Вход с непривязанным TG ID"),
            ("config_create",   "Создание / пересоздание конфига"),
            ("config_delete",   "Удаление конфига"),
            ("user_create",     "Добавление пользователя"),
            ("user_delete",     "Удаление пользователя"),
            ("client_ban",      "Блокировка / разблокировка клиента"),
            ("settings_change", "Изменение настроек"),
            ("high_cpu",        "Высокая нагрузка CPU"),
            ("high_ram",        "Высокая нагрузка RAM"),
        ]
        enabled = [label for key, label in _ev_labels if user.has_tg_notify_event(key)]
        events_text = "\n".join(f"  ✓ {l}" for l in enabled) if enabled else "  (нет включённых событий)"

        text = (
            "🔔 <b>Тест уведомлений AdminAntiZapret</b>\n\n"
            f"Аккаунт: <code>{target_username}</code>\n\n"
            f"Включённые события:\n{events_text}"
        )
        send_tg_message(bot_token, user.telegram_id, text)
        return jsonify({"success": True, "message": "Тестовое сообщение отправлено"})

