import tempfile
import time
import unittest
from pathlib import Path

from utils.temporary_whitelist_store import (
    TemporaryWhitelistStore,
    duration_seconds_from_label,
    normalize_host_ip,
)


class TemporaryWhitelistStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = TemporaryWhitelistStore(
            data_path=Path(self._tmpdir.name) / "temporary_whitelist.json"
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_normalize_rejects_cidr(self):
        self.assertIsNone(normalize_host_ip("10.0.0.0/24"))
        self.assertEqual(normalize_host_ip("10.0.0.1"), "10.0.0.1")

    def test_duration_labels(self):
        self.assertEqual(duration_seconds_from_label("1h"), 3600)
        self.assertEqual(duration_seconds_from_label("12h"), 43200)
        self.assertIsNone(duration_seconds_from_label("2h"))

    def test_add_and_is_allowed(self):
        now = 1_000_000.0
        self.assertTrue(self.store.add("192.168.1.5", 3600, now=now))
        self.assertTrue(self.store.is_allowed("192.168.1.5", now=now + 100))
        self.assertFalse(self.store.is_allowed("192.168.1.5", now=now + 4000))

    def test_extend_on_readd(self):
        now = 2_000_000.0
        self.store.add("10.0.0.2", 3600, now=now)
        self.store.add("10.0.0.2", 43200, now=now + 1000)
        entries = self.store.get_active_entries(now=now + 2000)
        self.assertEqual(len(entries), 1)
        self.assertGreater(entries[0]["expires_at"], now + 3600)

    def test_purge_expired(self):
        now = 3_000_000.0
        self.store.add("10.0.0.3", 60, now=now)
        removed = self.store.purge_expired(now=now + 120)
        self.assertEqual(removed, ["10.0.0.3"])
        self.assertFalse(self.store.has_active(now=now + 120))

    def test_remove(self):
        now = 4_000_000.0
        self.store.add("10.0.0.4", 3600, now=now)
        self.assertTrue(self.store.remove("10.0.0.4"))
        self.assertFalse(self.store.is_allowed("10.0.0.4", now=now))


if __name__ == "__main__":
    unittest.main()
