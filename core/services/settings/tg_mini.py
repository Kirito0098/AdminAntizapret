import os

from core.services.settings.telegram_normalize import nightly_time_from_cron


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
