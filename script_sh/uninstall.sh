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
		use_nginx=false

		# Определяем тип установки
		if [ -f "$INSTALL_DIR/.env" ]; then
			if grep -q "USE_HTTPS=true" "$INSTALL_DIR/.env" 2>/dev/null; then
				if [ -f "/etc/ssl/certs/admin-antizapret.crt" ] && [ -f "/etc/ssl/private/admin-antizapret.key" ]; then
					use_selfsigned=true
				elif grep -q "DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null; then
					use_letsencrypt=true
				fi
			elif grep -q "USE_HTTPS=false" "$INSTALL_DIR/.env" && grep -q "DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null; then
				# Это вариант с Nginx reverse proxy
				use_nginx=true
				use_letsencrypt=true
			fi
		fi

		printf "%s\n" "${YELLOW}Остановка сервиса...${NC}"
		systemctl stop "$SERVICE_NAME" 2>/dev/null || true
		systemctl disable "$SERVICE_NAME" 2>/dev/null || true
		rm -f "/etc/systemd/system/$SERVICE_NAME.service"
		systemctl daemon-reload

		# Удаление самоподписанного сертификата
		if [ "$use_selfsigned" = true ]; then
			printf "%s\n" "${YELLOW}Удаление самоподписанного сертификата...${NC}"
			rm -f /etc/ssl/certs/admin-antizapret.crt
			rm -f /etc/ssl/private/admin-antizapret.key
		fi

		# Обработка Let's Encrypt (включая вариант с Nginx)
		if [ "$use_letsencrypt" = true ]; then
			DOMAIN=$(grep "^DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr -d '" ' || echo "")

			printf "%s\n" "${YELLOW}Обнаружено использование Let's Encrypt сертификатов.${NC}"
			printf "%s " "${YELLOW}Хотите полностью удалить сертификаты, конфиги Nginx (если есть) и компоненты Certbot? (y/n): ${NC}"
			read -r response

			if [[ $response =~ ^[yY]$ ]]; then
				# Удаление конфига Nginx (если был вариант с reverse proxy)
				if [ "$use_nginx" = true ] && [ -n "$DOMAIN" ]; then
					NGINX_CONF_NAME=$(echo "$DOMAIN" | sed 's/\./_/g')
					printf "%s\n" "${YELLOW}Удаление конфигурации Nginx для домена $DOMAIN...${NC}"
					rm -f "/etc/nginx/sites-available/$NGINX_CONF_NAME"
					rm -f "/etc/nginx/sites-enabled/$NGINX_CONF_NAME"
					nginx -t && systemctl reload nginx || echo "${YELLOW}Nginx не перезапущен (возможно, не запущен)${NC}"
				fi

				# Удаление сертификата Let's Encrypt
				if [ -n "$DOMAIN" ] && command -v certbot >/dev/null 2>&1; then
					printf "%s\n" "${YELLOW}Удаление сертификата Let's Encrypt для $DOMAIN...${NC}"
					certbot delete --non-interactive --cert-name "$DOMAIN" >/dev/null 2>&1 ||
						echo "${YELLOW}Сертификат $DOMAIN не найден или уже удалён${NC}"
				fi

				# Удаление старых cron-задач (из старых вариантов)
				crontab -l 2>/dev/null | grep -v 'renew_cert.sh' | crontab - 2>/dev/null || true

				# Отключение таймера certbot (современный способ)
				systemctl disable --now certbot.timer 2>/dev/null || true

				# Полное удаление certbot и всех его данных
				printf "%s\n" "${YELLOW}Удаление пакета certbot и всех связанных файлов...${NC}"
				apt-get remove --purge -y -qq certbot python3-certbot-nginx >/dev/null 2>&1 || true
				rm -rf /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt
				apt-get autoremove -y -qq >/dev/null 2>&1
			else
				printf "%s\n" "${YELLOW}Удаление Let's Encrypt компонентов отменено пользователем.${NC}"
			fi
		fi

		printf "%s\n" "${YELLOW}Удаление основных файлов приложения...${NC}"
		rm -rf "$INSTALL_DIR"
		rm -f "$LOG_FILE"

		printf "%s\n" "${GREEN}Удаление завершено успешно!${NC}"
		printf "%s\n" "${YELLOW}Резервная копия сохранена в /var/backups/antizapret${NC}"
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
