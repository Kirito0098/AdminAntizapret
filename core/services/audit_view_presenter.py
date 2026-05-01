from __future__ import annotations

from typing import Any


def _mini_protocol_label(raw_value: str | None) -> str:
    value = (raw_value or "").strip().lower()
    if value in {"openvpn", "ovpn"}:
        return "OpenVPN"
    if value in {"wireguard", "wg"}:
        return "WireGuard"
    if value in {"amneziawg", "amnezia"}:
        return "AmneziaWG"
    return "неизвестно"


def parse_mini_details_kv(raw_details: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in str(raw_details or "").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        if not key:
            continue
        result[key] = value.strip()
    return result


def mini_event_label(event_type: str | None) -> str:
    mapping = {
        "telegram_login_failed": "Вход через Telegram: ошибка",
        "telegram_login_unlinked": "Вход через Telegram: TG ID не привязан",
        "telegram_login_success": "Вход через Telegram: успешно",
        "telegram_mini_login_failed": "Вход в Mini App: ошибка",
        "telegram_mini_login_unlinked": "Вход в Mini App: TG ID не привязан",
        "telegram_mini_login_success": "Вход в Mini App: успешно",
        "mini_send_config": "Отправка конфига в Telegram",
        "mini_send_config_failed": "Отправка конфига: ошибка",
        "mini_check_bot_delivery": "Проверка связи с ботом",
        "mini_check_bot_delivery_failed": "Проверка связи с ботом: ошибка",
        "mini_openvpn_block_toggle": "Изменение статуса OpenVPN-клиента",
        "mini_run_doall": "Применение изменений (doall)",
        "mini_create_openvpn_config": "Создание OpenVPN-конфига",
        "mini_delete_openvpn_config": "Удаление OpenVPN-конфига",
        "mini_create_wireguard_config": "Создание WireGuard/AmneziaWG-конфига",
        "mini_delete_wireguard_config": "Удаление WireGuard/AmneziaWG-конфига",
        "mini_recreate_wireguard_config": "Пересоздание WireGuard/AmneziaWG-конфига",
        "mini_index_action": "Действие с конфигом",
        "mini_settings_port": "Изменение порта панели",
        "mini_settings_nightly": "Изменение настроек ночного рестарта",
        "mini_settings_telegram_auth": "Изменение Telegram-авторизации",
        "mini_restart_service": "Перезапуск службы",
        "mini_antizapret_settings_update": "Изменение настроек Antizapret",
    }
    event_key = str(event_type or "").strip()
    if event_key in mapping:
        return mapping[event_key]
    fallback = event_key.replace("_", " ").strip()
    return fallback.capitalize() if fallback else "Событие"


def mini_event_details_label(
    event_type: str | None,
    details: str | None,
    config_name: str | None = None,
) -> str:
    event_key = str(event_type or "").strip()
    details_value = str(details or "").strip()
    config_value = str(config_name or "").strip()
    detail_map = parse_mini_details_kv(details_value)

    if event_key == "mini_send_config":
        protocol = _mini_protocol_label(detail_map.get("kind"))
        config_label = config_value or "-"
        return f"Тип конфига: {protocol}; конфиг: {config_label}"

    if not details_value:
        return "-"

    if event_key == "mini_send_config_failed":
        return f"Причина: {details_value}"

    if event_key == "mini_check_bot_delivery":
        return "Бот доступен, отправка сообщений работает"

    if event_key == "mini_check_bot_delivery_failed":
        return f"Причина: {details_value}"

    if event_key in {"telegram_login_success", "telegram_mini_login_success"}:
        return "Авторизация подтверждена"

    if event_key in {
        "telegram_login_failed",
        "telegram_login_unlinked",
        "telegram_mini_login_failed",
        "telegram_mini_login_unlinked",
    }:
        return f"Причина: {details_value}"

    if event_key == "mini_openvpn_block_toggle":
        blocked_state = detail_map.get("blocked")
        if blocked_state == "1":
            return "Блокировка включена (доступ клиента отключен)"
        if blocked_state == "0":
            return "Блокировка выключена (доступ клиента включен)"
        return details_value

    if event_key == "mini_settings_port":
        port = detail_map.get("port", "-")
        restart = "да" if detail_map.get("restart") == "1" else "нет"
        return f"Порт: {port}, перезапуск службы: {restart}"

    if event_key == "mini_settings_nightly":
        enabled = "включено" if detail_map.get("enabled") == "1" else "выключено"
        time_value = detail_map.get("time", "-")
        ttl = detail_map.get("ttl", "-")
        touch = detail_map.get("touch", "-")
        return f"Ночной рестарт: {enabled}, время: {time_value}, TTL сессии: {ttl}с, heartbeat: {touch}с"

    if event_key == "mini_settings_telegram_auth":
        bot_name = detail_map.get("bot", "-")
        max_age = detail_map.get("max_age", "-")
        token_changed = "да" if detail_map.get("token_updated") == "1" else "нет"
        return f"Бот: {bot_name}, max age: {max_age}с, токен обновлен: {token_changed}"

    if event_key in {"mini_restart_service", "mini_run_doall"}:
        task_id = detail_map.get("task_id")
        if task_id:
            return f"Запущена фоновая задача: {task_id}"
        return "Запущена фоновая задача"

    if event_key == "mini_antizapret_settings_update":
        changes = detail_map.get("changes", "-")
        keys = detail_map.get("keys", "-")
        return f"Изменено параметров: {changes}; ключи: {keys.replace(',', ', ')}"

    if event_key in {
        "mini_create_openvpn_config",
        "mini_delete_openvpn_config",
        "mini_create_wireguard_config",
        "mini_delete_wireguard_config",
        "mini_recreate_wireguard_config",
        "mini_index_action",
    }:
        cert_days = detail_map.get("cert_days")
        if cert_days and cert_days != "-":
            return f"Срок сертификата: {cert_days} дней"
        return "Действие выполнено через Mini App"

    return details_value


def build_telegram_mini_audit_view(rows: list[Any] | None) -> list[dict[str, Any]]:
    view_rows: list[dict[str, Any]] = []
    for row in rows or []:
        event_type = str(getattr(row, "event_type", "") or "").strip()
        details_raw = str(getattr(row, "details", "") or "").strip()
        config_name = str(getattr(row, "config_name", "") or "").strip()
        base_event_label = mini_event_label(event_type)
        event_display = f"{base_event_label}: {config_name}" if config_name else base_event_label
        view_rows.append(
            {
                "created_at": row.created_at,
                "actor_username": row.actor_username,
                "telegram_id": row.telegram_id,
                "event_type": event_type,
                "event_label": base_event_label,
                "event_display": event_display,
                "details_raw": details_raw,
                "details_label": mini_event_details_label(event_type, details_raw, config_name),
            }
        )
    return view_rows


def resolve_user_action_source(event_type: str | None, details: str | None) -> tuple[str, str]:
    event_key = str(event_type or "").strip().lower()
    detail_map = parse_mini_details_kv(details)
    via = str(detail_map.get("via") or "").strip().lower()
    channel = str(detail_map.get("channel") or "").strip().lower()

    if event_key.startswith("miniapp:") or via in {"tg-mini", "tg_mini", "miniapp", "mini-app"}:
        return "miniapp", "📱 MiniApp"

    if channel in {"qr_one_time", "qr", "one_time"}:
        return "qr", "🔗 QR"

    if channel in {"public", "public_download"}:
        return "public", "🌍 Public"

    if channel in {"api", "rest", "webapi"}:
        return "api", "🔌 API"

    if channel in {"web", "panel", "ui"}:
        return "web", "🖥 Панель"

    return "web", "🖥 Панель"


def user_action_event_label(event_type: str | None) -> str:
    mapping = {
        "config_create": "Создание конфига",
        "config_delete": "Удаление конфига",
        "config_recreate": "Пересоздание конфига",
        "config_action": "Действие с конфигом",
        "config_download": "Скачивание конфига",
        "config_send_telegram": "Отправка конфига в Telegram",
        "telegram_bot_delivery_check": "Проверка связи с Telegram-ботом",
        "openvpn_client_block_toggle": "Изменение статуса OpenVPN-клиента",
        "settings_port_update": "Изменение порта панели",
        "settings_qr_ttl_update": "Изменение TTL одноразовой ссылки",
        "settings_qr_max_downloads_update": "Изменение лимита скачиваний QR-ссылки",
        "settings_qr_pin_clear": "Очистка PIN одноразовой ссылки",
        "settings_qr_pin_update": "Изменение PIN одноразовой ссылки",
        "settings_public_download_toggle": "Переключение публичного скачивания",
        "settings_nightly_update": "Изменение настроек ночного рестарта",
        "settings_telegram_auth_update": "Изменение Telegram-авторизации",
        "settings_user_create": "Создание пользователя",
        "settings_user_telegram_update": "Изменение Telegram ID пользователя",
        "settings_user_delete": "Удаление пользователя",
        "settings_user_role_update": "Изменение роли пользователя",
        "settings_user_password_update": "Смена пароля пользователя",
        "settings_ip_add": "Добавление IP-ограничения",
        "settings_ip_remove": "Удаление IP-ограничения",
        "settings_ip_clear": "Сброс IP-ограничений",
        "settings_ip_bulk_enable": "Массовое включение IP-ограничений",
        "settings_ip_add_from_file": "Добавление IP из файла",
        "settings_ip_file_toggle": "Изменение статуса IP-файла",
        "settings_restart_service": "Запуск перезапуска службы",
        "settings_run_doall": "Применение изменений (doall)",
        "settings_viewer_access_grant": "Выдача доступа viewer",
        "settings_viewer_access_revoke": "Отзыв доступа viewer",
        "settings_antizapret_update": "Изменение настроек Antizapret",
    }
    event_key = str(event_type or "").strip()

    if event_key.startswith("miniapp:"):
        original_event = event_key[8:]
        return mini_event_label(original_event)

    if event_key in mapping:
        return mapping[event_key]
    fallback = event_key.replace("_", " ").strip()
    return fallback.capitalize() if fallback else "Событие"


def user_action_event_display(
    event_type: str | None,
    target_name: str | None,
    target_type: str | None,
    details: str | None,
) -> str:
    event_key = str(event_type or "").strip()
    target_value = str(target_name or "").strip()
    target_kind = str(target_type or "").strip()
    details_value = str(details or "").strip()
    detail_map = parse_mini_details_kv(details_value)

    if event_key.startswith("miniapp:"):
        original_event = event_key[8:]
        return mini_event_details_label(original_event, details_value, target_value)

    if event_key == "settings_qr_max_downloads_update":
        value = detail_map.get("value")
        if value:
            return f"Изменение лимита скачиваний QR-ссылки: увеличение до {value}"
        return "Изменение лимита скачиваний QR-ссылки"

    if event_key == "settings_qr_ttl_update":
        value = detail_map.get("value")
        if value:
            return f"Изменение TTL одноразовой ссылки: до {value} секунд"
        return "Изменение TTL одноразовой ссылки"

    if event_key == "settings_port_update":
        value = detail_map.get("value")
        if value:
            return f"Изменение порта панели: до {value}"
        return "Изменение порта панели"

    if event_key == "settings_public_download_toggle":
        enabled = detail_map.get("enabled")
        if enabled == "1":
            return "Публичное скачивание: включено"
        if enabled == "0":
            return "Публичное скачивание: выключено"
        return "Переключение публичного скачивания"

    if event_key == "config_download":
        if target_value:
            return f"Скачивание конфига: {target_value}"
        return "Скачивание конфига"

    if event_key == "config_send_telegram":
        if target_value:
            return f"Отправка конфига в Telegram: {target_value}"
        return "Отправка конфига в Telegram"

    if event_key == "telegram_bot_delivery_check":
        result = str(detail_map.get("result") or "").strip().lower()
        if result == "ok":
            return "Проверка связи с Telegram-ботом: успешно"
        if result == "failed":
            return "Проверка связи с Telegram-ботом: ошибка"
        return "Проверка связи с Telegram-ботом"

    if event_key == "openvpn_client_block_toggle":
        blocked_state = str(detail_map.get("blocked") or "").strip()
        if blocked_state == "1":
            return f"OpenVPN-клиент: блокировка включена ({target_value or '-'})"
        if blocked_state == "0":
            return f"OpenVPN-клиент: блокировка выключена ({target_value or '-'})"
        if target_value:
            return f"Изменение статуса OpenVPN-клиента: {target_value}"
        return "Изменение статуса OpenVPN-клиента"

    if event_key == "settings_run_doall":
        task_id = str(detail_map.get("task_id") or "").strip()
        if task_id:
            return f"Применение изменений (doall): задача {task_id}"
        return "Применение изменений (doall)"

    if event_key in {"config_create", "config_delete", "config_recreate", "config_action"} and target_value:
        return f"{user_action_event_label(event_key)}: {target_value}"

    if event_key in {
        "settings_user_create",
        "settings_user_delete",
        "settings_user_role_update",
        "settings_user_password_update",
        "settings_user_telegram_update",
    } and target_value:
        return f"{user_action_event_label(event_key)}: {target_value}"

    if target_value and target_kind in {"ip_restriction", "ip_file"}:
        return f"{user_action_event_label(event_key)}: {target_value}"

    return user_action_event_label(event_key)


def build_user_action_audit_view(rows: list[Any] | None) -> list[dict[str, Any]]:
    view_rows: list[dict[str, Any]] = []
    for row in rows or []:
        event_type = str(getattr(row, "event_type", "") or "").strip()
        target_type = str(getattr(row, "target_type", "") or "").strip()
        target_name = str(getattr(row, "target_name", "") or "").strip()
        target_display = target_name or "-"
        if target_type:
            target_display = f"{target_display} ({target_type})" if target_name else target_type

        source_kind, source_label = resolve_user_action_source(event_type, getattr(row, "details", None))
        is_miniapp = source_kind == "miniapp"

        view_rows.append(
            {
                "created_at": row.created_at,
                "actor_username": row.actor_username,
                "event_type": event_type,
                "event_label": user_action_event_label(event_type),
                "event_display": user_action_event_display(
                    event_type,
                    target_name,
                    target_type,
                    getattr(row, "details", None),
                ),
                "target_display": target_display,
                "status": str(getattr(row, "status", "") or "").strip() or "success",
                "details": str(getattr(row, "details", "") or "").strip() or "-",
                "remote_addr": getattr(row, "remote_addr", None),
                "is_miniapp": is_miniapp,
                "source_kind": source_kind,
                "source_label": source_label,
            }
        )
    return view_rows
