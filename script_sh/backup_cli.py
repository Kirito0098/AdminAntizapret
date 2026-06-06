#!/usr/bin/env python3
"""CLI резервного копирования панели через BackupManagerService."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.services.backup_manager import BackupManagerService  # noqa: E402
from core.services.backup_telegram_job import env_value, load_env_map  # noqa: E402


def _default_install_dir() -> str:
    return os.environ.get("INSTALL_DIR", "/opt/AdminAntizapret")


def _build_service(install_dir: str) -> BackupManagerService:
    install_dir = os.path.abspath(install_dir)
    env_map = load_env_map(os.path.join(install_dir, ".env"))
    return BackupManagerService(
        app_root=install_dir,
        backup_root=env_value(env_map, "APP_BACKUP_ROOT", "/var/backups/antizapret"),
        service_name=env_value(env_map, "APP_BACKUP_SERVICE_NAME", "admin-antizapret"),
        retention_count=5,
    )


def _default_components(install_dir: str) -> list[str]:
    env_map = load_env_map(os.path.join(install_dir, ".env"))
    components_csv = env_value(env_map, "APP_BACKUP_COMPONENTS", "db,env,data")
    return [item.strip().lower() for item in components_csv.split(",") if item.strip()]


def cmd_create(args: argparse.Namespace) -> int:
    install_dir = os.path.abspath(args.install_dir)
    service = _build_service(install_dir)
    components = (
        [item.strip().lower() for item in args.components.split(",") if item.strip()]
        if args.components
        else _default_components(install_dir)
    )
    service._service_control("stop", allow_failure=True)
    try:
        result = service.create_backup(
            selected_components=components,
            trigger=args.trigger,
        )
        print(result.get("archive_path", ""))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        service._service_control("start", allow_failure=True)


def cmd_restore(args: argparse.Namespace) -> int:
    service = _build_service(args.install_dir)
    try:
        result = service.restore_backup(args.backup_name)
        print(result.get("archive_path", ""))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Резервное копирование панели AdminAntizapret")
    parser.add_argument(
        "--install-dir",
        default=_default_install_dir(),
        help="Корень установки панели",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Создать бэкап")
    create_parser.add_argument(
        "--components",
        default="",
        help="Компоненты через запятую (db,env,data); по умолчанию из .env",
    )
    create_parser.add_argument(
        "--trigger",
        default="manual",
        help="Метка источника бэкапа (manual, auto, …)",
    )
    create_parser.set_defaults(func=cmd_create)

    restore_parser = subparsers.add_parser("restore", help="Восстановить из бэкапа")
    restore_parser.add_argument(
        "backup_name",
        help="Имя файла или абсолютный путь к архиву .tar.gz",
    )
    restore_parser.set_defaults(func=cmd_restore)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
