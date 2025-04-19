#!/bin/bash

# Управление сервисом
restart_service() {
    echo "${YELLOW}Перезапуск сервиса...${NC}"
    systemctl restart $SERVICE_NAME
    check_status
}

# Проверка статуса сервиса
check_status() {
    echo "${YELLOW}Статус сервиса:${NC}"
    systemctl status $SERVICE_NAME --no-pager -l
    press_any_key
}

check_updates() {
    auto_update
    press_any_key
}

# Просмотр логов сервиса
show_logs() {
    echo "${YELLOW}Log File:${NC}"
    journalctl -u $SERVICE_NAME -n 50 --no-pager
    press_any_key
}

# Валидация конфигурации
validate_config() {
    local errors=0
    
    echo "${YELLOW}Проверка конфигурации...${NC}"
    
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        echo "${RED}Ошибка: .env файл не найден${NC}"
        errors=$((errors+1))
    fi
    
    if ! grep -q "SECRET_KEY=" "$INSTALL_DIR/.env"; then
        echo "${RED}Ошибка: SECRET_KEY не установлен${NC}"
        errors=$((errors+1))
    fi
    
    if [ ! -f "$DB_FILE" ]; then
        echo "${RED}Ошибка: База данных не найдена${NC}"
        errors=$((errors+1))
    fi
    
    if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        echo "${RED}Ошибка: Сервис systemd не найден${NC}"
        errors=$((errors+1))
    fi
    
    if [ $errors -eq 0 ]; then
        echo "${GREEN}Конфигурация в порядке.${NC}"
        return 0
    else
        echo "${RED}Найдено $errors ошибок в конфигурации.${NC}"
        return 1
    fi
}

# Проверка и установка прав выполнения для файлов
check_and_set_permissions() {
  echo "${YELLOW}Проверка и установка прав выполнения для client.sh и doall.sh...${NC}"
  
  files=("$INSTALL_DIR/client.sh" "$ANTIZAPRET_INSTALL_DIR/doall.sh")
  for file in "${files[@]}"; do
    if [ -f "$file" ]; then
      if [ ! -x "$file" ]; then
        chmod +x "$file"
        if [ $? -eq 0 ]; then
          echo "${GREEN}Права выполнения установлены для $file${NC}"
        else
          echo "${RED}Ошибка при установке прав выполнения для $file!${NC}"
        fi
      else
        echo "${GREEN}Права выполнения уже установлены для $file${NC}"
      fi
    else
      echo "${RED}Файл $file не найден!${NC}"
    fi
  done
  
  press_any_key
}

# Изменение порта сервиса
change_port() {
    echo "${YELLOW}Изменение порта сервиса...${NC}"
    read -p "Введите новый порт: " new_port
    
    # Проверка валидности порта
    if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [ "$new_port" -lt 1 ] || [ "$new_port" -gt 65535 ]; then
        echo "${RED}Неверный номер порта! Должен быть от 1 до 65535.${NC}"
        press_any_key
        return
    fi

    # Проверка занятости порта
    if lsof -i :"$new_port" > /dev/null 2>&1; then
        echo "${RED}Порт $new_port уже занят!${NC}"
        press_any_key
        return
    fi

    # Обновляем .env
    if [ -f "$INSTALL_DIR/.env" ]; then
        sed -i "/^APP_PORT=/d" "$INSTALL_DIR/.env"
    fi
    echo "APP_PORT=$new_port" >> "$INSTALL_DIR/.env"

    echo "${GREEN}Порт изменен на $new_port. Перезапустите сервис для применения изменений.${NC}"
    press_any_key
}

copy_to_adminpanel() {
    echo "${YELLOW}Копирование скрипта в ${ADMIN_PANEL_DIR}...${NC}"
    mkdir -p "$ADMIN_PANEL_DIR"
    cp "$0" "$ADMIN_PANEL_DIR/"
    chmod +x "$ADMIN_PANEL_DIR/$(basename "$0")"
    echo "${GREEN}[✓] Скрипт успешно скопирован в ${ADMIN_PANEL_DIR}${NC}"
}