import json
import os
import shutil
import tarfile
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
        os.makedirs(os.path.join(self.app_root, "data"), exist_ok=True)
        with open(os.path.join(self.app_root, "instance", "users.db"), "w", encoding="utf-8") as fh:
            fh.write("db")
        with open(os.path.join(self.app_root, "instance", "site.db"), "w", encoding="utf-8") as fh:
            fh.write("site")
        with open(os.path.join(self.app_root, ".env"), "w", encoding="utf-8") as fh:
            fh.write("KEY=value\n")
        with open(
            os.path.join(self.app_root, "data", "temporary_whitelist.json"),
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump({"version": 1, "entries": {}}, fh)
        self.service = BackupManagerService(
            app_root=self.app_root,
            backup_root=self.backup_root,
            retention_count=5,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_db_candidates_globs_all_sqlite_files(self):
        candidates = self.service._db_candidates()
        names = {os.path.basename(path) for path in candidates}
        self.assertIn("users.db", names)
        self.assertIn("site.db", names)

    def test_create_backup_includes_db_env_data(self):
        result = self.service.create_backup(
            selected_components=["db", "env", "data"],
            trigger="manual",
        )
        self.assertTrue(os.path.isfile(result["archive_path"]))
        backups = self.service.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(set(backups[0]["components"]), {"db", "env", "data"})
        self.assertIn("DATA:", result["metadata"]["summary"])

        with tarfile.open(result["archive_path"], "r:gz") as tar:
            names = tar.getnames()
        arc_prefix = self.app_root.lstrip("/")
        self.assertTrue(any("instance/users.db" in name for name in names))
        self.assertTrue(any(name.endswith(".env") for name in names))
        self.assertTrue(
            any("data/temporary_whitelist.json" in name for name in names),
            names,
        )

    def test_normalize_components_drops_unknown_and_configs(self):
        normalized = self.service.normalize_components(["configs", "db", "data", "db"])
        self.assertEqual(normalized, ["db", "data"])

    def test_default_components(self):
        self.assertEqual(self.service.default_components(), ["db", "env", "data"])

    def test_enrich_backup_list_entry_full_panel(self):
        enriched = self.service.enrich_backup_list_entry(
            {
                "components": ["db", "env", "data"],
                "summary": "DB: 2, ENV: 1, DATA: 1",
                "items_count": 4,
            }
        )
        self.assertTrue(enriched["is_full_panel_backup"])
        self.assertEqual(enriched["content_description"], "Полный бэкап панели для переустановки")
        self.assertIn("файлов БД", enriched["content_detail"])

    def test_enrich_backup_list_entry_legacy(self):
        enriched = self.service.enrich_backup_list_entry(
            {
                "components": ["db"],
                "summary": "Legacy data-only backup",
                "items_count": 3,
            }
        )
        self.assertIn("старый скриптовый", enriched["content_description"])

    def test_prune_old_backups_keeps_max_five(self):
        for _ in range(6):
            self.service.create_backup(
                selected_components=["db"],
                trigger="manual",
            )
        backups = self.service.list_backups()
        self.assertEqual(len(backups), 5)

    def test_delete_backup_removes_archive_and_meta(self):
        result = self.service.create_backup(
            selected_components=["db"],
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
            trigger="manual",
        )
        with patch.object(self.service, "_service_control") as service_control:
            self.service.restore_backup(os.path.basename(result["archive_path"]))
            self.assertEqual(service_control.call_count, 2)


if __name__ == "__main__":
    unittest.main()
