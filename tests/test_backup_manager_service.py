import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from core.services.backup_manager import BackupManagerService


def _write_test_sqlite(path, *, with_cidr=False):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO user (id, username) VALUES (1, 'testadmin')")
        if with_cidr:
            conn.execute(
                """
                CREATE TABLE provider_cidr (
                    id INTEGER PRIMARY KEY,
                    provider_key TEXT NOT NULL,
                    cidr TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO provider_cidr (id, provider_key, cidr) VALUES (1, 'google', '10.0.0.0/8')"
            )
        conn.commit()
    finally:
        conn.close()


class BackupManagerServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="backup-manager-test-")
        self.app_root = os.path.join(self.tmp_dir, "app")
        self.backup_root = os.path.join(self.tmp_dir, "backups")
        os.makedirs(self.app_root, exist_ok=True)
        os.makedirs(os.path.join(self.app_root, "instance"), exist_ok=True)
        os.makedirs(os.path.join(self.app_root, "data"), exist_ok=True)
        _write_test_sqlite(os.path.join(self.app_root, "instance", "users.db"), with_cidr=True)
        _write_test_sqlite(os.path.join(self.app_root, "instance", "site.db"), with_cidr=False)
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
        self.assertTrue(result["metadata"].get("db_without_cidr"))
        self.assertIn("без CIDR", result["metadata"]["summary"])

        with tarfile.open(result["archive_path"], "r:gz") as tar:
            names = tar.getnames()
        self.assertTrue(any("instance/users.db" in name for name in names))

    def test_create_backup_archive_db_has_no_cidr_tables(self):
        result = self.service.create_backup(
            selected_components=["db"],
            trigger="manual",
        )
        extract_dir = os.path.join(self.tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with tarfile.open(result["archive_path"], "r:gz") as tar:
            tar.extractall(extract_dir)
        db_rel = os.path.join(self.app_root, "instance", "users.db").lstrip("/")
        backed_up_db = os.path.join(extract_dir, db_rel)
        self.assertTrue(os.path.isfile(backed_up_db))

        conn = sqlite3.connect(backed_up_db)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            self.assertIn("user", tables)
            self.assertNotIn("provider_cidr", tables)
        finally:
            conn.close()

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

    def test_enrich_backup_list_entry_without_cidr(self):
        enriched = self.service.enrich_backup_list_entry(
            {
                "components": ["db", "env", "data"],
                "summary": "DB: 1 (без CIDR), ENV: 1, DATA: 1",
                "items_count": 3,
                "db_without_cidr": True,
            }
        )
        self.assertIn("без базы CIDR", enriched["content_description"])

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
