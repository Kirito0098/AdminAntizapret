#!/bin/bash

# Резервное копирование через BackupManagerService (как в веб-панели)
BACKUP_CLI="$INSTALL_DIR/script_sh/backup_cli.py"

_backup_python() {
    if [ -x "$VENV_PATH/bin/python3" ]; then
        printf '%s\n' "$VENV_PATH/bin/python3"
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        printf '%s\n' "python3"
        return 0
    fi
    return 1
}

_run_backup_cli() {
    local python_bin

    if [ ! -f "$BACKUP_CLI" ]; then
        ui_fail "Не найден модуль резервного копирования: $BACKUP_CLI"
        return 1
    fi
    if ! python_bin=$(_backup_python); then
        ui_fail "Python3 не найден (нужен venv или python3 в PATH)"
        return 1
    fi
    "$python_bin" "$BACKUP_CLI" "$@"
}

# Создание резервной копии
create_backup() {
    local archive_path

    log "Создание резервной копии через BackupManagerService"
    ui_info "Создание резервной копии (db, env, data)..."

    if ! archive_path=$(_run_backup_cli create --install-dir "$INSTALL_DIR" --trigger manual); then
        ui_fail "Не удалось создать резервную копию"
        return 1
    fi

    ui_ok "Резервная копия создана:"
    printf "  ${DIM}%s${NC}\n" "$archive_path"
    printf "  ${DIM}Восстановление: %s --restore %s${NC}\n" "$0" "$archive_path"
    press_any_key
}

# Восстановление из резервной копии
restore_backup() {
    local backup_file="$1"
    local backup_label

    if [ -z "$backup_file" ]; then
        ui_fail "Не указан файл резервной копии"
        return 1
    fi

    if [ ! -f "$backup_file" ]; then
        ui_fail "Файл резервной копии не найден: $backup_file"
        return 1
    fi

    backup_label=$(basename "$backup_file")
    log "Восстановление из: $backup_file"
    ui_warn "Восстановление перезапишет текущие данные панели (БД, .env, data/)."
    ui_warn "Служба $SERVICE_NAME будет остановлена на время восстановления."
    if ! ui_confirm "Продолжить восстановление из ${backup_label}?"; then
        ui_info "Восстановление отменено"
        return 1
    fi

    ui_info "Восстановление из резервной копии..."
    if _run_backup_cli restore --install-dir "$INSTALL_DIR" "$backup_file"; then
        log "Восстановление завершено"
        ui_ok "Данные восстановлены"
        return 0
    fi

    ui_fail "Не удалось восстановить данные из резервной копии"
    ui_info "Проверьте: journalctl -u $SERVICE_NAME -n 100 --no-pager"
    return 1
}
