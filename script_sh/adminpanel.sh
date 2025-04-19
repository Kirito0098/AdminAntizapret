#!/bin/bash

# Полный менеджер AdminAntizapret
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"

# Цвета для вывода
RED=$(printf '\033[31m')
GREEN=$(printf '\033[32m')
YELLOW=$(printf '\033[33m')
NC=$(printf '\033[0m') # No Color

# Основные параметры
INSTALL_DIR="/opt/AdminAntizapret"
VENV_PATH="$INSTALL_DIR/venv"
SERVICE_NAME="admin-antizapret"
DEFAULT_PORT="5050"
APP_PORT="$DEFAULT_PORT"
DB_FILE="$INSTALL_DIR/instance/users.db"
ANTIZAPRET_INSTALL_DIR="/root/antizapret"
ANTIZAPRET_INSTALL_SCRIPT="https://raw.githubusercontent.com/GubernievS/AntiZapret-VPN/main/setup.sh"
LOG_FILE="/var/log/adminpanel.log"
INCLUDE_DIR="$INSTALL_DIR/script_sh"
ADMIN_PANEL_DIR="/root/AdminPanel"

modules=(
    "ssl_setup"
    "backup_functions"
    "monitoring"
    "service_functions"
    "uninstall"
    "utils"
    "user_management"
)

for module in "${modules[@]}"; do
    if [ -f "$INCLUDE_DIR/${module}.sh" ]; then
        . "$INCLUDE_DIR/${module}.sh"
    else
        echo "${RED}Ошибка: не найден файл ${module}.sh${NC}" >&2
        exit 1
    fi
done

# Генерируем случайный секретный ключ
SECRET_KEY=$(openssl rand -hex 32)

# Функция проверки занятости порта
check_port() {
    port=$1
    if command -v ss >/dev/null 2>&1; then
        if ss -tuln | grep -q ":$port "; then
            return 0
        fi
    elif command -v netstat >/dev/null 2>&1; then
        if netstat -tuln | grep -q ":$port "; then
            return 0
        fi
    elif command -v lsof >/dev/null 2>&1; then
        if lsof -i :$port >/dev/null; then
            return 0
        fi
    elif grep -q ":$port " /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
        return 0
    else
        printf "%s\n" "${YELLOW}Не удалось проверить порт (установите ss, netstat или lsof для точной проверки)${NC}"
        return 1
    fi
    return 1
}

# Проверка зависимостей
check_dependencies() {
    echo "${YELLOW}Установка зависимостей...${NC}" 
    apt-get update --quiet --quiet && apt-get install -y --quiet --quiet apt-utils > /dev/null
    apt-get install -y --quiet --quiet python3 python3-pip git wget openssl python3-venv cron > /dev/null
    echo "${GREEN}[✓] Готово${NC}"
    check_error "Не удалось установить зависимости"
}

# Проверка прав root
check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log "Попытка запуска без прав root"
    printf "%s\n" "${RED}Этот скрипт должен быть запущен с правами root!${NC}" >&2
    exit 1
  fi
}

# Установка AntiZapret-VPN
install_antizapret() {
    log "Проверка наличия AntiZapret-VPN"
    echo "${YELLOW}Проверка установленного AntiZapret-VPN...${NC}"

    # Функция проверки установки AntiZapret
    check_antizapret_installed() {
        if systemctl is-active --quiet antizapret.service 2>/dev/null; then
            return 0
        fi
        if [ -d "/root/antizapret" ]; then
            return 0
        fi
        return 1
    }

    # Проверяем установлен ли AntiZapret
    if check_antizapret_installed; then
        log "AntiZapret-VPN обнаружен в системе"
        echo "${GREEN}AntiZapret-VPN уже установлен (обнаружен сервис или директория).${NC}"
        return 0
    fi

    log "AntiZapret-VPN не установлен"
    echo "${RED}ВНИМАНИЕ! Модуль AntiZapret-VPN не установлен!${NC}"
    echo ""
    echo "${YELLOW}Это обязательный компонент для работы системы.${NC}"
    echo "Пожалуйста, установите его вручную следующими командами:"
    echo ""
    echo "1. Скачайте и запустите установочный скрипт:"
    echo "${CYAN} bash <(wget --no-hsts -qO- https://raw.githubusercontent.com/GubernievS/AntiZapret-VPN/main/setup.sh) | bash${NC}"
    echo ""
    echo "2. Затем запустите этот скрипт снова"
    echo ""
    echo "${YELLOW}Без этого модуля работа системы невозможна.${NC}"
    echo ""
    exit 1
}

# Автоматическое обновление
auto_update() {
    log "Проверка обновлений"
    echo "${YELLOW}Проверка обновлений...${NC}"
    cd "$INSTALL_DIR" || return 1
    
    git fetch origin main
    
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
        echo "${GREEN}Найдены обновления. Установка...${NC}"
        git pull origin main
        "$VENV_PATH/bin/pip" install -q -r requirements.txt
        systemctl restart $SERVICE_NAME
        echo "${GREEN}Обновление завершено!${NC}"
    else
        echo "${GREEN}Система актуальна.${NC}"
    fi
}

# Главное меню
main_menu() {
    while true; do
        clear
        printf "%s\n" "${GREEN}"
        printf "┌────────────────────────────────────────────┐\n"
        printf "│          Меню управления AdminAntizapret   │\n"
        printf "├────────────────────────────────────────────┤\n"
        printf "│ 1. Добавить администратора                 │\n"
        printf "│ 2. Удалить администратора                  │\n"
        printf "│ 3. Перезапустить сервис                    │\n"
        printf "│ 4. Проверить статус сервиса                │\n"
        printf "│ 5. Просмотреть логи                        │\n"
        printf "│ 6. Проверить обновления                    │\n"
        printf "│ 7. Создать резервную копию                 │\n"
        printf "│ 8. Восстановить из резервной копии         │\n"
        printf "│ 9. Удалить AdminAntizapret                 │\n"
        printf "│ 10. Проверить и установить права           │\n"
        printf "│ 11. Изменить порт сервиса                  │\n"
        printf "│ 12. Мониторинг системы                     │\n"
        printf "│ 13. Проверить конфигурацию                 │\n"
        printf "│ 0. Выход                                   │\n"
        printf "└────────────────────────────────────────────┘\n"
        printf "%s\n" "${NC}"
        
        read -p "Выберите действие [0-13]: " choice
        case $choice in
            1) add_admin ;;
            2) delete_admin ;;
            3) restart_service ;;
            4) check_status ;;
            5) show_logs ;;
            6) check_updates ;;
            7) create_backup ;;
            8) 
                read -p "Введите путь к файлу резервной копии: " backup_file
                restore_backup "$backup_file"
                press_any_key
                ;;
            9) uninstall ;;
            10) check_and_set_permissions ;;
            11) change_port ;;
            12) show_monitor ;;
            13) validate_config; press_any_key ;;
            0) exit 0 ;;
            *) printf "%s\n" "${RED}Неверный выбор!${NC}"; sleep 1 ;;
        esac
    done
}

# Установка AdminAntizapret
install() {
    clear
    printf "%s\n" "${GREEN}"
    printf "┌────────────────────────────────────────────┐\n"
    printf "│          Установка AdminAntizapret         │\n"
    printf "└────────────────────────────────────────────┘\n"
    printf "%s\n" "${NC}"

# Проверка установки AntiZapret-VPN
check_antizapret_installed() {
  [ -d "$ANTIZAPRET_INSTALL_DIR" ]
}

    # Проверка установки AntiZapret-VPN
    echo "${YELLOW}Проверка установки AntiZapret-VPN...${NC}"
    if ! check_antizapret_installed; then
        install_antizapret
        # После установки делаем дополнительную проверку
        if ! check_antizapret_installed; then
            echo "${RED}[!] Критическая ошибка: AntiZapret-VPN не установлен!${NC}"
            echo "${YELLOW}Админ-панель не может работать без AntiZapret. Установка прервана.${NC}"
            exit 1
        fi
    else
        echo "${GREEN}[✓] Готово${NC}"
    fi
    
    # Установка прав выполнения
    echo "${YELLOW}Установка прав выполнения...${NC}" && \
    chmod +x "$INSTALL_DIR/client.sh" "$ANTIZAPRET_INSTALL_DIR/doall.sh" 2>/dev/null || true
    echo "${GREEN}[✓] Готово${NC}"

    # Обновление пакетов
    echo "${YELLOW}Обновление списка пакетов...${NC}"
    apt-get update --quiet --quiet > /dev/null
    echo "${GREEN}[✓] Готово${NC}"
    check_error "Не удалось обновить пакеты"
    
    # Проверка и установка зависимостей
    check_dependencies

    # Создание виртуального окружения
    echo "${YELLOW}Создание виртуального окружения...${NC}"
    python3 -m venv "$VENV_PATH"
    echo "${GREEN}[✓] Готово${NC}"
    check_error "Не удалось создать виртуальное окружение"

    # Установка Python-зависимостей
    echo "${YELLOW}Установка Python-зависимостей...${NC}"
    "$VENV_PATH/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
    echo "${GREEN}[✓] Готово${NC}"
    check_error "Не удалось установить Python-зависимости"

    # Выбор способа установки
    choose_installation_type || exit 1

    # Инициализация базы данных
    init_db

    # Создание systemd сервиса
    echo "${YELLOW}Создание systemd сервиса...${NC}"
    cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOL
[Unit]
Description=AdminAntizapret VPN Management
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_PATH/bin/python $INSTALL_DIR/app.py
Restart=always
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOL

    # Включение и запуск сервиса
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"
    check_error "Не удалось запустить сервис"

    # Проверка установки
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "${GREEN}"
        echo "┌────────────────────────────────────────────┐"
        echo "│   Установка успешно завершена!             │"
        echo "├────────────────────────────────────────────┤"
        
        if grep -q "USE_HTTPS=true" "$INSTALL_DIR/.env"; then
            if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
                echo "│ Адрес: https://$DOMAIN:$APP_PORT"
            elif [ -f "$INSTALL_DIR/.env" ] && grep -q "DOMAIN=" "$INSTALL_DIR/.env"; then
                DOMAIN=$(grep "DOMAIN=" "$INSTALL_DIR/.env" | cut -d'=' -f2)
                echo "│ Адрес: https://$DOMAIN:$APP_PORT"
            else
                echo "│ Адрес: https://$(hostname -I | awk '{print $1}'):$APP_PORT"
            fi
        else
            echo "│ Адрес: http://$(hostname -I | awk '{print $1}'):$APP_PORT"
        fi
        
        echo "│"
        echo "│ Для входа используйте учетные данные,"
        echo "│ созданные при инициализации базы данных"
        echo "└────────────────────────────────────────────┘"
        echo "${NC}"
        copy_to_adminpanel
    else
        echo "${RED}Ошибка при запуске сервиса!${NC}"
        journalctl -u "$SERVICE_NAME" -n 10 --no-pager
        exit 1
    fi

    press_any_key
}

# Главная функция
main() {
    check_root
    init_logging
    
    case "$1" in
        "--install")
            install
            ;;
        "--update")
            auto_update
            ;;
        "--backup")
            create_backup
            ;;
        "--restore")
            if [ -z "$2" ]; then
                echo "${RED}Укажите файл для восстановления!${NC}"
                exit 1
            fi
            restore_backup "$2"
            ;;
        *)
            if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        printf "%s\n" "${YELLOW}AdminAntizapret не установлен.${NC}"
        while true; do
            printf "Хотите установить? (y/n) "
            read -r answer
            answer=$(echo "$answer" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
            case $answer in
                [Yy]*)
                    install
                    main_menu
                    break
                    ;;
                [Nn]*)
                    exit 0
                    ;;
                *)
                    printf "%s\n" "${RED}Пожалуйста, введите только 'y' или 'n'${NC}"
                    ;;
            esac
        done
    else
        main_menu
            fi
            ;;
    esac
}

# Запуск скрипта
main "$@"