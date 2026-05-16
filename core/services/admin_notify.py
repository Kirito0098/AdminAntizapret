import threading
import psutil
from datetime import datetime, timedelta

from core.services.tg_notify import send_tg_message

SETTINGS_CHANGE_NOTIFY = frozenset({
    # Основные настройки
    "settings_port_update",
    "settings_telegram_auth_update",
    "settings_nightly_update",
    "settings_restart_service",
    "settings_public_download_toggle",
    # QR
    "settings_qr_ttl_update",
    "settings_qr_pin_update",
    "settings_qr_pin_clear",
    "settings_qr_max_downloads_update",
    # IP-ограничения
    "settings_ip_add",
    "settings_ip_remove",
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
    "settings_restart_service": "Перезапуск сервиса",
    "settings_public_download_toggle": "Изменён публичный доступ к конфигам",
    # QR
    "settings_qr_ttl_update": "Изменён TTL QR-ссылок",
    "settings_qr_pin_update": "Обновлён PIN для QR",
    "settings_qr_pin_clear": "Сброшен PIN для QR",
    "settings_qr_max_downloads_update": "Изменён лимит загрузок QR",
    # IP-ограничения
    "settings_ip_add": "Добавлен IP в белый список",
    "settings_ip_remove": "Удалён IP из белого списка",
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

# These are one-shot actions (no before/after value); shown with 🔧 header
SETTINGS_ACTION_EVENTS = frozenset({
    "settings_restart_service",
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


class AdminNotifyService:
    def __init__(self, *, user_model, get_env_value, logger):
        self.user_model = user_model
        self.get_env_value = get_env_value
        self.logger = logger
        self._monitor_cooldowns: dict = {}
        self._monitor_lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, event_type, *, actor_username=None, target_name=None,
             remote_addr=None, details=None):
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

            text = self._build_text(event_type, actor_username, target_name,
                                    remote_addr, details)
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
                    remote_addr, details):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        a = f"<code>{actor_username or '—'}</code>"
        ip = f"<code>{remote_addr or '—'}</code>"
        t = f"<code>{target_name or '—'}</code>"
        d = f"\n🔄 <code>{details}</code>" if details else ""

        if event_type == "login_success":
            return f"✅ <b>Успешный вход</b>\n👤 {a}\n🌐 IP: {ip}\n🕐 {now}"
        if event_type == "login_failed":
            return f"⚠️ <b>Неудачная попытка входа</b>\n👤 Логин: {a}\n🌐 IP: {ip}\n🕐 {now}"
        if event_type in ("tg_login_unlinked", "tg_mini_login_unlinked"):
            via = "Mini App" if "mini" in event_type else "Telegram"
            return (f"🚫 <b>Вход через {via}: TG ID не привязан</b>\n"
                    f"🆔 TG ID: {t}\n🌐 IP: {ip}\n🕐 {now}")
        if event_type in ("config_create", "config_recreate"):
            verb = "Пересоздан" if event_type == "config_recreate" else "Создан"
            return f"📄 <b>{verb} конфиг</b>\n📁 {t}\n👤 {a}\n🕐 {now}"
        if event_type == "config_delete":
            return f"🗑 <b>Удалён конфиг</b>\n📁 {t}\n👤 {a}\n🕐 {now}"
        if event_type == "user_create":
            return f"👤 <b>Добавлен пользователь</b>\n🆔 {t}{d}\n👤 Кем: {a}\n🕐 {now}"
        if event_type == "user_delete":
            return f"❌ <b>Удалён пользователь</b>\n🆔 {t}\n👤 Кем: {a}\n🕐 {now}"
        if event_type == "client_ban":
            if details and "blocked=1" in details:
                ban_status = "🔴 Заблокирован"
            elif details and "blocked=0" in details:
                ban_status = "🟢 Разблокирован"
            else:
                ban_status = "Изменён статус"
            return f"🔒 <b>Блокировка клиента</b>\n📁 {t}\n{ban_status}\n👤 {a}\n🕐 {now}"
        if event_type == "settings_change":
            if target_name == "settings_ip_file_toggle" and details:
                parts = details.split("|")
                is_on = parts[0] == "вкл" if parts else False
                display = parts[1] if len(parts) > 1 else "—"
                ip_info = parts[2] if len(parts) > 2 else ""
                icon = "✅" if is_on else "🔴"
                verb = "Включён" if is_on else "Отключён"
                suffix = f" ({ip_info})" if ip_info else ""
                return f"{icon} <b>{verb} фильтр: {display}{suffix}</b>\n👤 {a}\n🕐 {now}"
            label = SETTINGS_CHANGE_LABELS.get(target_name, target_name or "—")
            if target_name in SETTINGS_ACTION_EVENTS:
                # One-shot action — no before/after value
                ctx = f"\n📋 <code>{details}</code>" if details else ""
                return f"🔧 <b>Действие выполнено</b>\n📌 {label}{ctx}\n👤 {a}\n🕐 {now}"
            else:
                # Value change — show old → new
                return f"⚙️ <b>Изменены настройки</b>\n📝 {label}{d}\n👤 {a}\n🕐 {now}"
        if event_type == "high_cpu":
            return f"🔥 <b>Высокая нагрузка CPU</b>{d}\n🕐 {now}"
        if event_type == "high_ram":
            return f"💾 <b>Высокая нагрузка RAM</b>{d}\n🕐 {now}"
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
