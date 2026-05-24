import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from utils import app_auto_backup
from core.services import backup_telegram_job


class AppAutoBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="app-auto-backup-test-")
        self.app_root = os.path.join(self.tmp_dir, "app")
        os.makedirs(os.path.join(self.app_root, "instance"), exist_ok=True)
        db_path = os.path.join(self.app_root, "instance", "users.db")
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, role TEXT, telegram_id TEXT)"
            )
            cur.execute("INSERT INTO user (id, role, telegram_id) VALUES (1, 'admin', '111')")
            cur.execute("INSERT INTO user (id, role, telegram_id) VALUES (2, 'admin', '222')")
            cur.execute("INSERT INTO user (id, role, telegram_id) VALUES (3, 'viewer', '333')")
            conn.commit()
        finally:
            conn.close()
        with open(os.path.join(self.app_root, ".env"), "w", encoding="utf-8") as fh:
            fh.write("APP_BACKUP_ENABLED=true\n")
            fh.write("APP_BACKUP_TG_ENABLED=true\n")
            fh.write("APP_BACKUP_AZ_ENABLED=true\n")
            fh.write("APP_BACKUP_TG_ADMIN_IDS=1,2\n")
            fh.write("TELEGRAM_AUTH_BOT_TOKEN=token\n")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_load_admin_chat_ids_filters_selected_admins(self):
        chat_ids = backup_telegram_job.load_admin_chat_ids(self.app_root, ["2"])
        self.assertEqual(chat_ids, ["222"])

    def test_main_sends_panel_and_az_documents(self):
        panel_archive = os.path.join(self.tmp_dir, "panel.tar.gz")
        az_archive = os.path.join(self.tmp_dir, "az.tar.gz")
        with open(panel_archive, "wb") as fh:
            fh.write(b"panel")
        with open(az_archive, "wb") as fh:
            fh.write(b"az")

        fake_backup_service = MagicMock()
        fake_backup_service.create_backup.return_value = {"archive_path": panel_archive}
        fake_az_service = MagicMock()
        fake_az_service.create_backup.return_value = {
            "archive_path": az_archive,
            "archive_name": "backup-1.2.3.4.tar.gz",
        }

        with patch.dict(
            os.environ,
            {
                "APP_BACKUP_ENABLED": "true",
                "APP_BACKUP_TG_ENABLED": "true",
                "APP_BACKUP_AZ_ENABLED": "true",
                "APP_BACKUP_TG_ADMIN_IDS": "1,2",
                "TELEGRAM_AUTH_BOT_TOKEN": "token",
            },
            clear=False,
        ), patch.object(backup_telegram_job, "load_env_map", return_value={
            "APP_BACKUP_ENABLED": "true",
            "APP_BACKUP_TG_ENABLED": "true",
            "APP_BACKUP_AZ_ENABLED": "true",
            "APP_BACKUP_TG_ADMIN_IDS": "1,2",
            "TELEGRAM_AUTH_BOT_TOKEN": "token",
            "APP_BACKUP_ROOT": self.tmp_dir,
            "APP_BACKUP_COMPONENTS": "db",
        }), patch.object(
            backup_telegram_job, "BackupManagerService", return_value=fake_backup_service
        ), patch.object(
            backup_telegram_job, "AntizapretBackupService", return_value=fake_az_service
        ), patch.object(
            backup_telegram_job, "send_tg_document"
        ) as send_tg_document_mock:
            app_auto_backup.main()

        self.assertEqual(send_tg_document_mock.call_count, 4)

    def test_run_backup_job_test_mode_forces_telegram(self):
        panel_archive = os.path.join(self.tmp_dir, "panel.tar.gz")
        with open(panel_archive, "wb") as fh:
            fh.write(b"panel")

        fake_backup_service = MagicMock()
        fake_backup_service.create_backup.return_value = {"archive_path": panel_archive, "archive_name": "p.tar.gz"}

        with patch.object(backup_telegram_job, "load_env_map", return_value={
            "APP_BACKUP_ENABLED": "false",
            "APP_BACKUP_TG_ENABLED": "false",
            "APP_BACKUP_AZ_ENABLED": "false",
            "APP_BACKUP_TG_ADMIN_IDS": "1",
            "TELEGRAM_AUTH_BOT_TOKEN": "token",
            "APP_BACKUP_ROOT": self.tmp_dir,
            "APP_BACKUP_COMPONENTS": "db",
        }), patch.object(
            backup_telegram_job, "BackupManagerService", return_value=fake_backup_service
        ), patch.object(
            backup_telegram_job, "send_tg_document"
        ) as send_tg_document_mock, patch.object(
            backup_telegram_job, "load_admin_chat_ids", return_value=["111"]
        ):
            result = backup_telegram_job.run_backup_job(
                self.app_root,
                trigger="test",
                require_auto_enabled=False,
                send_telegram=True,
            )

        self.assertTrue(result["tg_sent"])
        self.assertEqual(send_tg_document_mock.call_count, 1)
        caption = send_tg_document_mock.call_args.kwargs.get("caption") or (
            send_tg_document_mock.call_args.args[3] if len(send_tg_document_mock.call_args.args) > 3 else ""
        )
        self.assertIn("Тестовый бэкап", caption)


if __name__ == "__main__":
    unittest.main()
