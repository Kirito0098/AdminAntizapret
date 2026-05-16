"""IP-ограничения и бан сканеров — только ключевые сценарии."""

import os
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.auth_routes import register_auth_routes
from utils.ip_restriction import IPRestriction
from utils.scanner_firewall_store import ScannerFirewallStore


def _register_test_auth_app(restriction: IPRestriction) -> Flask:
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
    return app


class IPRestrictionScannerBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {key: os.environ.get(key) for key in ("ALLOWED_IPS", "IP_BLOCK_SCANNERS")}

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

    def test_rate_limit_then_hard_deny(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            restriction = self._build_restriction(Path(tmp_dir))
            restriction.block_scanners = True
            ip = "203.0.113.5"
            self.assertFalse(restriction.should_hard_deny(ip))
            restriction.record_denied_access(ip)
            restriction.record_denied_access(ip)
            restriction.record_denied_access(ip)
            self.assertTrue(restriction.should_hard_deny(ip))

    def test_ip_blocked_unavailable_when_restrictions_disabled(self) -> None:
        restriction = self._build_restriction()
        restriction.enabled = False
        app = _register_test_auth_app(restriction)

        with app.test_client() as client:
            page = client.get("/ip-blocked")
            self.assertEqual(page.status_code, 302)
            self.assertIn("/login", page.location or "")
            ping = client.get("/ip-blocked/ping")
            self.assertEqual(ping.status_code, 404)

    def test_denied_ip_redirects_until_banned(self) -> None:
        restriction = self._build_restriction()
        restriction.block_scanners = True
        app = _register_test_auth_app(restriction)

        with app.test_client() as client:
            response = client.get("/", environ_base={"REMOTE_ADDR": "203.0.113.9"})
            self.assertEqual(response.status_code, 302)
            self.assertIn("/ip-blocked", response.location or "")


if __name__ == "__main__":
    unittest.main()
