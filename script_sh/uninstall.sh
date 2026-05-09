#!/bin/bash

uninstall() {
    printf "\n"
    _m_top
    _m_title "Удаление AdminAntizapret"
    _m_sep
    _m_item "Это действие необратимо!"
    _m_bot
    printf "\n"

    ui_confirm "Вы уверены, что хотите удалить AdminAntizapret?" || {
        ui_ok "Удаление отменено"
        press_any_key
        return
    }

    create_backup

    local use_selfsigned=false use_letsencrypt=false use_nginx=false

    if [ -f "$INSTALL_DIR/.env" ]; then
        if grep -q "USE_HTTPS=true" "$INSTALL_DIR/.env" 2>/dev/null; then
            if [ -f "/etc/ssl/certs/admin-antizapret.crt" ] && \
               [ -f "/etc/ssl/private/admin-antizapret.key" ]; then
                use_selfsigned=true
            elif grep -q "DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null; then
                use_letsencrypt=true
            fi
        elif grep -q "USE_HTTPS=false" "$INSTALL_DIR/.env" && \
             grep -q "DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null; then
            use_nginx=true
            use_letsencrypt=true
        fi
    fi

    ui_info "Остановка сервисов..."
    crontab -l 2>/dev/null | grep -v 'adminantizapret-nightly-idle-restart' | crontab - 2>/dev/null || true
    systemctl stop  "admin-antizapret-traffic-sync.timer"   2>/dev/null || true
    systemctl disable "admin-antizapret-traffic-sync.timer" 2>/dev/null || true
    systemctl stop  "admin-antizapret-traffic-sync.service" 2>/dev/null || true
    systemctl disable "admin-antizapret-traffic-sync.service" 2>/dev/null || true
    rm -f "/etc/systemd/system/admin-antizapret-traffic-sync.timer"
    rm -f "/etc/systemd/system/admin-antizapret-traffic-sync.service"
    systemctl stop    "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    ui_ok "Сервисы остановлены"

    if [ "$use_selfsigned" = true ]; then
        ui_info "Удаление самоподписанного сертификата..."
        rm -f /etc/ssl/certs/admin-antizapret.crt
        rm -f /etc/ssl/private/admin-antizapret.key
        ui_ok "Сертификат удалён"
    fi

    if [ "$use_letsencrypt" = true ]; then
        local DOMAIN
        DOMAIN=$(grep "^DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr -d '" ' || printf '')

        ui_warn "Обнаружены сертификаты Let's Encrypt для домена: $DOMAIN"
        if ui_confirm "Удалить сертификат и конфиг Nginx (если есть)?"; then
            if [ "$use_nginx" = true ] && [ -n "$DOMAIN" ]; then
                local conf="${DOMAIN//./_}"
                ui_info "Удаление конфигурации Nginx..."
                rm -f "/etc/nginx/sites-available/$conf"
                rm -f "/etc/nginx/sites-enabled/$conf"
                nginx -t && systemctl reload nginx 2>/dev/null || ui_warn "Nginx не перезагружен"
            fi
            if [ -n "$DOMAIN" ] && command -v certbot >/dev/null 2>&1; then
                ui_info "Удаление сертификата Let's Encrypt..."
                certbot delete --non-interactive --cert-name "$DOMAIN" >/dev/null 2>&1 || \
                    ui_warn "Сертификат $DOMAIN не найден или уже удалён"
            fi
            crontab -l 2>/dev/null | grep -v 'renew_cert.sh' | crontab - 2>/dev/null || true
            systemctl disable --now certbot.timer 2>/dev/null || true
            ui_ok "Сертификат и связанные файлы удалены"
        else
            ui_ok "Удаление сертификата отменено"
        fi
    fi

    ui_info "Удаление файлов приложения..."
    rm -rf "$INSTALL_DIR"
    rm -f "$LOG_FILE"
    ui_ok "Файлы удалены"

    printf "\n"
    ui_ok "Удаление завершено"
    ui_info "Резервная копия сохранена в /var/backups/antizapret"
    press_any_key
    exit 0
}
