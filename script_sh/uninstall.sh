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
                if [ -f "/etc/ssl/certs/admin-antizapret.crt" ] && \
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
                printf "%s\n" "${YELLOW}Удаление Let's Encrypt сертификата...${NC}"
                certbot delete --non-interactive --cert-name $DOMAIN 2>/dev/null || \
                    echo "${YELLOW}Не удалось удалить сертификат Let's Encrypt${NC}"
                crontab -l | grep -v 'certbot renew' | crontab -
            fi
            
            printf "%s\n" "${YELLOW}Удаление файлов...${NC}"
            rm -rf "$INSTALL_DIR"
            rm -f "$LOG_FILE"
            
            printf "%s\n" "${YELLOW}Очистка зависимостей...${NC}"
            apt-get autoremove -y --purge python3-venv python3-pip certbot >/dev/null 2>&1
        
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