from core.services.cidr_list_updater import OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS

__all__ = [
    "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS",
    "clamp_openvpn_route_total_cidr_limit",
    "resolve_openvpn_route_total_cidr_limit",
]


def clamp_openvpn_route_total_cidr_limit(value, *, default=OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return int(default)
    if parsed <= 0:
        return int(default)
    return min(parsed, OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)


def resolve_openvpn_route_total_cidr_limit(get_env_value):
    raw = str(
        get_env_value(
            "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
            str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS),
        )
        or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)
    ).strip()
    return str(clamp_openvpn_route_total_cidr_limit(raw))
