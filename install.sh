#!/bin/bash
# AdminAntizapret — Установщик

export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"
export DEBIAN_FRONTEND=noninteractive

# ─── Конфигурация ─────────────────────────────────
INSTALL_DIR="/opt/AdminAntizapret"
REPO_URL="https://github.com/Kirito0098/AdminAntizapret.git"
SCRIPT_SH_DIR="$INSTALL_DIR/script_sh"
MAIN_SCRIPT="$SCRIPT_SH_DIR/adminpanel.sh"
LOG_FILE="/var/log/adminantizapret-bootstrap-$(date '+%Y%m%d-%H%M%S').log"
LOG_KEEP_COUNT=30
MODE="install"

REQUIRED_COMMANDS=(apt-get dpkg-query systemctl find)

REQUIRED_PACKAGES=(
    apt-utils whiptail iproute2 dnsutils net-tools git
    vnstat openssl python3 python3-pip python3-venv
    wget cron ca-certificates
)

# ─── Цвета (только в интерактивном терминале) ─────
if [ -t 1 ] && tput colors >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    NC='\033[0m'
    USE_SPIN=1
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' DIM='' NC=''
    USE_SPIN=0
fi
[ -t 1 ] || USE_SPIN=0

# ─── Логирование ──────────────────────────────────
_LOG_READY=0

log_init() {
    if ! touch "$LOG_FILE" 2>/dev/null; then
        printf '%bОшибка: не удалось создать лог %s%b\n' "$RED" "$LOG_FILE" "$NC" >&2
        exit 1
    fi
    chmod 600 "$LOG_FILE" 2>/dev/null || true
    _LOG_READY=1
    _log "════════════════════════════════════════"
    _log "  AdminAntizapret Installer"
    _log "  Дата    : $(date '+%Y-%m-%d %H:%M:%S %Z')"
    _log "  Хост    : $(hostname 2>/dev/null || printf '?')"
    _log "  Польз.  : $(id 2>/dev/null)"
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        _log "  ОС      : ${PRETTY_NAME:-${ID}}"
    fi
    _log "════════════════════════════════════════"
}

_log() {
    [ "$_LOG_READY" -eq 1 ] || return 0
    printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
}

# ─── Очистка старых логов ─────────────────────────
_prune_logs() {
    local i=0 f
    while IFS= read -r f; do
        i=$((i + 1))
        [ "$i" -gt "$LOG_KEEP_COUNT" ] && rm -f -- "$f"
    done < <(
        find /var/log -maxdepth 1 -type f \
            -name 'adminantizapret-bootstrap-*.log' \
            -printf '%T@ %p\n' 2>/dev/null \
            | sort -rn \
            | awk '{$1=""; sub(/^ /,""); print}'
    )
}

# ─── UI ───────────────────────────────────────────
_ui_ok()   { printf "  %b✓%b  %s\n"  "$GREEN"  "$NC" "$1"; }
_ui_fail() { printf "  %b✗%b  %s\n"  "$RED"    "$NC" "$1"; }
_ui_warn() { printf "  %b!%b  %s\n"  "$YELLOW" "$NC" "$1"; }
_ui_info() { printf "  %b·%b  %s\n"  "$CYAN"   "$NC" "$1"; }

_ui_header() {
    printf '\n'
    printf "  %bAdminAntizapret%b — Установщик\n" "$BOLD" "$NC"
    printf "  %bЛог: %s%b\n" "$DIM" "$LOG_FILE" "$NC"
    printf "  %bПервая установка может занять 5–10 минут%b\n" "$DIM" "$NC"
    printf '\n'
}

_ui_done() {
    printf '\n  %b%s%b\n' "$GREEN" "$1" "$NC"
    printf "  %bЛог сохранён: %s%b\n\n" "$DIM" "$LOG_FILE" "$NC"
}

_ui_err() {
    printf '\n  %b%s%b\n' "$RED" "$1" "$NC"
    printf "  %bПодробности: %s%b\n\n" "$DIM" "$LOG_FILE" "$NC"
}

# ─── Спиннер ──────────────────────────────────────
_SP_PID=
_SP_START=0
_SP_FR=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

_spin_start() {
    [ "$USE_SPIN" -eq 0 ] && return
    local msg="$1"
    _SP_START=$(date +%s)
    (
        trap '' INT TERM HUP
        i=0
        start=$(date +%s)
        while true; do
            elapsed=$(( $(date +%s) - start ))
            if [ "$elapsed" -ge 60 ]; then
                timer="$(( elapsed / 60 ))м$(( elapsed % 60 ))с"
            else
                timer="${elapsed}с"
            fi
            printf '\r  %b%s%b  %s  %b(%s)%b  ' \
                "$CYAN" "${_SP_FR[$i]}" "$NC" "$msg" "$DIM" "$timer" "$NC"
            i=$(( (i + 1) % 10 ))
            sleep 0.5
        done
    ) &
    _SP_PID=$!
}

_spin_stop() {
    [ -z "${_SP_PID:-}" ] && return
    kill "$_SP_PID" 2>/dev/null || true
    { wait "$_SP_PID"; } 2>/dev/null || true
    _SP_PID=
    printf '\r%80s\r' ''
}

# ─── run_step: шаг с прогрессом ───────────────────
# Использование: run_step "Описание" cmd [args...]
run_step() {
    local desc="$1"
    shift
    _log ">>> ШАГ: $desc"

    _spin_start "$desc"
    "$@" >> "$LOG_FILE" 2>&1
    local rc=$?
    _spin_stop

    if [ "$rc" -eq 0 ]; then
        _ui_ok "$desc"
        _log "    OK"
    else
        _ui_fail "$desc"
        _log "    ОШИБКА (код выхода: $rc)"
    fi
    return "$rc"
}

# ─── Проверка ОС ──────────────────────────────────
_check_os() {
    [ -r /etc/os-release ] || return 1
    # shellcheck disable=SC1091
    . /etc/os-release
    local id="${ID:-}" major
    major="${VERSION_ID%%.*}"
    case "$id" in
        ubuntu) [ "${major:-0}" -ge 24 ] 2>/dev/null ;;
        debian) [ "${major:-0}" -ge 13 ] 2>/dev/null ;;
        *)      return 1 ;;
    esac
}

# ─── Ожидание блокировки apt ─────────────────────
# На свежем Ubuntu apt-daily/unattended-upgrades держат lock после загрузки
_wait_apt_lock() {
    local lock="/var/lib/dpkg/lock-frontend"
    local waited=0

    # Проверяем через lsof: если lock занят — ждём
    if ! lsof "$lock" >/dev/null 2>&1; then
        return 0
    fi

    _spin_stop  # останавливаем спиннер чтобы написать сообщение
    printf "  ${YELLOW}!${NC}  Ожидание освобождения блокировки apt...\n"
    printf "  ${DIM}(Фоновое обновление Ubuntu займёт несколько минут)${NC}\n"
    _log "Ожидание блокировки apt (занята другим процессом)"

    while lsof "$lock" >/dev/null 2>&1; do
        sleep 2
        waited=$((waited + 2))
        if [ "$((waited % 20))" -eq 0 ]; then
            printf "  ${DIM}Ожидаем apt: %d сек...${NC}\n" "$waited"
            _log "Ожидание apt lock: ${waited}с"
        fi
    done

    _log "Блокировка снята через ${waited}с"
    printf "  ${GREEN}✓${NC}  Блокировка снята (ожидали %d сек)\n" "$waited"
    # Пересоздаём спиннер для следующего шага (вызывающий сам запустит)
}

# ─── Шаги установки ───────────────────────────────

_do_vnstat() {
    local svc i
    svc=$(systemctl list-unit-files --no-legend 2>/dev/null \
        | grep -oE '^vnstatd?\.service' \
        | head -1)
    svc="${svc%.service}"
    if [ -z "$svc" ]; then
        printf 'Служба vnstat/vnstatd не найдена в системе\n'
        return 1
    fi
    systemctl enable --now "$svc"
    for i in $(seq 1 10); do
        systemctl is-active --quiet "$svc" && return 0
        sleep 1
    done
    printf 'Служба %s не запустилась в течение 10 секунд\n' "$svc"
    return 1
}

_do_clone_or_update() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        _log "Обновление репозитория (git pull)"
        git -C "$INSTALL_DIR" pull
    else
        if [ -d "$INSTALL_DIR" ]; then
            local bk="${INSTALL_DIR}.backup-$(date '+%Y%m%d-%H%M%S')"
            _log "Перемещение существующей директории в: $bk"
            mv "$INSTALL_DIR" "$bk"
        fi
        _log "Клонирование репозитория: $REPO_URL"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
}

_do_permissions() {
    find "$SCRIPT_SH_DIR" -type f -name "*.sh" -exec chmod +x {} \;
}

_do_write_env() {
    [ -f "$INSTALL_DIR/.env" ] || touch "$INSTALL_DIR/.env"
    grep -q "^OPENVPN_ROUTE_TOTAL_CIDR_LIMIT=" "$INSTALL_DIR/.env" \
        || printf 'OPENVPN_ROUTE_TOTAL_CIDR_LIMIT=1500\n' >> "$INSTALL_DIR/.env"
}

# ─── Режим --check ────────────────────────────────
_run_check() {
    printf '\n  %bAdminAntizapret%b — Проверка окружения\n\n' "$BOLD" "$NC"
    local fail=0

    if [ "$(id -u)" -eq 0 ]; then
        _ui_ok "Права root"
    else
        _ui_warn "Не root (для установки требуется sudo)"
    fi

    if _check_os; then
        # shellcheck disable=SC1091
        . /etc/os-release 2>/dev/null || true
        _ui_ok "ОС: ${PRETTY_NAME:-${ID}}"
    else
        [ -r /etc/os-release ] && . /etc/os-release 2>/dev/null || true
        _ui_fail "Неподдерживаемая ОС: ${PRETTY_NAME:-неизвестно}"
        _ui_info "Требуется Ubuntu ≥ 24.04 или Debian ≥ 13"
        fail=1
    fi

    local bad_cmds=()
    for _cmd in "${REQUIRED_COMMANDS[@]}"; do
        command -v "$_cmd" >/dev/null 2>&1 || bad_cmds+=("$_cmd")
    done
    if [ "${#bad_cmds[@]}" -eq 0 ]; then
        _ui_ok "Системные утилиты"
    else
        _ui_fail "Отсутствуют утилиты: ${bad_cmds[*]}"
        fail=1
    fi

    if command -v dpkg-query >/dev/null 2>&1; then
        local miss=() pkg st
        for pkg in "${REQUIRED_PACKAGES[@]}"; do
            st=$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null || true)
            [[ "$st" == *"ok installed"* ]] || miss+=("$pkg")
        done
        if [ "${#miss[@]}" -eq 0 ]; then
            _ui_ok "Все пакеты установлены"
        else
            _ui_fail "Не установлены (${#miss[@]} шт.): ${miss[*]}"
            fail=1
        fi
    else
        _ui_fail "dpkg-query недоступен — проверка пакетов невозможна"
        fail=1
    fi

    printf '\n'
    if [ "$fail" -eq 0 ]; then
        printf "  %bСистема готова к установке.%b\n\n" "$GREEN" "$NC"
    else
        printf "  %bЕсть проблемы. Исправьте их и повторите запуск.%b\n\n" "$RED" "$NC"
    fi
    return "$fail"
}

# ─── Аргументы ────────────────────────────────────
_usage() {
    printf '\nИспользование:\n'
    printf '  sudo bash install.sh            — полная установка\n'
    printf '  sudo bash install.sh --install  — полная установка\n'
    printf '       bash install.sh --check    — проверка окружения\n'
    printf '       bash install.sh --help     — справка\n\n'
}

_parse_args() {
    case "${1:-}" in
        ""|"--install") MODE="install" ;;
        "--check"|"--self-check") MODE="check" ;;
        "-h"|"--help") _usage; exit 0 ;;
        *)
            printf '%bНеизвестный аргумент: %s%b\n' "$RED" "$1" "$NC" >&2
            _usage
            exit 1
            ;;
    esac
}

# ─── Ловушка выхода ───────────────────────────────
_install_done=0
_trap_exit() {
    local rc=$?
    _spin_stop
    if [ "$_install_done" -eq 0 ] && [ "$rc" -ne 0 ] && [ "$_LOG_READY" -eq 1 ]; then
        _log "=== УСТАНОВКА ПРЕРВАНА (код: $rc) ==="
        printf '\n  %bУстановка прервана.%b\n' "$RED" "$NC"
        printf "  %bПодробности в лог-файле: %s%b\n\n" "$DIM" "$LOG_FILE" "$NC"
    fi
}
trap '_trap_exit' EXIT

# ─── Точка входа ──────────────────────────────────
_parse_args "$@"

if [ "$MODE" = "check" ]; then
    _run_check
    exit $?
fi

# ── Предварительные проверки (до инициализации лога) ──

if [ "$(id -u)" -ne 0 ]; then
    printf '%bОшибка: запустите скрипт с правами root (sudo bash install.sh).%b\n' "$RED" "$NC" >&2
    exit 1
fi

for _cmd in "${REQUIRED_COMMANDS[@]}"; do
    command -v "$_cmd" >/dev/null 2>&1 || {
        printf '%bОшибка: не найдена команда "%s". Установите её и повторите.%b\n' "$RED" "$_cmd" "$NC" >&2
        exit 1
    }
done
unset _cmd

if ! _check_os; then
    [ -r /etc/os-release ] && . /etc/os-release 2>/dev/null || true
    printf '%bОшибка: неподдерживаемая ОС: %s%b\n' "$RED" "${PRETTY_NAME:-неизвестно}" "$NC" >&2
    printf '%bПоддерживается Ubuntu ≥ 24.04 и Debian ≥ 13%b\n' "$YELLOW" "$NC" >&2
    exit 1
fi

# ── Инициализация лога ────────────────────────────
_prune_logs
log_init

_ui_header

# ─── Шаг 1: Пакеты ───────────────────────────────
_log "Проверка установленных пакетов..."
_miss=()
for _pkg in "${REQUIRED_PACKAGES[@]}"; do
    _st=$(dpkg-query -W -f='${Status}' "$_pkg" 2>/dev/null || true)
    [[ "$_st" == *"ok installed"* ]] || _miss+=("$_pkg")
done
unset _pkg _st

if [ "${#_miss[@]}" -gt 0 ]; then
    _log "Отсутствуют пакеты: ${_miss[*]}"

    # Ждём освобождения блокировки перед apt (Ubuntu держит её при автообновлении)
    _wait_apt_lock

    # -o Acquire::ForceIPv4=true — исключает зависание на IPv6-таймаутах
    run_step "Обновление индексов пакетов" \
        apt-get -o Acquire::ForceIPv4=true update \
        || { _ui_err "Не удалось обновить apt. Проверьте сеть."; exit 1; }

    run_step "Установка пакетов (${#_miss[@]} шт.)" \
        apt-get -o Acquire::ForceIPv4=true install -y "${_miss[@]}" \
        || { _ui_err "Не удалось установить пакеты."; exit 1; }
else
    _log "Все пакеты уже установлены"
    _ui_ok "Все пакеты уже установлены"
fi
unset _miss

# ─── Шаг 2: vnStat ───────────────────────────────
run_step "Настройка vnStat" \
    _do_vnstat \
    || { _ui_err "Не удалось настроить vnStat."; exit 1; }

# ─── Шаг 3: Репозиторий ──────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    _repo_label="Обновление репозитория"
else
    _repo_label="Загрузка AdminAntizapret"
fi

run_step "$_repo_label" \
    _do_clone_or_update \
    || { _ui_err "Не удалось получить репозиторий. Проверьте сеть."; exit 1; }
unset _repo_label

if [ ! -f "$MAIN_SCRIPT" ]; then
    _ui_fail "Основной скрипт не найден: $MAIN_SCRIPT"
    _log "ОШИБКА: файл не существует: $MAIN_SCRIPT"
    _ui_err "Установка не завершена — репозиторий повреждён."
    exit 1
fi

# ─── Шаг 4: Права и конфигурация ─────────────────
run_step "Настройка прав на скрипты" \
    _do_permissions \
    || { _ui_err "Не удалось установить права на скрипты."; exit 1; }

run_step "Запись начальной конфигурации" \
    _do_write_env \
    || { _ui_err "Не удалось записать конфигурацию."; exit 1; }

# ─── Завершение ───────────────────────────────────
_install_done=1
_log "=== BOOTSTRAP ЗАВЕРШЁН УСПЕШНО ==="
_ui_done "Установка завершена. Запускаем AdminAntizapret..."

exec bash "$MAIN_SCRIPT"
