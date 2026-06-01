import re
import unittest
from unittest.mock import MagicMock

from core.services.admin_notify import AdminNotifyService


class AdminNotifyTextTests(unittest.TestCase):
    def setUp(self):
        self.service = AdminNotifyService(
            user_model=MagicMock(),
            get_env_value=lambda _key, default="": default,
            logger=MagicMock(),
        )

    def _build(self, event_type, **kwargs):
        return self.service._build_text(
            event_type,
            kwargs.get("actor_username"),
            kwargs.get("target_name"),
            kwargs.get("target_type"),
            kwargs.get("remote_addr"),
            kwargs.get("details"),
            kwargs.get("subject_name"),
            client_timezone=kwargs.get("client_timezone"),
        )

    def _lines(self, text):
        return (text or "").split("\n")

    def test_config_delete_four_line_layout(self):
        text = self._build(
            "config_delete",
            actor_username="Claymore",
            target_name="Test",
            target_type="openvpn",
        )
        self.assertIsNotNone(text)
        lines = self._lines(text)
        self.assertEqual(len(lines), 4)
        self.assertIn("🗑️", lines[0])
        self.assertIn("Удаление конфига", lines[0])
        self.assertIn("👨‍💼", lines[1])
        self.assertIn("<code>Claymore</code>", lines[1])
        self.assertNotIn("удалил", lines[1].lower())
        self.assertTrue(lines[2].startswith("Удалил"))
        self.assertIn("🔐", lines[2])
        self.assertIn("OpenVPN", lines[2])
        self.assertIn("📁", lines[2])
        self.assertIn("<code>Test</code>", lines[2])
        self.assertRegex(lines[3], r"^🕐 \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$")

    def test_settings_change_uses_client_timezone(self):
        text = self._build(
            "settings_change",
            actor_username="admin1",
            subject_name="settings_backup_test_telegram",
            client_timezone="Europe/Moscow",
        )
        lines = self._lines(text)
        self.assertRegex(lines[3], r"^🕐 \d{4}-\d{2}-\d{2} \d{2}:\d{2} ")
        self.assertNotRegex(lines[3], r" UTC$")

    def test_config_create_openvpn_narrative(self):
        text = self._build(
            "config_create",
            actor_username="admin1",
            target_name="client-a",
            target_type="openvpn",
        )
        self.assertIsNotNone(text)
        lines = self._lines(text)
        self.assertEqual(len(lines), 4)
        self.assertIn("✨", lines[0])
        self.assertTrue(lines[2].startswith("Создал"))
        self.assertIn("🔐", lines[2])
        self.assertIn("<code>client-a</code>", lines[2])

    def test_login_success_four_line_layout(self):
        text = self._build(
            "login_success",
            actor_username="viewer1",
            remote_addr="203.0.113.10",
        )
        self.assertIsNotNone(text)
        lines = self._lines(text)
        self.assertEqual(len(lines), 4)
        self.assertIn("👤", lines[1])
        self.assertIn("Вошёл", lines[2])
        self.assertIn("🌐", lines[2])
        self.assertIn("<code>203.0.113.10</code>", lines[2])

    def test_client_ban_temp_permanent_and_unblock(self):
        temp = self._build(
            "client_ban",
            actor_username="Claymore",
            target_name="Test",
            target_type="wireguard",
            details="action=temp_block days=7 block_until=2026-05-30 09:13:00",
        )
        permanent = self._build(
            "client_ban",
            actor_username="Claymore",
            target_name="Test",
            target_type="wireguard",
            details="action=permanent_block",
        )
        unblocked = self._build(
            "client_ban",
            actor_username="Claymore",
            target_name="Test",
            target_type="wireguard",
            details="action=unblock",
        )
        for text in (temp, permanent, unblocked):
            self.assertEqual(len(self._lines(text)), 4)

        self.assertIn("⏱️", temp)
        self.assertTrue(self._lines(temp)[2].startswith("Временно"))
        self.assertIn("на 7 дн.", temp)
        self.assertIn("2026-05-30", temp)
        self.assertIn("🛡️", temp)
        self.assertIn("WireGuard", temp)

        self.assertIn("Постоянная блокировка", permanent)
        self.assertIn("бессрочно", self._lines(permanent)[2])

        self.assertIn("🟢", unblocked)
        self.assertTrue(self._lines(unblocked)[2].startswith("Разблокировал"))

    def test_client_ban_legacy_blocked_flags(self):
        blocked = self._build(
            "client_ban",
            actor_username="admin",
            target_name="vpn-user",
            details="blocked=1",
        )
        unblocked = self._build(
            "client_ban",
            actor_username="admin",
            target_name="vpn-user",
            details="blocked=0",
        )
        self.assertIn("Постоянная блокировка", blocked)
        self.assertTrue(self._lines(unblocked)[2].startswith("Разблокировал"))

    def test_settings_change_nightly_russian(self):
        text = self._build(
            "settings_change",
            actor_username="Claymore",
            target_name="settings_nightly_update",
            details="enabled=вкл cron=0 4 * * * ttl=180с touch=29с",
        )
        lines = self._lines(text)
        self.assertEqual(len(lines), 4)
        self.assertIn("Ночной рестарт", lines[0])
        self.assertIn("включён", lines[2])
        self.assertIn("04:00", lines[2])
        self.assertIn("180", lines[2])
        self.assertIn("29", lines[2])
        self.assertNotIn("enabled=", text)
        self.assertNotIn("cron=", text)

    def test_settings_change_port_russian(self):
        text = self._build(
            "settings_change",
            actor_username="Claymore",
            target_name="settings_port_update",
            details="5050 → 8080",
        )
        lines = self._lines(text)
        self.assertEqual(len(lines), 4)
        self.assertIn("Порт панели", lines[0])
        self.assertIn("с 5050 на 8080", lines[2])

    def test_settings_change_games_routes_sync_russian(self):
        text = self._build(
            "settings_change",
            actor_username="Claymore",
            target_name="settings_cidr_games_routes_sync",
            details=(
                "include_games=2 include_cidrs=42 include_domains=0 include_overlap=0 "
                "exclude_games=1 exclude_cidrs=10 exclude_domains=0 exclude_overlap=0"
            ),
        )
        lines = self._lines(text)
        self.assertEqual(len(lines), 4)
        self.assertIn("Игровые маршруты", lines[0])
        self.assertIn("VPN: 2 игр, 42 CIDR", lines[2])
        self.assertIn("DIRECT: 1 игр, 10 CIDR", lines[2])
        self.assertNotIn("игр: 0", text)

    def test_settings_change_games_sync_skips_zero_counts(self):
        text = self._build(
            "settings_change",
            actor_username="Claymore",
            target_name="settings_cidr_games_sync",
            details="selected_games=0 domains=0 cidrs=0 overlap=0",
        )
        lines = self._lines(text)
        self.assertIn("VPN: фильтры очищены", lines[2])
        self.assertNotIn("игр: 0", text)


if __name__ == "__main__":
    unittest.main()
