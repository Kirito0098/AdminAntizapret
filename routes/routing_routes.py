import re

from flask import render_template

from config.antizapret_params import ANTIZAPRET_PARAMS
from core.services.cidr_list_updater import (
    get_available_game_filters,
    get_available_regions,
    get_saved_game_keys,
)

OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS = 900
_ANTIZAPRET_SETUP_FILE = "/root/antizapret/setup"


def _read_antizapret_settings():
    """Читает /root/antizapret/setup и возвращает dict {key: value}."""
    try:
        with open(_ANTIZAPRET_SETUP_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        content = ""

    settings = {}
    for p in ANTIZAPRET_PARAMS:
        key, env, typ, default = p["key"], p["env"], p["type"], p["default"]
        if typ == "string":
            m = re.search(rf"^{re.escape(env)}=(.+)$", content, re.M | re.I)
            settings[key] = m.group(1).strip() if m else default
        else:
            m = re.search(rf"^{re.escape(env)}=([yn])$", content, re.M | re.I)
            settings[key] = m.group(1).lower() if m else default
    return settings


def _clamp_total_cidr_limit_for_ios(value, default=OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return int(default)
    if parsed <= 0:
        return int(default)
    return min(parsed, OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)


def register_routing_routes(
    app,
    *,
    auth_manager,
    ip_manager,
    get_env_value,
):
    @app.route("/routing", methods=["GET"])
    @auth_manager.admin_required
    def routing():
        cidr_total_limit_raw = str(
            get_env_value(
                "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
                str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS),
            )
            or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)
        ).strip()
        cidr_total_limit_raw = str(_clamp_total_cidr_limit_for_ios(cidr_total_limit_raw))

        ip_manager.sync_enabled()
        ip_files = ip_manager.list_ip_files()
        ip_file_states = ip_manager.get_file_states()
        cidr_regions = get_available_regions()
        cidr_game_filters = get_available_game_filters()
        saved_game_keys = get_saved_game_keys()
        antizapret_settings = _read_antizapret_settings()

        return render_template(
            "routing.html",
            ip_files=ip_files,
            ip_file_states=ip_file_states,
            cidr_regions=cidr_regions,
            cidr_game_filters=cidr_game_filters,
            saved_game_keys=saved_game_keys,
            cidr_total_limit=cidr_total_limit_raw,
            antizapret_settings=antizapret_settings,
        )
