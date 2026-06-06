"""Публичная точка входа settings-API.

`register_settings_api_routes` сохраняет прежнюю сигнатуру (её вызывает
routes/settings/__init__.py). Обработчик `/api/cidr-lists` остаётся в этом
модуле, потому что тесты патчат `routes.settings.api.get_game_filter_route_limit_settings`
и `routes.settings.api.get_config_include_ips_route_stats` — эти имена должны
резолвиться в пространстве имён данного модуля. Остальные группы обработчиков
вынесены в api_misc.py, api_tests.py и api_cidr_db.py.
"""

import os

from flask import jsonify, request, url_for

from core.services.cidr_list_updater import (
    AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK_ENV,
    AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT_ENV,
    analyze_dpi_log,
    estimate_cidr_matches,
    get_available_game_filters,
    get_available_provider_filters,
    get_available_regions,
    get_config_include_ips_route_stats,
    get_game_filter_route_limit_settings,
    get_saved_exclude_game_keys,
    get_saved_exclude_provider_keys,
    get_saved_game_keys,
    get_saved_provider_keys,
    preview_game_exclude_filter,
    preview_game_hosts_filter,
    preview_games_batch_stats,
    rollback_to_baseline,
    sync_game_exclude_filter,
    sync_game_hosts_filter,
    sync_game_routes_filter,
    update_cidr_files,
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
from routes.settings._api_shared import parse_provider_filter_payload as _parse_provider_filter_payload
from routes.settings.api_cidr_db import register_settings_cidr_db_api_routes
from routes.settings.api_misc import register_settings_misc_api_routes
from routes.settings.api_tests import register_settings_tests_api_routes


def _build_games_scope_sync_details(game_hosts_filter, game_ips_filter, *, include_game_domains=False):
    overlap_summary = game_ips_filter.get("overlap_summary") or {}
    return (
        f"domains_enabled={1 if include_game_domains else 0} "
        f"selected_games={int(game_hosts_filter.get('selected_provider_count') or game_hosts_filter.get('selected_game_count') or 0)} "
        f"domains={int(game_hosts_filter.get('domain_count') or 0)} "
        f"cidrs={int(game_ips_filter.get('cidr_count') or 0)} "
        f"overlap={int(overlap_summary.get('overlap_count') or 0)}"
    )


def _build_games_routes_sync_details(result, *, include_game_domains=False):
    include_hosts = result.get("game_hosts_filter") or {}
    include_ips = result.get("game_ips_filter") or {}
    exclude_hosts = result.get("game_exclude_hosts_filter") or {}
    exclude_ips = result.get("game_exclude_ips_filter") or {}
    include_overlap = (include_ips.get("overlap_summary") or {}).get("overlap_count") or 0
    exclude_overlap = (exclude_ips.get("overlap_summary") or {}).get("overlap_count") or 0
    return (
        f"domains_enabled={1 if include_game_domains else 0} "
        f"include_providers={int(include_hosts.get('selected_provider_count') or include_hosts.get('selected_game_count') or 0)} "
        f"include_domains={int(include_hosts.get('domain_count') or 0)} "
        f"include_cidrs={int(include_ips.get('cidr_count') or 0)} "
        f"include_overlap={int(include_overlap)} "
        f"exclude_providers={int(exclude_hosts.get('selected_provider_count') or exclude_hosts.get('selected_game_count') or 0)} "
        f"exclude_domains={int(exclude_hosts.get('domain_count') or 0)} "
        f"exclude_cidrs={int(exclude_ips.get('cidr_count') or 0)} "
        f"exclude_overlap={int(exclude_overlap)}"
    )


def register_settings_api_routes(
    app,
    *,
    auth_manager,
    db,
    user_model,
    user_action_log_model,
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

    register_settings_misc_api_routes(
        app,
        auth_manager=auth_manager,
        user_model=user_model,
        user_action_log_model=user_action_log_model,
        ip_manager=ip_manager,
        set_env_value=set_env_value,
        get_env_value=get_env_value,
        log_user_action_event=log_user_action_event,
    )

    register_settings_tests_api_routes(
        app,
        auth_manager=auth_manager,
        log_user_action_event=log_user_action_event,
        create_cidr_task=create_cidr_task,
        find_active_cidr_task=find_active_cidr_task,
        start_cidr_task=_start_cidr_task,
    )

    register_settings_cidr_db_api_routes(
        app,
        auth_manager=auth_manager,
        cidr_db_updater_service=cidr_db_updater_service,
        ip_manager=ip_manager,
        log_user_action_event=log_user_action_event,
        create_cidr_task=create_cidr_task,
        find_active_cidr_task=find_active_cidr_task,
        start_cidr_task=_start_cidr_task,
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
                    "provider_filters": get_available_provider_filters(),
                    "game_filters": get_available_game_filters(),
                    "saved_provider_keys": get_saved_provider_keys(),
                    "saved_exclude_provider_keys": get_saved_exclude_provider_keys(),
                    "saved_game_keys": get_saved_game_keys(),
                    "saved_exclude_game_keys": get_saved_exclude_game_keys(),
                    "config_include_ips_routes": get_config_include_ips_route_stats(),
                    "game_filter_route_limit_settings": get_game_filter_route_limit_settings(
                        get_env_value=get_env_value
                    ),
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
        silent = bool(payload.get("silent", False))
        include_game_hosts = bool(payload.get("include_game_hosts", False))
        include_game_domains = bool(payload.get("include_game_domains", False))
        provider_filter_payload = _parse_provider_filter_payload(payload)
        include_provider_keys = provider_filter_payload["include_provider_keys"]
        exclude_provider_keys = provider_filter_payload["exclude_provider_keys"]
        invalid_provider_keys = provider_filter_payload["invalid_keys"]
        conflicted_provider_keys = provider_filter_payload["conflicted_provider_keys"]
        include_game_keys = list(include_provider_keys)
        exclude_game_keys = list(exclude_provider_keys)
        invalid_game_keys = list(invalid_provider_keys)
        conflicted_game_keys = list(conflicted_provider_keys)
        if conflicted_provider_keys:
            message = (
                "Один и тот же провайдер не может быть одновременно в include и exclude: "
                f"{', '.join(conflicted_provider_keys[:10])}"
            )
            return jsonify(
                {
                    "success": False,
                    "message": message,
                    "conflicted_provider_keys": conflicted_provider_keys,
                    "conflicted_game_keys": conflicted_game_keys,
                }
            ), 400
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

        if action in {"update", "estimate"} and invalid_provider_keys:
            message = f"Найдены невалидные ключи провайдеров: {', '.join(invalid_provider_keys[:10])}"
            return jsonify(
                {
                    "success": False,
                    "message": message,
                    "invalid_provider_keys": invalid_provider_keys,
                    "invalid_game_keys": invalid_game_keys,
                }
            ), 400

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

        if action == "set_game_filter_route_limit":
            disable_route_limit = bool(payload.get("disable_route_limit", False))
            route_limit_risk_ack = bool(payload.get("route_limit_risk_ack", False))

            if disable_route_limit and not route_limit_risk_ack:
                return jsonify(
                    {
                        "success": False,
                        "message": (
                            "Чтобы отключить лимит маршрутов, подтвердите принятие рисков "
                            "превышения лимита OpenVPN/iOS/Android."
                        ),
                    }
                ), 400

            disable_env = "true" if disable_route_limit else "false"
            risk_env = "true" if route_limit_risk_ack else "false"
            set_env_value(AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT_ENV, disable_env)
            set_env_value(AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK_ENV, risk_env)
            os.environ[AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT_ENV] = disable_env
            os.environ[AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK_ENV] = risk_env

            route_limit_settings = get_game_filter_route_limit_settings(get_env_value=get_env_value)
            log_user_action_event(
                "settings_game_filter_route_limit_update",
                target_type="cidr",
                target_name="game_filter_route_limit",
                details=(
                    f"disable={disable_route_limit}|risk_ack={route_limit_risk_ack}|"
                    f"enforced={route_limit_settings['route_limit_enforced']}"
                ),
                status="success",
            )

            return jsonify(
                {
                    "success": True,
                    "message": (
                        "Лимит маршрутов для игровых фильтров отключён"
                        if not route_limit_settings["route_limit_enforced"]
                        else "Лимит маршрутов для игровых фильтров включён"
                    ),
                    "game_filter_route_limit_settings": route_limit_settings,
                    "config_include_ips_routes": get_config_include_ips_route_stats(),
                }
            )

        if action == "preview_games_sync":
            if invalid_provider_keys:
                message = f"Найдены невалидные ключи провайдеров: {', '.join(invalid_provider_keys[:10])}"
                log_user_action_event(
                    "settings_cidr_games_preview",
                    target_type="cidr",
                    target_name="include-hosts",
                    details=message,
                    status="error",
                )
                return jsonify(
                    {
                        "success": False,
                        "message": message,
                        "invalid_provider_keys": invalid_provider_keys,
                        "invalid_game_keys": invalid_game_keys,
                    }
                ), 400
            result = preview_game_hosts_filter(
                include_game_hosts=include_game_hosts,
                include_provider_keys=include_provider_keys,
                include_game_domains=include_game_domains,
            )
            preview_info = result.get("preview") or {}
            overlap_summary = preview_info.get("overlap_summary") or {}
            if not silent:
                log_user_action_event(
                    "settings_cidr_games_preview",
                    target_type="cidr",
                    target_name="AZ-Game-include",
                    details=(
                        f"selected_providers={int(preview_info.get('selected_provider_count') or preview_info.get('selected_game_count') or 0)} "
                        f"domains={int(preview_info.get('domain_count') or 0)} "
                        f"cidrs={int(preview_info.get('cidr_count') or 0)} "
                        f"unresolved={int(preview_info.get('unresolved_domain_count') or 0)} "
                        f"overlap={int(overlap_summary.get('overlap_count') or 0)} "
                        f"domains_enabled={1 if include_game_domains else 0}"
                    ),
                    status="success" if result.get("success") else "error",
                )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "preview_games_stats":
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
            result = preview_games_batch_stats(include_provider_keys=include_provider_keys)
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "preview_games_exclude":
            if invalid_provider_keys:
                message = f"Найдены невалидные ключи провайдеров: {', '.join(invalid_provider_keys[:10])}"
                log_user_action_event(
                    "settings_cidr_games_exclude_preview",
                    target_type="cidr",
                    target_name="AZ-Game-exclude",
                    details=message,
                    status="error",
                )
                return jsonify(
                    {
                        "success": False,
                        "message": message,
                        "invalid_provider_keys": invalid_provider_keys,
                        "invalid_game_keys": invalid_game_keys,
                    }
                ), 400
            result = preview_game_exclude_filter(
                include_game_hosts=include_game_hosts,
                include_provider_keys=include_provider_keys,
                include_game_domains=include_game_domains,
            )
            preview_info = result.get("preview") or {}
            overlap_summary = preview_info.get("overlap_summary") or {}
            if not silent:
                log_user_action_event(
                    "settings_cidr_games_exclude_preview",
                    target_type="cidr",
                    target_name="AZ-Game-exclude",
                    details=(
                        f"selected_providers={int(preview_info.get('selected_provider_count') or preview_info.get('selected_game_count') or 0)} "
                        f"domains={int(preview_info.get('domain_count') or 0)} "
                        f"cidrs={int(preview_info.get('cidr_count') or 0)} "
                        f"unresolved={int(preview_info.get('unresolved_domain_count') or 0)} "
                        f"overlap={int(overlap_summary.get('overlap_count') or 0)} "
                        f"domains_enabled={1 if include_game_domains else 0}"
                    ),
                    status="success" if result.get("success") else "error",
                )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "sync_games_hosts":
            if invalid_provider_keys:
                message = f"Найдены невалидные ключи провайдеров: {', '.join(invalid_provider_keys[:10])}"
                log_user_action_event(
                    "settings_cidr_games_sync",
                    target_type="cidr",
                    target_name="include-hosts",
                    details=message,
                    status="error",
                )
                return jsonify(
                    {
                        "success": False,
                        "message": message,
                        "invalid_provider_keys": invalid_provider_keys,
                        "invalid_game_keys": invalid_game_keys,
                    }
                ), 400
            result = sync_game_hosts_filter(
                include_game_hosts=include_game_hosts,
                include_provider_keys=include_provider_keys,
                include_game_domains=include_game_domains,
            )
            if result.get("success"):
                game_hosts_filter = result.get("game_hosts_filter") or {}
                game_ips_filter = result.get("game_ips_filter") or {}
                if bool(game_hosts_filter.get("changed") or game_ips_filter.get("changed")):
                    log_user_action_event(
                        "settings_cidr_games_sync",
                        target_type="cidr",
                        target_name="AZ-Game-include",
                        details=_build_games_scope_sync_details(
                            game_hosts_filter,
                            game_ips_filter,
                            include_game_domains=include_game_domains,
                        ),
                        status="success",
                    )
            else:
                log_user_action_event(
                    "settings_cidr_games_sync",
                    target_type="cidr",
                    target_name="AZ-Game-include",
                    details=str(result.get("message") or result.get("error") or "unknown_error"),
                    status="error",
                )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "sync_games_exclude":
            if invalid_provider_keys:
                message = f"Найдены невалидные ключи провайдеров: {', '.join(invalid_provider_keys[:10])}"
                log_user_action_event(
                    "settings_cidr_games_exclude_sync",
                    target_type="cidr",
                    target_name="AZ-Game-exclude",
                    details=message,
                    status="error",
                )
                return jsonify(
                    {
                        "success": False,
                        "message": message,
                        "invalid_provider_keys": invalid_provider_keys,
                        "invalid_game_keys": invalid_game_keys,
                    }
                ), 400
            result = sync_game_exclude_filter(
                include_game_hosts=include_game_hosts,
                include_provider_keys=include_provider_keys,
                include_game_domains=include_game_domains,
            )
            if result.get("success"):
                game_hosts_filter = result.get("game_hosts_filter") or {}
                game_ips_filter = result.get("game_ips_filter") or {}
                if bool(game_hosts_filter.get("changed") or game_ips_filter.get("changed")):
                    log_user_action_event(
                        "settings_cidr_games_exclude_sync",
                        target_type="cidr",
                        target_name="AZ-Game-exclude",
                        details=_build_games_scope_sync_details(
                            game_hosts_filter,
                            game_ips_filter,
                            include_game_domains=include_game_domains,
                        ),
                        status="success",
                    )
            else:
                log_user_action_event(
                    "settings_cidr_games_exclude_sync",
                    target_type="cidr",
                    target_name="AZ-Game-exclude",
                    details=str(result.get("message") or result.get("error") or "unknown_error"),
                    status="error",
                )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "sync_games_routes":
            if invalid_provider_keys:
                message = f"Найдены невалидные ключи провайдеров: {', '.join(invalid_provider_keys[:10])}"
                log_user_action_event(
                    "settings_cidr_games_routes_sync",
                    target_type="cidr",
                    target_name="AZ-Game-routes",
                    details=message,
                    status="error",
                )
                return jsonify(
                    {
                        "success": False,
                        "message": message,
                        "invalid_provider_keys": invalid_provider_keys,
                        "invalid_game_keys": invalid_game_keys,
                    }
                ), 400
            result = sync_game_routes_filter(
                include_provider_keys=include_provider_keys,
                exclude_provider_keys=exclude_provider_keys,
                include_game_domains=include_game_domains,
            )
            if result.get("success"):
                if bool(result.get("changed")):
                    log_user_action_event(
                        "settings_cidr_games_routes_sync",
                        target_type="cidr",
                        target_name="AZ-Game-routes",
                        details=_build_games_routes_sync_details(
                            result,
                            include_game_domains=include_game_domains,
                        ),
                        status="success",
                    )
            else:
                log_user_action_event(
                    "settings_cidr_games_routes_sync",
                    target_type="cidr",
                    target_name="AZ-Game-routes",
                    details=str(result.get("message") or result.get("error") or "unknown_error"),
                    status="error",
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
                    + (f"провайдеры: {len(include_provider_keys)}; " if include_game_hosts else "")
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
