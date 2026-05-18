"""Проверка наличия iptables и ipset для банов сканеров и whitelist-порта панели."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

RunCmd = Callable[[list[str], float], subprocess.CompletedProcess]

FIREWALL_COMMANDS = ("iptables", "ipset")
FIREWALL_DEB_PACKAGES = ("iptables", "ipset")


@dataclass(frozen=True)
class FirewallToolsStatus:
    missing_commands: tuple[str, ...]
    missing_packages: tuple[str, ...]
    commands_ok: bool
    operational_ok: bool
    operational_detail: str

    @property
    def binaries_available(self) -> bool:
        return not self.missing_commands

    @property
    def packages_installed(self) -> bool:
        return not self.missing_packages

    @property
    def fully_ready(self) -> bool:
        return self.binaries_available and self.commands_ok and self.operational_ok


def _default_run_cmd(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _dpkg_installed(package: str, run_cmd: RunCmd) -> bool:
    proc = run_cmd(["dpkg", "-s", package], 3.0)
    return proc.returncode == 0


def missing_firewall_commands() -> list[str]:
    return [name for name in FIREWALL_COMMANDS if not shutil.which(name)]


def missing_firewall_packages(*, run_cmd: RunCmd | None = None) -> list[str]:
    runner = run_cmd or _default_run_cmd
    if not shutil.which("dpkg"):
        return list(FIREWALL_DEB_PACKAGES)
    return [pkg for pkg in FIREWALL_DEB_PACKAGES if not _dpkg_installed(pkg, runner)]


def probe_firewall_tools(*, run_cmd: RunCmd | None = None) -> tuple[bool, str]:
    """Проверка, что iptables/ipset реально выполняются (не только есть в PATH)."""
    runner = run_cmd or _default_run_cmd
    missing = missing_firewall_commands()
    if missing:
        return False, f"не найдены: {', '.join(missing)}"

    ipt = runner(["iptables", "-L", "INPUT", "-n"], 10.0)
    if ipt.returncode != 0:
        detail = (ipt.stderr or ipt.stdout or "").strip() or f"код {ipt.returncode}"
        return False, f"iptables: {detail}"

    ipset_proc = runner(["ipset", "version"], 5.0)
    if ipset_proc.returncode != 0:
        detail = (ipset_proc.stderr or ipset_proc.stdout or "").strip() or f"код {ipset_proc.returncode}"
        return False, f"ipset: {detail}"

    return True, "iptables и ipset отвечают"


def check_firewall_tools(*, run_cmd: RunCmd | None = None) -> FirewallToolsStatus:
    runner = run_cmd or _default_run_cmd
    miss_cmds = tuple(missing_firewall_commands())
    miss_pkgs = tuple(missing_firewall_packages(run_cmd=runner))
    operational_ok, operational_detail = probe_firewall_tools(run_cmd=runner)
    return FirewallToolsStatus(
        missing_commands=miss_cmds,
        missing_packages=miss_pkgs,
        commands_ok=not miss_cmds,
        operational_ok=operational_ok,
        operational_detail=operational_detail,
    )


def apt_install_hint(missing_packages: tuple[str, ...] | list[str]) -> str:
    pkgs = " ".join(missing_packages) if missing_packages else "iptables ipset"
    return f"apt install -y {pkgs}"
