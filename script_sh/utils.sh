#!/bin/bash

# Инициализация логгирования
init_logging() {
  touch "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
  log "Запуск скрипта"
}

# Логирование
log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Ожидание нажатия клавиши
press_any_key() {
  printf "\n%s\n" "${YELLOW}Нажмите любую клавишу чтобы продолжить...${NC}"
  read -r _
}

# Проверка ошибок
check_error() {
  if [ $? -ne 0 ]; then
    log "Ошибка при выполнении: $1"
    printf "%s\n" "${RED}Ошибка при выполнении: $1${NC}" >&2
    exit 1
  fi
}