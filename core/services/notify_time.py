"""Format timestamps for admin Telegram notifications in the client's timezone."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from flask import has_request_context, request
except ImportError:  # pragma: no cover
    has_request_context = None  # type: ignore
    request = None  # type: ignore


def _normalize_timezone_name(raw: str | None) -> str | None:
    name = str(raw or "").strip()
    if not name or len(name) > 64:
        return None
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return None
    return name


def get_client_timezone_from_request() -> str | None:
    if not has_request_context or not request:
        return None
    return _normalize_timezone_name(request.headers.get("X-Client-Timezone"))


def _timezone_suffix(tz: ZoneInfo, dt: datetime) -> str:
    try:
        abbrev = dt.strftime("%Z")
        if abbrev and abbrev != "UTC" and not abbrev.startswith("+"):
            return abbrev
    except Exception:
        pass
    offset = dt.utcoffset()
    if offset is None:
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    if minutes:
        return f"UTC{sign}{hours}:{minutes:02d}"
    return f"UTC{sign}{hours}"


def format_notify_when(tz_name: str | None = None) -> str:
    """Return 'YYYY-MM-DD HH:MM <zone>' for notification footers."""
    resolved = _normalize_timezone_name(tz_name)
    now_utc = datetime.now(timezone.utc)
    if resolved:
        tz = ZoneInfo(resolved)
        local = now_utc.astimezone(tz)
        suffix = _timezone_suffix(tz, local)
        return f"{local.strftime('%Y-%m-%d %H:%M')} {suffix}"
    return now_utc.strftime("%Y-%m-%d %H:%M UTC")
