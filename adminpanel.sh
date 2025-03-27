#!/bin/bash

# Полный менеджер AdminAntizapret без UFW

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

# Функция проверки занятости порта (универсальная)
check_port() {
    local port=$1
    # Проверка через ss (предпочтительный метод)
    if command -v ss >/dev/null 2>&1; then
        if ss -tuln | grep -q ":$port "; then
            return 0
        fi
    # Проверка через netstat (альтернатива)
    elif command -v netstat >/dev/null 2>&1; then
        if netstat -tuln | grep -q ":$port "; then
            return 0
        fi
    # Проверка через lsof (если установлен)
    elif command -v lsof >/dev/null 2>&1; then
        if lsof -i :$port >/dev/null; then
            return 0
        fi
    # Проверка через /proc (универсальный, но менее надежный)
    elif grep -q ":$port " /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
        return 0
    else
        echo -e "${YELLOW}Не удалось проверить порт (установите ss, netstat или lsof для точной проверки)${NC}"
        return 1
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
  
  # Проверка занятости порта
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
  apt-get install -y python3 python3-pip python3-venv git
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
  "$VENV_PATH/bin/pip" install flask
  check_error "Не удалось установить Python-зависимости"

  # Настройка конфигурации
  echo -e "${YELLOW}Настройка конфигурации...${NC}"
  sed -i "s/port=5050/port=$APP_PORT/" "$INSTALL_DIR/app.py"
  sed -i "s/'admin': 'password'/'$ADMIN_USER': '$ADMIN_PASS'/" "$INSTALL_DIR/app.py"

  # Создание systemd сервиса
  echo -e "${YELLOW}Создание systemd сервиса...${NC}"
  cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOL
[Unit]
Description=AdminAntizapret VPN Management
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
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
  echo -e "${YELLOW}Проверка установки...${NC}"
  sleep 3
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo -e "${GREEN}"
    echo "┌────────────────────────────────────────────┐"
    echo "│   Установка успешно завершена!             │"
    echo "├────────────────────────────────────────────┤"
    echo "│ Адрес: http://$(hostname -I | awk '{print $1}'):$APP_PORT"
    echo "│ Логин: $ADMIN_USER"
    echo "│ Пароль: $ADMIN_PASS"
    echo "└────────────────────────────────────────────┘"
    echo -e "${NC}"
    echo -e "${YELLOW}Сохраните эти данные в надежном месте!${NC}"
  else
    echo -e "${RED}Ошибка при запуске сервиса!${NC}"
    journalctl -u "$SERVICE_NAME" -n 10 --no-pager
    exit 1
  fi

  press_any_key
}

# Перезапуск сервиса
restart_service() {
  echo -e "${YELLOW}Перезапуск сервиса...${NC}"
  systemctl restart $SERVICE_NAME
  check_status
}

# Проверка статуса
check_status() {
  echo -e "${YELLOW}Статус сервиса:${NC}"
  systemctl status $SERVICE_NAME --no-pager -l
  press_any_key
}

# Просмотр логов
show_logs() {
  echo -e "${YELLOW}Последние логи (Ctrl+C для выхода):${NC}"
  journalctl -u $SERVICE_NAME -n 50 -f
}

# Проверка обновлений
check_updates() {
  echo -e "${YELLOW}Проверка обновлений...${NC}"
  cd $INSTALL_DIR || exit 1
  git fetch
  LOCAL_HASH=$(git rev-parse HEAD)
  REMOTE_HASH=$(git rev-parse origin/main)

  if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo -e "${GREEN}Доступны обновления!${NC}"
    echo -e "Локальная версия: ${LOCAL_HASH:0:7}"
    echo -e "Удалённая версия: ${REMOTE_HASH:0:7}"
    read -p "Установить обновления? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      git pull origin main
      $VENV_PATH/bin/pip install -r requirements.txt 2>/dev/null || \
        echo -e "${YELLOW}Файл requirements.txt не найден, пропускаем...${NC}"
      systemctl restart $SERVICE_NAME
      echo -e "${GREEN}Обновление завершено!${NC}"
    fi
  else
    echo -e "${GREEN}У вас актуальная версия.${NC}"
  fi
  press_any_key
}

# Тестирование работы
test_installation() {
  echo -e "${YELLOW}Тестирование работы сервиса...${NC}"
  
  if ! check_port $APP_PORT; then
    echo -e "${RED}Сервис не слушает порт $APP_PORT!${NC}"
  else
    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$APP_PORT/login)
    if [ "$response" -eq 200 ]; then
      echo -e "${GREEN}Тест пройден успешно! Код ответа: $response${NC}"
    else
      echo -e "${RED}Ошибка тестирования! Код ответа: $response${NC}"
    fi
  fi
  press_any_key
}

# Создание резервной копии
create_backup() {
  local backup_dir="/var/backups/antizapret"
  local timestamp=$(date +%Y%m%d_%H%M%S)
  local backup_file="$backup_dir/backup_$timestamp.tar.gz"
  
  echo -e "${YELLOW}Создание резервной копии...${NC}"
  mkdir -p "$backup_dir"
  
  tar -czf "$backup_file" \
    "$INSTALL_DIR" \
    /etc/systemd/system/$SERVICE_NAME.service \
    /root/antizapret/client 2>/dev/null
  
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}Резервная копия создана: $backup_file${NC}"
    du -h "$backup_file"
  else
    echo -e "${RED}Ошибка при создании резервной копии!${NC}"
  fi
  press_any_key
}

# Удаление сервиса
uninstall() {
  echo -e "${YELLOW}Подготовка к удалению AdminAntizapret...${NC}"
  echo -e "${RED}ВНИМАНИЕ! Это действие необратимо!${NC}"
  
  read -p "Вы уверены, что хотите удалить AdminAntizapret? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Удаление отменено.${NC}"
    press_any_key
    return
  fi
  
  # Создать резервную копию перед удалением
  create_backup
  
  # Остановка и удаление сервиса
  echo -e "${YELLOW}Остановка сервиса...${NC}"
  systemctl stop $SERVICE_NAME
  systemctl disable $SERVICE_NAME
  rm -f "/etc/systemd/system/$SERVICE_NAME.service"
  systemctl daemon-reload
  
  # Удаление файлов
  echo -e "${YELLOW}Удаление файлов...${NC}"
  rm -rf "$INSTALL_DIR"
  
  echo -e "${GREEN}Удаление завершено успешно!${NC}"
  echo -e "Резервная копия сохранена в /var/backups/antizapret"
  press_any_key
  exit 0
}

# Главное меню
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
    echo "│ 7. Удалить AdminAntizapret                 │"
    echo "│ 0. Выход                                   │"
    echo "└────────────────────────────────────────────┘"
    echo -e "${NC}"
    
    read -p "Выберите действие [0-7]: " choice
    case $choice in
      1) restart_service;;
      2) check_status;;
      3) show_logs;;
      4) check_updates;;
      5) test_installation;;
      6) create_backup;;
      7) uninstall;;
      0) exit 0;;
      *) echo -e "${RED}Неверный выбор!${NC}"; sleep 1;;
    esac
  done
}

# Главная функция
main() {
  check_root
  
  # Если сервис не установлен - предложить установку
  if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    echo -e "${YELLOW}AdminAntizapret не установлен.${NC}"
    read -p "Хотите установить? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      install
      # После установки переходим в меню управления
      main_menu
    else
      exit 0
    fi
  else
    # Если установлен - сразу в меню управления
    main_menu
  fi
}

# Запуск скрипта
main "$@"