#!/bin/bash

show_network_connections() {
    if command -v ss >/dev/null 2>&1; then
        ss -tuln
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tuln
    else
        ui_warn "Команды ss/netstat не найдены. Установите iproute2 или net-tools."
    fi
}

# Мониторинг системы
show_monitor() {
    while true; do
        clear
        _m_top
        _m_title "Мониторинг системы"
        _m_sep
        _m_item "1. CPU"
        _m_item "2. Память"
        _m_item "3. Диск"
        _m_item "4. Журнал сервиса"
        _m_item "5. Сетевые соединения"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"

        read -r -p "  Выберите действие [0-5]: " choice
        case $choice in
        1)
            printf "\n"
            top -bn1 | grep "Cpu(s)"
            press_any_key
            ;;
        2)
            printf "\n"
            free -h
            press_any_key
            ;;
        3)
            printf "\n"
            df -h
            press_any_key
            ;;
        4)
            printf "\n"
            journalctl -u "$SERVICE_NAME" -n 50 --no-pager
            press_any_key
            ;;
        5)
            printf "\n"
            show_network_connections
            press_any_key
            ;;
        0) break ;;
        *)
            ui_warn "Неверный выбор"
            sleep 1
            ;;
        esac
    done
}
