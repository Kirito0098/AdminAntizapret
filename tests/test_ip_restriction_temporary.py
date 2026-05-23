import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.ip_restriction import IPRestriction
from utils.temporary_whitelist_store import TemporaryWhitelistStore


class IPRestrictionTemporaryTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.env_file = Path(self._tmpdir.name) / ".env"
        self.env_file.write_text("ALLOWED_IPS=10.0.0.1\n", encoding="utf-8")
        self.data_file = Path(self._tmpdir.name) / "temporary_whitelist.json"
        self._env_backup = os.environ.get("ALLOWED_IPS")
        os.environ["ALLOWED_IPS"] = "10.0.0.1"
        self.restriction = IPRestriction(env_file_path=self.env_file)
        self.restriction._temp_whitelist_store = TemporaryWhitelistStore(
            data_path=self.data_file
        )
        self.restriction._load_from_env()

    def tearDown(self):
        if self._env_backup is None:
            os.environ.pop("ALLOWED_IPS", None)
        else:
            os.environ["ALLOWED_IPS"] = self._env_backup
        self._tmpdir.cleanup()

    def test_temporary_allowed_when_enabled(self):
        now = time.time()
        ok, ip_key = self.restriction.add_temporary_ip("203.0.113.10", 3600)
        self.assertTrue(ok)
        self.assertEqual(ip_key, "203.0.113.10")
        self.assertTrue(self.restriction.is_ip_allowed("203.0.113.10"))

    def test_temporary_rejected_when_disabled(self):
        self.restriction.clear_all()
        self.restriction._load_from_env()
        self.assertFalse(self.restriction.is_enabled())
        ok, detail = self.restriction.add_temporary_ip("203.0.113.11", 3600)
        self.assertFalse(ok)
        self.assertEqual(detail, "disabled")

    def test_clear_all_removes_temporary(self):
        self.restriction.add_temporary_ip("203.0.113.12", 3600)
        self.restriction.clear_all()
        self.assertEqual(self.restriction.get_temporary_whitelist_display(), [])

    def test_firewall_sync_includes_temporary(self):
        panel_fw = MagicMock()
        panel_fw.sync.return_value = True
        self.restriction._panel_port_firewall = panel_fw
        self.restriction.whitelist_firewall = True
        with patch(
            "utils.ip_restriction.is_whitelist_port_firewall_applicable",
            return_value=True,
        ):
            self.restriction.add_temporary_ip("203.0.113.20", 3600)
            self.restriction.whitelist_firewall = True
            self.restriction.sync_whitelist_port_firewall()
        called_ips = panel_fw.sync.call_args[0][0]
        self.assertIn("203.0.113.20", called_ips)
        self.assertIn("10.0.0.1", called_ips)


if __name__ == "__main__":
    unittest.main()
