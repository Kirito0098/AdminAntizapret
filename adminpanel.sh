#!/bin/sh

# Полный менеджер AdminAntizapret

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
REPO_URL="https://github.com/Kirito0098/AdminAntizapret.git"
APP_PORT="$DEFAULT_PORT"
DB_FILE="$INSTALL_DIR/users.db"

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

# Функция проверки ошибок
check_error() {
  if [ $? -ne 0 ]; then
    printf "%s\n" "${RED}Ошибка при выполнении: $1${NC}" >&2
    exit 1
  fi
}

# Проверка прав root
check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    printf "%s\n" "${RED}Этот скрипт должен быть запущен с правами root!${NC}" >&2
    exit 1
  fi
}

# Ожидание нажатия клавиши
press_any_key() {
  printf "\n%s\n" "${YELLOW}Нажмите любую клавишу чтобы продолжить...${NC}"
  read -r _
}

# Инициализация базы данных
init_db() {
  echo "${YELLOW}Инициализация базы данных...${NC}"
  "$VENV_PATH/bin/python" "$INSTALL_DIR/init_db.py"
  check_error "Не удалось инициализировать базу данных"
}

# Установка AdminAntizapret
install() {
  clear
  printf "%s\n" "${GREEN}"
  printf "┌────────────────────────────────────────────┐\n"
  printf "│          Установка AdminAntizapret         │\n"
  printf "└────────────────────────────────────────────┘\n"
  printf "%s\n" "${NC}"

  # Запрос параметров
  read -p "Введите порт для сервиса [$DEFAULT_PORT]: " APP_PORT
  APP_PORT=${APP_PORT:-$DEFAULT_PORT}
  
  # Проверка занятости порта
  while check_port $APP_PORT; do
    echo "${RED}Порт $APP_PORT уже занят!${NC}"
    read -p "Введите другой порт: " APP_PORT
  done

  # Обновление пакетов
  echo "${YELLOW}Обновление списка пакетов...${NC}"
  apt-get update
  check_error "Не удалось обновить пакеты"

  # Установка зависимостей
  echo "${YELLOW}Установка системных зависимостей...${NC}"
  apt-get install -y python3 python3-pip python3-venv git
  check_error "Не удалось установить зависимости"

  # Клонирование репозитория
  echo "${YELLOW}Клонирование репозитория...${NC}"
  if [ -d "$INSTALL_DIR" ]; then
    echo "${YELLOW}Директория уже существует, обновляем...${NC}"
    cd "$INSTALL_DIR" && git pull
  else
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
  check_error "Не удалось клонировать репозиторий"

  # Создание виртуального окружения
  echo "${YELLOW}Создание виртуального окружения...${NC}"
  python3 -m venv "$VENV_PATH"
  check_error "Не удалось создать виртуальное окружение"

  # Установка Python-зависимостей
  echo "${YELLOW}Установка Python-зависимостей...${NC}"
  "$VENV_PATH/bin/pip" install flask flask-sqlalchemy werkzeug
  check_error "Не удалось установить Python-зависимости"

  # Настройка конфигурации
  echo "${YELLOW}Настройка конфигурации...${NC}"
  sed -i "s/port=5050/port=$APP_PORT/" "$INSTALL_DIR/app.py"

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
  echo "${YELLOW}Проверка установки...${NC}"
  sleep 3
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "${GREEN}"
    echo "┌────────────────────────────────────────────┐"
    echo "│   Установка успешно завершена!             │"
    echo "├────────────────────────────────────────────┤"
    echo "│ Адрес: http://$(hostname -I | awk '{print $1}'):$APP_PORT"
    echo "│"
    echo "│ Для входа используйте учетные данные,"
    echo "│ созданные при инициализации базы данных"
    echo "└────────────────────────────────────────────┘"
    echo "${NC}"
  else
    echo "${RED}Ошибка при запуске сервиса!${NC}"
    journalctl -u "$SERVICE_NAME" -n 10 --no-pager
    exit 1
  fi

  press_any_key
}

# Перезапуск сервиса
restart_service() {
  echo "${YELLOW}Перезапуск сервиса...${NC}"
  systemctl restart $SERVICE_NAME
  check_status
}

# Проверка статуса
check_status() {
  echo "${YELLOW}Статус сервиса:${NC}"
  systemctl status $SERVICE_NAME --no-pager -l
  press_any_key
}

# Просмотр логов
show_logs() {
  echo "${YELLOW}Последние логи (Ctrl+C для выхода):${NC}"
  journalctl -u $SERVICE_NAME -n 50 -f
}

# Проверка обновлений
check_updates() {
  echo "${YELLOW}Проверка обновлений...${NC}"
  cd $INSTALL_DIR || exit 1
  git fetch
  LOCAL_HASH=$(git rev-parse HEAD)
  REMOTE_HASH=$(git rev-parse origin/main)

  if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "${GREEN}Доступны обновления!${NC}"
    echo "Локальная версия: ${LOCAL_HASH:0:7}"
    echo "Удалённая версия: ${REMOTE_HASH:0:7}"
    echo -n "Установить обновления? (y/n) "
    read -r
    if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
      git pull origin main
      $VENV_PATH/bin/pip install -r requirements.txt 2>/dev/null || \
        echo "${YELLOW}Файл requirements.txt не найден, пропускаем...${NC}"
      systemctl restart $SERVICE_NAME
      echo "${GREEN}Обновление завершено!${NC}"
    fi
  else
    echo "${GREEN}У вас актуальная версия.${NC}"
  fi
  press_any_key
}

# Тестирование работы
test_installation() {
  echo "${YELLOW}Тестирование работы сервиса...${NC}"
  
  if ! check_port $APP_PORT; then
    echo "${RED}Сервис не слушает порт $APP_PORT!${NC}"
  else
    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$APP_PORT/login)
    if [ "$response" -eq 200 ]; then
      echo "${GREEN}Тест пройден успешно! Код ответа: $response${NC}"
    else
      echo "${RED}Ошибка тестирования! Код ответа: $response${NC}"
    fi
  fi
  press_any_key
}

# Создание резервной копии
create_backup() {
  local backup_dir="/var/backups/antizapret"
  local timestamp=$(date +%Y%m%d_%H%M%S)
  local backup_file="$backup_dir/backup_$timestamp.tar.gz"
  
  echo "${YELLOW}Создание резервной копии...${NC}"
  mkdir -p "$backup_dir"
  
  tar -czf "$backup_file" \
    "$INSTALL_DIR" \
    /etc/systemd/system/$SERVICE_NAME.service \
    /root/antizapret/client 2>/dev/null
  
  if [ $? -eq 0 ]; then
    echo "${GREEN}Резервная копия создана: $backup_file${NC}"
    du -h "$backup_file"
  else
    echo "${RED}Ошибка при создании резервной копии!${NC}"
  fi
  press_any_key
}

# Восстановление из резервной копии
restore_backup() {
  local backup_dir="/var/backups/antizapret"
  
  echo "${YELLOW}Доступные резервные копии:${NC}"
  ls -lh "$backup_dir"/*.tar.gz 2>/dev/null || {
    echo "${RED}Резервные копии не найдены!${NC}"
    press_any_key
    return
  }
  
  read -p "Введите имя файла для восстановления: " backup_file
  
  if [ ! -f "$backup_dir/$backup_file" ]; then
    echo "${RED}Файл не найден!${NC}"
    press_any_key
    return
  fi
  
  echo "${YELLOW}Восстановление из $backup_file...${NC}"
  
  # Остановка сервиса перед восстановлением
  systemctl stop $SERVICE_NAME
  
  # Восстановление файлов
  tar -xzf "$backup_dir/$backup_file" -C /
  
  # Перезапуск сервиса
  systemctl start $SERVICE_NAME
  
  echo "${GREEN}Восстановление завершено!${NC}"
  press_any_key
}

# Удаление сервиса
uninstall() {
  printf "%s\n" "${YELLOW}Подготовка к удалению AdminAntizapret...${NC}"
  printf "%s\n" "${RED}ВНИМАНИЕ! Это действие необратимо!${NC}"
  
  printf "Вы уверены, что хотите удалить AdminAntizapret? (y/n) "
  read answer
  
  case "$answer" in
    [Yy]*)
      # Создать резервную копию перед удалением
      create_backup
      
      # Остановка и удаление сервиса
      printf "%s\n" "${YELLOW}Остановка сервиса...${NC}"
      systemctl stop $SERVICE_NAME
      systemctl disable $SERVICE_NAME
      rm -f "/etc/systemd/system/$SERVICE_NAME.service"
      systemctl daemon-reload
      
      # Удаление файлов
      printf "%s\n" "${YELLOW}Удаление файлов...${NC}"
      rm -rf "$INSTALL_DIR"
      
      printf "%s\n" "${GREEN}Удаление завершено успешно!${NC}"
      printf "Резервная копия сохранена в /var/backups/antizapret\n"
      press_any_key
      exit 0
      ;;
    *)
      printf "%s\n" "${GREEN}Удаление отменено.${NC}"
      press_any_key
      return
      ;;
  esac
}

# Главное меню
main_menu() {
  while true; do
    clear
    printf "%s\n" "${GREEN}"
    printf "┌────────────────────────────────────────────┐\n"
    printf "│          Меню управления AdminAntizapret   │\n"
    printf "├────────────────────────────────────────────┤\n"
    printf "│ 1. Перезапустить сервис                    │\n"
    printf "│ 2. Проверить статус сервиса                │\n"
    printf "│ 3. Просмотреть логи                        │\n"
    printf "│ 4. Проверить обновления                    │\n"
    printf "│ 5. Протестировать работу                   │\n"
    printf "│ 6. Создать резервную копию                 │\n"
    printf "│ 7. Восстановить из резервной копии         │\n"
    printf "│ 8. Удалить AdminAntizapret                 │\n"
    printf "│ 0. Выход                                   │\n"
    printf "└────────────────────────────────────────────┘\n"
    printf "%s\n" "${NC}"
    
    printf "Выберите действие [0-8]: "
    read choice
    case $choice in
      1) restart_service;;
      2) check_status;;
      3) show_logs;;
      4) check_updates;;
      5) test_installation;;
      6) create_backup;;
      7) restore_backup;;
      8) uninstall;;
      0) exit 0;;
      *) printf "%s\n" "${RED}Неверный выбор!${NC}"; sleep 1;;
    esac
  done
}

# Главная функция
main() {
  check_root
  
  if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    printf "%s\n" "${YELLOW}AdminAntizapret не установлен.${NC}"
    printf "Хотите установить? (y/n) "
    read -r answer
    case $answer in
      [Yy]*) install; main_menu;;
      *) exit 0;;
    esac
  else
    main_menu
  fi
}

# Запуск скрипта
main "$@"
