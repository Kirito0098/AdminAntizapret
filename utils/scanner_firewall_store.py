"""Персистентные баны сканеров + блокировка на уровне сервера (ipset/iptables)."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DATA_VERSION = 2
DEFAULT_STRIKES_FOR_YEAR = 5
DEFAULT_YEAR_BAN_SECONDS = 365 * 24 * 3600
DEFAULT_UNBAN_GRACE_SECONDS = 1800
IPSET_V4 = "aa_scanner_v4"
IPSET_V6 = "aa_scanner_v6"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 10**9) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


class ScannerFirewallStore:
    def __init__(
        self,
        data_path: Path | str | None = None,
        *,
        strikes_for_year: int | None = None,
        year_ban_seconds: int | None = None,
        firewall_enabled: bool | None = None,
        dry_run: bool | None = None,
    ) -> None:
        root = Path(__file__).resolve().parent.parent
        default_path = root / "data" / "scanner_blocks.json"
        self.data_path = Path(data_path or os.getenv("SCANNER_BLOCKS_FILE", str(default_path)))
        self.strikes_for_year = strikes_for_year or _env_int(
            "IP_SCANNER_STRIKES_FOR_YEAR_BAN", DEFAULT_STRIKES_FOR_YEAR, minimum=1, maximum=100
        )
        self.year_ban_seconds = year_ban_seconds or _env_int(
            "IP_SCANNER_YEAR_BAN_SECONDS", DEFAULT_YEAR_BAN_SECONDS, minimum=3600, maximum=10 * 365 * 86400
        )
        self.firewall_enabled = (
            firewall_enabled
            if firewall_enabled is not None
            else _env_bool("IP_SCANNER_FIREWALL_ENABLED", True)
        )
        self.dry_run = dry_run if dry_run is not None else _env_bool("IP_SCANNER_FIREWALL_DRY_RUN", False)
        self.unban_grace_seconds = _env_int(
            "IP_SCANNER_UNBAN_GRACE_SECONDS", DEFAULT_UNBAN_GRACE_SECONDS, minimum=60, maximum=86400
        )
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"version": DEFAULT_DATA_VERSION, "entries": {}}
        self._load()

    def _load(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_path.exists():
            self._save_unlocked()
            return
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Не удалось прочитать %s: %s", self.data_path, exc)
            return
        if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
            self._data = raw
            if "version" not in self._data:
                self._data["version"] = DEFAULT_DATA_VERSION

    def _save_unlocked(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{self.data_path.name}.",
            dir=str(self.data_path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.data_path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    def _save(self) -> None:
        with self._lock:
            self._save_unlocked()

    def _entry(self, ip: str) -> dict[str, Any]:
        entries = self._data.setdefault("entries", {})
        record = entries.get(ip)
        if not isinstance(record, dict):
            record = {
                "ip": ip,
                "strikes": 0,
                "ban_until": 0.0,
                "long_term": False,
                "recent_attempts": [],
                "ip_blocked_since": None,
                "unban_grace_until": 0.0,
                "events": [],
            }
            entries[ip] = record
        return record

    def is_in_unban_grace(self, ip: str, *, now: float | None = None) -> bool:
        now = now or time.time()
        with self._lock:
            record = (self._data.get("entries") or {}).get(ip)
            if not isinstance(record, dict):
                return False
            grace_until = float(record.get("unban_grace_until") or 0)
            return grace_until > now

    def _can_apply_firewall_ban(self, ip: str, *, now: float | None = None) -> bool:
        return not self.is_in_unban_grace(ip, now=now)

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

    def _ip_version(self, ip: str) -> int:
        if ":" in ip:
            return 6
        return 4

    def _ipset_name(self, ip: str) -> str:
        return IPSET_V6 if self._ip_version(ip) == 6 else IPSET_V4

    def ensure_firewall_infrastructure(self) -> bool:
        if not self.firewall_enabled or self.dry_run:
            return True

        ok_v4, err_v4 = self._run_command(
            [
                "ipset", "create", IPSET_V4, "hash:ip", "family", "inet",
                "hashsize", "4096", "maxelem", "65536", "-exist",
            ]
        )
        ok_v6, err_v6 = self._run_command(
            [
                "ipset", "create", IPSET_V6, "hash:ip", "family", "inet6",
                "hashsize", "4096", "maxelem", "65536", "-exist",
            ]
        )
        for ipset_name in (IPSET_V4, IPSET_V6):
            exists, _ = self._run_command(
                ["iptables", "-C", "INPUT", "-m", "set", "--match-set", ipset_name, "src", "-j", "DROP"]
            )
            if not exists:
                self._run_command(
                    ["iptables", "-I", "INPUT", "-m", "set", "--match-set", ipset_name, "src", "-j", "DROP"]
                )

        if not ok_v4 or not ok_v6:
            logger.warning("ipset init: v4=%s v6=%s (%s / %s)", ok_v4, ok_v6, err_v4, err_v6)
        return ok_v4 or ok_v6

    def _firewall_add(self, ip: str, timeout_seconds: int) -> bool:
        if not self.firewall_enabled:
            return False
        if self.dry_run:
            logger.info("scanner firewall dry-run add %s timeout=%s", ip, timeout_seconds)
            return True

        self.ensure_firewall_infrastructure()
        ipset_name = self._ipset_name(ip)
        args = ["ipset", "add", ipset_name, ip, "-exist"]
        if timeout_seconds > 0:
            args.extend(["timeout", str(int(timeout_seconds))])
        ok, err = self._run_command(args)
        if not ok:
            logger.warning("ipset add failed for %s: %s", ip, err)
        return ok

    def _firewall_remove(self, ip: str) -> None:
        if not self.firewall_enabled or self.dry_run:
            if self.dry_run:
                logger.info("scanner firewall dry-run del %s", ip)
            return
        ipset_name = self._ipset_name(ip)
        self._run_command(["ipset", "del", ipset_name, ip, "-exist"])

    def sync_firewall_from_store(self) -> None:
        if not self.firewall_enabled:
            return
        now = time.time()
        with self._lock:
            entries = dict(self._data.get("entries") or {})

        self.ensure_firewall_infrastructure()
        for ip, record in entries.items():
            if not isinstance(record, dict):
                continue
            ban_until = float(record.get("ban_until") or 0)
            if ban_until <= now:
                continue
            timeout = max(1, int(ban_until - now))
            self._firewall_add(ip, timeout)

    def is_banned(self, ip: str, *, now: float | None = None) -> bool:
        now = now or time.time()
        with self._lock:
            record = (self._data.get("entries") or {}).get(ip)
            if not isinstance(record, dict):
                return False
            ban_until = float(record.get("ban_until") or 0)
            if ban_until > now:
                return True
            if ban_until > 0:
                record["ban_until"] = 0.0
                self._firewall_remove(ip)
                self._save_unlocked()
            return False

    def get_ban_until(self, ip: str) -> float:
        with self._lock:
            record = (self._data.get("entries") or {}).get(ip)
            if not isinstance(record, dict):
                return 0.0
            return float(record.get("ban_until") or 0)

    def prune_attempts(self, ip: str, window_seconds: int, *, now: float | None = None) -> list[float]:
        now = now or time.time()
        cutoff = now - window_seconds
        with self._lock:
            record = self._entry(ip)
            attempts = [float(ts) for ts in (record.get("recent_attempts") or []) if float(ts) >= cutoff]
            record["recent_attempts"] = attempts
            return attempts

    def record_attempt(self, ip: str, window_seconds: int, *, now: float | None = None) -> int:
        now = now or time.time()
        with self._lock:
            attempts = self.prune_attempts(ip, window_seconds, now=now)
            record = self._entry(ip)
            attempts.append(now)
            record["recent_attempts"] = attempts
            self._save_unlocked()
            return len(attempts)

    def touch_ip_blocked(self, ip: str, *, now: float | None = None) -> float | None:
        now = now or time.time()
        with self._lock:
            record = self._entry(ip)
            since = record.get("ip_blocked_since")
            if since is None:
                record["ip_blocked_since"] = now
                self._save_unlocked()
                return now
            return float(since)

    def register_ban(
        self,
        ip: str,
        *,
        reason: str,
        short_ban_seconds: int,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        now = now or time.time()
        if not self._can_apply_firewall_ban(ip, now=now):
            return None
        with self._lock:
            record = self._entry(ip)
            strikes = int(record.get("strikes") or 0) + 1
            record["strikes"] = strikes
            record["ip_blocked_since"] = None
            record["recent_attempts"] = []

            long_term = strikes >= self.strikes_for_year
            if long_term:
                ban_seconds = self.year_ban_seconds
                record["long_term"] = True
            else:
                ban_seconds = max(60, int(short_ban_seconds))
                record["long_term"] = False

            ban_until = now + ban_seconds
            record["ban_until"] = ban_until
            events = list(record.get("events") or [])
            events.append(
                {
                    "at": now,
                    "reason": reason,
                    "ban_seconds": ban_seconds,
                    "strike": strikes,
                    "long_term": long_term,
                    "firewall": self.firewall_enabled and not self.dry_run,
                }
            )
            record["events"] = events[-50:]
            self._save_unlocked()

        self._firewall_add(ip, ban_seconds)
        return {
            "ip": ip,
            "strikes": strikes,
            "ban_until": ban_until,
            "remaining_seconds": int(ban_until - now),
            "long_term": long_term,
            "firewall": self.firewall_enabled,
        }

    def get_active_bans(self, *, now: float | None = None) -> list[dict[str, Any]]:
        now = now or time.time()
        active: list[dict[str, Any]] = []
        with self._lock:
            entries = dict(self._data.get("entries") or {})
            changed = False
            for ip, record in entries.items():
                if not isinstance(record, dict):
                    continue
                ban_until = float(record.get("ban_until") or 0)
                if ban_until <= now:
                    if ban_until > 0:
                        record["ban_until"] = 0.0
                        self._firewall_remove(ip)
                        changed = True
                    continue
                active.append(
                    {
                        "ip": ip,
                        "ban_until": ban_until,
                        "remaining_seconds": int(ban_until - now),
                        "strikes": int(record.get("strikes") or 0),
                        "long_term": bool(record.get("long_term")),
                    }
                )
            if changed:
                self._save_unlocked()
        active.sort(key=lambda item: item["ban_until"], reverse=True)
        return active

    def get_grace_entries(self, *, now: float | None = None) -> list[dict[str, Any]]:
        now = now or time.time()
        grace_list: list[dict[str, Any]] = []
        with self._lock:
            for ip, record in (self._data.get("entries") or {}).items():
                if not isinstance(record, dict):
                    continue
                ban_until = float(record.get("ban_until") or 0)
                grace_until = float(record.get("unban_grace_until") or 0)
                if ban_until > now or grace_until <= now:
                    continue
                grace_list.append(
                    {
                        "ip": ip,
                        "strikes": int(record.get("strikes") or 0),
                        "grace_remaining_seconds": int(grace_until - now),
                    }
                )
        grace_list.sort(key=lambda item: item["grace_remaining_seconds"], reverse=True)
        return grace_list

    def get_display_state(self, *, now: float | None = None) -> dict[str, Any]:
        active_bans = self.get_active_bans(now=now)
        grace_entries = self.get_grace_entries(now=now)
        return {
            "active_bans": active_bans,
            "grace_entries": grace_entries,
            "has_firewall_entries": bool(active_bans or grace_entries),
        }

    def flush_firewall_sets(self) -> None:
        if not self.firewall_enabled or self.dry_run:
            return
        for ipset_name in (IPSET_V4, IPSET_V6):
            self._run_command(["ipset", "flush", ipset_name])

    def release_firewall_only(self, ip: str) -> bool:
        """Только снять ipset (для IP из whitelist), без тестовой grace-записи."""
        ip_key = (ip or "").strip()
        if not ip_key:
            return False
        with self._lock:
            record = (self._data.get("entries") or {}).get(ip_key)
            if isinstance(record, dict):
                record["ban_until"] = 0.0
                record["long_term"] = False
                record["recent_attempts"] = []
                record["ip_blocked_since"] = None
                self._save_unlocked()
        self._firewall_remove(ip_key)
        return True

    def unban_ip(self, ip: str, *, clear_strikes: bool = True, grace_seconds: int | None = None) -> bool:
        ip_key = (ip or "").strip()
        if not ip_key:
            return False

        grace = grace_seconds if grace_seconds is not None else self.unban_grace_seconds
        grace_until = time.time() + max(60, int(grace))

        with self._lock:
            entries = self._data.setdefault("entries", {})
            if clear_strikes:
                record = {
                    "ip": ip_key,
                    "strikes": 0,
                    "ban_until": 0.0,
                    "long_term": False,
                    "recent_attempts": [],
                    "ip_blocked_since": None,
                    "unban_grace_until": grace_until,
                    "events": [],
                }
                entries[ip_key] = record
            elif ip_key in entries and isinstance(entries[ip_key], dict):
                record = entries[ip_key]
                record["ban_until"] = 0.0
                record["long_term"] = False
                record["recent_attempts"] = []
                record["ip_blocked_since"] = None
                record["unban_grace_until"] = grace_until
            else:
                entries[ip_key] = {
                    "ip": ip_key,
                    "strikes": 0,
                    "ban_until": 0.0,
                    "long_term": False,
                    "recent_attempts": [],
                    "ip_blocked_since": None,
                    "unban_grace_until": grace_until,
                    "events": [],
                }
            self._save_unlocked()

        self._firewall_remove(ip_key)
        return True

    def clear_all(self) -> int:
        with self._lock:
            entries = dict(self._data.get("entries") or {})
            for ip in list(entries.keys()):
                self._firewall_remove(ip)
            self._data["entries"] = {}
            self._save_unlocked()
        self.flush_firewall_sets()
        return 0

    def get_grace_entries(self, *, now: float | None = None) -> list[dict[str, Any]]:
        now = now or time.time()
        grace_list: list[dict[str, Any]] = []
        with self._lock:
            for ip, record in (self._data.get("entries") or {}).items():
                if not isinstance(record, dict):
                    continue
                ban_until = float(record.get("ban_until") or 0)
                grace_until = float(record.get("unban_grace_until") or 0)
                if ban_until > now:
                    continue
                if grace_until <= now:
                    continue
                grace_list.append(
                    {
                        "ip": ip,
                        "strikes": int(record.get("strikes") or 0),
                        "grace_remaining_seconds": int(grace_until - now),
                    }
                )
        grace_list.sort(key=lambda item: item["grace_remaining_seconds"], reverse=True)
        return grace_list

    def get_display_state(self, *, now: float | None = None) -> dict[str, Any]:
        active_bans = self.get_active_bans(now=now)
        grace_entries = self.get_grace_entries(now=now)
        return {
            "active_bans": active_bans,
            "grace_entries": grace_entries,
            "has_firewall_entries": bool(active_bans or grace_entries),
        }

    def get_settings_snapshot(self) -> dict[str, Any]:
        return {
            "strikes_for_year": self.strikes_for_year,
            "year_ban_seconds": self.year_ban_seconds,
            "unban_grace_seconds": self.unban_grace_seconds,
            "firewall_enabled": self.firewall_enabled,
            "data_path": str(self.data_path),
        }
