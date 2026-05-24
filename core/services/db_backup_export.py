import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone


BACKUP_EXCLUDED_TABLES = frozenset(
    {
        "provider_cidr",
        "provider_meta",
        "provider_asn",
        "provider_asn_snapshot",
        "cidr_db_refresh_log",
        "cidr_preset",
        "antifilter_cidr",
        "antifilter_meta",
    }
)


@dataclass(frozen=True)
class PreparedDbFile:
    """File to place in the backup archive."""

    file_path: str
    tar_arcname: str
    cleanup_dir: str | None = None


def _is_wal_or_shm(path: str) -> bool:
    name = os.path.basename(path)
    return name.endswith(".db-wal") or name.endswith(".db-shm")


def _main_db_path_for_sidecar(path: str) -> str:
    if path.endswith(".db-wal"):
        return path[: -len("-wal")]
    if path.endswith(".db-shm"):
        return path[: -len("-shm")]
    return path


def export_sqlite_excluding_tables(
    source_path: str,
    dest_path: str,
    *,
    excluded_tables: frozenset[str] | None = None,
) -> None:
    """Copy SQLite schema/data to dest_path, skipping excluded tables and their indexes/triggers."""
    excluded = {name.lower() for name in (excluded_tables or BACKUP_EXCLUDED_TABLES)}
    abs_source = os.path.abspath(source_path)
    if not os.path.isfile(abs_source):
        raise FileNotFoundError(f"База не найдена: {abs_source}")

    if os.path.exists(dest_path):
        os.remove(dest_path)

    dst = sqlite3.connect(dest_path)
    try:
        dst.execute("PRAGMA foreign_keys = OFF")
        dst.execute("ATTACH DATABASE ? AS src", (abs_source,))

        rows = dst.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM src.sqlite_master
            WHERE sql IS NOT NULL
              AND name NOT LIKE 'sqlite_%'
            ORDER BY CASE type
                WHEN 'table' THEN 0
                WHEN 'index' THEN 1
                WHEN 'trigger' THEN 2
                ELSE 3
            END,
            name
            """
        ).fetchall()

        for obj_type, name, tbl_name, sql in rows:
            lname = (name or "").lower()
            ltbl = (tbl_name or "").lower()
            if obj_type == "table" and lname in excluded:
                continue
            if obj_type in {"index", "trigger"} and ltbl in excluded:
                continue
            if not sql:
                continue

            dst.execute(sql)
            if obj_type == "table":
                dst.execute(f'INSERT INTO main."{name}" SELECT * FROM src."{name}"')

        dst.commit()
    finally:
        dst.execute("DETACH src")
        dst.close()


def prepare_db_files_for_backup(db_paths) -> tuple[list[PreparedDbFile], bool]:
    """
    Build backup DB file list: exported snapshots without CIDR tables, no WAL/SHM for those.
    Returns (prepared files, db_without_cidr flag).
    """
    paths = []
    seen = set()
    for raw in db_paths or []:
        abs_path = os.path.abspath(raw)
        if not os.path.isfile(abs_path) or abs_path in seen:
            continue
        seen.add(abs_path)
        paths.append(abs_path)

    main_dbs = [p for p in paths if p.endswith(".db") and not _is_wal_or_shm(p)]
    sidecars = [p for p in paths if _is_wal_or_shm(p)]

    exported_bases: set[str] = set()
    prepared: list[PreparedDbFile] = []
    db_without_cidr = False

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    for index, source_db in enumerate(main_dbs):
        tmp_dir = tempfile.mkdtemp(prefix="panel-db-backup-")
        dest_name = os.path.basename(source_db)
        if index > 0:
            dest_name = f"panel_backup_{stamp}_{index}_{dest_name}"
        dest_path = os.path.join(tmp_dir, dest_name)
        try:
            export_sqlite_excluding_tables(source_db, dest_path)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        prepared.append(
            PreparedDbFile(
                file_path=dest_path,
                tar_arcname=source_db,
                cleanup_dir=tmp_dir,
            )
        )
        exported_bases.add(source_db)
        db_without_cidr = True

    for sidecar in sidecars:
        base = _main_db_path_for_sidecar(sidecar)
        if base in exported_bases:
            continue
        prepared.append(
            PreparedDbFile(
                file_path=sidecar,
                tar_arcname=sidecar,
                cleanup_dir=None,
            )
        )

    return prepared, db_without_cidr
