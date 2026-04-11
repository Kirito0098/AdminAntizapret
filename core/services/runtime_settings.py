import os


class RuntimeSettingsService:
    def __init__(self, *, get_env_value, logs_dir="/etc/openvpn/server/logs"):
        self.get_env_value = get_env_value
        self.logs_dir = logs_dir

    def _env_int(self, key, default, min_value=None):
        try:
            value = int(self.get_env_value(key, str(default)))
        except (TypeError, ValueError):
            value = int(default)
        if min_value is not None and value < int(min_value):
            value = int(min_value)
        return value

    def _env_bool(self, key, default=False):
        fallback = "true" if default else "false"
        return self.get_env_value(key, fallback).strip().lower() == "true"

    def _env_str(self, key, default):
        return (self.get_env_value(key, default) or default).strip()

    def load(self):
        logs_dir = self.logs_dir

        openvpn_log_tail_lines = self._env_int("OPENVPN_LOG_TAIL_LINES", 2000, min_value=0)
        openvpn_event_max_response_bytes = self._env_int(
            "OPENVPN_EVENT_MAX_RESPONSE_BYTES", 1048576, min_value=0
        )
        openvpn_peer_info_cache_ttl_seconds = self._env_int(
            "OPENVPN_PEER_INFO_CACHE_TTL_SECONDS", 604800, min_value=0
        )
        openvpn_peer_info_history_retention_seconds = self._env_int(
            "OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS", 604800, min_value=0
        )
        traffic_db_stale_seconds = self._env_int("TRAFFIC_DB_STALE_SECONDS", 600, min_value=0)
        active_web_session_ttl_seconds = self._env_int(
            "ACTIVE_WEB_SESSION_TTL_SECONDS", 180, min_value=30
        )
        active_web_session_touch_interval_seconds = self._env_int(
            "ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", 30, min_value=1
        )
        logs_dashboard_cache_ttl_seconds = self._env_int(
            "LOGS_DASHBOARD_CACHE_TTL_SECONDS", 45, min_value=5
        )
        wireguard_active_handshake_seconds = self._env_int(
            "WIREGUARD_ACTIVE_HANDSHAKE_SECONDS", 180, min_value=0
        )
        wireguard_peer_cache_sync_min_interval_seconds = self._env_int(
            "WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS", 300, min_value=0
        )

        return {
            "LOGS_DIR": logs_dir,
            "OPENVPN_SOCKET_DIR": self._env_str("OPENVPN_SOCKET_DIR", "/run/openvpn-server"),
            "OPENVPN_SOCKET_TIMEOUT": 2.5,
            "OPENVPN_SOCKET_IDLE_TIMEOUT": 0.12,
            "OPENVPN_LOG_TAIL_LINES": openvpn_log_tail_lines,
            "OPENVPN_EVENT_MAX_RESPONSE_BYTES": openvpn_event_max_response_bytes,
            "OPENVPN_PEER_INFO_CACHE_TTL_SECONDS": openvpn_peer_info_cache_ttl_seconds,
            "OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS": openvpn_peer_info_history_retention_seconds,
            "TRAFFIC_DB_STALE_SECONDS": traffic_db_stale_seconds,
            "TRAFFIC_SYNC_CRON_MARKER": "# adminantizapret-traffic-sync",
            "TRAFFIC_SYNC_CRON_EXPR": self._env_str("TRAFFIC_SYNC_CRON", "*/1 * * * *"),
            "TRAFFIC_SYNC_ENABLED": self._env_bool("TRAFFIC_SYNC_ENABLED", default=True),
            "NIGHTLY_IDLE_RESTART_MARKER": "# adminantizapret-nightly-idle-restart",
            "NIGHTLY_IDLE_RESTART_CRON_EXPR": self._env_str("NIGHTLY_IDLE_RESTART_CRON", "0 4 * * *"),
            "NIGHTLY_IDLE_RESTART_ENABLED": self._env_bool("NIGHTLY_IDLE_RESTART_ENABLED", default=True),
            "ACTIVE_WEB_SESSION_TTL_SECONDS": active_web_session_ttl_seconds,
            "ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS": active_web_session_touch_interval_seconds,
            "LOGS_DASHBOARD_CACHE_TTL_SECONDS": logs_dashboard_cache_ttl_seconds,
            "STATUS_LOG_FILES": {
                "antizapret-tcp": os.path.join(logs_dir, "antizapret-tcp-status.log"),
                "antizapret-udp": os.path.join(logs_dir, "antizapret-udp-status.log"),
                "vpn-tcp": os.path.join(logs_dir, "vpn-tcp-status.log"),
                "vpn-udp": os.path.join(logs_dir, "vpn-udp-status.log"),
            },
            "EVENT_LOG_FILES": {
                "antizapret-tcp": os.path.join(logs_dir, "antizapret-tcp.log"),
                "antizapret-udp": os.path.join(logs_dir, "antizapret-udp.log"),
                "vpn-tcp": os.path.join(logs_dir, "vpn-tcp.log"),
                "vpn-udp": os.path.join(logs_dir, "vpn-udp.log"),
            },
            "WIREGUARD_CONFIG_FILES": {
                "antizapret": "/etc/wireguard/antizapret.conf",
                "vpn": "/etc/wireguard/vpn.conf",
            },
            "WIREGUARD_ACTIVE_HANDSHAKE_SECONDS": wireguard_active_handshake_seconds,
            "WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS": wireguard_peer_cache_sync_min_interval_seconds,
            "STATUS_LOG_CLEANUP_MARKER": "# adminantizapret-status-cleanup",
            "STATUS_LOG_CLEANUP_PERIODS": {
                "daily": ("0 3 * * *", "Ежедневно"),
                "weekly": ("0 3 * * 0", "Еженедельно"),
                "monthly": ("0 3 1 * *", "Ежемесячно"),
            },
        }
