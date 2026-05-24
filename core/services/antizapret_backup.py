import glob
import os
import re
import subprocess
import tarfile


class AntizapretBackupService:
    _BACKUP_STDOUT_RE = re.compile(
        r"recreated at\s+(\S+\.tar\.gz)",
        re.IGNORECASE,
    )

    def __init__(self, *, install_dir="/root/antizapret", timeout_seconds=600):
        self.install_dir = os.path.abspath(install_dir or "/root/antizapret")
        self.timeout_seconds = max(30, int(timeout_seconds or 600))

    def create_backup(self):
        client_sh = os.path.join(self.install_dir, "client.sh")
        if not os.path.isfile(client_sh):
            raise FileNotFoundError(f"client.sh не найден: {client_sh}")
        if not os.access(client_sh, os.X_OK):
            raise PermissionError(f"client.sh не исполняемый: {client_sh}")

        result = subprocess.run(
            [client_sh, "8"],
            cwd=self.install_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"код выхода {result.returncode}"
            raise RuntimeError(f"client.sh 8 завершился с ошибкой: {detail}")

        archive_path = self._resolve_archive_path(result.stdout or "")
        self._verify_archive(archive_path)
        return {
            "archive_path": archive_path,
            "archive_name": os.path.basename(archive_path),
        }

    def _resolve_archive_path(self, stdout):
        for line in (stdout or "").splitlines():
            match = self._BACKUP_STDOUT_RE.search(line)
            if match:
                candidate = match.group(1).strip()
                if os.path.isabs(candidate) and os.path.isfile(candidate):
                    return os.path.abspath(candidate)
                joined = os.path.join(self.install_dir, os.path.basename(candidate))
                if os.path.isfile(joined):
                    return os.path.abspath(joined)

        pattern = os.path.join(self.install_dir, "backup-*.tar.gz")
        candidates = [p for p in glob.glob(pattern) if os.path.isfile(p)]
        if not candidates:
            raise FileNotFoundError(
                f"Архив AntiZapret не найден после client.sh 8 (ожидался {pattern})"
            )
        return os.path.abspath(max(candidates, key=os.path.getmtime))

    def _verify_archive(self, archive_path):
        if not os.path.isfile(archive_path):
            raise FileNotFoundError(f"Файл бэкапа не найден: {archive_path}")
        with tarfile.open(archive_path, "r:gz"):
            pass
