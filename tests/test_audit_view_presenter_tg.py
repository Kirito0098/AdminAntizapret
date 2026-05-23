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

    def test_tg_action_line_backup_settings_russian(self):
        text = user_action_tg_action_line(
            "settings_backup_update",
            details="enabled=вкл interval=7d time=04:30 components=db,env,data tg=вкл admins=1,2",
        )
        self.assertIn("Авто-бэкап включён", text)
        self.assertIn("каждые 7 дней", text)
        self.assertIn("базы SQLite", text)
        self.assertNotIn("enabled=", text)

    def test_tg_action_line_backup_restore(self):
        text = user_action_tg_action_line(
            "settings_backup_restore",
            target_name="full_backup_20260101.tar.gz",
        )
        self.assertIn("full_backup_20260101.tar.gz", text)
        self.assertIn("Восстановление", text)


if __name__ == "__main__":
    unittest.main()
