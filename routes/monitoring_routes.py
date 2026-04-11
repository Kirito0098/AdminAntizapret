import json
import os
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import jsonify, redirect, render_template, request, session, url_for


def register_monitoring_routes(
    app,
    sock,
    *,
    auth_manager,
    server_monitor_proc,
    collect_bw_interface_groups,
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
    @app.route("/server_monitor", methods=["GET"])
    @auth_manager.login_required
    def server_monitor():
        bw_iface_groups = collect_bw_interface_groups()
        iface = os.getenv("VNSTAT_IFACE", "ens3")
        cpu_usage = server_monitor_proc.get_cpu_usage()
        memory_usage = server_monitor_proc.get_memory_usage()
        return render_template(
            "server_monitor.html",
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            iface=iface,
            bw_iface_groups=bw_iface_groups,
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

    @app.route("/api/bw")
    @auth_manager.login_required
    def api_bw():
        iface = os.environ.get("VNSTAT_IFACE") or app.config.get("VNSTAT_IFACE")
        q_iface = request.args.get("iface")
        if q_iface:
            iface = q_iface

        rng = request.args.get("range", "1d")
        if rng not in ("1d", "7d", "30d"):
            rng = "1d"

        vnstat_bin = os.environ.get("VNSTAT_BIN", "/usr/bin/vnstat")

        def _run(args):
            return subprocess.run(args, check=True, capture_output=True, text=True)

        try:
            data_f = json.loads(_run([vnstat_bin, "--json", "f", "-i", iface]).stdout)
        except Exception:
            data_f = {}

        try:
            data_d = json.loads(_run([vnstat_bin, "--json", "d", "-i", iface]).stdout)
        except Exception as e:
            return jsonify({"error": str(e), "iface": iface}), 500

        def get_iface_block(data):
            for it in data.get("interfaces") or []:
                if it.get("name") == iface:
                    return it
            return {}

        it_f = get_iface_block(data_f)
        it_d = get_iface_block(data_d)

        traffic_f = it_f.get("traffic") or {}
        traffic_d = it_d.get("traffic") or {}

        fivemin = (
            traffic_f.get("fiveminute")
            or traffic_f.get("fiveMinute")
            or traffic_f.get("five_minutes")
            or []
        )

        days = traffic_d.get("day") or traffic_d.get("days") or []

        def sort_key_dt(h):
            d = h.get("date") or {}
            t = h.get("time") or {}
            return (
                d.get("year", 0),
                d.get("month", 0),
                d.get("day", 0),
                (t.get("hour", 0) if t else 0),
                (t.get("minute", 0) if t else 0),
            )

        def to_mbps_from_5min_bytes(b):
            return round((int(b) * 8) / (300 * 1_000_000), 3)

        def to_mbps_avg_per_day(bytes_val):
            return round((int(bytes_val) * 8) / (86_400 * 1_000_000), 3)

        labels, rx_mbps, tx_mbps = [], [], []

        if rng == "1d":
            if fivemin:
                last288 = sorted(fivemin, key=sort_key_dt)[-288:]
                for m in last288:
                    t = m.get("time") or {}
                    labels.append(
                        f"{int(t.get('hour',0)):02d}:{int(t.get('minute',0)):02d}"
                    )
                    rx_mbps.append(to_mbps_from_5min_bytes(m.get("rx", 0)))
                    tx_mbps.append(to_mbps_from_5min_bytes(m.get("tx", 0)))
            else:
                labels = [""] * 288
                rx_mbps = [0.0] * 288
                tx_mbps = [0.0] * 288
        else:
            need_days = 7 if rng == "7d" else 30
            use_days = sorted(days, key=sort_key_dt)[-need_days:]
            for d in use_days:
                date = d.get("date") or {}
                labels.append(
                    f"{int(date.get('day',0)):02d}.{int(date.get('month',0)):02d}"
                )
                rx_mbps.append(to_mbps_avg_per_day(d.get("rx", 0)))
                tx_mbps.append(to_mbps_avg_per_day(d.get("tx", 0)))

            if len(labels) < need_days:
                pad = need_days - len(labels)
                labels = [""] * pad + labels
                rx_mbps = [0.0] * pad + rx_mbps
                tx_mbps = [0.0] * pad + tx_mbps

        days_sorted = sorted(days, key=sort_key_dt)

        def sum_days(n):
            chunk = days_sorted[-n:] if days_sorted else []
            rx_sum = sum(int(x.get("rx", 0)) for x in chunk)
            tx_sum = sum(int(x.get("tx", 0)) for x in chunk)
            return {"rx_bytes": rx_sum, "tx_bytes": tx_sum, "total_bytes": rx_sum + tx_sum}

        totals = {
            "1d": sum_days(1),
            "7d": sum_days(7),
            "30d": sum_days(30),
        }

        return jsonify(
            {
                "iface": iface,
                "range": rng,
                "labels": labels,
                "rx_mbps": rx_mbps,
                "tx_mbps": tx_mbps,
                "totals": totals,
            }
        )

    @app.route("/api/user-traffic-chart")
    @auth_manager.login_required
    def api_user_traffic_chart():
        client = (request.args.get("client") or "").strip()
        range_key = (request.args.get("range") or "7d").strip().lower()
        protocol_filter = (request.args.get("protocol") or "all").strip().lower()

        if not client:
            return jsonify({"error": "Параметр client обязателен"}), 400

        if range_key not in ("1h", "24h", "7d", "30d", "all"):
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
        elif range_key == "24h":
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
            }
        )

    @app.route("/api/system-info")
    @auth_manager.login_required
    def api_system_info():
        try:
            cpu_usage = server_monitor_proc.get_cpu_usage()
            memory_usage = server_monitor_proc.get_memory_usage()
            disk_usage = server_monitor_proc.get_disk_usage()
            load_avg = server_monitor_proc.get_load_average()
            system_info = server_monitor_proc.get_system_info()
            uptime = server_monitor_proc.get_uptime()

            return jsonify({
                "cpu": {
                    "usage": cpu_usage,
                    "color": server_monitor_proc.get_status_color(cpu_usage),
                },
                "memory": {
                    "usage": memory_usage,
                    "color": server_monitor_proc.get_status_color(memory_usage),
                },
                "disk": {
                    "usage_percent": disk_usage.get("percent", 0),
                    "used_gb": round(disk_usage.get("used", 0) / (1024**3), 2),
                    "total_gb": round(disk_usage.get("total", 0) / (1024**3), 2),
                    "color": server_monitor_proc.get_status_color(disk_usage.get("percent", 0)),
                },
                "load_average": load_avg,
                "system_info": system_info,
                "uptime": uptime,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            app.logger.error("Ошибка при получении информации о системе: %s", e)
            return jsonify({"error": "Ошибка при получении информации о системе"}), 500

    @sock.route("/ws/monitor")
    def monitor_websocket(ws):
        try:
            if "username" not in session:
                ws.close(code=1008, message="Unauthorized")
                return

            while True:
                time.sleep(2)
                try:
                    cpu_usage = server_monitor_proc.get_cpu_usage()
                    memory_usage = server_monitor_proc.get_memory_usage()

                    message = json.dumps({
                        "type": "monitor_update",
                        "cpu": round(cpu_usage, 1),
                        "memory": round(memory_usage, 1),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    ws.send(message)
                except Exception as e:
                    app.logger.error("Ошибка при отправке WebSocket сообщения: %s", e)
                    break
        except Exception as e:
            app.logger.error("Ошибка WebSocket подключения: %s", e)
            try:
                ws.close()
            except Exception:
                pass
