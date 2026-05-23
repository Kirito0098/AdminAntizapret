import unittest
from datetime import datetime, timedelta

from core.services.access_remaining import format_access_remaining


class AccessRemainingTests(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(format_access_remaining(None))

    def test_ten_days_left(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = now + timedelta(days=10, hours=2)
        self.assertEqual(format_access_remaining(expires, now=now), "10 дн.")

    def test_less_than_24_hours_shows_hours_and_minutes(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = now + timedelta(hours=5, minutes=30)
        self.assertEqual(format_access_remaining(expires, now=now), "5 ч. 30 мин.")

    def test_23_hours_59_minutes(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = now + timedelta(hours=23, minutes=59)
        self.assertEqual(format_access_remaining(expires, now=now), "23 ч. 59 мин.")

    def test_one_hour_only(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = now + timedelta(hours=1)
        self.assertEqual(format_access_remaining(expires, now=now), "1 ч.")

    def test_minutes_only(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = now + timedelta(minutes=45)
        self.assertEqual(format_access_remaining(expires, now=now), "45 мин.")

    def test_expired_two_hours_ago(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = now - timedelta(hours=2)
        self.assertEqual(format_access_remaining(expires, now=now), "срок истёк")

    def test_parses_string_expires_at(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = "2026-05-19 15:30:00"
        self.assertEqual(format_access_remaining(expires, now=now), "5 ч. 30 мин.")

    def test_parses_openvpn_utc_string(self):
        now = datetime(2026, 5, 19, 10, 0, 0)
        expires = "2026-05-19 15:00 UTC"
        self.assertEqual(format_access_remaining(expires, now=now), "5 ч.")


if __name__ == "__main__":
    unittest.main()
