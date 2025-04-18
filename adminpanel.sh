#!/bin/bash

# Полный менеджер AdminAntizapret

export LC_ALL="en_US.UTF-8"
export LANG="en_US.UTF-8"

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
DB_FILE="$INSTALL_DIR/instance/users.db"
ANTIZAPRET_INSTALL_DIR="/root/antizapret"
ANTIZAPRET_INSTALL_SCRIPT="https://raw.githubusercontent.com/GubernievS/AntiZapret-VPN/main/setup.sh"
DOMAIN=""
EMAIL=""
LOG_FILE="/var/log/adminpanel.log"

# Генерируем случайный секретный ключ
SECRET_KEY=$(openssl rand -hex 32)

# Инициализация логгирования
init_logging() {
  touch "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
  log "Запуск скрипта"
}

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

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
    apt-get update --quiet --quiet && apt-get install -y --quiet --quiet python3 python3-pip git wget openssl python3-venv > /dev/null 
    if [ $? -ne 0 ]; then
        echo "Ошибка установки зависимостей!"
        exit 1
    fi
    echo "${GREEN}Зависимости установлены.${NC}"
}

# Функция проверки ошибок
check_error() {
  if [ $? -ne 0 ]; then
    log "Ошибка при выполнении: $1"
    printf "%s\n" "${RED}Ошибка при выполнении: $1${NC}" >&2
    exit 1
  fi
}

# Проверка прав root
check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log "Попытка запуска без прав root"
    printf "%s\n" "${RED}Этот скрипт должен быть запущен с правами root!${NC}" >&2
    exit 1
  fi
}

# Ожидание нажатия клавиши
press_any_key() {
  printf "\n%s\n" "${YELLOW}Нажмите любую клавишу чтобы продолжить...${NC}"
  read -r _
}

# Проверка установки AntiZapret-VPN
check_antizapret_installed() {
  if [ -d "$ANTIZAPRET_INSTALL_DIR" ]; then
    return 0
  else
    return 1
  fi
}

# Установка AntiZapret-VPN
install_antizapret() {
    log "Попытка установки AntiZapret-VPN"
    echo "${YELLOW}Установка AntiZapret-VPN (обязательный компонент)...${NC}"

    # Запуск установочного скрипта с проверкой ошибок
    if ! bash <(wget --no-hsts -qO- "$ANTIZAPRET_INSTALL_SCRIPT"); then
        log "Ошибка: сбой установки AntiZapret-VPN"
        echo "${RED}Не удалось установить AntiZapret-VPN!${NC}"
        echo "${YELLOW}Админ-панель требует AntiZapret-VPN для работы. Установка прервана.${NC}"
        exit 1  # Жёсткое завершение скрипта
    fi

    # Проверка, что установка прошла успешно
    if ! check_antizapret_installed; then
        log "Ошибка: AntiZapret-VPN не обнаружен после установки"
        echo "${RED}AntiZapret-VPN не установлен, хотя скрипт завершился без ошибок!${NC}"
        echo "${YELLOW}Проверьте вручную: $ANTIZAPRET_INSTALL_DIR${NC}"
        exit 1
    fi

    log "AntiZapret-VPN успешно установлен"
    echo "${GREEN}AntiZapret-VPN установлен и готов к работе.${NC}"
}

# Инициализация базы данных
init_db() {
  log "Инициализация базы данных"
  echo "${YELLOW}Инициализация базы данных...${NC}"
  PYTHONIOENCODING=utf-8 "$VENV_PATH/bin/python" "$INSTALL_DIR/init_db.py"
  check_error "Не удалось инициализировать базу данных"
}

# Валидация домена
validate_domain() {
  local domain=$1
  if [[ ! $domain =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    echo "${RED}Неверный формат домена!${NC}"
    return 1
  fi
  return 0
}

# Проверка DNS
check_dns() {
  if ! dig +short $DOMAIN | grep -q '[0-9]'; then
    echo "${YELLOW}DNS запись для $DOMAIN не найдена или неверна!${NC}"
    return 1
  fi
  return 0
}

# Установка Nginx с Let's Encrypt
setup_nginx_letsencrypt() {
    log "Настройка Nginx + Let's Encrypt для домена $DOMAIN"
    echo "${YELLOW}Установка Nginx и Let's Encrypt...${NC}"
    
    # Установка Nginx
    apt-get install -y -qq nginx >/dev/null 2>&1
    check_error "Не удалось установить Nginx"
    
    # Установка Certbot
    apt-get install -y -qq certbot python3-certbot-nginx >/dev/null 2>&1
    check_error "Не удалось установить Certbot"
    
    # Настройка Nginx
    cat > /etc/nginx/sites-available/admin-antizapret <<EOL
server {
    listen 80;
    server_name $DOMAIN;
    
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOL
    
    ln -s /etc/nginx/sites-available/admin-antizapret /etc/nginx/sites-enabled/
    systemctl restart nginx
    
    # Получение сертификата
    certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL
    check_error "Не удалось получить сертификат Let's Encrypt"
    
    # Удаляем старый файл с SSL-параметрами, чтобы избежать дублирования
    rm -f /etc/nginx/conf.d/ssl-params.conf
    
    # Настройка SSL параметров
    cat > /etc/nginx/conf.d/ssl-params.conf <<EOL
ssl_session_timeout 1d;
ssl_session_cache shared:MozSSL:10m;
ssl_session_tickets off;
ssl_stapling on;
ssl_stapling_verify on;
add_header Strict-Transport-Security "max-age=63072000" always;
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
EOL
    
    # Настройка автоматического обновления
    (crontab -l 2>/dev/null; echo "0 60 * * * /usr/bin/certbot renew --quiet") | crontab -
    
    # Проверяем конфигурацию и перезапускаем Nginx
    nginx -t && systemctl restart nginx
    
    log "Nginx с Let's Encrypt успешно настроен"
    echo "${GREEN}Nginx с Let's Encrypt успешно настроен!${NC}"
}

# Установка с самоподписанным сертификатом
setup_selfsigned() {
    log "Настройка самоподписанного сертификата"
    echo "${YELLOW}Настройка самоподписанного сертификата...${NC}"
    
    # Создание сертификата
    mkdir -p /etc/ssl/private
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/private/admin-antizapret.key \
        -out /etc/ssl/certs/admin-antizapret.crt \
        -subj "/CN=$(hostname)" >/dev/null 2>&1
    
    # Настройка конфигурации Flask для HTTPS
    if [ -f "$INSTALL_DIR/.env" ]; then
        echo "${YELLOW}Добавляем значения в .env...${NC}"

        # Проверяем, есть ли уже строки USE_HTTPS, SSL_CERT, SSL_KEY
        grep -qxF "USE_HTTPS=true" "$INSTALL_DIR/.env" || echo "USE_HTTPS=true" >> "$INSTALL_DIR/.env"
        grep -qxF "SSL_CERT=/etc/ssl/certs/admin-antizapret.crt" "$INSTALL_DIR/.env" || echo "SSL_CERT=/etc/ssl/certs/admin-antizapret.crt" >> "$INSTALL_DIR/.env"
        grep -qxF "SSL_KEY=/etc/ssl/private/admin-antizapret.key" "$INSTALL_DIR/.env" || echo "SSL_KEY=/etc/ssl/private/admin-antizapret.key" >> "$INSTALL_DIR/.env"
    else
    # Если файл не существует, создаем его с необходимыми значениями
    echo "${YELLOW}Создаем файл .env...${NC}"
        cat > "$INSTALL_DIR/.env" <<EOL
USE_HTTPS=true
SSL_CERT=/etc/ssl/certs/admin-antizapret.crt
SSL_KEY=/etc/ssl/private/admin-antizapret.key
EOL
    fi
    
    log "Самоподписанный сертификат создан"
    echo "${GREEN}Самоподписанный сертификат успешно создан!${NC}"
}

# Настройка фаервола
configure_firewall() {
    log "Настройка фаервола для порта $APP_PORT"
    if command -v ufw >/dev/null; then
        echo "${YELLOW}Настройка UFW...${NC}"
        ufw allow "$APP_PORT/tcp"
        
        if [ "$ssl_choice" = "1" ]; then
            ufw allow 80/tcp
            ufw allow 443/tcp
        fi
        
        ufw reload
    elif command -v firewall-cmd >/dev/null; then
        echo "${YELLOW}Настройка firewalld...${NC}"
        firewall-cmd --permanent --add-port="$APP_PORT/tcp"
        
        if [ "$ssl_choice" = "1" ]; then
            firewall-cmd --permanent --add-service=http
            firewall-cmd --permanent --add-service=https
        fi
        
        firewall-cmd --reload
    else
        echo "${YELLOW}Фаервол не найден, пропускаем настройку${NC}"
    fi
}

# Валидация конфигурации
validate_config() {
    local errors=0
    
    echo "${YELLOW}Проверка конфигурации...${NC}"
    
    # Проверка файла .env
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        echo "${RED}Ошибка: .env файл не найден${NC}"
        errors=$((errors+1))
    fi
    
    # Проверка секретного ключа
    if ! grep -q "SECRET_KEY=" "$INSTALL_DIR/.env"; then
        echo "${RED}Ошибка: SECRET_KEY не установлен${NC}"
        errors=$((errors+1))
    fi
    
    # Проверка базы данных
    if [ ! -f "$DB_FILE" ]; then
        echo "${RED}Ошибка: База данных не найдена${NC}"
        errors=$((errors+1))
    fi
    
    # Проверка сервиса systemd
    if [ ! -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        echo "${RED}Ошибка: Сервис systemd не найден${NC}"
        errors=$((errors+1))
    fi
    
    if [ $errors -eq 0 ]; then
        echo "${GREEN}Конфигурация в порядке.${NC}"
        return 0
    else
        echo "${RED}Найдено $errors ошибок в конфигурации.${NC}"
        return 1
    fi
}

# Создание резервной копии
create_backup() {
    local backup_dir="/var/backups/antizapret"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$backup_dir/full_backup_$timestamp.tar.gz"
    
    log "Создание резервной копии в $backup_file"
    echo "${YELLOW}Создание полной резервной копии...${NC}"
    mkdir -p "$backup_dir"
    
    tar -czf "$backup_file" \
        "$INSTALL_DIR" \
        /etc/systemd/system/$SERVICE_NAME.service \
        "$DB_FILE" \
        /etc/ssl/certs/admin-antizapret.crt 2>/dev/null \
        /etc/ssl/private/admin-antizapret.key 2>/dev/null \
        /etc/nginx/sites-*/admin-antizapret 2>/dev/null \
        /etc/letsencrypt/live/$DOMAIN 2>/dev/null
    
    # Проверка целостности архива
    if ! tar -tzf "$backup_file" >/dev/null; then
        echo "${RED}Ошибка: резервная копия повреждена!${NC}"
        rm -f "$backup_file"
        return 1
    fi
    
    echo "${GREEN}Резервная копия создана:${NC}"
    ls -lh "$backup_file"
    echo "Для восстановления используйте: $0 --restore $backup_file"
}

# Восстановление из резервной копии
restore_backup() {
    local backup_file=$1
    
    if [ ! -f "$backup_file" ]; then
        echo "${RED}Файл резервной копии не найден!${NC}"
        return 1
    fi
    
    log "Восстановление из резервной копии $backup_file"
    echo "${YELLOW}Восстановление из резервной копии...${NC}"
    
    # Остановка сервисов
    systemctl stop $SERVICE_NAME 2>/dev/null
    systemctl stop nginx 2>/dev/null
    
    # Восстановление файлов
    tar -xzf "$backup_file" -C /
    
    # Перезапуск сервисов
    systemctl daemon-reload
    systemctl start $SERVICE_NAME
    systemctl start nginx 2>/dev/null
    
    log "Восстановление завершено"
    echo "${GREEN}Восстановление завершено успешно!${NC}"
}

# Автоматическое обновление
auto_update() {
    log "Проверка обновлений"
    echo "${YELLOW}Проверка обновлений...${NC}"
    cd "$INSTALL_DIR" || return 1
    
    # Fetch updates
    git fetch origin main
    
    # Check if update needed
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
            
            # Определяем способ установки для правильного удаления
            use_nginx=false
            use_letsencrypt=false
            use_selfsigned=false
            
            # Проверяем, используется ли Nginx
            if [ -f "/etc/nginx/sites-enabled/admin-antizapret" ]; then
                use_nginx=true
                # Проверяем, используется ли Let's Encrypt
                if [ -d "/etc/letsencrypt/live/" ]; then
                    use_letsencrypt=true
                fi
            fi
            
            # Проверяем, используется ли самоподписанный сертификат
            if grep -q "USE_HTTPS=true" "$INSTALL_DIR/.env" 2>/dev/null && \
               [ -f "/etc/ssl/certs/admin-antizapret.crt" ] && \
               [ -f "/etc/ssl/private/admin-antizapret.key" ]; then
                use_selfsigned=true
            fi
            
            # Остановка и удаление сервиса
            printf "%s\n" "${YELLOW}Остановка сервиса...${NC}"
            systemctl stop $SERVICE_NAME
            systemctl disable $SERVICE_NAME
            rm -f "/etc/systemd/system/$SERVICE_NAME.service"
            systemctl daemon-reload
            
            # Удаление конфигурации Nginx, если использовался
            if [ "$use_nginx" = true ]; then
                printf "%s\n" "${YELLOW}Удаление конфигурации Nginx...${NC}"
                rm -f /etc/nginx/sites-enabled/admin-antizapret
                rm -f /etc/nginx/sites-available/admin-antizapret
                systemctl reload nginx
                
                # Удаление Let's Encrypt сертификата, если использовался
                if [ "$use_letsencrypt" = true ]; then
                    printf "%s\n" "${YELLOW}Удаление Let's Encrypt сертификата...${NC}"
                    certbot delete --non-interactive --cert-name $DOMAIN 2>/dev/null || \
                        echo "${YELLOW}Не удалось удалить сертификат Let's Encrypt, возможно он уже удален${NC}"
                    
                    # Удаление задания cron для обновления сертификатов
                    crontab -l | grep -v 'certbot renew' | crontab -
                fi
            fi
            
            # Удаление самоподписанного сертификата, если использовался
            if [ "$use_selfsigned" = true ]; then
                printf "%s\n" "${YELLOW}Удаление самоподписанного сертификата...${NC}"
                rm -f /etc/ssl/certs/admin-antizapret.crt
                rm -f /etc/ssl/private/admin-antizapret.key
            fi
            
            # Удаление файлов приложения
            printf "%s\n" "${YELLOW}Удаление файлов...${NC}"
            rm -rf "$INSTALL_DIR"
            rm -f /root/adminpanel/adminpanel.sh
            
            # Удаление зависимостей, если они больше не нужны
            printf "%s\n" "${YELLOW}Очистка зависимостей...${NC}"
            apt-get autoremove -y --purge python3-venv python3-pip nginx nginx-common >/dev/null 2>&1
        
            # Удаление файлов приложения
            printf "%s\n" "${YELLOW}Удаление логов...${NC}"
            rm -f "$LOG_FILE"

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

# Установка AdminAntizapret
install() {
    clear
    printf "%s\n" "${GREEN}"
    printf "┌────────────────────────────────────────────┐\n"
    printf "│          Установка AdminAntizapret         │\n"
    printf "└────────────────────────────────────────────┘\n"
    printf "%s\n" "${NC}"

    # Клонирование репозитория
    echo "${YELLOW}Клонирование репозитория...${NC}"
    if [ -d "$INSTALL_DIR" ]; then
        echo "${YELLOW}Директория уже существует, обновляем...${NC}"
        cd "$INSTALL_DIR" && git pull > /dev/null 2>&1
    else
        git clone "$REPO_URL" "$INSTALL_DIR" > /dev/null 2>&1
    fi
    check_error "Не удалось клонировать репозиторий"

    # Установка прав выполнения для client.sh и doall.sh
    echo "${YELLOW}Установка прав выполнения...${NC}"
    chmod +x "$INSTALL_DIR/client.sh" "$ANTIZAPRET_INSTALL_DIR/doall.sh" 2>/dev/null || true

    # Обновление пакетов
    echo "${YELLOW}Обновление списка пакетов...${NC}"
    apt-get update --quiet --quiet > /dev/null
    check_error "Не удалось обновить пакеты"
    
    # Проверка и установка зависимостей
    check_dependencies

    # Создание виртуального окружения
    echo "${YELLOW}Создание виртуального окружения...${NC}"
    python3 -m venv "$VENV_PATH"
    check_error "Не удалось создать виртуальное окружение"

    # Установка Python-зависимостей
    echo "${YELLOW}Установка Python-зависимостей...${NC}"
    "$VENV_PATH/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
    check_error "Не удалось установить Python-зависимости"

    # Выбор способа установки
    while true; do
        echo "${YELLOW}Выберите способ установки:${NC}"
        echo "1) Nginx + Let's Encrypt (рекомендуется)"
        echo "2) Самоподписанный сертификат"
        echo "3) Только HTTP (без HTTPS)"
        read -p "Ваш выбор [1-3]: " ssl_choice

        case $ssl_choice in
            1)
                # Проверка конфигурации AntiZapret перед запросом домена
                antizapret_conf="/root/antizapret/setup"
                need_restart=false
                ports_ok=true

                if [ -f "$antizapret_conf" ]; then
                    tcp_ports=$(grep -oP 'OPENVPN_80_443_TCP=\K[yn]' "$antizapret_conf" 2>/dev/null)
                    udp_ports=$(grep -oP 'OPENVPN_80_443_UDP=\K[yn]' "$antizapret_conf" 2>/dev/null)

                    if [[ "$tcp_ports" == "y" || "$udp_ports" == "y" ]]; then
                        echo "${RED}ВНИМАНИЕ: AntiZapret использует порты 80/443${NC}"
                        echo "${YELLOW}Для Nginx + Let's Encrypt эти порты должны быть свободны${NC}"
                        
                        read -p "Освободить порты? (y/n): " choice
                        case "$choice" in
                            [Yy]*)
                                sed -i 's/OPENVPN_80_443_TCP=y/OPENVPN_80_443_TCP=n/' "$antizapret_conf"
                                sed -i 's/OPENVPN_80_443_UDP=y/OPENVPN_80_443_UDP=n/' "$antizapret_conf"
                                need_restart=true
                                ;;
                            *)
                                echo "${RED}Установка невозможна без освобождения портов${NC}"
                                ports_ok=false
                                ;;
                        esac
                    fi
                fi

                if [ "$ports_ok" = false ]; then
                    continue
                fi

                if [ "$need_restart" = true ] && [ -f "/root/antizapret/up.sh" ]; then
                    echo "${YELLOW}Освобождение портов...${NC}"
                    /root/antizapret/up.sh > /dev/null 2>&1
                    sleep 2
                fi

                # Запрос домена и email
                while true; do
                    read -p "Введите доменное имя (например, example.com): " DOMAIN
                    if validate_domain "$DOMAIN"; then
                        break
                    fi
                done
                
                while true; do
                    read -p "Введите email для Let's Encrypt: " EMAIL
                    if [[ "$EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
                        break
                    else
                        echo "${RED}Неверный формат email!${NC}"
                    fi
                done
                
                if ! check_dns; then
                    echo "${YELLOW}Продолжение без корректной DNS записи может привести к ошибкам.${NC}"
                    read -p "Продолжить установку? (y/n): " choice
                    [[ "$choice" =~ ^[Yy]$ ]] || continue
                fi
                break
                ;;
            2)
                # Для самоподписанного сертификата запрашиваем порт
                read -p "Введите порт для сервиса [$DEFAULT_PORT]: " APP_PORT
                APP_PORT=${APP_PORT:-$DEFAULT_PORT}
                
                # Проверка занятости порта
                while check_port $APP_PORT; do
                    echo "${RED}Порт $APP_PORT уже занят!${NC}"
                    read -p "Введите другой порт: " APP_PORT
                done
                
                setup_selfsigned
                break
                ;;
            3)
                # Для HTTP запрашиваем порт
                read -p "Введите порт для сервиса [$DEFAULT_PORT]: " APP_PORT
                APP_PORT=${APP_PORT:-$DEFAULT_PORT}
                
                # Проверка занятости порта
                while check_port $APP_PORT; do
                    echo "${RED}Порт $APP_PORT уже занят!${NC}"
                    read -p "Введите другой порт: " APP_PORT
                done
                
                echo "${YELLOW}Будет использовано HTTP соединение без шифрования${NC}"
                break
                ;;
            *)
                echo "${RED}Неверный выбор!${NC}"
                ;;
        esac
    done

    # Настройка конфигурации
    echo "${YELLOW}Настройка конфигурации...${NC}"
    if [ -f "$INSTALL_DIR/.env" ]; then
        grep -qxF "SECRET_KEY='$SECRET_KEY'" "$INSTALL_DIR/.env" || echo "SECRET_KEY='$SECRET_KEY'" >> "$INSTALL_DIR/.env"
        grep -qxF "APP_PORT=$APP_PORT" "$INSTALL_DIR/.env" || echo "APP_PORT=$APP_PORT" >> "$INSTALL_DIR/.env"
    else
        cat > "$INSTALL_DIR/.env" <<EOL
SECRET_KEY='$SECRET_KEY'
APP_PORT=$APP_PORT
EOL
        chmod 600 "$INSTALL_DIR/.env"
    fi

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

    # Настройка выбранного способа HTTPS
    case $ssl_choice in
        1)
            setup_nginx_letsencrypt
            ;;
        2)
            systemctl restart "$SERVICE_NAME"
            ;;
        3)
            echo "${YELLOW}HTTP режим активирован${NC}"
            ;;
    esac

    # Проверка установки
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "${GREEN}"
        echo "┌────────────────────────────────────────────┐"
        echo "│   Установка успешно завершена!             │"
        echo "├────────────────────────────────────────────┤"
        case $ssl_choice in
            1)
                echo "│ Адрес: https://$DOMAIN"
                ;;
            2)
                echo "│ Адрес: https://$(hostname -I | awk '{print $1}'):$APP_PORT"
                ;;
            3)
                echo "│ Адрес: http://$(hostname -I | awk '{print $1}'):$APP_PORT"
                ;;
        esac
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

# Добавление администратора
add_admin() {
    echo "${YELLOW}Добавление нового администратора...${NC}"
    
    read -p "Введите логин администратора: " username
    while true; do
        read -s -p "Введите пароль: " password
        echo
        read -s -p "Повторите пароль: " password_confirm
        echo
        if [ "$password" != "$password_confirm" ]; then
            echo "${RED}Пароли не совпадают! Попробуйте снова.${NC}"
        elif [ ${#password} -lt 8 ]; then
            echo "${RED}Пароль должен содержать минимум 8 символов!${NC}"
        else
            break
        fi
    done

    "$VENV_PATH/bin/python" "$INSTALL_DIR/init_db.py" --add-user "$username" "$password"
    check_error "Не удалось добавить администратора"
    press_any_key
}

# Удаление администратора
delete_admin() {
    echo "${YELLOW}Удаление администратора...${NC}"
    
    echo "${YELLOW}Список администраторов:${NC}"
    "$VENV_PATH/bin/python" "$INSTALL_DIR/init_db.py" --list-users
    if [ $? -ne 0 ]; then
        echo "${RED}Ошибка при получении списка администраторов!${NC}"
        press_any_key
        return
    fi

    read -p "Введите логин администратора для удаления: " username
    if [ -z "$username" ]; then
        echo "${RED}Логин не может быть пустым!${NC}"
        press_any_key
        return
    fi

    "$VENV_PATH/bin/python" "$INSTALL_DIR/init_db.py" --delete-user "$username"
    if [ $? -eq 0 ]; then
        echo "${GREEN}Администратор '$username' успешно удалён!${NC}"
    else
        echo "${RED}Ошибка при удалении администратора '$username'!${NC}"
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
    auto_update
    press_any_key
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
        printf "│ 11. Изменить порт сервиса (Для http)       │\n"
        printf "│ 12. Мониторинг системы                     │\n"
        printf "│ 13. Проверить конфигурацию                 │\n"
        printf "│ 0. Выход                                   │\n"
        printf "└────────────────────────────────────────────┘\n"
        printf "%s\n" "${NC}"
        
        printf "Выберите действие [0-13]: "
        read choice
        case $choice in
            1) add_admin;;
            2) delete_admin;;
            3) restart_service;;
            4) check_status;;
            5) show_logs;;
            6) check_updates;;
            7) create_backup;;
            8) 
                read -p "Введите путь к файлу резервной копии: " backup_file
                restore_backup "$backup_file"
                press_any_key
                ;;
            9) uninstall;;
            10) check_and_set_permissions;;
            11) change_port;;
            12) show_monitor;;
            13) validate_config; press_any_key;;
            0) exit 0;;
            *) printf "%s\n" "${RED}Неверный выбор!${NC}"; sleep 1;;
        esac
    done
}

# Главная функция
main() {
    check_root
    init_logging
    
    # Обработка аргументов командной строки
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
                printf "Хотите установить? (y/n) "
                read -r answer
                case $answer in
                    [Yy]*) install; main_menu;;
                    *) exit 0;;
                esac
            else
                main_menu
            fi
            ;;
    esac
}

# Запуск скрипта
main "$@"
