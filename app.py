from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, make_response
import subprocess
import os

app = Flask(__name__)

# Путь к директориям с конфигурациями
config_dir_openvpn_1 = '/root/antizapret/client/openvpn/antizapret'
config_dir_openvpn_2 = '/root/antizapret/client/openvpn/vpn'
config_dir_wg_1 = '/root/antizapret/client/wireguard/antizapret'
config_dir_wg_2 = '/root/antizapret/client/wireguard/vpn'
config_dir_amneziawg_1 = '/root/antizapret/client/amneziawg/antizapret'
config_dir_amneziawg_2 = '/root/antizapret/client/amneziawg/vpn'

# Секретный ключ для сессий
app.secret_key = os.urandom(24)

# Список пользователей
users = {
    'claymore': '159753qQSIROV',
    'andrew': '1qaz@WSX#EDC',
    'user1': 'password2'
}

# Запуск Bash-скрипта с передачей параметров
def run_bash_script(option, client_name, cert_expire=None):
    command = ['./client.sh', option, client_name]
    if cert_expire:
        command.append(cert_expire)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
@app.route('/', methods=['GET', 'POST'])
def index():
    if not is_authenticated():
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
        
        if users.get(username) == password:
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return 'Неверные данные для входа!', 401
    
    return render_template('login.html')

# Страница выхода
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# Роут для скачивания конфигурационных файлов
@app.route('/download/<file_type>/<filename>')
def download(file_type, filename):
    file_path = None

    if file_type == 'openvpn':
        for config_dir in [config_dir_openvpn_1, config_dir_openvpn_2]:
            potential_path = os.path.join(config_dir, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                break
    elif file_type == 'wg':
        for config_dir in [config_dir_wg_1, config_dir_wg_2]:
            potential_path = os.path.join(config_dir, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                break
    elif file_type == 'amneziawg':
        for config_dir in [config_dir_amneziawg_1, config_dir_amneziawg_2]:
            potential_path = os.path.join(config_dir, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                break
    else:
        return abort(404, description="File type not found")

    if file_path and os.path.exists(file_path):
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), as_attachment=True)
    else:
        return abort(404, description="File not found")
        

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)