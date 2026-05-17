#!/usr/bin/env python3
"""CLI автотестов для adminpanel (без веб-панели)."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.services.system_preflight import (  # noqa: E402
    PreflightContext,
    format_preflight_report,
    run_preflight_checks,
)
from tests.user_labels import enrich_test_nodeids  # noqa: E402

TESTS_DIR = os.path.join(ROOT, "tests")
_STATUS_RE = re.compile(r"\s+(PASSED|FAILED|ERROR|SKIPPED)(?:\s+\[|\s*$)")
_SUMMARY_RE = re.compile(
    r"(?P<passed>\d+) passed"
    r"(?:, (?P<failed>\d+) failed)?"
    r"(?:, (?P<errors>\d+) error)?"
    r"(?:, (?P<skipped>\d+) skipped)?",
    re.I,
)


def _pytest_bin() -> str:
    venv_pytest = os.path.join(ROOT, "venv", "bin", "pytest")
    return venv_pytest if os.path.isfile(venv_pytest) else "pytest"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = ROOT + (":" + existing if existing else "")
    return env


def collect_nodeids() -> list[str]:
    proc = subprocess.run(
        [_pytest_bin(), "--collect-only", "-q", "--no-header", TESTS_DIR],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        env=_subprocess_env(),
    )
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    nodeids: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if "::" not in stripped or stripped.startswith("="):
            continue
        if stripped not in seen:
            seen.add(stripped)
            nodeids.append(stripped)
    if proc.returncode != 0 and not nodeids:
        err = (proc.stderr or proc.stdout or "").strip() or f"pytest exit {proc.returncode}"
        raise RuntimeError(err)
    nodeids.sort()
    return nodeids


def cmd_list() -> int:
    try:
        nodeids = collect_nodeids()
    except RuntimeError as exc:
        print(f"Ошибка сбора тестов: {exc}", file=sys.stderr)
        return 1

    items = enrich_test_nodeids(nodeids)
    current_group = None
    print(f"Всего тестов: {len(items)}\n")
    for index, item in enumerate(items, start=1):
        group = item.get("group") or ""
        if group != current_group:
            current_group = group
            print(f"[{group}]")
        print(f"  {index:3}. {item['title']}")
        print(f"       {item['id']}")
    return 0


def _parse_pytest_summary_line(output: str) -> dict[str, int] | None:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if "passed" not in stripped and "failed" not in stripped:
            continue
        match = _SUMMARY_RE.search(stripped)
        if not match:
            continue
        passed = int(match.group("passed") or 0)
        failed = int(match.group("failed") or 0)
        errors = int(match.group("errors") or 0)
        skipped = int(match.group("skipped") or 0)
        return {
            "passed": passed,
            "failed": failed,
            "error": errors,
            "skipped": skipped,
            "total": passed + failed + errors + skipped,
        }
    return None


def _parse_pytest_verbose_output(output: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    results: list[dict[str, str]] = []
    passed = failed = errors = skipped = 0
    for line in output.splitlines():
        stripped = line.strip()
        if "::" not in stripped:
            continue
        match = _STATUS_RE.search(stripped)
        if not match:
            continue
        status = match.group(1).lower()
        test_id = stripped[: match.start()].strip()
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        elif status == "error":
            errors += 1
        elif status == "skipped":
            skipped += 1
        results.append({"id": test_id, "status": status})

    line_summary = _parse_pytest_summary_line(output)
    if line_summary:
        summary = line_summary
    else:
        summary = {
            "passed": passed,
            "failed": failed,
            "error": errors,
            "skipped": skipped,
            "total": passed + failed + errors + skipped,
        }
    return results, summary


def _print_summary(results: list[dict[str, str]], summary: dict[str, int], *, show_failures: bool) -> None:
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    errors = summary.get("error", 0)
    skipped = summary.get("skipped", 0)
    problems = failed + errors

    print()
    print("─" * 50)
    print(f"Итого: {total}  |  OK: {passed}  |  FAIL: {failed}  |  ERR: {errors}  |  SKIP: {skipped}")
    if problems:
        print(f"С ошибками: {problems}")
    elif total:
        print("Результат: все тесты прошли успешно")
    print("─" * 50)

    if show_failures and problems:
        print("\nУпавшие тесты:")
        items = enrich_test_nodeids([r["id"] for r in results if r["status"] in ("failed", "error")])
        title_by_id = {item["id"]: item["title"] for item in items}
        for row in results:
            if row["status"] not in ("failed", "error"):
                continue
            title = title_by_id.get(row["id"], row["id"])
            print(f"  ✗ {title}")
            print(f"    {row['id']}")


def cmd_run(nodeids: list[str], *, quiet: bool) -> int:
    if not nodeids:
        print("Не указаны тесты для запуска.", file=sys.stderr)
        return 1

    if quiet:
        print(f"Запуск {len(nodeids)} тест(ов)…", flush=True)
    else:
        print(f"Запуск {len(nodeids)} тест(ов)…\n", flush=True)

    proc = subprocess.run(
        [
            _pytest_bin(),
            "-v",
            "--tb=short",
            "--no-header",
            "--color=yes" if sys.stdout.isatty() else "--color=no",
            *nodeids,
        ],
        cwd=ROOT,
        env=_subprocess_env(),
        text=True,
        capture_output=quiet,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if not quiet:
        return int(proc.returncode or 0)

    results, summary = _parse_pytest_verbose_output(output)
    _print_summary(results, summary, show_failures=True)
    return int(proc.returncode or 0)


def _preflight_context() -> PreflightContext:
    install_dir = os.environ.get("INSTALL_DIR", ROOT)
    venv_path = os.environ.get("VENV_PATH") or os.path.join(install_dir, "venv")
    db_file = os.environ.get("DB_FILE") or os.path.join(install_dir, "instance", "users.db")
    return PreflightContext(
        install_dir=install_dir,
        venv_path=venv_path,
        service_name=os.environ.get("SERVICE_NAME", "admin-antizapret"),
        db_file=db_file,
        antizapret_install_dir=os.environ.get("ANTIZAPRET_INSTALL_DIR", "/root/antizapret"),
        include_dir=os.environ.get("INCLUDE_DIR") or os.path.join(install_dir, "script_sh"),
    )


def cmd_summary() -> int:
    """Общий тест: окружение/модули/права + pytest (краткий отчёт)."""
    sep = "─" * 50
    print(sep)
    print("1) Окружение, модули и доступы")
    print(sep)
    preflight = run_preflight_checks(_preflight_context())
    print(format_preflight_report(preflight))
    print()

    print(sep)
    print("2) Автотесты (pytest)")
    print(sep)
    try:
        all_nodeids = collect_nodeids()
    except RuntimeError as exc:
        print(f"Ошибка сбора тестов: {exc}", file=sys.stderr)
        pytest_code = 1
    else:
        pytest_code = cmd_run(all_nodeids, quiet=True)
        pytest_summary = {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}

    print()
    print(sep)
    print("ИТОГ общего теста")
    print(sep)
    print(
        f"  Окружение:  OK={preflight.ok_count}  "
        f"предупреждений={preflight.warn_count}  ошибок={preflight.fail_count}"
    )
    problems = preflight.fail_count + (1 if pytest_code != 0 else 0)
    if preflight.has_failures():
        print("  Окружение: есть критические ошибки — устраните перед работой")
    elif preflight.warn_count:
        print("  Окружение: есть предупреждения (сервис/AntiZapret)")

    if pytest_code == 0:
        print("  Автотесты:  все прошли")
    else:
        print("  Автотесты:  есть упавшие тесты")

    if problems:
        print("\n  Результат: НЕ ПРОЙДЕН")
        return 1
    if preflight.warn_count:
        print("\n  Результат: ПРОЙДЕН с предупреждениями")
    else:
        print("\n  Результат: ВСЁ В ПОРЯДКЕ")
    return 0


def _resolve_nodeids_by_index(numbers: list[int], all_nodeids: list[str]) -> list[str]:
    selected: list[str] = []
    for num in numbers:
        if num < 1 or num > len(all_nodeids):
            raise ValueError(f"Номер вне диапазона: {num} (доступно 1–{len(all_nodeids)})")
        selected.append(all_nodeids[num - 1])
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Автотесты AdminAntizapret (pytest)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Список тестов с понятными названиями")
    sub.add_parser(
        "summary",
        help="Общий тест: окружение, модули, права и все pytest-тесты",
    )

    run_parser = sub.add_parser("run", help="Запуск тестов")
    run_group = run_parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--all", action="store_true", help="Запустить все тесты")
    run_group.add_argument(
        "--index",
        action="append",
        type=int,
        dest="indexes",
        metavar="N",
        help="Номер теста из list (можно указать несколько раз)",
    )
    run_group.add_argument(
        "--nodeid",
        action="append",
        dest="nodeids",
        metavar="ID",
        help="Pytest node id",
    )
    run_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Краткий вывод и сводка в конце",
    )

    args = parser.parse_args(argv)

    if args.command == "list":
        return cmd_list()

    if args.command == "summary":
        return cmd_summary()

    try:
        all_nodeids = collect_nodeids()
    except RuntimeError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    if args.all:
        targets = all_nodeids
    elif args.nodeids:
        targets = list(args.nodeids)
    elif args.indexes:
        try:
            targets = _resolve_nodeids_by_index(args.indexes, all_nodeids)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        print("Укажите --all, --index или --nodeid", file=sys.stderr)
        return 1

    return cmd_run(targets, quiet=bool(args.quiet))


if __name__ == "__main__":
    raise SystemExit(main())
