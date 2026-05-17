#!/bin/bash
# Подменю главной панели AdminAntizapret (группировка пунктов).

menu_service_panel() {
    while true; do
        clear
        _m_top
        _m_title "Сервис панели"
        _m_sep
        _m_item "1. Перезапустить сервис"
        _m_item "2. Статус сервиса"
        _m_item "3. Журнал сервиса"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"
        ui_info "Диагностика запуска сайта — пункт 7 в главном меню"

        read -r -p "  Выберите действие [0-3]: " choice
        case $choice in
        1) restart_service ;;
        2) check_status ;;
        3) show_logs ;;
        0) break ;;
        *)
            ui_warn "Неверный выбор"
            sleep 1
            ;;
        esac
    done
}

menu_administrators() {
    while true; do
        clear
        _m_top
        _m_title "Администраторы"
        _m_sep
        _m_item "1. Добавить администратора"
        _m_item "2. Удалить администратора"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"

        read -r -p "  Выберите действие [0-2]: " choice
        case $choice in
        1) add_admin ;;
        2) delete_admin ;;
        0) break ;;
        *)
            ui_warn "Неверный выбор"
            sleep 1
            ;;
        esac
    done
}

menu_network_https() {
    while true; do
        clear
        _m_top
        _m_title "Сеть и HTTPS"
        _m_sep
        _m_item "1. Изменить порт сервиса"
        _m_item "2. Изменить протокол (HTTP/HTTPS)"
        _m_item "3. Проверить конфликт портов 80/443"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"

        read -r -p "  Выберите действие [0-3]: " choice
        case $choice in
        1) change_port ;;
        2) change_protocol ;;
        3)
            check_openvpn_tcp_setting
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

menu_backups_updates() {
    while true; do
        clear
        _m_top
        _m_title "Резервные копии и обновления"
        _m_sep
        _m_item "1. Проверить обновления"
        _m_item "2. Создать резервную копию"
        _m_item "3. Восстановить из резервной копии"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"

        read -r -p "  Выберите действие [0-3]: " choice
        case $choice in
        1) check_updates ;;
        2) create_backup ;;
        3)
            read -r -p "  Путь к файлу резервной копии: " backup_file
            restore_backup "$backup_file"
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

menu_diagnostics_tests() {
    while true; do
        clear
        _m_top
        _m_title "Диагностика и тесты"
        _m_sep
        _m_item "1. Проверить и установить права"
        _m_item "2. Проверить конфигурацию"
        _m_item "3. Проверить окружение проекта"
        _m_item "4. Мониторинг системы"
        _m_item "5. Автотесты системы (pytest)"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"
        ui_info "Общий тест — пункт 8 в главном меню"

        read -r -p "  Выберите действие [0-5]: " choice
        case $choice in
        1) check_and_set_permissions ;;
        2)
            validate_config
            press_any_key
            ;;
        3)
            verify_project_environment
            press_any_key
            ;;
        4) show_monitor ;;
        5) show_unit_tests_menu ;;
        0) break ;;
        *)
            ui_warn "Неверный выбор"
            sleep 1
            ;;
        esac
    done
}
