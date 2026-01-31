# ip_restriction.py
import os
from flask import request, jsonify
import ipaddress

class IPRestriction:
    def __init__(self):
        self.allowed_ips = set()
        self.enabled = False
        self.app = None
        self._load_from_env()

    def init_app(self, app):
        """Инициализация с приложением Flask"""
        self.app = app
        # Регистрируем обработчик ошибок 403
        @app.errorhandler(403)
        def forbidden_error(e):
            if request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Доступ запрещен с вашего IP-адреса'
                }), 403

            client_ip = self.get_client_ip()
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
                        Путь: {request.path}
                    </div>
                    <p>Доступ к этой странице разрешен только с определенных IP-адресов.</p>
                    <a href="/login">На страницу входа</a>
                </div>
            </body>
            </html>
            ''', 403

    def _load_from_env(self):
        """Загружает настройки из переменных окружения"""
        allowed_ips_str = os.getenv('ALLOWED_IPS', '')
        self.allowed_ips = set(ip.strip() for ip in allowed_ips_str.split(',') if ip.strip())
        self.enabled = bool(self.allowed_ips)

    def save_to_env(self):
        """Сохраняет настройки в .env файл"""
        env_file = '/opt/AdminAntizapret/.env'

        # Читаем текущий файл
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
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
        with open(env_file, 'w') as f:
            f.writelines(new_lines)

        # Обновляем переменные окружения
        os.environ['ALLOWED_IPS'] = ','.join(sorted(self.allowed_ips)) if self.allowed_ips else ''

    def get_client_ip(self):
        """Получаем IP клиента"""
        if request.headers.get('X-Forwarded-For'):
            ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            ip = request.headers.get('X-Real-IP')
        else:
            ip = request.remote_addr

        if ip.startswith('::ffff:'):
            ip = ip[7:]

        return ip


    def is_ip_allowed(self, ip_str):
        """Проверяет, разрешен ли IP (одиночный или из подсети)"""
        if not self.enabled:
            return True

    # если ip уже в точном списке — сразу ок
        if ip_str in self.allowed_ips:
            return True

        try:
            client_ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False  # битый IP → запрещаем по умолчанию

        for entry in self.allowed_ips:
            entry = entry.strip()
            if '/' not in entry:
                continue  # одиночные уже проверили выше

            try:
                network = ipaddress.ip_network(entry, strict=False)
                if client_ip in network:
                    return True
            except ValueError:
                # битая запись в allowed_ips — пропускаем, не падаем
                continue

        return False

    def add_ip(self, ip):
        """Добавляет IP"""
        ip = ip.strip()
        if ip:
            self.allowed_ips.add(ip)
            self.enabled = True
            self.save_to_env()
            return True
        return False

    def remove_ip(self, ip):
        """Удаляет IP"""
        if ip in self.allowed_ips:
            self.allowed_ips.remove(ip)
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
