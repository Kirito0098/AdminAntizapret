#!/bin/bash

# Перезапуск сервиса
restart_service() {
    ui_info "Перезапуск сервиса..."
    systemctl restart "$SERVICE_NAME"
    check_status
}

# Статус сервиса
check_status() {
    printf "\n"
    systemctl status "$SERVICE_NAME" --no-pager -l
    press_any_key
}

check_updates() {
    auto_update
    press_any_key
}

# Журнал сервиса
show_logs() {
    printf "\n"
    journalctl -u "$SERVICE_NAME" -n 50 --no-pager
    press_any_key
}

# Проверка конфигурации
validate_config() {
    local errors=0 env_file="$INSTALL_DIR/.env"

    ui_section "Проверка конфигурации"

    if [ ! -f "$env_file" ]; then
        ui_fail ".env файл не найден"
        errors=$((errors + 1))
    else
        if grep -q "^SECRET_KEY=" "$env_file"; then
            ui_ok "SECRET_KEY задан"
        else
            ui_fail "SECRET_KEY не установлен"
            errors=$((errors + 1))
        fi
        if grep -q "^VNSTAT_IFACE=" "$env_file"; then
            ui_ok "VNSTAT_IFACE задан"
        else
            ui_fail "VNSTAT_IFACE не установлен"
            errors=$((errors + 1))
        fi
    fi

    if [ -f "$DB_FILE" ]; then
        ui_ok "База данных найдена"
    else
        ui_fail "База данных не найдена"
        errors=$((errors + 1))
    fi

    if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        ui_ok "Systemd unit найден"
    else
        ui_fail "Systemd unit не найден"
        errors=$((errors + 1))
    fi

    printf "\n"
    if [ "$errors" -eq 0 ]; then
        ui_ok "Конфигурация в порядке"
        return 0
    else
        ui_fail "Найдено $errors ошибок"
        return 1
    fi
}

# Проверка и установка прав выполнения
check_and_set_permissions() {
    ui_section "Проверка прав выполнения"
    local files=("$INSTALL_DIR/client.sh" "$ANTIZAPRET_INSTALL_DIR/doall.sh")
    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            if [ ! -x "$file" ]; then
                if chmod +x "$file"; then
                    ui_ok "Права установлены: $file"
                else
                    ui_fail "Не удалось установить права: $file"
                fi
            else
                ui_ok "Права уже установлены: $file"
            fi
        else
            ui_warn "Файл не найден: $file"
        fi
    done
    press_any_key
}

_update_nginx_proxy_port_if_present() {
    local new_port="$1"
    local domain nginx_conf
    domain=$(grep "^DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr -d '" ')
    [ -n "$domain" ] || return 0
    nginx_conf="/etc/nginx/sites-available/${domain//./_}"
    [ -f "$nginx_conf" ] || return 0
    if grep -q "proxy_pass http://127.0.0.1:" "$nginx_conf"; then
        sed -i -E "s|proxy_pass http://127.0.0.1:[0-9]+;|proxy_pass http://127.0.0.1:${new_port};|" "$nginx_conf"
        nginx -t >/dev/null 2>&1 && systemctl reload nginx 2>/dev/null && \
            ui_ok "Nginx proxy_pass обновлён на порт $new_port" || \
            ui_warn "Порт в .env изменён, но Nginx не перезагружен — проверьте $nginx_conf"
    fi
}

# Изменение порта сервиса
change_port() {
    ui_info "Изменение порта сервиса..."
    local current_port=""
    get_port
    if [ -f "$INSTALL_DIR/.env" ]; then
        current_port=$(grep -oP 'APP_PORT=\K\d+' "$INSTALL_DIR/.env" 2>/dev/null || true)
    fi
    if [[ "$current_port" == "$APP_PORT" ]]; then
        ui_ok "Порт не изменился ($APP_PORT)"
        press_any_key
        return
    fi
    if [ -f "$INSTALL_DIR/.env" ]; then
        sed -i "/^APP_PORT=/d" "$INSTALL_DIR/.env"
    fi
    printf 'APP_PORT=%s\n' "$APP_PORT" >> "$INSTALL_DIR/.env"
    _update_nginx_proxy_port_if_present "$APP_PORT"
    ui_ok "Порт изменён на $APP_PORT. Перезапуск..."
    restart_service
}

copy_to_adminpanel() {
    ui_info "Копирование скрипта в $ADMIN_PANEL_DIR..."
    mkdir -p "$ADMIN_PANEL_DIR"
    cp "$0" "$ADMIN_PANEL_DIR/"
    chmod +x "$ADMIN_PANEL_DIR/$(basename "$0")"
    ui_ok "Скрипт скопирован в $ADMIN_PANEL_DIR"
}
