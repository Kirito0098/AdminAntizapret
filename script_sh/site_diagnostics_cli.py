#!/usr/bin/env python3
"""CLI диагностики запуска сайта для adminpanel."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.services.site_diagnostics import (  # noqa: E402
    DiagnosticsContext,
    format_report,
    run_site_diagnostics,
)


def _default_install_dir() -> str:
    return os.environ.get("INSTALL_DIR", "/opt/AdminAntizapret")


def cmd_run(args: argparse.Namespace) -> int:
    install_dir = args.install_dir or _default_install_dir()
    service_name = args.service_name or os.environ.get("SERVICE_NAME", "admin-antizapret")
    venv_path = args.venv_path or os.environ.get("VENV_PATH") or os.path.join(install_dir, "venv")

    ctx = DiagnosticsContext(
        install_dir=install_dir,
        service_name=service_name,
        venv_path=venv_path,
    )
    report = run_site_diagnostics(ctx)
    print(format_report(report))
    return 1 if report.has_failures() else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Диагностика запуска AdminAntizapret")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Запустить полную диагностику")
    run_parser.add_argument("--install-dir", default=None)
    run_parser.add_argument("--service-name", default=None)
    run_parser.add_argument("--venv-path", default=None)
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
