import time

from flask import jsonify, redirect, render_template, url_for

from ip_blocked.blueprint import bp
from ip_blocked.constants import IP_BLOCKED_PAGE_ENDPOINT, IP_BLOCKED_PING_ENDPOINT


def register_ip_blocked_routes(app, *, ip_restriction):
    app.register_blueprint(bp)

    @app.route("/ip-blocked", endpoint=IP_BLOCKED_PAGE_ENDPOINT)
    def ip_blocked_page():
        if not ip_restriction.is_enabled():
            return redirect(url_for("login"))

        client_ip = ip_restriction.get_client_ip()
        if ip_restriction.is_ip_allowed(client_ip):
            return redirect(url_for("login"))

        dwell_status = ip_restriction.touch_ip_blocked_presence(client_ip)
        if dwell_status.get("banned"):
            return ip_restriction.build_hard_deny_response()

        current_time = time.strftime("%Y-%m-%d %H:%M:%S")

        return render_template(
            "blocked.html",
            client_ip=client_ip,
            current_time=current_time,
            ip_blocked_dwell_tracking=ip_restriction.block_ip_blocked_dwell,
            ip_blocked_dwell_seconds=ip_restriction.ip_blocked_dwell_seconds,
            ping_url=url_for(IP_BLOCKED_PING_ENDPOINT),
        )

    @app.route("/ip-blocked/ping", methods=["GET", "POST"], endpoint=IP_BLOCKED_PING_ENDPOINT)
    def ip_blocked_ping():
        if not ip_restriction.is_enabled():
            return jsonify({"success": False, "message": "IP-ограничения выключены"}), 404

        client_ip = ip_restriction.get_client_ip()
        if ip_restriction.is_ip_allowed(client_ip):
            return jsonify({"banned": False, "tracking": False})

        dwell_status = ip_restriction.touch_ip_blocked_presence(client_ip)
        if dwell_status.get("banned"):
            return ip_restriction.build_denied_json_response(client_ip)

        return jsonify({"success": True, **dwell_status})
