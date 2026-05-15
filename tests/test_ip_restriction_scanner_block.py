import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from utils.ip_restriction import IPRestriction
from utils.scanner_firewall_store import ScannerFirewallStore


class IPRestrictionScannerBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {
            key: os.environ.get(key)
            for key in (
                "ALLOWED_IPS",
                "IP_BLOCK_SCANNERS",
                "IP_SCANNER_MAX_ATTEMPTS",
                "IP_SCANNER_WINDOW_SECONDS",
                "IP_SCANNER_BAN_SECONDS",
            )
        }
        os.environ["ALLOWED_IPS"] = "10.0.0.1"
        os.environ["IP_BLOCK_SCANNERS"] = "false"
        os.environ["IP_SCANNER_MAX_ATTEMPTS"] = "3"
        os.environ["IP_SCANNER_WINDOW_SECONDS"] = "60"
        os.environ["IP_SCANNER_BAN_SECONDS"] = "120"

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _build_restriction(self, tmp_path: Path | None = None) -> IPRestriction:
        restriction = IPRestriction()
        restriction.enabled = True
        restriction.allowed_ips = {"10.0.0.1"}
        restriction.block_scanners = False
        restriction.scanner_max_attempts = 3
        restriction.scanner_window_seconds = 60
        restriction.scanner_ban_seconds = 120
        if tmp_path is not None:
            restriction._firewall_store = ScannerFirewallStore(
                tmp_path / "scanner_blocks.json",
                strikes_for_year=5,
                year_ban_seconds=365 * 86400,
                firewall_enabled=True,
                dry_run=True,
            )
        return restriction

    def test_hard_deny_only_when_server_ban_active(self) -> None:
        restriction = self._build_restriction()
        restriction.block_scanners = True
        self.assertFalse(restriction.should_hard_deny("203.0.113.5"))
        restriction._firewall_store.register_ban(
            "203.0.113.5", reason="test", short_ban_seconds=120
        )
        self.assertTrue(restriction.should_hard_deny("203.0.113.5"))

    def test_ip_blocked_dwell_bans_after_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            restriction = self._build_restriction(Path(tmp_dir))
            restriction.block_ip_blocked_dwell = True
            restriction.ip_blocked_dwell_seconds = 30

            self.assertFalse(restriction.touch_ip_blocked_presence("203.0.113.7").get("banned"))

            entry = restriction._firewall_store._entry("203.0.113.7")
            entry["ip_blocked_since"] = time.time() - 31
            status = restriction.touch_ip_blocked_presence("203.0.113.7")
            self.assertTrue(status.get("banned"))
            self.assertTrue(restriction.is_scanner_banned("203.0.113.7"))

    def test_soft_deny_until_ban_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            restriction = self._build_restriction(Path(tmp_dir))
            restriction.block_scanners = True
            self.assertFalse(restriction.should_hard_deny("203.0.113.5"))
            restriction.record_denied_access("203.0.113.5")
            restriction.record_denied_access("203.0.113.5")
            self.assertFalse(restriction.should_hard_deny("203.0.113.5"))
            restriction.record_denied_access("203.0.113.5")
            self.assertTrue(restriction.should_hard_deny("203.0.113.5"))

    def test_fifth_strike_triggers_year_ban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            restriction = self._build_restriction(Path(tmp_dir))
            ip = "203.0.113.99"
            for _ in range(4):
                restriction._firewall_store.register_ban(
                    ip, reason="test", short_ban_seconds=60
                )
                restriction._firewall_store._entry(ip)["ban_until"] = 0

            info = restriction._firewall_store.register_ban(
                ip, reason="test", short_ban_seconds=60
            )
            self.assertTrue(info["long_term"])
            self.assertGreaterEqual(info["remaining_seconds"], 364 * 86400)

    def test_save_scanner_settings_writes_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            project_root.mkdir(parents=True, exist_ok=True)
            app = Flask(__name__, root_path=str(project_root))

            restriction = IPRestriction()
            restriction.init_app(app)
            restriction.set_scanner_protection(
                enabled=True,
                max_attempts=7,
                window_seconds=90,
                ban_seconds=600,
            )

            env_text = (project_root / ".env").read_text(encoding="utf-8")
            self.assertIn("IP_BLOCK_SCANNERS=true", env_text)
            self.assertIn("IP_SCANNER_MAX_ATTEMPTS=7", env_text)
            self.assertIn("IP_SCANNER_WINDOW_SECONDS=90", env_text)
            self.assertIn("IP_SCANNER_BAN_SECONDS=600", env_text)

    def test_ip_blocked_unavailable_when_restrictions_disabled(self) -> None:
        from routes.auth_routes import register_auth_routes

        restriction = self._build_restriction()
        restriction.enabled = False

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        app.config["TESTING"] = True

        class FakeAuthManager:
            def login_required(self, fn):
                return fn

        register_auth_routes(
            app,
            auth_manager=FakeAuthManager(),
            captcha_generator=object(),
            ip_restriction=restriction,
            limiter=None,
            db=object(),
            user_model=object(),
            touch_active_web_session=lambda *args, **kwargs: None,
            remove_active_web_session=lambda: None,
            log_telegram_audit_event=lambda *args, **kwargs: None,
        )

        with app.test_client() as client:
            page = client.get("/ip-blocked")
            self.assertEqual(page.status_code, 302)
            self.assertIn("/login", page.location or "")

            ping = client.get("/ip-blocked/ping")
            self.assertEqual(ping.status_code, 404)
            self.assertFalse(ping.get_json().get("success"))

    def test_before_request_redirects_to_ip_blocked_when_not_banned(self) -> None:
        from routes.auth_routes import register_auth_routes

        restriction = self._build_restriction()
        restriction.block_scanners = True

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        app.config["TESTING"] = True

        class FakeAuthManager:
            def login_required(self, fn):
                return fn

        register_auth_routes(
            app,
            auth_manager=FakeAuthManager(),
            captcha_generator=object(),
            ip_restriction=restriction,
            limiter=None,
            db=object(),
            user_model=object(),
            touch_active_web_session=lambda *args, **kwargs: None,
            remove_active_web_session=lambda: None,
            log_telegram_audit_event=lambda *args, **kwargs: None,
        )

        with app.test_client() as client:
            response = client.get("/", environ_base={"REMOTE_ADDR": "203.0.113.9"})
            self.assertEqual(response.status_code, 302)
            self.assertIn("/ip-blocked", response.location or "")

    def test_before_request_hard_deny_when_banned(self) -> None:
        from routes.auth_routes import register_auth_routes

        with tempfile.TemporaryDirectory() as tmp_dir:
            restriction = self._build_restriction(Path(tmp_dir))
            restriction.block_scanners = True
            restriction._firewall_store.register_ban(
                "203.0.113.9", reason="test", short_ban_seconds=120
            )

            app = Flask(__name__)
            app.config["SECRET_KEY"] = "test"
            app.config["TESTING"] = True

            class FakeAuthManager:
                def login_required(self, fn):
                    return fn

            register_auth_routes(
                app,
                auth_manager=FakeAuthManager(),
                captcha_generator=object(),
                ip_restriction=restriction,
                limiter=None,
                db=object(),
                user_model=object(),
                touch_active_web_session=lambda *args, **kwargs: None,
                remove_active_web_session=lambda: None,
                log_telegram_audit_event=lambda *args, **kwargs: None,
            )

            with app.test_client() as client:
                response = client.get("/", environ_base={"REMOTE_ADDR": "203.0.113.9"})
                self.assertEqual(response.status_code, 403)
                self.assertIn(b"Forbidden", response.data)


if __name__ == "__main__":
    unittest.main()
