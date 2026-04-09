#!/bin/bash
# Минималистичный установщик AdminAntizapret

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры установки
INSTALL_DIR="/opt/AdminAntizapret"
REPO_URL="https://github.com/Kirito0098/AdminAntizapret.git"
SCRIPT_SH_DIR="$INSTALL_DIR/script_sh"
MAIN_SCRIPT="$SCRIPT_SH_DIR/adminpanel.sh"
BOOTSTRAP_LOG_FILE="/var/log/adminantizapret-bootstrap-$(date '+%Y%m%d-%H%M%S').log"
BOOTSTRAP_LOG_KEEP_COUNT=30
MODE="install"

REQUIRED_COMMANDS=(
  apt-get
  dpkg-query
  systemctl
  tee
  find
)

REQUIRED_PACKAGES=(
  apt-utils
  whiptail
  iproute2
  dnsutils
  net-tools
  git
  vnstat
  openssl
  python3
  python3-pip
  python3-venv
  wget
  cron
  ca-certificates
)

DEBIAN_FRONTEND=noninteractive
export DEBIAN_FRONTEND

print_usage() {
  cat <<'EOF'
Использование:
  ./install.sh --install   # полная установка (по умолчанию)
  ./install.sh --check     # проверка окружения без установки
  ./install.sh --help      # показать справку
EOF
}

parse_args() {
  case "${1:-}" in
    ""|"--install")
      MODE="install"
      ;;
    "--check"|"--self-check")
      MODE="check"
      ;;
    "-h"|"--help")
      print_usage
      exit 0
      ;;
    *)
      echo -e "${RED}Ошибка: неизвестный аргумент '$1'${NC}" >&2
      print_usage
      exit 1
      ;;
  esac
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo -e "${RED}Ошибка: не найдена обязательная команда '$cmd'${NC}" >&2
    exit 1
  fi
}

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $*"
}

check_supported_os() {
  if [ ! -r /etc/os-release ]; then
    echo -e "${RED}Ошибка: не удалось определить ОС (нет /etc/os-release).${NC}" >&2
    return 1
  fi

  # shellcheck disable=SC1091
  . /etc/os-release

  local os_id="${ID:-}"
  local os_version_major="${VERSION_ID%%.*}"

  if [ "$os_id" = "ubuntu" ] && [ "$os_version_major" = "24" ]; then
    return 0
  fi

  if [ "$os_id" = "debian" ] && [ "$os_version_major" = "13" ]; then
    return 0
  fi

  echo -e "${RED}Неподдерживаемая ОС: ${PRETTY_NAME:-$os_id}.${NC}" >&2
  echo -e "${YELLOW}Поддерживаются только Ubuntu 24.x и Debian 13.x.${NC}" >&2
  return 1
}

run_preflight_check() {
  local failed=0
  local missing_packages=()
  local status=""

  echo -e "${YELLOW}Режим проверки окружения (--check). Установка не выполняется.${NC}"

  if [ "$(id -u)" -eq 0 ]; then
    echo -e "${GREEN}[✓] Запуск от root${NC}"
  else
    echo -e "${YELLOW}[!] Скрипт запущен не от root. Это допустимо для проверки, но для установки нужен root.${NC}"
  fi

  if check_supported_os; then
    echo -e "${GREEN}[✓] Поддерживаемая ОС: ${PRETTY_NAME}${NC}"
  else
    failed=1
  fi

  echo -e "${YELLOW}Проверка обязательных команд...${NC}"
  for cmd in "${REQUIRED_COMMANDS[@]}"; do
    if command -v "$cmd" >/dev/null 2>&1; then
      echo -e "${GREEN}[✓] $cmd${NC}"
    else
      echo -e "${RED}[✗] $cmd не найден${NC}"
      failed=1
    fi
  done

  if command -v dpkg-query >/dev/null 2>&1; then
    echo -e "${YELLOW}Проверка обязательных пакетов...${NC}"
    for package in "${REQUIRED_PACKAGES[@]}"; do
      status=$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null)
      if [[ "$status" == *"ok installed"* ]]; then
        echo -e "${GREEN}[✓] $package${NC}"
      else
        echo -e "${RED}[✗] $package не установлен${NC}"
        missing_packages+=("$package")
      fi
    done
  else
    echo -e "${RED}[✗] Невозможно проверить пакеты: команда dpkg-query недоступна${NC}"
    failed=1
  fi

  if [ "${#missing_packages[@]}" -gt 0 ]; then
    failed=1
    echo -e "${YELLOW}Для подготовки системы установите:${NC}"
    echo "  apt-get update && apt-get install -y ${missing_packages[*]}"
  fi

  if [ "$failed" -eq 0 ]; then
    echo -e "${GREEN}Проверка пройдена: система готова к установке.${NC}"
    return 0
  fi

  echo -e "${RED}Проверка не пройдена: исправьте проблемы и повторите запуск.${NC}"
  return 1
}

prune_logs_by_pattern() {
  local pattern="$1"
  local keep_count="${2:-20}"
  local i=0
  local files=()

  mapfile -t files < <(ls -1t $pattern 2>/dev/null || true)
  for file in "${files[@]}"; do
    i=$((i + 1))
    if [ "$i" -gt "$keep_count" ]; then
      rm -f -- "$file"
    fi
  done
}

parse_args "$@"

if [ "$MODE" = "check" ]; then
  run_preflight_check
  exit $?
fi

# Проверка root
if [ "$(id -u)" -ne 0 ]; then
  echo -e "${RED}Ошибка: этот скрипт требует прав root!${NC}" >&2
  exit 1
fi

for cmd in "${REQUIRED_COMMANDS[@]}"; do
  require_command "$cmd"
done

if ! check_supported_os; then
  exit 1
fi

# Полный лог bootstrap-установки
prune_logs_by_pattern "/var/log/adminantizapret-bootstrap-*.log" "$BOOTSTRAP_LOG_KEEP_COUNT"

touch "$BOOTSTRAP_LOG_FILE" 2>/dev/null || {
  echo -e "${RED}Ошибка: не удалось создать лог ${BOOTSTRAP_LOG_FILE}${NC}" >&2
  exit 1
}
chmod 600 "$BOOTSTRAP_LOG_FILE" 2>/dev/null || true
exec > >(tee -a "$BOOTSTRAP_LOG_FILE") 2>&1
log "Запуск install.sh"
echo -e "${YELLOW}Лог bootstrap-установки: ${BOOTSTRAP_LOG_FILE}${NC}"

missing_packages=()
for package in "${REQUIRED_PACKAGES[@]}"; do
  status=$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null)
  if [[ "$status" != *"ok installed"* ]]; then
    missing_packages+=("$package")
  fi
done

if [ "${#missing_packages[@]}" -gt 0 ]; then
  echo -e "${YELLOW}Установка необходимых компонентов...${NC}"
  if ! apt-get update; then
    echo -e "${RED}Ошибка: не удалось обновить индексы пакетов (apt-get update).${NC}" >&2
    exit 1
  fi

  if ! apt-get install -y "${missing_packages[@]}"; then
    echo -e "${RED}Ошибка: не удалось установить один или несколько пакетов: ${missing_packages[*]}${NC}" >&2
    exit 1
  fi
fi

require_command git
# Включение и запуск vnstat
echo -e "${YELLOW}Настройка vnStat...${NC}"
if systemctl list-unit-files | grep -q "^vnstat.service"; then
  systemctl enable --now vnstat
    if systemctl is-active --quiet vnstat; then
        echo -e "${GREEN}Служба vnStat успешно запущена и добавлена в автозагрузку.${NC}"
    else
        echo -e "${RED}Ошибка при запуске службы vnStat!${NC}" >&2
    fi
else
    echo -e "${RED}Служба vnStat не найдена в системе.${NC}" >&2
fi
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
log "Bootstrap-этап завершен успешно"
echo -e "${YELLOW}Подробный лог bootstrap-установки: ${BOOTSTRAP_LOG_FILE}${NC}"
exec bash "$MAIN_SCRIPT"
