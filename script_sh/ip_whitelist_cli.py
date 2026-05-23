#!/usr/bin/env python3
"""CLI управления whitelist IP для adminpanel."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

from utils.ip_restriction import IPRestriction  # noqa: E402
from utils.temporary_whitelist_store import DURATION_LABELS  # noqa: E402


def _default_install_dir() -> str:
    return os.environ.get("INSTALL_DIR", "/opt/AdminAntizapret")


def _restriction(install_dir: str) -> IPRestriction:
    env_path = os.path.join(install_dir, ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    restriction = IPRestriction(env_file_path=env_path)
    restriction._load_from_env()
    return restriction


def _format_remaining(seconds: int) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600} ч"
    if seconds >= 60:
        return f"{seconds // 60} мин"
    return f"{seconds} с"


def cmd_add(args: argparse.Namespace) -> int:
    restriction = _restriction(args.install_dir)
    if restriction.add_ip(args.ip):
        print(f"OK: {args.ip} добавлен в постоянный whitelist")
        return 0
    print("ERROR: неверный формат IP или подсети", file=sys.stderr)
    return 1


def cmd_remove(args: argparse.Namespace) -> int:
    restriction = _restriction(args.install_dir)
    if restriction.remove_ip_any(args.ip):
        print(f"OK: {args.ip} удалён из whitelist")
        return 0
    print("ERROR: IP не найден в whitelist", file=sys.stderr)
    return 1


def cmd_add_temp(args: argparse.Namespace) -> int:
    restriction = _restriction(args.install_dir)
    duration = IPRestriction.parse_duration_label(args.duration)
    if duration is None:
        labels = ", ".join(sorted(DURATION_LABELS))
        print(f"ERROR: укажите --duration ({labels})", file=sys.stderr)
        return 1
    ok, detail = restriction.add_temporary_ip(args.ip, duration)
    if not ok:
        if detail == "disabled":
            print("ERROR: сначала включите IP-ограничения (постоянный whitelist)", file=sys.stderr)
        else:
            print("ERROR: неверный IP (только одиночный адрес, без CIDR)", file=sys.stderr)
        return 1
    print(f"OK: {detail} добавлен на {args.duration}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    restriction = _restriction(args.install_dir)
    enabled = restriction.is_enabled()
    print(f"IP-ограничения: {'включены' if enabled else 'выключены'}")
    permanent = restriction.get_allowed_ips()
    print("\nПостоянные:")
    if permanent:
        for entry in permanent:
            print(f"  {entry}")
    else:
        print("  (пусто)")
    temporary = restriction.get_temporary_whitelist_display()
    print("\nВременные:")
    if temporary:
        for row in temporary:
            rem = _format_remaining(row["remaining_seconds"])
            print(f"  {row['ip']} — осталось {rem} (до {int(row['expires_at'])})")
    else:
        print("  (пусто)")
    return 0


def cmd_purge(args: argparse.Namespace) -> int:
    restriction = _restriction(args.install_dir)
    removed = restriction._temp_whitelist_store.purge_expired()
    if removed:
        restriction.sync_whitelist_port_firewall()
        print(f"OK: удалено истёкших записей: {len(removed)}")
    else:
        print("OK: истёкших записей нет")
    return 0


def main(argv: list[str] | None = None) -> int:
    install_default = _default_install_dir()
    parser = argparse.ArgumentParser(description="Управление whitelist IP AdminAntizapret")
    parser.add_argument("--install-dir", default=install_default)
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="Добавить постоянно")
    add_p.add_argument("ip")
    add_p.set_defaults(func=cmd_add)

    rem_p = sub.add_parser("remove", help="Удалить из постоянного и временного")
    rem_p.add_argument("ip")
    rem_p.set_defaults(func=cmd_remove)

    temp_p = sub.add_parser("add-temp", help="Добавить временно")
    temp_p.add_argument("ip")
    temp_p.add_argument(
        "--duration",
        required=True,
        choices=sorted(DURATION_LABELS.keys()),
    )
    temp_p.set_defaults(func=cmd_add_temp)

    list_p = sub.add_parser("list", help="Показать списки")
    list_p.set_defaults(func=cmd_list)

    purge_p = sub.add_parser("purge", help="Удалить истёкшие временные записи")
    purge_p.set_defaults(func=cmd_purge)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
