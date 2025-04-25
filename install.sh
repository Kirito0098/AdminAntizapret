#!/bin/bash
# Минималистичный установщик AdminAntizapret

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры установки
INSTALL_DIR="/opt/AdminAntizapret"
REPO_URL="https://github.com/CarolusFuchs/AdminAntizapret.git"
SCRIPT_SH_DIR="$INSTALL_DIR/script_sh"
MAIN_SCRIPT="$SCRIPT_SH_DIR/adminpanel.sh"

# Проверка root
if [ "$(id -u)" -ne 0 ]; then
  echo -e "${RED}Ошибка: этот скрипт требует прав root!${NC}" >&2
  exit 1
fi

# Установка компонентов, необходимых для работы скрипта
packages=(apt-utils whiptail iproute2 dnsutils net-tools git)
# Обновление репозитория только если чего-то не хватает
for package in "${packages[@]}"; do
    status=$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null)
    if [[ "$status" != *"ok installed"* ]]; then
        echo -e "${YELLOW}Установка необходимых для работы скрипта компонентов...${NC}"
        apt-get update > /dev/null
        break
    fi
done
#Установка недостающих компонентов
for package in "${packages[@]}"; do
    status=$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null)
    if [[ "$status" != *"ok installed"* ]]; then
        echo "Установка $package"
        sudo apt-get install -y "$package" &> /dev/null
    fi
done

# Клонирование или обновление репозитория
echo -e "${YELLOW}Проверка репозитория...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
  echo -e "${YELLOW}Репо уже существует, обновляем...${NC}"
  cd "$INSTALL_DIR" || exit 1
  git pull || {
    echo -e "${RED}Ошибка при обновлении репозитория!${NC}" >&2
    exit 1
  }
else
  if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}Директория существует, но не является репо. Удаляем и клонируем заново...${NC}"
    rm -rf "$INSTALL_DIR" || {
      echo -e "${RED}Ошибка при удалении директории!${NC}" >&2
      exit 1
    }
  fi
  git clone "$REPO_URL" "$INSTALL_DIR" || {
    echo -e "${RED}Ошибка при клонировании репозитория!${NC}" >&2
    exit 1
  }
fi

# Проверка успешности клонирования/обновления
if [ ! -f "$MAIN_SCRIPT" ]; then
  echo -e "${RED}Ошибка: не удалось найти основной скрипт!${NC}" >&2
  exit 1
fi

# Установка прав на все .sh файлы в script_sh
echo -e "${YELLOW}Установка прав на скрипты...${NC}"
find "$SCRIPT_SH_DIR" -type f -name "*.sh" -exec chmod +x {} \; || {
  echo -e "${RED}Ошибка при установке прав на скрипты!${NC}" >&2
  exit 1
}

# Запуск основного скрипта
echo -e "${GREEN}Установка завершена. Запускаем основной скрипт...${NC}"
exec "$MAIN_SCRIPT"
