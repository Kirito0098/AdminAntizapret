import os

from core.services.settings.telegram_normalize import (
    normalize_telegram_bot_token,
    normalize_telegram_bot_username,
)
from core.services.settings.telegram_audit_details import build_telegram_auth_audit_details


def handle_telegram_auth_settings(
    form,
    *,
    flash,
    get_env_value,
    set_env_value,
    log_user_action_event,
    log_telegram_audit_event,
):
    if form.get("telegram_auth_action") != "save":
        return None

    tg_username_raw = form.get("telegram_auth_bot_username", "")
    tg_token_raw = form.get("telegram_auth_bot_token", "")
    tg_max_age_raw = form.get("telegram_auth_max_age_seconds", "").strip()

    has_tg_error = False
    tg_username, username_error = normalize_telegram_bot_username(tg_username_raw)
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

    existing_username = (get_env_value("TELEGRAM_AUTH_BOT_USERNAME", "") or "").strip()
    existing_max_age_raw = (get_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300") or "300").strip()
    existing_max_age = int(existing_max_age_raw) if existing_max_age_raw.isdigit() else 300
    existing_token = (get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
    token_to_apply = existing_token
    token_updated = False
    if (tg_token_raw or "").strip():
        tg_token, token_error = normalize_telegram_bot_token(tg_token_raw)
        if token_error:
            flash(token_error, "error")
            has_tg_error = True
        else:
            token_to_apply = tg_token
            token_updated = True

    if not has_tg_error:
        changed_fields = []
        if tg_username != existing_username:
            changed_fields.append("bot_username")
        if tg_max_age_value != existing_max_age:
            changed_fields.append("max_age_seconds")
        if token_updated:
            changed_fields.append("bot_token")

        unified_details = build_telegram_auth_audit_details(
            source="web_settings",
            status="success",
            bot_username=tg_username or "-",
            max_age_seconds=tg_max_age_value,
            changed_fields=changed_fields,
            token_updated=token_updated,
        )

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
            details=unified_details,
        )
        log_telegram_audit_event(
            "mini_settings_telegram_auth",
            details=unified_details,
            mirror_user_action=False,
        )
    return None
