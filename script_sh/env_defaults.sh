#!/bin/bash

# Общие значения по умолчанию для .env (install.sh и adminpanel.sh).
# Добавляет ключ только если он ещё не задан — существующие значения не перезаписываются.

_ensure_env_default() {
    local key="$1"
    local value="$2"
    local env_file="${INSTALL_DIR:?INSTALL_DIR не задан}/.env"

    mkdir -p "$INSTALL_DIR"
    [ -f "$env_file" ] || touch "$env_file"
    grep -q "^${key}=" "$env_file" 2>/dev/null && return 0
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
}

ensure_env_defaults() {
    local include_dir="${INCLUDE_DIR:-${SCRIPT_SH_DIR:-$INSTALL_DIR/script_sh}}"

    # Пути и идентификаторы службы (для systemd, CLI и бэкапов)
    _ensure_env_default "INSTALL_DIR" "$INSTALL_DIR"
    _ensure_env_default "VENV_PATH" "${VENV_PATH:-$INSTALL_DIR/venv}"
    _ensure_env_default "DB_FILE" "${DB_FILE:-$INSTALL_DIR/instance/users.db}"
    _ensure_env_default "SERVICE_NAME" "${SERVICE_NAME:-admin-antizapret}"
    _ensure_env_default "ADMIN_ANTIZAPRET_SERVICE_NAME" "admin-antizapret"
    _ensure_env_default "ANTIZAPRET_INSTALL_DIR" "${ANTIZAPRET_INSTALL_DIR:-/root/antizapret}"
    _ensure_env_default "INCLUDE_DIR" "$include_dir"

    # Брендинг панели (SECRET_KEY, APP_PORT, HTTPS — задаёт ssl_setup.sh при установке)
    _ensure_env_default "PANEL_BRAND_NAME" "Admin Panel"

    # Сессии и безопасность cookies (SESSION_COOKIE_SECURE / WTF_CSRF — в ssl_setup.sh)
    _ensure_env_default "ACTIVE_WEB_SESSION_TTL_SECONDS" "180"
    _ensure_env_default "ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS" "30"

    # Ограничение доступа по IP
    _ensure_env_default "TRUSTED_PROXY_IPS" "127.0.0.1,::1"
    _ensure_env_default "ALLOWED_IPS" ""
    _ensure_env_default "IP_RESTRICTION_MODE" "strict"
    _ensure_env_default "PUBLIC_DOWNLOAD_ENABLED" "false"

    # Telegram-авторизация (токены и секреты задаются вручную в настройках)
    _ensure_env_default "TELEGRAM_AUTH_BOT_USERNAME" "YourBot"
    _ensure_env_default "TELEGRAM_AUTH_BOT_TOKEN" ""
    _ensure_env_default "TELEGRAM_AUTH_MAX_AGE_SECONDS" "300"
    _ensure_env_default "TELEGRAM_OIDC_CLIENT_ID" ""
    _ensure_env_default "TELEGRAM_OIDC_CLIENT_SECRET" ""
    _ensure_env_default "TELEGRAM_MINI_APP_SHORT_NAME" ""

    # Автоматические бэкапы
    _ensure_env_default "APP_BACKUP_ENABLED" "true"
    _ensure_env_default "APP_BACKUP_INTERVAL_DAYS" "7"
    _ensure_env_default "APP_BACKUP_TIME" "03:00"
    _ensure_env_default "APP_BACKUP_COMPONENTS" "db,env,data"
    _ensure_env_default "APP_BACKUP_TG_ENABLED" "false"
    _ensure_env_default "APP_BACKUP_TG_ADMIN_IDS" ""
    _ensure_env_default "APP_BACKUP_AZ_ENABLED" "true"

    # Ночной перезапуск при простое
    _ensure_env_default "NIGHTLY_IDLE_RESTART_ENABLED" "true"
    _ensure_env_default "NIGHTLY_IDLE_RESTART_CRON" "0 4 * * *"

    # Фоновые задачи (Настройки → «Модули и задачи»)
    _ensure_env_default "TRAFFIC_SYNC_ENABLED" "true"
    _ensure_env_default "WG_POLICY_SYNC_ENABLED" "true"
    _ensure_env_default "MONITOR_ENABLED" "true"
    _ensure_env_default "ACTIVE_WEB_SESSION_TRACKING_ENABLED" "true"
    _ensure_env_default "RUNTIME_BACKUP_CLEANUP_ENABLED" "true"

    # Разделы приложения (FEATURE_*_ENABLED)
    _ensure_env_default "FEATURE_OPENVPN_ENABLED" "true"
    _ensure_env_default "FEATURE_WIREGUARD_ENABLED" "true"
    _ensure_env_default "FEATURE_AMNEZIAWG_ENABLED" "true"
    _ensure_env_default "FEATURE_LOGS_DASHBOARD_ENABLED" "true"
    _ensure_env_default "FEATURE_SERVER_MONITOR_ENABLED" "true"
    _ensure_env_default "FEATURE_ROUTING_ENABLED" "true"
    _ensure_env_default "FEATURE_EDIT_FILES_ENABLED" "true"
    _ensure_env_default "FEATURE_TELEGRAM_ENABLED" "true"
    _ensure_env_default "FEATURE_BACKUPS_ENABLED" "true"
    _ensure_env_default "FEATURE_USER_MANAGEMENT_ENABLED" "true"
    _ensure_env_default "FEATURE_SECURITY_ENABLED" "true"
    _ensure_env_default "FEATURE_ACTION_LOGS_ENABLED" "true"
    _ensure_env_default "FEATURE_SYSTEM_UPDATES_ENABLED" "true"
    _ensure_env_default "FEATURE_DIAGNOSTICS_TESTS_ENABLED" "true"
    _ensure_env_default "FEATURE_QR_DOWNLOADS_ENABLED" "true"
    _ensure_env_default "FEATURE_VPN_NETWORK_ENABLED" "true"
    _ensure_env_default "FEATURE_MAINTENANCE_ENABLED" "true"

    # Мониторинг сервера и vnStat (VNSTAT_IFACE уточняется в adminpanel.sh)
    _ensure_env_default "MONITOR_CPU_THRESHOLD" "90"
    _ensure_env_default "MONITOR_RAM_THRESHOLD" "90"
    _ensure_env_default "MONITOR_CHECK_INTERVAL_SECONDS" "60"
    _ensure_env_default "MONITOR_COOLDOWN_MINUTES" "30"
    _ensure_env_default "VNSTAT_IFACE" "ens3"

    # Лимиты маршрутизации и CIDR
    _ensure_env_default "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT" "1500"
    _ensure_env_default "AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT" "false"
    _ensure_env_default "AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK" "false"
}
