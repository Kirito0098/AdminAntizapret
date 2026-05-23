#!/bin/bash

# Полный менеджер AdminAntizapret
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"
export DEBIAN_FRONTEND=noninteractive

# ─── Цвета ────────────────────────────────────────
RED=$(printf '\033[0;31m')
GREEN=$(printf '\033[0;32m')
YELLOW=$(printf '\033[1;33m')
CYAN=$(printf '\033[0;36m')
BOLD=$(printf '\033[1m')
DIM=$(printf '\033[2m')
NC=$(printf '\033[0m')

# ─── Основные параметры ───────────────────────────
export INSTALL_DIR="/opt/AdminAntizapret"
export VENV_PATH="$INSTALL_DIR/venv"
export SERVICE_NAME="admin-antizapret"
export DEFAULT_PORT="5050"
export APP_PORT="$DEFAULT_PORT"
export DB_FILE="$INSTALL_DIR/instance/users.db"
export ANTIZAPRET_INSTALL_DIR="/root/antizapret"
export ANTIZAPRET_INSTALL_SCRIPT="https://raw.githubusercontent.com/GubernievS/AntiZapret-VPN/main/setup.sh"
export LOG_FILE="/var/log/adminpanel.log"
export INSTALL_LOG_FILE=""
export INSTALL_LOG_ACTIVE=0
export INSTALL_LOG_KEEP_COUNT=30
export MAX_MAIN_LOG_SIZE_MB=20
export MAX_MAIN_LOG_BACKUPS=5
export INCLUDE_DIR="$INSTALL_DIR/script_sh"
export ADMIN_PANEL_DIR="/root/AdminPanel"

# utils — первым, чтобы UI-функции были доступны всем модулям
modules=(
    "utils"
    "ssl_setup"
    "backup_functions"
    "monitoring"
    "service_functions"
    "uninstall"
    "user_management"
    "unit_tests"
    "site_diagnostics"
    "panel_menus"
    "ip_whitelist"
)

for module in "${modules[@]}"; do
    if [ -f "$INCLUDE_DIR/${module}.sh" ]; then
        # shellcheck disable=SC1090
        . "$INCLUDE_DIR/${module}.sh"
    else
        printf "  ${RED}✗${NC}  Не найден модуль: ${module}.sh\n" >&2
        exit 1
    fi
done

# ─── Генерация секретного ключа ───────────────────
generate_secret_key() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32
        return $?
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
        return $?
    fi
    if [ -r /dev/urandom ]; then
        od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
        return $?
    fi
    return 1
}

SECRET_KEY=$(generate_secret_key)
if [ -z "$SECRET_KEY" ]; then
    ui_fail "Не удалось сгенерировать SECRET_KEY." >&2
    exit 1
fi

# ─── Проверка занятости порта ─────────────────────
check_port() {
    local port=$1
    if command -v ss >/dev/null 2>&1; then
        ss -tuln | grep -q ":$port " && return 0
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tuln | grep -q ":$port " && return 0
    elif command -v lsof >/dev/null 2>&1; then
        lsof -i :"$port" >/dev/null && return 0
    elif grep -q ":$port " /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
        return 0
    else
        ui_warn "Не удалось проверить порт (нужен ss, netstat или lsof)"
        return 1
    fi
    return 1
}

# Debian ≥13: пакет dnsutils заменён на bind9-dnsutils (dig/host/nslookup)
_is_dnsutils_pkg_installed() {
    dpkg -s dnsutils >/dev/null 2>&1 || dpkg -s bind9-dnsutils >/dev/null 2>&1
}

_dnsutils_apt_pkg_name() {
    if apt-cache show dnsutils >/dev/null 2>&1; then
        printf '%s\n' dnsutils
    else
        printf '%s\n' bind9-dnsutils
    fi
}

# ─── Установка зависимостей ───────────────────────
check_dependencies() {
    local dns_pkg
    dns_pkg=$(_dnsutils_apt_pkg_name)
    ui_info "Установка зависимостей..."
    apt-get update --quiet --quiet >/dev/null
    check_error "Не удалось обновить индексы пакетов"
    apt-get install -y --quiet --quiet apt-utils >/dev/null
    check_error "Не удалось установить apt-utils"
    apt-get install -y --quiet --quiet python3 python3-pip python3-venv python3-dev \
        git wget openssl cron vnstat "$dns_pkg" \
        libjpeg-dev zlib1g-dev >/dev/null
    check_error "Не удалось установить зависимости"
    ui_ok "Зависимости установлены"
}

# ─── Проверка окружения ───────────────────────────
verify_project_environment() {
    local failed=0 warned=0 passed=0
    local req_file="$INSTALL_DIR/requirements.txt"
    local missing_system_packages=()
    local required_system_packages=(python3 python3-pip python3-venv python3-dev git wget openssl cron vnstat dnsutils libjpeg-dev zlib1g-dev iptables ipset)

    _vpe_ok()   { ui_ok "$1";   passed=$((passed + 1)); }
    _vpe_warn() { ui_warn "$1"; warned=$((warned + 1)); }
    _vpe_fail() { ui_fail "$1"; failed=$((failed + 1)); }

    normalize_pkg_name() {
        printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[-_.]+/-/g'
    }

    ui_section "1) Системные команды"
    local required_commands=(python3 pip3 git wget openssl systemctl awk sed grep ss dig iptables ipset)
    for cmd in "${required_commands[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            _vpe_ok "$cmd"
        else
            _vpe_fail "$cmd — не найден"
        fi
    done

    ui_section "2) Системные пакеты"
    for pkg in "${required_system_packages[@]}"; do
        if [ "$pkg" = "dnsutils" ]; then
            if _is_dnsutils_pkg_installed; then
                if dpkg -s dnsutils >/dev/null 2>&1; then
                    _vpe_ok "dnsutils"
                else
                    _vpe_ok "dnsutils (bind9-dnsutils)"
                fi
            else
                _vpe_fail "dnsutils — не установлен"
                missing_system_packages+=("dnsutils")
            fi
        elif dpkg -s "$pkg" >/dev/null 2>&1; then
            _vpe_ok "$pkg"
        else
            _vpe_fail "$pkg — не установлен"
            missing_system_packages+=("$pkg")
        fi
    done

    if [ "${#missing_system_packages[@]}" -gt 0 ]; then
        ui_warn "Отсутствуют пакеты: ${missing_system_packages[*]}"
        if ui_confirm "Установить недостающие пакеты?"; then
            ui_info "Устанавливаем недостающие пакеты..."
            local apt_install_packages=()
            local mpkg resolved_dns
            for mpkg in "${missing_system_packages[@]}"; do
                if [ "$mpkg" = "dnsutils" ]; then
                    resolved_dns=$(_dnsutils_apt_pkg_name)
                    apt_install_packages+=("$resolved_dns")
                else
                    apt_install_packages+=("$mpkg")
                fi
            done
            if apt-get update --quiet --quiet >/dev/null && \
               apt-get install -y --quiet --quiet "${apt_install_packages[@]}" >/dev/null; then
                _vpe_ok "Пакеты установлены"
            else
                _vpe_fail "Не удалось установить часть пакетов"
            fi
        else
            _vpe_warn "Установка пакетов пропущена"
        fi
    fi

    ui_section "3) Виртуальное окружение"
    if [ -x "$VENV_PATH/bin/python3" ] && [ -x "$VENV_PATH/bin/pip" ]; then
        _vpe_ok "Окружение: $VENV_PATH"
    else
        _vpe_fail "Не найдено или повреждено: $VENV_PATH"
    fi

    ui_section "4) Python-зависимости"
    if [ ! -f "$req_file" ]; then
        _vpe_fail "requirements.txt не найден"
    else
        _vpe_ok "requirements.txt найден"

        if [ -x "$VENV_PATH/bin/pip" ]; then
            local installed_pkgs
            installed_pkgs=$(
                "$VENV_PATH/bin/pip" list --format=freeze 2>/dev/null |
                    cut -d'=' -f1 | sed '/^$/d' |
                    while IFS= read -r p; do normalize_pkg_name "$p"; done
            )
            local missing_python_packages=()
            while IFS= read -r line; do
                line=$(printf '%s' "$line" | sed -E 's/[[:space:]]*#.*$//' | tr -d '[:space:]')
                [ -z "$line" ] && continue
                local req_name
                req_name=$(printf '%s' "$line" | sed -E 's/[<>=!~].*$//; s/\[.*\]$//')
                req_name=$(normalize_pkg_name "$req_name")
                printf '%s\n' "$installed_pkgs" | grep -qx "$req_name" || missing_python_packages+=("$line")
            done < "$req_file"

            if [ "${#missing_python_packages[@]}" -eq 0 ]; then
                _vpe_ok "Все зависимости из requirements.txt установлены"
            else
                _vpe_fail "Не установлены (${#missing_python_packages[@]} шт.):"
                printf '%s\n' "${missing_python_packages[@]}" | sed 's/^/      - /'
                if ui_confirm "Установить Python-зависимости?"; then
                    ui_info "Устанавливаем..."
                    if "$VENV_PATH/bin/pip" install -q -r "$req_file"; then
                        _vpe_ok "Python-зависимости установлены"
                    else
                        _vpe_fail "Не удалось установить Python-зависимости"
                    fi
                else
                    _vpe_warn "Установка Python-зависимостей пропущена"
                fi
            fi

            if "$VENV_PATH/bin/pip" check >/dev/null 2>&1; then
                _vpe_ok "Зависимости согласованы (pip check)"
            else
                _vpe_warn "Конфликты зависимостей (pip check). Проверьте вручную."
            fi
        else
            _vpe_fail "pip в venv не найден"
        fi
    fi

    ui_section "5) Файлы и сервисы"
    if [ -f "$INSTALL_DIR/.env" ]; then
        _vpe_ok ".env присутствует"
    else
        _vpe_fail ".env отсутствует"
    fi
    if [ -f "$DB_FILE" ]; then
        _vpe_ok "База данных: $DB_FILE"
    else
        _vpe_fail "База данных не найдена: $DB_FILE"
    fi
    if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        _vpe_ok "Systemd unit: $SERVICE_NAME.service"
    else
        _vpe_fail "Systemd unit не найден"
    fi
    if systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
        _vpe_ok "Сервис включён в автозапуск"
    else
        _vpe_warn "Сервис не включён в автозапуск"
    fi
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        _vpe_ok "Сервис запущен"
    else
        _vpe_warn "Сервис не запущен"
    fi

    ui_section "6) AntiZapret-VPN"
    if [ -d "$ANTIZAPRET_INSTALL_DIR" ]; then
        _vpe_ok "Каталог $ANTIZAPRET_INSTALL_DIR"
    else
        _vpe_fail "Каталог $ANTIZAPRET_INSTALL_DIR не найден"
    fi
    if [ -x "$ANTIZAPRET_INSTALL_DIR/doall.sh" ]; then
        _vpe_ok "doall.sh доступен"
    else
        _vpe_fail "doall.sh не найден или не исполняемый"
    fi
    if systemctl is-active --quiet antizapret.service 2>/dev/null; then
        _vpe_ok "antizapret.service активен"
    else
        _vpe_warn "antizapret.service не активен (панель частично ограничена)"
    fi

    printf "\n"
    _m_top
    _m_item "$(printf "${GREEN}Успешно:${NC}       %d" "$passed")"
    _m_item "$(printf "${RED}Ошибок:${NC}        %d" "$failed")"
    _m_item "$(printf "${YELLOW}Предупреждений:${NC} %d" "$warned")"
    _m_bot
    printf "\n"

    if [ "$failed" -eq 0 ]; then
        ui_ok "Окружение готово."
    else
        ui_fail "Обнаружены ошибки. Устраните их перед работой."
    fi
}

# ─── Проверка root ────────────────────────────────
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log "Попытка запуска без прав root"
        ui_fail "Запустите скрипт с правами root." >&2
        exit 1
    fi
}

# ─── Поиск unit-файла vnstat ──────────────────────
resolve_vnstat_unit_file() {
    local fragment_path=""
    if command -v systemctl >/dev/null 2>&1; then
        fragment_path=$(systemctl show -P FragmentPath vnstat.service 2>/dev/null || true)
        if [ -n "$fragment_path" ] && [ -f "$fragment_path" ]; then
            printf '%s\n' "$fragment_path"
            return 0
        fi
    fi
    for p in "/lib/systemd/system/vnstat.service" "/usr/lib/systemd/system/vnstat.service"; do
        [ -f "$p" ] && { printf '%s\n' "$p"; return 0; }
    done
    return 1
}

# ─── Установка AntiZapret-VPN ─────────────────────
install_antizapret() {
    log "Проверка наличия AntiZapret-VPN"

    check_antizapret_installed() {
        systemctl is-active --quiet antizapret.service 2>/dev/null && return 0
        [ -d "/root/antizapret" ]
    }

    if check_antizapret_installed; then
        log "AntiZapret-VPN уже установлен"
        ui_ok "AntiZapret-VPN уже установлен"
        return 0
    fi

    log "AntiZapret-VPN не установлен"
    printf "\n"
    _m_top
    _m_title "Требуется AntiZapret-VPN"
    _m_sep
    _m_item "Модуль AntiZapret-VPN не установлен."
    _m_item "Установите его вручную:"
    _m_blank
    _m_item "bash <(wget --no-hsts -qO-"
    _m_item "  ${ANTIZAPRET_INSTALL_SCRIPT})"
    _m_blank
    _m_item "Затем запустите этот скрипт снова."
    _m_bot
    printf "\n"
    exit 1
}

# ─── Автообновление ───────────────────────────────
auto_update() {
    log "Проверка обновлений"
    ui_info "Проверка обновлений..."
    cd "$INSTALL_DIR" || return 1

    if ! git fetch origin main; then
        check_error "Не удалось получить обновления из origin/main"
    fi

    if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
        ui_info "Найдены обновления. Установка..."
        git pull origin main
        check_error "Не удалось выполнить git pull"
        "$VENV_PATH/bin/pip" install -q -r requirements.txt
        check_error "Не удалось обновить Python-зависимости"
        systemctl restart "$SERVICE_NAME"
        check_error "Не удалось перезапустить сервис"
        ui_ok "Обновление завершено"
    else
        ui_ok "Система актуальна"
    fi
}

# ─── Логирование установки ────────────────────────
start_install_logging() {
    prune_logs_by_pattern "/var/log/adminpanel-install-*.log" "$INSTALL_LOG_KEEP_COUNT"

    INSTALL_LOG_FILE="/var/log/adminpanel-install-$(date '+%Y%m%d-%H%M%S').log"
    if ! touch "$INSTALL_LOG_FILE" 2>/dev/null; then
        ui_fail "Не удалось создать лог установки: $INSTALL_LOG_FILE"
        return 1
    fi
    chmod 600 "$INSTALL_LOG_FILE" 2>/dev/null || true

    INSTALL_LOG_ACTIVE=1
    exec 7>&1 8>&2
    exec > >(tee >(sed 's/\x1B\[[0-9;]*[A-Za-z]//g; s/\r//g' >> "$INSTALL_LOG_FILE")) 2>&1

    ui_info "Лог установки: $INSTALL_LOG_FILE"
    log "Начата установка. Лог: $INSTALL_LOG_FILE"
}

finish_install_logging() {
    local status=${1:-0}
    [ "${INSTALL_LOG_ACTIVE:-0}" -eq 1 ] || return

    if [ "$status" -eq 0 ]; then
        log "Установка завершена успешно"
        ui_ok "Установка завершена успешно"
    else
        log "Установка завершена с ошибкой (код: $status)"
        ui_fail "Установка завершена с ошибкой (код: $status)"
    fi
    printf "  ${DIM}Лог установки: %s${NC}\n" "$INSTALL_LOG_FILE"

    exec 1>&7 2>&8
    exec 7>&- 8>&-
    INSTALL_LOG_ACTIVE=0
}

# ─── Главное меню ─────────────────────────────────
main_menu() {
    while true; do
        clear
        _m_top
        _m_title "AdminAntizapret — Управление"
        _m_sep
        _m_item "1. Сервис панели"
        _m_item "2. Администраторы"
        _m_item "3. Сеть и HTTPS"
        _m_item "4. Резервные копии и обновления"
        _m_item "5. Диагностика и тесты"
        _m_item "6. Удалить AdminAntizapret"
        _m_sep
        _m_item "7. Диагностика запуска сайта"
        _m_item "8. Общий тест системы (окружение + pytest)"
        _m_item "9. Белый список IP"
        _m_sep
        _m_item "0. Выход"
        _m_bot
        printf "\n"

        read -r -p "  Выберите действие [0-9]: " choice
        case $choice in
        1) menu_service_panel ;;
        2) menu_administrators ;;
        3) menu_network_https ;;
        4) menu_backups_updates ;;
        5) menu_diagnostics_tests ;;
        6) uninstall ;;
        7)
            diagnose_site_startup
            press_any_key
            ;;
        8)
            run_unit_tests_summary
            press_any_key
            ;;
        9) menu_ip_whitelist ;;
        0) exit 0 ;;
        *)
            ui_warn "Неверный выбор"
            sleep 1
            ;;
        esac
    done
}

# ─── Установка AdminAntizapret ────────────────────
install() {
    start_install_logging || exit 1
    log "Старт процедуры установки AdminAntizapret"

    clear
    _m_top
    _m_title "Установка AdminAntizapret"
    _m_bot
    printf "\n"

    # Проверка AntiZapret-VPN
    check_antizapret_installed() {
        systemctl is-active --quiet antizapret.service 2>/dev/null && return 0
        [ -d "$ANTIZAPRET_INSTALL_DIR" ]
    }

    ui_info "Проверка AntiZapret-VPN..."
    if ! check_antizapret_installed; then
        install_antizapret
        if ! check_antizapret_installed; then
            ui_fail "AntiZapret-VPN не установлен. Установка прервана."
            finish_install_logging 1
            exit 1
        fi
    else
        ui_ok "AntiZapret-VPN установлен"
    fi

    # Права выполнения
    ui_info "Установка прав выполнения..."
    chmod +x "$INSTALL_DIR/client.sh" "$ANTIZAPRET_INSTALL_DIR/doall.sh" 2>/dev/null || true
    ui_ok "Права установлены"

    # Обновление пакетов
    ui_info "Обновление списка пакетов..."
    apt-get update --quiet --quiet >/dev/null
    check_error "Не удалось обновить пакеты"
    ui_ok "Список пакетов обновлён"

    # Зависимости
    check_dependencies

    # Виртуальное окружение
    if [ -x "$VENV_PATH/bin/python3" ]; then
        ui_ok "Виртуальное окружение уже есть: $VENV_PATH"
    else
        ui_info "Создание виртуального окружения..."
        python3 -m venv "$VENV_PATH"
        check_error "Не удалось создать виртуальное окружение"
        ui_ok "Виртуальное окружение создано"
    fi

    # Обновление pip
    ui_info "Обновление pip/setuptools/wheel..."
    "$VENV_PATH/bin/pip" install -q --upgrade pip setuptools wheel
    check_error "Не удалось обновить pip/setuptools/wheel"
    ui_ok "pip обновлён"

    # Python-зависимости
    ui_info "Установка Python-зависимостей..."
    "$VENV_PATH/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
    check_error "Не удалось установить Python-зависимости"
    ui_ok "Python-зависимости установлены"

    # Тип установки
    if ! choose_installation_type; then
        finish_install_logging 1
        exit 1
    fi

    # База данных
    init_db

    # Systemd сервис
    ui_info "Создание systemd сервиса..."
    cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOL
[Unit]
Description=AdminAntizapret VPN Management
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_PATH/bin/gunicorn \
    -c $INSTALL_DIR/gunicorn.conf.py \
    app:app
Restart=always
RestartSec=5
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOL

    # Systemd таймер синхронизации трафика
    ui_info "Создание systemd таймера трафика..."
    cat > "/etc/systemd/system/admin-antizapret-traffic-sync.service" << EOL
[Unit]
Description=AdminAntizapret Traffic Sync
After=network.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_PATH/bin/python3 $INSTALL_DIR/utils/traffic_sync.py
Environment="PYTHONUNBUFFERED=1"
EOL

    cat > "/etc/systemd/system/admin-antizapret-traffic-sync.timer" << EOL
[Unit]
Description=Run AdminAntizapret traffic sync every 30 seconds

[Timer]
OnBootSec=45sec
OnUnitActiveSec=30sec
AccuracySec=1s
Unit=admin-antizapret-traffic-sync.service
Persistent=true

[Install]
WantedBy=timers.target
EOL

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"
    check_error "Не удалось запустить сервис"
    systemctl enable --now admin-antizapret-traffic-sync.timer
    check_error "Не удалось включить таймер трафика"
    ui_ok "Сервисы запущены"

    # Выбор сетевого интерфейса для vnstat
    local available_interfaces
    available_interfaces=$(ip link show | grep -E '^[0-9]+: ' | awk -F: '{print $2}' | \
        sed 's/ //g' | grep -vE '^(lo|docker|veth|br-|vpn|antizapret|tun|tap)' | sort)
    local interface_count
    interface_count=$(printf '%s\n' "$available_interfaces" | grep -c '.')
    local default_interface
    default_interface=$(ip route | awk '/default/{print $5; exit}')
    default_interface="${default_interface:-eth0}"

    if [ -z "$available_interfaces" ]; then
        ui_fail "Не найдено доступных сетевых интерфейсов"
        finish_install_logging 1
        exit 1
    fi

    local vnstat_iface
    if [ "$interface_count" -eq 1 ]; then
        vnstat_iface="$available_interfaces"
        ui_ok "Интерфейс: $vnstat_iface (единственный)"
    else
        ui_section "Доступные интерфейсы:"
        printf '%s\n' "$available_interfaces" | sed 's/^/      /'
        while true; do
            read -r -p "  Интерфейс для vnstat [${default_interface}]: " vnstat_iface
            vnstat_iface="${vnstat_iface:-$default_interface}"
            if ip link show "$vnstat_iface" >/dev/null 2>&1; then
                break
            else
                ui_fail "Интерфейс '$vnstat_iface' не найден"
            fi
        done
    fi

    # Запись VNSTAT_IFACE в .env
    if [ -f "$INSTALL_DIR/.env" ] && grep -q "^VNSTAT_IFACE=" "$INSTALL_DIR/.env"; then
        local current_iface
        current_iface=$(grep "^VNSTAT_IFACE=" "$INSTALL_DIR/.env" | cut -d'=' -f2)
        ui_warn "VNSTAT_IFACE уже задан: $current_iface"
        if ui_confirm "Изменить на $vnstat_iface?"; then
            sed -i "s/^VNSTAT_IFACE=.*/VNSTAT_IFACE=$vnstat_iface/" "$INSTALL_DIR/.env"
            ui_ok "VNSTAT_IFACE → $vnstat_iface"
        else
            vnstat_iface="$current_iface"
            ui_ok "Оставлен текущий VNSTAT_IFACE=$current_iface"
        fi
    else
        printf 'VNSTAT_IFACE=%s\n' "$vnstat_iface" >> "$INSTALL_DIR/.env"
        ui_ok "VNSTAT_IFACE=$vnstat_iface"
    fi

    # Настройка vnstat
    ui_info "Настройка vnstat..."
    local vnstat_unit_file
    vnstat_unit_file=$(resolve_vnstat_unit_file)
    if [ -n "$vnstat_unit_file" ] && [ -f "$vnstat_unit_file" ]; then
        if grep -q "ExecStartPre=/bin/sleep 10" "$vnstat_unit_file"; then
            ui_ok "ExecStartPre уже настроен в vnstat.service"
        else
            local tmp
            tmp=$(mktemp)
            awk '/^\[Service\]$/{print; print "ExecStartPre=/bin/sleep 10"; next}1' \
                "$vnstat_unit_file" > "$tmp"
            cat "$tmp" > "$vnstat_unit_file"
            rm -f "$tmp"
            ui_ok "ExecStartPre добавлен в vnstat.service"
        fi
    else
        ui_fail "unit-файл vnstat.service не найден"
        exit 1
    fi

    systemctl daemon-reload
    systemctl enable vnstat
    check_error "Не удалось включить vnstat"
    systemctl restart vnstat
    check_error "Не удалось запустить vnstat"
    ui_ok "vnstat настроен и запущен"

    # Дополнительные настройки .env
    ui_info "Запись конфигурации .env..."
    set_env_value "ALLOWED_IPS" ""
    set_env_value "IP_RESTRICTION_MODE" "strict"
    grep -q "^OPENVPN_ROUTE_TOTAL_CIDR_LIMIT=" "$INSTALL_DIR/.env" 2>/dev/null || \
        set_env_value "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT" "1500"
    ui_ok "Конфигурация записана"

    # Итог установки
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        local DOMAIN="" BIND_VAL="" address
        grep -q "^DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null && \
            DOMAIN=$(grep "^DOMAIN=" "$INSTALL_DIR/.env" | cut -d'=' -f2 | tr -d '" ')
        BIND_VAL=$(grep "^BIND=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr -d '" ')

        if grep -q "^USE_HTTPS=true" "$INSTALL_DIR/.env" 2>/dev/null; then
            if [ -n "$DOMAIN" ]; then
                address="https://${DOMAIN}:${APP_PORT}"
            else
                address="https://$(hostname -I | awk '{print $1}'):${APP_PORT}"
            fi
        elif [ -n "$DOMAIN" ] && [ "$BIND_VAL" = "127.0.0.1" ]; then
            address="https://${DOMAIN}"
        elif [ -n "$DOMAIN" ]; then
            address="http://${DOMAIN}:${APP_PORT}"
        else
            address="http://$(hostname -I | awk '{print $1}'):${APP_PORT}"
        fi

        printf "\n"
        _m_top
        _m_title "Установка успешно завершена!"
        _m_sep
        _m_item "Адрес панели:"
        _m_item "  ${CYAN}${address}${NC}"
        _m_blank
        _m_item "Используйте учётные данные,"
        _m_item "созданные при инициализации БД."
        _m_bot
        printf "\n"

        copy_to_adminpanel
    else
        ui_fail "Сервис не запустился"
        journalctl -u "$SERVICE_NAME" -n 10 --no-pager
        finish_install_logging 1
        exit 1
    fi

    finish_install_logging 0
    press_any_key
}

# ─── Точка входа ──────────────────────────────────
main() {
    check_root
    init_logging

    case "${1:-}" in
    "--install")
        install
        ;;
    "--restart")
        restart_service
        ;;
    "--update")
        auto_update
        ;;
    "--backup")
        create_backup
        ;;
    "--restore")
        if [ -z "${2:-}" ]; then
            ui_fail "Укажите файл для восстановления"
            exit 1
        fi
        restore_backup "$2"
        ;;
    "--tests")
        run_unit_tests_summary
        exit $?
        ;;
    "--diagnose")
        run_site_diagnostics_cli
        exit $?
        ;;
    "--ip-add")
        if [ -z "${2:-}" ]; then
            ui_fail "Укажите IP: adminpanel.sh --ip-add <IP>"
            exit 1
        fi
        ip_whitelist_apply add "$2"
        exit $?
        ;;
    "--ip-remove")
        if [ -z "${2:-}" ]; then
            ui_fail "Укажите IP: adminpanel.sh --ip-remove <IP>"
            exit 1
        fi
        ip_whitelist_apply remove "$2"
        exit $?
        ;;
    "--ip-add-temp")
        if [ -z "${2:-}" ] || [ -z "${3:-}" ]; then
            ui_fail "Использование: adminpanel.sh --ip-add-temp <IP> <1h|12h|24h>"
            exit 1
        fi
        ip_whitelist_apply add-temp "$2" --duration "$3"
        exit $?
        ;;
    "--ip-list")
        ip_whitelist_run_cli list
        exit $?
        ;;
    *)
        if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
            ui_warn "AdminAntizapret не установлен."
            if ui_confirm "Установить сейчас?"; then
                install
                main_menu
            else
                exit 0
            fi
        else
            main_menu
        fi
        ;;
    esac
}

main "$@"
