import unittest
from unittest.mock import MagicMock

from core.services.settings.post_handlers.maintenance import (
    handle_backup_delete,
    handle_backup_settings,
)
from core.services.settings.post_handlers.vpn_network import handle_vpn_network_port
from core.services.settings.telegram_normalize import normalize_telegram_id


class SettingsPostHandlersTests(unittest.TestCase):
    def test_invalid_port_shows_error(self):
        flash = MagicMock()
        form = {"port": "99999"}

        handle_vpn_network_port(
            form,
            flash=flash,
            get_env_value=lambda _key, default=None: default,
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

    def test_backup_settings_reject_invalid_interval(self):
        flash = MagicMock()
        form = {
            "backup_settings_action": "save",
            "app_backup_enabled": "true",
            "app_backup_interval_days": "2",
            "app_backup_time_hhmm": "03:00",
        }
        handle_backup_settings(
            form,
            flash=flash,
            to_bool=lambda value, default=False: str(value).lower() == "true",
            set_backup_settings=MagicMock(),
            set_env_value=MagicMock(),
            ensure_app_backup_cron=MagicMock(return_value=(True, "ok")),
            log_user_action_event=MagicMock(),
        )
        flash.assert_called_once_with("Интервал авто-бэкапа должен быть 1, 7 или 30 дней", "error")

    def test_backup_settings_save_success(self):
        flash = MagicMock()
        set_backup_settings = MagicMock()
        set_env_value = MagicMock()
        ensure_app_backup_cron = MagicMock(return_value=(True, "ok"))
        log_user_action_event = MagicMock()

        class _Form(dict):
            def getlist(self, key):
                values = {
                    "app_backup_components": ["db", "env", "data"],
                    "app_backup_tg_admin_ids": ["1", "x", "2"],
                }
                return values.get(key, [])

        form = _Form(
            backup_settings_action="save",
            app_backup_enabled="true",
            app_backup_interval_days="7",
            app_backup_time_hhmm="04:30",
            app_backup_tg_enabled="true",
        )

        handle_backup_settings(
            form,
            flash=flash,
            to_bool=lambda value, default=False: str(value).lower() == "true",
            set_backup_settings=set_backup_settings,
            set_env_value=set_env_value,
            ensure_app_backup_cron=ensure_app_backup_cron,
            log_user_action_event=log_user_action_event,
        )

        set_backup_settings.assert_called_once()
        ensure_app_backup_cron.assert_called_once()
        self.assertTrue(any(call.args[0] == "APP_BACKUP_INTERVAL_DAYS" for call in set_env_value.call_args_list))
        flash.assert_any_call("Настройки авто-бэкапов сохранены", "success")
        log_user_action_event.assert_called_once()

    def test_backup_delete_success(self):
        flash = MagicMock()
        backup_manager_service = MagicMock()
        log_user_action_event = MagicMock()
        form = {
            "backup_delete_action": "delete",
            "backup_file_name": "full_backup_20260101.tar.gz",
        }
        handle_backup_delete(
            form,
            flash=flash,
            backup_manager_service=backup_manager_service,
            log_user_action_event=log_user_action_event,
        )
        backup_manager_service.delete_backup.assert_called_once_with("full_backup_20260101.tar.gz")
        flash.assert_called_once_with(
            "Бэкап удалён: full_backup_20260101.tar.gz",
            "success",
        )
        log_user_action_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
