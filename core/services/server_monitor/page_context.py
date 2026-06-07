import os

# Shared with frontend mini-charts and REST fallback poll (page-core.js).
METRICS_POLL_INTERVAL_MS = 15_000
WS_PUSH_INTERVAL_MS = 2_000
METRICS_HISTORY_LEN = 30


def build_server_monitor_page_context(collect_bw_interface_groups, default_iface=None):
    iface = default_iface or os.getenv("VNSTAT_IFACE", "ens3")
    bw_iface_groups = collect_bw_interface_groups()
    return {
        "cpu_usage": None,
        "memory_usage": None,
        "iface": iface,
        "bw_iface_groups": bw_iface_groups,
        "metrics_poll_interval_ms": METRICS_POLL_INTERVAL_MS,
        "ws_push_interval_ms": WS_PUSH_INTERVAL_MS,
        "metrics_history_len": METRICS_HISTORY_LEN,
    }
