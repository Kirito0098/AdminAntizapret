import os
import platform
import re
import subprocess
from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, session, url_for


def register_settings_routes(
    app,
    *,
    auth_manager,
    db,
    user_model,
    active_web_session_model,
    qr_download_audit_log_model,
    telegram_mini_audit_log_model,
    user_action_log_model,
    ip_restriction,
    ip_manager,
    collect_all_openvpn_files_for_access,
    build_openvpn_access_groups,
    config_file_handler,
    group_folders,
    build_conf_access_groups,
    enqueue_background_task,
    task_restart_service,
    set_env_value,
    get_env_value,
    to_bool,
    is_valid_cron_expression,
    ensure_nightly_idle_restart_cron,
    get_nightly_idle_restart_settings,
    set_nightly_idle_restart_settings,
    get_active_web_session_settings,
    set_active_web_session_settings,
    get_public_download_enabled,
    log_telegram_audit_event,
    log_user_action_event,
):
    def _has_telegram_mini_session():
        return bool(
            session.get("telegram_mini_auth")
            and session.get("telegram_mini_username")
            and session.get("telegram_mini_username") == session.get("username")
        )

    def _normalize_telegram_id(raw_value):
        value = (raw_value or "").strip()
        if not value:
            return "", None
        if not re.fullmatch(r"^[1-9][0-9]{4,20}$", value):
            return None, "Telegram ID должен содержать только цифры (5..21 символ) и не начинаться с 0"
        return value, None

    def _normalize_telegram_bot_username(raw_value):
        value = (raw_value or "").strip().lstrip("@")
        if not value:
            return "", None
        if not re.fullmatch(r"^[A-Za-z0-9_]{5,64}$", value):
            return None, "Username Telegram-бота должен содержать 5..64 символа: латиница, цифры, _"
        return value, None

    def _normalize_telegram_bot_token(raw_value):
        value = (raw_value or "").strip()
        if not value:
            return "", None
        if not re.fullmatch(r"^[0-9]{6,12}:[A-Za-z0-9_-]{20,}$", value):
            return None, "Неверный формат токена Telegram-бота"
        return value, None

    def _nightly_time_from_cron(cron_expr):
        value = (cron_expr or "").strip()
        parts = value.split()
        if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit():
            minute_value = int(parts[0])
            hour_value = int(parts[1])
            if 0 <= minute_value <= 59 and 0 <= hour_value <= 23:
                return f"{hour_value:02d}:{minute_value:02d}"
        return "04:00"

    def _mini_protocol_label(raw_value):
        value = (raw_value or "").strip().lower()
        if value in {"openvpn", "ovpn"}:
            return "OpenVPN"
        if value in {"wireguard", "wg"}:
            return "WireGuard"
        if value in {"amneziawg", "amnezia"}:
            return "AmneziaWG"
        return "неизвестно"

    def _parse_mini_details_kv(raw_details):
        result = {}
        for token in str(raw_details or "").split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            key = key.strip()
            if not key:
                continue
            result[key] = value.strip()
        return result

    def _mini_event_label(event_type):
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

    def _mini_event_details_label(event_type, details, config_name=None):
        event_key = str(event_type or "").strip()
        details_value = str(details or "").strip()
        config_value = str(config_name or "").strip()
        detail_map = _parse_mini_details_kv(details_value)

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

    def _build_telegram_mini_audit_view(rows):
        view_rows = []
        for row in rows or []:
            event_type = str(getattr(row, "event_type", "") or "").strip()
            details_raw = str(getattr(row, "details", "") or "").strip()
            config_name = str(getattr(row, "config_name", "") or "").strip()
            base_event_label = _mini_event_label(event_type)
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
                    "details_label": _mini_event_details_label(event_type, details_raw, config_name),
                }
            )
        return view_rows

    def _resolve_user_action_source(event_type, details):
        event_key = str(event_type or "").strip().lower()
        detail_map = _parse_mini_details_kv(details)
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

    def _user_action_event_label(event_type):
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

        # Handle miniapp: prefixed events
        if event_key.startswith("miniapp:"):
            original_event = event_key[8:]  # Strip 'miniapp:' prefix
            # Use the mini app event label mapping
            mini_label = _mini_event_label(original_event)
            return mini_label

        if event_key in mapping:
            return mapping[event_key]
        fallback = event_key.replace("_", " ").strip()
        return fallback.capitalize() if fallback else "Событие"

    def _user_action_event_display(event_type, target_name, target_type, details):
        event_key = str(event_type or "").strip()
        target_value = str(target_name or "").strip()
        target_kind = str(target_type or "").strip()
        details_value = str(details or "").strip()
        detail_map = _parse_mini_details_kv(details_value)

        # Handle miniapp: prefixed events
        if event_key.startswith("miniapp:"):
            original_event = event_key[8:]  # Strip 'miniapp:' prefix
            # Use the mini app event details mapping
            return _mini_event_details_label(original_event, details_value, target_value)

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
            return f"{_user_action_event_label(event_key)}: {target_value}"

        if event_key in {
            "settings_user_create",
            "settings_user_delete",
            "settings_user_role_update",
            "settings_user_password_update",
            "settings_user_telegram_update",
        } and target_value:
            return f"{_user_action_event_label(event_key)}: {target_value}"

        if target_value and target_kind in {"ip_restriction", "ip_file"}:
            return f"{_user_action_event_label(event_key)}: {target_value}"

        return _user_action_event_label(event_key)

    def _build_user_action_audit_view(rows):
        view_rows = []
        for row in rows or []:
            event_type = str(getattr(row, "event_type", "") or "").strip()
            target_type = str(getattr(row, "target_type", "") or "").strip()
            target_name = str(getattr(row, "target_name", "") or "").strip()
            target_display = target_name or "-"
            if target_type:
                target_display = f"{target_display} ({target_type})" if target_name else target_type

            source_kind, source_label = _resolve_user_action_source(event_type, getattr(row, "details", None))
            is_miniapp = source_kind == "miniapp"

            view_rows.append(
                {
                    "created_at": row.created_at,
                    "actor_username": row.actor_username,
                    "event_type": event_type,
                    "event_label": _user_action_event_label(event_type),
                    "event_display": _user_action_event_display(
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

    def _build_tg_mini_settings_payload():
        nightly_idle_restart_enabled, nightly_idle_restart_cron = get_nightly_idle_restart_settings()
        active_web_session_ttl_seconds, active_web_session_touch_interval_seconds = get_active_web_session_settings()

        telegram_auth_bot_username = get_env_value("TELEGRAM_AUTH_BOT_USERNAME", "")
        telegram_auth_max_age_seconds = get_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300")
        telegram_auth_bot_token_set = bool((get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip())
        telegram_auth_enabled = bool(telegram_auth_bot_username and telegram_auth_bot_token_set)

        return {
            "app_port": get_env_value("APP_PORT", os.getenv("APP_PORT", "5050")),
            "nightly_idle_restart_enabled": bool(nightly_idle_restart_enabled),
            "nightly_idle_restart_cron": nightly_idle_restart_cron,
            "nightly_idle_restart_time": _nightly_time_from_cron(nightly_idle_restart_cron),
            "active_web_session_ttl_seconds": int(active_web_session_ttl_seconds),
            "active_web_session_touch_interval_seconds": int(active_web_session_touch_interval_seconds),
            "telegram_auth_bot_username": telegram_auth_bot_username,
            "telegram_auth_max_age_seconds": int(telegram_auth_max_age_seconds or 300),
            "telegram_auth_bot_token_set": telegram_auth_bot_token_set,
            "telegram_auth_enabled": telegram_auth_enabled,
        }

    @app.route("/settings", methods=["GET", "POST"])
    @auth_manager.admin_required
    def settings():
        if request.method == "POST":
            new_port_raw = (request.form.get("port") or "").strip()
            if new_port_raw:
                if new_port_raw.isdigit() and 1 <= int(new_port_raw) <= 65535:
                    set_env_value("APP_PORT", new_port_raw)
                    os.environ["APP_PORT"] = new_port_raw
                    flash("Порт успешно изменён. Перезапуск службы...", "success")
                    log_user_action_event(
                        "settings_port_update",
                        target_type="app",
                        target_name="APP_PORT",
                        details=f"value={new_port_raw}",
                    )

                    try:
                        if platform.system() == "Linux":
                            subprocess.run(
                                ["systemctl", "restart", "admin-antizapret.service"], check=True
                            )
                    except subprocess.CalledProcessError as e:
                        flash(f"Ошибка при перезапуске службы: {e}", "error")
                else:
                    flash("Порт должен быть целым числом в диапазоне 1..65535", "error")

            ttl_raw = request.form.get("qr_download_token_ttl_seconds", "").strip()
            if ttl_raw:
                if ttl_raw.isdigit():
                    ttl_value = int(ttl_raw)
                    if 60 <= ttl_value <= 3600:
                        set_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", str(ttl_value))
                        os.environ["QR_DOWNLOAD_TOKEN_TTL_SECONDS"] = str(ttl_value)
                        flash("TTL одноразовой QR-ссылки обновлен", "success")
                        log_user_action_event(
                            "settings_qr_ttl_update",
                            target_type="qr",
                            target_name="QR_DOWNLOAD_TOKEN_TTL_SECONDS",
                            details=f"value={ttl_value}",
                        )
                    else:
                        flash("TTL QR-ссылки должен быть в диапазоне 60..3600 секунд", "error")
                else:
                    flash("TTL QR-ссылки должен быть целым числом", "error")

            max_downloads_raw = request.form.get("qr_download_token_max_downloads", "").strip()
            if max_downloads_raw:
                if max_downloads_raw.isdigit() and int(max_downloads_raw) in (1, 3, 5):
                    set_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", max_downloads_raw)
                    os.environ["QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS"] = max_downloads_raw
                    flash("Лимит скачиваний одноразовой ссылки обновлен", "success")
                    log_user_action_event(
                        "settings_qr_max_downloads_update",
                        target_type="qr",
                        target_name="QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS",
                        details=f"value={max_downloads_raw}",
                    )
                else:
                    flash("Лимит скачиваний должен быть одним из значений: 1, 3 или 5", "error")

            clear_pin = request.form.get("clear_qr_download_pin") == "on"
            pin_raw = (request.form.get("qr_download_pin") or "").strip()
            if clear_pin:
                set_env_value("QR_DOWNLOAD_PIN", "")
                os.environ["QR_DOWNLOAD_PIN"] = ""
                flash("PIN для QR-ссылок очищен", "success")
                log_user_action_event(
                    "settings_qr_pin_clear",
                    target_type="qr",
                    target_name="QR_DOWNLOAD_PIN",
                )
            elif pin_raw:
                if pin_raw.isdigit() and 4 <= len(pin_raw) <= 12:
                    set_env_value("QR_DOWNLOAD_PIN", pin_raw)
                    os.environ["QR_DOWNLOAD_PIN"] = pin_raw
                    flash("PIN для QR-ссылок обновлен", "success")
                    log_user_action_event(
                        "settings_qr_pin_update",
                        target_type="qr",
                        target_name="QR_DOWNLOAD_PIN",
                        details=f"length={len(pin_raw)}",
                    )
                else:
                    flash("PIN должен содержать только цифры и иметь длину от 4 до 12", "error")

            if request.form.get("nightly_settings_action") == "save":
                nightly_enabled_raw = (request.form.get("nightly_idle_restart_enabled") or "true").strip().lower()
                nightly_enabled = to_bool(nightly_enabled_raw, default=True)

                ttl_raw = (request.form.get("active_web_session_ttl_seconds") or "").strip()
                touch_raw = (request.form.get("active_web_session_touch_interval_seconds") or "").strip()
                nightly_time_raw = (request.form.get("nightly_idle_restart_time") or "").strip()
                cron_expr_raw = (request.form.get("nightly_idle_restart_cron") or "").strip()

                has_error = False

                cron_expr = ""
                if nightly_time_raw:
                    time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", nightly_time_raw)
                    if time_match:
                        hour_value = int(time_match.group(1))
                        minute_value = int(time_match.group(2))
                        cron_expr = f"{minute_value} {hour_value} * * *"
                    else:
                        flash("Укажите время в формате ЧЧ:ММ (например, 04:00)", "error")
                        has_error = True

                if not cron_expr:
                    cron_expr = cron_expr_raw or "0 4 * * *"

                if not is_valid_cron_expression(cron_expr):
                    flash("Cron-выражение должно состоять из 5 полей и содержать только цифры и символы */,-", "error")
                    has_error = True

                active_ttl_seconds, active_touch_interval_seconds = get_active_web_session_settings()
                ttl_value = active_ttl_seconds
                if ttl_raw:
                    if ttl_raw.isdigit() and 30 <= int(ttl_raw) <= 86400:
                        ttl_value = int(ttl_raw)
                    else:
                        flash("TTL активной сессии должен быть целым числом в диапазоне 30..86400 секунд", "error")
                        has_error = True

                touch_value = active_touch_interval_seconds
                if touch_raw:
                    if touch_raw.isdigit() and 1 <= int(touch_raw) <= 3600:
                        touch_value = int(touch_raw)
                    else:
                        flash("Интервал heartbeat должен быть целым числом в диапазоне 1..3600 секунд", "error")
                        has_error = True

                if not has_error:
                    set_nightly_idle_restart_settings(nightly_enabled, cron_expr)
                    set_active_web_session_settings(ttl_value, touch_value)

                    env_enabled = "true" if nightly_enabled else "false"
                    set_env_value("NIGHTLY_IDLE_RESTART_ENABLED", env_enabled)
                    set_env_value("NIGHTLY_IDLE_RESTART_CRON", cron_expr)
                    set_env_value("ACTIVE_WEB_SESSION_TTL_SECONDS", str(ttl_value))
                    set_env_value("ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", str(touch_value))

                    os.environ["NIGHTLY_IDLE_RESTART_ENABLED"] = env_enabled
                    os.environ["NIGHTLY_IDLE_RESTART_CRON"] = cron_expr
                    os.environ["ACTIVE_WEB_SESSION_TTL_SECONDS"] = str(ttl_value)
                    os.environ["ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS"] = str(touch_value)

                    cron_ok, cron_msg = ensure_nightly_idle_restart_cron()
                    if cron_ok:
                        flash("Настройки ночного рестарта сохранены", "success")
                    else:
                        flash(cron_msg, "error")
                    log_user_action_event(
                        "settings_nightly_update",
                        target_type="maintenance",
                        target_name="nightly_idle_restart",
                        details=(
                            f"enabled={1 if nightly_enabled else 0} "
                            f"cron={cron_expr} ttl={ttl_value} touch={touch_value}"
                        ),
                        status="success" if cron_ok else "warning",
                    )

            if request.form.get("telegram_auth_action") == "save":
                tg_username_raw = request.form.get("telegram_auth_bot_username", "")
                tg_token_raw = request.form.get("telegram_auth_bot_token", "")
                tg_max_age_raw = request.form.get("telegram_auth_max_age_seconds", "").strip()

                has_tg_error = False
                tg_username, username_error = _normalize_telegram_bot_username(tg_username_raw)
                if username_error:
                    flash(username_error, "error")
                    has_tg_error = True

                tg_max_age_value = 300
                if tg_max_age_raw:
                    if tg_max_age_raw.isdigit() and 30 <= int(tg_max_age_raw) <= 86400:
                        tg_max_age_value = int(tg_max_age_raw)
                    else:
                        flash("Срок действия Telegram авторизации должен быть в диапазоне 30..86400 секунд", "error")
                        has_tg_error = True

                existing_token = (get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
                token_to_apply = existing_token
                token_updated = False
                if (tg_token_raw or "").strip():
                    tg_token, token_error = _normalize_telegram_bot_token(tg_token_raw)
                    if token_error:
                        flash(token_error, "error")
                        has_tg_error = True
                    else:
                        token_to_apply = tg_token
                        token_updated = True

                if not has_tg_error:
                    set_env_value("TELEGRAM_AUTH_BOT_USERNAME", tg_username)
                    set_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", str(tg_max_age_value))
                    os.environ["TELEGRAM_AUTH_BOT_USERNAME"] = tg_username
                    os.environ["TELEGRAM_AUTH_MAX_AGE_SECONDS"] = str(tg_max_age_value)

                    if token_updated:
                        set_env_value("TELEGRAM_AUTH_BOT_TOKEN", token_to_apply)
                        os.environ["TELEGRAM_AUTH_BOT_TOKEN"] = token_to_apply

                    if token_to_apply:
                        if tg_username:
                            flash("Настройки Telegram авторизации обновлены. Telegram логин включен.", "success")
                        else:
                            flash("Токен сохранен, но Telegram логин выключен: не заполнен username бота.", "info")
                    else:
                        flash("Telegram логин выключен (токен бота пустой).", "success")
                    log_user_action_event(
                        "settings_telegram_auth_update",
                        target_type="telegram_auth",
                        target_name=(tg_username or "-"),
                        details=(
                            f"max_age={tg_max_age_value} "
                            f"token_set={1 if bool(token_to_apply) else 0} "
                            f"token_updated={1 if token_updated else 0}"
                        ),
                    )

            username = request.form.get("username")
            password = request.form.get("password")
            if username and password:
                if len(password) < 8:
                    flash("Пароль должен содержать минимум 8 символов!", "error")
                else:
                    role = request.form.get("role", "admin")
                    if role not in ("admin", "viewer"):
                        role = "admin"
                    telegram_id_raw = request.form.get("telegram_id", "")
                    normalized_telegram_id, tg_error = _normalize_telegram_id(telegram_id_raw)

                    if tg_error:
                        flash(tg_error, "error")
                    elif user_model.query.filter_by(username=username).first():
                        flash(f"Пользователь '{username}' уже существует!", "error")
                    elif normalized_telegram_id and user_model.query.filter_by(telegram_id=normalized_telegram_id).first():
                        flash(f"Telegram ID {normalized_telegram_id} уже привязан к другому пользователю!", "error")
                    else:
                        user = user_model(
                            username=username,
                            role=role,
                            telegram_id=normalized_telegram_id or None,
                        )
                        user.set_password(password)
                        db.session.add(user)
                        db.session.commit()
                        flash(f"Пользователь '{username}' ({role}) успешно добавлен!", "success")
                        log_user_action_event(
                            "settings_user_create",
                            target_type="user",
                            target_name=username,
                            details=f"role={role} telegram_id={normalized_telegram_id or '-'}",
                        )

            change_telegram_username = request.form.get("change_telegram_username")
            if change_telegram_username:
                tg_user = user_model.query.filter_by(username=change_telegram_username).first()
                if not tg_user:
                    flash(f"Пользователь '{change_telegram_username}' не найден!", "error")
                else:
                    new_telegram_id_raw = request.form.get("new_telegram_id", "")
                    normalized_telegram_id, tg_error = _normalize_telegram_id(new_telegram_id_raw)
                    if tg_error:
                        flash(tg_error, "error")
                    else:
                        if normalized_telegram_id:
                            owner = user_model.query.filter(
                                user_model.telegram_id == normalized_telegram_id,
                                user_model.username != change_telegram_username,
                            ).first()
                            if owner:
                                flash(
                                    f"Telegram ID {normalized_telegram_id} уже привязан к пользователю '{owner.username}'",
                                    "error",
                                )
                                return redirect(url_for("settings"))

                        tg_user.telegram_id = normalized_telegram_id or None
                        db.session.commit()
                        if normalized_telegram_id:
                            flash(
                                f"Telegram ID пользователя '{change_telegram_username}' обновлён",
                                "success",
                            )
                        else:
                            flash(
                                f"Telegram ID пользователя '{change_telegram_username}' очищен",
                                "success",
                            )
                        log_user_action_event(
                            "settings_user_telegram_update",
                            target_type="user",
                            target_name=change_telegram_username,
                            details=f"telegram_id={normalized_telegram_id or '-'}",
                        )

            delete_username = request.form.get("delete_username")
            if delete_username:
                if delete_username == session.get("username"):
                    flash("Нельзя удалить собственный аккаунт!", "error")
                else:
                    user = user_model.query.filter_by(username=delete_username).first()
                    if user:
                        db.session.delete(user)
                        db.session.commit()
                        flash(f"Пользователь '{delete_username}' успешно удалён!", "success")
                        log_user_action_event(
                            "settings_user_delete",
                            target_type="user",
                            target_name=delete_username,
                        )
                    else:
                        flash(f"Пользователь '{delete_username}' не найден!", "error")

            change_role_username = request.form.get("change_role_username")
            new_role = request.form.get("new_role")
            if change_role_username and new_role:
                if new_role not in ("admin", "viewer"):
                    flash("Неверная роль!", "error")
                elif change_role_username == session.get("username"):
                    flash("Нельзя изменить собственную роль!", "error")
                else:
                    role_user = user_model.query.filter_by(username=change_role_username).first()
                    if role_user:
                        role_user.role = new_role
                        db.session.commit()
                        flash(f"Роль пользователя '{change_role_username}' изменена на '{new_role}'!", "success")
                        log_user_action_event(
                            "settings_user_role_update",
                            target_type="user",
                            target_name=change_role_username,
                            details=f"role={new_role}",
                        )
                    else:
                        flash(f"Пользователь '{change_role_username}' не найден!", "error")

            change_password_username = request.form.get("change_password_username")
            new_password = request.form.get("new_password")
            if change_password_username and new_password:
                if len(new_password) < 8:
                    flash("Пароль должен содержать минимум 8 символов!", "error")
                else:
                    pw_user = user_model.query.filter_by(username=change_password_username).first()
                    if pw_user:
                        pw_user.set_password(new_password)
                        db.session.commit()
                        flash(f"Пароль пользователя '{change_password_username}' изменён!", "success")
                        log_user_action_event(
                            "settings_user_password_update",
                            target_type="user",
                            target_name=change_password_username,
                        )
                    else:
                        flash(f"Пользователь '{change_password_username}' не найден!", "error")

            ip_action = request.form.get("ip_action")

            if ip_action == "add_ip":
                new_ip = request.form.get("new_ip", "").strip()
                if new_ip:
                    if ip_restriction.add_ip(new_ip):
                        flash(f"IP {new_ip} добавлен", "success")
                        log_user_action_event(
                            "settings_ip_add",
                            target_type="ip_restriction",
                            target_name=new_ip,
                        )
                    else:
                        flash("Неверный формат IP", "error")

            elif ip_action == "remove_ip":
                ip_to_remove = request.form.get("ip_to_remove", "").strip()
                if ip_to_remove:
                    if ip_restriction.remove_ip(ip_to_remove):
                        flash(f"IP {ip_to_remove} удален", "success")
                        log_user_action_event(
                            "settings_ip_remove",
                            target_type="ip_restriction",
                            target_name=ip_to_remove,
                        )
                    else:
                        flash("IP не найден", "error")

            elif ip_action == "clear_all_ips":
                ip_restriction.clear_all()
                flash("Все IP ограничения сброшены (доступ разрешен всем)", "success")
                log_user_action_event(
                    "settings_ip_clear",
                    target_type="ip_restriction",
                    target_name="all",
                )

            elif ip_action == "enable_ips":
                ips_text = request.form.get("ips_text", "").strip()
                if ips_text:
                    ip_restriction.clear_all()
                    for ip in ips_text.split(","):
                        ip_restriction.add_ip(ip.strip())
                    flash("IP ограничения включены", "success")
                    entries_count = len([ip for ip in ips_text.split(",") if ip.strip()])
                    log_user_action_event(
                        "settings_ip_bulk_enable",
                        target_type="ip_restriction",
                        target_name="bulk",
                        details=f"entries={entries_count}",
                    )
                else:
                    flash("Укажите хотя бы один IP-адрес", "error")

            file_action = request.form.get("file_action")

            if file_action == "add_from_file":
                ip_file = request.form.get("ip_file", "").strip()
                if ip_file:
                    try:
                        added_count = ip_manager.add_from_file(ip_file)
                        flash(f"Добавлено {added_count} IP из файла {ip_file}", "success")
                        log_user_action_event(
                            "settings_ip_add_from_file",
                            target_type="ip_file",
                            target_name=ip_file,
                            details=f"count={added_count}",
                        )
                    except FileNotFoundError:
                        flash("Файл не найден", "error")
                    except Exception as e:
                        flash(f"Ошибка при добавлении IP: {e}", "error")
                else:
                    flash("Выберите файл", "error")

            elif file_action in ("enable_file", "disable_file"):
                ip_file = request.form.get("ip_file", "").strip()
                if ip_file:
                    try:
                        if file_action == "enable_file":
                            cnt = ip_manager.enable_file(ip_file)
                            flash(f"Добавлено {cnt} IP из файла {ip_file}", "success")
                        else:
                            cnt = ip_manager.disable_file(ip_file)
                            flash(f"Удалено {cnt} IP из файла {ip_file}", "success")
                        log_user_action_event(
                            "settings_ip_file_toggle",
                            target_type="ip_file",
                            target_name=ip_file,
                            details=f"action={file_action} count={cnt}",
                        )
                    except FileNotFoundError:
                        flash("Файл не найден", "error")
                    except Exception as e:
                        flash(f"Ошибка при обработке файла: {e}", "error")
                else:
                    flash("Не указан файл", "error")

            restart_action = request.form.get("restart_action")

            if restart_action == "restart_service":
                try:
                    task = enqueue_background_task(
                        "restart_service",
                        task_restart_service,
                        created_by_username=session.get("username"),
                        queued_message="Перезапуск службы поставлен в очередь",
                    )
                    flash(
                        f"Перезапуск службы запущен в фоне (task: {task.id[:8]}). Обновите страницу через 10-20 секунд.",
                        "info",
                    )
                    log_user_action_event(
                        "settings_restart_service",
                        target_type="service",
                        target_name="admin-antizapret.service",
                        details=f"task_id={task.id}",
                    )
                except Exception as e:
                    flash(f"Ошибка запуска фонового перезапуска: {str(e)}", "error")

            return redirect(url_for("settings"))

        current_port = os.getenv("APP_PORT", "5050")
        qr_download_token_ttl_seconds = get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600")
        qr_download_token_max_downloads = get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1")
        qr_download_pin_set = bool((get_env_value("QR_DOWNLOAD_PIN", "") or "").strip())
        telegram_auth_bot_username = get_env_value("TELEGRAM_AUTH_BOT_USERNAME", "")
        telegram_auth_max_age_seconds = get_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300")
        telegram_auth_bot_token_set = bool((get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip())
        telegram_auth_enabled = bool(telegram_auth_bot_username and telegram_auth_bot_token_set)

        nightly_idle_restart_enabled, nightly_idle_restart_cron = get_nightly_idle_restart_settings()
        nightly_idle_restart_time = "04:00"
        cron_parts = (nightly_idle_restart_cron or "").split()
        if len(cron_parts) == 5 and cron_parts[0].isdigit() and cron_parts[1].isdigit():
            minute_value = int(cron_parts[0])
            hour_value = int(cron_parts[1])
            if 0 <= minute_value <= 59 and 0 <= hour_value <= 23:
                nightly_idle_restart_time = f"{hour_value:02d}:{minute_value:02d}"

        active_web_session_ttl_seconds, active_web_session_touch_interval_seconds = get_active_web_session_settings()
        active_web_sessions_count = active_web_session_model.query.filter(
            active_web_session_model.last_seen_at >= datetime.utcnow() - timedelta(seconds=active_web_session_ttl_seconds)
        ).count()

        qr_download_audit_logs = qr_download_audit_log_model.query.order_by(
            qr_download_audit_log_model.created_at.desc()
        ).limit(100).all()
        telegram_mini_audit_logs = telegram_mini_audit_log_model.query.order_by(
            telegram_mini_audit_log_model.created_at.desc()
        ).limit(200).all()
        telegram_mini_audit_view = _build_telegram_mini_audit_view(telegram_mini_audit_logs)
        user_action_logs = user_action_log_model.query.order_by(
            user_action_log_model.created_at.desc()
        ).limit(300).all()
        user_action_audit_view = _build_user_action_audit_view(user_action_logs)
        users = user_model.query.all()
        viewer_users = user_model.query.filter_by(role="viewer").all()

        all_openvpn = collect_all_openvpn_files_for_access()
        openvpn_access_groups = build_openvpn_access_groups(all_openvpn)

        orig_paths = config_file_handler.config_paths["openvpn"]
        try:
            config_file_handler.config_paths["openvpn"] = [d for g in group_folders.values() for d in g]
            _, all_wg, all_amneziawg = config_file_handler.get_config_files()
        finally:
            config_file_handler.config_paths["openvpn"] = orig_paths

        wg_access_groups = build_conf_access_groups(all_wg, "wg")
        amneziawg_access_groups = build_conf_access_groups(all_amneziawg, "amneziawg")

        viewer_access = {vu.id: {acc.config_name for acc in vu.allowed_configs} for vu in viewer_users}

        allowed_ips = ip_restriction.get_allowed_ips()
        ip_enabled = ip_restriction.is_enabled()
        current_ip = ip_restriction.get_client_ip()

        ip_manager.sync_enabled()
        ip_files = ip_manager.list_ip_files()
        ip_file_states = ip_manager.get_file_states()

        return render_template(
            "settings.html",
            port=current_port,
            users=users,
            viewer_users=viewer_users,
            allowed_ips=allowed_ips,
            ip_enabled=ip_enabled,
            current_ip=current_ip,
            ip_files=ip_files,
            ip_file_states=ip_file_states,
            all_openvpn=all_openvpn,
            openvpn_access_groups=openvpn_access_groups,
            all_wg=all_wg,
            all_amneziawg=all_amneziawg,
            wg_access_groups=wg_access_groups,
            amneziawg_access_groups=amneziawg_access_groups,
            viewer_access=viewer_access,
            public_download_enabled=get_public_download_enabled(),
            qr_download_token_ttl_seconds=qr_download_token_ttl_seconds,
            qr_download_token_max_downloads=qr_download_token_max_downloads,
            qr_download_pin_set=qr_download_pin_set,
            telegram_auth_bot_username=telegram_auth_bot_username,
            telegram_auth_max_age_seconds=telegram_auth_max_age_seconds,
            telegram_auth_bot_token_set=telegram_auth_bot_token_set,
            telegram_auth_enabled=telegram_auth_enabled,
            nightly_idle_restart_enabled=nightly_idle_restart_enabled,
            nightly_idle_restart_cron=nightly_idle_restart_cron,
            nightly_idle_restart_time=nightly_idle_restart_time,
            active_web_session_ttl_seconds=active_web_session_ttl_seconds,
            active_web_session_touch_interval_seconds=active_web_session_touch_interval_seconds,
            active_web_sessions_count=active_web_sessions_count,
            qr_download_audit_logs=qr_download_audit_logs,
            telegram_mini_audit_logs=telegram_mini_audit_view,
            user_action_audit_logs=user_action_audit_view,
        )

    @app.route("/api/tg-mini/settings", methods=["GET"])
    @auth_manager.admin_required
    def api_tg_mini_settings_get():
        if not _has_telegram_mini_session():
            return jsonify({"success": False, "message": "Доступ разрешён только из Telegram Mini App."}), 403
        return jsonify({"success": True, "settings": _build_tg_mini_settings_payload()})

    @app.route("/api/tg-mini/settings", methods=["POST"])
    @auth_manager.admin_required
    def api_tg_mini_settings_update():
        if not _has_telegram_mini_session():
            return jsonify({"success": False, "message": "Доступ разрешён только из Telegram Mini App."}), 403

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        section = (data.get("section") or "").strip().lower()
        if section not in {"port", "nightly", "telegram_auth", "restart_service", "update_system"}:
            return jsonify({"success": False, "message": "Неизвестный раздел настроек"}), 400

        try:
            if section == "port":
                new_port = str(data.get("port") or "").strip()
                if not new_port.isdigit():
                    return jsonify({"success": False, "message": "Порт должен быть числом"}), 400

                port_value = int(new_port)
                if port_value < 1 or port_value > 65535:
                    return jsonify({"success": False, "message": "Порт должен быть в диапазоне 1..65535"}), 400

                set_env_value("APP_PORT", str(port_value))
                os.environ["APP_PORT"] = str(port_value)

                restart_task_id = None
                if bool(data.get("restart_service", True)):
                    task = enqueue_background_task(
                        "restart_service",
                        task_restart_service,
                        created_by_username=session.get("username"),
                        queued_message="Перезапуск службы поставлен в очередь",
                    )
                    restart_task_id = task.id

                log_telegram_audit_event(
                    "mini_settings_port",
                    details=f"port={port_value} restart={1 if bool(data.get('restart_service', True)) else 0}",
                )
                log_user_action_event(
                    "settings_port_update",
                    target_type="app",
                    target_name="APP_PORT",
                    details=(
                        f"value={port_value} via=tg-mini "
                        f"restart={1 if bool(data.get('restart_service', True)) else 0}"
                    ),
                )

                return jsonify(
                    {
                        "success": True,
                        "message": "Порт сохранен",
                        "restart_task_id": restart_task_id,
                        "settings": _build_tg_mini_settings_payload(),
                    }
                )

            if section == "nightly":
                nightly_enabled = bool(data.get("nightly_idle_restart_enabled", True))
                nightly_time_raw = (data.get("nightly_idle_restart_time") or "").strip()

                cron_expr = ""
                if nightly_time_raw:
                    time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", nightly_time_raw)
                    if not time_match:
                        return jsonify(
                            {
                                "success": False,
                                "message": "Укажите время в формате ЧЧ:ММ (например, 04:00)",
                            }
                        ), 400

                    hour_value = int(time_match.group(1))
                    minute_value = int(time_match.group(2))
                    cron_expr = f"{minute_value} {hour_value} * * *"

                if not cron_expr:
                    cron_expr = (data.get("nightly_idle_restart_cron") or "").strip() or "0 4 * * *"

                if not is_valid_cron_expression(cron_expr):
                    return jsonify(
                        {
                            "success": False,
                            "message": "Cron-выражение должно состоять из 5 полей и содержать только цифры и символы */,-",
                        }
                    ), 400

                ttl_raw = str(data.get("active_web_session_ttl_seconds") or "").strip()
                touch_raw = str(data.get("active_web_session_touch_interval_seconds") or "").strip()

                if not ttl_raw.isdigit() or not (30 <= int(ttl_raw) <= 86400):
                    return jsonify(
                        {
                            "success": False,
                            "message": "TTL активной сессии должен быть целым числом в диапазоне 30..86400 секунд",
                        }
                    ), 400

                if not touch_raw.isdigit() or not (1 <= int(touch_raw) <= 3600):
                    return jsonify(
                        {
                            "success": False,
                            "message": "Интервал heartbeat должен быть целым числом в диапазоне 1..3600 секунд",
                        }
                    ), 400

                ttl_value = int(ttl_raw)
                touch_value = int(touch_raw)

                set_nightly_idle_restart_settings(nightly_enabled, cron_expr)
                set_active_web_session_settings(ttl_value, touch_value)

                env_enabled = "true" if nightly_enabled else "false"
                set_env_value("NIGHTLY_IDLE_RESTART_ENABLED", env_enabled)
                set_env_value("NIGHTLY_IDLE_RESTART_CRON", cron_expr)
                set_env_value("ACTIVE_WEB_SESSION_TTL_SECONDS", str(ttl_value))
                set_env_value("ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", str(touch_value))

                os.environ["NIGHTLY_IDLE_RESTART_ENABLED"] = env_enabled
                os.environ["NIGHTLY_IDLE_RESTART_CRON"] = cron_expr
                os.environ["ACTIVE_WEB_SESSION_TTL_SECONDS"] = str(ttl_value)
                os.environ["ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS"] = str(touch_value)

                cron_ok, cron_msg = ensure_nightly_idle_restart_cron()
                if not cron_ok:
                    return jsonify({"success": False, "message": cron_msg}), 500

                log_telegram_audit_event(
                    "mini_settings_nightly",
                    details=(
                        f"enabled={1 if nightly_enabled else 0} "
                        f"time={nightly_time_raw or '-'} ttl={ttl_value} touch={touch_value}"
                    ),
                )
                log_user_action_event(
                    "settings_nightly_update",
                    target_type="maintenance",
                    target_name="nightly_idle_restart",
                    details=(
                        f"enabled={1 if nightly_enabled else 0} cron={cron_expr} "
                        f"ttl={ttl_value} touch={touch_value} via=tg-mini"
                    ),
                )

                return jsonify(
                    {
                        "success": True,
                        "message": "Настройки ночного рестарта сохранены",
                        "settings": _build_tg_mini_settings_payload(),
                    }
                )

            if section == "telegram_auth":
                tg_username_raw = data.get("telegram_auth_bot_username", "")
                tg_token_raw = data.get("telegram_auth_bot_token", None)
                tg_max_age_raw = str(data.get("telegram_auth_max_age_seconds") or "").strip()

                tg_username, username_error = _normalize_telegram_bot_username(tg_username_raw)
                if username_error:
                    return jsonify({"success": False, "message": username_error}), 400

                if not tg_max_age_raw.isdigit() or not (30 <= int(tg_max_age_raw) <= 86400):
                    return jsonify(
                        {
                            "success": False,
                            "message": "Срок действия Telegram авторизации должен быть в диапазоне 30..86400 секунд",
                        }
                    ), 400

                tg_max_age_value = int(tg_max_age_raw)

                set_env_value("TELEGRAM_AUTH_BOT_USERNAME", tg_username)
                set_env_value("TELEGRAM_AUTH_MAX_AGE_SECONDS", str(tg_max_age_value))
                os.environ["TELEGRAM_AUTH_BOT_USERNAME"] = tg_username
                os.environ["TELEGRAM_AUTH_MAX_AGE_SECONDS"] = str(tg_max_age_value)

                if tg_token_raw is not None:
                    tg_token, token_error = _normalize_telegram_bot_token(tg_token_raw)
                    if token_error:
                        return jsonify({"success": False, "message": token_error}), 400
                    set_env_value("TELEGRAM_AUTH_BOT_TOKEN", tg_token)
                    os.environ["TELEGRAM_AUTH_BOT_TOKEN"] = tg_token

                log_telegram_audit_event(
                    "mini_settings_telegram_auth",
                    details=(
                        f"bot={tg_username or '-'} max_age={tg_max_age_value} "
                        f"token_updated={1 if tg_token_raw is not None else 0}"
                    ),
                )
                log_user_action_event(
                    "settings_telegram_auth_update",
                    target_type="telegram_auth",
                    target_name=(tg_username or "-"),
                    details=(
                        f"max_age={tg_max_age_value} "
                        f"token_updated={1 if tg_token_raw is not None else 0} via=tg-mini"
                    ),
                )

                return jsonify(
                    {
                        "success": True,
                        "message": "Настройки Telegram авторизации сохранены",
                        "settings": _build_tg_mini_settings_payload(),
                    }
                )

            if section == "restart_service":
                task = enqueue_background_task(
                    "restart_service",
                    task_restart_service,
                    created_by_username=session.get("username"),
                    queued_message="Перезапуск службы поставлен в очередь",
                )
                log_telegram_audit_event(
                    "mini_restart_service",
                    details=f"task_id={task.id}",
                )
                log_user_action_event(
                    "settings_restart_service",
                    target_type="service",
                    target_name="admin-antizapret.service",
                    details=f"task_id={task.id} via=tg-mini",
                )
                return jsonify(
                    {
                        "success": True,
                        "message": "Перезапуск службы запущен в фоне",
                        "task_id": task.id,
                    }
                )

            if section == "update_system":
                return jsonify(
                    {
                        "success": False,
                        "message": "Используйте /update_system для запуска обновления",
                    }
                ), 400

            return jsonify({"success": False, "message": "Неизвестная операция"}), 400
        except Exception as e:
            app.logger.error("Ошибка API tg-mini settings: %s", e)
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
