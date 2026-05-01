import unittest
from dataclasses import dataclass
from datetime import datetime

from core.services.audit_view_presenter import (
    build_telegram_mini_audit_view,
    build_user_action_audit_view,
)


@dataclass
class MiniAuditRow:
    created_at: datetime
    actor_username: str
    telegram_id: str
    event_type: str
    config_name: str
    details: str


@dataclass
class UserActionRow:
    created_at: datetime
    actor_username: str
    event_type: str
    target_type: str
    target_name: str
    details: str
    status: str = "success"
    remote_addr: str | None = None


class AuditViewPresenterTests(unittest.TestCase):
    def test_build_telegram_mini_audit_view_formats_mini_send_config(self) -> None:
        rows = [
            MiniAuditRow(
                created_at=datetime.utcnow(),
                actor_username="admin",
                telegram_id="123456",
                event_type="mini_send_config",
                config_name="vpn-user.conf",
                details="kind=wg",
            )
        ]

        result = build_telegram_mini_audit_view(rows)
        self.assertEqual(len(result), 1)
        self.assertIn("WireGuard", result[0]["details_label"])
        self.assertIn("vpn-user.conf", result[0]["event_display"])

    def test_build_user_action_audit_view_marks_miniapp_source(self) -> None:
        rows = [
            UserActionRow(
                created_at=datetime.utcnow(),
                actor_username="admin",
                event_type="config_create",
                target_type="openvpn",
                target_name="client-1",
                details="via=tg-mini option=1",
            )
        ]

        result = build_user_action_audit_view(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_kind"], "miniapp")
        self.assertTrue(result[0]["is_miniapp"])


if __name__ == "__main__":
    unittest.main()
