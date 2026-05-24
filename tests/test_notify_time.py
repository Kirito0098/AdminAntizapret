import unittest

from core.services.notify_time import format_notify_when, _normalize_timezone_name


class NotifyTimeTests(unittest.TestCase):
    def test_normalize_timezone_valid(self):
        self.assertEqual(_normalize_timezone_name("Europe/Moscow"), "Europe/Moscow")

    def test_normalize_timezone_invalid(self):
        self.assertIsNone(_normalize_timezone_name("Not/A/Zone"))

    def test_format_notify_when_utc_fallback(self):
        text = format_notify_when(None)
        self.assertRegex(text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$")

    def test_format_notify_when_client_zone(self):
        text = format_notify_when("Europe/Moscow")
        self.assertRegex(text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} ")
        self.assertNotRegex(text, r" UTC$")


if __name__ == "__main__":
    unittest.main()
