#!/bin/bash

# Полный менеджер AdminAntizapret
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"

# Цвета для вывода
RED=$(printf '\033[31m')
GREEN=$(printf '\033[32m')
YELLOW=$(printf '\033[33m')
NC=$(printf '\033[0m') # No Color

# Основные параметры
INSTALL_DIR="/opt/AdminAntizapret"

# Функция для проверки ошибок
check_error() {
	local error_message="$1"
	if [ $? -ne 0 ]; then
		echo "${RED}Ошибка: $error_message${NC}" >&2
		exit 1
	fi
}

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
			# Обновляем значение VNSTAT_IFACE
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
	# Если переменной нет, добавляем её
	echo "VNSTAT_IFACE=$vnstat_iface" >>"$INSTALL_DIR/.env"
	echo "${GREEN}Установлено VNSTAT_IFACE=$vnstat_iface в $INSTALL_DIR/.env${NC}"
fi

# Настройка сервиса vnstat
echo "${YELLOW}Настройка сервиса vnstat...${NC}"
if [ -f "/lib/systemd/system/vnstat.service" ]; then
	# Проверка, существует ли уже ExecStartPre
	if grep -q "ExecStartPre=/bin/sleep 10" /lib/systemd/system/vnstat.service; then
		echo "${GREEN}ExecStartPre=/bin/sleep 10 уже присутствует в vnstat.service${NC}"
	else
		# Создаем временный файл для модификации сервиса
		temp_file=$(mktemp)
		awk '/^\[Service\]$/{print; print "ExecStartPre=/bin/sleep 10"; next}1' /lib/systemd/system/vnstat.service >"$temp_file"
		cat "$temp_file" >/lib/systemd/system/vnstat.service
		rm "$temp_file"
		echo "${GREEN}Добавлена строка ExecStartPre=/bin/sleep 10 в vnstat.service${NC}"
	fi
else
	echo "${RED}Ошибка: Файл /lib/systemd/system/vnstat.service не найден! Убедитесь, что vnstat установлен корректно.${NC}"
	exit 1
fi

# Перезагрузка конфигурации systemd и перезапуск vnstat
systemctl daemon-reload
systemctl enable vnstat
check_error "Не удалось включить сервис vnstat"
systemctl restart vnstat
check_error "Не удалось запустить сервис vnstat"
echo "${GREEN}[✓] Сервис vnstat настроен и запущен${NC}"
