import os
import platform
import re
import secrets
import subprocess
import threading
import ipaddress
from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from core.services.audit_view_presenter import (
    build_telegram_mini_audit_view,
    build_user_action_audit_view,
    build_user_action_sessions,
)
from core.services.cidr_list_updater import (
    analyze_dpi_log,
    estimate_cidr_matches,
    estimate_cidr_matches_from_db,
    get_available_game_filters,
    get_available_regions,
    get_saved_game_keys,
    rollback_to_baseline,
    sync_game_hosts_filter,
    update_cidr_files,
    update_cidr_files_from_db,
)
from config.antizapret_params import IP_FILES as _IP_FILES_META
from core.services.telegram_mini_session import has_telegram_mini_session
from core.services.tg_notify import send_tg_message


CIDR_TASKS = {}
CIDR_TASKS_LOCK = threading.Lock()
CIDR_TASK_RETENTION = timedelta(hours=2)
OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS = 900


def _clamp_total_cidr_limit_for_ios(value, default=OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return int(default)
    if parsed <= 0:
        return int(default)
    return min(parsed, OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)


def _cidr_now_utc():
    return datetime.utcnow()


def _cleanup_cidr_tasks():
    cutoff = _cidr_now_utc() - CIDR_TASK_RETENTION
    with CIDR_TASKS_LOCK:
        stale_task_ids = []
        for task_id, task in CIDR_TASKS.items():
            finished_at = task.get("finished_at")
            if not finished_at:
                continue
            if finished_at < cutoff:
                stale_task_ids.append(task_id)
        for task_id in stale_task_ids:
            CIDR_TASKS.pop(task_id, None)


def _create_cidr_task(task_type, message):
    _cleanup_cidr_tasks()
    task_id = secrets.token_hex(16)
    task = {
        "task_id": task_id,
        "task_type": task_type,
        "status": "queued",
        "message": str(message or "Задача поставлена в очередь"),
        "progress_percent": 0,
        "progress_stage": "Ожидание запуска...",
        "error": None,
        "result": None,
        "created_at": _cidr_now_utc(),
        "started_at": None,
        "finished_at": None,
        "updated_at": _cidr_now_utc(),
    }
    with CIDR_TASKS_LOCK:
        CIDR_TASKS[task_id] = task
    return task_id


def _update_cidr_task(task_id, **fields):
    with CIDR_TASKS_LOCK:
        task = CIDR_TASKS.get(task_id)
        if not task:
            return
        task.update(fields)
        task["updated_at"] = _cidr_now_utc()


def _get_cidr_task(task_id):
    with CIDR_TASKS_LOCK:
        task = CIDR_TASKS.get(task_id)
        if not task:
            return None
        return dict(task)


def _find_active_cidr_task(task_type):
    with CIDR_TASKS_LOCK:
        for task in CIDR_TASKS.values():
            if str(task.get("task_type") or "") != str(task_type or ""):
                continue
            if str(task.get("status") or "") in {"queued", "running"}:
                return dict(task)
    return None


def _serialize_cidr_task(task):
    payload = dict(task)
    for key in ("created_at", "started_at", "finished_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if isinstance(value, datetime) else None
    return payload


def register_settings_routes(
    app,
    *,
    auth_manager,
    db,
    user_model,
    active_web_session_model,
    qr_download_audit_log_model,
    telegram_mini_audit_log_model,
    user_action_log_model,
    ip_restriction,
    ip_manager,
    collect_all_openvpn_files_for_access,
    build_openvpn_access_groups,
    config_file_handler,
    group_folders,
    build_conf_access_groups,
    enqueue_background_task,
    task_restart_service,
    set_env_value,
    get_env_value,
    to_bool,
    is_valid_cron_expression,
    ensure_nightly_idle_restart_cron,
    get_nightly_idle_restart_settings,
    set_nightly_idle_restart_settings,
    get_active_web_session_settings,
    set_active_web_session_settings,
    get_public_download_enabled,
    log_telegram_audit_event,
    log_user_action_event,
    cidr_db_updater_service,
):
    def _start_cidr_task(task_id, runner):
        def _progress_callback(percent, stage):
            _update_cidr_task(
                task_id,
                status="running",
                progress_percent=max(0, min(99, int(percent))),
                progress_stage=str(stage or "Выполняется операция"),
                message=str(stage or "Выполняется операция"),
            )

        def _worker():
            _update_cidr_task(
                task_id,
                status="running",
                progress_percent=1,
                progress_stage="Подготовка...",
                started_at=_cidr_now_utc(),
            )
            try:
                with app.app_context():
                    result = runner(_progress_callback) or {}
                if not bool(result.get("success")):
                    _update_cidr_task(
                        task_id,
                        status="failed",
                        progress_percent=100,
                        progress_stage="Операция завершилась с ошибкой",
                        message=str(result.get("message") or "Операция завершилась с ошибкой"),
                        error=str(result.get("message") or "Операция завершилась с ошибкой"),
                        result=result,
                        finished_at=_cidr_now_utc(),
                    )
                    return

                _update_cidr_task(
                    task_id,
                    status="completed",
                    progress_percent=100,
                    progress_stage="Операция завершена",
                    message=str(result.get("message") or "Операция завершена"),
                    result=result,
                    error=None,
                    finished_at=_cidr_now_utc(),
                )
            except Exception as exc:  # noqa: BLE001
                _update_cidr_task(
                    task_id,
                    status="failed",
                    progress_percent=100,
                    progress_stage="Операция завершилась с ошибкой",
                    message="Операция завершилась с ошибкой",
                    error=str(exc),
                    finished_at=_cidr_now_utc(),
                )
                app.logger.exception("CIDR background task failed (%s): %s", task_id, exc)

        threading.Thread(target=_worker, daemon=True).start()

    def _has_telegram_mini_session() -> bool:
        return has_telegram_mini_session(session)

    def _normalize_telegram_id(raw_value):
        value = (raw_value or "").strip()
        if not value:
            return "", None
        if not re.fullmatch(r"^[1-9][0-9]{4,20}$", value):
            return None, "Telegram ID должен содержать только цифры (5..21 символ) и не начинаться с 0"
        return value, None

    def _normalize_telegram_bot_username(raw_value):
        value = (raw_value or "").strip().lstrip("@")
        if not value:
            return "", None
        if not re.fullmatch(r"^[A-Za-z0-9_]{5,64}$", value):
            return None, "Username Telegram-бота должен содержать 5..64 символа: латиница, цифры, _"
        return value, None

    def _normalize_telegram_bot_token(raw_value):
        value = (raw_value or "").strip()
        if not value:
            return "", None
        if not re.fullmatch(r"^[0-9]{6,12}:[A-Za-z0-9_-]{20,}$", value):
            return None, "Неверный формат токена Telegram-бота"
        return value, None

    def _normalize_ip_entry(raw_value):
        value = (raw_value or "").strip()
        if not value:
            return None
        try:
            if "/" in value:
                return str(ipaddress.ip_network(value, strict=False))
            return str(ipaddress.ip_address(value))
        except ValueError:
            return None

    def _nightly_time_from_cron(cron_expr):
        value = (cron_expr or "").strip()
        parts = value.split()
        if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit():
            minute_value = int(parts[0])
            hour_value = int(parts[1])
            if 0 <= minute_value <= 59 and 0 <= hour_value <= 23:
                return f"{hour_value:02d}:{minute_value:02d}"
        return "04:00"

    def _build_telegram_mini_audit_view(rows):
        return build_telegram_mini_audit_view(rows)

    def _build_user_action_audit_view(rows):
        return build_user_action_audit_view(rows)

    def _build_tg_mini_settings_payload():
        nightly_idle_restart_enabled, nightly_idle_restart_cron = get_nightly_idle_restart_settings()
        active_web_session_ttl_seconds, active_web_session_touch_interval_seconds = get_active_web_session_settings()

        telegram_auth_bot_username = get_env_value("TELEGRAM_AUTH_BOT_USERNAME", "")
        telegram_auth_max_age_seconds = get_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300")
        telegram_auth_bot_token_set = bool((get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip())
        telegram_auth_enabled = bool(telegram_auth_bot_username and telegram_auth_bot_token_set)

        return {
            "app_port": get_env_value("APP_PORT", os.getenv("APP_PORT", "5050")),
            "nightly_idle_restart_enabled": bool(nightly_idle_restart_enabled),
            "nightly_idle_restart_cron": nightly_idle_restart_cron,
            "nightly_idle_restart_time": _nightly_time_from_cron(nightly_idle_restart_cron),
            "active_web_session_ttl_seconds": int(active_web_session_ttl_seconds),
            "active_web_session_touch_interval_seconds": int(active_web_session_touch_interval_seconds),
            "telegram_auth_bot_username": telegram_auth_bot_username,
            "telegram_auth_max_age_seconds": int(telegram_auth_max_age_seconds or 300),
            "telegram_auth_bot_token_set": telegram_auth_bot_token_set,
            "telegram_auth_enabled": telegram_auth_enabled,
        }

    @app.route("/settings", methods=["GET", "POST"])
    @auth_manager.admin_required
    def settings():
        if request.method == "POST":
            new_port_raw = (request.form.get("port") or "").strip()
            if new_port_raw:
                if new_port_raw.isdigit() and 1 <= int(new_port_raw) <= 65535:
                    old_port = (get_env_value("APP_PORT", os.getenv("APP_PORT", "5050")) or "5050").strip()
                    set_env_value("APP_PORT", new_port_raw)
                    os.environ["APP_PORT"] = new_port_raw
                    flash("Порт успешно изменён. Перезапуск службы...", "success")
                    log_user_action_event(
                        "settings_port_update",
                        target_type="app",
                        target_name="APP_PORT",
                        details=f"{old_port} → {new_port_raw}",
                    )

                    try:
                        if platform.system() == "Linux":
                            subprocess.run(
                                ["systemctl", "restart", "admin-antizapret.service"], check=True
                            )
                    except subprocess.CalledProcessError as e:
                        flash(f"Ошибка при перезапуске службы: {e}", "error")
                else:
                    flash("Порт должен быть целым числом в диапазоне 1..65535", "error")

            ttl_raw = request.form.get("qr_download_token_ttl_seconds", "").strip()
            if ttl_raw:
                if ttl_raw.isdigit():
                    ttl_value = int(ttl_raw)
                    if 60 <= ttl_value <= 3600:
                        old_ttl = (get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600") or "600").strip()
                        set_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", str(ttl_value))
                        os.environ["QR_DOWNLOAD_TOKEN_TTL_SECONDS"] = str(ttl_value)
                        flash("TTL одноразовой QR-ссылки обновлен", "success")
                        log_user_action_event(
                            "settings_qr_ttl_update",
                            target_type="qr",
                            target_name="QR_DOWNLOAD_TOKEN_TTL_SECONDS",
                            details=f"{old_ttl} → {ttl_value}с",
                        )
                    else:
                        flash("TTL QR-ссылки должен быть в диапазоне 60..3600 секунд", "error")
                else:
                    flash("TTL QR-ссылки должен быть целым числом", "error")

            max_downloads_raw = request.form.get("qr_download_token_max_downloads", "").strip()
            if max_downloads_raw:
                if max_downloads_raw.isdigit() and int(max_downloads_raw) in (1, 3, 5):
                    old_max_dl = (get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1") or "1").strip()
                    set_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", max_downloads_raw)
                    os.environ["QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS"] = max_downloads_raw
                    flash("Лимит скачиваний одноразовой ссылки обновлен", "success")
                    log_user_action_event(
                        "settings_qr_max_downloads_update",
                        target_type="qr",
                        target_name="QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS",
                        details=f"{old_max_dl} → {max_downloads_raw}",
                    )
                else:
                    flash("Лимит скачиваний должен быть одним из значений: 1, 3 или 5", "error")

            clear_pin = request.form.get("clear_qr_download_pin") == "on"
            pin_raw = (request.form.get("qr_download_pin") or "").strip()
            if clear_pin:
                set_env_value("QR_DOWNLOAD_PIN", "")
                os.environ["QR_DOWNLOAD_PIN"] = ""
                flash("PIN для QR-ссылок очищен", "success")
                log_user_action_event(
                    "settings_qr_pin_clear",
                    target_type="qr",
                    target_name="QR_DOWNLOAD_PIN",
                )
            elif pin_raw:
                if pin_raw.isdigit() and 4 <= len(pin_raw) <= 12:
                    set_env_value("QR_DOWNLOAD_PIN", pin_raw)
                    os.environ["QR_DOWNLOAD_PIN"] = pin_raw
                    flash("PIN для QR-ссылок обновлен", "success")
                    log_user_action_event(
                        "settings_qr_pin_update",
                        target_type="qr",
                        target_name="QR_DOWNLOAD_PIN",
                        details=f"length={len(pin_raw)}",
                    )
                else:
                    flash("PIN должен содержать только цифры и иметь длину от 4 до 12", "error")

            if request.form.get("nightly_settings_action") == "save":
                nightly_enabled_raw = (request.form.get("nightly_idle_restart_enabled") or "true").strip().lower()
                nightly_enabled = to_bool(nightly_enabled_raw, default=True)

                ttl_raw = (request.form.get("active_web_session_ttl_seconds") or "").strip()
                touch_raw = (request.form.get("active_web_session_touch_interval_seconds") or "").strip()
                nightly_time_raw = (request.form.get("nightly_idle_restart_time") or "").strip()
                cron_expr_raw = (request.form.get("nightly_idle_restart_cron") or "").strip()

                has_error = False

                cron_expr = ""
                if nightly_time_raw:
                    time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", nightly_time_raw)
                    if time_match:
                        hour_value = int(time_match.group(1))
                        minute_value = int(time_match.group(2))
                        cron_expr = f"{minute_value} {hour_value} * * *"
                    else:
                        flash("Укажите время в формате ЧЧ:ММ (например, 04:00)", "error")
                        has_error = True

                if not cron_expr:
                    cron_expr = cron_expr_raw or "0 4 * * *"

                if not is_valid_cron_expression(cron_expr):
                    flash("Cron-выражение должно состоять из 5 полей и содержать только цифры и символы */,-", "error")
                    has_error = True

                active_ttl_seconds, active_touch_interval_seconds = get_active_web_session_settings()
                ttl_value = active_ttl_seconds
                if ttl_raw:
                    if ttl_raw.isdigit() and 30 <= int(ttl_raw) <= 86400:
                        ttl_value = int(ttl_raw)
                    else:
                        flash("TTL активной сессии должен быть целым числом в диапазоне 30..86400 секунд", "error")
                        has_error = True

                touch_value = active_touch_interval_seconds
                if touch_raw:
                    if touch_raw.isdigit() and 1 <= int(touch_raw) <= 3600:
                        touch_value = int(touch_raw)
                    else:
                        flash("Интервал heartbeat должен быть целым числом в диапазоне 1..3600 секунд", "error")
                        has_error = True

                if not has_error:
                    set_nightly_idle_restart_settings(nightly_enabled, cron_expr)
                    set_active_web_session_settings(ttl_value, touch_value)

                    env_enabled = "true" if nightly_enabled else "false"
                    set_env_value("NIGHTLY_IDLE_RESTART_ENABLED", env_enabled)
                    set_env_value("NIGHTLY_IDLE_RESTART_CRON", cron_expr)
                    set_env_value("ACTIVE_WEB_SESSION_TTL_SECONDS", str(ttl_value))
                    set_env_value("ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", str(touch_value))

                    os.environ["NIGHTLY_IDLE_RESTART_ENABLED"] = env_enabled
                    os.environ["NIGHTLY_IDLE_RESTART_CRON"] = cron_expr
                    os.environ["ACTIVE_WEB_SESSION_TTL_SECONDS"] = str(ttl_value)
                    os.environ["ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS"] = str(touch_value)

                    cron_ok, cron_msg = ensure_nightly_idle_restart_cron()
                    if cron_ok:
                        flash("Настройки ночного рестарта сохранены", "success")
                    else:
                        flash(cron_msg, "error")
                    log_user_action_event(
                        "settings_nightly_update",
                        target_type="maintenance",
                        target_name="nightly_idle_restart",
                        details=(
                            f"enabled={'вкл' if nightly_enabled else 'выкл'} "
                            f"cron={cron_expr} ttl={ttl_value}с touch={touch_value}с"
                        ),
                        status="success" if cron_ok else "warning",
                    )

            if request.form.get("telegram_auth_action") == "save":
                tg_username_raw = request.form.get("telegram_auth_bot_username", "")
                tg_token_raw = request.form.get("telegram_auth_bot_token", "")
                tg_max_age_raw = request.form.get("telegram_auth_max_age_seconds", "").strip()

                has_tg_error = False
                tg_username, username_error = _normalize_telegram_bot_username(tg_username_raw)
                if username_error:
                    flash(username_error, "error")
                    has_tg_error = True

                tg_max_age_value = 300
                if tg_max_age_raw:
                    if tg_max_age_raw.isdigit() and 30 <= int(tg_max_age_raw) <= 86400:
                        tg_max_age_value = int(tg_max_age_raw)
                    else:
                        flash("Срок действия Telegram авторизации должен быть в диапазоне 30..86400 секунд", "error")
                        has_tg_error = True

                existing_token = (get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
                token_to_apply = existing_token
                token_updated = False
                if (tg_token_raw or "").strip():
                    tg_token, token_error = _normalize_telegram_bot_token(tg_token_raw)
                    if token_error:
                        flash(token_error, "error")
                        has_tg_error = True
                    else:
                        token_to_apply = tg_token
                        token_updated = True

                if not has_tg_error:
                    set_env_value("TELEGRAM_AUTH_BOT_USERNAME", tg_username)
                    set_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", str(tg_max_age_value))
                    os.environ["TELEGRAM_AUTH_BOT_USERNAME"] = tg_username
                    os.environ["TELEGRAM_AUTH_MAX_AGE_SECONDS"] = str(tg_max_age_value)

                    if token_updated:
                        set_env_value("TELEGRAM_AUTH_BOT_TOKEN", token_to_apply)
                        os.environ["TELEGRAM_AUTH_BOT_TOKEN"] = token_to_apply

                    if token_to_apply:
                        if tg_username:
                            flash("Настройки Telegram авторизации обновлены. Telegram логин включен.", "success")
                        else:
                            flash("Токен сохранен, но Telegram логин выключен: не заполнен username бота.", "info")
                    else:
                        flash("Telegram логин выключен (токен бота пустой).", "success")
                    log_user_action_event(
                        "settings_telegram_auth_update",
                        target_type="telegram_auth",
                        target_name=(tg_username or "—"),
                        details=(
                            f"bot=@{tg_username or '—'} "
                            f"max_age={tg_max_age_value}с"
                            + (" токен обновлён" if token_updated else "")
                        ),
                    )

            username = request.form.get("username")
            password = request.form.get("password")
            if username and password:
                if len(password) < 8:
                    flash("Пароль должен содержать минимум 8 символов!", "error")
                else:
                    role = request.form.get("role", "admin")
                    if role not in ("admin", "viewer"):
                        role = "admin"
                    telegram_id_raw = request.form.get("telegram_id", "")
                    normalized_telegram_id, tg_error = _normalize_telegram_id(telegram_id_raw)

                    if tg_error:
                        flash(tg_error, "error")
                    elif user_model.query.filter_by(username=username).first():
                        flash(f"Пользователь '{username}' уже существует!", "error")
                    elif normalized_telegram_id and user_model.query.filter_by(telegram_id=normalized_telegram_id).first():
                        flash(f"Telegram ID {normalized_telegram_id} уже привязан к другому пользователю!", "error")
                    else:
                        user = user_model(
                            username=username,
                            role=role,
                            telegram_id=normalized_telegram_id or None,
                        )
                        user.set_password(password)
                        db.session.add(user)
                        db.session.commit()
                        flash(f"Пользователь '{username}' ({role}) успешно добавлен!", "success")
                        log_user_action_event(
                            "settings_user_create",
                            target_type="user",
                            target_name=username,
                            details=f"роль={role}" + (f" TG={normalized_telegram_id}" if normalized_telegram_id else ""),
                        )

            change_tg_notify_username = request.form.get("change_tg_notify_username")
            if change_tg_notify_username:
                import json as _json
                notify_user = user_model.query.filter_by(username=change_tg_notify_username).first()
                if notify_user:
                    _ev_keys = [
                        "login_success", "login_failed", "tg_unlinked",
                        "config_create", "config_delete",
                        "user_create", "user_delete",
                        "client_ban", "settings_change",
                        "high_cpu", "high_ram",
                    ]
                    events = {k: (request.form.get(f"tg_e_{k}") == "1") for k in _ev_keys}
                    notify_user.tg_notify_events = _json.dumps(events)
                    db.session.commit()
                    flash(f"Настройки уведомлений для '{change_tg_notify_username}' сохранены", "success")
                    log_user_action_event(
                        "settings_user_tg_notify_update",
                        target_type="user",
                        target_name=change_tg_notify_username,
                        details=_json.dumps({k: v for k, v in events.items() if v}),
                    )
                else:
                    flash(f"Пользователь '{change_tg_notify_username}' не найден!", "error")

            change_telegram_username = request.form.get("change_telegram_username")
            if change_telegram_username:
                tg_user = user_model.query.filter_by(username=change_telegram_username).first()
                if not tg_user:
                    flash(f"Пользователь '{change_telegram_username}' не найден!", "error")
                else:
                    new_telegram_id_raw = request.form.get("new_telegram_id", "")
                    normalized_telegram_id, tg_error = _normalize_telegram_id(new_telegram_id_raw)
                    if tg_error:
                        flash(tg_error, "error")
                    else:
                        if normalized_telegram_id:
                            owner = user_model.query.filter(
                                user_model.telegram_id == normalized_telegram_id,
                                user_model.username != change_telegram_username,
                            ).first()
                            if owner:
                                flash(
                                    f"Telegram ID {normalized_telegram_id} уже привязан к пользователю '{owner.username}'",
                                    "error",
                                )
                                return redirect(url_for("settings"))

                        old_telegram_id = tg_user.telegram_id or "—"
                        tg_user.telegram_id = normalized_telegram_id or None
                        db.session.commit()
                        if normalized_telegram_id:
                            flash(
                                f"Telegram ID пользователя '{change_telegram_username}' обновлён",
                                "success",
                            )
                        else:
                            flash(
                                f"Telegram ID пользователя '{change_telegram_username}' очищен",
                                "success",
                            )
                        log_user_action_event(
                            "settings_user_telegram_update",
                            target_type="user",
                            target_name=change_telegram_username,
                            details=f"{old_telegram_id} → {normalized_telegram_id or '—'}",
                        )

            delete_username = request.form.get("delete_username")
            if delete_username:
                if delete_username == session.get("username"):
                    flash("Нельзя удалить собственный аккаунт!", "error")
                else:
                    user = user_model.query.filter_by(username=delete_username).first()
                    if user:
                        db.session.delete(user)
                        db.session.commit()
                        flash(f"Пользователь '{delete_username}' успешно удалён!", "success")
                        log_user_action_event(
                            "settings_user_delete",
                            target_type="user",
                            target_name=delete_username,
                        )
                    else:
                        flash(f"Пользователь '{delete_username}' не найден!", "error")

            change_role_username = request.form.get("change_role_username")
            new_role = request.form.get("new_role")
            if change_role_username and new_role:
                if new_role not in ("admin", "viewer"):
                    flash("Неверная роль!", "error")
                elif change_role_username == session.get("username"):
                    flash("Нельзя изменить собственную роль!", "error")
                else:
                    role_user = user_model.query.filter_by(username=change_role_username).first()
                    if role_user:
                        old_role = role_user.role
                        role_user.role = new_role
                        db.session.commit()
                        flash(f"Роль пользователя '{change_role_username}' изменена на '{new_role}'!", "success")
                        log_user_action_event(
                            "settings_user_role_update",
                            target_type="user",
                            target_name=change_role_username,
                            details=f"{old_role} → {new_role}",
                        )
                    else:
                        flash(f"Пользователь '{change_role_username}' не найден!", "error")

            change_password_username = request.form.get("change_password_username")
            new_password = request.form.get("new_password")
            if change_password_username and new_password:
                if len(new_password) < 8:
                    flash("Пароль должен содержать минимум 8 символов!", "error")
                else:
                    pw_user = user_model.query.filter_by(username=change_password_username).first()
                    if pw_user:
                        pw_user.set_password(new_password)
                        db.session.commit()
                        flash(f"Пароль пользователя '{change_password_username}' изменён!", "success")
                        log_user_action_event(
                            "settings_user_password_update",
                            target_type="user",
                            target_name=change_password_username,
                            details="пароль изменён",
                        )
                    else:
                        flash(f"Пользователь '{change_password_username}' не найден!", "error")

            ip_action_values = request.form.getlist("ip_action")
            if "clear_scanner_bans" in ip_action_values:
                ip_action = "clear_scanner_bans"
            elif "unban_scanner_ip" in ip_action_values:
                ip_action = "unban_scanner_ip"
            else:
                ip_action = ip_action_values[0] if ip_action_values else request.form.get("ip_action")

            if ip_action == "add_ip":
                new_ip = request.form.get("new_ip", "").strip()
                if new_ip:
                    if ip_restriction.add_ip(new_ip):
                        flash(f"IP {new_ip} добавлен", "success")
                        log_user_action_event(
                            "settings_ip_add",
                            target_type="ip_restriction",
                            target_name=new_ip,
                        )
                    else:
                        flash("Неверный формат IP", "error")

            elif ip_action == "remove_ip":
                ip_to_remove = request.form.get("ip_to_remove", "").strip()
                if ip_to_remove:
                    if ip_restriction.remove_ip(ip_to_remove):
                        flash(f"IP {ip_to_remove} удален", "success")
                        log_user_action_event(
                            "settings_ip_remove",
                            target_type="ip_restriction",
                            target_name=ip_to_remove,
                        )
                    else:
                        flash("IP не найден", "error")

            elif ip_action == "clear_all_ips":
                ip_restriction.clear_all()
                flash("Все IP ограничения сброшены (доступ разрешен всем)", "success")
                log_user_action_event(
                    "settings_ip_clear",
                    target_type="ip_restriction",
                    target_name="all",
                )

            elif ip_action == "save_scanner_block":
                if not ip_restriction.is_enabled():
                    flash("Сначала включите IP-ограничения", "error")
                else:
                    block_scanners = request.form.get("block_scanners") == "true"
                    block_ip_blocked_dwell = request.form.get("block_ip_blocked_dwell") == "true"
                    try:
                        max_attempts = int(request.form.get("scanner_max_attempts", ip_restriction.scanner_max_attempts))
                        window_seconds = int(request.form.get("scanner_window_seconds", ip_restriction.scanner_window_seconds))
                        ban_seconds = int(request.form.get("scanner_ban_seconds", ip_restriction.scanner_ban_seconds))
                        ip_blocked_dwell_seconds = int(
                            request.form.get(
                                "ip_blocked_dwell_seconds",
                                ip_restriction.ip_blocked_dwell_seconds,
                            )
                        )
                    except (TypeError, ValueError):
                        flash("Некорректные параметры блокировки сканеров", "error")
                    else:
                        ip_restriction.set_scanner_protection(
                            enabled=block_scanners,
                            max_attempts=max_attempts,
                            window_seconds=window_seconds,
                            ban_seconds=ban_seconds,
                            block_ip_blocked_dwell=block_ip_blocked_dwell,
                            ip_blocked_dwell_seconds=ip_blocked_dwell_seconds,
                        )
                        state = "включена" if block_scanners else "выключена"
                        dwell_state = "включён" if block_ip_blocked_dwell else "выключен"
                        flash(
                            f"Защита от сканеров {state}. Бан за пребывание на странице блокировки: {dwell_state}.",
                            "success",
                        )
                        log_user_action_event(
                            "settings_ip_scanner_block",
                            target_type="ip_restriction",
                            target_name="scanner_block",
                            details=(
                                f"enabled={1 if block_scanners else 0};"
                                f"max={ip_restriction.scanner_max_attempts};"
                                f"window={ip_restriction.scanner_window_seconds};"
                                f"ban={ip_restriction.scanner_ban_seconds};"
                                f"dwell={1 if block_ip_blocked_dwell else 0};"
                                f"dwell_sec={ip_restriction.ip_blocked_dwell_seconds}"
                            ),
                        )

            elif ip_action == "clear_scanner_bans":
                ip_restriction.clear_scanner_bans()
                flash("Все баны сканеров сброшены (файл и iptables)", "success")
                log_user_action_event(
                    "settings_ip_scanner_bans_clear",
                    target_type="ip_restriction",
                    target_name="scanner_bans",
                )

            elif ip_action == "unban_scanner_ip":
                ip_to_unban = request.form.get("ip_to_unban", "").strip()
                if ip_to_unban:
                    if ip_restriction.unban_scanner_ip(ip_to_unban):
                        flash(
                            f"IP {ip_to_unban} разблокирован на сервере (iptables). "
                            f"Повторный серверный бан отложен — можно тестировать без whitelist.",
                            "success",
                        )
                        log_user_action_event(
                            "settings_ip_scanner_unban",
                            target_type="ip_restriction",
                            target_name=ip_to_unban,
                        )
                    else:
                        flash("Некорректный IP для разблокировки", "error")
                else:
                    flash("Укажите IP для разблокировки", "error")

            elif ip_action == "enable_ips":
                ips_text = request.form.get("ips_text", "").strip()
                if ips_text:
                    raw_entries = [ip.strip() for ip in ips_text.split(",") if ip.strip()]
                    normalized_entries = []
                    invalid_entries = []

                    for raw_entry in raw_entries:
                        normalized_entry = _normalize_ip_entry(raw_entry)
                        if normalized_entry is None:
                            invalid_entries.append(raw_entry)
                        else:
                            normalized_entries.append(normalized_entry)

                    if invalid_entries:
                        invalid_preview = ", ".join(invalid_entries[:5])
                        if len(invalid_entries) > 5:
                            invalid_preview += ", ..."
                        flash(
                            f"Обнаружены некорректные IP/подсети: {invalid_preview}. Исправьте список и повторите.",
                            "error",
                        )
                    elif not normalized_entries:
                        flash("Укажите хотя бы один корректный IP-адрес", "error")
                    else:
                        unique_entries = sorted(set(normalized_entries))
                        ip_restriction.allowed_ips = set(unique_entries)
                        ip_restriction.enabled = True
                        ip_restriction.save_to_env()
                        flash("IP ограничения включены", "success")
                        log_user_action_event(
                            "settings_ip_bulk_enable",
                            target_type="ip_restriction",
                            target_name="bulk",
                            details=f"entries={len(unique_entries)}",
                        )
                else:
                    flash("Укажите хотя бы один IP-адрес", "error")

            file_action = request.form.get("file_action")

            if file_action == "add_from_file":
                ip_file = request.form.get("ip_file", "").strip()
                if ip_file:
                    try:
                        added_count = ip_manager.add_from_file(ip_file)
                        flash(f"Добавлено {added_count} IP из файла {ip_file}", "success")
                        log_user_action_event(
                            "settings_ip_add_from_file",
                            target_type="ip_file",
                            target_name=ip_file,
                            details=f"count={added_count}",
                        )
                    except FileNotFoundError:
                        flash("Файл не найден", "error")
                    except Exception as e:
                        flash(f"Ошибка при добавлении IP: {e}", "error")
                else:
                    flash("Выберите файл", "error")

            elif file_action in ("enable_file", "disable_file"):
                ip_file = request.form.get("ip_file", "").strip()
                if ip_file:
                    try:
                        if file_action == "enable_file":
                            cnt = ip_manager.enable_file(ip_file)
                            flash(f"Добавлено {cnt} IP из файла {ip_file}", "success")
                        else:
                            cnt = ip_manager.disable_file(ip_file)
                            flash(f"Удалено {cnt} IP из файла {ip_file}", "success")
                        log_user_action_event(
                            "settings_ip_file_toggle",
                            target_type="ip_file",
                            target_name=ip_file,
                            details=f"action={file_action} count={cnt}",
                        )
                    except FileNotFoundError:
                        flash("Файл не найден", "error")
                    except Exception as e:
                        flash(f"Ошибка при обработке файла: {e}", "error")
                else:
                    flash("Не указан файл", "error")

            restart_action = request.form.get("restart_action")

            if restart_action == "restart_service":
                try:
                    task = enqueue_background_task(
                        "restart_service",
                        task_restart_service,
                        created_by_username=session.get("username"),
                        queued_message="Перезапуск службы поставлен в очередь",
                    )
                    flash(
                        f"Перезапуск службы запущен в фоне (task: {task.id[:8]}). Обновите страницу через 10-20 секунд.",
                        "info",
                    )
                    log_user_action_event(
                        "settings_restart_service",
                        target_type="service",
                        target_name="admin-antizapret.service",
                    )
                except Exception as e:
                    flash(f"Ошибка запуска фонового перезапуска: {str(e)}", "error")

            return redirect(url_for("settings"))

        current_port = os.getenv("APP_PORT", "5050")
        cidr_total_limit_raw = str(get_env_value("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)) or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)).strip()
        cidr_total_limit_raw = str(_clamp_total_cidr_limit_for_ios(cidr_total_limit_raw))
        qr_download_token_ttl_seconds = get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600")
        qr_download_token_max_downloads = get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1")
        qr_download_pin_set = bool((get_env_value("QR_DOWNLOAD_PIN", "") or "").strip())
        telegram_auth_bot_username = get_env_value("TELEGRAM_AUTH_BOT_USERNAME", "")
        telegram_auth_max_age_seconds = get_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300")
        telegram_auth_bot_token_set = bool((get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip())
        telegram_auth_enabled = bool(telegram_auth_bot_username and telegram_auth_bot_token_set)

        nightly_idle_restart_enabled, nightly_idle_restart_cron = get_nightly_idle_restart_settings()
        nightly_idle_restart_time = "04:00"
        cron_parts = (nightly_idle_restart_cron or "").split()
        if len(cron_parts) == 5 and cron_parts[0].isdigit() and cron_parts[1].isdigit():
            minute_value = int(cron_parts[0])
            hour_value = int(cron_parts[1])
            if 0 <= minute_value <= 59 and 0 <= hour_value <= 23:
                nightly_idle_restart_time = f"{hour_value:02d}:{minute_value:02d}"

        active_web_session_ttl_seconds, active_web_session_touch_interval_seconds = get_active_web_session_settings()
        active_web_sessions_count = active_web_session_model.query.filter(
            active_web_session_model.last_seen_at >= datetime.utcnow() - timedelta(seconds=active_web_session_ttl_seconds)
        ).count()

        qr_download_audit_logs = qr_download_audit_log_model.query.order_by(
            qr_download_audit_log_model.created_at.desc()
        ).limit(100).all()
        telegram_mini_audit_logs = telegram_mini_audit_log_model.query.order_by(
            telegram_mini_audit_log_model.created_at.desc()
        ).limit(200).all()
        telegram_mini_audit_view = _build_telegram_mini_audit_view(telegram_mini_audit_logs)
        user_action_logs = user_action_log_model.query.order_by(
            user_action_log_model.created_at.desc()
        ).limit(300).all()
        user_action_audit_view = _build_user_action_audit_view(user_action_logs)
        user_action_sessions = build_user_action_sessions(user_action_logs)
        users = user_model.query.all()
        viewer_users = user_model.query.filter_by(role="viewer").all()

        all_openvpn = collect_all_openvpn_files_for_access()
        openvpn_access_groups = build_openvpn_access_groups(all_openvpn)

        orig_paths = config_file_handler.config_paths["openvpn"]
        try:
            config_file_handler.config_paths["openvpn"] = [d for g in group_folders.values() for d in g]
            _, all_wg, all_amneziawg = config_file_handler.get_config_files()
        finally:
            config_file_handler.config_paths["openvpn"] = orig_paths

        wg_access_groups = build_conf_access_groups(all_wg, "wg")
        amneziawg_access_groups = build_conf_access_groups(all_amneziawg, "amneziawg")

        viewer_access = {vu.id: {acc.config_name for acc in vu.allowed_configs} for vu in viewer_users}

        allowed_ips = ip_restriction.get_allowed_ips()
        ip_enabled = ip_restriction.is_enabled()
        current_ip = ip_restriction.get_client_ip()
        scanner_settings = ip_restriction.get_scanner_settings()
        ip_block_scanners = scanner_settings["enabled"]
        ip_scanner_max_attempts = scanner_settings["max_attempts"]
        ip_scanner_window_seconds = scanner_settings["window_seconds"]
        ip_scanner_ban_seconds = scanner_settings["ban_seconds"]
        ip_scanner_active_bans = scanner_settings["active_bans"]
        ip_scanner_grace_entries = scanner_settings["grace_entries"]
        ip_scanner_has_firewall_entries = scanner_settings["has_firewall_entries"]
        ip_block_ip_blocked_dwell = scanner_settings["block_ip_blocked_dwell"]
        ip_blocked_dwell_seconds = scanner_settings["ip_blocked_dwell_seconds"]
        ip_scanner_strikes_for_year = scanner_settings["strikes_for_year"]
        ip_scanner_year_ban_seconds = scanner_settings["year_ban_seconds"]
        ip_scanner_unban_grace_seconds = scanner_settings["unban_grace_seconds"]
        ip_scanner_firewall_enabled = scanner_settings["firewall_enabled"]

        ip_manager.sync_enabled()
        ip_files = ip_manager.list_ip_files()
        ip_file_states = ip_manager.get_file_states()
        cidr_regions = get_available_regions()
        cidr_game_filters = get_available_game_filters()
        saved_game_keys = get_saved_game_keys()

        monitor_cpu_threshold = int((get_env_value("MONITOR_CPU_THRESHOLD", "90") or "90").strip())
        monitor_ram_threshold = int((get_env_value("MONITOR_RAM_THRESHOLD", "90") or "90").strip())
        monitor_interval_seconds = int((get_env_value("MONITOR_CHECK_INTERVAL_SECONDS", "60") or "60").strip())
        monitor_cooldown_minutes = int((get_env_value("MONITOR_COOLDOWN_MINUTES", "30") or "30").strip())

        return render_template(
            "settings.html",
            port=current_port,
            users=users,
            viewer_users=viewer_users,
            allowed_ips=allowed_ips,
            ip_enabled=ip_enabled,
            current_ip=current_ip,
            ip_block_scanners=ip_block_scanners,
            ip_scanner_max_attempts=ip_scanner_max_attempts,
            ip_scanner_window_seconds=ip_scanner_window_seconds,
            ip_scanner_ban_seconds=ip_scanner_ban_seconds,
            ip_scanner_active_bans=ip_scanner_active_bans,
            ip_scanner_grace_entries=ip_scanner_grace_entries,
            ip_scanner_has_firewall_entries=ip_scanner_has_firewall_entries,
            ip_block_ip_blocked_dwell=ip_block_ip_blocked_dwell,
            ip_blocked_dwell_seconds=ip_blocked_dwell_seconds,
            ip_scanner_strikes_for_year=ip_scanner_strikes_for_year,
            ip_scanner_year_ban_seconds=ip_scanner_year_ban_seconds,
            ip_scanner_unban_grace_seconds=ip_scanner_unban_grace_seconds,
            ip_scanner_firewall_enabled=ip_scanner_firewall_enabled,
            ip_files=ip_files,
            ip_file_states=ip_file_states,
            cidr_regions=cidr_regions,
            cidr_game_filters=cidr_game_filters,
            saved_game_keys=saved_game_keys,
            cidr_total_limit=cidr_total_limit_raw,
            all_openvpn=all_openvpn,
            openvpn_access_groups=openvpn_access_groups,
            all_wg=all_wg,
            all_amneziawg=all_amneziawg,
            wg_access_groups=wg_access_groups,
            amneziawg_access_groups=amneziawg_access_groups,
            viewer_access=viewer_access,
            public_download_enabled=get_public_download_enabled(),
            qr_download_token_ttl_seconds=qr_download_token_ttl_seconds,
            qr_download_token_max_downloads=qr_download_token_max_downloads,
            qr_download_pin_set=qr_download_pin_set,
            telegram_auth_bot_username=telegram_auth_bot_username,
            telegram_auth_max_age_seconds=telegram_auth_max_age_seconds,
            telegram_auth_bot_token_set=telegram_auth_bot_token_set,
            telegram_auth_enabled=telegram_auth_enabled,
            nightly_idle_restart_enabled=nightly_idle_restart_enabled,
            nightly_idle_restart_cron=nightly_idle_restart_cron,
            nightly_idle_restart_time=nightly_idle_restart_time,
            active_web_session_ttl_seconds=active_web_session_ttl_seconds,
            active_web_session_touch_interval_seconds=active_web_session_touch_interval_seconds,
            active_web_sessions_count=active_web_sessions_count,
            qr_download_audit_logs=qr_download_audit_logs,
            telegram_mini_audit_logs=telegram_mini_audit_view,
            user_action_audit_logs=user_action_audit_view,
            user_action_sessions=user_action_sessions,
            monitor_cpu_threshold=monitor_cpu_threshold,
            monitor_ram_threshold=monitor_ram_threshold,
            monitor_interval_seconds=monitor_interval_seconds,
            monitor_cooldown_minutes=monitor_cooldown_minutes,
        )

    @app.route("/api/antizapret/ip-files", methods=["GET", "POST"])
    @auth_manager.admin_required
    def api_antizapret_ip_files():
        if request.method == "GET":
            ip_manager.sync_enabled()
            return jsonify(
                {
                    "success": True,
                    "states": {k: bool(v) for k, v in ip_manager.get_file_states().items()},
                    "source_states": {k: bool(v) for k, v in ip_manager.get_source_states().items()},
                }
            )

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "").strip().lower()
        if action == "sync_with_list":
            ip_manager.sync_enabled()
            sync_result = ip_manager.sync_enabled_from_list()
            refreshed_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

            synced_files = int(sync_result.get("synced_files", 0))
            updated_files = int(sync_result.get("updated_files", 0))
            missing_sources = [str(item) for item in (sync_result.get("missing_sources") or [])]

            details_parts = [f"synced={synced_files}", f"updated={updated_files}"]
            if missing_sources:
                details_parts.append(f"missing={','.join(missing_sources[:5])}")

            log_user_action_event(
                "settings_ip_files_sync",
                target_type="ip_file",
                target_name="all_enabled",
                details=" ".join(details_parts),
            )

            if missing_sources:
                message = (
                    f"Сверка завершена: синхронизировано {synced_files}, обновлено {updated_files}. "
                    f"Не найдены исходные файлы: {', '.join(missing_sources)}"
                )
            else:
                message = (
                    f"Сверка завершена: синхронизировано {synced_files}, обновлено {updated_files}."
                )

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "synced_files": synced_files,
                    "updated_files": updated_files,
                    "missing_sources": missing_sources,
                    "states": refreshed_states,
                }
            )

        states = payload.get("states")
        if not isinstance(states, dict):
            return jsonify({"success": False, "message": "Ожидается поле states в формате объекта"}), 400

        ip_manager.sync_enabled()
        all_ip_files_meta = ip_manager.list_ip_files()
        available_files = set(all_ip_files_meta.keys())
        current_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

        changes_count = 0
        details = []

        for ip_file, raw_state in states.items():
            if ip_file not in available_files:
                continue

            desired_enabled = bool(raw_state)
            current_enabled = bool(current_states.get(ip_file, False))
            if desired_enabled == current_enabled:
                continue

            if desired_enabled:
                affected_count = ip_manager.enable_file(ip_file)
            else:
                affected_count = ip_manager.disable_file(ip_file)

            _meta = all_ip_files_meta.get(ip_file, {})
            _display = (_meta.get("name") if isinstance(_meta, dict) else None) \
                       or ip_file.replace(".txt", "").replace("-ips", "").replace("-", " ").title()

            changes_count += 1
            details.append(ip_file)

            log_user_action_event(
                "settings_ip_file_toggle",
                target_type="ip_file",
                target_name=ip_file,
                details=f"{'вкл' if desired_enabled else 'выкл'}|{_display}|{affected_count} IP",
            )

        refreshed_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

        return jsonify(
            {
                "success": True,
                "message": "Состояние IP-файлов сохранено" if changes_count else "Изменений в IP-файлах нет",
                "changes": changes_count,
                "states": refreshed_states,
                "details": details,
            }
        )

    @app.route("/api/cidr-lists", methods=["GET", "POST"])
    @auth_manager.admin_required
    def api_cidr_lists():
        if request.method == "GET":
            current_total_limit = str(get_env_value("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)) or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)).strip()
            current_total_limit = str(_clamp_total_cidr_limit_for_ios(current_total_limit))
            return jsonify(
                {
                    "success": True,
                    "regions": get_available_regions(),
                    "game_filters": get_available_game_filters(),
                    "settings": {
                        "openvpn_route_total_cidr_limit": int(current_total_limit),
                        "openvpn_route_total_cidr_limit_max": OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS,
                    },
                }
            )

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "").strip().lower()
        selected = payload.get("regions")
        selected_files = [str(item) for item in selected] if isinstance(selected, list) else None
        region_scopes_raw = payload.get("region_scopes")
        if isinstance(region_scopes_raw, list):
            region_scopes = [str(item).strip().lower() for item in region_scopes_raw if str(item).strip()]
        else:
            legacy_scope = str(payload.get("region_scope") or "all").strip().lower() or "all"
            region_scopes = [legacy_scope]

        include_non_geo_fallback = bool(payload.get("include_non_geo_fallback", False))
        exclude_ru_cidrs = bool(payload.get("exclude_ru_cidrs", False))
        include_game_hosts = bool(payload.get("include_game_hosts", False))
        include_game_keys_raw = payload.get("include_game_keys")
        if isinstance(include_game_keys_raw, list):
            include_game_keys = [str(item).strip().lower() for item in include_game_keys_raw if str(item).strip()]
        else:
            include_game_keys = []
        strict_geo_filter = bool(payload.get("strict_geo_filter", False))
        dpi_priority_files_raw = payload.get("dpi_priority_files")
        if isinstance(dpi_priority_files_raw, list):
            dpi_priority_files = [str(item).strip() for item in dpi_priority_files_raw if str(item).strip()]
        else:
            dpi_priority_files = []
        dpi_mandatory_files_raw = payload.get("dpi_mandatory_files")
        if isinstance(dpi_mandatory_files_raw, list):
            dpi_mandatory_files = [str(item).strip() for item in dpi_mandatory_files_raw if str(item).strip()]
        else:
            dpi_mandatory_files = []
        try:
            dpi_priority_min_budget = int(payload.get("dpi_priority_min_budget") or 0)
        except (TypeError, ValueError):
            dpi_priority_min_budget = 0

        if action == "analyze_dpi_log":
            dpi_log_text = str(payload.get("dpi_log_text") or "")
            result = analyze_dpi_log(dpi_log_text)
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "set_total_limit":
            raw_limit = str(payload.get("openvpn_route_total_cidr_limit") or "").strip()
            if not raw_limit.isdigit():
                return jsonify({"success": False, "message": "Лимит CIDR должен быть целым числом"}), 400

            limit_value = int(raw_limit)
            if limit_value <= 0 or limit_value > OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS:
                return jsonify({"success": False, "message": f"Лимит CIDR должен быть в диапазоне 1..{OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS} (ограничение iOS)"}), 400

            old_cidr_limit = (get_env_value("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)) or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)).strip()
            set_env_value("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", str(limit_value))
            os.environ["OPENVPN_ROUTE_TOTAL_CIDR_LIMIT"] = str(limit_value)

            log_user_action_event(
                "settings_cidr_total_limit_update",
                target_type="cidr",
                target_name="OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
                details=f"{old_cidr_limit} → {limit_value}",
                status="success",
            )

            return jsonify(
                {
                    "success": True,
                    "message": f"Общий лимит CIDR сохранен: {limit_value}",
                    "openvpn_route_total_cidr_limit": limit_value,
                }
            )

        if action == "sync_games_hosts":
            result = sync_game_hosts_filter(
                include_game_hosts=include_game_hosts,
                include_game_keys=include_game_keys,
            )
            if result.get("success"):
                game_hosts_filter = result.get("game_hosts_filter") or {}
                game_ips_filter = result.get("game_ips_filter") or {}
                log_user_action_event(
                    "settings_cidr_games_sync",
                    target_type="cidr",
                    target_name="include-hosts",
                    details=(
                        f"enabled={1 if game_hosts_filter.get('enabled') else 0} "
                        f"selected_games={int(game_hosts_filter.get('selected_game_count') or 0)} "
                        f"domains={int(game_hosts_filter.get('domain_count') or 0)} "
                        f"cidrs={int(game_ips_filter.get('cidr_count') or 0)}"
                    ),
                    status="success",
                )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "update":
            scopes_text = ",".join(region_scopes or ["all"])

            task_id = _create_cidr_task(
                "cidr_update",
                "Обновление CIDR-файлов поставлено в очередь",
            )

            def _runner(progress_callback):
                result = update_cidr_files(
                    selected_files,
                    region_scopes=region_scopes,
                    include_non_geo_fallback=include_non_geo_fallback,
                    exclude_ru_cidrs=exclude_ru_cidrs,
                    include_game_hosts=include_game_hosts,
                    include_game_keys=include_game_keys,
                    strict_geo_filter=strict_geo_filter,
                    dpi_priority_files=dpi_priority_files,
                    dpi_mandatory_files=dpi_mandatory_files,
                    dpi_priority_min_budget=dpi_priority_min_budget,
                    progress_callback=progress_callback,
                )
                # Keep AP-* files in antizapret/config in sync with freshly generated
                # ips/list/ files so that doall.sh (run separately) reads current data.
                if result.get("success") or result.get("updated"):
                    ip_manager.sync_enabled_from_list()
                return result

            _start_cidr_task(task_id, _runner)

            _files_label = "все файлы" if not selected_files else ", ".join(selected_files[:5]) + ("…" if len(selected_files) > 5 else "")
            log_user_action_event(
                "settings_cidr_update_queued",
                target_type="cidr",
                target_name="all" if not selected_files else ",".join(selected_files[:10]),
                details=(
                    f"файлы: {_files_label}; "
                    f"регионы: {scopes_text}; "
                    + (f"игры: {len(include_game_keys)}; " if include_game_hosts else "")
                    + (f"exclude_ru; " if exclude_ru_cidrs else "")
                    + (f"strict_geo" if strict_geo_filter else "")
                ).rstrip("; "),
                status="info",
            )
            return (
                jsonify(
                    {
                        "success": True,
                        "queued": True,
                        "task_id": task_id,
                        "message": "Обновление CIDR-файлов запущено в фоне",
                        "status_url": url_for("api_cidr_task_status", task_id=task_id),
                    }
                ),
                202,
            )

        if action == "estimate":
            result = estimate_cidr_matches(
                selected_files,
                region_scopes=region_scopes,
                include_non_geo_fallback=include_non_geo_fallback,
                exclude_ru_cidrs=exclude_ru_cidrs,
                include_game_hosts=include_game_hosts,
                include_game_keys=include_game_keys,
                strict_geo_filter=strict_geo_filter,
                dpi_priority_files=dpi_priority_files,
                dpi_mandatory_files=dpi_mandatory_files,
                dpi_priority_min_budget=dpi_priority_min_budget,
            )
            return jsonify(result), (200 if result.get("success") else 400)

        if action == "rollback":
            task_id = _create_cidr_task(
                "cidr_rollback",
                "Откат CIDR-файлов поставлен в очередь",
            )

            def _runner(progress_callback):
                return rollback_to_baseline(selected_files, progress_callback=progress_callback)

            _start_cidr_task(task_id, _runner)

            _rollback_files_label = "все файлы" if not selected_files else ", ".join(selected_files[:5]) + ("…" if len(selected_files) > 5 else "")
            log_user_action_event(
                "settings_cidr_rollback_queued",
                target_type="cidr",
                target_name="all" if not selected_files else ",".join(selected_files[:10]),
                details=f"файлы: {_rollback_files_label}",
                status="info",
            )
            return (
                jsonify(
                    {
                        "success": True,
                        "queued": True,
                        "task_id": task_id,
                        "message": "Откат CIDR-файлов запущен в фоне",
                        "status_url": url_for("api_cidr_task_status", task_id=task_id),
                    }
                ),
                202,
            )

        return jsonify({"success": False, "message": "Неизвестное действие"}), 400

    @app.route("/api/cidr-lists/task/<task_id>", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_task_status(task_id):
        task = _get_cidr_task(task_id)
        if not task:
            return jsonify({"success": False, "message": "Задача CIDR не найдена"}), 404

        payload = _serialize_cidr_task(task)
        payload["success"] = True
        return jsonify(payload)

    # ── CIDR DB: статус, ручное обновление, история ──────────────────────────

    @app.route("/api/cidr-db/status", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_db_status():
        status = cidr_db_updater_service.get_db_status()
        history = cidr_db_updater_service.get_refresh_history(limit=5)
        provider_meta = {}
        for key, info in status.get("providers", {}).items():
            meta = _IP_FILES_META.get(key, {})
            dynamic_asns = info.get("active_asns") or []
            provider_meta[key] = {
                **info,
                "name": meta.get("name", key),
                "as_numbers": dynamic_asns or meta.get("as_numbers", []),
                "configured_as_numbers": meta.get("as_numbers", []),
                "category": meta.get("category", ""),
                "what_hosts": meta.get("what_hosts", ""),
                "tags": meta.get("tags", []),
            }
        return jsonify({
            "success": True,
            "last_refresh_started": status.get("last_refresh_started"),
            "last_refresh_finished": status.get("last_refresh_finished"),
            "last_refresh_status": status.get("last_refresh_status"),
            "last_refresh_triggered_by": status.get("last_refresh_triggered_by"),
            "total_cidrs": status.get("total_cidrs"),
            "providers": provider_meta,
            "alerts": status.get("alerts", []),
            "history": history,
        })

    @app.route("/api/cidr-db/refresh", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_db_refresh():
        payload = request.get_json(silent=True) or {}
        selected_files = payload.get("selected_files") or None
        if isinstance(selected_files, list):
            selected_files = [str(f) for f in selected_files] or None

        triggered_by = f"manual:{session.get('username', 'unknown')}"

        task_id = _create_cidr_task("cidr_db_refresh", "Обновление CIDR БД запущено в фоне")

        def _runner(progress_callback):
            return cidr_db_updater_service.refresh_all_providers(
                triggered_by=triggered_by,
                selected_files=selected_files,
                progress_callback=progress_callback,
            )

        _start_cidr_task(task_id, _runner)

        _db_files_label = "все файлы" if not selected_files else ", ".join((selected_files or [])[:5]) + ("…" if len(selected_files or []) > 5 else "")
        log_user_action_event(
            "settings_cidr_db_refresh_queued",
            target_type="cidr_db",
            target_name="all" if not selected_files else ",".join((selected_files or [])[:10]),
            details=f"файлы: {_db_files_label}",
            status="info",
        )
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Обновление CIDR БД запущено в фоне",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

    @app.route("/api/cidr-db/generate", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_db_generate():
        """Generate .txt route files from DB data (no download)."""
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "generate").strip().lower()
        selected = payload.get("regions")
        selected_files = [str(item) for item in selected] if isinstance(selected, list) else None
        region_scopes_raw = payload.get("region_scopes")
        if isinstance(region_scopes_raw, list):
            region_scopes = [str(item).strip().lower() for item in region_scopes_raw if str(item).strip()]
        else:
            region_scopes = [str(payload.get("region_scope") or "all").strip().lower() or "all"]
        include_non_geo_fallback = bool(payload.get("include_non_geo_fallback", False))
        exclude_ru_cidrs = bool(payload.get("exclude_ru_cidrs", False))
        include_game_hosts = bool(payload.get("include_game_hosts", False))
        include_game_keys_raw = payload.get("include_game_keys")
        include_game_keys = [str(k).strip().lower() for k in include_game_keys_raw if str(k).strip()] if isinstance(include_game_keys_raw, list) else []
        strict_geo_filter = bool(payload.get("strict_geo_filter", False))
        filter_by_antifilter = bool(payload.get("filter_by_antifilter", False))
        dpi_priority_files_raw = payload.get("dpi_priority_files")
        if isinstance(dpi_priority_files_raw, list):
            dpi_priority_files = [str(item).strip() for item in dpi_priority_files_raw if str(item).strip()]
        else:
            dpi_priority_files = []
        dpi_mandatory_files_raw = payload.get("dpi_mandatory_files")
        if isinstance(dpi_mandatory_files_raw, list):
            dpi_mandatory_files = [str(item).strip() for item in dpi_mandatory_files_raw if str(item).strip()]
        else:
            dpi_mandatory_files = []
        try:
            dpi_priority_min_budget = int(payload.get("dpi_priority_min_budget") or 0)
        except (TypeError, ValueError):
            dpi_priority_min_budget = 0
        # Use None so update_cidr_files_from_db reads OPENVPN_ROUTE_TOTAL_CIDR_LIMIT
        # from the .env file at runtime (respects the value saved via the UI).
        route_limit = None

        if action == "estimate":
            active_task = _find_active_cidr_task("cidr_estimate_from_db")
            if active_task:
                return jsonify({
                    "success": True,
                    "queued": True,
                    "task_id": active_task.get("task_id"),
                    "message": "Оценка CIDR из БД уже выполняется",
                    "status_url": url_for("api_cidr_task_status", task_id=active_task.get("task_id")),
                }), 202

            task_id = _create_cidr_task("cidr_estimate_from_db", "Оценка CIDR из БД запущена")

            def _estimate_runner(progress_callback):
                return estimate_cidr_matches_from_db(
                    selected_files,
                    region_scopes=region_scopes,
                    include_non_geo_fallback=include_non_geo_fallback,
                    exclude_ru_cidrs=exclude_ru_cidrs,
                    include_game_hosts=include_game_hosts,
                    include_game_keys=include_game_keys,
                    strict_geo_filter=strict_geo_filter,
                    filter_by_antifilter=filter_by_antifilter,
                    total_cidr_limit=route_limit,
                    dpi_priority_files=dpi_priority_files,
                    dpi_mandatory_files=dpi_mandatory_files,
                    dpi_priority_min_budget=dpi_priority_min_budget,
                    progress_callback=progress_callback,
                )

            _start_cidr_task(task_id, _estimate_runner)

            return jsonify({
                "success": True,
                "queued": True,
                "task_id": task_id,
                "message": "Оценка CIDR из БД запущена",
                "status_url": url_for("api_cidr_task_status", task_id=task_id),
            }), 202

        task_id = _create_cidr_task("cidr_generate_from_db", "Генерация CIDR-файлов из БД запущена")

        def _runner(progress_callback):
            result = update_cidr_files_from_db(
                selected_files,
                region_scopes=region_scopes,
                include_non_geo_fallback=include_non_geo_fallback,
                exclude_ru_cidrs=exclude_ru_cidrs,
                include_game_hosts=include_game_hosts,
                include_game_keys=include_game_keys,
                strict_geo_filter=strict_geo_filter,
                filter_by_antifilter=filter_by_antifilter,
                total_cidr_limit=route_limit,
                dpi_priority_files=dpi_priority_files,
                dpi_mandatory_files=dpi_mandatory_files,
                dpi_priority_min_budget=dpi_priority_min_budget,
                progress_callback=progress_callback,
            )
            # Sync newly generated ips/list/ files into antizapret/config/AP-* so
            # that the subsequent doall.sh call picks up the fresh data.
            # update.sh reads config/*include-ips.txt, not ips/list/ directly.
            if result.get("success") or result.get("updated"):
                ip_manager.sync_enabled_from_list()
            return result

        _start_cidr_task(task_id, _runner)

        _gen_files_label = "все файлы" if not selected_files else ", ".join((selected_files or [])[:5]) + ("…" if len(selected_files or []) > 5 else "")
        log_user_action_event(
            "settings_cidr_generate_from_db",
            target_type="cidr",
            target_name="all" if not selected_files else ",".join((selected_files or [])[:10]),
            details=(
                f"файлы: {_gen_files_label}; регионы: {','.join(region_scopes)}"
                + ("; без РУ" if exclude_ru_cidrs else "")
            ),
            status="info",
        )
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Генерация CIDR-файлов из БД запущена",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

    # ── CIDR Presets ──────────────────────────────────────────────────────────

    @app.route("/api/cidr-presets", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_presets_list():
        presets = cidr_db_updater_service.get_presets()
        for preset in presets:
            for prov_key in preset.get("providers", []):
                meta = _IP_FILES_META.get(prov_key, {})
                preset.setdefault("providers_meta", {})[prov_key] = {
                    "name": meta.get("name", prov_key),
                    "category": meta.get("category", ""),
                    "tags": meta.get("tags", []),
                }
        return jsonify({"success": True, "presets": presets})

    @app.route("/api/cidr-presets", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_presets_create():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "message": "Необходимо указать имя пресета"}), 400
        providers = data.get("providers")
        if not isinstance(providers, list):
            return jsonify({"success": False, "message": "Необходимо указать список провайдеров"}), 400
        preset = cidr_db_updater_service.create_preset(
            name=name,
            description=str(data.get("description") or ""),
            providers=providers,
            settings=data.get("settings"),
        )
        log_user_action_event("settings_cidr_preset_create", target_type="cidr_preset", target_name=name, status="success")
        return jsonify({"success": True, "preset": preset}), 201

    @app.route("/api/cidr-presets/<int:preset_id>", methods=["PUT"])
    @auth_manager.admin_required
    def api_cidr_presets_update(preset_id):
        data = request.get_json(silent=True) or {}
        preset = cidr_db_updater_service.update_preset(
            preset_id,
            name=str(data["name"]).strip() if "name" in data else None,
            description=str(data.get("description") or "") if "description" in data else None,
            providers=data["providers"] if "providers" in data else None,
            settings=data.get("settings") if "settings" in data else None,
        )
        if not preset:
            return jsonify({"success": False, "message": "Пресет не найден"}), 404
        log_user_action_event("settings_cidr_preset_update", target_type="cidr_preset", target_name=str(preset_id), status="success")
        return jsonify({"success": True, "preset": preset})

    @app.route("/api/cidr-presets/<int:preset_id>", methods=["DELETE"])
    @auth_manager.admin_required
    def api_cidr_presets_delete(preset_id):
        ok, msg = cidr_db_updater_service.delete_preset(preset_id)
        if not ok:
            return jsonify({"success": False, "message": msg}), 400
        log_user_action_event("settings_cidr_preset_delete", target_type="cidr_preset", target_name=str(preset_id), status="success")
        return jsonify({"success": True, "message": msg})

    @app.route("/api/cidr-presets/<int:preset_id>/reset", methods=["POST"])
    @auth_manager.admin_required
    def api_cidr_presets_reset(preset_id):
        preset = cidr_db_updater_service.reset_builtin_preset(preset_id)
        if not preset:
            return jsonify({"success": False, "message": "Встроенный пресет не найден"}), 404
        log_user_action_event("settings_cidr_preset_reset", target_type="cidr_preset", target_name=str(preset_id), status="success")
        return jsonify({"success": True, "preset": preset})

    # ── Provider info ─────────────────────────────────────────────────────────

    @app.route("/api/cidr-providers/meta", methods=["GET"])
    @auth_manager.admin_required
    def api_cidr_providers_meta():
        result = {}
        for key, meta in _IP_FILES_META.items():
            result[key] = {
                "name": meta.get("name", key),
                "description": meta.get("description", ""),
                "as_numbers": meta.get("as_numbers", []),
                "category": meta.get("category", ""),
                "what_hosts": meta.get("what_hosts", ""),
                "tags": meta.get("tags", []),
            }
        return jsonify({"success": True, "providers": result})

    # ── Antifilter.download ───────────────────────────────────────────────────

    @app.route("/api/antifilter/status", methods=["GET"])
    @auth_manager.admin_required
    def api_antifilter_status():
        status = cidr_db_updater_service.get_antifilter_status()
        return jsonify({"success": True, **status})

    @app.route("/api/antifilter/refresh", methods=["POST"])
    @auth_manager.admin_required
    def api_antifilter_refresh():
        task_id = _create_cidr_task("antifilter_refresh", "Обновление антифильтра запущено в фоне")
        _triggered_by = f"manual:{session.get('username', 'unknown')}"

        def _runner(progress_callback):
            return cidr_db_updater_service.refresh_antifilter(
                triggered_by=_triggered_by,
                progress_callback=progress_callback,
            )

        _start_cidr_task(task_id, _runner)
        log_user_action_event("settings_antifilter_refresh", target_type="antifilter", target_name="antifilter.download", status="info")
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Обновление антифильтра запущено в фоне (~1–2 минуты)",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

    @app.route("/api/tg-mini/settings", methods=["GET"])
    @auth_manager.admin_required
    def api_tg_mini_settings_get():
        if not _has_telegram_mini_session():
            return jsonify({"success": False, "message": "Доступ разрешён только из Telegram Mini App."}), 403
        return jsonify({"success": True, "settings": _build_tg_mini_settings_payload()})

    def _tests_subprocess_env(app_root_dir):
        import sys as _sys
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = app_root_dir + (":" + existing if existing else "")
        return env

    @app.route("/api/tests/collect", methods=["GET"])
    @auth_manager.admin_required
    def api_tests_collect():
        app_root_dir = os.path.dirname(os.path.dirname(__file__))
        venv_pytest = os.path.join(app_root_dir, "venv", "bin", "pytest")
        if not os.path.isfile(venv_pytest):
            venv_pytest = "pytest"
        tests_dir = os.path.join(app_root_dir, "tests")
        try:
            proc = subprocess.run(
                [venv_pytest, "--collect-only", "-q", "--no-header", tests_dir],
                capture_output=True, text=True, timeout=30, cwd=app_root_dir,
                env=_tests_subprocess_env(app_root_dir),
            )
            lines = (proc.stdout + proc.stderr).strip().splitlines()
            tests = []
            seen = set()
            for line in lines:
                stripped = line.strip()
                if "::" not in stripped or stripped.startswith("="):
                    continue
                if stripped not in seen:
                    seen.add(stripped)
                    tests.append(stripped)
            if proc.returncode != 0 and not tests:
                err = (proc.stderr or proc.stdout or "").strip() or f"pytest exit {proc.returncode}"
                return jsonify({"success": False, "message": err}), 500
            tests.sort()
            return jsonify({
                "success": True,
                "tests": tests,
                "count": len(tests),
                "collect_warnings": proc.returncode != 0,
            })
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    @app.route("/api/tests/run", methods=["POST"])
    @auth_manager.admin_required
    def api_tests_run():
        payload = request.get_json(silent=True) or {}
        test_ids = [str(t) for t in (payload.get("test_ids") or []) if t]

        app_root_dir = os.path.dirname(os.path.dirname(__file__))
        venv_pytest = os.path.join(app_root_dir, "venv", "bin", "pytest")
        if not os.path.isfile(venv_pytest):
            venv_pytest = "pytest"
        tests_dir = os.path.join(app_root_dir, "tests")

        active = _find_active_cidr_task("pytest_run")
        if active:
            return jsonify({
                "success": True,
                "queued": True,
                "task_id": active.get("task_id"),
                "message": "Тесты уже выполняются",
                "status_url": url_for("api_cidr_task_status", task_id=active.get("task_id")),
            }), 202

        task_id = _create_cidr_task("pytest_run", "Запуск тестов...")

        def _runner(progress_callback):
            progress_callback(5, "Запуск pytest...")
            cmd = [
                venv_pytest,
                "-v",
                "--tb=short",
                "--no-header",
                "--color=no",
            ]
            if test_ids:
                cmd.extend(test_ids)
            else:
                cmd.append(tests_dir)

            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300, cwd=app_root_dir,
                    env=_tests_subprocess_env(app_root_dir),
                )
                output = proc.stdout + (proc.stderr or "")
                progress_callback(90, "Разбор результатов...")

                tests_result = []
                passed = failed = errors = skipped = 0
                for line in output.splitlines():
                    stripped = line.strip()
                    if "::" not in stripped:
                        continue
                    if " PASSED" in stripped:
                        test_id = stripped.split(" PASSED")[0].strip()
                        tests_result.append({"id": test_id, "status": "passed"})
                        passed += 1
                    elif " FAILED" in stripped:
                        test_id = stripped.split(" FAILED")[0].strip()
                        tests_result.append({"id": test_id, "status": "failed"})
                        failed += 1
                    elif " ERROR" in stripped:
                        test_id = stripped.split(" ERROR")[0].strip()
                        tests_result.append({"id": test_id, "status": "error"})
                        errors += 1
                    elif " SKIPPED" in stripped:
                        test_id = stripped.split(" SKIPPED")[0].strip()
                        tests_result.append({"id": test_id, "status": "skipped"})
                        skipped += 1

                total = passed + failed + errors + skipped
                success = proc.returncode == 0
                problems = failed + errors
                return {
                    "success": success,
                    "message": (
                        f"Выполнено {total}: {passed} прошло"
                        + (f", {problems} с ошибками" if problems else "")
                        + (f", {skipped} пропущено" if skipped else "")
                    ),
                    "summary": {
                        "passed": passed,
                        "failed": failed,
                        "error": errors,
                        "skipped": skipped,
                        "total": total,
                    },
                    "tests": tests_result,
                    "raw_output": output,
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "Таймаут выполнения тестов (300 сек)"}
            except Exception as exc:
                return {"success": False, "message": str(exc)}

        _start_cidr_task(task_id, _runner)
        log_user_action_event(
            "settings_tests_run",
            target_type="tests",
            target_name="pytest",
            details=f"count={'all' if not test_ids else len(test_ids)}",
        )
        return jsonify({
            "success": True,
            "queued": True,
            "task_id": task_id,
            "message": "Тесты запущены в фоне",
            "status_url": url_for("api_cidr_task_status", task_id=task_id),
        }), 202

    @app.route("/api/monitor-settings", methods=["POST"])
    @auth_manager.admin_required
    def api_monitor_settings():
        data = request.get_json(silent=True) or {}

        def _int_clamp(val, lo, hi, default):
            try:
                v = int(str(val).strip())
                return max(lo, min(hi, v))
            except (TypeError, ValueError):
                return default

        cpu_threshold = _int_clamp(data.get("cpu_threshold"), 1, 100, 90)
        ram_threshold = _int_clamp(data.get("ram_threshold"), 1, 100, 90)
        interval_sec  = _int_clamp(data.get("interval_seconds"), 10, 3600, 60)
        cooldown_min  = _int_clamp(data.get("cooldown_minutes"), 1, 1440, 30)

        set_env_value("MONITOR_CPU_THRESHOLD", str(cpu_threshold))
        set_env_value("MONITOR_RAM_THRESHOLD", str(ram_threshold))
        set_env_value("MONITOR_CHECK_INTERVAL_SECONDS", str(interval_sec))
        set_env_value("MONITOR_COOLDOWN_MINUTES", str(cooldown_min))
        os.environ["MONITOR_CPU_THRESHOLD"] = str(cpu_threshold)
        os.environ["MONITOR_RAM_THRESHOLD"] = str(ram_threshold)
        os.environ["MONITOR_CHECK_INTERVAL_SECONDS"] = str(interval_sec)
        os.environ["MONITOR_COOLDOWN_MINUTES"] = str(cooldown_min)

        log_user_action_event(
            "settings_monitor_update",
            target_type="monitor",
            target_name="resource_monitor",
            details=f"cpu={cpu_threshold}% ram={ram_threshold}% interval={interval_sec}с cooldown={cooldown_min}мин",
        )
        return jsonify({"success": True, "message": "Настройки мониторинга сохранены"})

    @app.route("/api/tg-notify-test", methods=["POST"])
    @auth_manager.admin_required
    def api_tg_notify_test():
        data = request.get_json(silent=True) or {}
        target_username = (data.get("username") or "").strip()
        current_username = session.get("username", "")
        if not target_username or target_username != current_username:
            return jsonify({"success": False, "message": "Тест разрешён только для собственного аккаунта"}), 403

        user = user_model.query.filter_by(username=target_username).first()
        if not user or not user.telegram_id:
            return jsonify({"success": False, "message": "Telegram ID не привязан"}), 400

        bot_token = (get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
        if not bot_token:
            return jsonify({"success": False, "message": "Бот не настроен"}), 400

        _ev_labels = [
            ("login_success",   "Успешный вход"),
            ("login_failed",    "Неверный пароль"),
            ("tg_unlinked",     "Вход с непривязанным TG ID"),
            ("config_create",   "Создание / пересоздание конфига"),
            ("config_delete",   "Удаление конфига"),
            ("user_create",     "Добавление пользователя"),
            ("user_delete",     "Удаление пользователя"),
            ("client_ban",      "Блокировка / разблокировка клиента"),
            ("settings_change", "Изменение настроек"),
            ("high_cpu",        "Высокая нагрузка CPU"),
            ("high_ram",        "Высокая нагрузка RAM"),
        ]
        enabled = [label for key, label in _ev_labels if user.has_tg_notify_event(key)]
        events_text = "\n".join(f"  ✓ {l}" for l in enabled) if enabled else "  (нет включённых событий)"

        text = (
            "🔔 <b>Тест уведомлений AdminAntiZapret</b>\n\n"
            f"Аккаунт: <code>{target_username}</code>\n\n"
            f"Включённые события:\n{events_text}"
        )
        send_tg_message(bot_token, user.telegram_id, text)
        return jsonify({"success": True, "message": "Тестовое сообщение отправлено"})

    @app.route("/api/tg-mini/settings", methods=["POST"])
    @auth_manager.admin_required
    def api_tg_mini_settings_update():
        if not _has_telegram_mini_session():
            return jsonify({"success": False, "message": "Доступ разрешён только из Telegram Mini App."}), 403

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        section = (data.get("section") or "").strip().lower()
        if section not in {"port", "nightly", "telegram_auth", "restart_service", "update_system"}:
            return jsonify({"success": False, "message": "Неизвестный раздел настроек"}), 400

        try:
            if section == "port":
                new_port = str(data.get("port") or "").strip()
                if not new_port.isdigit():
                    return jsonify({"success": False, "message": "Порт должен быть числом"}), 400

                port_value = int(new_port)
                if port_value < 1 or port_value > 65535:
                    return jsonify({"success": False, "message": "Порт должен быть в диапазоне 1..65535"}), 400

                set_env_value("APP_PORT", str(port_value))
                os.environ["APP_PORT"] = str(port_value)

                restart_task_id = None
                if bool(data.get("restart_service", True)):
                    task = enqueue_background_task(
                        "restart_service",
                        task_restart_service,
                        created_by_username=session.get("username"),
                        queued_message="Перезапуск службы поставлен в очередь",
                    )
                    restart_task_id = task.id

                log_telegram_audit_event(
                    "mini_settings_port",
                    details=f"port={port_value} restart={1 if bool(data.get('restart_service', True)) else 0}",
                )
                log_user_action_event(
                    "settings_port_update",
                    target_type="app",
                    target_name="APP_PORT",
                    details=(
                        f"value={port_value} via=tg-mini "
                        f"restart={1 if bool(data.get('restart_service', True)) else 0}"
                    ),
                )

                return jsonify(
                    {
                        "success": True,
                        "message": "Порт сохранен",
                        "restart_task_id": restart_task_id,
                        "settings": _build_tg_mini_settings_payload(),
                    }
                )

            if section == "nightly":
                nightly_enabled = bool(data.get("nightly_idle_restart_enabled", True))
                nightly_time_raw = (data.get("nightly_idle_restart_time") or "").strip()

                cron_expr = ""
                if nightly_time_raw:
                    time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", nightly_time_raw)
                    if not time_match:
                        return jsonify(
                            {
                                "success": False,
                                "message": "Укажите время в формате ЧЧ:ММ (например, 04:00)",
                            }
                        ), 400

                    hour_value = int(time_match.group(1))
                    minute_value = int(time_match.group(2))
                    cron_expr = f"{minute_value} {hour_value} * * *"

                if not cron_expr:
                    cron_expr = (data.get("nightly_idle_restart_cron") or "").strip() or "0 4 * * *"

                if not is_valid_cron_expression(cron_expr):
                    return jsonify(
                        {
                            "success": False,
                            "message": "Cron-выражение должно состоять из 5 полей и содержать только цифры и символы */,-",
                        }
                    ), 400

                ttl_raw = str(data.get("active_web_session_ttl_seconds") or "").strip()
                touch_raw = str(data.get("active_web_session_touch_interval_seconds") or "").strip()

                if not ttl_raw.isdigit() or not (30 <= int(ttl_raw) <= 86400):
                    return jsonify(
                        {
                            "success": False,
                            "message": "TTL активной сессии должен быть целым числом в диапазоне 30..86400 секунд",
                        }
                    ), 400

                if not touch_raw.isdigit() or not (1 <= int(touch_raw) <= 3600):
                    return jsonify(
                        {
                            "success": False,
                            "message": "Интервал heartbeat должен быть целым числом в диапазоне 1..3600 секунд",
                        }
                    ), 400

                ttl_value = int(ttl_raw)
                touch_value = int(touch_raw)

                set_nightly_idle_restart_settings(nightly_enabled, cron_expr)
                set_active_web_session_settings(ttl_value, touch_value)

                env_enabled = "true" if nightly_enabled else "false"
                set_env_value("NIGHTLY_IDLE_RESTART_ENABLED", env_enabled)
                set_env_value("NIGHTLY_IDLE_RESTART_CRON", cron_expr)
                set_env_value("ACTIVE_WEB_SESSION_TTL_SECONDS", str(ttl_value))
                set_env_value("ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", str(touch_value))

                os.environ["NIGHTLY_IDLE_RESTART_ENABLED"] = env_enabled
                os.environ["NIGHTLY_IDLE_RESTART_CRON"] = cron_expr
                os.environ["ACTIVE_WEB_SESSION_TTL_SECONDS"] = str(ttl_value)
                os.environ["ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS"] = str(touch_value)

                cron_ok, cron_msg = ensure_nightly_idle_restart_cron()
                if not cron_ok:
                    return jsonify({"success": False, "message": cron_msg}), 500

                log_telegram_audit_event(
                    "mini_settings_nightly",
                    details=(
                        f"enabled={1 if nightly_enabled else 0} "
                        f"time={nightly_time_raw or '-'} ttl={ttl_value} touch={touch_value}"
                    ),
                )
                log_user_action_event(
                    "settings_nightly_update",
                    target_type="maintenance",
                    target_name="nightly_idle_restart",
                    details=(
                        f"enabled={1 if nightly_enabled else 0} cron={cron_expr} "
                        f"ttl={ttl_value} touch={touch_value} via=tg-mini"
                    ),
                )

                return jsonify(
                    {
                        "success": True,
                        "message": "Настройки ночного рестарта сохранены",
                        "settings": _build_tg_mini_settings_payload(),
                    }
                )

            if section == "telegram_auth":
                tg_username_raw = data.get("telegram_auth_bot_username", "")
                tg_token_raw = data.get("telegram_auth_bot_token", None)
                tg_max_age_raw = str(data.get("telegram_auth_max_age_seconds") or "").strip()

                tg_username, username_error = _normalize_telegram_bot_username(tg_username_raw)
                if username_error:
                    return jsonify({"success": False, "message": username_error}), 400

                if not tg_max_age_raw.isdigit() or not (30 <= int(tg_max_age_raw) <= 86400):
                    return jsonify(
                        {
                            "success": False,
                            "message": "Срок действия Telegram авторизации должен быть в диапазоне 30..86400 секунд",
                        }
                    ), 400

                tg_max_age_value = int(tg_max_age_raw)

                set_env_value("TELEGRAM_AUTH_BOT_USERNAME", tg_username)
                set_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", str(tg_max_age_value))
                os.environ["TELEGRAM_AUTH_BOT_USERNAME"] = tg_username
                os.environ["TELEGRAM_AUTH_MAX_AGE_SECONDS"] = str(tg_max_age_value)

                if tg_token_raw is not None:
                    tg_token, token_error = _normalize_telegram_bot_token(tg_token_raw)
                    if token_error:
                        return jsonify({"success": False, "message": token_error}), 400
                    set_env_value("TELEGRAM_AUTH_BOT_TOKEN", tg_token)
                    os.environ["TELEGRAM_AUTH_BOT_TOKEN"] = tg_token

                log_telegram_audit_event(
                    "mini_settings_telegram_auth",
                    details=(
                        f"bot={tg_username or '-'} max_age={tg_max_age_value} "
                        f"token_updated={1 if tg_token_raw is not None else 0}"
                    ),
                )
                log_user_action_event(
                    "settings_telegram_auth_update",
                    target_type="telegram_auth",
                    target_name=(tg_username or "-"),
                    details=(
                        f"max_age={tg_max_age_value} "
                        f"token_updated={1 if tg_token_raw is not None else 0} via=tg-mini"
                    ),
                )

                return jsonify(
                    {
                        "success": True,
                        "message": "Настройки Telegram авторизации сохранены",
                        "settings": _build_tg_mini_settings_payload(),
                    }
                )

            if section == "restart_service":
                task = enqueue_background_task(
                    "restart_service",
                    task_restart_service,
                    created_by_username=session.get("username"),
                    queued_message="Перезапуск службы поставлен в очередь",
                )
                log_telegram_audit_event(
                    "mini_restart_service",
                    details=f"task_id={task.id}",
                )
                log_user_action_event(
                    "settings_restart_service",
                    target_type="service",
                    target_name="admin-antizapret.service",
                    details="via=tg-mini",
                )
                return jsonify(
                    {
                        "success": True,
                        "message": "Перезапуск службы запущен в фоне",
                        "task_id": task.id,
                    }
                )

            if section == "update_system":
                return jsonify(
                    {
                        "success": False,
                        "message": "Используйте /update_system для запуска обновления",
                    }
                ), 400

            return jsonify({"success": False, "message": "Неизвестная операция"}), 400
        except Exception as e:
            app.logger.error("Ошибка API tg-mini settings: %s", e)
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
