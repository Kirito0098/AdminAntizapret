import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import jsonify, make_response, redirect, render_template, request, session, url_for

from core.services.telegram_mini_session import enforce_telegram_mini_session, has_telegram_mini_session


def register_monitoring_routes(
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
    delete_client_traffic_stats,
    openvpn_log_tail_lines,
    collect_config_protocols_by_client,
    user_traffic_sample_model,
    human_bytes,
):
    def _has_telegram_mini_session() -> bool:
        return has_telegram_mini_session(session)

    def _enforce_telegram_mini_session():
        return enforce_telegram_mini_session(
            session,
            api_request=request.path.startswith("/api/"),
            redirect_endpoint="tg_mini_open",
        )

    @app.route("/logs_dashboard", methods=["GET"])
    @auth_manager.login_required
    def logs_dashboard():
        dashboard_data = get_logs_dashboard_data_cached(created_by_username=session.get("username"))
        cleanup_notice = request.args.get("cleanup_notice", "")
        cleanup_notice_kind = request.args.get("cleanup_notice_kind", "info")
        return render_template(
            "logs_dashboard.html",
            status_rows=dashboard_data["status_rows"],
            event_rows=dashboard_data["event_rows"],
            grouped_status_rows=dashboard_data["grouped_status_rows"],
            grouped_event_rows=dashboard_data["grouped_event_rows"],
            openvpn_logging_enabled=dashboard_data["openvpn_logging_enabled"],
            missing_event_log_files=dashboard_data["missing_event_log_files"],
            summary=dashboard_data["summary"],
            connected_clients=dashboard_data["connected_clients"],
            persisted_traffic_rows=dashboard_data["persisted_traffic_rows"],
            deleted_persisted_traffic_rows=dashboard_data["deleted_persisted_traffic_rows"],
            persisted_traffic_summary=dashboard_data["persisted_traffic_summary"],
            deleted_persisted_traffic_summary=dashboard_data["deleted_persisted_traffic_summary"],
            generated_at=dashboard_data["generated_at"],
            cache_meta=dashboard_data.get("cache_meta", {}),
            openvpn_log_tail_lines=openvpn_log_tail_lines,
            cleanup_notice=cleanup_notice,
            cleanup_notice_kind=cleanup_notice_kind,
        )

    @app.route("/tg-mini", methods=["GET"])
    @auth_manager.login_required
    def tg_mini_app():
        denied = _enforce_telegram_mini_session()
        if denied is not None:
            return denied

        # Always require a fresh Mini App auth hop to prevent stale session reuse
        # when Telegram account is switched on the same device.
        fresh_login = bool(session.pop("telegram_mini_fresh_login", False))
        if not fresh_login:
            return redirect(url_for("tg_mini_open"))

        response = make_response(
            render_template(
                "tg_mini_app.html",
                panel_username=str(session.get("username") or "").strip(),
                telegram_mini_id=str(session.get("telegram_mini_id") or "").strip(),
                telegram_mini_tg_username=str(session.get("telegram_mini_tg_username") or "").strip(),
                telegram_mini_tg_display_name=str(session.get("telegram_mini_tg_display_name") or "").strip(),
            )
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.route("/tg-mini/open", methods=["GET"])
    def tg_mini_open():
        response = make_response(render_template("tg_mini_open.html"))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.route("/api/tg-mini/dashboard", methods=["GET"])
    @auth_manager.login_required
    def api_tg_mini_dashboard():
        denied = _enforce_telegram_mini_session()
        if denied is not None:
            return denied

        dashboard_data = get_logs_dashboard_data_cached(created_by_username=session.get("username"))

        connected_clients = dashboard_data.get("connected_clients") or []
        grouped_status_rows = dashboard_data.get("grouped_status_rows") or []
        persisted_rows = dashboard_data.get("persisted_traffic_rows") or []
        summary = dashboard_data.get("summary") or {}

        top_connected = sorted(
            connected_clients,
            key=lambda item: (
                int(item.get("sessions") or 0),
                int(item.get("total_bytes") or 0),
            ),
            reverse=True,
        )

        one_hour_since = datetime.utcnow() - timedelta(hours=1)
        one_hour_rows = user_traffic_sample_model.query.filter(
            user_traffic_sample_model.created_at >= one_hour_since
        ).all()
        one_hour_by_client = defaultdict(int)
        for sample in one_hour_rows:
            common_name = (sample.common_name or "").strip()
            if not common_name:
                continue
            one_hour_by_client[common_name] += int(sample.delta_received or 0) + int(sample.delta_sent or 0)

        traffic_by_client = {}
        for row in persisted_rows:
            common_name = (row.get("common_name") or "").strip()
            if not common_name:
                continue

            item = traffic_by_client.setdefault(
                common_name,
                {
                    "common_name": common_name,
                    "traffic_1h": 0,
                    "traffic_1d": 0,
                    "traffic_7d": 0,
                    "traffic_30d": 0,
                    "total_bytes": 0,
                    "is_active": False,
                    "last_seen_at": "-",
                },
            )

            item["traffic_1d"] += int(row.get("traffic_1d") or 0)
            item["traffic_7d"] += int(row.get("traffic_7d") or 0)
            item["traffic_30d"] += int(row.get("traffic_30d") or 0)
            item["total_bytes"] += int(row.get("total_bytes") or 0)
            item["is_active"] = bool(item["is_active"] or row.get("is_active"))

            row_last_seen = (row.get("last_seen_at") or "-").strip() or "-"
            if row_last_seen != "-" and (
                item["last_seen_at"] in (None, "-")
                or str(row_last_seen) > str(item["last_seen_at"])
            ):
                item["last_seen_at"] = row_last_seen

        for client_name, bytes_total in one_hour_by_client.items():
            if client_name not in traffic_by_client:
                continue
            traffic_by_client[client_name]["traffic_1h"] = int(bytes_total or 0)

        top_traffic = sorted(
            traffic_by_client.values(),
            key=lambda item: int(item.get("total_bytes") or 0),
            reverse=True,
        )

        for item in top_traffic:
            item["traffic_1h_human"] = human_bytes(int(item.get("traffic_1h") or 0))
            item["traffic_1d_human"] = human_bytes(int(item.get("traffic_1d") or 0))
            item["traffic_7d_human"] = human_bytes(int(item.get("traffic_7d") or 0))
            item["traffic_30d_human"] = human_bytes(int(item.get("traffic_30d") or 0))
            item["total_bytes_human"] = human_bytes(int(item.get("total_bytes") or 0))

        top_networks = sorted(
            grouped_status_rows,
            key=lambda item: int(item.get("client_count") or 0),
            reverse=True,
        )[:10]

        return jsonify(
            {
                "success": True,
                "generated_at": dashboard_data.get("generated_at"),
                "cache_meta": dashboard_data.get("cache_meta", {}),
                "summary": {
                    "total_active_clients": int(summary.get("total_active_clients") or 0),
                    "unique_client_names": int(summary.get("unique_client_names") or 0),
                    "unique_ips": int(summary.get("unique_ips") or 0),
                    "total_openvpn_sessions": int(summary.get("total_openvpn_sessions") or 0),
                    "total_wireguard_sessions": int(summary.get("total_wireguard_sessions") or 0),
                    "total_traffic_human": summary.get("total_traffic_human") or "0 B",
                },
                "top_connected": [
                    {
                        "common_name": item.get("common_name") or "-",
                        "sessions": int(item.get("sessions") or 0),
                        "profiles": item.get("profiles") or "-",
                        "protocols": item.get("protocols") or "-",
                        "bytes_received_human": item.get("bytes_received_human") or "0 B",
                        "bytes_sent_human": item.get("bytes_sent_human") or "0 B",
                        "total_bytes_human": item.get("total_bytes_human") or "0 B",
                    }
                    for item in top_connected
                ],
                "top_networks": [
                    {
                        "network": item.get("network") or "-",
                        "client_count": int(item.get("client_count") or 0),
                        "unique_real_ips": int(item.get("unique_real_ips") or 0),
                        "total_traffic_human": item.get("total_traffic_human") or "0 B",
                    }
                    for item in top_networks
                ],
                "top_traffic": top_traffic,
                "traffic_clients": sorted(traffic_by_client.keys(), key=str.lower),
                "top_connected_count": len(top_connected),
                "top_traffic_count": len(top_traffic),
            }
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

        existing_clients = {name.lower() for name in collect_existing_config_client_names() if name}
        if client_name.lower() in existing_clients:
            return redirect(
                url_for(
                    "logs_dashboard",
                    cleanup_notice=f"У клиента '{client_name}' есть актуальный конфиг. Удаление статистики отменено.",
                    cleanup_notice_kind="error",
                )
            )

        ok, message = delete_client_traffic_stats(client_name)
        return redirect(
            url_for(
                "logs_dashboard",
                cleanup_notice=message,
                cleanup_notice_kind="success" if ok else "error",
            )
        )

    @app.route("/api/user-traffic-chart")
    @auth_manager.login_required
    def api_user_traffic_chart():
        client = (request.args.get("client") or "").strip()
        range_key = (request.args.get("range") or "7d").strip().lower()
        protocol_filter = (request.args.get("protocol") or "all").strip().lower()

        if not client:
            return jsonify({"error": "Параметр client обязателен"}), 400

        if range_key == "24h":
            range_key = "1d"

        if range_key not in ("1h", "1d", "7d", "30d", "all"):
            range_key = "7d"
        if protocol_filter not in ("all", "openvpn", "wireguard"):
            protocol_filter = "all"

        client_protocols_map = collect_config_protocols_by_client()
        client_protocols = set(client_protocols_map.get(client.lower(), set()))
        is_wireguard_only_client = bool(client_protocols) and "WireGuard" in client_protocols and "OpenVPN" not in client_protocols

        now = datetime.utcnow()
        since_dt = None
        bucket = "day"

        if range_key == "1h":
            since_dt = now - timedelta(hours=1)
            bucket = "minute5"
        elif range_key == "1d":
            since_dt = now - timedelta(hours=24)
            bucket = "hour"
        elif range_key == "7d":
            since_dt = now - timedelta(days=7)
            bucket = "day"
        elif range_key == "30d":
            since_dt = now - timedelta(days=30)
            bucket = "day"
        else:
            bucket = "month"

        query = user_traffic_sample_model.query.filter_by(common_name=client)
        if since_dt is not None:
            query = query.filter(user_traffic_sample_model.created_at >= since_dt)

        samples = query.order_by(user_traffic_sample_model.created_at.asc()).all()

        grouped = defaultdict(lambda: {"vpn": 0, "antizapret": 0, "openvpn": 0, "wireguard": 0})

        def format_bucket_dt_utc(dt_value, bucket_name):
            if not dt_value:
                return None

            if bucket_name == "minute5":
                aligned = dt_value.replace(minute=(dt_value.minute // 5) * 5, second=0, microsecond=0)
            elif bucket_name == "hour":
                aligned = dt_value.replace(minute=0, second=0, microsecond=0)
            elif bucket_name == "day":
                aligned = dt_value.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                aligned = dt_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            if aligned.tzinfo is None:
                aligned = aligned.replace(tzinfo=timezone.utc)
            else:
                aligned = aligned.astimezone(timezone.utc)

            return aligned.isoformat().replace("+00:00", "Z")

        for item in samples:
            dt = item.created_at
            if not dt:
                continue

            label_dt_utc = format_bucket_dt_utc(dt, bucket)

            if bucket == "minute5":
                minute = (dt.minute // 5) * 5
                bucket_key = dt.strftime("%Y-%m-%d %H") + f":{minute:02d}"
                label = dt.strftime("%H") + f":{minute:02d}"
            elif bucket == "hour":
                bucket_key = dt.strftime("%Y-%m-%d %H")
                label = dt.strftime("%d.%m %H:00")
            elif bucket == "day":
                bucket_key = dt.strftime("%Y-%m-%d")
                label = dt.strftime("%d.%m")
            else:
                bucket_key = dt.strftime("%Y-%m")
                label = dt.strftime("%Y-%m")

            total_delta = int(item.delta_received or 0) + int(item.delta_sent or 0)
            net = "antizapret" if item.network_type == "antizapret" else "vpn"
            protocol = (item.protocol_type or "openvpn").strip().lower()
            if protocol not in ("openvpn", "wireguard"):
                protocol = "openvpn"
            if is_wireguard_only_client and protocol == "openvpn":
                protocol = "wireguard"

            if protocol_filter != "all" and protocol != protocol_filter:
                continue

            grouped[bucket_key]["label"] = label
            if label_dt_utc and "label_dt_utc" not in grouped[bucket_key]:
                grouped[bucket_key]["label_dt_utc"] = label_dt_utc
            grouped[bucket_key][net] += total_delta
            grouped[bucket_key][protocol] += total_delta

        ordered_keys = sorted(grouped.keys())
        labels = [grouped[key].get("label", key) for key in ordered_keys]
        label_datetimes_utc = [grouped[key].get("label_dt_utc") for key in ordered_keys]
        vpn_bytes = [int(grouped[key].get("vpn", 0)) for key in ordered_keys]
        antizapret_bytes = [int(grouped[key].get("antizapret", 0)) for key in ordered_keys]
        openvpn_bytes = [int(grouped[key].get("openvpn", 0)) for key in ordered_keys]
        wireguard_bytes = [int(grouped[key].get("wireguard", 0)) for key in ordered_keys]

        total_vpn = sum(vpn_bytes)
        total_antizapret = sum(antizapret_bytes)
        total_openvpn = sum(openvpn_bytes)
        total_wireguard = sum(wireguard_bytes)

        def window_totals(since_window):
            win_query = user_traffic_sample_model.query.filter_by(common_name=client)
            if since_window is not None:
                win_query = win_query.filter(user_traffic_sample_model.created_at >= since_window)

            totals = {"vpn": 0, "antizapret": 0, "openvpn": 0, "wireguard": 0}
            for row in win_query.all():
                delta_total = int(row.delta_received or 0) + int(row.delta_sent or 0)
                network_name = "antizapret" if row.network_type == "antizapret" else "vpn"
                protocol_name = (row.protocol_type or "openvpn").strip().lower()
                if protocol_name not in ("openvpn", "wireguard"):
                    protocol_name = "openvpn"
                if is_wireguard_only_client and protocol_name == "openvpn":
                    protocol_name = "wireguard"

                if protocol_filter != "all" and protocol_name != protocol_filter:
                    continue

                totals[network_name] += delta_total
                totals[protocol_name] += delta_total

            totals["total"] = totals["vpn"] + totals["antizapret"]
            return totals

        totals_1h = window_totals(now - timedelta(hours=1))
        totals_1d = window_totals(now - timedelta(hours=24))

        return jsonify(
            {
                "client": client,
                "range": range_key,
                "bucket": bucket,
                "protocol_filter": protocol_filter,
                "labels": labels,
                "label_datetimes_utc": label_datetimes_utc,
                "vpn_bytes": vpn_bytes,
                "antizapret_bytes": antizapret_bytes,
                "openvpn_bytes": openvpn_bytes,
                "wireguard_bytes": wireguard_bytes,
                "total_vpn": total_vpn,
                "total_antizapret": total_antizapret,
                "total_openvpn": total_openvpn,
                "total_wireguard": total_wireguard,
                "total": total_vpn + total_antizapret,
                "total_vpn_human": human_bytes(total_vpn),
                "total_antizapret_human": human_bytes(total_antizapret),
                "total_openvpn_human": human_bytes(total_openvpn),
                "total_wireguard_human": human_bytes(total_wireguard),
                "total_human": human_bytes(total_vpn + total_antizapret),
                "total_1h": int(totals_1h["total"]),
                "total_1d": int(totals_1d["total"]),
                "total_1h_human": human_bytes(int(totals_1h["total"])),
                "total_1d_human": human_bytes(int(totals_1d["total"])),
            }
        )
