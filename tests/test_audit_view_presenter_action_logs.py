import unittest
from datetime import datetime
from types import SimpleNamespace

from core.services.audit_view_presenter import build_user_action_audit_view


class AuditViewPresenterActionLogsTests(unittest.TestCase):
    def test_build_user_action_audit_view_adds_normalized_columns(self):
        rows = [
            SimpleNamespace(
                created_at=datetime(2026, 1, 15, 10, 22, 33),
                actor_username=None,
                event_type="login_failed",
                target_type="auth",
                target_name="admin",
                status="success",
                details="invalid_credentials",
                remote_addr="203.0.113.10",
            )
        ]

        view_rows = build_user_action_audit_view(rows)
        self.assertEqual(len(view_rows), 1)
        row = view_rows[0]

        self.assertEqual(row["actor_display"], "system/anonymous")
        self.assertEqual(row["status"], "warning")
        self.assertEqual(row["status_display"], "Предупреждение")
        self.assertIn("search_blob", row)
        self.assertIn("csv_row", row)
        self.assertEqual(row["csv_row"]["ip"], "203.0.113.10")
        self.assertEqual(row["csv_row"]["username"], "system/anonymous")
        self.assertIn("Неудачная попытка входа", row["csv_row"]["action"])

    def test_build_user_action_audit_view_humanizes_monitor_details(self):
        rows = [
            SimpleNamespace(
                created_at=datetime(2026, 1, 16, 11, 0, 0),
                actor_username="admin",
                event_type="settings_monitor_update",
                target_type="monitor",
                target_name="resource_monitor",
                status="success",
                details="cpu=85% ram=80% interval=60с cooldown=30мин",
                remote_addr="198.51.100.2",
            )
        ]

        row = build_user_action_audit_view(rows)[0]
        self.assertIn("интервал проверки", row["details_display"])
        self.assertIn("пауза уведомлений", row["details_display"])

    def test_build_user_action_audit_view_humanizes_viewer_access_details(self):
        rows = [
            SimpleNamespace(
                created_at=datetime(2026, 1, 16, 12, 0, 0),
                actor_username="admin",
                event_type="settings_viewer_access_grant",
                target_type="openvpn",
                target_name="viewer1",
                status="success",
                details="configs=3 group=group-a",
                remote_addr="198.51.100.3",
            )
        ]

        row = build_user_action_audit_view(rows)[0]
        self.assertIn("Выдан доступ", row["details_display"])
        self.assertIn("3 конфиг", row["details_display"])


if __name__ == "__main__":
    unittest.main()
