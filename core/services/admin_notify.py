import threading
import psutil
from datetime import datetime, timedelta

from core.services.audit_view_presenter import (
    _mini_protocol_label,
    parse_mini_details_kv,
    user_action_tg_action_line,
)
from core.services.tg_notify import send_tg_message

CLIENT_BLOCK_NOTIFY_EVENTS = frozenset({
    "openvpn_client_block_toggle",
    "wg_client_temp_block_set",
    "wg_client_permanent_block_set",
    "wg_client_block_clear",
})

SETTINGS_CHANGE_NOTIFY = frozenset({
    # Основные настройки
    "settings_port_update",
    "settings_telegram_auth_update",
    "settings_nightly_update",
    "settings_backup_update",
    "settings_backup_create",
    "settings_backup_test_telegram",
    "settings_backup_restore",
    "settings_backup_delete",
    "settings_restart_service",
    "settings_public_download_toggle",
    # QR
    "settings_qr_ttl_update",
    "settings_qr_pin_update",
    "settings_qr_pin_clear",
    "settings_qr_max_downloads_update",
    # IP-ограничения
    "settings_ip_add",
    "settings_ip_add_temp",
    "settings_ip_remove",
    "settings_ip_remove_temp",
    "settings_ip_clear",
    "settings_ip_bulk_enable",
    "settings_ip_add_from_file",
    "settings_ip_files_sync",
    "settings_ip_file_toggle",
    # Пользователи
    "settings_user_password_update",
    "settings_user_role_update",
    "settings_user_telegram_update",
    # CIDR / Фильтры и сервисы
    "settings_cidr_update_queued",
    "settings_cidr_rollback_queued",
    "settings_cidr_games_sync",
    "settings_cidr_total_limit_update",
    "settings_cidr_db_refresh_queued",
    "settings_cidr_generate_from_db",
    "settings_cidr_preset_create",
    "settings_cidr_preset_update",
    "settings_cidr_preset_delete",
    "settings_cidr_preset_reset",
    "settings_antifilter_refresh",
    "settings_run_doall",
})

SETTINGS_CHANGE_LABELS = {
    # Основные настройки
    "settings_port_update": "Изменён порт",
    "settings_telegram_auth_update": "Изменены настройки Telegram-авторизации",
    "settings_nightly_update": "Изменено расписание ночного рестарта",
    "settings_backup_update": "Изменены настройки бэкапов",
    "settings_backup_create": "Создан бэкап",
    "settings_backup_test_telegram": "Тестовый бэкап в Telegram",
    "settings_backup_restore": "Запущено восстановление из бэкапа",
    "settings_backup_delete": "Удалён бэкап",
    "settings_restart_service": "Перезапуск сервиса",
    "settings_public_download_toggle": "Изменён публичный доступ к конфигам",
    # QR
    "settings_qr_ttl_update": "Изменён TTL QR-ссылок",
    "settings_qr_pin_update": "Обновлён PIN для QR",
    "settings_qr_pin_clear": "Сброшен PIN для QR",
    "settings_qr_max_downloads_update": "Изменён лимит загрузок QR",
    # IP-ограничения
    "settings_ip_add": "Добавлен IP в белый список",
    "settings_ip_add_temp": "Добавлен временный IP в белый список",
    "settings_ip_remove": "Удалён IP из белого списка",
    "settings_ip_remove_temp": "Удалён временный IP из белого списка",
    "settings_ip_clear": "Очищен список IP",
    "settings_ip_bulk_enable": "Массовое включение IP-файлов",
    "settings_ip_add_from_file": "Добавлены IP из файла",
    "settings_ip_files_sync": "Сверка IP-файлов",
    "settings_ip_file_toggle": "Включение/отключение IP-файла",
    # Пользователи
    "settings_user_password_update": "Изменён пароль пользователя",
    "settings_user_role_update": "Изменена роль пользователя",
    "settings_user_telegram_update": "Изменён Telegram ID пользователя",
    # CIDR / Фильтры и сервисы
    "settings_cidr_update_queued": "Обновление CIDR-файлов",
    "settings_cidr_rollback_queued": "Откат CIDR-файлов",
    "settings_cidr_games_sync": "Синхронизация игровых фильтров",
    "settings_cidr_total_limit_update": "Изменён лимит CIDR",
    "settings_cidr_db_refresh_queued": "Обновление CIDR из базы",
    "settings_cidr_generate_from_db": "Генерация CIDR из базы",
    "settings_cidr_preset_create": "Создан CIDR-пресет",
    "settings_cidr_preset_update": "Обновлён CIDR-пресет",
    "settings_cidr_preset_delete": "Удалён CIDR-пресет",
    "settings_cidr_preset_reset": "Сброс CIDR-пресета до базовых значений",
    "settings_antifilter_refresh": "Обновление AntiFilter",
    "settings_run_doall": "Перегенерация конфигурации VPN (doall.sh)",
}

SETTINGS_TG_TITLES = {
    "settings_port_update": "Порт панели",
    "settings_telegram_auth_update": "Авторизация Telegram",
    "settings_nightly_update": "Ночной рестарт",
    "settings_backup_update": "Бэкапы",
    "settings_backup_create": "Бэкапы",
    "settings_backup_test_telegram": "Бэкапы",
    "settings_backup_restore": "Бэкапы",
    "settings_backup_delete": "Бэкапы",
    "settings_restart_service": "Перезапуск сервиса",
    "settings_public_download_toggle": "Публичное скачивание",
    "settings_qr_ttl_update": "QR-ссылки",
    "settings_qr_pin_update": "PIN QR-ссылок",
    "settings_qr_pin_clear": "PIN QR-ссылок",
    "settings_qr_max_downloads_update": "Лимит QR-скачиваний",
    "settings_ip_add": "Белый список IP",
    "settings_ip_add_temp": "Белый список IP",
    "settings_ip_remove": "Белый список IP",
    "settings_ip_remove_temp": "Белый список IP",
    "settings_ip_clear": "Белый список IP",
    "settings_ip_bulk_enable": "IP-файлы",
    "settings_ip_add_from_file": "Белый список IP",
    "settings_ip_files_sync": "Сверка IP-файлов",
    "settings_ip_file_toggle": "Фильтр IP",
    "settings_user_password_update": "Пароль пользователя",
    "settings_user_role_update": "Роль пользователя",
    "settings_user_telegram_update": "Telegram ID",
    "settings_cidr_update_queued": "Обновление CIDR",
    "settings_cidr_rollback_queued": "Откат CIDR",
    "settings_cidr_games_sync": "Игровые фильтры",
    "settings_cidr_total_limit_update": "Лимит CIDR",
    "settings_cidr_db_refresh_queued": "База CIDR",
    "settings_cidr_generate_from_db": "Генерация CIDR",
    "settings_cidr_preset_create": "CIDR-пресет",
    "settings_cidr_preset_update": "CIDR-пресет",
    "settings_cidr_preset_delete": "CIDR-пресет",
    "settings_cidr_preset_reset": "CIDR-пресет",
    "settings_antifilter_refresh": "AntiFilter",
    "settings_run_doall": "Применение изменений",
}

# These are one-shot actions (no before/after value)
SETTINGS_ACTION_EVENTS = frozenset({
    "settings_restart_service",
    "settings_backup_create",
    "settings_backup_test_telegram",
    "settings_backup_restore",
    "settings_backup_delete",
    "settings_run_doall",
    "settings_cidr_update_queued",
    "settings_cidr_rollback_queued",
    "settings_cidr_db_refresh_queued",
    "settings_cidr_generate_from_db",
    "settings_cidr_games_sync",
    "settings_ip_files_sync",
    "settings_antifilter_refresh",
    "settings_cidr_preset_reset",
})

# Maps internal event_type to the preference key stored in user.tg_notify_events
_PREF_KEY_MAP = {
    "tg_login_unlinked": "tg_unlinked",
    "tg_mini_login_unlinked": "tg_unlinked",
    "config_recreate": "config_create",
}


def _fmt_code(value: str | None) -> str:
    text = str(value or "").strip()
    return f"<code>{text or '—'}</code>"


def _fmt_protocol(target_type: str | None) -> str:
    kind = str(target_type or "").strip().lower()
    if kind in {"wireguard", "wg", "amneziawg", "amnezia"}:
        wg = _mini_protocol_label("wg")
        awg = _mini_protocol_label("amneziawg")
        if kind in {"wireguard", "wg"}:
            return wg
        return awg
    label = _mini_protocol_label(kind)
    if label != "неизвестно":
        return label
    return ""


def _protocol_emoji(target_type: str | None) -> str:
    kind = str(target_type or "").strip().lower()
    if kind in {"openvpn", "ovpn"}:
        return "🔐"
    if kind in {"wireguard", "wg"}:
        return "🛡️"
    if kind in {"amneziawg", "amnezia"}:
        return "🌀"
    return "📄"


def _fmt_config_object(target_type: str | None, target_name: str | None) -> str:
    protocol = _fmt_protocol(target_type)
    emoji = _protocol_emoji(target_type)
    name = _fmt_code(target_name)
    if protocol:
        return f"{emoji} {protocol} 📁 {name}"
    return f"📁 {name}"


def _fmt_action_config(verb: str, target_type: str | None, target_name: str | None) -> str:
    verb_text = (verb or "").strip()
    if verb_text:
        verb_text = verb_text[0].upper() + verb_text[1:]
    return f"{verb_text} конфигурацию {_fmt_config_object(target_type, target_name)}"


def _format_notify(title: str, actor_line: str | None, action_line: str, when: str) -> str:
    lines = [title]
    if actor_line:
        lines.append(actor_line)
    lines.append(action_line)
    lines.append(when)
    return "\n".join(lines)


def _format_notify_system(title: str, action_line: str, when: str) -> str:
    return f"{title}\n{action_line}\n{when}"


def _fmt_actor(actor_username: str | None, *, as_admin: bool = False) -> str:
    icon = "👨‍💼" if as_admin else "👤"
    role = "Администратор" if as_admin else "Пользователь"
    return f"{icon} {role} {_fmt_code(actor_username)}"


def _fmt_ip(remote_addr: str | None) -> str:
    return f"🌐 IP {_fmt_code(remote_addr)}"


def _fmt_when(now: str) -> str:
    return f"🕐 {now}"


def _resolve_client_block_action(details: str | None) -> str:
    detail_map = parse_mini_details_kv(details)
    action = str(detail_map.get("action") or "").strip().lower()
    if action in {"temp_block", "permanent_block", "unblock"}:
        return action
    if detail_map.get("manual_unblock") == "1":
        return "unblock"
    if detail_map.get("manual_permanent") == "1":
        return "permanent_block"
    if detail_map.get("days") and detail_map.get("blocked") not in {"0", "1"}:
        return "temp_block"
    blocked = detail_map.get("blocked")
    if blocked == "0":
        return "unblock"
    if blocked == "1":
        return "permanent_block"
    return ""


def _build_client_ban_message(
    actor_admin: str,
    target_type: str | None,
    target_name: str | None,
    details: str | None,
    when: str,
) -> str | None:
    client = _fmt_config_object(target_type, target_name)
    action = _resolve_client_block_action(details)
    detail_map = parse_mini_details_kv(details)
    days = detail_map.get("days")
    block_until = detail_map.get("block_until")

    if action == "unblock":
        return _format_notify(
            "🟢 <b>Разблокировка клиента</b>",
            actor_admin,
            f"Разблокировал клиента {client}",
            when,
        )
    if action == "permanent_block":
        return _format_notify(
            "🔴 <b>Постоянная блокировка</b>",
            actor_admin,
            f"Заблокировал клиента {client} бессрочно (до ручной разблокировки)",
            when,
        )
    if action == "temp_block":
        duration = f"на {days} дн." if days else "временно"
        if block_until:
            duration = f"{duration}, до {_fmt_code(block_until)}"
        return _format_notify(
            "⏱️ <b>Временная блокировка</b>",
            actor_admin,
            f"Временно заблокировал клиента {client} {duration}",
            when,
        )
    return None


class AdminNotifyService:
    def __init__(self, *, user_model, get_env_value, logger):
        self.user_model = user_model
        self.get_env_value = get_env_value
        self.logger = logger
        self._monitor_cooldowns: dict = {}
        self._monitor_lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, event_type, *, actor_username=None, target_name=None,
             target_type=None, remote_addr=None, details=None,
             subject_name=None):
        try:
            bot_token = (self.get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
            if not bot_token:
                return

            pref_key = _PREF_KEY_MAP.get(event_type, event_type)
            notify_users = [
                u for u in self.user_model.query.filter(
                    self.user_model.telegram_id.isnot(None)
                ).all()
                if u.has_tg_notify_event(pref_key)
            ]
            if not notify_users:
                return

            text = self._build_text(
                event_type,
                actor_username,
                target_name,
                target_type,
                remote_addr,
                details,
                subject_name,
            )
            if text is None:
                return

            for u in notify_users:
                send_tg_message(bot_token, u.telegram_id, text)
        except Exception as exc:
            self.logger.warning("TG admin notify error: %s", exc)

    def start_monitor(self):
        t = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="resource-monitor",
        )
        t.start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_text(self, event_type, actor_username, target_name,
                    target_type, remote_addr, details, subject_name=None):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        when = _fmt_when(now)
        actor_admin = _fmt_actor(actor_username, as_admin=True)
        actor_user = _fmt_actor(actor_username, as_admin=False)
        ip = _fmt_ip(remote_addr)

        if event_type == "login_success":
            return _format_notify(
                "✅ <b>Вход в панель</b>",
                actor_user,
                f"Вошёл в панель · {ip}",
                when,
            )
        if event_type == "login_failed":
            return _format_notify_system(
                "⚠️ <b>Неудачный вход</b>",
                f"🔑 Логин {_fmt_code(actor_username)} · {ip}",
                when,
            )
        if event_type in ("tg_login_unlinked", "tg_mini_login_unlinked"):
            via = "📱 мини-приложение" if "mini" in event_type else "✈️ Телеграм"
            return _format_notify_system(
                "🚫 <b>TG ID не привязан</b>",
                f"Попытка входа через {via} · 🆔 {_fmt_code(target_name)} · {ip}",
                when,
            )
        if event_type == "config_create":
            return _format_notify(
                "✨ <b>Создание конфига</b>",
                actor_admin,
                _fmt_action_config("создал", target_type, target_name),
                when,
            )
        if event_type == "config_recreate":
            return _format_notify(
                "🔄 <b>Пересоздание конфига</b>",
                actor_admin,
                _fmt_action_config("пересоздал", target_type, target_name),
                when,
            )
        if event_type == "config_delete":
            return _format_notify(
                "🗑️ <b>Удаление конфига</b>",
                actor_admin,
                _fmt_action_config("удалил", target_type, target_name),
                when,
            )
        if event_type == "user_create":
            extra = f" · 📝 {_fmt_code(details)}" if details else ""
            return _format_notify(
                "➕ <b>Новый пользователь</b>",
                actor_admin,
                f"Добавил пользователя 🆔 {_fmt_code(target_name)}{extra}",
                when,
            )
        if event_type == "user_delete":
            return _format_notify(
                "➖ <b>Удаление пользователя</b>",
                actor_admin,
                f"Удалил пользователя 🆔 {_fmt_code(target_name)}",
                when,
            )
        if event_type == "client_ban":
            block_text = _build_client_ban_message(
                actor_admin, target_type, target_name, details, when,
            )
            if block_text:
                return block_text
            return _format_notify(
                "🔒 <b>Статус клиента</b>",
                actor_admin,
                f"Изменил статус блокировки для {_fmt_config_object(target_type, target_name)}",
                when,
            )
        if event_type == "settings_change":
            if target_name == "settings_ip_file_toggle" and details:
                parts = details.split("|")
                is_on = parts[0] == "вкл" if parts else False
                display = parts[1] if len(parts) > 1 else "—"
                ip_info = parts[2] if len(parts) > 2 else ""
                verb = "Включил" if is_on else "Отключил"
                suffix = f" · 📋 {ip_info}" if ip_info else ""
                icon = "✅" if is_on else "🔴"
                return _format_notify(
                    f"{icon} <b>Фильтр IP</b>",
                    actor_admin,
                    f"{verb} 🗂️ <code>{display}</code>{suffix}",
                    when,
                )
            settings_key = str(target_name or "").strip()
            tg_title = SETTINGS_TG_TITLES.get(settings_key, "Изменение настроек")
            action_line = user_action_tg_action_line(
                settings_key,
                details=details,
                target_name=subject_name,
                target_type=target_type,
            )
            icon = "🔧" if settings_key in SETTINGS_ACTION_EVENTS else "⚙️"
            return _format_notify(
                f"{icon} <b>{tg_title}</b>",
                actor_admin,
                action_line,
                when,
            )
        if event_type == "high_cpu":
            metric = _fmt_code(details) if details else "—"
            return _format_notify_system(
                "🔥 <b>Высокая нагрузка процессора</b>",
                f"📊 {metric}",
                when,
            )
        if event_type == "high_ram":
            metric = _fmt_code(details) if details else "—"
            return _format_notify_system(
                "💾 <b>Высокая нагрузка памяти</b>",
                f"📊 {metric}",
                when,
            )
        return None

    def _monitor_loop(self):
        import time
        time.sleep(15)
        psutil.cpu_percent(interval=None)
        time.sleep(1)
        while True:
            try:
                cpu_thr = int((self.get_env_value("MONITOR_CPU_THRESHOLD", "90") or "90").strip())
                ram_thr = int((self.get_env_value("MONITOR_RAM_THRESHOLD", "90") or "90").strip())
                cooldown_min = int((self.get_env_value("MONITOR_COOLDOWN_MINUTES", "30") or "30").strip())
                interval_sec = int((self.get_env_value("MONITOR_CHECK_INTERVAL_SECONDS", "60") or "60").strip())

                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                now = datetime.utcnow()
                cooldown = timedelta(minutes=cooldown_min)

                with self._monitor_lock:
                    for event_type, value, threshold in (
                        ("high_cpu", cpu, cpu_thr),
                        ("high_ram", ram, ram_thr),
                    ):
                        if value >= threshold:
                            last = self._monitor_cooldowns.get(event_type)
                            if last is None or (now - last) >= cooldown:
                                self._monitor_cooldowns[event_type] = now
                                self.send(event_type,
                                          details=f"{value:.1f}% (порог {threshold}%)")

                time.sleep(max(9, interval_sec - 1))
            except Exception as exc:
                self.logger.warning("Resource monitor error: %s", exc)
                import time as _t
                _t.sleep(60)
