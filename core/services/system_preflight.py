"""Неблокирующая проверка окружения для общего теста системы."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from core.services.firewall_tools_check import apt_install_hint, check_firewall_tools

Status = Literal["ok", "warn", "fail"]
RunCmd = Callable[[list[str], float], subprocess.CompletedProcess]

REQUIRED_COMMANDS = (
    "python3",
    "pip3",
    "git",
    "wget",
    "openssl",
    "systemctl",
    "awk",
    "sed",
    "grep",
    "ss",
    "dig",
)

REQUIRED_SYSTEM_PACKAGES = (
    "python3",
    "python3-pip",
    "python3-venv",
    "python3-dev",
    "git",
    "wget",
    "openssl",
    "cron",
    "vnstat",
    "libjpeg-dev",
    "zlib1g-dev",
)

REQUIRED_SCRIPT_MODULES = (
    "utils",
    "ssl_setup",
    "backup_functions",
    "monitoring",
    "service_functions",
    "uninstall",
    "user_management",
    "unit_tests",
    "site_diagnostics",
    "panel_menus",
)

EXECUTABLE_FILES = ("client.sh",)


@dataclass
class CheckResult:
    status: Status
    title: str
    detail: str = ""


@dataclass
class PreflightContext:
    install_dir: str
    venv_path: str | None = None
    service_name: str = "admin-antizapret"
    db_file: str | None = None
    antizapret_install_dir: str = "/root/antizapret"
    include_dir: str | None = None

    def resolved_venv(self) -> str:
        if self.venv_path:
            return self.venv_path
        return os.path.join(self.install_dir, "venv")

    def resolved_db(self) -> str:
        if self.db_file:
            return self.db_file
        return os.path.join(self.install_dir, "instance", "users.db")

    def resolved_include(self) -> str:
        if self.include_dir:
            return self.include_dir
        return os.path.join(self.install_dir, "script_sh")


@dataclass
class PreflightReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == "warn")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    def has_failures(self) -> bool:
        return self.fail_count > 0


def _default_run_cmd(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _add(report: PreflightReport, result: CheckResult) -> None:
    report.results.append(result)


def _normalize_pkg_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _dpkg_installed(package: str, run_cmd: RunCmd) -> bool:
    proc = run_cmd(["dpkg", "-s", package], 3.0)
    return proc.returncode == 0


def _dnsutils_installed(run_cmd: RunCmd) -> bool:
    return _dpkg_installed("dnsutils", run_cmd) or _dpkg_installed("bind9-dnsutils", run_cmd)


def _read_requirements_names(req_path: str) -> list[str]:
    names: list[str] = []
    if not os.path.isfile(req_path):
        return names
    with open(req_path, encoding="utf-8") as fh:
        for raw in fh:
            line = re.sub(r"#.*$", "", raw).strip()
            if not line:
                continue
            name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip()
            if name:
                names.append(_normalize_pkg_name(name))
    return names


def _installed_pip_names(venv_path: str, run_cmd: RunCmd) -> set[str]:
    pip_bin = os.path.join(venv_path, "bin", "pip")
    if not os.path.isfile(pip_bin):
        return set()
    proc = run_cmd([pip_bin, "list", "--format=freeze"], 30.0)
    if proc.returncode != 0:
        return set()
    names: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        if not line or line.startswith("#"):
            continue
        pkg = line.split("=", 1)[0].strip()
        if pkg:
            names.add(_normalize_pkg_name(pkg))
    return names


def _read_env_keys(env_path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not os.path.isfile(env_path):
        return values
    with open(env_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def run_preflight_checks(
    ctx: PreflightContext,
    *,
    run_cmd: RunCmd | None = None,
) -> PreflightReport:
    """Проверка модулей, пакетов, прав и конфигурации без интерактива."""
    runner = run_cmd or _default_run_cmd
    report = PreflightReport()
    install = ctx.install_dir
    venv = ctx.resolved_venv()
    include = ctx.resolved_include()
    req_file = os.path.join(install, "requirements.txt")
    env_path = os.path.join(install, ".env")

    missing_cmds = [c for c in REQUIRED_COMMANDS if not shutil.which(c)]
    if missing_cmds:
        _add(
            report,
            CheckResult(
                "fail",
                "Системные команды",
                detail=", ".join(missing_cmds),
            ),
        )
    else:
        _add(report, CheckResult("ok", "Системные команды установлены"))

    missing_pkgs: list[str] = []
    for pkg in REQUIRED_SYSTEM_PACKAGES:
        if not _dpkg_installed(pkg, runner):
            missing_pkgs.append(pkg)
    if not _dnsutils_installed(runner):
        missing_pkgs.append("dnsutils")
    if missing_pkgs:
        _add(
            report,
            CheckResult(
                "fail",
                "Системные пакеты",
                detail=", ".join(missing_pkgs),
            ),
        )
    else:
        _add(report, CheckResult("ok", "Системные пакеты установлены"))

    fw = check_firewall_tools(run_cmd=runner)
    if fw.fully_ready:
        _add(
            report,
            CheckResult("ok", "iptables и ipset", detail=fw.operational_detail),
        )
    else:
        fw_parts: list[str] = []
        if fw.missing_commands:
            fw_parts.append(f"команды: {', '.join(fw.missing_commands)}")
        if fw.missing_packages:
            fw_parts.append(f"пакеты: {', '.join(fw.missing_packages)}")
        if fw.binaries_available and not fw.operational_ok:
            fw_parts.append(fw.operational_detail)
        fw_detail = "; ".join(fw_parts) or fw.operational_detail
        if fw.missing_packages or fw.missing_commands:
            hint = apt_install_hint(fw.missing_packages)
            fw_detail = (
                f"{fw_detail}; установка: {hint}" if fw_detail else f"установка: {hint}"
            )
        _add(
            report,
            CheckResult(
                "warn",
                "iptables / ipset (бан сканеров, whitelist порта панели)",
                detail=fw_detail,
            ),
        )

    py_bin = os.path.join(venv, "bin", "python3")
    pip_bin = os.path.join(venv, "bin", "pip")
    if os.path.isfile(py_bin) and os.access(py_bin, os.X_OK) and os.path.isfile(pip_bin):
        _add(report, CheckResult("ok", "Виртуальное окружение venv"))
    else:
        _add(
            report,
            CheckResult("fail", "Виртуальное окружение", detail=venv),
        )

    if not os.path.isfile(req_file):
        _add(report, CheckResult("fail", "requirements.txt не найден"))
    else:
        required = _read_requirements_names(req_file)
        installed = _installed_pip_names(venv, runner)
        missing_py = [n for n in required if n not in installed]
        if missing_py:
            shown = ", ".join(missing_py[:8])
            if len(missing_py) > 8:
                shown += f" … (+{len(missing_py) - 8})"
            _add(
                report,
                CheckResult(
                    "fail",
                    "Python-зависимости",
                    detail=f"не установлено: {shown}",
                ),
            )
        else:
            _add(report, CheckResult("ok", "Python-зависимости из requirements.txt"))

        if os.path.isfile(pip_bin):
            pip_check = runner([pip_bin, "check"], 30.0)
            if pip_check.returncode == 0:
                _add(report, CheckResult("ok", "Согласованность pip (pip check)"))
            else:
                _add(
                    report,
                    CheckResult(
                        "warn",
                        "Конфликты pip check",
                        detail=(pip_check.stdout or pip_check.stderr or "").strip()[:200],
                    ),
                )

    missing_modules = [
        f"{name}.sh"
        for name in REQUIRED_SCRIPT_MODULES
        if not os.path.isfile(os.path.join(include, f"{name}.sh"))
    ]
    if missing_modules:
        _add(
            report,
            CheckResult(
                "fail",
                "Модули script_sh",
                detail=", ".join(missing_modules),
            ),
        )
    else:
        _add(report, CheckResult("ok", "Модули adminpanel (script_sh)"))

    env = _read_env_keys(env_path)
    if os.path.isfile(env_path):
        _add(report, CheckResult("ok", "Файл .env"))
        if env.get("SECRET_KEY"):
            _add(report, CheckResult("ok", "SECRET_KEY в .env"))
        else:
            _add(report, CheckResult("fail", "SECRET_KEY не задан"))
        if env.get("VNSTAT_IFACE"):
            _add(report, CheckResult("ok", "VNSTAT_IFACE в .env"))
        else:
            _add(report, CheckResult("fail", "VNSTAT_IFACE не задан"))
    else:
        _add(report, CheckResult("fail", "Файл .env отсутствует"))

    db_path = ctx.resolved_db()
    if os.path.isfile(db_path):
        _add(report, CheckResult("ok", "База users.db"))
    else:
        _add(report, CheckResult("fail", "База users.db не найдена", detail=db_path))

    unit_path = f"/etc/systemd/system/{ctx.service_name}.service"
    if os.path.isfile(unit_path):
        _add(report, CheckResult("ok", f"Systemd unit {ctx.service_name}"))
    else:
        _add(report, CheckResult("fail", "Systemd unit не найден", detail=unit_path))

    if shutil.which("systemctl"):
        enabled = runner(["systemctl", "is-enabled", ctx.service_name], 5.0)
        if enabled.returncode == 0:
            _add(report, CheckResult("ok", "Сервис в автозагрузке"))
        else:
            _add(report, CheckResult("warn", "Сервис не в автозагрузке"))

        active = runner(["systemctl", "is-active", ctx.service_name], 5.0)
        if active.returncode == 0 and (active.stdout or "").strip() == "active":
            _add(report, CheckResult("ok", "Сервис панели запущен"))
        else:
            _add(report, CheckResult("warn", "Сервис панели не запущен"))

    gunicorn = os.path.join(venv, "bin", "gunicorn")
    if os.path.isfile(gunicorn) and os.access(gunicorn, os.X_OK):
        _add(report, CheckResult("ok", "gunicorn в venv"))
    else:
        _add(report, CheckResult("fail", "gunicorn в venv не найден"))

    if os.path.isfile(os.path.join(install, "gunicorn.conf.py")):
        _add(report, CheckResult("ok", "gunicorn.conf.py"))
    else:
        _add(report, CheckResult("fail", "gunicorn.conf.py не найден"))

    perm_issues: list[str] = []
    for rel in EXECUTABLE_FILES:
        path = os.path.join(install, rel)
        if not os.path.isfile(path):
            perm_issues.append(f"{rel}: нет файла")
        elif not os.access(path, os.X_OK):
            perm_issues.append(f"{rel}: нет +x")
    doall = os.path.join(ctx.antizapret_install_dir, "doall.sh")
    if not os.path.isfile(doall):
        perm_issues.append("doall.sh: нет файла")
    elif not os.access(doall, os.X_OK):
        perm_issues.append("doall.sh: нет +x")

    if perm_issues:
        _add(
            report,
            CheckResult(
                "fail",
                "Права на исполняемые скрипты",
                detail="; ".join(perm_issues),
            ),
        )
    else:
        _add(report, CheckResult("ok", "Права на client.sh и doall.sh"))

    az_dir = ctx.antizapret_install_dir
    if os.path.isdir(az_dir):
        _add(report, CheckResult("ok", "Каталог AntiZapret-VPN"))
    else:
        _add(
            report,
            CheckResult("warn", "Каталог AntiZapret-VPN не найден", detail=az_dir),
        )

    if shutil.which("systemctl"):
        az_active = runner(["systemctl", "is-active", "antizapret.service"], 5.0)
        if az_active.returncode == 0:
            _add(report, CheckResult("ok", "antizapret.service активен"))
        else:
            _add(report, CheckResult("warn", "antizapret.service не активен"))

    return report


def format_preflight_report(report: PreflightReport, *, verbose: bool = False) -> str:
    lines: list[str] = []
    problems = [r for r in report.results if r.status in ("fail", "warn")]

    if verbose:
        for item in report.results:
            tag = item.status.upper()
            lines.append(f"[{tag}] {item.title}")
            if item.detail:
                lines.append(f"       {item.detail}")
    elif problems:
        for item in problems:
            tag = "ОШИБКА" if item.status == "fail" else "ВНИМАНИЕ"
            line = f"  {tag}: {item.title}"
            if item.detail:
                line += f" — {item.detail}"
            lines.append(line)
    else:
        lines.append(f"  OK: {report.ok_count} проверок пройдено")

    lines.append(
        f"  Сводка: OK={report.ok_count}  предупреждений={report.warn_count}  "
        f"ошибок={report.fail_count}"
    )
    return "\n".join(lines)
