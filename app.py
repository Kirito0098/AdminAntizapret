from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, make_response
import subprocess
import os
from werkzeug.utils import secure_filename
from flask import abort
import shlex
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Путь к директориям с конфигурациями
config_dir_openvpn_1 = '/root/antizapret/client/openvpn/antizapret'
config_dir_openvpn_2 = '/root/antizapret/client/openvpn/vpn'
config_dir_wg_1 = '/root/antizapret/client/wireguard/antizapret'
config_dir_wg_2 = '/root/antizapret/client/wireguard/vpn'
config_dir_amneziawg_1 = '/root/antizapret/client/amneziawg/antizapret'
config_dir_amneziawg_2 = '/root/antizapret/client/amneziawg/vpn'

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
    # Валидация option (только цифры)
    if not option.isdigit():
        raise ValueError("Некорректный параметр option")
    
    # Экранирование всех параметров
    safe_client_name = shlex.quote(client_name)
    command = ['./client.sh', option, safe_client_name]
    
    if cert_expire:
        if not cert_expire.isdigit() or not (1 <= int(cert_expire) <= 365):
            raise ValueError("Некорректный срок действия сертификата")
        command.append(cert_expire)
    
    # Безопасный вызов subprocess
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False  
    )
    return result.stdout.decode(), result.stderr.decode()

# Получение списка конфигурационных файлов
def get_config_files():
    openvpn_files = []
    wg_files = []
    amneziawg_files = []
    
    # Поиск файлов OpenVPN
    for directory in [config_dir_openvpn_1, config_dir_openvpn_2]:
        if os.path.exists(directory):
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith('.ovpn'):
                        openvpn_files.append(os.path.join(root, file))
    
    # Поиск файлов WireGuard
    for directory in [config_dir_wg_1, config_dir_wg_2]:
        if os.path.exists(directory):
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith('.conf'):
                        wg_files.append(os.path.join(root, file))
    
    # Поиск файлов AmneziaWG
    for directory in [config_dir_amneziawg_1, config_dir_amneziawg_2]:
        if os.path.exists(directory):
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith('.conf'):  # или другое расширение для AmneziaWG
                        amneziawg_files.append(os.path.join(root, file))
    
    return openvpn_files, wg_files, amneziawg_files


# Проверка авторизации
def is_authenticated():
    return 'username' in session

# Главная страница
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Получаем все три списка файлов
    openvpn_files, wg_files, amneziawg_files = get_config_files()

    if request.method == 'POST':
        option = request.form.get('option')
        client_name = request.form.get('client-name')
        cert_expire = request.form.get('work-term')

        if option in ['1', '2', '4', '5', '6']:  # Добавлена опция '6' для AmneziaWG
            stdout, stderr = run_bash_script(option, client_name, cert_expire)
            
            # Обновляем списки файлов после выполнения скрипта
            openvpn_files, wg_files, amneziawg_files = get_config_files()

            response = make_response(render_template('index.html', 
                stdout=stdout, 
                stderr=stderr, 
                openvpn_files=openvpn_files, 
                wg_files=wg_files,
                amneziawg_files=amneziawg_files,
                option=option))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
    
    return render_template('index.html', 
        openvpn_files=openvpn_files, 
        wg_files=wg_files,
        amneziawg_files=amneziawg_files)

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
        
        flash('Неверные учетные данные')
        return redirect(url_for('login'))
    
    return render_template('login.html')

# Страница выхода
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# Роут для скачивания конфигурационных файлов
@app.route('/download/<file_type>/<filename>')
def download(file_type, filename):
    # Проверка и очистка имени файла
    safe_filename = secure_filename(filename)
    if safe_filename != filename:
        abort(400, description="Некорректное имя файла")
    
    # Проверка допустимых типов файлов
    allowed_types = ['openvpn', 'wg', 'amneziawg']
    if file_type not in allowed_types:
        abort(404, description="Тип файла не поддерживается")
    
    # Определяем разрешенные расширения для каждого типа
    extensions = {
        'openvpn': ['.ovpn'],
        'wg': ['.conf'],
        'amneziawg': ['.conf']
    }
    
    # Проверяем расширение файла
    if not any(safe_filename.endswith(ext) for ext in extensions[file_type]):
        abort(400, description="Недопустимое расширение файла")
    
    # Безопасный поиск файла
    file_path = None
    config_dirs = {
        'openvpn': [config_dir_openvpn_1, config_dir_openvpn_2],
        'wg': [config_dir_wg_1, config_dir_wg_2],
        'amneziawg': [config_dir_amneziawg_1, config_dir_amneziawg_2]
    }
    
    for config_dir in config_dirs[file_type]:
        try:
            potential_path = os.path.abspath(os.path.join(config_dir, safe_filename))
            # Дополнительная проверка, что файл внутри разрешенной директории
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
        

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)