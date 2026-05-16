import unittest
from unittest.mock import MagicMock

from core.services.settings.post_handlers.vpn_network import handle_vpn_network_port
from core.services.settings.telegram_normalize import normalize_telegram_id


class SettingsPostHandlersTests(unittest.TestCase):
    def test_invalid_port_shows_error(self):
        flash = MagicMock()
        form = {"port": "99999"}

        handle_vpn_network_port(
            form,
            flash=flash,
            get_env_value=MagicMock(),
            set_env_value=MagicMock(),
            log_user_action_event=MagicMock(),
        )

        flash.assert_called_once_with(
            "Порт должен быть целым числом в диапазоне 1..65535",
            "error",
        )

    def test_normalize_telegram_id_rejects_leading_zero(self):
        value, error = normalize_telegram_id("012345")
        self.assertIsNone(value)
        self.assertIsNotNone(error)

    def test_normalize_telegram_id_accepts_valid(self):
        value, error = normalize_telegram_id("123456789")
        self.assertEqual(value, "123456789")
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
