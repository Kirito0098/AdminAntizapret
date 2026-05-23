#!/bin/bash
# Управление whitelist IP (постоянный и временный).

IP_WHITELIST_CLI="$INSTALL_DIR/script_sh/ip_whitelist_cli.py"

ip_whitelist_run_cli() {
    if ! "$VENV_PATH/bin/python" "$IP_WHITELIST_CLI" --install-dir "$INSTALL_DIR" "$@"; then
        return 1
    fi
    return 0
}

ip_whitelist_apply() {
    if ip_whitelist_run_cli "$@"; then
        ui_info "Перезапуск сервиса для применения изменений..."
        systemctl restart "$SERVICE_NAME" >/dev/null 2>&1 || true
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            ui_ok "Сервис перезапущен"
        else
            ui_warn "Проверьте статус: systemctl status $SERVICE_NAME"
        fi
        return 0
    fi
    return 1
}

ip_whitelist_list() {
    ui_section "Белый список IP"
    ip_whitelist_run_cli list || ui_fail "Не удалось получить список"
    press_any_key
}

ip_whitelist_add_permanent() {
    ui_section "Добавить IP (постоянно)"
    local ip
    read -r -p "  IP или подсеть (CIDR): " ip
    if [ -z "$ip" ]; then
        ui_fail "IP не указан"
        press_any_key
        return
    fi
    if ip_whitelist_apply add "$ip"; then
        ui_ok "IP добавлен"
    else
        ui_fail "Не удалось добавить IP"
    fi
    press_any_key
}

ip_whitelist_add_temp_menu() {
    ui_section "Добавить IP (временно)"
    local ip duration
    read -r -p "  IP (без CIDR): " ip
    if [ -z "$ip" ]; then
        ui_fail "IP не указан"
        press_any_key
        return
    fi
    printf "\n"
    _m_item "1. 1 час"
    _m_item "2. 12 часов"
    _m_item "3. 24 часа"
    printf "\n"
    read -r -p "  Срок [1-3]: " choice
    case "$choice" in
    1) duration="1h" ;;
    2) duration="12h" ;;
    3) duration="24h" ;;
    *)
        ui_fail "Неверный выбор"
        press_any_key
        return
        ;;
    esac
    if ip_whitelist_apply add-temp "$ip" --duration "$duration"; then
        ui_ok "Временный доступ добавлен ($duration)"
    else
        ui_fail "Не удалось добавить (включите IP-ограничения и укажите одиночный IP)"
    fi
    press_any_key
}

ip_whitelist_remove() {
    ui_section "Удалить IP"
    local ip
    read -r -p "  IP для удаления: " ip
    if [ -z "$ip" ]; then
        ui_fail "IP не указан"
        press_any_key
        return
    fi
    if ip_whitelist_apply remove "$ip"; then
        ui_ok "IP удалён"
    else
        ui_fail "IP не найден"
    fi
    press_any_key
}

menu_ip_whitelist() {
    while true; do
        clear
        _m_top
        _m_title "Белый список IP"
        _m_sep
        _m_item "1. Показать список"
        _m_item "2. Добавить постоянно"
        _m_item "3. Добавить временно (1ч / 12ч / 24ч)"
        _m_item "4. Удалить IP"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"

        read -r -p "  Выберите действие [0-4]: " choice
        case $choice in
        1) ip_whitelist_list ;;
        2) ip_whitelist_add_permanent ;;
        3) ip_whitelist_add_temp_menu ;;
        4) ip_whitelist_remove ;;
        0) break ;;
        *)
            ui_warn "Неверный выбор"
            sleep 1
            ;;
        esac
    done
}
