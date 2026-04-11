#!/bin/bash

show_network_connections() {
    if command -v ss >/dev/null 2>&1; then
        ss -tuln
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tuln
    else
        echo "${YELLOW}Команды ss/netstat не найдены. Установите iproute2 или net-tools.${NC}"
    fi
}

# Мониторинг системы
show_monitor() {
    while true; do
        clear
        echo "${GREEN}┌────────────────────────────────────────────┐"
        echo "│          Мониторинг системы                │"
        echo "├────────────────────────────────────────────┤"
        echo "│ 1. Проверить использование CPU             │"
        echo "│ 2. Проверить использование памяти          │"
        echo "│ 3. Проверить использование диска           │"
        echo "│ 4. Просмотреть логи сервиса                │"
        echo "│ 5. Проверить сетевые соединения            │"
        echo "│ 0. Назад                                   │"
        echo "└────────────────────────────────────────────┘${NC}"

        read -r -p "Выберите действие: " choice
        case $choice in
        1) top -bn1 | grep "Cpu(s)" ;;
        2) free -h ;;
        3) df -h ;;
        4) journalctl -u "$SERVICE_NAME" -n 50 --no-pager ;;
        5) show_network_connections ;;
        0) break ;;
        *)
            echo "${RED}Неверный выбор!${NC}"
            sleep 1
            ;;
        esac
        press_any_key
    done
}
