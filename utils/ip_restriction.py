# ip_restriction.py
import ipaddress
import os
import tempfile
from pathlib import Path

from flask import jsonify, request
from markupsafe import escape


class IPRestriction:
    def __init__(self, env_file_path=None):
        self.allowed_ips = set()
        self.enabled = False
        self.app = None
        self.env_file_path = Path(env_file_path) if env_file_path else None
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

    def _load_from_env(self):
        """Загружает настройки из переменных окружения"""
        allowed_ips_str = os.getenv('ALLOWED_IPS', '')
        self.allowed_ips = set()
        for entry in allowed_ips_str.split(','):
            normalized = self._normalize_ip_entry(entry)
            if normalized:
                self.allowed_ips.add(normalized)
        self.enabled = bool(self.allowed_ips)

    def save_to_env(self):
        """Сохраняет настройки в .env файл"""
        env_file = self._resolve_env_file()

        # Читаем текущий файл
        if env_file.exists():
            with env_file.open('r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []

        # Обновляем или добавляем ALLOWED_IPS
        new_lines = []
        found = False
        for line in lines:
            if line.strip().startswith('ALLOWED_IPS='):
                if self.allowed_ips:
                    new_lines.append(f"ALLOWED_IPS={','.join(sorted(self.allowed_ips))}\n")
                else:
                    new_lines.append("ALLOWED_IPS=\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            if self.allowed_ips:
                new_lines.append(f"ALLOWED_IPS={','.join(sorted(self.allowed_ips))}\n")
            else:
                new_lines.append("ALLOWED_IPS=\n")

        # Записываем обратно
        self._atomic_write_lines(env_file, new_lines)

        # Обновляем переменные окружения
        os.environ['ALLOWED_IPS'] = ','.join(sorted(self.allowed_ips)) if self.allowed_ips else ''

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
                # битая запись в allowed_ips — пропускаем, не падаем
                continue

        return False

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

# Глобальный экземпляр
ip_restriction = IPRestriction()
