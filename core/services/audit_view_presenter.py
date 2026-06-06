from __future__ import annotations

import json as _json
import re
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


def _parse_arrow_change(details: str | None) -> tuple[str, str] | None:
    text = str(details or "").strip()
    if "→" not in text:
        return None
    old_value, new_value = text.split("→", 1)
    return old_value.strip(), new_value.strip()


def _humanize_cron(cron_expr: str) -> str:
    parts = str(cron_expr or "").strip().split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        minute, hour = int(parts[0]), int(parts[1])
        return f"ежедневно в {hour:02d}:{minute:02d}"
    return str(cron_expr or "").strip()


def _format_nightly_update_details(details: str | None) -> str:
    raw = str(details or "").strip()
    if not raw:
        return "Ночной рестарт: настройки изменены"

    enabled_match = re.search(r"enabled=(\S+)", raw)
    cron_match = re.search(r"cron=(.+?)\s+ttl=", raw)
    ttl_match = re.search(r"ttl=(\d+)", raw)
    touch_match = re.search(r"touch=(\d+)", raw)

    enabled_raw = (enabled_match.group(1) if enabled_match else "").lower()
    if enabled_raw in {"вкл", "1", "true", "yes"}:
        enabled_text = "включён"
    elif enabled_raw in {"выкл", "0", "false", "no"}:
        enabled_text = "выключен"
    else:
        enabled_text = "изменён"

    parts = [f"Ночной рестарт {enabled_text}"]
    if cron_match:
        parts.append(f"по расписанию {_humanize_cron(cron_match.group(1))}")
    if ttl_match:
        parts.append(f"TTL сессии {ttl_match.group(1)} с")
    if touch_match:
        parts.append(f"интервал активности {touch_match.group(1)} с")
    return ", ".join(parts)


_BACKUP_COMPONENT_LABELS_RU = {
    "db": "базы SQLite",
    "env": "файл .env",
    "data": "файлы data/",
}

_ROLE_LABELS_RU = {
    "admin": "администратор",
    "viewer": "наблюдатель",
}


def _format_backup_interval_ru(interval_token: str) -> str:
    raw = str(interval_token or "").strip().lower()
    if raw in {"1", "1d"}:
        return "каждый день"
    if raw.endswith("d") and raw[:-1].isdigit():
        days = int(raw[:-1])
        if days == 7:
            return "каждые 7 дней"
        if days == 30:
            return "каждые 30 дней"
        return f"каждые {days} дн."
    return raw or "—"


def _format_backup_components_ru(components_csv: str) -> str:
    parts = []
    for item in str(components_csv or "").split(","):
        key = item.strip().lower()
        if not key:
            continue
        parts.append(_BACKUP_COMPONENT_LABELS_RU.get(key, key))
    return ", ".join(parts) if parts else "—"


def _format_backup_settings_details_ru(details: str | None) -> str:
    raw = str(details or "").strip()
    if not raw:
        return "Настройки авто-бэкапа изменены"

    enabled_match = re.search(r"enabled=(\S+)", raw)
    interval_match = re.search(r"interval=(\S+)", raw)
    time_match = re.search(r"time=(\S+)", raw)
    components_match = re.search(r"components=([^\s]+)", raw)
    tg_match = re.search(r"tg=(\S+)", raw)
    admins_match = re.search(r"admins=(\S+)", raw)

    enabled_raw = (enabled_match.group(1) if enabled_match else "").lower()
    if enabled_raw in {"вкл", "1", "true", "yes"}:
        enabled_text = "включён"
    elif enabled_raw in {"выкл", "0", "false", "no"}:
        enabled_text = "выключен"
    else:
        enabled_text = "изменён"

    interval_text = _format_backup_interval_ru(interval_match.group(1) if interval_match else "")
    time_text = time_match.group(1) if time_match else "—"
    components_text = _format_backup_components_ru(
        components_match.group(1) if components_match else ""
    )

    tg_raw = (tg_match.group(1) if tg_match else "").lower()
    if tg_raw in {"вкл", "1", "true", "yes"}:
        tg_text = "включена"
    elif tg_raw in {"выкл", "0", "false", "no"}:
        tg_text = "выключена"
    else:
        tg_text = "не изменена"

    admins_text = admins_match.group(1) if admins_match else "—"
    if admins_text == "-":
        admins_text = "не выбраны"

    return (
        f"Авто-бэкап {enabled_text}, интервал {interval_text}, время {time_text}, "
        f"состав: {components_text}, отправка в Telegram {tg_text}, "
        f"получатели: {admins_text}"
    )


def _detail_int(detail_map: dict[str, str], key: str) -> int:
    try:
        return int(str(detail_map.get(key) or "0").strip())
    except ValueError:
        return 0


def _format_games_sync_tg_line(event_key: str, details: str | None) -> str | None:
    detail_map = parse_mini_details_kv(details)
    key = str(event_key or "").strip()

    if key == "settings_cidr_games_routes_sync":
        include_games = _detail_int(detail_map, "include_games")
        include_cidrs = _detail_int(detail_map, "include_cidrs")
        include_domains = _detail_int(detail_map, "include_domains")
        exclude_games = _detail_int(detail_map, "exclude_games")
        exclude_cidrs = _detail_int(detail_map, "exclude_cidrs")
        exclude_domains = _detail_int(detail_map, "exclude_domains")
        include_overlap = _detail_int(detail_map, "include_overlap")
        exclude_overlap = _detail_int(detail_map, "exclude_overlap")
        if include_games == 0 and exclude_games == 0 and include_cidrs == 0 and exclude_cidrs == 0:
            return "Игровые маршруты очищены"
        parts = []
        if include_games > 0 or include_cidrs > 0:
            chunk = f"VPN: {include_games} игр, {include_cidrs} CIDR"
            if include_domains > 0:
                chunk += f", {include_domains} доменов"
            if include_overlap > 0:
                chunk += f", пересечений {include_overlap}"
            parts.append(chunk)
        if exclude_games > 0 or exclude_cidrs > 0:
            chunk = f"DIRECT: {exclude_games} игр, {exclude_cidrs} CIDR"
            if exclude_domains > 0:
                chunk += f", {exclude_domains} доменов"
            if exclude_overlap > 0:
                chunk += f", пересечений {exclude_overlap}"
            parts.append(chunk)
        return " · ".join(parts) if parts else "Игровые маршруты обновлены"

    scope = "exclude" if key == "settings_cidr_games_exclude_sync" else "include"
    scope_label = "DIRECT" if scope == "exclude" else "VPN"
    games = _detail_int(detail_map, "selected_games")
    domains = _detail_int(detail_map, "domains")
    cidrs = _detail_int(detail_map, "cidrs")
    overlap = _detail_int(detail_map, "overlap")
    if games == 0 and cidrs == 0 and domains == 0:
        return f"{scope_label}: фильтры очищены"
    parts = [f"{scope_label}: {games} игр", f"{cidrs} CIDR"]
    if domains > 0:
        parts.append(f"{domains} доменов")
    if overlap > 0:
        parts.append(f"пересечений {overlap}")
    return ", ".join(parts)


def _humanize_raw_details_for_tg(details: str | None) -> str | None:
    """Translate common technical audit detail strings to Russian for Telegram."""
    text = str(details or "").strip()
    if not text:
        return None
    if "→" in text:
        return text

    lowered = text.lower()
    replacements = {
        "invalid_credentials": "неверный логин или пароль",
        "verification_failed": "ошибка проверки подписи Telegram",
        "mini_verification_failed": "ошибка проверки данных Mini App",
        "telegram_id_not_bound": "Telegram ID не привязан",
        "manual_create": "ручное создание",
        "manual_unblock": "ручная разблокировка",
        "temp_block": "временная блокировка",
        "permanent_block": "постоянная блокировка",
        "unblock": "разблокировка",
        "success": "успешно",
        "failed": "ошибка",
        "warning": "предупреждение",
        "web_login": "вход через веб",
    }
    for src, dst in replacements.items():
        if lowered == src:
            return dst

    if "=" in text and re.search(r"\b(enabled|interval|components|cron|ttl|touch)=\S+", text):
        if "components=" in text and "interval=" in text:
            return _format_backup_settings_details_ru(text)
        if "cron=" in text or "enabled=" in text:
            return _format_nightly_update_details(text)

    return None


def _format_telegram_auth_details_ru(details: str | None) -> str:
    detail_map = parse_mini_details_kv(str(details or ""))
    source_raw = str(detail_map.get("source") or "").strip().lower()
    source_map = {
        "mini_app": "мини-приложение",
        "miniapp": "мини-приложение",
        "web_settings": "веб-настройки",
        "web": "веб-панель",
        "panel": "веб-панель",
    }
    source = source_map.get(source_raw, "панель")
    changed = str(detail_map.get("changed") or "—").replace(",", ", ")
    status = "успешно" if str(detail_map.get("status") or "") == "success" else "с ошибкой"
    token_changed = "да" if detail_map.get("token_updated") == "1" else "нет"
    max_age = detail_map.get("max_age", "—")
    return (
        f"источник: {source}; статус: {status}; "
        f"макс. возраст данных: {max_age} с; токен обновлён: {token_changed}; "
        f"изменено: {changed}"
    )


def mini_event_label(event_type: str | None) -> str:
    mapping = {
        "telegram_login_failed": "Вход через Telegram: ошибка",
        "telegram_login_unlinked": "Вход через Telegram: TG ID не привязан",
        "telegram_login_success": "Вход через Telegram: успешно",
        "telegram_mini_login_failed": "Вход в мини-приложение: ошибка",
        "telegram_mini_login_unlinked": "Вход в мини-приложение: TG ID не привязан",
        "telegram_mini_login_success": "Вход в мини-приложение: успешно",
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


def _translate_auth_failure_detail(raw: str) -> str:
    """Translate raw English auth failure detail strings to Russian."""
    v = raw.strip().lower()
    if not raw.strip():
        return "Причина не указана"
    if "telegram_id_not_bound" in v or "not_bound" in v:
        return "Telegram ID не привязан ни к одному пользователю"
    if "verification_failed" in v or "некорректные данные" in v:
        return "Ошибка проверки подписи Telegram"
    if "mini_verification_failed" in v:
        return "Ошибка проверки данных Mini App"
    if "invalid_credentials" in v:
        return "Неверный логин или пароль"
    if "invalid_hash" in v or "hash" in v:
        return "Недействительная подпись запроса"
    if "expired" in v:
        return "Срок действия авторизации истёк"
    return raw


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
        return _translate_auth_failure_detail(details_value)

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
        source_raw = str(detail_map.get("source") or "").strip().lower()
        source_map = {
            "mini_app": "мини-приложение",
            "miniapp": "мини-приложение",
            "web_settings": "веб-настройки",
            "web": "веб-панель",
            "panel": "веб-панель",
        }
        source = source_map.get(source_raw, "панель")
        changed = str(detail_map.get("changed") or "—").replace(",", ", ")
        status = "успешно" if str(detail_map.get("status") or "") == "success" else "с ошибкой"
        return (
            f"Источник: {source}; статус: {status}; бот: {bot_name}; "
            f"макс. возраст данных: {max_age} с; токен обновлён: {token_changed}; "
            f"изменено: {changed}"
        )

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
        detail_map = parse_mini_details_kv(details_raw)
        source_kind = str(detail_map.get("source") or "").strip().lower()
        if source_kind in {"mini_app", "miniapp"}:
            source_label = "Мини-приложение"
            source_kind = "miniapp"
        elif source_kind == "web_settings":
            source_label = "Веб-настройки"
            source_kind = "web"
        else:
            source_label = "Система"
            source_kind = "system"
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
                "source_kind": source_kind,
                "source_label": source_label,
            }
        )
    return view_rows


def resolve_user_action_source(event_type: str | None, details: str | None) -> tuple[str, str]:
    event_key = str(event_type or "").strip().lower()
    detail_map = parse_mini_details_kv(details)
    via = str(detail_map.get("via") or "").strip().lower()
    source = str(detail_map.get("source") or "").strip().lower()
    channel = str(detail_map.get("channel") or "").strip().lower()

    if event_key.startswith("miniapp:") or via in {"tg-mini", "tg_mini", "miniapp", "mini-app"}:
        return "miniapp", "📱 Мини-приложение"
    if source in {"mini_app", "miniapp"}:
        return "miniapp", "📱 Мини-приложение"
    if source in {"web_settings", "web", "panel"}:
        return "web", "🖥 Панель"

    if channel in {"qr_one_time", "qr", "one_time"}:
        return "qr", "🔗 QR"

    if channel in {"public", "public_download"}:
        return "public", "🌍 Публичное скачивание"

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
        "settings_ip_add_temp": "Временный доступ по IP",
        "settings_ip_remove_temp": "Удаление временного IP",
        "settings_ip_scanner_block": "Защита от сканеров (IP)",
        "settings_ip_scanner_bans_clear": "Сброс банов сканеров",
        "settings_ip_scanner_unban": "Разблокировка IP сканера",
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
        # Auth
        "login_failed": "Неудачная попытка входа",
        # Antizapret / обновления
        "settings_antifilter_refresh": "Обновление списков Antizapret",
        # CIDR
        "settings_cidr_update_queued": "Обновление CIDR-файлов",
        "settings_cidr_rollback_queued": "Откат CIDR-файлов",
        "settings_cidr_db_refresh_queued": "Обновление базы CIDR",
        "settings_cidr_db_clear": "Очистка базы CIDR",
        "settings_cidr_generate_from_db": "Генерация CIDR из базы",
        "settings_cidr_games_sync": "Синхронизация игровых хостов",
        "settings_cidr_games_exclude_sync": "Синхронизация игровых хостов (DIRECT)",
        "settings_cidr_games_routes_sync": "Синхронизация игровых маршрутов",
        "settings_cidr_total_limit_update": "Изменение лимита CIDR",
        "settings_cidr_preset_create": "Создание пресета CIDR",
        "settings_cidr_preset_update": "Изменение пресета CIDR",
        "settings_cidr_preset_delete": "Удаление пресета CIDR",
        "settings_cidr_preset_reset": "Сброс пресета CIDR до базового",
        # IP
        "settings_ip_files_sync": "Синхронизация IP-файлов",
        # Тесты
        "settings_tests_run": "Запуск тестов панели",
        "settings_backup_update": "Изменение настроек бэкапов",
        "settings_backup_create": "Создание бэкапа",
        "settings_backup_test_telegram": "Бэкап и отправка в Telegram",
        "settings_backup_restore": "Восстановление из бэкапа",
        "settings_backup_delete": "Удаление бэкапа",
        "settings_user_tg_notify_update": "Изменение уведомлений в Telegram",
        "settings_monitor_update": "Изменение мониторинга ресурсов",
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

    label = user_action_event_label(event_key)

    # ── MiniApp events ──────────────────────────────────────────────────
    if event_key.startswith("miniapp:"):
        original_event = event_key[8:]
        # For config actions append config name
        if target_value and original_event in {
            "mini_send_config", "mini_create_openvpn_config", "mini_delete_openvpn_config",
            "mini_create_wireguard_config", "mini_delete_wireguard_config",
            "mini_recreate_wireguard_config", "mini_index_action",
        }:
            return f"{label}: {target_value}"
        # For auth failures/unlinked — translate the reason into clean Russian
        if original_event in {
            "telegram_login_failed", "telegram_mini_login_failed",
            "telegram_login_unlinked", "telegram_mini_login_unlinked",
        }:
            reason = _translate_auth_failure_detail(details_value)
            return f"{label} — {reason}"
        return label

    # ── QR settings ─────────────────────────────────────────────────────
    if event_key == "settings_qr_max_downloads_update":
        arrow = _parse_arrow_change(details_value)
        if arrow:
            return f"Лимит скачиваний QR: с {arrow[0]} до {arrow[1]}"
        value = detail_map.get("value")
        return f"Лимит скачиваний QR-ссылки изменён до {value}" if value else label

    if event_key == "settings_qr_ttl_update":
        arrow = _parse_arrow_change(details_value)
        if arrow:
            old_val, new_val = arrow
            new_clean = new_val.rstrip("с").strip()
            old_clean = old_val.rstrip("с").strip()
            return f"TTL QR-ссылки: с {old_clean} до {new_clean} с"
        value = detail_map.get("value")
        return f"TTL одноразовой ссылки изменён до {value} сек." if value else label

    if event_key == "settings_qr_pin_update":
        length = detail_map.get("length")
        if length:
            return f"PIN QR-ссылки обновлён (длина {length} цифр)"
        return "PIN одноразовой ссылки обновлён"

    if event_key == "settings_qr_pin_clear":
        return "PIN одноразовой ссылки сброшен"

    # ── Порт ────────────────────────────────────────────────────────────
    if event_key == "settings_port_update":
        arrow = _parse_arrow_change(details_value)
        if arrow:
            return f"Порт панели изменён: с {arrow[0]} на {arrow[1]}"
        value = detail_map.get("value")
        return f"Порт панели изменён на {value}" if value else label

    # ── Публичное скачивание ────────────────────────────────────────────
    if event_key == "settings_public_download_toggle":
        enabled = detail_map.get("enabled")
        if enabled == "1":
            return "Публичное скачивание конфигов: включено"
        if enabled == "0":
            return "Публичное скачивание конфигов: выключено"
        return label

    # ── Конфиги ─────────────────────────────────────────────────────────
    if event_key == "config_download" and target_value:
        return f"Скачивание конфига: {target_value}"

    if event_key == "config_send_telegram" and target_value:
        return f"Отправка конфига в Telegram: {target_value}"

    if event_key in {"config_create", "config_delete", "config_recreate", "config_action"} and target_value:
        return f"{label}: {target_value}"

    # ── Telegram-бот ────────────────────────────────────────────────────
    if event_key == "telegram_bot_delivery_check":
        result = str(detail_map.get("result") or "").strip().lower()
        if result == "ok":
            return "Проверка связи с Telegram-ботом: соединение в норме"
        if result == "failed":
            return "Проверка связи с Telegram-ботом: ошибка соединения"
        return label

    # ── OpenVPN-клиент ──────────────────────────────────────────────────
    if event_key == "openvpn_client_block_toggle":
        blocked_state = str(detail_map.get("blocked") or "").strip()
        client = target_value or "—"
        if blocked_state == "1":
            return f"Клиент {client}: доступ заблокирован"
        if blocked_state == "0":
            return f"Клиент {client}: доступ разблокирован"
        return f"{label}: {client}" if target_value else label

    # ── Применение изменений ────────────────────────────────────────────
    if event_key == "settings_run_doall":
        task_id = str(detail_map.get("task_id") or "").strip()
        return f"Применение изменений: задача {task_id}" if task_id else "Применение изменений (doall)"

    if event_key == "settings_restart_service":
        svc = target_value or "служба"
        return f"Запуск перезапуска: {svc}"

    # ── Пользователи ────────────────────────────────────────────────────
    if event_key in {
        "settings_user_create", "settings_user_delete",
        "settings_user_role_update", "settings_user_password_update",
        "settings_user_telegram_update",
    } and target_value:
        return f"{label}: {target_value}"

    # ── IP-ограничения ──────────────────────────────────────────────────
    if event_key == "settings_ip_clear":
        return "Все IP-ограничения сброшены"

    if event_key == "settings_ip_bulk_enable":
        return "IP-ограничения: массовое включение"

    if event_key == "settings_ip_add_from_file":
        return f"IP-адреса добавлены из файла: {target_value}" if target_value else label

    if event_key == "settings_ip_files_sync":
        synced = detail_map.get("synced", "")
        updated = detail_map.get("updated", "")
        parts = []
        if synced:
            parts.append(f"синхронизировано: {synced}")
        if updated:
            parts.append(f"обновлено: {updated}")
        suffix = "; ".join(parts)
        return f"Синхронизация IP-файлов — {suffix}" if suffix else "Синхронизация IP-файлов выполнена"

    if target_value and target_kind in {"ip_restriction", "ip_file"}:
        return f"{label}: {target_value}"

    # ── Ночной рестарт ──────────────────────────────────────────────────
    if event_key == "settings_nightly_update":
        if "cron=" in details_value or "enabled=" in details_value:
            return _format_nightly_update_details(details_value)
        enabled = detail_map.get("enabled")
        if enabled == "1":
            return "Ночной рестарт: включён"
        if enabled == "0":
            return "Ночной рестарт: выключен"
        return label

    # ── Viewer-доступ ───────────────────────────────────────────────────
    if event_key in {"settings_viewer_access_grant", "settings_viewer_access_revoke"} and target_value:
        return f"{label}: {target_value}"

    # ── CIDR ────────────────────────────────────────────────────────────
    if event_key == "settings_cidr_total_limit_update":
        value = detail_map.get("value")
        return f"Лимит CIDR изменён: {value} маршрутов" if value else label

    if event_key == "settings_cidr_games_sync":
        formatted = _format_games_sync_tg_line(event_key, details)
        if formatted:
            return formatted
        games = detail_map.get("selected_games", "")
        domains = detail_map.get("domains", "")
        cidrs = detail_map.get("cidrs", "")
        parts = []
        if _detail_int(detail_map, "selected_games") > 0:
            parts.append(f"игр: {_detail_int(detail_map, 'selected_games')}")
        if _detail_int(detail_map, "domains") > 0:
            parts.append(f"доменов: {_detail_int(detail_map, 'domains')}")
        if _detail_int(detail_map, "cidrs") > 0:
            parts.append(f"CIDR: {_detail_int(detail_map, 'cidrs')}")
        suffix = ", ".join(parts)
        return f"Синхронизация игровых хостов — {suffix}" if suffix else "Синхронизация игровых хостов — фильтры очищены"

    if event_key in {"settings_cidr_games_exclude_sync", "settings_cidr_games_routes_sync"}:
        formatted = _format_games_sync_tg_line(event_key, details)
        if formatted:
            return formatted

    if event_key in {
        "settings_cidr_preset_create", "settings_cidr_preset_update",
        "settings_cidr_preset_delete", "settings_cidr_preset_reset",
    } and target_value:
        return f"{label}: {target_value}"

    if event_key in {
        "settings_cidr_update_queued", "settings_cidr_rollback_queued",
        "settings_cidr_db_refresh_queued", "settings_cidr_db_clear",
        "settings_cidr_generate_from_db",
    }:
        scope = target_value if target_value and target_value != "all" else "все файлы"
        return f"{label} ({scope})"

    # ── Antizapret ──────────────────────────────────────────────────────
    if event_key == "settings_antifilter_refresh":
        return "Обновление списков Antizapret: запущена загрузка"

    if event_key == "settings_antizapret_update":
        return label

    # ── Тесты ───────────────────────────────────────────────────────────
    if event_key == "settings_tests_run":
        count = detail_map.get("count", "")
        if count == "all":
            return "Запуск всех тестов панели"
        if count:
            return f"Запуск тестов панели: {count} тестов"
        return "Запуск тестов панели"

    # ── Вход ────────────────────────────────────────────────────────────
    if event_key == "login_failed":
        return f"Неудачная попытка входа: пользователь «{target_value}»" if target_value else label

    return label


def user_action_tg_action_line(
    event_key: str,
    *,
    details: str | None = None,
    target_name: str | None = None,
    target_type: str | None = None,
) -> str:
    """Human-readable Russian action line for Telegram settings notifications."""
    key = str(event_key or "").strip()
    details_value = str(details or "").strip()
    target_value = str(target_name or "").strip()

    if key == "settings_nightly_update":
        return _format_nightly_update_details(details_value)

    if key == "settings_port_update":
        arrow = _parse_arrow_change(details_value)
        if arrow:
            return f"Порт панели: с {arrow[0]} на {arrow[1]}"

    if key == "settings_qr_ttl_update":
        arrow = _parse_arrow_change(details_value)
        if arrow:
            old_val, new_val = arrow
            new_clean = new_val.rstrip("с").strip()
            old_clean = old_val.rstrip("с").strip()
            return f"TTL QR-ссылки: с {old_clean} до {new_clean} с"

    if key == "settings_qr_max_downloads_update":
        arrow = _parse_arrow_change(details_value)
        if arrow:
            return f"Лимит скачиваний QR: с {arrow[0]} до {arrow[1]}"

    if key == "settings_qr_pin_update":
        length = parse_mini_details_kv(details_value).get("length")
        if length:
            return f"PIN QR-ссылки обновлён (длина {length} цифр)"
        return "PIN QR-ссылки обновлён"

    if key == "settings_qr_pin_clear":
        return "PIN QR-ссылок сброшен"

    if key == "settings_telegram_auth_update" and details_value:
        return f"Изменены настройки авторизации Telegram: {_format_telegram_auth_details_ru(details_value)}"

    if key == "settings_user_password_update":
        return "Пароль пользователя изменён"

    if key == "settings_user_role_update" and "→" in details_value:
        old_val, new_val = _parse_arrow_change(details_value) or ("—", "—")
        user = target_value or "пользователь"
        old_ru = _ROLE_LABELS_RU.get(old_val.lower(), old_val)
        new_ru = _ROLE_LABELS_RU.get(new_val.lower(), new_val)
        return f"Роль пользователя {user}: с «{old_ru}» на «{new_ru}»"

    if key == "settings_backup_update":
        return _format_backup_settings_details_ru(details_value)

    if key == "settings_backup_create":
        return "Запущено ручное создание резервной копии"

    if key == "settings_backup_test_telegram":
        return "Запущено создание бэкапа и отправка архивов в Telegram"

    if key == "settings_backup_restore":
        archive = target_value if target_value and target_value != "manual_create" else ""
        if archive:
            return f"Восстановление из архива «{archive}» поставлено в очередь"
        return "Восстановление из бэкапа поставлено в очередь"

    if key == "settings_backup_delete":
        if target_value:
            return f"Удалён бэкап «{target_value}»"
        return "Удалён файл бэкапа"

    if key == "settings_user_tg_notify_update":
        return f"Обновлены подписки на уведомления пользователя «{target_value}»" if target_value else "Обновлены подписки на уведомления"

    if key == "settings_monitor_update" and details_value:
        humanized = _humanize_raw_details_for_tg(details_value)
        return humanized or f"Мониторинг ресурсов: {details_value}"

    if key == "settings_user_telegram_update" and "→" in details_value:
        old_val, new_val = _parse_arrow_change(details_value) or ("—", "—")
        user = target_value or "пользователь"
        return f"Telegram ID пользователя {user}: с {old_val} на {new_val}"

    if key in {
        "settings_cidr_games_sync",
        "settings_cidr_games_exclude_sync",
        "settings_cidr_games_routes_sync",
    }:
        formatted = _format_games_sync_tg_line(key, details_value)
        if formatted:
            return formatted

    humanized = _humanize_raw_details_for_tg(details_value)
    if humanized:
        return humanized

    display = user_action_event_display(key, target_value, target_type, details)
    label = user_action_event_label(key)
    if display and display != label:
        return display
    if details_value and "→" in details_value:
        return details_value
    return label


def _humanize_boolean_flag(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if value in {"1", "true", "yes", "вкл"}:
        return "включено"
    if value in {"0", "false", "no", "выкл"}:
        return "выключено"
    return value or "—"


def _humanize_source_flag(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if value in {"tg-mini", "tg_mini", "mini_app", "miniapp"}:
        return "Telegram Mini App"
    if value in {"web", "panel", "web_settings"}:
        return "веб-панель"
    return value or "панель"


_TG_NOTIFY_EVENT_LABELS = {
    "login_success": "успешный вход",
    "login_failed": "неудачный вход",
    "tg_unlinked": "непривязанный Telegram",
    "config_create": "создание конфига",
    "config_delete": "удаление конфига",
    "user_create": "добавление пользователя",
    "user_delete": "удаление пользователя",
    "client_ban": "блокировка клиента",
    "traffic_limit": "лимит трафика",
    "settings_change": "изменение настроек",
    "high_cpu": "высокая нагрузка CPU",
    "high_ram": "высокая нагрузка RAM",
}


def _humanize_user_action_details(event_key: str, details_value: str) -> str:
    if not details_value:
        return "-"

    if "→" in details_value and event_key not in {
        "settings_nightly_update",
        "settings_backup_update",
        "settings_telegram_auth_update",
    }:
        old_value, new_value = _parse_arrow_change(details_value) or ("—", "—")
        return f"Изменено: с {old_value} на {new_value}"

    if event_key == "login_failed":
        translated = _translate_auth_failure_detail(details_value)
        return translated if translated != details_value else "Ошибка входа"

    if event_key == "settings_user_password_update":
        return "Пароль успешно изменён"

    if event_key == "settings_user_tg_notify_update":
        try:
            enabled = _json.loads(details_value)
            if isinstance(enabled, dict) and enabled:
                labels = [
                    _TG_NOTIFY_EVENT_LABELS.get(str(key), str(key))
                    for key, val in enabled.items()
                    if bool(val)
                ]
                if labels:
                    return "Включены уведомления: " + ", ".join(labels)
            return "Настройки уведомлений обновлены"
        except Exception:
            return "Настройки уведомлений обновлены"

    if event_key in {"settings_viewer_access_grant", "settings_viewer_access_revoke"}:
        detail_map = parse_mini_details_kv(details_value)
        count = detail_map.get("configs")
        group = detail_map.get("group")
        action_text = "Выдан доступ" if event_key.endswith("grant") else "Доступ отозван"
        if count and group:
            return f"{action_text}: {count} конфиг(ов), группа {group}"
        return action_text

    if event_key == "settings_ip_file_toggle" and "|" in details_value:
        parts = [part.strip() for part in details_value.split("|")]
        if len(parts) >= 3:
            state_text = "включён" if parts[0] == "вкл" else "выключен"
            return f"Файл «{parts[1]}» {state_text}, затронуто {parts[2]}"

    detail_map = parse_mini_details_kv(details_value)
    if detail_map:
        if event_key == "settings_port_update":
            port = detail_map.get("value", "—")
            restart = _humanize_boolean_flag(detail_map.get("restart"))
            source = _humanize_source_flag(detail_map.get("via"))
            return f"Новый порт: {port}; перезапуск: {restart}; источник: {source}"

        if event_key == "settings_ip_add_temp":
            duration = detail_map.get("duration", "—")
            return f"Временный доступ выдан на {duration}"

        if event_key == "settings_ip_bulk_enable":
            entries = detail_map.get("entries", "0")
            return f"Включено IP-ограничений: {entries}"

        if event_key == "settings_ip_files_sync":
            synced = detail_map.get("synced", "0")
            updated = detail_map.get("updated", "0")
            missing = detail_map.get("missing")
            base = f"Синхронизировано файлов: {synced}; обновлено: {updated}"
            if missing:
                return f"{base}; отсутствуют источники: {missing.replace(',', ', ')}"
            return base

        if event_key == "settings_ip_scanner_block":
            return (
                f"Защита: {_humanize_boolean_flag(detail_map.get('enabled'))}; "
                f"порог попыток: {detail_map.get('max', '—')}; "
                f"окно: {detail_map.get('window', '—')} сек.; "
                f"бан: {detail_map.get('ban', '—')} сек.; "
                f"бан на странице блокировки: {_humanize_boolean_flag(detail_map.get('dwell'))}; "
                f"iptables whitelist: {_humanize_boolean_flag(detail_map.get('whitelist_fw'))}"
            )

        if event_key == "settings_monitor_update":
            cpu = detail_map.get("cpu", "—")
            ram = detail_map.get("ram", "—")
            interval = detail_map.get("interval", "—")
            cooldown = detail_map.get("cooldown", "—")
            return (
                f"CPU: {cpu}; RAM: {ram}; "
                f"интервал проверки: {interval}; "
                f"пауза уведомлений: {cooldown}"
            )

        if event_key == "settings_tests_run":
            count = detail_map.get("count")
            if count == "all":
                return "Запущены все тесты"
            if count:
                return f"Запущено тестов: {count}"
            return "Тесты запущены"

        if event_key == "settings_user_create":
            role = detail_map.get("роль", detail_map.get("role", "admin"))
            role_h = _ROLE_LABELS_RU.get(str(role).lower(), role)
            tg_id = detail_map.get("TG")
            if tg_id:
                return f"Роль: {role_h}; Telegram ID: {tg_id}"
            return f"Роль: {role_h}"

    humanized = _humanize_raw_details_for_tg(details_value)
    if humanized:
        return humanized

    return details_value


def user_action_details_label(event_type: str | None, details: str | None) -> str:
    event_key = str(event_type or "").strip()
    details_value = str(details or "").strip()
    if not details_value:
        return "-"

    if event_key == "settings_telegram_auth_update":
        return _format_telegram_auth_details_ru(details_value)

    if event_key == "settings_nightly_update" and (
        "cron=" in details_value or "enabled=" in details_value
    ):
        return _format_nightly_update_details(details_value)

    return _humanize_user_action_details(event_key, details_value)


_STATUS_DISPLAY_MAP = {
    "success": "Успешно",
    "ok": "Успешно",
    "info": "Инфо",
    "warning": "Предупреждение",
    "warn": "Предупреждение",
    "error": "Ошибка",
    "failed": "Ошибка",
    "fail": "Ошибка",
}


def _normalize_result_status(raw_status: str | None, *, is_security_alert: bool) -> tuple[str, str]:
    normalized = str(raw_status or "").strip().lower()
    if not normalized:
        normalized = "success"
    if is_security_alert and normalized not in {"error", "failed", "fail"}:
        normalized = "warning"
    return normalized, _STATUS_DISPLAY_MAP.get(normalized, normalized.capitalize())


def _csv_safe_value(raw_value: str | None) -> str:
    # Keep CSV rows single-line and predictable.
    return str(raw_value or "").replace("\r", " ").replace("\n", " ").strip()


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

        _SECURITY_ALERT_EVENTS = {
            "login_failed",
            "miniapp:telegram_login_failed",
            "miniapp:telegram_mini_login_failed",
            "miniapp:telegram_login_unlinked",
            "miniapp:telegram_mini_login_unlinked",
        }
        is_security_alert = event_type in _SECURITY_ALERT_EVENTS
        status, status_display = _normalize_result_status(
            getattr(row, "status", None),
            is_security_alert=is_security_alert,
        )
        actor_display = str(getattr(row, "actor_username", "") or "").strip() or "system/anonymous"
        details_display = user_action_details_label(event_type, getattr(row, "details", None))
        if is_security_alert or status in {"error", "failed", "fail"}:
            severity = "high"
        elif status in {"warning", "warn"}:
            severity = "medium"
        else:
            severity = "low"

        created_at = row.created_at
        event_display = user_action_event_display(
            event_type,
            target_name,
            target_type,
            getattr(row, "details", None),
        )
        csv_action = _csv_safe_value(event_display)
        csv_details = _csv_safe_value(details_display if details_display != "-" else "")
        csv_ip = _csv_safe_value(getattr(row, "remote_addr", None) or "")
        csv_user = _csv_safe_value(actor_display)
        csv_result = _csv_safe_value(status_display)

        view_rows.append(
            {
                "created_at": created_at,
                "created_at_iso": created_at.isoformat(),
                "created_at_ts": int(created_at.timestamp()),
                "actor_username": row.actor_username,
                "actor_display": actor_display,
                "event_type": event_type,
                "event_label": user_action_event_label(event_type),
                "event_display": event_display,
                "target_display": target_display,
                "status": status,
                "status_display": status_display,
                "details": str(getattr(row, "details", "") or "").strip() or "-",
                "details_display": details_display,
                "remote_addr": getattr(row, "remote_addr", None),
                "is_miniapp": is_miniapp,
                "source_kind": source_kind,
                "source_label": source_label,
                "is_security_alert": is_security_alert,
                "severity": severity,
                "search_blob": " ".join(
                    [
                        actor_display.lower(),
                        event_display.lower(),
                        str(details_display or "").lower(),
                        str(getattr(row, "remote_addr", "") or "").lower(),
                        str(status_display).lower(),
                        str(source_label).lower(),
                    ]
                ).strip(),
                "csv_row": {
                    "timestamp": created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "username": csv_user,
                    "action": csv_action,
                    "ip": csv_ip or "—",
                    "result": csv_result,
                    "details": csv_details or "—",
                },
            }
        )
    return view_rows


# ── Session grouping ───────────────────────────────────────────────────────


def _make_session(rows: list[dict[str, Any]], index: int) -> dict[str, Any]:
    alert_count = sum(1 for r in rows if r.get("is_security_alert"))
    ips: list[str] = list(dict.fromkeys(r["remote_addr"] for r in rows if r.get("remote_addr")))
    if len(ips) == 1:
        ip_display = ips[0]
    elif len(ips) > 1:
        ip_display = "разные IP"
    else:
        ip_display = "—"
    return {
        "session_id": str(index),
        "actor_username": rows[0]["actor_username"] or "system/anonymous",
        "session_end": rows[0]["created_at"],     # newest (rows are DESC)
        "session_start": rows[-1]["created_at"],  # oldest
        "session_date": rows[0]["created_at"].date().isoformat(),  # UTC date for day grouping
        "ip_display": ip_display,
        "row_count": len(rows),
        "alert_count": alert_count,
        "has_alerts": alert_count > 0,
        "rows": rows,
    }


def _make_day_group(date_key: str, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    total_rows = sum(s["row_count"] for s in sessions)
    total_alerts = sum(s["alert_count"] for s in sessions)
    return {
        "date_key": date_key,
        "date_utc": sessions[0]["session_end"].isoformat(),
        "sessions": sessions,
        "session_count": len(sessions),
        "row_count": total_rows,
        "alert_count": total_alerts,
        "has_alerts": total_alerts > 0,
    }


def build_user_action_sessions(
    rows: list[Any] | None,
    gap_seconds: int = 7200,
) -> list[dict[str, Any]]:
    """Group flat UserActionLog rows into sessions.

    A new session starts when the user changes, the time gap between consecutive
    actions exceeds gap_seconds (default 2 h), or an anonymous user changes IP.
    """
    flat = build_user_action_audit_view(rows)
    if not flat:
        return []

    sessions: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = [flat[0]]

    for row in flat[1:]:
        last = current[-1]  # oldest so far in current session (DESC order)
        curr_user = row["actor_username"] or "system/anonymous"
        last_user = last["actor_username"] or "system/anonymous"

        same_user = curr_user == last_user
        gap = (last["created_at"] - row["created_at"]).total_seconds()
        within_gap = gap <= gap_seconds

        is_anon = not (row["actor_username"] or "").strip()
        diff_ip = is_anon and row.get("remote_addr") != last.get("remote_addr")

        if same_user and within_gap and not diff_ip:
            current.append(row)
        else:
            sessions.append(_make_session(current, len(sessions)))
            current = [row]

    sessions.append(_make_session(current, len(sessions)))
    return sessions


def build_user_action_day_groups(
    rows: list[Any] | None,
    gap_seconds: int = 7200,
) -> list[dict[str, Any]]:
    """Group sessions by calendar day (UTC). Returns DESC-ordered day groups."""
    sessions = build_user_action_sessions(rows, gap_seconds)
    if not sessions:
        return []

    groups: list[dict[str, Any]] = []
    current_date = sessions[0]["session_date"]
    current_sessions: list[dict[str, Any]] = [sessions[0]]

    for session in sessions[1:]:
        if session["session_date"] == current_date:
            current_sessions.append(session)
        else:
            groups.append(_make_day_group(current_date, current_sessions))
            current_date = session["session_date"]
            current_sessions = [session]

    groups.append(_make_day_group(current_date, current_sessions))
    return groups
