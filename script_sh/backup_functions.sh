#!/bin/bash

append_if_exists() {
    local -n _arr_ref=$1
    shift
    local path
    for path in "$@"; do
        [ -e "$path" ] || continue
        _arr_ref+=("$path")
    done
}

# Создание резервной копии
create_backup() {
    local backup_dir="/var/backups/antizapret"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$backup_dir/full_backup_${timestamp}.tar.gz"
    local backup_meta="$backup_dir/full_backup_${timestamp}.meta.txt"
    local backup_items=()

    log "Создание резервной копии: $backup_file"
    ui_info "Создание резервной копии..."
    mkdir -p "$backup_dir"

    append_if_exists backup_items \
        "$DB_FILE" \
        "$DB_FILE-wal" \
        "$DB_FILE-shm" \
        "$INSTALL_DIR/users.db" \
        "$INSTALL_DIR/users.db-wal" \
        "$INSTALL_DIR/users.db-shm" \
        "$INSTALL_DIR/instance/site.db" \
        "$INSTALL_DIR/instance/site.db-wal" \
        "$INSTALL_DIR/instance/site.db-shm"

    if [ "${#backup_items[@]}" -eq 0 ]; then
        ui_fail "Нет данных для резервного копирования"
        return 1
    fi

    {
        printf 'backup_created_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf 'backup_scope=data-only\n'
        printf 'service_name=%s\n' "$SERVICE_NAME"
        printf 'db_file=%s\n' "$DB_FILE"
        printf 'data_items_count=%d\n' "${#backup_items[@]}"
    } > "$backup_meta"

    if ! tar -czf "$backup_file" "${backup_items[@]}" 2>/dev/null; then
        ui_fail "Не удалось создать архив резервной копии"
        rm -f "$backup_file"
        return 1
    fi

    if ! tar -tzf "$backup_file" >/dev/null; then
        ui_fail "Резервная копия повреждена"
        rm -f "$backup_file"
        return 1
    fi

    ui_ok "Резервная копия создана:"
    printf "  ${DIM}%s${NC}\n" "$backup_file"
    printf "  ${DIM}Восстановление: %s --restore %s${NC}\n" "$0" "$backup_file"
    press_any_key
}

# Восстановление из резервной копии
restore_backup() {
    local backup_file="$1"

    if [ ! -f "$backup_file" ]; then
        ui_fail "Файл резервной копии не найден: $backup_file"
        return 1
    fi

    log "Восстановление из: $backup_file"
    ui_info "Восстановление из резервной копии..."

    systemctl stop "$SERVICE_NAME" 2>/dev/null || true

    if ! tar -xzf "$backup_file" -C /; then
        ui_fail "Не удалось распаковать резервную копию"
        return 1
    fi

    if systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE_NAME}\.service"; then
        systemctl start "$SERVICE_NAME" 2>/dev/null || true
        if ! systemctl is-active --quiet "$SERVICE_NAME"; then
            ui_warn "Данные восстановлены, но сервис не запустился"
            ui_info "Проверьте: journalctl -u $SERVICE_NAME -n 100 --no-pager"
            return 1
        fi
    else
        ui_warn "Сервис $SERVICE_NAME не найден. Установите проект и повторите восстановление."
    fi

    log "Восстановление завершено"
    ui_ok "Данные восстановлены"
}
