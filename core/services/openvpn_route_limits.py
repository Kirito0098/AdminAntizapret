from core.services.cidr.constants import OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS
from core.services.cidr.route_limits import (
    clamp_openvpn_route_total_cidr_limit,
    resolve_openvpn_route_total_cidr_limit,
)

__all__ = [
    "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS",
    "clamp_openvpn_route_total_cidr_limit",
    "resolve_openvpn_route_total_cidr_limit",
]
