#!/bin/bash

# Функция выбора порта
get_port() {
    local forbidden_port=$1
    local default_port_check=$2
    while true; do
        read -p "Введите порт для сервиса [$DEFAULT_PORT]: " APP_PORT
        APP_PORT=${APP_PORT:-"$DEFAULT_PORT"}
        if ! [[ "$APP_PORT" =~ ^[0-9]+$ ]] || ((APP_PORT < 1 || APP_PORT > 65535)) || [ "$APP_PORT" -eq "$forbidden_port" ]; then
            echo "${RED}Некорректный номер порта!${NC}"
            continue
        fi
        if [ "$APP_PORT" -eq "$default_port_check" ]; then
            if ! check_openvpn_tcp_setting; then
                continue
            fi
        fi
        SERVICE_BUSY=$(ss -tlpn | grep ":$APP_PORT" | awk -F'[(),"]' '{print $4; exit}')
        RULES_BUSY=$(iptables-save | grep "PREROUTING.*-p tcp.*--dport ${APP_PORT}")      
        if [ -n "$SERVICE_BUSY" ] || [ -n "$RULES_BUSY" ]; then
            [ -n "$SERVICE_BUSY" ] && echo "${RED}Порт ${YELLOW}$APP_PORT${RED} занят процессом ${YELLOW}$SERVICE_BUSY${NC}"
            [ -n "$RULES_BUSY" ] && {
                echo "${RED}В таблице маршрутизации обнаружено перенаправление порта ${YELLOW}$APP_PORT${RED}, приложение не будет работать корректно${NC}"
                echo "$RULES_BUSY"
            }
            continue
        fi
        return 0
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
            echo "${YELLOW}Выберите тип HTTPS соединения:${NC}"
            echo "  1) Использовать собственный домен и получить сертификаты Let's Encrypt"
            echo "  2) Использовать собственный домен и собственные сертификаты"
            echo "  3) Самоподписанный сертификат"
            read -p "Ваш выбор [1-3]: " ssl_sub_choice

            case $ssl_sub_choice in
            1|2|3)
                # Для HTTPS запрещаем 80 порт и предлагаем отключить резервирование при выборе 443
                get_port 80 443
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
            # Для HTTP все наоборот: нельзя 443 порт и предлагаем отключить резервирование при выборе 80
            get_port 443 80
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
            echo "${RED}Обнаружено, что порты 80 и 443 используются в AntiZapret-VPN как резервные для TCP OpenVPN.${NC}"
            echo "${YELLOW}Такое резервирование гарантирует работоспособность OPENVPN даже в ситуации, если провайдер использует блокирующий фаервол.${NC}"    
            echo "${YELLOW}Использование портов 80 и 443 для сервиса AdminAntizapret удобно (в случае HTTPS например можно подключаться к WEB оснастке по${NC}"
            echo "${YELLOW}адресу https://example.com вместо https://example.com:443), но это не является безопасным вариантом.${NC}"
            echo "${YELLOW}Учтите, что подавляющая часть сетевых атак приходятся именно на WEB сервисы, размещенные на 80 и 443 портах.${NC}"
            echo "Вы можете отключить это резервирование для OpenVPN, чтобы использовать стандартные WEB порты для AdminAntizapret(y) или оставить как есть, выбрав другой порт(n)"           
            read -p "Отключить резервирование портов в OpenVPN? (y/n): " change_choice
            if [[ "$change_choice" =~ ^[Yy]$ ]]; then
                sed -i 's/^OPENVPN_80_443_TCP=y/OPENVPN_80_443_TCP=n/' /root/antizapret/setup
                systemctl restart antizapret.service
                echo "${GREEN}Резервирование портов в OpenVPN отключено и сервис перезапущен!${NC}"
                return 0
            else
                return 1
            fi
        else
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

    # Тут изменил блок для email с возможностью пропуска
    read -p "Введите email для уведомлений и рассылки от Let's Encrypt (нажмите ENTER, если эта функция не нужна): " EMAIL
    while [[ -n "$EMAIL" && ! "$EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; do
        echo "${RED}Неверный формат email!${NC}"
        read -p "Попробуйте еще раз или нажмите ENTER для отмены: " EMAIL
    done

    if ! dig +short $DOMAIN | grep -q '[0-9]'; then
        echo "${YELLOW}DNS запись для $DOMAIN не найдена или неверна!${NC}"
        read -p "Продолжить установку? (y/n): " choice
        [[ "$choice" =~ ^[Yy]$ ]] || return 1
    fi

    # Функция восстановления правил
    restore_rules() {
        if [ -z "$rules" ]; then
            echo "${YELLOW}Восстановление правил с портом 80 не требуется${NC}"
        else
            echo "$SAVE_RULES" | iptables-restore
            if iptables-save | grep -q "PREROUTING.*--dport 80"; then
                echo "${GREEN}Правила с портом 80 успешно восстановлены${NC}"
            else
                check_error "Ошибка при восстановлении правил с портом 80"
            fi
        fi
    }

    # Функция восстановления служб (если они конечно были)
    restore_services() {
        if [ -n "$SERVICE_BUSY" ] && systemctl is-enabled "$SERVICE_BUSY" &> /dev/null; then
            if ! systemctl is-active "$SERVICE_BUSY" &> /dev/null; then
                printf "%s" "${YELLOW}Попытка автоматического возобновления работы службы $SERVICE_BUSY...${NC}"
                if systemctl start "$SERVICE_BUSY" &> /dev/null; then
                    echo "${GREEN}УСПЕХ${NC}"
                else
                    echo "${RED}НЕУДАЧА${NC}"
                fi
            fi
        fi
        if systemctl is-enabled "$SERVICE_NAME" &> /dev/null && ! systemctl is-active "$SERVICE_NAME" &> /dev/null; then
            systemctl start "$SERVICE_NAME"
        fi
    }    

    # Стоп службы (если они конечно есть). Для первой установки можно было и не делать остановку AdminAntizapret, добавил чтобы этим же скриптом переустанавливать можно было
    SERVICE_BUSY=$(ss -tlpn | grep ":$APP_PORT" | awk -F'[(),"]' '{print $4; exit}')
    if [ -n "$SERVICE_BUSY" ]; then
        printf "%s" "${YELLOW}Порт 80 занят службой $SERVICE_BUSY, попытка автоматического освобождения...${NC}"
        if systemctl is-enabled "$SERVICE_BUSY" &> /dev/null && systemctl is-active "$SERVICE_BUSY" &> /dev/null && systemctl stop "$SERVICE_BUSY" &> /dev/null; then
            echo "${GREEN}УСПЕХ${NC}"
        else
            echo "${RED}НЕУДАЧА${NC}"
            check_error "Попробуйте освободить порт вручную или выберите другой"
        fi
    fi

    if systemctl is-enabled "$SERVICE_NAME" &> /dev/null && systemctl is-active "$SERVICE_NAME" &> /dev/null; then
        systemctl stop "$SERVICE_NAME"
    fi

    # Временно удаляю перенаправление для порта 80
    SAVE_RULES=$(iptables-save)
    rules=$(iptables-save | grep "PREROUTING.*-p tcp.*--dport 80")
    if [ -n "$rules" ]; then
        while read -r line; do
            iptables -t nat -D $(echo $line | sed 's/^-A //')
        done <<< "$rules"
        
        if ! iptables-save | grep -q "PREROUTING.*--dport 80"; then
            echo "${GREEN}Все правила с портом 80 временно удалены${NC}"
        else
            restore_services
            check_error "Ошибка при удалении правил с портом 80"
        fi
    else
        echo "${YELLOW}Правил перенаправления с порта 80 не обнаружено. Отключение не требуется${NC}"
    fi

     # Установка certbot без дополнительных nginx и apache компонентов
    echo "${YELLOW}Установка Certbot...${NC}"  
    apt-get install -y -qq certbot --no-install-recommends >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        restore_rules
        restore_services
        check_error "Не удалось установить Certbot"
    fi

    # Удаляю файл дефолтной задачи certbot в systemd
    if [ -f /etc/cron.d/certbot ]; then
        rm -f /etc/cron.d/certbot
    fi

    # Измененный вызов certbot (с учетом нужна рассылка или нет)
    if [[ -n "$EMAIL" ]]; then
        certbot certonly --standalone --non-interactive --agree-tos -m $EMAIL -d $DOMAIN
    else
        certbot certonly --standalone --non-interactive --agree-tos --register-unsafely-without-email -d $DOMAIN
    fi

    if [ $? -ne 0 ]; then
        restore_rules
        restore_services
        check_error "Не удалось получить сертификат Let's Encrypt"
    fi

    # Создание cron-задачи
    SCRIPT_PATH="/usr/local/bin/renew_cert.sh"
    if ! [ -d "$(dirname "$SCRIPT_PATH")" ]; then
        sudo mkdir -p "$(dirname "$SCRIPT_PATH")"
    fi
    if [ -f "$SCRIPT_PATH" ]; then
        rm -f "$SCRIPT_PATH"
    fi

    cat > "$SCRIPT_PATH" <<EOF
#!/bin/bash

SERVICE_BUSY=\$(ss -tlpn | grep ':80' | awk -F'[(),"]' '{print \$4; exit}')
if [ -n "\$SERVICE_BUSY" ] && systemctl is-enabled "\$SERVICE_BUSY" && systemctl is-active "\$SERVICE_BUSY"; then
    systemctl stop "\$SERVICE_BUSY"
fi
if systemctl is-enabled "$SERVICE_NAME" &> /dev/null && systemctl is-active "$SERVICE_NAME"; then
    systemctl stop "$SERVICE_NAME"
fi

SAVE_RULES=\$(iptables-save)
PORT80_RULES=\$(iptables-save | grep "PREROUTING.*-p tcp.*--dport 80")
if [ -n "\$PORT80_RULES" ]; then
    while read -r line; do
        iptables -t nat -D \$(echo \$line | sed 's/^-A //')
    done <<< "\$PORT80_RULES"
fi

certbot renew --quiet

if [ -n "\$SAVE_RULES" ]; then
    echo "\$SAVE_RULES" | iptables-restore
fi

if [ -n "\$SERVICE_BUSY" ] && systemctl is-enabled "\$SERVICE_BUSY" && ! systemctl is-active "\$SERVICE_BUSY"; then
    systemctl start "\$SERVICE_BUSY"
fi

if systemctl is-enabled "$SERVICE_NAME" && ! systemctl is-active "$SERVICE_NAME"; then
            systemctl start "$SERVICE_NAME"
fi
EOF

    chmod +x "$SCRIPT_PATH"
    (crontab -l 2>/dev/null; echo "0 3 1 * * $SCRIPT_PATH") | crontab -

# Запись в базу пути скриптов Let's Encript и названия домена
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
