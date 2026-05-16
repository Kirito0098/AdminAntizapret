from flask import redirect, render_template, request, session, url_for

from core.services.logs_dashboard import build_logs_dashboard_page_context


def register_logs_dashboard_page_routes(
    app,
    sock,
    *,
    auth_manager,
    get_logs_dashboard_data_cached,
    cleanup_status_logs_now,
    set_status_cleanup_schedule,
    normalize_traffic_protocol_scope,
    reset_persisted_traffic_data,
    collect_existing_config_client_names,
    normalize_traffic_client_identity,
    delete_client_traffic_stats,
    queue_logs_dashboard_refresh_after_traffic_mutation,
    openvpn_log_tail_lines,
):
    @app.route("/logs_dashboard", methods=["GET"])
    @auth_manager.login_required
    def logs_dashboard():
        dashboard_data = get_logs_dashboard_data_cached(created_by_username=session.get("username"))
        cleanup_notice = request.args.get("cleanup_notice", "")
        cleanup_notice_kind = request.args.get("cleanup_notice_kind", "info")
        return render_template(
            "logs_dashboard.html",
            **build_logs_dashboard_page_context(
                dashboard_data,
                cleanup_notice=cleanup_notice,
                cleanup_notice_kind=cleanup_notice_kind,
                openvpn_log_tail_lines=openvpn_log_tail_lines,
            ),
        )

    @app.route("/logs_dashboard/cleanup_status_now", methods=["POST"])
    @auth_manager.admin_required
    def logs_cleanup_status_now():
        ok, message = cleanup_status_logs_now()
        return redirect(
            url_for(
                "logs_dashboard",
                cleanup_notice=message,
                cleanup_notice_kind="success" if ok else "error",
            )
        )

    @app.route("/logs_dashboard/cleanup_status_schedule", methods=["POST"])
    @auth_manager.admin_required
    def logs_cleanup_status_schedule():
        period = (request.form.get("cleanup_period") or "none").strip().lower()
        if period not in ("none", "daily", "weekly", "monthly"):
            period = "none"

        ok, message = set_status_cleanup_schedule(period)
        return redirect(
            url_for(
                "logs_dashboard",
                cleanup_notice=message,
                cleanup_notice_kind="success" if ok else "error",
            )
        )

    @app.route("/logs_dashboard/reset_persisted_traffic", methods=["POST"])
    @auth_manager.admin_required
    def logs_reset_persisted_traffic():
        protocol_scope = normalize_traffic_protocol_scope(
            request.form.get("protocol_scope") or request.form.get("traffic_scope") or "all"
        )
        ok, message = reset_persisted_traffic_data(protocol_scope=protocol_scope)
        if ok:
            queue_logs_dashboard_refresh_after_traffic_mutation(
                created_by_username=session.get("username")
            )
        return redirect(
            url_for(
                "logs_dashboard",
                cleanup_notice=message,
                cleanup_notice_kind="success" if ok else "error",
            )
        )

    @app.route("/logs_dashboard/delete_deleted_client_traffic", methods=["POST"])
    @auth_manager.admin_required
    def logs_delete_deleted_client_traffic():
        client_name = (request.form.get("client_name") or "").strip()
        if not client_name:
            return redirect(
                url_for(
                    "logs_dashboard",
                    cleanup_notice="Не указано имя клиента для удаления статистики.",
                    cleanup_notice_kind="error",
                )
            )

        client_identity = normalize_traffic_client_identity(client_name)
        existing_clients = {
            normalize_traffic_client_identity(name)
            for name in collect_existing_config_client_names()
            if normalize_traffic_client_identity(name)
        }
        if client_identity in existing_clients:
            return redirect(
                url_for(
                    "logs_dashboard",
                    cleanup_notice=f"У клиента '{client_name}' есть актуальный конфиг. Удаление статистики отменено.",
                    cleanup_notice_kind="error",
                )
            )

        ok, message = delete_client_traffic_stats(client_name)
        if ok:
            queue_logs_dashboard_refresh_after_traffic_mutation(
                created_by_username=session.get("username")
            )
        return redirect(
            url_for(
                "logs_dashboard",
                cleanup_notice=message,
                cleanup_notice_kind="success" if ok else "error",
            )
        )
