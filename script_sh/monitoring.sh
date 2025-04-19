#!/bin/bash

# Мониторинг системы
show_monitor() {
    while true; do
        clear
        echo "${GREEN}┌────────────────────────────────────────────┐"
        echo "│          Мониторинг системы              │"
        echo "├────────────────────────────────────────────┤"
        echo "│ 1. Проверить использование CPU            │"
        echo "│ 2. Проверить использование памяти        │"
        echo "│ 3. Проверить использование диска         │"
        echo "│ 4. Просмотреть логи сервиса              │"
        echo "│ 5. Проверить сетевые соединения          │"
        echo "│ 0. Назад                                 │"
        echo "└────────────────────────────────────────────┘${NC}"
        
        read -p "Выберите действие: " choice
        case $choice in
            1) top -bn1 | grep "Cpu(s)" ;;
            2) free -h ;;
            3) df -h ;;
            4) journalctl -u $SERVICE_NAME -n 50 --no-pager ;;
            5) netstat -tuln ;;
            0) break ;;
            *) echo "${RED}Неверный выбор!${NC}"; sleep 1 ;;
        esac
        press_any_key
    done
}