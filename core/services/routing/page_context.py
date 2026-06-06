from core.services.antizapret_settings import read_antizapret_settings
from core.services.cidr import (
    get_available_provider_filters,
    get_available_regions,
    get_config_include_ips_route_stats,
    get_game_filter_route_limit_settings,
    get_saved_exclude_provider_keys,
    get_saved_provider_keys,
)
from core.services.cidr.route_limits import resolve_openvpn_route_total_cidr_limit


def build_routing_page_context(*, ip_manager, get_env_value):
    ip_manager.sync_enabled()
    ip_manager.restore_source_from_config()
    saved_provider_keys = get_saved_provider_keys()
    saved_exclude_provider_keys = get_saved_exclude_provider_keys()
    route_limit_settings = get_game_filter_route_limit_settings(get_env_value=get_env_value)
    return {
        "ip_files": ip_manager.list_ip_files(),
        "ip_file_states": ip_manager.get_file_states(),
        "ip_source_states": ip_manager.get_source_states(),
        "cidr_regions": get_available_regions(),
        "cidr_provider_filters": get_available_provider_filters(),
        "cidr_game_filters": get_available_provider_filters(),
        "saved_provider_keys": saved_provider_keys,
        "saved_exclude_provider_keys": saved_exclude_provider_keys,
        "saved_game_keys": saved_provider_keys,
        "game_filter_route_limit_settings": route_limit_settings,
        "config_include_ips_routes": get_config_include_ips_route_stats(
            route_limit_enforced=route_limit_settings["route_limit_enforced"],
        ),
        "cidr_total_limit": resolve_openvpn_route_total_cidr_limit(get_env_value),
        "antizapret_settings": read_antizapret_settings(),
    }
