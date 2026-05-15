# ip_restriction.py
import ipaddress
import os
import tempfile
import time
from collections import defaultdict
from threading import Lock
from pathlib import Path

from flask import jsonify, make_response, request
from markupsafe import escape


def _env_bool(name, default=False):
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _env_int(name, default, *, minimum=1, maximum=86400):
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


class IPRestriction:
    SCANNER_ENV_KEYS = (
        "IP_BLOCK_SCANNERS",
        "IP_SCANNER_MAX_ATTEMPTS",
        "IP_SCANNER_WINDOW_SECONDS",
        "IP_SCANNER_BAN_SECONDS",
        "IP_BLOCK_IP_BLOCKED_DWELL",
        "IP_BLOCKED_DWELL_SECONDS",
    )

    def __init__(self, env_file_path=None):
        self.allowed_ips = set()
        self.enabled = False
        self.block_scanners = False
        self.scanner_max_attempts = 5
        self.scanner_window_seconds = 60
        self.scanner_ban_seconds = 3600
        self.block_ip_blocked_dwell = True
        self.ip_blocked_dwell_seconds = 120
        self.app = None
        self.env_file_path = Path(env_file_path) if env_file_path else None
        self._scanner_lock = Lock()
        self._scanner_attempts = defaultdict(list)
        self._scanner_bans = {}
        self._ip_blocked_presence = {}
        self._load_from_env()

    def init_app(self, app):
        """Инициализация с приложением Flask"""
        self.app = app
        if self.env_file_path is None:
            # Flask root_path already points to project root in this app layout.
            self.env_file_path = Path(app.root_path) / ".env"

        # Регистрируем обработчик ошибок 403
        @app.errorhandler(403)
        def forbidden_error(e):
            if request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Доступ запрещен с вашего IP-адреса'
                }), 403

            client_ip = escape(self.get_client_ip() or "unknown")
            request_path = escape(request.path or "/")
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Доступ запрещен</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .container {{ max-width: 600px; margin: 0 auto; }}
                    h1 {{ color: #dc3545; }}
                    .ip-box {{
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 20px 0;
                        font-family: monospace;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>403 - Доступ запрещен</h1>
                    <p>Ваш IP-адрес: <strong>{client_ip}</strong></p>
                    <div class="ip-box">
                        IP: {client_ip}<br>
                        Путь: {request_path}
                    </div>
                    <p>Доступ к этой странице разрешен только с определенных IP-адресов.</p>
                    <a href="/login">На страницу входа</a>
                </div>
            </body>
            </html>
            ''', 403

    def _resolve_env_file(self):
        if self.env_file_path:
            return self.env_file_path
        return Path(__file__).resolve().parent.parent / ".env"

    def _get_trusted_proxy_entries(self):
        trusted_raw = os.getenv('TRUSTED_PROXY_IPS', '')
        if self.app is not None:
            trusted_raw = self.app.config.get('TRUSTED_PROXY_IPS', trusted_raw)
        return [entry.strip() for entry in str(trusted_raw).split(',') if entry.strip()]

    def _is_trusted_proxy(self, remote_ip):
        if not remote_ip:
            return False

        entries = self._get_trusted_proxy_entries()
        if not entries:
            return False

        if '*' in entries:
            return True

        try:
            remote_addr = ipaddress.ip_address(remote_ip)
        except ValueError:
            return False

        for entry in entries:
            try:
                if '/' in entry:
                    if remote_addr in ipaddress.ip_network(entry, strict=False):
                        return True
                elif remote_addr == ipaddress.ip_address(entry):
                    return True
            except ValueError:
                continue

        return False

    def _atomic_write_lines(self, file_path, lines):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=f".{file_path.name}.", dir=str(file_path.parent), text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, file_path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    def _normalize_ip_entry(self, ip_or_network):
        value = (ip_or_network or '').strip()
        if not value:
            return None

        try:
            if '/' in value:
                return str(ipaddress.ip_network(value, strict=False))
            return str(ipaddress.ip_address(value))
        except ValueError:
            return None

    def _load_scanner_settings_from_env(self):
        self.block_scanners = _env_bool("IP_BLOCK_SCANNERS", False)
        self.scanner_max_attempts = _env_int(
            "IP_SCANNER_MAX_ATTEMPTS", 5, minimum=1, maximum=100
        )
        self.scanner_window_seconds = _env_int(
            "IP_SCANNER_WINDOW_SECONDS", 60, minimum=10, maximum=3600
        )
        self.scanner_ban_seconds = _env_int(
            "IP_SCANNER_BAN_SECONDS", 3600, minimum=60, maximum=86400
        )
        self.block_ip_blocked_dwell = _env_bool("IP_BLOCK_IP_BLOCKED_DWELL", True)
        self.ip_blocked_dwell_seconds = _env_int(
            "IP_BLOCKED_DWELL_SECONDS", 120, minimum=30, maximum=3600
        )

    def _load_from_env(self):
        """Загружает настройки из переменных окружения"""
        allowed_ips_str = os.getenv('ALLOWED_IPS', '')
        self.allowed_ips = set()
        for entry in allowed_ips_str.split(','):
            normalized = self._normalize_ip_entry(entry)
            if normalized:
                self.allowed_ips.add(normalized)
        self.enabled = bool(self.allowed_ips)
        self._load_scanner_settings_from_env()

    def _apply_env_updates(self, updates):
        """Обновляет несколько ключей в .env одной записью."""
        env_file = self._resolve_env_file()

        if env_file.exists():
            with env_file.open('r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []

        remaining = dict(updates)
        new_lines = []
        for line in lines:
            stripped = line.strip()
            matched_key = None
            for key in list(remaining.keys()):
                if stripped.startswith(f"{key}="):
                    new_lines.append(f"{key}={remaining.pop(key)}\n")
                    matched_key = key
                    break
            if matched_key is None:
                new_lines.append(line)

        for key, value in remaining.items():
            new_lines.append(f"{key}={value}\n")

        self._atomic_write_lines(env_file, new_lines)

        for key, value in updates.items():
            os.environ[key] = value

    def save_to_env(self):
        """Сохраняет настройки в .env файл"""
        allowed_value = ','.join(sorted(self.allowed_ips)) if self.allowed_ips else ''
        self._apply_env_updates({"ALLOWED_IPS": allowed_value})

    def save_scanner_settings_to_env(self):
        updates = {
            "IP_BLOCK_SCANNERS": "true" if self.block_scanners else "false",
            "IP_SCANNER_MAX_ATTEMPTS": str(self.scanner_max_attempts),
            "IP_SCANNER_WINDOW_SECONDS": str(self.scanner_window_seconds),
            "IP_SCANNER_BAN_SECONDS": str(self.scanner_ban_seconds),
            "IP_BLOCK_IP_BLOCKED_DWELL": "true" if self.block_ip_blocked_dwell else "false",
            "IP_BLOCKED_DWELL_SECONDS": str(self.ip_blocked_dwell_seconds),
        }
        self._apply_env_updates(updates)

    def set_scanner_protection(
        self,
        *,
        enabled,
        max_attempts=None,
        window_seconds=None,
        ban_seconds=None,
        block_ip_blocked_dwell=None,
        ip_blocked_dwell_seconds=None,
    ):
        self.block_scanners = bool(enabled)
        if max_attempts is not None:
            self.scanner_max_attempts = max(1, min(100, int(max_attempts)))
        if window_seconds is not None:
            self.scanner_window_seconds = max(10, min(3600, int(window_seconds)))
        if ban_seconds is not None:
            self.scanner_ban_seconds = max(60, min(86400, int(ban_seconds)))
        if block_ip_blocked_dwell is not None:
            self.block_ip_blocked_dwell = bool(block_ip_blocked_dwell)
        if ip_blocked_dwell_seconds is not None:
            self.ip_blocked_dwell_seconds = max(30, min(3600, int(ip_blocked_dwell_seconds)))
        self.save_scanner_settings_to_env()

    def reload_scanner_settings(self):
        self._load_scanner_settings_from_env()

    def get_client_ip(self):
        """Получаем IP клиента"""
        remote_ip = (request.remote_addr or '').strip()
        ip = remote_ip

        if self._is_trusted_proxy(remote_ip):
            if request.headers.get('X-Forwarded-For'):
                ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
            elif request.headers.get('X-Real-IP'):
                ip = request.headers.get('X-Real-IP', '').strip()

        if ip and ip.startswith('::ffff:'):
            ip = ip[7:]

        return ip or remote_ip

    def is_ip_allowed(self, ip_str):
        """Проверяет, разрешен ли IP (одиночный или из подсети)"""
        if not self.enabled:
            return True

        ip_str = (ip_str or '').strip()
        if not ip_str:
            return False

        try:
            client_ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False  # битый IP → запрещаем по умолчанию

        for entry in self.allowed_ips:
            try:
                if '/' in entry:
                    if client_ip in ipaddress.ip_network(entry, strict=False):
                        return True
                elif client_ip == ipaddress.ip_address(entry):
                    return True
            except ValueError:
                continue

        return False

    def _normalize_tracker_ip(self, ip_str):
        ip_str = (ip_str or "").strip()
        if not ip_str:
            return None
        try:
            return str(ipaddress.ip_address(ip_str))
        except ValueError:
            return None

    def _prune_scanner_attempts(self, ip_key, now=None):
        now = now or time.time()
        cutoff = now - self.scanner_window_seconds
        attempts = self._scanner_attempts.get(ip_key, [])
        self._scanner_attempts[ip_key] = [ts for ts in attempts if ts >= cutoff]

    def _is_banned_locked(self, ip_key, now):
        ban_until = self._scanner_bans.get(ip_key)
        if ban_until is None:
            return False
        if ban_until <= now:
            self._scanner_bans.pop(ip_key, None)
            self._scanner_attempts.pop(ip_key, None)
            self._ip_blocked_presence.pop(ip_key, None)
            return False
        return True

    def _apply_ban_locked(self, ip_key, now=None):
        now = now or time.time()
        self._scanner_bans[ip_key] = now + self.scanner_ban_seconds
        self._scanner_attempts.pop(ip_key, None)
        self._ip_blocked_presence.pop(ip_key, None)

    def is_scanner_banned(self, ip_str):
        ip_key = self._normalize_tracker_ip(ip_str)
        if not ip_key:
            return False

        now = time.time()
        with self._scanner_lock:
            return self._is_banned_locked(ip_key, now)

    def touch_ip_blocked_presence(self, ip_str):
        """Отслеживает время на /ip-blocked; при превышении лимита — временный бан."""
        if not self.enabled or not self.block_ip_blocked_dwell:
            return {"banned": False, "tracking": False}

        ip_key = self._normalize_tracker_ip(ip_str)
        if not ip_key:
            return {"banned": False, "tracking": False}

        now = time.time()
        with self._scanner_lock:
            if self._is_banned_locked(ip_key, now):
                ban_until = self._scanner_bans[ip_key]
                return {
                    "banned": True,
                    "tracking": True,
                    "ban_remaining_seconds": int(ban_until - now),
                }

            first_seen = self._ip_blocked_presence.get(ip_key)
            if first_seen is None:
                self._ip_blocked_presence[ip_key] = now
                first_seen = now

            elapsed = now - first_seen
            limit = self.ip_blocked_dwell_seconds
            if elapsed >= limit:
                self._apply_ban_locked(ip_key, now)
                return {
                    "banned": True,
                    "tracking": True,
                    "dwell_exceeded": True,
                    "dwell_seconds": limit,
                    "ban_seconds": self.scanner_ban_seconds,
                }

            return {
                "banned": False,
                "tracking": True,
                "elapsed_seconds": int(elapsed),
                "dwell_seconds": limit,
                "remaining_seconds": max(0, int(limit - elapsed)),
            }

    def record_denied_access(self, ip_str):
        """Учитывает отказ в доступе; при превышении порога — временный бан."""
        ip_key = self._normalize_tracker_ip(ip_str)
        if not ip_key:
            return False

        now = time.time()
        banned = False
        with self._scanner_lock:
            if self._is_banned_locked(ip_key, now):
                return True

            self._prune_scanner_attempts(ip_key, now)
            self._scanner_attempts[ip_key].append(now)
            if len(self._scanner_attempts[ip_key]) >= self.scanner_max_attempts:
                self._apply_ban_locked(ip_key, now)
                banned = True
        return banned

    def should_hard_deny(self, ip_str):
        """Жёсткий отказ без страницы /ip-blocked."""
        if not self.enabled:
            return False
        if self.is_scanner_banned(ip_str):
            return True
        return bool(self.block_scanners)

    def build_hard_deny_response(self, *, message="Forbidden"):
        response = make_response(f"{message}\n", 403)
        response.headers["Connection"] = "close"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def build_denied_json_response(self, client_ip):
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Доступ запрещен с вашего IP-адреса: {client_ip}",
                }
            ),
            403,
        )

    def get_active_scanner_bans(self):
        now = time.time()
        active = []
        with self._scanner_lock:
            expired = []
            for ip_key, ban_until in self._scanner_bans.items():
                if ban_until <= now:
                    expired.append(ip_key)
                else:
                    active.append(
                        {
                            "ip": ip_key,
                            "ban_until": ban_until,
                            "remaining_seconds": int(ban_until - now),
                        }
                    )
            for ip_key in expired:
                self._scanner_bans.pop(ip_key, None)
                self._scanner_attempts.pop(ip_key, None)
                self._ip_blocked_presence.pop(ip_key, None)
        active.sort(key=lambda item: item["ban_until"])
        return active

    def clear_scanner_bans(self):
        with self._scanner_lock:
            self._scanner_bans.clear()
            self._scanner_attempts.clear()
            self._ip_blocked_presence.clear()

    def add_ip(self, ip):
        """Добавляет IP"""
        normalized = self._normalize_ip_entry(ip)
        if normalized is None:
            return False

        self.allowed_ips.add(normalized)
        self.enabled = True
        self.save_to_env()
        return True

    def remove_ip(self, ip):
        """Удаляет IP"""
        normalized = self._normalize_ip_entry(ip)
        targets = [normalized, (ip or '').strip()]
        removed = False

        for target in targets:
            if target and target in self.allowed_ips:
                self.allowed_ips.remove(target)
                removed = True

        if removed:
            if not self.allowed_ips:
                self.enabled = False
            self.save_to_env()
            return True

        return False

    def clear_all(self):
        """Очищает все IP (выключает ограничения)"""
        self.allowed_ips.clear()
        self.enabled = False
        self.save_to_env()

    def get_allowed_ips(self):
        """Возвращает список разрешенных IP"""
        return sorted(list(self.allowed_ips))

    def is_enabled(self):
        """Проверяет, включены ли ограничения"""
        return self.enabled

    def is_scanner_protection_enabled(self):
        return bool(self.block_scanners)

    def get_scanner_settings(self):
        return {
            "enabled": self.block_scanners,
            "max_attempts": self.scanner_max_attempts,
            "window_seconds": self.scanner_window_seconds,
            "ban_seconds": self.scanner_ban_seconds,
            "block_ip_blocked_dwell": self.block_ip_blocked_dwell,
            "ip_blocked_dwell_seconds": self.ip_blocked_dwell_seconds,
            "active_bans": self.get_active_scanner_bans(),
        }


# Глобальный экземпляр
ip_restriction = IPRestriction()
