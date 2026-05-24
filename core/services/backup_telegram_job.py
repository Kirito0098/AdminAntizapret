import logging
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone

from core.services.antizapret_backup import AntizapretBackupService
from core.services.backup_manager import BackupManagerService
from core.services.tg_notify import send_tg_document, send_tg_message

logger = logging.getLogger(__name__)

# Telegram Bot API limit for sendDocument (use a small margin).
TELEGRAM_MAX_DOCUMENT_BYTES = 48 * 1024 * 1024
# Panel DB archives often exceed the limit; send env+data in Telegram instead.
TELEGRAM_PANEL_FALLBACK_COMPONENTS = ("env", "data")


def load_env_map(env_path):
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


def env_value(env_map, key, default=""):
    value = os.getenv(key)
    if value is not None and value != "":
        return value
    return env_map.get(key, default)


def to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_admin_chat_ids(app_root, selected_admin_ids):
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


def az_install_dir(env_map):
    return (
        env_value(env_map, "APP_BACKUP_AZ_INSTALL_DIR", "").strip()
        or env_value(env_map, "ANTIZAPRET_INSTALL_DIR", "").strip()
        or "/root/antizapret"
    )


def create_az_backup(env_map):
    return AntizapretBackupService(install_dir=az_install_dir(env_map)).create_backup()


def human_size(size_bytes):
    size = float(max(0, int(size_bytes or 0)))
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def file_fits_telegram(file_path):
    try:
        return os.path.getsize(file_path) <= TELEGRAM_MAX_DOCUMENT_BYTES
    except OSError:
        return False


def _create_panel_telegram_fallback_archive(backup_service, app_root):
    """Lightweight panel archive (env + data) for Telegram when full backup is too large."""
    tmp_root = tempfile.mkdtemp(prefix="panel-tg-backup-")
    try:
        tmp_service = BackupManagerService(
            app_root=app_root,
            backup_root=tmp_root,
            service_name=backup_service.service_name,
            retention_count=99,
        )
        result = tmp_service.create_backup(
            selected_components=list(TELEGRAM_PANEL_FALLBACK_COMPONENTS),
            trigger="telegram",
        )
        return result, tmp_root
    except Exception:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise


def build_panel_telegram_documents(
    *,
    backup_service,
    app_root,
    panel_result,
    label,
    created_at,
):
    """
    Return list of (path, caption) for panel backup in Telegram.
    Falls back to env+data archive when full backup exceeds Telegram size limit.
    """
    archive_path = panel_result.get("archive_path") or ""
    archive_name = panel_result.get("archive_name") or os.path.basename(archive_path)
    documents = []
    notices = []
    cleanup_dirs = []

    if archive_path and os.path.isfile(archive_path) and file_fits_telegram(archive_path):
        documents.append(
            (
                archive_path,
                f"{label} панели\nФайл: {archive_name}\nДата: {created_at}",
            )
        )
        return documents, notices, cleanup_dirs

    full_size = ""
    if archive_path and os.path.isfile(archive_path):
        full_size = human_size(os.path.getsize(archive_path))
        notices.append(
            f"Полный бэкап панели ({full_size}) не отправлен в Telegram: лимит 50 МБ. "
            f"Файл на сервере: {archive_path}"
        )

    try:
        fallback, tmp_root = _create_panel_telegram_fallback_archive(backup_service, app_root)
        fallback_path = fallback.get("archive_path") or ""
        fallback_name = fallback.get("archive_name") or os.path.basename(fallback_path)
        if fallback_path and os.path.isfile(fallback_path) and file_fits_telegram(fallback_path):
            note = "без базы SQLite"
            if full_size:
                note = f"без БД (полный архив {full_size} на сервере)"
            documents.append(
                (
                    fallback_path,
                    f"{label} панели ({note})\nФайл: {fallback_name}\nДата: {created_at}",
                )
            )
            cleanup_dirs.append(tmp_root)
        elif fallback_path and os.path.isfile(fallback_path):
            notices.append(
                f"Облегчённый бэкап панели тоже слишком большой "
                f"({human_size(os.path.getsize(fallback_path))}): {fallback_path}"
            )
            shutil.rmtree(tmp_root, ignore_errors=True)
        else:
            shutil.rmtree(tmp_root, ignore_errors=True)
    except Exception as exc:
        logger.warning("Panel Telegram fallback backup failed: %s", exc)
        notices.append(f"Не удалось создать облегчённый бэкап для Telegram: {exc}")

    return documents, notices, cleanup_dirs


def send_backup_documents(bot_token, chat_ids, documents, *, notices=None):
    notices = notices or []
    sent = 0
    failed = 0

    for chat_id in chat_ids:
        for notice in notices:
            send_tg_message(bot_token, chat_id, notice, run_async=False)

        for index, (file_path, caption) in enumerate(documents):
            if index > 0:
                time.sleep(1.5)
            if send_tg_document(
                bot_token,
                chat_id,
                file_path,
                caption=caption,
                run_async=False,
            ):
                sent += 1
            else:
                failed += 1

    return {"sent": sent, "failed": failed}


def validate_telegram_delivery(app_root, env_map=None):
    env_map = env_map or load_env_map(os.path.join(app_root, ".env"))
    bot_token = env_value(env_map, "TELEGRAM_AUTH_BOT_TOKEN", "").strip()
    if not bot_token:
        return False, "Не задан TELEGRAM_AUTH_BOT_TOKEN (Настройки → Telegram авторизация)."

    selected_admin_ids = [
        item.strip()
        for item in env_value(env_map, "APP_BACKUP_TG_ADMIN_IDS", "").split(",")
        if item.strip()
    ]
    chat_ids = load_admin_chat_ids(app_root, selected_admin_ids)
    if not chat_ids:
        return False, (
            "Нет получателей: укажите админов с Telegram ID в списке получателей "
            "и сохраните настройки бэкапов."
        )
    return True, ""


def run_backup_job(
    app_root,
    *,
    trigger="auto",
    require_auto_enabled=True,
    send_telegram=None,
):
    """
    Create panel (+ optional AZ) backups and optionally send archives to Telegram.

    send_telegram: None — follow APP_BACKUP_TG_ENABLED; True — always send; False — never send.
    Returns dict with paths, flags and human-readable summary for background tasks.
    """
    app_root = os.path.abspath(app_root)
    env_map = load_env_map(os.path.join(app_root, ".env"))

    if require_auto_enabled and not to_bool(env_value(env_map, "APP_BACKUP_ENABLED", "false")):
        return {"skipped": True, "reason": "auto_backup_disabled"}

    backup_root = env_value(env_map, "APP_BACKUP_ROOT", "/var/backups/antizapret")
    service_name = env_value(env_map, "APP_BACKUP_SERVICE_NAME", "admin-antizapret")
    components_csv = env_value(env_map, "APP_BACKUP_COMPONENTS", "db,env,data")
    components = [item.strip().lower() for item in components_csv.split(",") if item.strip()]

    backup_service = BackupManagerService(
        app_root=app_root,
        backup_root=backup_root,
        service_name=service_name,
        retention_count=5,
    )
    panel_result = backup_service.create_backup(
        selected_components=components,
        trigger=trigger,
    )

    az_result = None
    az_error = ""
    if to_bool(env_value(env_map, "APP_BACKUP_AZ_ENABLED", "true")):
        try:
            az_result = create_az_backup(env_map)
        except Exception as exc:
            az_error = str(exc)
            logger.warning("AntiZapret backup (client.sh 8) failed: %s", exc)

    should_send = send_telegram
    if should_send is None:
        should_send = to_bool(env_value(env_map, "APP_BACKUP_TG_ENABLED", "false"))

    tg_sent = False
    tg_error = ""
    tg_notices = []
    documents_sent = 0
    tg_failed = 0
    tg_cleanup_dirs = []
    if should_send:
        ok, tg_error = validate_telegram_delivery(app_root, env_map)
        if ok:
            bot_token = env_value(env_map, "TELEGRAM_AUTH_BOT_TOKEN", "").strip()
            selected_admin_ids = [
                item.strip()
                for item in env_value(env_map, "APP_BACKUP_TG_ADMIN_IDS", "").split(",")
                if item.strip()
            ]
            chat_ids = load_admin_chat_ids(app_root, selected_admin_ids)
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            label = "Тестовый бэкап" if trigger == "test" else "Авто-бэкап"
            panel_documents, panel_notices, tg_cleanup_dirs = build_panel_telegram_documents(
                backup_service=backup_service,
                app_root=app_root,
                panel_result=panel_result,
                label=label,
                created_at=created_at,
            )
            tg_notices.extend(panel_notices)
            documents = list(panel_documents)
            if az_result and az_result.get("archive_path"):
                az_path = az_result["archive_path"]
                az_name = az_result.get("archive_name") or os.path.basename(az_path)
                if file_fits_telegram(az_path):
                    documents.append(
                        (
                            az_path,
                            f"{label} AntiZapret (VPN)\nФайл: {az_name}\nДата: {created_at}",
                        ),
                    )
                else:
                    tg_notices.append(
                        f"Бэкап AntiZapret ({human_size(os.path.getsize(az_path))}) не отправлен: "
                        f"лимит Telegram 50 МБ. Файл: {az_path}"
                    )
            try:
                tg_stats = send_backup_documents(
                    bot_token, chat_ids, documents, notices=tg_notices
                )
                documents_sent = tg_stats["sent"]
                tg_failed = tg_stats["failed"]
                tg_sent = documents_sent > 0 or bool(tg_notices)
            finally:
                for cleanup_dir in tg_cleanup_dirs:
                    shutil.rmtree(cleanup_dir, ignore_errors=True)

    summary_parts = [f"панель: {panel_result.get('archive_name', '')}"]
    if az_result:
        summary_parts.append(f"AZ: {az_result.get('archive_name', '')}")
    elif az_error:
        summary_parts.append(f"AZ: ошибка ({az_error})")
    if should_send:
        if tg_sent:
            summary_parts.append(f"Telegram: отправлено файлов {documents_sent}")
            if tg_failed:
                summary_parts.append(f"ошибок TG {tg_failed}")
            if tg_notices:
                summary_parts.append("уведомления о лимите 50 МБ")
        else:
            summary_parts.append(f"Telegram: не отправлено ({tg_error})")

    return {
        "panel": panel_result,
        "az": az_result,
        "az_error": az_error,
        "tg_sent": tg_sent,
        "tg_error": tg_error,
        "tg_notices": tg_notices,
        "documents_sent": documents_sent,
        "tg_failed": tg_failed,
        "summary": "; ".join(summary_parts),
    }
