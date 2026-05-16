import os
from datetime import datetime, timedelta

from core.services.audit_view_presenter import (
    build_telegram_mini_audit_view,
    build_user_action_audit_view,
    build_user_action_sessions,
)
from core.services.panel_publish_info import build_panel_publish_context
from core.services.settings.telegram_normalize import nightly_time_from_cron


def _telegram_auth_fields(get_env_value):
    telegram_auth_bot_username = get_env_value("TELEGRAM_AUTH_BOT_USERNAME", "")
    telegram_auth_max_age_seconds = get_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300")
    telegram_auth_bot_token_set = bool((get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip())
    telegram_auth_enabled = bool(telegram_auth_bot_username and telegram_auth_bot_token_set)
    return {
        "telegram_auth_bot_username": telegram_auth_bot_username,
        "telegram_auth_max_age_seconds": telegram_auth_max_age_seconds,
        "telegram_auth_bot_token_set": telegram_auth_bot_token_set,
        "telegram_auth_enabled": telegram_auth_enabled,
    }


def build_settings_page_context(
    *,
    user_model,
    active_web_session_model,
    qr_download_audit_log_model,
    telegram_mini_audit_log_model,
    user_action_log_model,
    ip_restriction,
    config_file_handler,
    group_folders,
    get_env_value,
    get_nightly_idle_restart_settings,
    get_active_web_session_settings,
    get_public_download_enabled,
    collect_all_openvpn_files_for_access,
    build_openvpn_access_groups,
    build_conf_access_groups,
    request_url_root=None,
):
    current_port = os.getenv("APP_PORT", "5050")
    qr_download_token_ttl_seconds = get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600")
    qr_download_token_max_downloads = get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1")
    qr_download_pin_set = bool((get_env_value("QR_DOWNLOAD_PIN", "") or "").strip())

    nightly_idle_restart_enabled, nightly_idle_restart_cron = get_nightly_idle_restart_settings()
    nightly_idle_restart_time = nightly_time_from_cron(nightly_idle_restart_cron)

    active_web_session_ttl_seconds, active_web_session_touch_interval_seconds = get_active_web_session_settings()
    active_web_sessions_count = active_web_session_model.query.filter(
        active_web_session_model.last_seen_at
        >= datetime.utcnow() - timedelta(seconds=active_web_session_ttl_seconds)
    ).count()

    qr_download_audit_logs = qr_download_audit_log_model.query.order_by(
        qr_download_audit_log_model.created_at.desc()
    ).limit(100).all()
    telegram_mini_audit_logs = telegram_mini_audit_log_model.query.order_by(
        telegram_mini_audit_log_model.created_at.desc()
    ).limit(200).all()
    telegram_mini_audit_view = build_telegram_mini_audit_view(telegram_mini_audit_logs)
    user_action_logs = user_action_log_model.query.order_by(
        user_action_log_model.created_at.desc()
    ).limit(300).all()
    user_action_audit_view = build_user_action_audit_view(user_action_logs)
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

    monitor_cpu_threshold = int((get_env_value("MONITOR_CPU_THRESHOLD", "90") or "90").strip())
    monitor_ram_threshold = int((get_env_value("MONITOR_RAM_THRESHOLD", "90") or "90").strip())
    monitor_interval_seconds = int((get_env_value("MONITOR_CHECK_INTERVAL_SECONDS", "60") or "60").strip())
    monitor_cooldown_minutes = int((get_env_value("MONITOR_COOLDOWN_MINUTES", "30") or "30").strip())

    panel_publish = build_panel_publish_context(
        get_env_value=get_env_value,
        url_root=request_url_root,
    )

    return {
        "port": current_port,
        "panel_publish": panel_publish,
        "users": users,
        "viewer_users": viewer_users,
        "allowed_ips": allowed_ips,
        "ip_enabled": ip_enabled,
        "current_ip": current_ip,
        "ip_block_scanners": scanner_settings["enabled"],
        "ip_scanner_max_attempts": scanner_settings["max_attempts"],
        "ip_scanner_window_seconds": scanner_settings["window_seconds"],
        "ip_scanner_ban_seconds": scanner_settings["ban_seconds"],
        "ip_scanner_active_bans": scanner_settings["active_bans"],
        "ip_scanner_grace_entries": scanner_settings["grace_entries"],
        "ip_scanner_has_firewall_entries": scanner_settings["has_firewall_entries"],
        "ip_block_ip_blocked_dwell": scanner_settings["block_ip_blocked_dwell"],
        "ip_blocked_dwell_seconds": scanner_settings["ip_blocked_dwell_seconds"],
        "ip_scanner_strikes_for_year": scanner_settings["strikes_for_year"],
        "ip_scanner_year_ban_seconds": scanner_settings["year_ban_seconds"],
        "ip_scanner_unban_grace_seconds": scanner_settings["unban_grace_seconds"],
        "ip_scanner_firewall_enabled": scanner_settings["firewall_enabled"],
        "all_openvpn": all_openvpn,
        "openvpn_access_groups": openvpn_access_groups,
        "all_wg": all_wg,
        "all_amneziawg": all_amneziawg,
        "wg_access_groups": wg_access_groups,
        "amneziawg_access_groups": amneziawg_access_groups,
        "viewer_access": viewer_access,
        "public_download_enabled": get_public_download_enabled(),
        "qr_download_token_ttl_seconds": qr_download_token_ttl_seconds,
        "qr_download_token_max_downloads": qr_download_token_max_downloads,
        "qr_download_pin_set": qr_download_pin_set,
        "nightly_idle_restart_enabled": nightly_idle_restart_enabled,
        "nightly_idle_restart_cron": nightly_idle_restart_cron,
        "nightly_idle_restart_time": nightly_idle_restart_time,
        "active_web_session_ttl_seconds": active_web_session_ttl_seconds,
        "active_web_session_touch_interval_seconds": active_web_session_touch_interval_seconds,
        "active_web_sessions_count": active_web_sessions_count,
        "qr_download_audit_logs": qr_download_audit_logs,
        "telegram_mini_audit_logs": telegram_mini_audit_view,
        "user_action_audit_logs": user_action_audit_view,
        "user_action_sessions": user_action_sessions,
        "monitor_cpu_threshold": monitor_cpu_threshold,
        "monitor_ram_threshold": monitor_ram_threshold,
        "monitor_interval_seconds": monitor_interval_seconds,
        "monitor_cooldown_minutes": monitor_cooldown_minutes,
        **_telegram_auth_fields(get_env_value),
    }
