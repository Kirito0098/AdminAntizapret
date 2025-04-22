#!/bin/bash

# Удаление сервиса
uninstall() {
    printf "%s\n" "${YELLOW}Подготовка к удалению AdminAntizapret...${NC}"
    printf "%s\n" "${RED}ВНИМАНИЕ! Это действие необратимо!${NC}"

    printf "Вы уверены, что хотите удалить AdminAntizapret? (y/n) "
    read answer

    answer=$(echo "$answer" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')

    case "$answer" in
    [Yy]*)
        create_backup

        use_selfsigned=false
        use_letsencrypt=false

        if grep -q "USE_HTTPS=true" "$INSTALL_DIR/.env" 2>/dev/null; then
            if [ -f "/etc/ssl/certs/admin-antizapret.crt" ] &&
                [ -f "/etc/ssl/private/admin-antizapret.key" ]; then
                use_selfsigned=true
            elif [ -d "/etc/letsencrypt/live/" ]; then
                use_letsencrypt=true
            fi
        fi

        printf "%s\n" "${YELLOW}Остановка сервиса...${NC}"
        systemctl stop $SERVICE_NAME
        systemctl disable $SERVICE_NAME
        rm -f "/etc/systemd/system/$SERVICE_NAME.service"
        systemctl daemon-reload

        if [ "$use_selfsigned" = true ]; then
            printf "%s\n" "${YELLOW}Удаление самоподписанного сертификата...${NC}"
            rm -f /etc/ssl/certs/admin-antizapret.crt
            rm -f /etc/ssl/private/admin-antizapret.key
        fi

        if [ "$use_letsencrypt" = true ]; then
            printf "%s\n" "${YELLOW}AdminAntizapret был настроен на получение Let's Encrypt сертификата для вашего домена. ${NC}"
            printf "%s " "${YELLOW}Хотите удалить также все установленные и настроенные компоненты Let's Encrypt? (будет удален certbot, сертификаты и задания обновления)? (y/n)${NC}"
            read -r response

            if [[ $response =~ ^[yY]$ ]]; then
                printf "%s\n" "${YELLOW}Удаление Let's Encrypt сертификата...${NC}"
                DOMAIN=$(certbot certificates 2>/dev/null | grep -oP '(?<=Certificate Name: ).*' | head -n 1)
                certbot delete --non-interactive --cert-name $DOMAIN >/dev/null 2>&1 || \
                    echo "${YELLOW}Не удалось удалить сертификат Let's Encrypt${NC}"                  
                crontab -l | grep -v 'renew_cert.sh' | crontab -
                rm -rf /etc/letsencrypt
                rm -rf /var/lib/letsencrypt
                apt-get remove --purge -y -qq certbot &> /dev/null
            else
                printf "%s\n" "${YELLOW}Удаление Let's Encrypt отменено пользователем${NC}"
            fi
        fi

        printf "%s\n" "${YELLOW}Удаление файлов...${NC}"
        rm -rf "$INSTALL_DIR"
        rm -f "$LOG_FILE"

        printf "%s\n" "${YELLOW}Очистка зависимостей...${NC}"
        apt-get autoremove -y > /dev/null 2>&1

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
