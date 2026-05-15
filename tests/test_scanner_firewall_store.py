import tempfile
import time
import unittest
from pathlib import Path

from utils.scanner_firewall_store import ScannerFirewallStore


class ScannerFirewallStoreTests(unittest.TestCase):
    def test_persists_strikes_and_ban_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scanner_blocks.json"
            store = ScannerFirewallStore(
                path,
                strikes_for_year=5,
                year_ban_seconds=86400,
                dry_run=True,
            )
            info = store.register_ban("198.51.100.10", reason="rate_limit", short_ban_seconds=120)
            self.assertEqual(info["strikes"], 1)
            self.assertFalse(info["long_term"])

            store2 = ScannerFirewallStore(path, dry_run=True)
            self.assertTrue(store2.is_banned("198.51.100.10"))
            self.assertEqual(store2._entry("198.51.100.10")["strikes"], 1)

    def test_grace_entries_visible_after_unban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scanner_blocks.json"
            store = ScannerFirewallStore(path, dry_run=True)
            store.register_ban("203.0.113.5", reason="test", short_ban_seconds=120)
            store.unban_ip("203.0.113.5")
            display = store.get_display_state()
            self.assertEqual(display["active_bans"], [])
            self.assertEqual(len(display["grace_entries"]), 1)
            self.assertEqual(display["grace_entries"][0]["ip"], "203.0.113.5")
            self.assertTrue(display["has_firewall_entries"])

    def test_clear_all_removes_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scanner_blocks.json"
            store = ScannerFirewallStore(path, dry_run=True)
            store.register_ban("198.51.100.11", reason="test", short_ban_seconds=60)
            store.clear_all()
            self.assertFalse(store.is_banned("198.51.100.11"))
            self.assertEqual((store._data.get("entries") or {}), {})


if __name__ == "__main__":
    unittest.main()
