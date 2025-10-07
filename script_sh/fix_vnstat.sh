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

# Сохранение выбранного интерфейса в файл .env
echo "VNSTAT_IFACE=$vnstat_iface" >>"$INSTALL_DIR/.env"
echo "${GREEN}Установлено VNSTAT_IFACE=$vnstat_iface в "$INSTALL_DIR/.env"${NC}"
