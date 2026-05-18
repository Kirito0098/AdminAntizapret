"""Ограничение iptables-whitelist режимом публикации."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.ip_restriction import IPRestriction
from utils.panel_port_firewall import PanelPortFirewall


class IPRestrictionWhitelistFirewallGatingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)

    def _build_restriction(self, tmp_path: Path) -> IPRestriction:
        restriction = IPRestriction(env_file_path=tmp_path / ".env")
        restriction.enabled = True
        restriction.allowed_ips = {"10.0.0.1"}
        restriction.whitelist_firewall = True
        restriction._panel_port_firewall = PanelPortFirewall(dry_run=True)
        return restriction

    @patch.dict(
        os.environ,
        {
            "BIND": "127.0.0.1",
            "USE_HTTPS": "false",
            "IP_WHITELIST_FIREWALL": "true",
        },
        clear=False,
    )
    def test_sync_disables_when_reverse_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            restriction = self._build_restriction(tmp_path)
            with patch.object(restriction._panel_port_firewall, "disable") as disable_mock, patch.object(
                restriction._panel_port_firewall, "sync"
            ) as sync_mock:
                result = restriction.sync_whitelist_port_firewall()
            self.assertFalse(result)
            self.assertFalse(restriction.whitelist_firewall)
            disable_mock.assert_called_once()
            sync_mock.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "BIND": "0.0.0.0",
            "USE_HTTPS": "false",
            "IP_WHITELIST_FIREWALL": "true",
        },
        clear=False,
    )
    def test_sync_applies_when_direct_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            restriction = self._build_restriction(tmp_path)
            with patch.object(restriction._panel_port_firewall, "disable") as disable_mock, patch.object(
                restriction._panel_port_firewall, "sync", return_value=True
            ) as sync_mock:
                result = restriction.sync_whitelist_port_firewall()
            self.assertTrue(result)
            sync_mock.assert_called_once_with(restriction.allowed_ips)
            disable_mock.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "BIND": "0.0.0.0",
            "USE_HTTPS": "true",
            "SSL_CERT": "/etc/ssl/cert.pem",
            "SSL_KEY": "/etc/ssl/key.pem",
            "IP_WHITELIST_FIREWALL": "true",
        },
        clear=False,
    )
    def test_sync_applies_when_app_https(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            restriction = self._build_restriction(tmp_path)
            with patch.object(restriction._panel_port_firewall, "disable") as disable_mock, patch.object(
                restriction._panel_port_firewall, "sync", return_value=True
            ) as sync_mock:
                result = restriction.sync_whitelist_port_firewall()
            self.assertTrue(result)
            sync_mock.assert_called_once_with(restriction.allowed_ips)
            disable_mock.assert_not_called()

    @patch.dict(
        os.environ,
        {"BIND": "0.0.0.0", "USE_HTTPS": "false"},
        clear=False,
    )
    def test_is_whitelist_port_firewall_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            restriction = self._build_restriction(Path(tmp_dir))
            self.assertTrue(restriction.is_whitelist_port_firewall_active())
            restriction.whitelist_firewall = False
            self.assertFalse(restriction.is_whitelist_port_firewall_active())


if __name__ == "__main__":
    unittest.main()
