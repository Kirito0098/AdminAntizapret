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

# Функция создания резервной копии
create_backup() {
    local backup_dir="/var/backups/antizapret"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$backup_dir/full_backup_$timestamp.tar.gz"
    local backup_meta_file="$backup_dir/full_backup_$timestamp.meta.txt"
    local backup_items=()

    log "Создание резервной копии в $backup_file"
    echo "${YELLOW}Создание полной резервной копии...${NC}"
    mkdir -p "$backup_dir"

    # Data-only backup: только пользовательские данные приложения (БД),
    # без инфраструктуры установки (.env, certs, nginx, systemd, cron, /root/antizapret).
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
        echo "${RED}Ошибка: не найдено данных для резервного копирования.${NC}"
        return 1
    fi

    {
        echo "backup_created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "backup_scope=data-only"
        echo "service_name=$SERVICE_NAME"
        echo "db_file=$DB_FILE"
        echo "data_items_count=${#backup_items[@]}"
    } >"$backup_meta_file"

    tar -czf "$backup_file" "${backup_items[@]}" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "${RED}Ошибка: не удалось создать архив резервной копии.${NC}"
        rm -f "$backup_file"
        return 1
    fi

    if ! tar -tzf "$backup_file" >/dev/null; then
        echo "${RED}Ошибка: резервная копия повреждена!${NC}"
        rm -f "$backup_file"
        return 1
    fi

    echo "${GREEN}Резервная копия создана:${NC}"
    ls -lh "$backup_file"
    echo "Для восстановления используйте: $0 --restore $backup_file"
    press_any_key
}

# Функция восстановления из резервной копии
restore_backup() {
    local backup_file=$1

    if [ ! -f "$backup_file" ]; then
        echo "${RED}Файл резервной копии не найден!${NC}"
        return 1
    fi

    log "Восстановление из резервной копии $backup_file"
    echo "${YELLOW}Восстановление из резервной копии...${NC}"

    systemctl stop "$SERVICE_NAME" 2>/dev/null || true

    if ! tar -xzf "$backup_file" -C /; then
        echo "${RED}Ошибка: не удалось распаковать резервную копию.${NC}"
        return 1
    fi

    if systemctl list-unit-files | grep -q "^${SERVICE_NAME}\.service"; then
        systemctl start "$SERVICE_NAME" 2>/dev/null || true
        if ! systemctl is-active --quiet "$SERVICE_NAME"; then
            echo "${RED}Данные восстановлены, но сервис $SERVICE_NAME не запустился автоматически.${NC}"
            echo "${YELLOW}Проверьте журнал: journalctl -u $SERVICE_NAME -n 100 --no-pager${NC}"
            return 1
        fi
    else
        echo "${YELLOW}Сервис $SERVICE_NAME не найден. Установите проект и затем повторите восстановление данных.${NC}"
    fi

    log "Восстановление завершено"
    echo "${GREEN}Восстановление данных завершено успешно!${NC}"
}
