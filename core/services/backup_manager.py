import glob
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from core.services.db_backup_export import (
    BACKUP_EXCLUDED_TABLES,
    prepare_db_files_for_backup,
)


class BackupManagerService:
    SUPPORTED_COMPONENTS = ("db", "env", "data")
    _DATA_ENV_KEYS = ("TEMPORARY_WHITELIST_FILE", "SCANNER_BLOCKS_FILE")
    _COMPONENT_ORDER = ("db", "env", "data", "configs")
    _COMPONENT_LABELS = {
        "db": "Базы SQLite",
        "env": "Настройки (.env)",
        "data": "Состояние IP (data/)",
        "configs": "VPN-конфиги",
    }

    def __init__(
        self,
        *,
        app_root,
        backup_root="/var/backups/antizapret",
        service_name="admin-antizapret",
        retention_count=5,
    ):
        self.app_root = os.path.abspath(app_root)
        self.backup_root = os.path.abspath(backup_root)
        self.service_name = service_name
        self.retention_count = max(1, int(retention_count or 5))

    def default_components(self):
        return ["db", "env", "data"]

    def normalize_components(self, components):
        if not components:
            return self.default_components()
        seen = set()
        result = []
        for item in components:
            key = str(item or "").strip().lower()
            if key not in self.SUPPORTED_COMPONENTS or key in seen:
                continue
            seen.add(key)
            result.append(key)
        return result or self.default_components()

    def list_backups(self):
        os.makedirs(self.backup_root, exist_ok=True)
        archive_paths = sorted(
            glob.glob(os.path.join(self.backup_root, "*.tar.gz")),
            key=lambda p: os.path.getmtime(p),
            reverse=True,
        )
        backups = []
        for archive_path in archive_paths:
            try:
                stat = os.stat(archive_path)
            except OSError:
                continue
            metadata = self.read_backup_metadata(archive_path)
            entry = {
                "file_name": os.path.basename(archive_path),
                "file_path": archive_path,
                "size_bytes": int(stat.st_size),
                "created_at": metadata.get("created_at")
                or datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "components": metadata.get("components", []),
                "items_count": int(metadata.get("items_count", 0)),
                "summary": metadata.get("summary", ""),
                "db_without_cidr": bool(metadata.get("db_without_cidr", False)),
            }
            backups.append(self.enrich_backup_list_entry(entry))
        return backups

    def enrich_backup_list_entry(self, entry):
        raw_components = [str(c).strip().lower() for c in (entry.get("components") or []) if str(c).strip()]
        components = []
        seen = set()
        for key in self._COMPONENT_ORDER:
            if key in raw_components and key not in seen:
                seen.add(key)
                components.append(key)
        for key in raw_components:
            if key not in seen:
                seen.add(key)
                components.append(key)

        summary = str(entry.get("summary") or "").strip()
        component_labels = [self._COMPONENT_LABELS[c] for c in components if c in self._COMPONENT_LABELS]
        items_count = int(entry.get("items_count") or 0)

        if summary == "Legacy data-only backup":
            content_description = "Только базы SQLite (старый скриптовый бэкап)"
            if not components:
                components = ["db"]
                component_labels = [self._COMPONENT_LABELS["db"]]
        elif set(components) >= {"db", "env", "data"}:
            if entry.get("db_without_cidr"):
                content_description = "Полный бэкап панели (без базы CIDR провайдеров)"
            else:
                content_description = "Полный бэкап панели для переустановки"
        elif component_labels:
            content_description = " · ".join(component_labels)
        elif items_count > 0:
            content_description = "Состав уточняется по файлам в архиве"
        else:
            content_description = "Состав не определён"

        detail = self._format_summary_detail(summary)
        entry["components"] = components
        entry["component_labels"] = component_labels
        entry["content_description"] = content_description
        entry["content_detail"] = detail
        entry["is_full_panel_backup"] = set(components) >= {"db", "env", "data"}
        return entry

    @classmethod
    def _format_summary_detail(cls, summary):
        if not summary or summary == "Legacy data-only backup":
            return ""
        mapping = {
            "DB": "файлов БД",
            "ENV": "файл .env",
            "DATA": "файлов data/",
            "CONFIGS": "VPN-файлов",
        }
        parts = []
        for chunk in summary.split(","):
            chunk = chunk.strip()
            if ":" not in chunk:
                continue
            key, _, count = chunk.partition(":")
            key = key.strip().upper()
            count = count.strip()
            label = mapping.get(key)
            if label and count.isdigit() and int(count) > 0:
                parts.append(f"{count} {label}")
        return ", ".join(parts) if parts else summary

    def create_backup(self, *, selected_components, trigger="manual"):
        os.makedirs(self.backup_root, exist_ok=True)
        components = self.normalize_components(selected_components)
        file_map, db_prepared, db_without_cidr = self._collect_component_files(components)
        tar_entries = self._build_tar_entries(file_map, db_prepared)
        if not tar_entries:
            raise RuntimeError("Нет файлов для резервного копирования")

        created_at = datetime.now(timezone.utc)
        stamp = created_at.strftime("%Y%m%d_%H%M%S_%f")
        archive_name = f"full_backup_{stamp}.tar.gz"
        archive_path = os.path.join(self.backup_root, archive_name)
        meta_path = os.path.join(self.backup_root, f"full_backup_{stamp}.meta.json")

        cleanup_dirs = [p.cleanup_dir for p in db_prepared if p.cleanup_dir]
        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                for file_path, arcname in tar_entries:
                    tar.add(file_path, arcname=arcname, recursive=False)

            with tarfile.open(archive_path, "r:gz"):
                pass

            metadata = self._build_metadata(
                created_at=created_at,
                archive_name=archive_name,
                components=components,
                file_map=file_map,
                trigger=trigger,
                db_without_cidr=db_without_cidr,
            )
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump(metadata, fh, ensure_ascii=False, indent=2)

            self.prune_old_backups()
            return {
                "archive_path": archive_path,
                "archive_name": archive_name,
                "meta_path": meta_path,
                "metadata": metadata,
            }
        finally:
            for cleanup_dir in cleanup_dirs:
                shutil.rmtree(cleanup_dir, ignore_errors=True)

    def restore_backup(self, backup_name):
        archive_path = self.resolve_backup_path(backup_name)
        if not os.path.isfile(archive_path):
            raise FileNotFoundError(f"Файл бэкапа не найден: {archive_path}")

        self._service_control("stop", allow_failure=True)
        self._safe_extract_archive_to_root(archive_path)
        self._service_control("start", allow_failure=True)
        return {"archive_path": archive_path, "message": "Восстановление завершено"}

    def delete_backup(self, backup_name):
        archive_path = self.resolve_backup_path(backup_name)
        if not os.path.isfile(archive_path):
            raise FileNotFoundError(f"Файл бэкапа не найден: {archive_path}")
        self._remove_backup_files(archive_path)
        return {
            "archive_path": archive_path,
            "archive_name": os.path.basename(archive_path),
            "message": "Бэкап удалён",
        }

    def resolve_backup_path(self, backup_name):
        raw = str(backup_name or "").strip()
        if not raw:
            raise ValueError("Не выбран файл бэкапа")
        if os.path.isabs(raw):
            path = os.path.abspath(raw)
        else:
            path = os.path.abspath(os.path.join(self.backup_root, os.path.basename(raw)))
        if os.path.commonpath([self.backup_root, path]) != self.backup_root:
            raise ValueError("Недопустимый путь к бэкапу")
        return path

    def read_backup_metadata(self, archive_path):
        archive_base = os.path.basename(archive_path)
        prefix = archive_base[:-7] if archive_base.endswith(".tar.gz") else archive_base
        meta_json_path = os.path.join(self.backup_root, f"{prefix}.meta.json")
        if os.path.isfile(meta_json_path):
            try:
                with open(meta_json_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
                return {
                    "created_at": str(meta.get("created_at", "")),
                    "components": list(meta.get("components", [])),
                    "items_count": int(meta.get("items_count", 0)),
                    "summary": str(meta.get("summary", "")),
                    "db_without_cidr": bool(meta.get("db_without_cidr", False)),
                }
            except Exception:
                pass

        meta_txt_path = os.path.join(self.backup_root, f"{prefix}.meta.txt")
        if os.path.isfile(meta_txt_path):
            created_at = ""
            items_count = 0
            try:
                with open(meta_txt_path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        if "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if key == "backup_created_at":
                            created_at = value
                        elif key == "data_items_count":
                            try:
                                items_count = int(value)
                            except (TypeError, ValueError):
                                items_count = 0
            except Exception:
                pass
            return {
                "created_at": created_at,
                "components": ["db"],
                "items_count": items_count,
                "summary": "Legacy data-only backup",
            }

        return self._inspect_tar_summary(archive_path)

    def prune_old_backups(self):
        archive_paths = sorted(
            glob.glob(os.path.join(self.backup_root, "*.tar.gz")),
            key=lambda p: os.path.getmtime(p),
            reverse=True,
        )
        stale = archive_paths[self.retention_count :]
        for archive_path in stale:
            self._remove_backup_files(archive_path)

    def _remove_backup_files(self, archive_path):
        prefix = os.path.basename(archive_path).replace(".tar.gz", "")
        for path in (
            archive_path,
            os.path.join(self.backup_root, f"{prefix}.meta.json"),
            os.path.join(self.backup_root, f"{prefix}.meta.txt"),
        ):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as exc:
                raise RuntimeError(f"Не удалось удалить {path}: {exc}") from exc

    def _db_candidates(self):
        result = []
        for parent in (self.app_root, os.path.join(self.app_root, "instance")):
            if not os.path.isdir(parent):
                continue
            for pattern in ("*.db", "*.db-wal", "*.db-shm"):
                result.extend(glob.glob(os.path.join(parent, pattern)))
        return result

    def _load_env_map(self, env_path):
        env_map = {}
        if not os.path.isfile(env_path):
            return env_map
        with open(env_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env_map[key.strip()] = value.strip().strip("'").strip('"')
        return env_map

    def _data_candidates(self):
        result = []
        data_dir = os.path.join(self.app_root, "data")
        if os.path.isdir(data_dir):
            result.extend(glob.glob(os.path.join(data_dir, "*.json")))
        env_map = self._load_env_map(os.path.join(self.app_root, ".env"))
        for key in self._DATA_ENV_KEYS:
            raw = (env_map.get(key) or os.getenv(key) or "").strip()
            if raw:
                result.append(raw)
        return result

    def _collect_component_files(self, components):
        file_map = {}
        db_prepared = []
        db_without_cidr = False
        if "db" in components:
            db_prepared, db_without_cidr = prepare_db_files_for_backup(
                self._dedupe_existing_paths(self._db_candidates())
            )
            file_map["db"] = [item.file_path for item in db_prepared]
        if "env" in components:
            file_map["env"] = self._dedupe_existing_paths([os.path.join(self.app_root, ".env")])
        if "data" in components:
            file_map["data"] = self._dedupe_existing_paths(self._data_candidates())
        return file_map, db_prepared, db_without_cidr

    def _build_tar_entries(self, file_map, db_prepared):
        arcname_by_path = {item.file_path: self._archive_name(item.tar_arcname) for item in db_prepared}
        entries = []
        seen = set()
        for paths in file_map.values():
            for file_path in paths:
                abs_path = os.path.abspath(file_path)
                if abs_path in seen:
                    continue
                seen.add(abs_path)
                arcname = arcname_by_path.get(abs_path, self._archive_name(abs_path))
                entries.append((abs_path, arcname))
        return entries

    def _dedupe_existing_paths(self, paths):
        seen = set()
        result = []
        for path in paths:
            abs_path = os.path.abspath(path)
            if not os.path.isfile(abs_path) or abs_path in seen:
                continue
            seen.add(abs_path)
            result.append(abs_path)
        return result

    def _archive_name(self, file_path):
        return file_path.lstrip("/") or os.path.basename(file_path)

    def _build_metadata(
        self,
        *,
        created_at,
        archive_name,
        components,
        file_map,
        trigger,
        db_without_cidr=False,
    ):
        counts = {key: len(file_map.get(key, [])) for key in self.SUPPORTED_COMPONENTS}
        db_summary = f"DB: {counts.get('db', 0)}"
        if db_without_cidr:
            db_summary = f"{db_summary} (без CIDR)"
        return {
            "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "archive_name": archive_name,
            "trigger": trigger,
            "components": components,
            "counts": counts,
            "items_count": sum(counts.values()),
            "db_without_cidr": bool(db_without_cidr),
            "db_excluded_tables": sorted(BACKUP_EXCLUDED_TABLES) if db_without_cidr else [],
            "summary": ", ".join(
                [
                    db_summary,
                    f"ENV: {counts.get('env', 0)}",
                    f"DATA: {counts.get('data', 0)}",
                ]
            ),
        }

    def _validate_archive_member(self, member):
        """Отклоняем потенциально опасные member'ы до распаковки.

        Запрещаем symlink/hardlink, device/char/fifo-файлы, абсолютные пути
        и пути с '..' — чтобы распаковка не могла выйти за staging или
        перезаписать произвольные файлы через ссылки.
        """
        member_name = member.name or ""
        if not member_name:
            raise RuntimeError("Бэкап содержит member без имени")
        if member.issym() or member.islnk():
            raise RuntimeError("Бэкап содержит ссылки (symlink/hardlink) — отклонено")
        if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
            raise RuntimeError("Бэкап содержит device/fifo-файлы — отклонено")
        if member_name.startswith("/") or ".." in Path(member_name).parts:
            raise RuntimeError("Бэкап содержит недопустимые пути")
        # Дополнительная защита: имя не должно резолвиться за пределы корня.
        target_path = os.path.abspath(os.path.join("/", member_name))
        if os.path.commonpath([target_path, "/"]) != "/":
            raise RuntimeError("Бэкап содержит путь вне корня")
        return target_path

    def _safe_extract_archive_to_root(self, archive_path):
        """Безопасное восстановление: распаковка в staging, затем копирование.

        Вместо tar.extractall(path="/") сначала проверяем все member'ы,
        распаковываем только обычные файлы/каталоги во временный staging,
        а затем контролируемо копируем их на штатные места. Staging чистится
        в finally.
        """
        staging_dir = tempfile.mkdtemp(prefix="az-restore-", dir="/var/tmp")
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                safe_members = []
                for member in tar.getmembers():
                    self._validate_archive_member(member)
                    if member.isfile() or member.isdir():
                        safe_members.append(member)
                    else:
                        raise RuntimeError(
                            f"Бэкап содержит неподдерживаемый тип записи: {member.name}"
                        )
                # Member'ы уже проверены вручную; дополнительно применяем
                # стандартный фильтр 'data' (Python 3.12+) как defense-in-depth.
                tar.extractall(path=staging_dir, members=safe_members, filter="data")

                for member in safe_members:
                    if not member.isfile():
                        continue
                    relative_name = member.name.lstrip("/")
                    source_path = os.path.join(staging_dir, relative_name)
                    target_path = os.path.abspath(os.path.join("/", relative_name))
                    if os.path.commonpath([target_path, "/"]) != "/":
                        raise RuntimeError("Бэкап содержит путь вне корня")
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    shutil.copy2(source_path, target_path)
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def _service_control(self, action, *, allow_failure):
        cmd = ["systemctl", action, self.service_name]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if allow_failure:
            return
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            raise RuntimeError(stderr or stdout or f"Ошибка команды: {' '.join(cmd)}")

    def _inspect_tar_summary(self, archive_path):
        items_count = 0
        components = set()
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    items_count += 1
                    name = member.name
                    if name.endswith(".env") or name.endswith("/.env"):
                        components.add("env")
                    elif "/etc/openvpn/" in name or "/etc/wireguard/" in name:
                        components.add("configs")
                    elif "/data/" in name and name.endswith(".json"):
                        components.add("data")
                    elif name.endswith(".db") or ".db-" in name:
                        components.add("db")
        except Exception:
            pass
        ordered = [c for c in self._COMPONENT_ORDER if c in components]
        labels = [self._COMPONENT_LABELS[c] for c in ordered if c in self._COMPONENT_LABELS]
        return {
            "created_at": "",
            "components": ordered,
            "items_count": items_count,
            "summary": "; ".join(labels) if labels else "",
        }
