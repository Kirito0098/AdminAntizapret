#!/bin/bash

# Инициализация логгирования
init_logging() {
  rotate_if_too_big "$LOG_FILE" "${MAX_MAIN_LOG_SIZE_MB:-20}"
  prune_logs_by_pattern "${LOG_FILE}.*.bak" "${MAX_MAIN_LOG_BACKUPS:-5}"

  touch "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
  log "Запуск скрипта"
}

# Очистка старых логов по шаблону (оставляет только keep_count самых новых)
prune_logs_by_pattern() {
  local pattern="$1"
  local keep_count="${2:-20}"
  local i=0
  local file
  local entry
  local matches=()
  local files=()

  while IFS= read -r file; do
    [ -n "$file" ] && matches+=("$file")
  done < <(compgen -G "$pattern" || true)

  [ "${#matches[@]}" -gt 0 ] || return 0

  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    files+=("${entry#*$'\t'}")
  done < <(
    for file in "${matches[@]}"; do
      printf '%s\t%s\n' "$(stat -c %Y "$file" 2>/dev/null || echo 0)" "$file"
    done | sort -nr
  )

  for file in "${files[@]}"; do
    i=$((i + 1))
    if [ "$i" -gt "$keep_count" ]; then
      rm -f -- "$file"
    fi
  done
}

# Ротация одного лога по размеру
rotate_if_too_big() {
  local file_path="$1"
  local max_mb="${2:-20}"
  local max_bytes=$((max_mb * 1024 * 1024))
  local file_size=0
  local ts

  [ -f "$file_path" ] || return 0
  file_size=$(stat -c%s "$file_path" 2>/dev/null || echo 0)

  if [ "$file_size" -ge "$max_bytes" ]; then
    ts=$(date '+%Y%m%d-%H%M%S')
    mv "$file_path" "${file_path}.${ts}.bak"
  fi
}

# Логирование
log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >>"$LOG_FILE"
}

# Ожидание нажатия клавиши
press_any_key() {
    printf "\n%s\n" "${YELLOW}Нажмите любую клавишу чтобы продолжить...${NC}"
    read -n 1 -s -r -p ""
}

# Проверка ошибок
check_error() {
  if [ $? -ne 0 ]; then
    log "Ошибка при выполнении: $1"
    if [ "${INSTALL_LOG_ACTIVE:-0}" -eq 1 ] && declare -F finish_install_logging >/dev/null 2>&1; then
      finish_install_logging 1
    fi
    printf "%s\n" "${RED}Ошибка при выполнении: $1${NC}" >&2
    exit 1
  fi
}
