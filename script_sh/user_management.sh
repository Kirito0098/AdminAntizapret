#!/bin/bash

# Добавление администратора
add_admin() {
    ui_section "Добавление администратора"

    local username
    while true; do
        read -r -p "  Логин: " username
        username=$(printf '%s' "$username" | tr -d '[:space:]')
        if [ -z "$username" ]; then
            ui_fail "Логин не может быть пустым"
        elif [[ "$username" =~ [^a-zA-Z0-9_-] ]]; then
            ui_fail "Допустимы только буквы, цифры, '-' и '_'"
        else
            break
        fi
    done

    local password password_confirm
    while true; do
        read -r -s -p "  Пароль: " password; printf "\n"
        read -r -s -p "  Повторите пароль: " password_confirm; printf "\n"
        if [ -z "$password" ]; then
            ui_fail "Пароль не может быть пустым"
        elif [ "$password" != "$password_confirm" ]; then
            ui_fail "Пароли не совпадают"
        elif [ "${#password}" -lt 8 ]; then
            ui_fail "Пароль должен содержать минимум 8 символов"
        else
            break
        fi
    done

    printf '%s\n' "$password" | \
        "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py" \
        --add-user "$username" --password-stdin
    check_error "Не удалось добавить администратора"
    ui_ok "Администратор '$username' добавлен"
    press_any_key
}

# Удаление администратора
delete_admin() {
    ui_section "Удаление администратора"

    ui_info "Список администраторов:"
    if ! "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py" --list-users; then
        ui_fail "Не удалось получить список администраторов"
        press_any_key
        return
    fi

    local username
    read -r -p "  Логин для удаления: " username
    if [ -z "$username" ]; then
        ui_fail "Логин не может быть пустым"
        press_any_key
        return
    fi

    if "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py" --delete-user "$username"; then
        ui_ok "Администратор '$username' удалён"
    else
        ui_fail "Не удалось удалить '$username'"
    fi
    press_any_key
}

# Инициализация базы данных
init_db() {
    log "Инициализация базы данных"
    ui_info "Инициализация базы данных..."
    PYTHONIOENCODING=utf-8 "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py"
    check_error "Не удалось инициализировать базу данных"
    ui_ok "База данных инициализирована"
}
