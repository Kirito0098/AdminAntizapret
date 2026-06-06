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
        wg_policy_sync_enabled = self._env_bool("WG_POLICY_SYNC_ENABLED", default=True)
        wg_policy_sync_cron_expr = self._env_str("WG_POLICY_SYNC_CRON", "*/2 * * * *")
        monitor_enabled = self._env_bool("MONITOR_ENABLED", default=True)
        active_web_session_tracking_enabled = self._env_bool(
            "ACTIVE_WEB_SESSION_TRACKING_ENABLED", default=True
        )
        runtime_backup_cleanup_enabled = self._env_bool(
            "RUNTIME_BACKUP_CLEANUP_ENABLED", default=True
        )
        backup_root = self._env_str("APP_BACKUP_ROOT", "/var/backups/antizapret")
        backup_interval_days = self._env_int("APP_BACKUP_INTERVAL_DAYS", 1, min_value=1)
        if backup_interval_days not in (1, 7, 30):
            backup_interval_days = 1
        backup_time = self._env_str("APP_BACKUP_TIME", "03:00")
        backup_components = self._env_str("APP_BACKUP_COMPONENTS", "db,env,data")
        backup_tg_admin_ids = self._env_str("APP_BACKUP_TG_ADMIN_IDS", "")
        backup_az_enabled = self._env_bool("APP_BACKUP_AZ_ENABLED", default=True)
        backup_az_install_dir = self._env_str("APP_BACKUP_AZ_INSTALL_DIR", "") or self._env_str(
            "ANTIZAPRET_INSTALL_DIR", "/root/antizapret"
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
            "RUNTIME_BACKUP_CLEANUP_MARKER": "# adminantizapret-runtime-backup-cleanup",
            "RUNTIME_BACKUP_CLEANUP_CRON_EXPR": self._env_str("RUNTIME_BACKUP_CLEANUP_CRON", "0 * * * *"),
            "RUNTIME_BACKUP_RETENTION_HOURS": self._env_int(
                "RUNTIME_BACKUP_RETENTION_HOURS", 12, min_value=0
            ),
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
            "WG_POLICY_SYNC_ENABLED": wg_policy_sync_enabled,
            "WG_POLICY_SYNC_CRON_MARKER": "# adminantizapret-wg-policy-sync",
            "WG_POLICY_SYNC_CRON_EXPR": wg_policy_sync_cron_expr,
            "MONITOR_ENABLED": monitor_enabled,
            "ACTIVE_WEB_SESSION_TRACKING_ENABLED": active_web_session_tracking_enabled,
            "RUNTIME_BACKUP_CLEANUP_ENABLED": runtime_backup_cleanup_enabled,
            "APP_BACKUP_CRON_MARKER": "# adminantizapret-app-backup",
            "APP_BACKUP_ENABLED": self._env_bool("APP_BACKUP_ENABLED", default=False),
            "APP_BACKUP_INTERVAL_DAYS": backup_interval_days,
            "APP_BACKUP_TIME": backup_time,
            "APP_BACKUP_COMPONENTS": backup_components,
            "APP_BACKUP_TG_ENABLED": self._env_bool("APP_BACKUP_TG_ENABLED", default=False),
            "APP_BACKUP_TG_ADMIN_IDS": backup_tg_admin_ids,
            "APP_BACKUP_ROOT": backup_root,
            "APP_BACKUP_RETENTION_COUNT": 5,
            "APP_BACKUP_SERVICE_NAME": self._env_str("APP_BACKUP_SERVICE_NAME", "admin-antizapret"),
            "APP_BACKUP_AZ_ENABLED": backup_az_enabled,
            "APP_BACKUP_AZ_INSTALL_DIR": backup_az_install_dir,
            "STATUS_LOG_CLEANUP_MARKER": "# adminantizapret-status-cleanup",
            "STATUS_LOG_CLEANUP_PERIODS": {
                "daily": ("0 3 * * *", "Ежедневно"),
                "weekly": ("0 3 * * 0", "Еженедельно"),
                "monthly": ("0 3 1 * *", "Ежемесячно"),
            },
        }
