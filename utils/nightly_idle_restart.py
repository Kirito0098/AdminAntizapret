#!/usr/bin/env python3
"""Nightly restart at 04:00 if no active authenticated web sessions."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _parse_bool(raw, default=False):
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(raw, default):
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def _load_env_file(env_path):
    env_map = {}
    if not env_path.exists():
        return env_map

    with env_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_map[key.strip()] = value.strip()

    return env_map


def _resolve_db_path(app_root):
    candidates = [
        app_root / "instance" / "users.db",
        app_root / "users.db",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _count_active_sessions(conn, ttl_seconds):
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM active_web_session
        WHERE last_seen_at >= datetime('now', ?)
        """,
        (f"-{ttl_seconds} seconds",),
    ).fetchone()
    return int(row[0] if row else 0)


def _cleanup_stale_rows(conn, ttl_seconds):
    stale_seconds = max(ttl_seconds * 8, 86400)
    conn.execute(
        """
        DELETE FROM active_web_session
        WHERE last_seen_at < datetime('now', ?)
        """,
        (f"-{stale_seconds} seconds",),
    )
    conn.commit()


def _restart_service(service_name):
    subprocess.run(
        ["systemctl", "restart", service_name],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )


def main():
    app_root = Path(__file__).resolve().parents[1]
    env_file = app_root / ".env"
    env_map = _load_env_file(env_file)

    enabled = _parse_bool(
        env_map.get("NIGHTLY_IDLE_RESTART_ENABLED", os.getenv("NIGHTLY_IDLE_RESTART_ENABLED")),
        default=True,
    )
    if not enabled:
        print("nightly idle restart disabled")
        return 0

    ttl_seconds = _parse_int(
        env_map.get("ACTIVE_WEB_SESSION_TTL_SECONDS", os.getenv("ACTIVE_WEB_SESSION_TTL_SECONDS", "180")),
        default=180,
    )
    if ttl_seconds < 30:
        ttl_seconds = 30

    service_name = (
        env_map.get("ADMIN_ANTIZAPRET_SERVICE_NAME")
        or os.getenv("ADMIN_ANTIZAPRET_SERVICE_NAME")
        or "admin-antizapret.service"
    ).strip()

    db_path = _resolve_db_path(app_root)
    if not db_path.exists():
        print(f"db not found: {db_path}")
        return 0

    try:
        conn = sqlite3.connect(str(db_path))
        try:
            if not _table_exists(conn, "active_web_session"):
                print("active_web_session table not found, skip restart")
                return 0

            _cleanup_stale_rows(conn, ttl_seconds)
            active_count = _count_active_sessions(conn, ttl_seconds)
            if active_count > 0:
                print(f"skip restart: active sessions = {active_count}")
                return 0
        finally:
            conn.close()

        _restart_service(service_name)
        print(f"service restarted: {service_name}")
        return 0
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        print(f"restart failed: {err}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"nightly idle restart failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
