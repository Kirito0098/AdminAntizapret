import os
import shutil
import sqlite3
import tempfile
import unittest

from core.services.db_backup_export import (
    BACKUP_EXCLUDED_TABLES,
    export_sqlite_excluding_tables,
    prepare_db_files_for_backup,
)


class DbBackupExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="db-backup-export-test-")
        self.source_db = os.path.join(self.tmp_dir, "users.db")
        conn = sqlite3.connect(self.source_db)
        try:
            conn.execute(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT NOT NULL)"
            )
            conn.execute("INSERT INTO user (id, username) VALUES (1, 'admin')")
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
                "INSERT INTO provider_cidr (id, provider_key, cidr) VALUES (1, 'google', '1.0.0.0/8')"
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_export_excludes_cidr_tables(self):
        dest_db = os.path.join(self.tmp_dir, "export.db")
        export_sqlite_excluding_tables(self.source_db, dest_db)

        conn = sqlite3.connect(dest_db)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        finally:
            conn.close()

        self.assertIn("user", tables)
        self.assertNotIn("provider_cidr", tables)
        for name in BACKUP_EXCLUDED_TABLES:
            self.assertNotIn(name, tables)

    def test_prepare_skips_wal_shm_when_main_exported(self):
        wal_path = f"{self.source_db}-wal"
        shm_path = f"{self.source_db}-shm"
        open(wal_path, "wb").close()
        open(shm_path, "wb").close()

        prepared, db_without_cidr = prepare_db_files_for_backup(
            [self.source_db, wal_path, shm_path]
        )
        self.assertTrue(db_without_cidr)
        self.assertEqual(len(prepared), 1)
        self.assertTrue(os.path.isfile(prepared[0].file_path))
        self.assertEqual(prepared[0].tar_arcname, os.path.abspath(self.source_db))

        conn = sqlite3.connect(prepared[0].file_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM user").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)
        if prepared[0].cleanup_dir:
            shutil.rmtree(prepared[0].cleanup_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
