import json
import os
import time
from datetime import datetime, timezone

from flask import jsonify, render_template, request, session

from core.services.server_monitor import (
    build_server_monitor_page_context,
    build_system_info_response,
    collect_interface_groups,
    fetch_bandwidth_chart,
    resolve_bw_iface,
)


def register_server_monitor_routes(
    app,
    sock,
    *,
    auth_manager,
    server_monitor_proc,
):
    def _collect_bw_interface_groups():
        return collect_interface_groups()

    @app.route("/server_monitor", methods=["GET"])
    @auth_manager.login_required
    def server_monitor():
        return render_template(
            "server_monitor.html",
            **build_server_monitor_page_context(_collect_bw_interface_groups),
        )

    @app.route("/api/bw")
    @auth_manager.login_required
    def api_bw():
        iface = resolve_bw_iface(
            request.args.get("iface"),
            env_iface=os.environ.get("VNSTAT_IFACE"),
            config_iface=app.config.get("VNSTAT_IFACE"),
            default="ens3",
        )
        rng = request.args.get("range", "1d")
        payload, status = fetch_bandwidth_chart(iface, rng)
        return jsonify(payload), status

    @app.route("/api/system-info")
    @auth_manager.login_required
    def api_system_info():
        try:
            accurate = request.args.get("accurate") in ("1", "true", "yes")
            return jsonify(
                build_system_info_response(
                    server_monitor_proc,
                    accurate_cpu=accurate,
                )
            )
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
                    cpu_usage = server_monitor_proc.get_cpu_usage_nonblocking()
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
