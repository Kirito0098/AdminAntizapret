import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from core.services.settings.page_context import build_settings_page_context


class SettingsPageContextTests(unittest.TestCase):
    def test_build_settings_page_context_keys(self):
        user_model = MagicMock()
        user_model.query.all.return_value = []
        user_model.query.filter_by.return_value.all.return_value = []

        active_web_session_model = MagicMock()
        active_web_session_model.last_seen_at = datetime(2020, 1, 1)
        session_filter = MagicMock()
        session_filter.count.return_value = 0
        active_web_session_model.query.filter.return_value = session_filter

        qr_download_audit_log_model = MagicMock()
        qr_download_audit_log_model.query.order_by.return_value.limit.return_value.all.return_value = []

        telegram_mini_audit_log_model = MagicMock()
        telegram_mini_audit_log_model.query.order_by.return_value.limit.return_value.all.return_value = []

        user_action_log_model = MagicMock()
        user_action_log_model.query.order_by.return_value.limit.return_value.all.return_value = []

        ip_restriction = MagicMock()
        ip_restriction.get_allowed_ips.return_value = []
        ip_restriction.is_enabled.return_value = False
        ip_restriction.get_client_ip.return_value = "127.0.0.1"
        ip_restriction.get_scanner_settings.return_value = {
            "enabled": False,
            "max_attempts": 5,
            "window_seconds": 60,
            "ban_seconds": 3600,
            "active_bans": [],
            "grace_entries": [],
            "has_firewall_entries": False,
            "block_ip_blocked_dwell": False,
            "ip_blocked_dwell_seconds": 30,
            "strikes_for_year": 3,
            "year_ban_seconds": 86400,
            "unban_grace_seconds": 300,
            "firewall_enabled": True,
        }

        config_file_handler = MagicMock()
        config_file_handler.config_paths = {"openvpn": ["/tmp/openvpn"]}
        config_file_handler.get_config_files.return_value = ([], [], [])

        get_env_value = MagicMock(side_effect=lambda key, default=None: {
            "QR_DOWNLOAD_TOKEN_TTL_SECONDS": "600",
            "QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS": "1",
            "QR_DOWNLOAD_PIN": "",
            "TELEGRAM_AUTH_BOT_USERNAME": "",
            "TELEGRAM_AUTH_MAX_AGE_SECONDS": "300",
            "TELEGRAM_AUTH_BOT_TOKEN": "",
            "MONITOR_CPU_THRESHOLD": "90",
            "MONITOR_RAM_THRESHOLD": "90",
            "MONITOR_CHECK_INTERVAL_SECONDS": "60",
            "MONITOR_COOLDOWN_MINUTES": "30",
        }.get(key, default))

        with patch.dict("os.environ", {"APP_PORT": "5050"}), patch(
            "core.services.settings.page_context.build_panel_publish_context",
            return_value={"public_url": "http://example"},
        ), patch(
            "core.services.settings.page_context.build_telegram_mini_audit_view",
            return_value=[],
        ), patch(
            "core.services.settings.page_context.build_user_action_audit_view",
            return_value=[],
        ), patch(
            "core.services.settings.page_context.build_user_action_sessions",
            return_value=[],
        ):
            context = build_settings_page_context(
                user_model=user_model,
                active_web_session_model=active_web_session_model,
                qr_download_audit_log_model=qr_download_audit_log_model,
                telegram_mini_audit_log_model=telegram_mini_audit_log_model,
                user_action_log_model=user_action_log_model,
                ip_restriction=ip_restriction,
                config_file_handler=config_file_handler,
                group_folders={"g": ["/tmp/openvpn"]},
                get_env_value=get_env_value,
                get_nightly_idle_restart_settings=MagicMock(return_value=(True, "0 4 * * *")),
                get_active_web_session_settings=MagicMock(return_value=(300, 60)),
                get_public_download_enabled=MagicMock(return_value=True),
                collect_all_openvpn_files_for_access=MagicMock(return_value=[]),
                build_openvpn_access_groups=MagicMock(return_value=[]),
                build_conf_access_groups=MagicMock(return_value=[]),
            )

        self.assertEqual(context["port"], "5050")
        self.assertIn("users", context)
        self.assertIn("panel_publish", context)
        self.assertIn("ip_scanner_max_attempts", context)
        self.assertIn("user_action_audit_logs", context)
        self.assertEqual(context["nightly_idle_restart_time"], "04:00")
        self.assertFalse(context["telegram_auth_enabled"])


if __name__ == "__main__":
    unittest.main()
