from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, make_response, jsonify, flash
import subprocess
import os
from werkzeug.utils import secure_filename
from flask import abort
import shlex
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)

# Путь к директориям с конфигурациями
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

# Список пользователей
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
    # Валидация option
    if not option.isdigit():
        raise ValueError("Недопустимый параметр option")

    # Экранирование всех параметров
    safe_client_name = shlex.quote(client_name)
    command = ['./client.sh', option, safe_client_name]
    
    if cert_expire:
        if not cert_expire.isdigit() or not (MIN_CERT_EXPIRE <= int(cert_expire) <= MAX_CERT_EXPIRE):
            raise ValueError("Некорректный срок действия сертификата")
        command.append(cert_expire)
    
    # Безопасный вызов subprocess
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
def find_config_files(dirs, extensions):
    found_files = []
    for directory in dirs:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                for file in files:
                    if any(file.endswith(ext) for ext in extensions):
                        found_files.append(os.path.join(root, file))
    return found_files

def get_config_files():
    return (
        find_config_files(CONFIG_PATHS["openvpn"], ['.ovpn']),
        find_config_files(CONFIG_PATHS["wg"], ['.conf']),
        find_config_files(CONFIG_PATHS["amneziawg"], ['.conf'])
    )

# Проверка авторизации
def is_authenticated():
    return 'username' in session

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Пожалуйста, войдите в систему для доступа к этой странице. Если у вас нет учетной записи, обратитесь к администратору.', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Главная страница
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'GET':
        # Отображение главной страницы
        openvpn_files, wg_files, amneziawg_files = get_config_files()
        return render_template('index.html', 
                               openvpn_files=openvpn_files, 
                               wg_files=wg_files, 
                               amneziawg_files=amneziawg_files)

    if request.method == 'POST':
        try:
            option = request.form.get('option')
            client_name = request.form.get('client-name', '').strip()
            cert_expire = request.form.get('work-term', '').strip()

            # Проверка обязательных параметров
            if not option or not client_name:
                return jsonify({"success": False, "message": "Не указаны обязательные параметры."}), 400

            # Выполнение логики
            stdout, stderr = run_bash_script(option, client_name, cert_expire)
            return jsonify({"success": True, "message": "Операция выполнена успешно.", "output": stdout})
        except subprocess.CalledProcessError as e:
            return jsonify({"success": False, "message": f"Ошибка выполнения скрипта: {e.stderr}", "output": e.stdout}), 500
        except Exception as e:
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

@app.route('/home')
@login_required
def home():
    return render_template('index.html')

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
        
        flash('Неверные учетные данные. Попробуйте снова.', 'error')  # Добавлено 'error'
        return redirect(url_for('login'))
    
    return render_template('login.html')

# Страница выхода
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# Роут для скачивания конфигурационных файлов (адаптирован под CONFIG_PATHS)
@app.route('/download/<file_type>/<filename>')
@login_required
def download(file_type, filename):
    safe_filename = secure_filename(filename)
    if safe_filename != filename:
        abort(400, description="Некорректное имя файла")
    
    allowed_types = ['openvpn', 'wg', 'amneziawg']
    if file_type not in allowed_types:
        abort(404, description="Тип файла не поддерживается")
    
    extensions = {
        'openvpn': ['.ovpn'],
        'wg': ['.conf'],
        'amneziawg': ['.conf']
    }
    
    if not any(safe_filename.endswith(ext) for ext in extensions[file_type]):
        abort(400, description="Недопустимое расширение файла")
    
    file_path = None
    for config_dir in CONFIG_PATHS[file_type]:
        try:
            potential_path = os.path.abspath(os.path.join(config_dir, safe_filename))
            if not potential_path.startswith(os.path.abspath(config_dir)):
                continue
            if os.path.exists(potential_path):
                file_path = potential_path
                break
        except Exception:
            continue
    
    if file_path and os.path.exists(file_path):
        return send_from_directory(
            os.path.dirname(file_path),
            os.path.basename(file_path),
            as_attachment=True
        )
    abort(404, description="Файл не найден")
        
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
                # Сохраняем изменения в файл
                with open(files[file_type], 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Перезапуск скрипта для применения изменений
                result = subprocess.run(
                    ['/root/antizapret/doall.sh'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                return jsonify({"success": True, "message": "Файл успешно обновлен и изменения применены.", "output": result.stdout})
            except subprocess.CalledProcessError as e:
                return jsonify({
                    "success": False,
                    "message": f"Ошибка выполнения скрипта: {e.stderr}",
                    "output": e.stdout
                }), 500
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
        return jsonify({
            "success": False,
            "message": f"Ошибка выполнения скрипта: {e.stderr}",
            "output": e.stdout
        }), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)