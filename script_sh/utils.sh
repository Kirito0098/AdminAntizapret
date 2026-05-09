#!/bin/bash

# ═══════════════════════════════════════════════════
#  UI Design System — AdminAntizapret
#  Требует: RED GREEN YELLOW CYAN BOLD DIM NC
#  (определены в adminpanel.sh до подключения модулей)
# ═══════════════════════════════════════════════════

# ─── Статусные сообщения ──────────────────────────
ui_ok()      { printf "  ${GREEN}✓${NC}  %s\n"  "$*"; }
ui_fail()    { printf "  ${RED}✗${NC}  %s\n"    "$*"; }
ui_warn()    { printf "  ${YELLOW}!${NC}  %s\n" "$*"; }
ui_info()    { printf "  ${CYAN}·${NC}  %s\n"   "$*"; }
ui_section() { printf "\n  ${BOLD}%s${NC}\n"    "$*"; }

# ─── Пауза ────────────────────────────────────────
press_any_key() {
    printf "\n  ${DIM}Нажмите любую клавишу...${NC}"
    read -n 1 -s -r
    printf "\n"
}

# ─── Запрос подтверждения (y/n) ───────────────────
# Использование: ui_confirm "Вопрос?" && действие
ui_confirm() {
    local prompt="${1:-Продолжить?}" _ans
    while true; do
        printf "  ${YELLOW}%s${NC} [y/n]: " "$prompt"
        read -r _ans
        _ans=$(printf '%s' "$_ans" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
        case "$_ans" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            *) ui_warn "Введите y или n" ;;
        esac
    done
}

# ─── Блок меню (ширина блока = 46 символов) ───────
_M_LINE="──────────────────────────────────────────────"

_m_top()   { printf "  ${CYAN}┌%s┐${NC}\n" "$_M_LINE"; }
_m_bot()   { printf "  ${CYAN}└%s┘${NC}\n" "$_M_LINE"; }
_m_sep()   { printf "  ${CYAN}├%s┤${NC}\n" "$_M_LINE"; }
_m_blank() { printf "  ${CYAN}│%46s│${NC}\n" ""; }

_m_title() {
    local t="$1" tlen="${#1}" pad_l pad_r
    pad_l=$(( (46 - tlen) / 2 ))
    pad_r=$(( 46 - tlen - pad_l ))
    [ "$pad_l" -lt 0 ] && pad_l=0
    [ "$pad_r" -lt 0 ] && pad_r=0
    # %Ns "" печатает N пробелов (однобайтовые) — корректно для кириллицы
    printf "  ${CYAN}│${NC}${BOLD}%${pad_l}s%s%${pad_r}s${NC}${CYAN}│${NC}\n" \
        "" "$t" ""
}

_m_item() {
    local text="$1" padlen
    padlen=$(( 44 - ${#text} ))
    [ "$padlen" -lt 0 ] && padlen=0
    # ${#text} считает символы, а не байты — правильно для UTF-8
    printf "  ${CYAN}│${NC}  %s%${padlen}s${CYAN}│${NC}\n" "$text" ""
}

# ─── Логирование ──────────────────────────────────

init_logging() {
    rotate_if_too_big "$LOG_FILE" "${MAX_MAIN_LOG_SIZE_MB:-20}"
    prune_logs_by_pattern "${LOG_FILE}.*.bak" "${MAX_MAIN_LOG_BACKUPS:-5}"
    touch "$LOG_FILE"
    # Дублируем вывод в лог, очищая ANSI-коды перед записью
    exec > >(tee >(sed 's/\x1B\[[0-9;]*[A-Za-z]//g; s/\r//g' >> "$LOG_FILE")) 2>&1
    log "Запуск скрипта"
}

prune_logs_by_pattern() {
    local pattern="$1"
    local keep_count="${2:-20}"
    local i=0 file entry
    local matches=() files=()

    while IFS= read -r file; do
        [ -n "$file" ] && matches+=("$file")
    done < <(compgen -G "$pattern" || true)

    [ "${#matches[@]}" -gt 0 ] || return 0

    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        files+=("${entry#*$'\t'}")
    done < <(
        for file in "${matches[@]}"; do
            printf '%s\t%s\n' "$(stat -c %Y "$file" 2>/dev/null || echo 0)" "$file"
        done | sort -nr
    )

    for file in "${files[@]}"; do
        i=$((i + 1))
        [ "$i" -gt "$keep_count" ] && rm -f -- "$file"
    done
}

rotate_if_too_big() {
    local file_path="$1" max_mb="${2:-20}" file_size=0 ts
    local max_bytes=$((max_mb * 1024 * 1024))
    [ -f "$file_path" ] || return 0
    file_size=$(stat -c%s "$file_path" 2>/dev/null || echo 0)
    if [ "$file_size" -ge "$max_bytes" ]; then
        ts=$(date '+%Y%m%d-%H%M%S')
        mv "$file_path" "${file_path}.${ts}.bak"
    fi
}

log() {
    printf '%s - %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE"
}

check_error() {
    if [ $? -ne 0 ]; then
        log "Ошибка: $1"
        if [ "${INSTALL_LOG_ACTIVE:-0}" -eq 1 ] && declare -F finish_install_logging >/dev/null 2>&1; then
            finish_install_logging 1
        fi
        ui_fail "$1" >&2
        exit 1
    fi
}
