"""iptables/ipset (IPv4): доступ к порту панели только с IP из whitelist."""
from __future__ import annotations

import ipaddress
import logging
import os
import subprocess
from typing import Iterable

logger = logging.getLogger(__name__)

CHAIN_V4 = "AA_PANEL_WHITELIST"
IPSET_ALLOW_V4 = "aa_panel_allow_v4"
COMMENT_JUMP_V4 = "aa-panel-port-jump-v4"
# Legacy IPv6 artifacts — only removed on disable, not created on sync.
CHAIN_V6_LEGACY = "AA_PANEL_WHITELIST6"
IPSET_ALLOW_V6_LEGACY = "aa_panel_allow_v6"
COMMENT_JUMP_V6_LEGACY = "aa-panel-port-jump-v6"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _panel_port() -> int:
    raw = (os.getenv("APP_PORT", "5050") or "").strip()
    try:
        return max(1, min(65535, int(raw)))
    except ValueError:
        return 5050


class PanelPortFirewall:
    def __init__(
        self,
        *,
        firewall_enabled: bool | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self.firewall_enabled = (
            firewall_enabled
            if firewall_enabled is not None
            else _env_bool("IP_SCANNER_FIREWALL_ENABLED", True)
        )
        self.dry_run = dry_run if dry_run is not None else _env_bool("IP_SCANNER_FIREWALL_DRY_RUN", False)
        self._active_port: int | None = None

    @staticmethod
    def _run_command(args: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode == 0:
                return True, ""
            stderr = (result.stderr or result.stdout or "").strip()
            return False, stderr
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    @staticmethod
    def _ipset_entry(entry: str) -> str | None:
        value = (entry or "").strip()
        if not value:
            return None
        try:
            if "/" in value:
                network = ipaddress.ip_network(value, strict=False)
                if network.version != 4:
                    return None
                return str(network)
            addr = ipaddress.ip_address(value)
            if addr.version != 4:
                return None
            return f"{addr}/32"
        except ValueError:
            return None

    def _ipv4_entries(self, allowed_ips: Iterable[str]) -> list[str]:
        entries: list[str] = []
        for raw in allowed_ips:
            normalized = self._ipset_entry(raw)
            if normalized:
                entries.append(normalized)
        return entries

    def _ensure_ipset(self) -> bool:
        ok, err = self._run_command(
            [
                "ipset", "create", IPSET_ALLOW_V4, "hash:net", "family", "inet",
                "hashsize", "4096", "maxelem", "65536", "-exist",
            ]
        )
        if not ok:
            logger.warning("ipset create %s failed: %s", IPSET_ALLOW_V4, err)
        return ok

    def _flush_ipset(self, name: str) -> None:
        self._run_command(["ipset", "flush", name])

    def _populate_ipset(self, entries: list[str]) -> None:
        self._flush_ipset(IPSET_ALLOW_V4)
        for entry in entries:
            ok, err = self._run_command(["ipset", "add", IPSET_ALLOW_V4, entry, "-exist"])
            if not ok:
                logger.warning("ipset add %s -> %s failed: %s", IPSET_ALLOW_V4, entry, err)

    def _ensure_chain(self) -> None:
        self._run_command(["iptables", "-N", CHAIN_V4])
        self._run_command(["iptables", "-F", CHAIN_V4])
        self._run_command(
            [
                "iptables", "-A", CHAIN_V4,
                "-m", "set", "--match-set", IPSET_ALLOW_V4, "src",
                "-j", "RETURN",
            ]
        )
        self._run_command(["iptables", "-A", CHAIN_V4, "-j", "DROP"])

    def _remove_jump_rules(self, table_cmd: str, comment: str) -> None:
        ok, out = self._run_command([table_cmd, "-S", "INPUT"])
        if not ok:
            return
        for line in (out or "").splitlines():
            if comment not in line or "-j" not in line:
                continue
            if not line.startswith("-A INPUT"):
                continue
            rule = line.replace("-A INPUT", "", 1).strip()
            if not rule:
                continue
            parts = ["-D", "INPUT"] + rule.split()
            self._run_command([table_cmd] + parts)

    def _ensure_jump(self, *, port: int) -> None:
        check = [
            "iptables", "-C", "INPUT",
            "-p", "tcp", "--dport", str(port),
            "-m", "comment", "--comment", COMMENT_JUMP_V4,
            "-j", CHAIN_V4,
        ]
        exists, _ = self._run_command(check)
        if exists:
            return
        self._remove_jump_rules("iptables", COMMENT_JUMP_V4)
        self._run_command(
            [
                "iptables", "-I", "INPUT",
                "-p", "tcp", "--dport", str(port),
                "-m", "comment", "--comment", COMMENT_JUMP_V4,
                "-j", CHAIN_V4,
            ]
        )

    def _cleanup_legacy_ipv6(self) -> None:
        """Снять старые правила IPv6, если остались от прежних версий."""
        self._remove_jump_rules("ip6tables", COMMENT_JUMP_V6_LEGACY)
        self._run_command(["ipset", "flush", IPSET_ALLOW_V6_LEGACY])

    def disable(self, *, port: int | None = None) -> bool:
        port = port or self._active_port or _panel_port()
        if self.dry_run:
            logger.info("panel port firewall dry-run disable port=%s", port)
            self._active_port = None
            return True
        if not self.firewall_enabled:
            return True

        self._remove_jump_rules("iptables", COMMENT_JUMP_V4)
        self._flush_ipset(IPSET_ALLOW_V4)
        self._cleanup_legacy_ipv6()
        self._active_port = None
        return True

    def sync(self, allowed_ips: Iterable[str], *, port: int | None = None) -> bool:
        port = port or _panel_port()
        v4_entries = self._ipv4_entries(allowed_ips)

        if self.dry_run:
            logger.info(
                "panel port firewall dry-run sync port=%s v4=%s",
                port,
                len(v4_entries),
            )
            self._active_port = port
            return True

        if not self.firewall_enabled:
            return False

        if not v4_entries:
            return self.disable(port=port)

        if not self._ensure_ipset():
            return False

        self._populate_ipset(v4_entries)
        self._ensure_chain()
        self._ensure_jump(port=port)
        self._cleanup_legacy_ipv6()
        self._active_port = port
        return True
