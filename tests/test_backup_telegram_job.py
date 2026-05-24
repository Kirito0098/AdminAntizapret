import os
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock

from core.services import backup_telegram_job


class BackupTelegramJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="backup-tg-job-test-")
        self.app_root = os.path.join(self.tmp_dir, "app")
        os.makedirs(self.app_root, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _large_archive(self):
        path = os.path.join(self.tmp_dir, "large.tar.gz")
        # Sparse seek does not count toward Telegram limit checks on all FS; write real bytes.
        chunk = b"x" * (1024 * 1024)
        with open(path, "wb") as fh:
            for _ in range(51):
                fh.write(chunk)
        return path

    def test_build_panel_uses_fallback_when_full_too_large(self):
        large_path = self._large_archive()
        self.assertGreater(os.path.getsize(large_path), backup_telegram_job.TELEGRAM_MAX_DOCUMENT_BYTES)
        panel_result = {"archive_path": large_path, "archive_name": os.path.basename(large_path)}

        small_path = os.path.join(self.tmp_dir, "small.tar.gz")
        with tarfile.open(small_path, "w:gz"):
            pass

        backup_service = MagicMock()
        backup_service.service_name = "admin-antizapret"
        backup_service.create_backup.return_value = {
            "archive_path": small_path,
            "archive_name": "small.tar.gz",
        }

        with unittest.mock.patch.object(
            backup_telegram_job,
            "_create_panel_telegram_fallback_archive",
            return_value=(
                {"archive_path": small_path, "archive_name": "small.tar.gz"},
                os.path.join(self.tmp_dir, "cleanup"),
            ),
        ):
            documents, notices, cleanup_dirs = backup_telegram_job.build_panel_telegram_documents(
                backup_service=backup_service,
                app_root=self.app_root,
                panel_result=panel_result,
                label="Тестовый бэкап",
                created_at="2026-05-24 11:00 UTC",
            )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0][0], small_path)
        self.assertIn("без БД", documents[0][1])
        self.assertTrue(any("50 МБ" in n for n in notices))
        self.assertEqual(len(cleanup_dirs), 1)

    def test_file_fits_telegram(self):
        small = os.path.join(self.tmp_dir, "s.bin")
        with open(small, "wb") as fh:
            fh.write(b"x" * 1024)
        self.assertTrue(backup_telegram_job.file_fits_telegram(small))
        self.assertFalse(backup_telegram_job.file_fits_telegram(self._large_archive()))


if __name__ == "__main__":
    unittest.main()
