#!/bin/bash

# Добавление администратора
add_admin() {
    echo "${YELLOW}Добавление нового администратора...${NC}"

    while true; do
        read -r -p "Введите логин администратора: " username
        username=$(echo "$username" | tr -d '[:space:]')

        if [ -z "$username" ]; then
            echo "${RED}Логин не может быть пустым!${NC}"
        elif [[ "$username" =~ [^a-zA-Z0-9_-] ]]; then
            echo "${RED}Логин может содержать только буквы, цифры, '-' и '_'!${NC}"
        else
            break
        fi
    done

    # Запрос пароля с проверкой
    while true; do
        read -r -s -p "Введите пароль: " password
        echo
        read -r -s -p "Повторите пароль: " password_confirm
        echo

        if [ -z "$password" ]; then
            echo "${RED}Пароль не может быть пустым!${NC}"
        elif [ "$password" != "$password_confirm" ]; then
            echo "${RED}Пароли не совпадают! Попробуйте снова.${NC}"
        elif [ "${#password}" -lt 8 ]; then
            echo "${RED}Пароль должен содержать минимум 8 символов!${NC}"
        else
            break
        fi
    done

    printf '%s\n' "$password" | "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py" --add-user "$username" --password-stdin
    check_error "Не удалось добавить администратора"
    press_any_key
}

# Удаление администратора
delete_admin() {
    echo "${YELLOW}Удаление администратора...${NC}"

    echo "${YELLOW}Список администраторов:${NC}"
    if ! "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py" --list-users; then
        echo "${RED}Ошибка при получении списка администраторов!${NC}"
        press_any_key
        return
    fi

    read -r -p "Введите логин администратора для удаления: " username
    if [ -z "$username" ]; then
        echo "${RED}Логин не может быть пустым!${NC}"
        press_any_key
        return
    fi

    if "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py" --delete-user "$username"; then
        echo "${GREEN}Администратор '$username' успешно удалён!${NC}"
    else
        echo "${RED}Ошибка при удалении администратора '$username'!${NC}"
    fi
    press_any_key
}

# Инициализация базы данных
init_db() {
    log "Инициализация базы данных"
    echo "${YELLOW}Инициализация базы данных...${NC}"
    PYTHONIOENCODING=utf-8 "$VENV_PATH/bin/python" "$INSTALL_DIR/utils/init_db.py"
    check_error "Не удалось инициализировать базу данных"
}
