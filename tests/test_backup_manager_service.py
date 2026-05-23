import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core.services.backup_manager import BackupManagerService


class BackupManagerServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="backup-manager-test-")
        self.app_root = os.path.join(self.tmp_dir, "app")
        self.backup_root = os.path.join(self.tmp_dir, "backups")
        os.makedirs(self.app_root, exist_ok=True)
        os.makedirs(os.path.join(self.app_root, "instance"), exist_ok=True)
        with open(os.path.join(self.app_root, "instance", "users.db"), "w", encoding="utf-8") as fh:
            fh.write("db")
        with open(os.path.join(self.app_root, ".env"), "w", encoding="utf-8") as fh:
            fh.write("KEY=value\n")
        self.config_file = os.path.join(self.tmp_dir, "client.ovpn")
        with open(self.config_file, "w", encoding="utf-8") as fh:
            fh.write("ovpn")
        self.service = BackupManagerService(
            app_root=self.app_root,
            backup_root=self.backup_root,
            retention_count=5,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_backup_and_list(self):
        result = self.service.create_backup(
            selected_components=["db", "env", "configs"],
            config_paths=[self.config_file],
            trigger="manual",
        )
        self.assertTrue(os.path.isfile(result["archive_path"]))
        backups = self.service.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertIn("db", backups[0]["components"])

    def test_prune_old_backups_keeps_max_five(self):
        for _ in range(6):
            self.service.create_backup(
                selected_components=["db"],
                config_paths=[],
                trigger="manual",
            )
        backups = self.service.list_backups()
        self.assertEqual(len(backups), 5)

    def test_delete_backup_removes_archive_and_meta(self):
        result = self.service.create_backup(
            selected_components=["db"],
            config_paths=[],
            trigger="manual",
        )
        archive_path = result["archive_path"]
        meta_path = result["meta_path"]
        self.assertTrue(os.path.isfile(archive_path))
        self.service.delete_backup(os.path.basename(archive_path))
        self.assertFalse(os.path.isfile(archive_path))
        self.assertFalse(os.path.isfile(meta_path))

    def test_restore_backup_runs_service_control(self):
        result = self.service.create_backup(
            selected_components=["db"],
            config_paths=[],
            trigger="manual",
        )
        with patch.object(self.service, "_service_control") as service_control:
            self.service.restore_backup(os.path.basename(result["archive_path"]))
            self.assertEqual(service_control.call_count, 2)


if __name__ == "__main__":
    unittest.main()
