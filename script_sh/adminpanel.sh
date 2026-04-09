#!/bin/bash

# Полный менеджер AdminAntizapret
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"

# Цвета для вывода
RED=$(printf '\033[31m')
GREEN=$(printf '\033[32m')
YELLOW=$(printf '\033[33m')
CYAN=$(printf '\033[36m')
NC=$(printf '\033[0m')

# Основные параметры
INSTALL_DIR="/opt/AdminAntizapret"
VENV_PATH="$INSTALL_DIR/venv"
SERVICE_NAME="admin-antizapret"
DEFAULT_PORT="5050"
APP_PORT="$DEFAULT_PORT"
DB_FILE="$INSTALL_DIR/instance/users.db"
ANTIZAPRET_INSTALL_DIR="/root/antizapret"
ANTIZAPRET_INSTALL_SCRIPT="https://raw.githubusercontent.com/GubernievS/AntiZapret-VPN/main/setup.sh"
LOG_FILE="/var/log/adminpanel.log"
INSTALL_LOG_FILE=""
INSTALL_LOG_ACTIVE=0
INSTALL_LOG_KEEP_COUNT=30
MAX_MAIN_LOG_SIZE_MB=20
MAX_MAIN_LOG_BACKUPS=5
INCLUDE_DIR="$INSTALL_DIR/script_sh"
ADMIN_PANEL_DIR="/root/AdminPanel"

modules=(
	"ssl_setup"
	"backup_functions"
	"monitoring"
	"service_functions"
	"uninstall"
	"utils"
	"user_management"
)

for module in "${modules[@]}"; do
	if [ -f "$INCLUDE_DIR/${module}.sh" ]; then
		. "$INCLUDE_DIR/${module}.sh"
	else
		echo "${RED}Ошибка: не найден файл ${module}.sh${NC}" >&2
		exit 1
	fi
done

generate_secret_key() {
	if command -v openssl >/dev/null 2>&1; then
		openssl rand -hex 32
		return $?
	fi

	if command -v python3 >/dev/null 2>&1; then
		python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
		return $?
	fi

	if [ -r /dev/urandom ]; then
		od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
		return $?
	fi

	return 1
}

# Генерируем случайный секретный ключ
SECRET_KEY=$(generate_secret_key)
if [ -z "$SECRET_KEY" ]; then
	echo "${RED}Ошибка: не удалось сгенерировать SECRET_KEY (openssl/python3/dev/urandom недоступны).${NC}" >&2
	exit 1
fi

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
	if ! apt-get update --quiet --quiet >/dev/null; then
		check_error "Не удалось обновить индексы пакетов"
	fi
	if ! apt-get install -y --quiet --quiet apt-utils >/dev/null; then
		check_error "Не удалось установить apt-utils"
	fi
	if ! apt-get install -y --quiet --quiet python3 python3-pip git wget openssl python3-venv cron vnstat >/dev/null; then
		check_error "Не удалось установить зависимости"
	fi
	echo "${GREEN}[✓] Готово${NC}"
}

# Полная проверка окружения и зависимостей
verify_project_environment() {
	echo "${YELLOW}Проверка окружения AdminAntizapret...${NC}"

	local failed=0
	local warned=0
	local passed=0
	local req_file="$INSTALL_DIR/requirements.txt"
	local missing_system_packages=()
	local required_system_packages=(python3 python3-pip python3-venv git wget openssl cron vnstat)

	print_ok() {
		echo "${GREEN}[✓] $1${NC}"
		passed=$((passed + 1))
	}

	print_warn() {
		echo "${YELLOW}[!] $1${NC}"
		warned=$((warned + 1))
	}

	print_fail() {
		echo "${RED}[✗] $1${NC}"
		failed=$((failed + 1))
	}

	normalize_pkg_name() {
		echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[-_.]+/-/g'
	}

	echo "${YELLOW}1) Проверка системных команд...${NC}"
	local required_commands=(python3 pip3 git wget openssl systemctl awk sed grep)
	for cmd in "${required_commands[@]}"; do
		if command -v "$cmd" >/dev/null 2>&1; then
			print_ok "Команда '$cmd' доступна"
		else
			print_fail "Команда '$cmd' не найдена"
		fi
	done

	echo "${YELLOW}2) Проверка системных пакетов...${NC}"
	for pkg in "${required_system_packages[@]}"; do
		if dpkg -s "$pkg" >/dev/null 2>&1; then
			print_ok "Пакет '$pkg' установлен"
		else
			print_fail "Пакет '$pkg' не установлен"
			missing_system_packages+=("$pkg")
		fi
	done

	if [ "${#missing_system_packages[@]}" -gt 0 ]; then
		echo "${YELLOW}Найдены отсутствующие системные пакеты: ${missing_system_packages[*]}${NC}"
		read -r -p "Установить их сейчас? (y/n): " install_missing_sys
		install_missing_sys=$(echo "$install_missing_sys" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
		if [[ "$install_missing_sys" =~ ^y ]]; then
			echo "${YELLOW}Устанавливаем недостающие системные пакеты...${NC}"
			apt-get update --quiet --quiet >/dev/null && apt-get install -y --quiet --quiet "${missing_system_packages[@]}" >/dev/null
			if [ $? -eq 0 ]; then
				print_ok "Системные пакеты установлены"
			else
				print_fail "Не удалось установить часть системных пакетов"
			fi
		else
			print_warn "Установка системных пакетов пропущена"
		fi
	fi

	echo "${YELLOW}3) Проверка виртуального окружения...${NC}"
	if [ -x "$VENV_PATH/bin/python3" ] && [ -x "$VENV_PATH/bin/pip" ]; then
		print_ok "Виртуальное окружение найдено: $VENV_PATH"
	else
		print_fail "Виртуальное окружение не найдено или повреждено ($VENV_PATH)"
	fi

	echo "${YELLOW}4) Проверка Python-зависимостей из requirements.txt...${NC}"
	if [ ! -f "$req_file" ]; then
		print_fail "Файл requirements.txt не найден: $req_file"
	else
		print_ok "Файл requirements.txt найден"

		if [ -x "$VENV_PATH/bin/pip" ]; then
			local installed_pkgs
			installed_pkgs=$(
				"$VENV_PATH/bin/pip" list --format=freeze 2>/dev/null |
					cut -d'=' -f1 |
					sed '/^$/d' |
					while IFS= read -r p; do normalize_pkg_name "$p"; done
			)

			local missing_python_packages=()
			while IFS= read -r line; do
				line=$(echo "$line" | sed -E 's/[[:space:]]*#.*$//' | tr -d '[:space:]')
				[ -z "$line" ] && continue

				local req_name
				req_name=$(echo "$line" | sed -E 's/[<>=!~].*$//' | sed -E 's/\[.*\]$//')
				req_name=$(normalize_pkg_name "$req_name")

				if ! echo "$installed_pkgs" | grep -qx "$req_name"; then
					missing_python_packages+=("$line")
				fi
			done <"$req_file"

			if [ "${#missing_python_packages[@]}" -eq 0 ]; then
				print_ok "Все пакеты из requirements.txt установлены"
			else
				print_fail "Не установлены Python-пакеты из requirements.txt (${#missing_python_packages[@]} шт.)"
				printf '%s\n' "${missing_python_packages[@]}" | sed 's/^/  - /'

				read -r -p "Установить/обновить Python-зависимости сейчас? (y/n): " install_py_missing
				install_py_missing=$(echo "$install_py_missing" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
				if [[ "$install_py_missing" =~ ^y ]]; then
					echo "${YELLOW}Устанавливаем Python-зависимости...${NC}"
					"$VENV_PATH/bin/pip" install -q -r "$req_file"
					if [ $? -eq 0 ]; then
						print_ok "Python-зависимости установлены"
					else
						print_fail "Не удалось установить Python-зависимости"
					fi
				else
					print_warn "Установка Python-зависимостей пропущена"
				fi
			fi

			"$VENV_PATH/bin/pip" check >/dev/null 2>&1
			if [ $? -eq 0 ]; then
				print_ok "Зависимости Python согласованы (pip check)"
			else
				print_warn "Обнаружены конфликты зависимостей Python (pip check). Выполните: $VENV_PATH/bin/pip check"
			fi
		else
			print_fail "Невозможно проверить Python-зависимости: pip в venv не найден"
		fi
	fi

	echo "${YELLOW}5) Проверка ключевых файлов и сервисов...${NC}"
	if [ -f "$INSTALL_DIR/.env" ]; then
		print_ok "Файл .env присутствует"
	else
		print_fail "Файл .env отсутствует"
	fi

	if [ -f "$DB_FILE" ]; then
		print_ok "База данных пользователей найдена: $DB_FILE"
	else
		print_fail "База данных пользователей не найдена: $DB_FILE"
	fi

	if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
		print_ok "Systemd unit найден: $SERVICE_NAME.service"
	else
		print_fail "Systemd unit не найден: /etc/systemd/system/$SERVICE_NAME.service"
	fi

	if systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
		print_ok "Сервис $SERVICE_NAME включен в автозапуск"
	else
		print_warn "Сервис $SERVICE_NAME не включен в автозапуск"
	fi

	if systemctl is-active --quiet "$SERVICE_NAME"; then
		print_ok "Сервис $SERVICE_NAME запущен"
	else
		print_warn "Сервис $SERVICE_NAME не запущен"
	fi

	echo ""
	echo "${YELLOW}Итог проверки:${NC}"
	echo "${GREEN}Успешно: $passed${NC}"
	echo "${RED}Ошибок: $failed${NC}"
	echo "${YELLOW}Предупреждений: $warned${NC}"

	if [ "$failed" -eq 0 ]; then
		echo "${GREEN}Окружение готово для работы проекта.${NC}"
	else
		echo "${RED}Обнаружены проблемы. Рекомендуется устранить ошибки перед дальнейшей работой.${NC}"
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

resolve_vnstat_unit_file() {
	local fragment_path=""

	if command -v systemctl >/dev/null 2>&1; then
		fragment_path=$(systemctl show -P FragmentPath vnstat.service 2>/dev/null || true)
		if [ -n "$fragment_path" ] && [ -f "$fragment_path" ]; then
			echo "$fragment_path"
			return 0
		fi
	fi

	if [ -f "/lib/systemd/system/vnstat.service" ]; then
		echo "/lib/systemd/system/vnstat.service"
		return 0
	fi

	if [ -f "/usr/lib/systemd/system/vnstat.service" ]; then
		echo "/usr/lib/systemd/system/vnstat.service"
		return 0
	fi

	return 1
}

# Установка AntiZapret-VPN
install_antizapret() {
	log "Проверка наличия AntiZapret-VPN"
	echo "${YELLOW}Проверка установленного AntiZapret-VPN...${NC}"

	# Функция проверки установки AntiZapret
	check_antizapret_installed() {
		if systemctl is-active --quiet antizapret.service 2>/dev/null; then
			return 0
		fi
		if [ -d "/root/antizapret" ]; then
			return 0
		fi
		return 1
	}

	# Проверяем установлен ли AntiZapret
	if check_antizapret_installed; then
		log "AntiZapret-VPN обнаружен в системе"
		echo "${GREEN}AntiZapret-VPN уже установлен (обнаружен сервис или директория).${NC}"
		return 0
	fi

	log "AntiZapret-VPN не установлен"
	echo "${RED}ВНИМАНИЕ! Модуль AntiZapret-VPN не установлен!${NC}"
	echo ""
	echo "${YELLOW}Это обязательный компонент для работы системы.${NC}"
	echo "Пожалуйста, установите его вручную следующими командами:"
	echo ""
	echo "1. Скачайте и запустите установочный скрипт:"
	echo "${CYAN} bash <(wget --no-hsts -qO- https://raw.githubusercontent.com/GubernievS/AntiZapret-VPN/main/setup.sh) | bash${NC}"
	echo ""
	echo "2. Затем запустите этот скрипт снова"
	echo ""
	echo "${YELLOW}Без этого модуля работа системы невозможна.${NC}"
	echo ""
	exit 1
}

# Автоматическое обновление
auto_update() {
	log "Проверка обновлений"
	echo "${YELLOW}Проверка обновлений...${NC}"
	cd "$INSTALL_DIR" || return 1

	if ! git fetch origin main; then
		check_error "Не удалось получить обновления из origin/main"
	fi

	if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
		echo "${GREEN}Найдены обновления. Установка...${NC}"
		if ! git pull origin main; then
			check_error "Не удалось выполнить git pull origin main"
		fi
		if ! "$VENV_PATH/bin/pip" install -q -r requirements.txt; then
			check_error "Не удалось обновить Python-зависимости"
		fi
		if ! systemctl restart "$SERVICE_NAME"; then
			check_error "Не удалось перезапустить сервис $SERVICE_NAME"
		fi
		echo "${GREEN}Обновление завершено!${NC}"
	else
		echo "${GREEN}Система актуальна.${NC}"
	fi
}

start_install_logging() {
	prune_logs_by_pattern "/var/log/adminpanel-install-*.log" "$INSTALL_LOG_KEEP_COUNT"

	INSTALL_LOG_FILE="/var/log/adminpanel-install-$(date '+%Y%m%d-%H%M%S').log"
	if ! touch "$INSTALL_LOG_FILE" 2>/dev/null; then
		echo "${RED}Не удалось создать файл лога установки: $INSTALL_LOG_FILE${NC}"
		return 1
	fi
	chmod 600 "$INSTALL_LOG_FILE" 2>/dev/null || true

	INSTALL_LOG_ACTIVE=1
	exec 7>&1 8>&2
	exec > >(tee -a "$INSTALL_LOG_FILE") 2>&1

	echo "${YELLOW}Лог установки: $INSTALL_LOG_FILE${NC}"
	log "Начата установка. Подробный лог: $INSTALL_LOG_FILE"
}

finish_install_logging() {
	local status=${1:-0}
	if [ "${INSTALL_LOG_ACTIVE:-0}" -ne 1 ]; then
		return
	fi

	if [ "$status" -eq 0 ]; then
		log "Установка завершена успешно"
		echo "${GREEN}Установка завершена успешно${NC}"
	else
		log "Установка завершена с ошибкой (код: $status)"
		echo "${RED}Установка завершена с ошибкой (код: $status)${NC}"
	fi
	echo "${YELLOW}Подробный лог установки: $INSTALL_LOG_FILE${NC}"

	exec 1>&7 2>&8
	exec 7>&- 8>&-
	INSTALL_LOG_ACTIVE=0
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
		printf "│ 11. Изменить порт сервиса                  │\n"
		printf "│ 12. Мониторинг системы                     │\n"
		printf "│ 13. Проверить конфигурацию                 │\n"
		printf "│ 14. Проверить конфликт портов 80/443       │\n"
		printf "│ 15. Изменить протокол (HTTP/HTTPS)         │\n"
		printf "│ 16. Проверить окружение проекта            │\n"
		printf "│ 0. Выход                                   │\n"
		printf "└────────────────────────────────────────────┘\n"
		printf "%s\n" "${NC}"

		read -p "Выберите действие [0-16]: " choice
		case $choice in
		1) add_admin ;;
		2) delete_admin ;;
		3) restart_service ;;
		4) check_status ;;
		5) show_logs ;;
		6) check_updates ;;
		7) create_backup ;;
		8)
			read -p "Введите путь к файлу резервной копии: " backup_file
			restore_backup "$backup_file"
			press_any_key
			;;
		9) uninstall ;;
		10) check_and_set_permissions ;;
		11) change_port ;;
		12) show_monitor ;;
		13)
			validate_config
			press_any_key
			;;
		14)
			check_openvpn_tcp_setting
			press_any_key
			;;
		15) change_protocol ;;
		16)
			verify_project_environment
			press_any_key
			;;
		0) exit 0 ;;
		*)
			printf "%s\n" "${RED}Неверный выбор!${NC}"
			sleep 1
			;;
		esac
	done
}

# Установка AdminAntizapret
install() {
	start_install_logging || exit 1
	log "Старт процедуры установки AdminAntizapret"

	clear
	printf "%s\n" "${GREEN}"
	printf "┌────────────────────────────────────────────┐\n"
	printf "│          Установка AdminAntizapret         │\n"
	printf "└────────────────────────────────────────────┘\n"
	printf "%s\n" "${NC}"

	# Проверка установки AntiZapret-VPN
	check_antizapret_installed() {
		if systemctl is-active --quiet antizapret.service 2>/dev/null; then
			return 0
		fi
		[ -d "$ANTIZAPRET_INSTALL_DIR" ]
	}

	# Проверка установки AntiZapret-VPN
	echo "${YELLOW}Проверка установки AntiZapret-VPN...${NC}"
	if ! check_antizapret_installed; then
		install_antizapret
		# После установки делаем дополнительную проверку
		if ! check_antizapret_installed; then
			echo "${RED}[!] Критическая ошибка: AntiZapret-VPN не установлен!${NC}"
			echo "${YELLOW}Админ-панель не может работать без AntiZapret. Установка прервана.${NC}"
			finish_install_logging 1
			exit 1
		fi
	else
		echo "${GREEN}[✓] Готово${NC}"
	fi

	# Установка прав выполнения
	echo "${YELLOW}Установка прав выполнения...${NC}" &&
		chmod +x "$INSTALL_DIR/client.sh" "$ANTIZAPRET_INSTALL_DIR/doall.sh" 2>/dev/null || true
	echo "${GREEN}[✓] Готово${NC}"

	# Обновление пакетов
	echo "${YELLOW}Обновление списка пакетов...${NC}"
	if ! apt-get update --quiet --quiet >/dev/null; then
		check_error "Не удалось обновить пакеты"
	fi
	echo "${GREEN}[✓] Готово${NC}"

	# Проверка и установка зависимостей
	check_dependencies

	# Создание виртуального окружения
	echo "${YELLOW}Создание виртуального окружения...${NC}"
	if ! python3 -m venv "$VENV_PATH"; then
		check_error "Не удалось создать виртуальное окружение"
	fi
	echo "${GREEN}[✓] Готово${NC}"

	# Обновление pip-инструментов внутри venv для лучшей совместимости пакетов
	echo "${YELLOW}Обновление pip/setuptools/wheel...${NC}"
	if ! "$VENV_PATH/bin/pip" install -q --upgrade pip setuptools wheel; then
		check_error "Не удалось обновить pip/setuptools/wheel"
	fi
	echo "${GREEN}[✓] Готово${NC}"

	# Установка Python-зависимостей
	echo "${YELLOW}Установка Python-зависимостей...${NC}"
	if ! "$VENV_PATH/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"; then
		check_error "Не удалось установить Python-зависимости"
	fi
	echo "${GREEN}[✓] Готово${NC}"

	# Выбор способа установки
	if ! choose_installation_type; then
		finish_install_logging 1
		exit 1
	fi

	# Инициализация базы данных
	init_db

	# Создание systemd сервиса
	echo "${YELLOW}Создание systemd сервиса...${NC}"
	cat >"/etc/systemd/system/$SERVICE_NAME.service" <<EOL
[Unit]
Description=AdminAntizapret VPN Management
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_PATH/bin/gunicorn \
    -c $INSTALL_DIR/gunicorn.conf.py \
    app:app
Restart=always
RestartSec=5
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOL

	# Создание systemd сервиса и таймера для фоновой синхронизации трафика
	echo "${YELLOW}Создание systemd таймера синхронизации трафика...${NC}"
	cat >"/etc/systemd/system/admin-antizapret-traffic-sync.service" <<EOL
[Unit]
Description=AdminAntizapret Traffic Sync
After=network.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_PATH/bin/python3 $INSTALL_DIR/utils/traffic_sync.py
Environment="PYTHONUNBUFFERED=1"
EOL

	cat >"/etc/systemd/system/admin-antizapret-traffic-sync.timer" <<EOL
[Unit]
Description=Run AdminAntizapret traffic sync every 30 seconds

[Timer]
OnBootSec=45sec
OnUnitActiveSec=30sec
AccuracySec=1s
Unit=admin-antizapret-traffic-sync.service
Persistent=true

[Install]
WantedBy=timers.target
EOL

	# Включение и запуск сервиса
	systemctl daemon-reload
	systemctl enable "$SERVICE_NAME"
	systemctl start "$SERVICE_NAME"
	check_error "Не удалось запустить сервис"
	systemctl enable --now admin-antizapret-traffic-sync.timer
	check_error "Не удалось включить таймер синхронизации трафика"

	# Фильтрация и получение списка доступных сетевых интерфейсов (исключая lo, docker, veth и т.д.)
	available_interfaces=$(ip link show | grep -E '^[0-9]+: ' | awk -F: '{print $2}' | sed 's/ //g' |
		grep -vE '^(lo|docker|veth|br-|vpn|antizapret|tun|tap)' | sort)

	# Подсчет количества доступных интерфейсов
	interface_count=$(echo "$available_interfaces" | wc -l)

	# Определение интерфейса по умолчанию (используемого для выхода в интернет)
	default_interface=$(ip route | grep default | awk '{print $5}' | head -n 1)
	if [ -z "$default_interface" ]; then
		default_interface="eth0"
	fi

	# Проверка наличия доступных интерфейсов
	if [ -z "$available_interfaces" ]; then
		echo "${RED}Не найдено доступных сетевых интерфейсов!${NC}"
		finish_install_logging 1
		exit 1
	fi

	# Автоматический выбор интерфейса, если доступен только один
	if [ "$interface_count" -eq 1 ]; then
		vnstat_iface="$available_interfaces"
		echo "${GREEN}Обнаружен только один интерфейс: $vnstat_iface. Используется автоматически.${NC}"
	else
		# Вывод списка доступных интерфейсов и запрос выбора у пользователя
		echo "${YELLOW}Доступные сетевые интерфейсы:${NC}"
		echo "$available_interfaces"
		while true; do
			read -p "Введите сетевой интерфейс для мониторинга трафика vnstat (по умолчанию: $default_interface): " vnstat_iface
			vnstat_iface=${vnstat_iface:-$default_interface}
			# Проверка существования выбранного интерфейса
			if ip link show "$vnstat_iface" >/dev/null 2>&1; then
				break
			else
				echo "${RED}Интерфейс '$vnstat_iface' не существует! Попробуйте другой.${NC}"
			fi
		done
	fi

	# Проверка наличия VNSTAT_IFACE в файле .env
	if [ -f "$INSTALL_DIR/.env" ] && grep -q "^VNSTAT_IFACE=" "$INSTALL_DIR/.env"; then
		current_vnstat_iface=$(grep "^VNSTAT_IFACE=" "$INSTALL_DIR/.env" | cut -d'=' -f2)
		echo "${YELLOW}Переменная VNSTAT_IFACE уже задана в $INSTALL_DIR/.env как: $current_vnstat_iface${NC}"
		while true; do
			read -p "Хотите изменить интерфейс на $vnstat_iface? (y/n): " answer
			answer=$(echo "$answer" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
			case $answer in
			[Yy]*)
				sed -i "s/^VNSTAT_IFACE=.*/VNSTAT_IFACE=$vnstat_iface/" "$INSTALL_DIR/.env"
				echo "${GREEN}Обновлено VNSTAT_IFACE=$vnstat_iface в $INSTALL_DIR/.env${NC}"
				break
				;;
			[Nn]*)
				echo "${GREEN}Сохранено текущее значение VNSTAT_IFACE=$current_vnstat_iface${NC}"
				vnstat_iface="$current_vnstat_iface"
				break
				;;
			*)
				echo "${RED}Пожалуйста, введите только 'y' или 'n'${NC}"
				;;
			esac
		done
	else
		echo "VNSTAT_IFACE=$vnstat_iface" >>"$INSTALL_DIR/.env"
		echo "${GREEN}Установлено VNSTAT_IFACE=$vnstat_iface в $INSTALL_DIR/.env${NC}"
	fi

	# Настройка сервиса vnstat
	echo "${YELLOW}Настройка сервиса vnstat...${NC}"
	vnstat_unit_file=$(resolve_vnstat_unit_file)
	if [ -n "$vnstat_unit_file" ] && [ -f "$vnstat_unit_file" ]; then
		if grep -q "ExecStartPre=/bin/sleep 10" "$vnstat_unit_file"; then
			echo "${GREEN}ExecStartPre=/bin/sleep 10 уже присутствует в vnstat.service${NC}"
		else
			temp_file=$(mktemp)
			awk '/^\[Service\]$/{print; print "ExecStartPre=/bin/sleep 10"; next}1' "$vnstat_unit_file" >"$temp_file"
			cat "$temp_file" >"$vnstat_unit_file"
			rm "$temp_file"
			echo "${GREEN}Добавлена строка ExecStartPre=/bin/sleep 10 в vnstat.service${NC}"
		fi
	else
		echo "${RED}Ошибка: unit-файл vnstat.service не найден! Убедитесь, что vnstat установлен корректно.${NC}"
		exit 1
	fi

	# Перезагрузка конфигурации systemd и перезапуск vnstat
	systemctl daemon-reload
	systemctl enable vnstat
	check_error "Не удалось включить сервис vnstat"
	systemctl restart vnstat
	check_error "Не удалось запустить сервис vnstat"
	echo "${GREEN}[✓] Сервис vnstat настроен и запущен${NC}"

	# Добавление дополнительных настроек в .env без дублей ключей
	echo "${YELLOW}Добавление дополнительных настроек в .env...${NC}"
	set_env_value "ALLOWED_IPS" ""
	set_env_value "IP_RESTRICTION_MODE" "strict"
	echo "${GREEN}[✓] Дополнительные настройки добавлены в .env${NC}"

	# Проверка установки
	if systemctl is-active --quiet "$SERVICE_NAME"; then
		if grep -q "^DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null; then
			DOMAIN=$(grep "^DOMAIN=" "$INSTALL_DIR/.env" | cut -d'=' -f2 | tr -d '"')
		else
			DOMAIN=""
		fi

		if grep -q "USE_HTTPS=true" "$INSTALL_DIR/.env"; then
			if [ -n "$DOMAIN" ]; then
				address="https://$DOMAIN:$APP_PORT"
			else

				address="https://$(hostname -I | awk '{print $1}'):$APP_PORT"
			fi
		else
			if [ -n "$DOMAIN" ]; then
				address="https://$DOMAIN"

			else
				address="http://$(hostname -I | awk '{print $1}'):$APP_PORT"
			fi
		fi

		line="│ Адрес: $address"
		line_len=${#line}
		max_len=55
		if [ "$line_len" -lt "$max_len" ]; then
			padding=$((max_len - line_len))
			line="$line$(printf '%*s' "$padding")│"
		else
			line="$line│"
		fi

		echo "${GREEN}"
		echo "┌──────────────────────────────────────────────────────┐"
		echo "│             Установка успешно завершена!             │"
		echo "├──────────────────────────────────────────────────────┤"
		echo "$line"
		echo "│                                                      │"
		echo "│ Для входа используйте учетные данные,                │"
		echo "│ созданные при инициализации базы данных              │"
		echo "└──────────────────────────────────────────────────────┘"
		echo "${NC}"

		copy_to_adminpanel
	else
		echo "${RED}Ошибка при запуске сервиса!${NC}"
		journalctl -u "$SERVICE_NAME" -n 10 --no-pager
		finish_install_logging 1
		exit 1
	fi

	finish_install_logging 0
	press_any_key
}

# Главная функция
main() {
	check_root
	init_logging

	case "$1" in
	"--install")
		install
		;;
	"--restart")
		restart_service
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
			while true; do
				printf "Хотите установить? (y/n) "
				read -r answer
				answer=$(echo "$answer" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
				case $answer in
				[Yy]*)
					install
					main_menu
					break
					;;
				[Nn]*)
					exit 0
					;;
				*)
					printf "%s\n" "${RED}Пожалуйста, введите только 'y' или 'n'${NC}"
					;;
				esac
			done
		else
			main_menu
		fi
		;;
	esac
}

# Запуск скрипта
main "$@"
