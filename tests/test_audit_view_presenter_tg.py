import unittest

from core.services.audit_view_presenter import (
    _format_nightly_update_details,
    user_action_tg_action_line,
)


class AuditViewPresenterTgTests(unittest.TestCase):
    def test_nightly_details_humanized(self):
        text = _format_nightly_update_details(
            "enabled=вкл cron=0 4 * * * ttl=180с touch=29с"
        )
        self.assertIn("включён", text)
        self.assertIn("04:00", text)
        self.assertIn("180", text)
        self.assertIn("29", text)

    def test_tg_action_line_port_arrow(self):
        text = user_action_tg_action_line(
            "settings_port_update",
            details="5050 → 8080",
        )
        self.assertEqual(text, "Порт панели: с 5050 на 8080")


if __name__ == "__main__":
    unittest.main()
