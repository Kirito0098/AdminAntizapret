#!/bin/bash
# Меню автотестов (pytest) — работает без веб-панели.
# Назначение: модульные тесты для разработки и проверки после обновлений, не ежедневная эксплуатация.

UNIT_TESTS_CLI="$INCLUDE_DIR/unit_tests_cli.py"

_unit_tests_print_purpose() {
    ui_info "Модульные автотесты (pytest) — для разработки и проверки кода после обновлений."
    ui_info "Проверяют отдельные модули панели (CIDR, авторизация, бэкапы, настройки и др.)."
    ui_info "На рабочем сервере запуск не обязателен: падение теста ≠ поломка VPN или панели."
    ui_info "«Общий тест» — диагностика окружения + все pytest; остальные пункты — только pytest."
}

_unit_tests_python() {
    if [ -x "$VENV_PATH/bin/python" ]; then
        printf '%s\n' "$VENV_PATH/bin/python"
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    return 1
}

_unit_tests_check() {
    local py
    if [ ! -d "$INSTALL_DIR/tests" ]; then
        ui_fail "Каталог тестов не найден: $INSTALL_DIR/tests"
        return 1
    fi
    if [ ! -f "$UNIT_TESTS_CLI" ]; then
        ui_fail "Не найден CLI: $UNIT_TESTS_CLI"
        return 1
    fi
    py=$(_unit_tests_python) || {
        ui_fail "Python не найден (нужен venv или python3)"
        return 1
    }
    if [ ! -x "$VENV_PATH/bin/pytest" ] && ! command -v pytest >/dev/null 2>&1; then
        ui_warn "pytest не найден. Установите зависимости: $VENV_PATH/bin/pip install -r requirements.txt"
        return 1
    fi
    return 0
}

_unit_tests_invoke() {
    local py
    py=$(_unit_tests_python) || return 1
    "$py" "$UNIT_TESTS_CLI" "$@"
}

run_unit_tests_all() {
    _unit_tests_check || return 1
    ui_section "Запуск всех автотестов (подробно)"
    _unit_tests_print_purpose
    ui_info "Каталог: $INSTALL_DIR/tests"
    printf "\n"
    _unit_tests_invoke run --all
    local code=$?
    printf "\n"
    if [ "$code" -eq 0 ]; then
        ui_ok "Все тесты прошли успешно"
    else
        ui_fail "Есть упавшие тесты (код выхода: $code)"
    fi
    return "$code"
}

# Общий тест: окружение, модули, права + все pytest (краткий отчёт)
run_unit_tests_summary() {
    local py
    if [ ! -f "$UNIT_TESTS_CLI" ]; then
        ui_fail "Не найден CLI: $UNIT_TESTS_CLI"
        return 1
    fi
    py=$(_unit_tests_python) || {
        ui_fail "Python не найден (нужен venv или python3)"
        return 1
    }
    ui_section "Общий тест системы"
    _unit_tests_print_purpose
    ui_info "Модули, пакеты, права, конфигурация и автотесты…"
    printf "\n"
    INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" VENV_PATH="$VENV_PATH" \
        DB_FILE="$DB_FILE" ANTIZAPRET_INSTALL_DIR="$ANTIZAPRET_INSTALL_DIR" \
        INCLUDE_DIR="$INCLUDE_DIR" \
        "$py" "$UNIT_TESTS_CLI" summary
    local code=$?
    printf "\n"
    if [ "$code" -eq 0 ]; then
        ui_ok "Общий тест пройден"
    else
        ui_fail "Общий тест не пройден — см. сводку выше (код: $code)"
    fi
    return "$code"
}

run_unit_tests_list() {
    _unit_tests_check || return 1
    ui_section "Список автотестов"
    _unit_tests_print_purpose
    printf "\n"
    _unit_tests_invoke list
}

run_unit_tests_by_number() {
    _unit_tests_check || return 1
    printf "\n"
    ui_info "Сначала покажем список с номерами."
    press_any_key
    clear
    _unit_tests_invoke list || return 1
    printf "\n"
    local raw py args=() n
    read -r -p "  Введите номера тестов через пробел или запятую: " raw
    raw=${raw//,/ }
    for n in $raw; do
        case "$n" in
            ''|*[!0-9]*)
                ui_fail "Некорректный номер: $n"
                return 1
                ;;
        esac
        args+=(--index "$n")
    done
    if [ "${#args[@]}" -eq 0 ]; then
        ui_warn "Номера не указаны"
        return 1
    fi
    printf "\n"
    ui_section "Запуск выбранных тестов"
    _unit_tests_invoke run "${args[@]}"
    local code=$?
    printf "\n"
    if [ "$code" -eq 0 ]; then
        ui_ok "Выбранные тесты прошли"
    else
        ui_fail "Есть ошибки (код: $code)"
    fi
    return "$code"
}

show_unit_tests_menu() {
    while true; do
        clear
        _m_top
        _m_title "Автотесты системы"
        _m_sep
        ui_info "Модульные тесты для разработки и проверки после обновлений (не ежедневная эксплуатация)."
        printf "\n"
        _m_sep
        _m_item "1. Общий тест (окружение + pytest)"
        _m_item "2. Запустить все тесты (подробно)"
        _m_item "3. Список тестов (с названиями)"
        _m_item "4. Запустить по номеру из списка"
        _m_sep
        _m_item "0. Назад"
        _m_bot
        printf "\n"
        ui_info "Работает без веб-панели (pytest + venv). Тот же раздел — Настройки → Тесты системы."
        printf "\n"

        read -r -p "  Выберите действие [0-4]: " choice
        case $choice in
        1)
            run_unit_tests_summary
            press_any_key
            ;;
        2)
            run_unit_tests_all
            press_any_key
            ;;
        3)
            run_unit_tests_list
            press_any_key
            ;;
        4)
            run_unit_tests_by_number
            press_any_key
            ;;
        0) break ;;
        *)
            ui_warn "Неверный выбор"
            sleep 1
            ;;
        esac
    done
}
