import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask

from routes.settings.api import register_settings_api_routes


class _AuthManagerStub:
    @staticmethod
    def admin_required(fn):
        return fn


class SettingsApiActionLogsExportTests(unittest.TestCase):
    def test_action_logs_export_returns_csv(self):
        app = Flask(__name__)
        app.config["TESTING"] = True

        user_action_log_model = MagicMock()
        user_action_log_model.query.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(
                created_at=datetime(2026, 1, 20, 12, 34, 56),
                actor_username="admin",
                event_type="settings_port_update",
                target_type="settings",
                target_name="APP_PORT",
                status="success",
                details="5050 → 8080",
                remote_addr="198.51.100.11",
            ),
        ]

        register_settings_api_routes(
            app,
            auth_manager=_AuthManagerStub(),
            db=MagicMock(),
            user_model=MagicMock(),
            user_action_log_model=user_action_log_model,
            ip_manager=MagicMock(),
            enqueue_background_task=MagicMock(),
            task_restart_service=MagicMock(),
            set_env_value=MagicMock(),
            get_env_value=MagicMock(return_value=""),
            to_bool=MagicMock(),
            is_valid_cron_expression=MagicMock(return_value=True),
            ensure_nightly_idle_restart_cron=MagicMock(),
            get_nightly_idle_restart_settings=MagicMock(return_value=(False, "0 3 * * *")),
            set_nightly_idle_restart_settings=MagicMock(),
            get_active_web_session_settings=MagicMock(return_value=(300, 60)),
            set_active_web_session_settings=MagicMock(),
            log_telegram_audit_event=MagicMock(),
            log_user_action_event=MagicMock(),
            cidr_db_updater_service=MagicMock(),
        )

        client = app.test_client()
        response = client.get("/api/settings/action-logs/export?status=success")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn("attachment;", response.headers.get("Content-Disposition", ""))
        payload = response.data.decode("utf-8-sig")
        self.assertIn("Дата/время,Пользователь,Действие,IP,Результат,Детали", payload)
        self.assertIn("admin", payload)
        self.assertIn("198.51.100.11", payload)


if __name__ == "__main__":
    unittest.main()
