#!/bin/bash

# Полный менеджер AdminAntizapret с поддержкой SQLite БД

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Основные параметры
INSTALL_DIR="/opt/AdminAntizapret"
VENV_PATH="$INSTALL_DIR/venv"
SERVICE_NAME="admin-antizapret"
DEFAULT_PORT="5050"
REPO_URL="https://github.com/Kirito0098/AdminAntizapret.git"
APP_PORT="$DEFAULT_PORT"
DB_PATH="$INSTALL_DIR/instance/users.db"

# Функция проверки занятости порта
check_port() {
    local port=$1
    if command -v ss >/dev/null; then
        ss -tuln | grep -q ":$port " && return 0
    elif command -v netstat >/dev/null; then
        netstat -tuln | grep -q ":$port " && return 0
    fi
    return 1
}

# Функция проверки ошибок
check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка при выполнении: $1${NC}" >&2
        exit 1
    fi
}

# Проверка прав root
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo -e "${RED}Этот скрипт должен быть запущен с правами root!${NC}" >&2
        exit 1
    fi
}

# Ожидание нажатия клавиши
press_any_key() {
    echo -e "\n${YELLOW}Нажмите любую клавишу чтобы продолжить...${NC}"
    read -n 1 -s -r
}

# Инициализация базы данных
init_db() {
    local admin_user="$1"
    local admin_pass="$2"
    
    echo -e "${YELLOW}Инициализация базы данных...${NC}"
    
    # Создаем директорию для БД
    mkdir -p "$INSTALL_DIR/instance"
    
    # Запускаем скрипт инициализации
    sudo -u nobody "$VENV_PATH/bin/python" <<EOF
from werkzeug.security import generate_password_hash
from app import app, db, User

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username="$admin_user").first():
        admin = User(username="$admin_user")
        admin.password_hash = generate_password_hash("$admin_pass")
        db.session.add(admin)
        db.session.commit()
        print("Администратор создан")
EOF
    
    check_error "Не удалось инициализировать базу данных"
    
    # Устанавливаем права на БД
    chown -R nobody:nogroup "$INSTALL_DIR/instance"
    chmod 600 "$DB_PATH"
}

# Установка AdminAntizapret
install() {
    clear
    echo -e "${GREEN}"
    echo "┌────────────────────────────────────────────┐"
    echo "│          Установка AdminAntizapret         │"
    echo "└────────────────────────────────────────────┘"
    echo -e "${NC}"

    # Запрос параметров
    read -p "Введите порт для сервиса [$DEFAULT_PORT]: " APP_PORT
    APP_PORT=${APP_PORT:-$DEFAULT_PORT}
    
    while check_port $APP_PORT; do
        echo -e "${RED}Порт $APP_PORT уже занят!${NC}"
        read -p "Введите другой порт: " APP_PORT
    done

    read -p "Введите имя администратора [admin]: " ADMIN_USER
    ADMIN_USER=${ADMIN_USER:-admin}
    
    while true; do
        read -s -p "Введите пароль администратора: " ADMIN_PASS
        echo
        if [ -z "$ADMIN_PASS" ]; then
            echo -e "${RED}Пароль не может быть пустым!${NC}"
        elif [ ${#ADMIN_PASS} -lt 8 ]; then
            echo -e "${RED}Пароль должен содержать минимум 8 символов!${NC}"
        else
            break
        fi
    done

    # Обновление пакетов
    echo -e "${YELLOW}Обновление списка пакетов...${NC}"
    apt-get update
    check_error "Не удалось обновить пакеты"

    # Установка зависимостей
    echo -e "${YELLOW}Установка системных зависимостей...${NC}"
    apt-get install -y python3 python3-pip python3-venv git sqlite3
    check_error "Не удалось установить зависимости"

    # Клонирование репозитория
    echo -e "${YELLOW}Клонирование репозитория...${NC}"
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}Директория уже существует, обновляем...${NC}"
        cd "$INSTALL_DIR" && git pull
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    check_error "Не удалось клонировать репозиторий"

    # Создание виртуального окружения
    echo -e "${YELLOW}Создание виртуального окружения...${NC}"
    python3 -m venv "$VENV_PATH"
    check_error "Не удалось создать виртуальное окружение"

    # Установка Python-зависимостей
    echo -e "${YELLOW}Установка Python-зависимостей...${NC}"
    "$VENV_PATH/bin/pip" install flask flask-sqlalchemy werkzeug
    check_error "Не удалось установить Python-зависимости"

    # Инициализация базы данных
    init_db "$ADMIN_USER" "$ADMIN_PASS"

    # Создание systemd сервиса
    echo -e "${YELLOW}Создание systemd сервиса...${NC}"
    cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOL
[Unit]
Description=AdminAntizapret VPN Management
After=network.target

[Service]
User=nobody
Group=nogroup
WorkingDirectory=$INSTALL_DIR
Environment="FLASK_APP=app.py"
Environment="FLASK_ENV=production"
ExecStart=$VENV_PATH/bin/python -m flask run --host=0.0.0.0 --port=$APP_PORT
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
    echo -e "${YELLOW}Проверка установки...${NC}"
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}"
        echo "┌────────────────────────────────────────────┐"
        echo "│   Установка успешно завершена!             │"
        echo "├────────────────────────────────────────────┤"
        echo "│ Адрес: http://$(hostname -I | awk '{print $1}'):$APP_PORT"
        echo "│ Логин: $ADMIN_USER"
        echo "└────────────────────────────────────────────┘"
        echo -e "${NC}"
        echo -e "${YELLOW}Пароль был установлен при установке.${NC}"
    else
        echo -e "${RED}Ошибка при запуске сервиса!${NC}"
        journalctl -u "$SERVICE_NAME" -n 10 --no-pager
        exit 1
    fi

    press_any_key
}

# Добавление нового пользователя
add_user() {
    echo -e "${YELLOW}Добавление нового пользователя${NC}"
    
    read -p "Введите имя пользователя: " username
    read -s -p "Введите пароль: " password
    echo
    
    sudo -u nobody "$VENV_PATH/bin/python" <<EOF
from werkzeug.security import generate_password_hash
from app import app, db, User

with app.app_context():
    if User.query.filter_by(username="$username").first():
        print("Ошибка: Пользователь уже существует!")
        exit(1)
    user = User(username="$username")
    user.password_hash = generate_password_hash("$password")
    db.session.add(user)
    db.session.commit()
    print("Пользователь успешно создан")
EOF
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Пользователь $username успешно добавлен!${NC}"
    else
        echo -e "${RED}Ошибка при добавлении пользователя!${NC}"
    fi
    press_any_key
}

# Остальные функции (restart_service, check_status, show_logs, check_updates, test_installation, create_backup, uninstall)
# остаются без изменений, как в вашем исходном скрипте

# Главное меню с добавленным пунктом управления пользователями
main_menu() {
    while true; do
        clear
        echo -e "${GREEN}"
        echo "┌────────────────────────────────────────────┐"
        echo "│          Меню управления AdminAntizapret   │"
        echo "├────────────────────────────────────────────┤"
        echo "│ 1. Перезапустить сервис                    │"
        echo "│ 2. Проверить статус сервиса                │"
        echo "│ 3. Просмотреть логи                        │"
        echo "│ 4. Проверить обновления                    │"
        echo "│ 5. Протестировать работу                   │"
        echo "│ 6. Создать резервную копию                 │"
        echo "│ 7. Управление пользователями               │"
        echo "│ 8. Удалить AdminAntizapret                 │"
        echo "│ 0. Выход                                   │"
        echo "└────────────────────────────────────────────┘"
        echo -e "${NC}"
        
        read -p "Выберите действие [0-8]: " choice
        case $choice in
            1) restart_service;;
            2) check_status;;
            3) show_logs;;
            4) check_updates;;
            5) test_installation;;
            6) create_backup;;
            7) add_user;;
            8) uninstall;;
            0) exit 0;;
            *) echo -e "${RED}Неверный выбор!${NC}"; sleep 1;;
        esac
    done
}

# Главная функция
main() {
    check_root
    
    if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        echo -e "${YELLOW}AdminAntizapret не установлен.${NC}"
        read -p "Хотите установить? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install
            main_menu
        else
            exit 0
        fi
    else
        main_menu
    fi
}

# Запуск скрипта
main "$@"