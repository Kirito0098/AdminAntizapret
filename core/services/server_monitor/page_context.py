import os


def build_server_monitor_page_context(collect_bw_interface_groups, default_iface=None):
    iface = default_iface or os.getenv("VNSTAT_IFACE", "ens3")
    bw_iface_groups = collect_bw_interface_groups()
    return {
        "cpu_usage": None,
        "memory_usage": None,
        "iface": iface,
        "bw_iface_groups": bw_iface_groups,
    }
