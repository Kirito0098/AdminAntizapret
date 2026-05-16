import os
import re

from core.services.settings.telegram_normalize import (
    normalize_telegram_bot_token,
    normalize_telegram_bot_username,
    nightly_time_from_cron,
)


def build_tg_mini_settings_payload(
    *,
    get_env_value,
    get_nightly_idle_restart_settings,
    get_active_web_session_settings,
):
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
        "nightly_idle_restart_time": nightly_time_from_cron(nightly_idle_restart_cron),
        "active_web_session_ttl_seconds": int(active_web_session_ttl_seconds),
        "active_web_session_touch_interval_seconds": int(active_web_session_touch_interval_seconds),
        "telegram_auth_bot_username": telegram_auth_bot_username,
        "telegram_auth_max_age_seconds": int(telegram_auth_max_age_seconds or 300),
        "telegram_auth_bot_token_set": telegram_auth_bot_token_set,
        "telegram_auth_enabled": telegram_auth_enabled,
    }


def update_tg_mini_settings(
    *,
    data: dict,
    set_env_value,
    get_env_value,
    get_nightly_idle_restart_settings,
    get_active_web_session_settings,
    set_nightly_idle_restart_settings,
    set_active_web_session_settings,
    is_valid_cron_expression,
    ensure_nightly_idle_restart_cron,
    enqueue_background_task,
    task_restart_service,
    session_username: str | None,
    log_telegram_audit_event,
    log_user_action_event,
):
    section = (data.get("section") or "").strip().lower()
    if section not in {"port", "nightly", "telegram_auth", "restart_service", "update_system"}:
        return {"success": False, "message": "Неизвестный раздел настроек"}, 400

    if section == "port":
        new_port = str(data.get("port") or "").strip()
        if not new_port.isdigit():
            return {"success": False, "message": "Порт должен быть числом"}, 400

        port_value = int(new_port)
        if port_value < 1 or port_value > 65535:
            return {"success": False, "message": "Порт должен быть в диапазоне 1..65535"}, 400

        set_env_value("APP_PORT", str(port_value))
        os.environ["APP_PORT"] = str(port_value)

        restart_task_id = None
        if bool(data.get("restart_service", True)):
            task = enqueue_background_task(
                "restart_service",
                task_restart_service,
                created_by_username=session_username,
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

        return {
            "success": True,
            "message": "Порт сохранен",
            "restart_task_id": restart_task_id,
            "settings": build_tg_mini_settings_payload(
                get_env_value=get_env_value,
                get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
                get_active_web_session_settings=get_active_web_session_settings,
            ),
        }, 200

    if section == "nightly":
        nightly_enabled = bool(data.get("nightly_idle_restart_enabled", True))
        nightly_time_raw = (data.get("nightly_idle_restart_time") or "").strip()

        cron_expr = ""
        if nightly_time_raw:
            time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", nightly_time_raw)
            if not time_match:
                return {
                    "success": False,
                    "message": "Укажите время в формате ЧЧ:ММ (например, 04:00)",
                }, 400

            hour_value = int(time_match.group(1))
            minute_value = int(time_match.group(2))
            cron_expr = f"{minute_value} {hour_value} * * *"

        if not cron_expr:
            cron_expr = (data.get("nightly_idle_restart_cron") or "").strip() or "0 4 * * *"

        if not is_valid_cron_expression(cron_expr):
            return {
                "success": False,
                "message": "Cron-выражение должно состоять из 5 полей и содержать только цифры и символы */,-",
            }, 400

        ttl_raw = str(data.get("active_web_session_ttl_seconds") or "").strip()
        touch_raw = str(data.get("active_web_session_touch_interval_seconds") or "").strip()

        if not ttl_raw.isdigit() or not (30 <= int(ttl_raw) <= 86400):
            return {
                "success": False,
                "message": "TTL активной сессии должен быть целым числом в диапазоне 30..86400 секунд",
            }, 400

        if not touch_raw.isdigit() or not (1 <= int(touch_raw) <= 3600):
            return {
                "success": False,
                "message": "Интервал heartbeat должен быть целым числом в диапазоне 1..3600 секунд",
            }, 400

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
            return {"success": False, "message": cron_msg}, 500

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

        return {
            "success": True,
            "message": "Настройки ночного рестарта сохранены",
            "settings": build_tg_mini_settings_payload(
                get_env_value=get_env_value,
                get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
                get_active_web_session_settings=get_active_web_session_settings,
            ),
        }, 200

    if section == "telegram_auth":
        tg_username_raw = data.get("telegram_auth_bot_username", "")
        tg_token_raw = data.get("telegram_auth_bot_token", None)
        tg_max_age_raw = str(data.get("telegram_auth_max_age_seconds") or "").strip()

        tg_username, username_error = normalize_telegram_bot_username(tg_username_raw)
        if username_error:
            return {"success": False, "message": username_error}, 400

        if not tg_max_age_raw.isdigit() or not (30 <= int(tg_max_age_raw) <= 86400):
            return {
                "success": False,
                "message": "Срок действия Telegram авторизации должен быть в диапазоне 30..86400 секунд",
            }, 400

        tg_max_age_value = int(tg_max_age_raw)

        set_env_value("TELEGRAM_AUTH_BOT_USERNAME", tg_username)
        set_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", str(tg_max_age_value))
        os.environ["TELEGRAM_AUTH_BOT_USERNAME"] = tg_username
        os.environ["TELEGRAM_AUTH_MAX_AGE_SECONDS"] = str(tg_max_age_value)

        if tg_token_raw is not None:
            tg_token, token_error = normalize_telegram_bot_token(tg_token_raw)
            if token_error:
                return {"success": False, "message": token_error}, 400
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

        return {
            "success": True,
            "message": "Настройки Telegram авторизации сохранены",
            "settings": build_tg_mini_settings_payload(
                get_env_value=get_env_value,
                get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
                get_active_web_session_settings=get_active_web_session_settings,
            ),
        }, 200

    if section == "restart_service":
        task = enqueue_background_task(
            "restart_service",
            task_restart_service,
            created_by_username=session_username,
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
        return {
            "success": True,
            "message": "Перезапуск службы запущен в фоне",
            "task_id": task.id,
        }, 200

    if section == "update_system":
        return {
            "success": False,
            "message": "Используйте /update_system для запуска обновления",
        }, 400

    return {"success": False, "message": "Неизвестная операция"}, 400
