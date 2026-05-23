#!/usr/bin/env python3
import glob
import os
import sqlite3
import sys
from datetime import datetime, timezone

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from core.services.backup_manager import BackupManagerService  # noqa: E402
from core.services.tg_notify import send_tg_document  # noqa: E402


def _load_env_map(env_path):
    env_map = {}
    if not os.path.isfile(env_path):
        return env_map
    with open(env_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_map[key.strip()] = value.strip().strip("'").strip('"')
    return env_map


def _env(env_map, key, default=""):
    value = os.getenv(key)
    if value is not None and value != "":
        return value
    return env_map.get(key, default)


def _to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _collect_config_paths():
    paths = []
    patterns = (
        "/etc/openvpn/client/*.ovpn",
        "/etc/openvpn/*.ovpn",
        "/etc/wireguard/*.conf",
        "/etc/amnezia/amneziawg/*.conf",
    )
    for pattern in patterns:
        paths.extend(glob.glob(pattern))
    seen = set()
    result = []
    for path in paths:
        abs_path = os.path.abspath(path)
        if abs_path in seen or not os.path.isfile(abs_path):
            continue
        seen.add(abs_path)
        result.append(abs_path)
    return result


def _load_admin_chat_ids(app_root, selected_admin_ids):
    db_candidates = [
        os.path.join(app_root, "instance", "users.db"),
        os.path.join(app_root, "users.db"),
    ]
    selected = {str(item) for item in selected_admin_ids if str(item).strip().isdigit()}
    for db_path in db_candidates:
        if not os.path.isfile(db_path):
            continue
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            if selected:
                placeholders = ",".join("?" for _ in selected)
                cur.execute(
                    f"""
                    SELECT telegram_id
                    FROM user
                    WHERE role='admin'
                      AND telegram_id IS NOT NULL
                      AND CAST(id AS TEXT) IN ({placeholders})
                    """,
                    sorted(selected),
                )
            else:
                cur.execute(
                    """
                    SELECT telegram_id
                    FROM user
                    WHERE role='admin'
                      AND telegram_id IS NOT NULL
                    """
                )
            rows = cur.fetchall()
            return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]
        finally:
            conn.close()
    return []


def main():
    app_root = APP_ROOT
    env_map = _load_env_map(os.path.join(app_root, ".env"))
    if not _to_bool(_env(env_map, "APP_BACKUP_ENABLED", "false")):
        return 0

    backup_root = _env(env_map, "APP_BACKUP_ROOT", "/var/backups/antizapret")
    service_name = _env(env_map, "APP_BACKUP_SERVICE_NAME", "admin-antizapret")
    components_csv = _env(env_map, "APP_BACKUP_COMPONENTS", "db,env,configs")
    components = [item.strip().lower() for item in components_csv.split(",") if item.strip()]

    backup_service = BackupManagerService(
        app_root=app_root,
        backup_root=backup_root,
        service_name=service_name,
        retention_count=5,
    )
    result = backup_service.create_backup(
        selected_components=components,
        config_paths=_collect_config_paths(),
        trigger="auto",
    )

    if not _to_bool(_env(env_map, "APP_BACKUP_TG_ENABLED", "false")):
        return 0

    bot_token = _env(env_map, "TELEGRAM_AUTH_BOT_TOKEN", "").strip()
    if not bot_token:
        return 0

    selected_admin_ids = [
        item.strip() for item in _env(env_map, "APP_BACKUP_TG_ADMIN_IDS", "").split(",") if item.strip()
    ]
    chat_ids = _load_admin_chat_ids(app_root, selected_admin_ids)
    if not chat_ids:
        return 0

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    caption = f"Авто-бэкап приложения\nДата: {created_at}"
    for chat_id in chat_ids:
        send_tg_document(
            bot_token,
            chat_id,
            result["archive_path"],
            caption=caption,
            run_async=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
