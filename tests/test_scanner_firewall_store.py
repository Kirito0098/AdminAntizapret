"""Хранилище банов сканеров (JSON + логика strikes)."""

import tempfile
import unittest
from pathlib import Path

from utils.scanner_firewall_store import ScannerFirewallStore


class ScannerFirewallStoreTests(unittest.TestCase):
    def test_persists_ban_and_strikes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scanner_blocks.json"
            store = ScannerFirewallStore(path, strikes_for_year=5, year_ban_seconds=86400, dry_run=True)
            info = store.register_ban("198.51.100.10", reason="rate_limit", short_ban_seconds=120)
            self.assertEqual(info["strikes"], 1)

            store2 = ScannerFirewallStore(path, dry_run=True)
            self.assertTrue(store2.is_banned("198.51.100.10"))

    def test_fifth_strike_is_year_ban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scanner_blocks.json"
            store = ScannerFirewallStore(
                path, strikes_for_year=5, year_ban_seconds=365 * 86400, dry_run=True
            )
            ip = "203.0.113.99"
            for _ in range(4):
                store.register_ban(ip, reason="test", short_ban_seconds=60)
                store._entry(ip)["ban_until"] = 0

            info = store.register_ban(ip, reason="test", short_ban_seconds=60)
            self.assertTrue(info["long_term"])
            self.assertGreaterEqual(info["remaining_seconds"], 364 * 86400)

    def test_unban_sets_grace_without_active_ban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scanner_blocks.json"
            store = ScannerFirewallStore(path, dry_run=True)
            store.register_ban("203.0.113.5", reason="test", short_ban_seconds=120)
            store.unban_ip("203.0.113.5")
            display = store.get_display_state()
            self.assertEqual(display["active_bans"], [])
            self.assertEqual(len(display["grace_entries"]), 1)

    def test_clear_all_removes_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scanner_blocks.json"
            store = ScannerFirewallStore(path, dry_run=True)
            store.register_ban("198.51.100.11", reason="test", short_ban_seconds=60)
            store.clear_all()
            self.assertFalse(store.is_banned("198.51.100.11"))


if __name__ == "__main__":
    unittest.main()
