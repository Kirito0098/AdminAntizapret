from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify, flash, abort, send_file
import subprocess
import os
import io
import qrcode
from qrcode.image.pil import PilImage
from PIL import Image
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import shlex
import psutil
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import time

load_dotenv() 

port = int(os.getenv('APP_PORT', '5050'))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
csrf = CSRFProtect(app) 

CONFIG_PATHS = {
    "openvpn": [
        '/root/antizapret/client/openvpn/antizapret',
        '/root/antizapret/client/openvpn/vpn'
    ],
    "wg": [
        '/root/antizapret/client/wireguard/antizapret',
        '/root/antizapret/client/wireguard/vpn'
    ],
    "amneziawg": [
        '/root/antizapret/client/amneziawg/antizapret',
        '/root/antizapret/client/amneziawg/vpn'
    ]
}

MIN_CERT_EXPIRE = 1
MAX_CERT_EXPIRE = 365

# Настройка БД
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Секретный ключ для сессий
app.secret_key = os.urandom(24)

# Модель пользователя для работы с БД
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Запуск Bash-скрипта с передачей параметров
def run_bash_script(option, client_name, cert_expire=None):
    if not option.isdigit():
        raise ValueError("Некорректный параметр option")

    safe_client_name = shlex.quote(client_name)
    command = ['./client.sh', option, safe_client_name]

    if cert_expire:
        if not cert_expire.isdigit() or not (MIN_CERT_EXPIRE <= int(cert_expire) <= MAX_CERT_EXPIRE):
            raise ValueError("Некорректный срок действия сертификата")
        command.append(cert_expire)

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command, output=result.stdout, stderr=result.stderr)
    return result.stdout, result.stderr

# Получение списка конфигурационных файлов
def get_config_files():
    openvpn_files, wg_files, amneziawg_files = [], [], []

    for directory in CONFIG_PATHS["openvpn"]:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                openvpn_files.extend(os.path.join(root, file) for file in files if file.endswith('.ovpn'))

    for directory in CONFIG_PATHS["wg"]:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                wg_files.extend(os.path.join(root, file) for file in files if file.endswith('.conf'))

    for directory in CONFIG_PATHS["amneziawg"]:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                amneziawg_files.extend(os.path.join(root, file) for file in files if file.endswith('.conf'))

    return openvpn_files, wg_files, amneziawg_files

# Проверка авторизации
def is_authenticated():
    return 'username' in session

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Пожалуйста, войдите в систему для доступа к этой странице.', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Главная страница
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'GET':
        openvpn_files, wg_files, amneziawg_files = get_config_files()
        return render_template('index.html', openvpn_files=openvpn_files, wg_files=wg_files, amneziawg_files=amneziawg_files)

    if request.method == 'POST':
        try:
            option = request.form.get('option')
            client_name = request.form.get('client-name', '').strip()
            cert_expire = request.form.get('work-term', '').strip()

            if not option or not client_name:
                return jsonify({"success": False, "message": "Не указаны обязательные параметры."}), 400

            stdout, stderr = run_bash_script(option, client_name, cert_expire)
            return jsonify({"success": True, "message": "Операция выполнена успешно.", "output": stdout})
        except subprocess.CalledProcessError as e:
            return jsonify({"success": False, "message": f"Ошибка выполнения скрипта: {e.stderr}", "output": e.stdout}), 500
        except Exception as e:
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

# Страница логина
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['username'] = user.username
            return redirect(url_for('index'))

        flash('Неверные учетные данные. Попробуйте снова.', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

# Страница выхода
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# Декоратор для проверки существования файла
def validate_file(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        file_type = kwargs.get('file_type')
        filename = kwargs.get('filename')
        
        # Проверка безопасного имени файла
        safe_filename = secure_filename(filename)
        if safe_filename != filename:
            abort(400, description="Некорректное имя файла")
            
        # Проверка расширения файла
        extensions = {
            'openvpn': ['.ovpn'],
            'wg': ['.conf'],
            'amneziawg': ['.conf']
        }
        if not any(safe_filename.endswith(ext) for ext in extensions.get(file_type, [])):
            abort(400, description="Недопустимое расширение файла")
            
        # Поиск файла в конфигурационных директориях
        config_dirs = CONFIG_PATHS.get(file_type)
        file_path = None
        if config_dirs:
            for config_dir in config_dirs:
                potential_path = os.path.abspath(os.path.join(config_dir, safe_filename))
                if potential_path.startswith(os.path.abspath(config_dir)) and os.path.exists(potential_path):
                    file_path = potential_path
                    break
        
        if not file_path:
            abort(404, description="Файл не найден")
            
        # Добавляем путь к файлу в kwargs
        kwargs['file_path'] = file_path
        return func(*args, **kwargs)
    return wrapper

# Роут для скачивания конфигурационных файлов
@app.route('/download/<file_type>/<filename>')
@login_required
@validate_file
def download(file_type, filename, file_path):
    basename = os.path.basename(file_path)
    name_parts = basename.split('-')
    extension = basename.split('.')[-1]
    vpn_type = '-AZ' if name_parts[0] == 'antizapret' else ''
    
    if extension == 'ovpn':
        client_name = '-'.join(name_parts[1:-1])
        download_name = f"{client_name}{vpn_type}.{extension}"
    elif extension == 'conf':
        client_name = '-'.join(name_parts[1:-2])
        download_name = f"{client_name}{vpn_type}.{extension}"
    else:
        download_name = basename
    
    return send_from_directory(
        os.path.dirname(file_path),
        os.path.basename(file_path),
        as_attachment=True,
        download_name=download_name
    )

# Роут для формирования QR кода
@app.route('/generate_qr/<file_type>/<filename>')
@login_required
@validate_file
def generate_qr(file_type, filename, file_path):
    try:
        # Читаем содержимое файла
        with open(file_path, 'r') as file:
            config_text = file.read()

        # Создаем QR-код
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(config_text)
        qr.make(fit=True)

        # Создаем изображение
        img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)

        # Конвертируем в байты
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        return send_file(img_byte_arr, mimetype='image/png')

    except Exception as e:
        print(f"Аларм! ошибка: {str(e)}")
        abort(500)

# Роут для редактирования файлов конфигурации
@app.route('/edit-files', methods=['GET', 'POST'])
@login_required
def edit_files():
    files = {
        "include_hosts": "/root/antizapret/config/include-hosts.txt",
        "exclude_hosts": "/root/antizapret/config/exclude-hosts.txt",
        "include_ips": "/root/antizapret/config/include-ips.txt"
    }

    if request.method == 'POST':
        file_type = request.form.get('file_type')
        content = request.form.get('content', '')

        if file_type in files:
            try:
                with open(files[file_type], 'w', encoding='utf-8') as f:
                    f.write(content)

                result = subprocess.run(
                    ['/root/antizapret/doall.sh'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                return jsonify({"success": True, "message": "Файл успешно обновлен и изменения применены.", "output": result.stdout})
            except subprocess.CalledProcessError as e:
                return jsonify({"success": False, "message": f"Ошибка выполнения скрипта: {e.stderr}", "output": e.stdout}), 500
            except Exception as e:
                return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

        return jsonify({"success": False, "message": "Неверный тип файла."}), 400

    file_contents = {}
    for key, path in files.items():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                file_contents[key] = f.read()
        except FileNotFoundError:
            file_contents[key] = ""

    return render_template('edit_files.html', file_contents=file_contents)

# Роут для запуска скрипта doall.sh
@app.route('/run-doall', methods=['POST'])
@login_required
def run_doall():
    try:
        result = subprocess.run(
            ['/root/antizapret/doall.sh'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return jsonify({"success": True, "message": "Скрипт успешно выполнен.", "output": result.stdout})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "message": f"Ошибка выполнения скрипта: {e.stderr}", "output": e.stdout}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

# Функции для получения данных о сервере
def get_cpu_usage():
    return psutil.cpu_percent(interval=1)

def get_memory_usage():
    memory = psutil.virtual_memory()
    return memory.percent

def get_uptime():
    boot_time = psutil.boot_time()
    current_time = time.time()
    uptime_seconds = current_time - boot_time
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(days)}д {int(hours)}ч {int(minutes)}м {int(seconds)}с"

# Маршрут для страницы мониторинга
@app.route('/server_monitor')
def server_monitor():
    try:
        cpu_usage = get_cpu_usage()
        memory_usage = get_memory_usage()
        uptime = get_uptime()
        return render_template('server_monitor.html', cpu_usage=cpu_usage, memory_usage=memory_usage, uptime=uptime)
    except Exception as e:
        app.logger.error(f"Ошибка при загрузке данных мониторинга: {e}")
        return "Ошибка при загрузке данных мониторинга", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)