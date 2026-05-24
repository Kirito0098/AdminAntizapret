import os
import shutil
import stat
import tarfile
import tempfile
import unittest
from core.services.antizapret_backup import AntizapretBackupService


class AntizapretBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="az-backup-test-")
        self.install_dir = os.path.join(self.tmp_dir, "antizapret")
        os.makedirs(self.install_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_fake_client_sh(self, *, archive_name="backup-10.0.0.1.tar.gz", exit_code=0):
        archive_path = os.path.join(self.install_dir, archive_name)
        script_path = os.path.join(self.install_dir, "client.sh")
        stub_dir = os.path.join(self.install_dir, "_stub")
        script = f"""#!/bin/bash
set -e
ARCHIVE="{archive_path}"
STUB="{stub_dir}"
mkdir -p "$STUB" "$(dirname "$ARCHIVE")"
echo stub > "$STUB/marker.txt"
tar -czf "$ARCHIVE" -C "$STUB" .
echo "Backup configuration and clients (re)created at $ARCHIVE"
exit {exit_code}
"""
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(script)
        os.chmod(script_path, stat.S_IRWXU)

    def test_resolve_archive_from_stdout(self):
        archive_path = os.path.join(self.install_dir, "backup-1.2.3.4.tar.gz")
        with tarfile.open(archive_path, "w:gz"):
            pass
        service = AntizapretBackupService(install_dir=self.install_dir)
        resolved = service._resolve_archive_path(
            f"Backup configuration and clients (re)created at {archive_path}\n"
        )
        self.assertEqual(resolved, os.path.abspath(archive_path))

    def test_resolve_archive_newest_glob(self):
        older = os.path.join(self.install_dir, "backup-old.tar.gz")
        newer = os.path.join(self.install_dir, "backup-new.tar.gz")
        for path in (older, newer):
            with tarfile.open(path, "w:gz"):
                pass
        os.utime(older, (1, 1))
        os.utime(newer, (2, 2))
        service = AntizapretBackupService(install_dir=self.install_dir)
        resolved = service._resolve_archive_path("")
        self.assertEqual(resolved, os.path.abspath(newer))

    def test_create_backup_runs_client_sh(self):
        self._write_fake_client_sh()
        service = AntizapretBackupService(install_dir=self.install_dir, timeout_seconds=30)
        result = service.create_backup()
        self.assertTrue(os.path.isfile(result["archive_path"]))
        self.assertEqual(result["archive_name"], "backup-10.0.0.1.tar.gz")

    def test_create_backup_raises_on_script_failure(self):
        self._write_fake_client_sh(exit_code=1)
        service = AntizapretBackupService(install_dir=self.install_dir, timeout_seconds=30)
        with self.assertRaises(RuntimeError):
            service.create_backup()

    def test_create_backup_missing_client_sh(self):
        service = AntizapretBackupService(install_dir=self.install_dir)
        with self.assertRaises(FileNotFoundError):
            service.create_backup()


if __name__ == "__main__":
    unittest.main()
