import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from utils import app_auto_backup


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
            fh.write("APP_BACKUP_TG_ADMIN_IDS=1,2\n")
            fh.write("TELEGRAM_AUTH_BOT_TOKEN=token\n")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_load_admin_chat_ids_filters_selected_admins(self):
        chat_ids = app_auto_backup._load_admin_chat_ids(self.app_root, ["2"])
        self.assertEqual(chat_ids, ["222"])

    def test_main_sends_documents_to_selected_admins(self):
        archive_path = os.path.join(self.tmp_dir, "backup.tar.gz")
        with open(archive_path, "wb") as fh:
            fh.write(b"ok")

        fake_backup_service = MagicMock()
        fake_backup_service.create_backup.return_value = {"archive_path": archive_path}

        with patch.object(app_auto_backup, "APP_ROOT", self.app_root), patch.object(
            app_auto_backup, "BackupManagerService", return_value=fake_backup_service
        ), patch.object(app_auto_backup, "_collect_config_paths", return_value=[]), patch.object(
            app_auto_backup, "send_tg_document"
        ) as send_tg_document_mock:
            code = app_auto_backup.main()

        self.assertEqual(code, 0)
        self.assertEqual(send_tg_document_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
