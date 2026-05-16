from core.services.antizapret_settings import read_antizapret_settings
from core.services.cidr import (
    get_available_game_filters,
    get_available_regions,
    get_saved_game_keys,
)
from core.services.cidr.route_limits import resolve_openvpn_route_total_cidr_limit


def build_routing_page_context(*, ip_manager, get_env_value):
    ip_manager.sync_enabled()
    ip_manager.restore_source_from_config()
    return {
        "ip_files": ip_manager.list_ip_files(),
        "ip_file_states": ip_manager.get_file_states(),
        "ip_source_states": ip_manager.get_source_states(),
        "cidr_regions": get_available_regions(),
        "cidr_game_filters": get_available_game_filters(),
        "saved_game_keys": get_saved_game_keys(),
        "cidr_total_limit": resolve_openvpn_route_total_cidr_limit(get_env_value),
        "antizapret_settings": read_antizapret_settings(),
    }
