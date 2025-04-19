#!/bin/bash

# Функция создания резервной копии
create_backup() {
    local backup_dir="/var/backups/antizapret"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$backup_dir/full_backup_$timestamp.tar.gz"
    
    log "Создание резервной копии в $backup_file"
    echo "${YELLOW}Создание полной резервной копии...${NC}"
    mkdir -p "$backup_dir"
    
    tar -czf "$backup_file" \
        "$INSTALL_DIR" \
        /etc/systemd/system/$SERVICE_NAME.service \
        "$DB_FILE" \
        /etc/ssl/certs/admin-antizapret.crt 2>/dev/null \
        /etc/ssl/private/admin-antizapret.key 2>/dev/null \
        /etc/letsencrypt/live/$DOMAIN 2>/dev/null
    
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
    
    systemctl stop $SERVICE_NAME 2>/dev/null
    tar -xzf "$backup_file" -C /
    systemctl daemon-reload
    systemctl start $SERVICE_NAME
    
    log "Восстановление завершено"
    echo "${GREEN}Восстановление завершено успешно!${NC}"
}