"""Временный whitelist IP (JSON, срок 1h / 12h / 24h)."""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DATA_VERSION = 1

DURATION_LABELS: dict[str, int] = {
    "1h": 3600,
    "12h": 43200,
    "24h": 86400,
}


def normalize_host_ip(value: str | None) -> str | None:
    """Одиночный IPv4/IPv6 без CIDR."""
    raw = (value or "").strip()
    if not raw or "/" in raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def duration_seconds_from_label(label: str) -> int | None:
    key = (label or "").strip().lower()
    return DURATION_LABELS.get(key)


def duration_label_from_seconds(seconds: int) -> str:
    for label, value in DURATION_LABELS.items():
        if value == seconds:
            return label
    if seconds % 3600 == 0 and seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


class TemporaryWhitelistStore:
    def __init__(self, data_path: Path | str | None = None) -> None:
        root = Path(__file__).resolve().parent.parent
        default_path = root / "data" / "temporary_whitelist.json"
        self.data_path = Path(
            data_path or os.getenv("TEMPORARY_WHITELIST_FILE", str(default_path))
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

    def purge_expired(self, now: float | None = None) -> list[str]:
        """Удаляет истёкшие записи. Возвращает список удалённых IP."""
        now = now if now is not None else time.time()
        removed: list[str] = []
        with self._lock:
            entries = self._data.setdefault("entries", {})
            for ip_key in list(entries.keys()):
                record = entries.get(ip_key)
                if not isinstance(record, dict):
                    del entries[ip_key]
                    removed.append(ip_key)
                    continue
                expires_at = float(record.get("expires_at") or 0)
                if expires_at <= now:
                    del entries[ip_key]
                    removed.append(ip_key)
            if removed:
                self._save_unlocked()
        return removed

    def has_active(self, now: float | None = None) -> bool:
        return bool(self.get_active_ips(now=now))

    def get_active_ips(self, now: float | None = None) -> set[str]:
        now = now if now is not None else time.time()
        self.purge_expired(now)
        with self._lock:
            entries = self._data.get("entries") or {}
            active: set[str] = set()
            for ip_key, record in entries.items():
                if not isinstance(record, dict):
                    continue
                if float(record.get("expires_at") or 0) > now:
                    active.add(ip_key)
            return active

    def get_active_entries(self, now: float | None = None) -> list[dict[str, Any]]:
        now = now if now is not None else time.time()
        self.purge_expired(now)
        rows: list[dict[str, Any]] = []
        with self._lock:
            entries = self._data.get("entries") or {}
            for ip_key, record in sorted(entries.items()):
                if not isinstance(record, dict):
                    continue
                expires_at = float(record.get("expires_at") or 0)
                if expires_at <= now:
                    continue
                duration_seconds = int(record.get("duration_seconds") or 0)
                rows.append(
                    {
                        "ip": ip_key,
                        "expires_at": expires_at,
                        "remaining_seconds": max(0, int(expires_at - now)),
                        "duration_seconds": duration_seconds,
                        "duration_label": duration_label_from_seconds(duration_seconds),
                    }
                )
        return rows

    def add(self, ip: str, duration_seconds: int, now: float | None = None) -> str | None:
        ip_key = normalize_host_ip(ip)
        if not ip_key:
            return None
        if duration_seconds < 60:
            return None
        now = now if now is not None else time.time()
        expires_at = now + duration_seconds
        with self._lock:
            entries = self._data.setdefault("entries", {})
            entries[ip_key] = {
                "expires_at": expires_at,
                "duration_seconds": duration_seconds,
                "added_at": now,
            }
            self._save_unlocked()
        return ip_key

    def remove(self, ip: str) -> bool:
        ip_key = normalize_host_ip(ip)
        if not ip_key:
            raw = (ip or "").strip()
            if not raw:
                return False
            ip_key = raw
        with self._lock:
            entries = self._data.setdefault("entries", {})
            if ip_key not in entries:
                return False
            del entries[ip_key]
            self._save_unlocked()
            return True

    def clear_all(self) -> None:
        with self._lock:
            self._data = {"version": DEFAULT_DATA_VERSION, "entries": {}}
            self._save_unlocked()

    def is_allowed(self, ip: str, now: float | None = None) -> bool:
        ip_key = normalize_host_ip(ip)
        if not ip_key:
            return False
        now = now if now is not None else time.time()
        self.purge_expired(now)
        with self._lock:
            record = (self._data.get("entries") or {}).get(ip_key)
            if not isinstance(record, dict):
                return False
            return float(record.get("expires_at") or 0) > now
