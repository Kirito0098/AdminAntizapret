#!/bin/bash

# Функция проверки занятости порта
validate_port() {
    while check_port $APP_PORT; do
        echo "${RED}Порт $APP_PORT уже занят!${NC}"
        read -p "Введите другой порт: " APP_PORT
    done
}

choose_installation_type() {
    while true; do
        echo "${YELLOW}Выберите способ установки:${NC}"
        echo "1) HTTPS (Защищенное соединение)"
        echo "2) HTTP (Не защищенное соединение)"
        read -p "Ваш выбор [1-2]: " ssl_main_choice

        case $ssl_main_choice in
        1)
            if ! check_openvpn_tcp_setting; then
                continue
            fi
            echo "${YELLOW}Выберите тип HTTPS соединения:${NC}"
            echo "  1) Использовать собственный домен и сертификаты Let's Encrypt"
            echo "  2) Использовать собственный домен и собственные сертификаты"
            echo "  3) Самоподписанный сертификат"
            read -p "Ваш выбор [1-3]: " ssl_sub_choice

            case $ssl_sub_choice in
            1|2|3)
                # Для HTTPS вариантов устанавливаем дефолтный порт 443
                read -p "Введите порт для сервиса [443]: " APP_PORT
                APP_PORT=${APP_PORT:-443}
                validate_port

                # Базовые настройки для HTTPS
                cat >"$INSTALL_DIR/.env" <<EOL
SECRET_KEY='$SECRET_KEY'
APP_PORT=$APP_PORT
EOL

                case $ssl_sub_choice in
                1) setup_letsencrypt ;;
                2) setup_custom_certs ;;
                3) setup_selfsigned ;;
                esac
                return 0
                ;;
            *)
                echo "${RED}Неверный выбор!${NC}"
                continue
                ;;
            esac
            ;;
        2)
            read -p "Введите порт для сервиса [$DEFAULT_PORT]: " APP_PORT
            APP_PORT=${APP_PORT:-$DEFAULT_PORT}
            validate_port
            configure_http
            return 0
            ;;
        *)
            echo "${RED}Неверный выбор!${NC}"
            ;;
        esac
    done
}

check_openvpn_tcp_setting() {
    if [ -f "/root/antizapret/setup" ]; then
        OPENVPN_SETTING=$(grep '^OPENVPN_80_443_TCP=' /root/antizapret/setup | cut -d'=' -f2)
        if [ "$OPENVPN_SETTING" = "y" ]; then
            echo "${RED}Обнаружено что порты 80 и 443 используются в AntiZapret-VPN как резрвные для TCP OpenVPN${NC}"
            echo "${YELLOW}Это приведёт к конфликту с веб-сервером:${NC}"
            echo "${YELLOW} • Для работы HTTPS (SSL) по умолчанию используется порт 443 — он позволяет открывать сайт просто по домену${NC}"
            echo "${YELLOW}   (например, https://example.com вместо https://example.com:443).${NC}"
            echo "${YELLOW} • Порт 80 критически важен для Let's Encrypt:${NC}"
            echo "${YELLOW}   - Используется для первичного получения сертификатов${NC}"
            echo "${YELLOW}   - Требуется для автоматического обновления (каждые 60 дней)${NC}"
            echo "${YELLOW}   - Без него невозможна автоматическая работа SSL${NC}"
            read -p "Отключить резервирование портов в OpenVPN и перезапустить сервис? (y/n): " change_choice
            if [[ "$change_choice" =~ ^[Yy]$ ]]; then
                sed -i 's/^OPENVPN_80_443_TCP=y/OPENVPN_80_443_TCP=n/' /root/antizapret/setup
                systemctl restart antizapret.service
                echo "${GREEN}Резервирование портов в OpenVPN отключено и сервис перезапущен!${NC}"
                return 0
            else
                echo "${RED}ВНИМАНИЕ: HTTPS не будет работать корректно с резервированием портов в OpenVPN${NC}"
                read -p "Вы уверены, что хотите продолжить без изменений? (y/n): " continue_choice
                if [[ "$continue_choice" =~ ^[Yy]$ ]]; then
                    return 0
                else
                    return 1
                fi
            fi
        else
            echo "${GREEN}Проверка портов: резервирование 80/443 портов в OpenVPN отключено${NC}"
            echo "${GREEN}Конфигурация не требует изменений, можно продолжать настройку веб-сервера${NC}"
            return 0
        fi
    fi
    return 0
}

setup_letsencrypt() {
    log "Настройка Let's Encrypt"
    echo "${YELLOW}Настройка Let's Encrypt...${NC}"

    while true; do
        read -p "Введите доменное имя (например, example.com): " DOMAIN
        if [[ $DOMAIN =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
            break
        else
            echo "${RED}Неверный формат домена!${NC}"
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

    if ! dig +short $DOMAIN | grep -q '[0-9]'; then
        echo "${YELLOW}DNS запись для $DOMAIN не найдена или неверна!${NC}"
        read -p "Продолжить установку? (y/n): " choice
        [[ "$choice" =~ ^[Yy]$ ]] || return 1
    fi

    echo "${YELLOW}Установка Certbot...${NC}"
    apt-get install -y -qq certbot >/dev/null 2>&1
    check_error "Не удалось установить Certbot"

    echo "${YELLOW}Получение сертификата Let's Encrypt...${NC}"
    certbot certonly --standalone --non-interactive --agree-tos -m $EMAIL -d $DOMAIN
    check_error "Не удалось получить сертификат Let's Encrypt"

    (
        crontab -l 2>/dev/null
        echo "0 3 1 * * /usr/bin/certbot renew --quiet --pre-hook 'systemctl stop $SERVICE_NAME' --post-hook 'systemctl start $SERVICE_NAME'"
    ) | crontab -

    cat >>"$INSTALL_DIR/.env" <<EOL
USE_HTTPS=true
SSL_CERT=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
SSL_KEY=/etc/letsencrypt/live/$DOMAIN/privkey.pem
DOMAIN=$DOMAIN
EOL

    echo "${GREEN}Let's Encrypt успешно настроен для домена $DOMAIN!${NC}"
}

setup_custom_certs() {
    log "Настройка пользовательских сертификатов"
    echo "${YELLOW}Настройка пользовательских сертификатов...${NC}"

    while true; do
        read -p "Введите доменное имя (например, example.com): " DOMAIN
        if [[ $DOMAIN =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
            break
        else
            echo "${RED}Неверный формат домена!${NC}"
        fi
    done

    read -p "Введите полный путь к файлу сертификата (.crt или .pem): " CERT_PATH
    read -p "Введите полный путь к файлу приватного ключа (.key): " KEY_PATH

    if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
        echo "${RED}Файлы сертификатов не найдены!${NC}"
        return 1
    fi

    cat >>"$INSTALL_DIR/.env" <<EOL
USE_HTTPS=true
SSL_CERT=$CERT_PATH
SSL_KEY=$KEY_PATH
DOMAIN=$DOMAIN
EOL

    echo "${GREEN}Собственные сертификаты успешно настроены для домена $DOMAIN!${NC}"
}

# Установка с самоподписанным сертификатом
setup_selfsigned() {
    log "Настройка самоподписанного сертификата"
    echo "${YELLOW}Настройка самоподписанного сертификата...${NC}"

    mkdir -p /etc/ssl/private
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/private/admin-antizapret.key \
        -out /etc/ssl/certs/admin-antizapret.crt \
        -subj "/CN=$(hostname)" >/dev/null 2>&1

    cat >>"$INSTALL_DIR/.env" <<EOL
USE_HTTPS=true
SSL_CERT=/etc/ssl/certs/admin-antizapret.crt
SSL_KEY=/etc/ssl/private/admin-antizapret.key
EOL

    log "Самоподписанный сертификат создан"
    echo "${GREEN}Самоподписанный сертификат успешно создан!${NC}"
}

configure_http() {
    log "Настройка HTTP соединения"
    echo "${YELLOW}Настройка HTTP соединения...${NC}"

    cat >"$INSTALL_DIR/.env" <<EOL
SECRET_KEY='$SECRET_KEY'
APP_PORT=$APP_PORT
USE_HTTPS=false
EOL

    echo "${GREEN}HTTP соединение настроено на порту $APP_PORT!${NC}"
}
