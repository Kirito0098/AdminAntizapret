from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
    jsonify,
    flash,
    abort,
    send_file,
    make_response,
)
import subprocess
import os
import re
import io
import qrcode
import random
import string
from qrcode.image.pil import PilImage
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import shlex
import psutil
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import time
import platform

load_dotenv()

port = int(os.getenv("APP_PORT", "5050"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise ValueError("SECRET_KEY is not set in .env!")

csrf = CSRFProtect(app)

CONFIG_PATHS = {
    "openvpn": [
        "/root/antizapret/client/openvpn/antizapret",
        "/root/antizapret/client/openvpn/vpn",
    ],
    "wg": [
        "/root/antizapret/client/wireguard/antizapret",
        "/root/antizapret/client/wireguard/vpn",
    ],
    "amneziawg": [
        "/root/antizapret/client/amneziawg/antizapret",
        "/root/antizapret/client/amneziawg/vpn",
    ],
}

MIN_CERT_EXPIRE = 1
MAX_CERT_EXPIRE = 3650

# Настройка БД
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# Модель пользователя для работы с БД
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class ScriptExecutor:
    def __init__(self):
        self.min_cert_expire = MIN_CERT_EXPIRE
        self.max_cert_expire = MAX_CERT_EXPIRE

    def run_bash_script(self, option, client_name, cert_expire=None):
        if not option.isdigit():
            raise ValueError("Некорректный параметр option")

        safe_client_name = shlex.quote(client_name)
        command = ["./client.sh", option, safe_client_name]

        if cert_expire:
            if not cert_expire.isdigit() or not (
                self.min_cert_expire <= int(cert_expire) <= self.max_cert_expire
            ):
                raise ValueError("Некорректный срок действия сертификата")
            command.append(cert_expire)

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, command, output=result.stdout, stderr=result.stderr
            )
        return result.stdout, result.stderr


class ConfigFileHandler:
    def __init__(self, config_paths):
        self.config_paths = config_paths

    def _collect_files(self, paths, extension):
        collected = []
        for directory in paths:
            if os.path.exists(directory):
                for root, _, files in os.walk(directory):
                    collected.extend(
                        os.path.join(root, f) for f in files if f.endswith(extension)
                    )
        return collected

    def get_config_files(self):
        openvpn_files = self._collect_files(self.config_paths["openvpn"], ".ovpn")
        wg_files = self._collect_files(self.config_paths["wg"], ".conf")
        amneziawg_files = self._collect_files(self.config_paths["amneziawg"], ".conf")
        return openvpn_files, wg_files, amneziawg_files


class AuthenticationManager:
    def __init__(self):
        pass

    def login_required(self, f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "username" not in session:
                flash(
                    "Пожалуйста, войдите в систему для доступа к этой странице.", "info"
                )
                return redirect(url_for("login"))
            return f(*args, **kwargs)

        return decorated_function


class CaptchaGenerator:
    def __init__(self):
        pass

    def generate_captcha(self):
        text = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return text

    def generate_captcha_image(self):
        text = session.get("captcha", "")

        width = 200
        height = 60
        image = Image.new("RGB", (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("./static/assets/fonts/SabirMono-Regular.ttf", 42)
        x_offset = 22
        y_offset = 10
        current_x = x_offset

        for char in text:
            try:
                bbox = draw.textbbox((0, 0), char, font=font)
                char_width = bbox[2] - bbox[0]
                char_height = bbox[3] - bbox[1]
            except AttributeError:
                char_width, char_height = draw.textsize(char, font=font)

            angle = random.randint(-15, 15)

            char_img = Image.new(
                "RGBA", (char_width * 2, char_height * 2), (255, 255, 255, 0)
            )
            char_draw = ImageDraw.Draw(char_img)
            char_draw.text((0, 0), char, font=font, fill=(0, 0, 0))

            char_img = char_img.rotate(angle, expand=1, resample=Image.BICUBIC)
            new_width, new_height = char_img.size

            char_x = current_x + (char_width // 2) - (new_width // 2)
            char_y = y_offset + (char_height // 2) - (new_height // 2)

            image.paste(char_img, (char_x, char_y), char_img)

            current_x += char_width + 10

        for _ in range(200):
            x = random.randint(0, width)
            y = random.randint(0, height)
            size = random.randint(1, 3)
            draw.ellipse((x, y, x + size, y + size), fill=(200, 200, 200))

        distortion = Image.new("L", (width, height), 255)
        draw_dist = ImageDraw.Draw(distortion)
        for _ in range(5):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = random.randint(0, width)
            y2 = random.randint(0, height)
            draw_dist.line((x1, y1, x2, y2), fill=0, width=2)

        image = Image.composite(
            image, Image.new("RGB", (width, height), (255, 255, 255)), distortion
        )

        image = image.filter(ImageFilter.GaussianBlur(radius=0.5))

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        image = image.convert("RGB")
        img_io = io.BytesIO()
        image.save(img_io, "PNG")
        img_io.seek(0)

        return img_io


class FileValidator:
    def __init__(self, config_paths):
        self.config_paths = config_paths

    def validate_file(self, func):
        @wraps(func)
        def wrapper(file_type, filename, *args, **kwargs):
            try:
                if file_type not in self.config_paths:
                    abort(400, description="Недопустимый тип файла")

                for config_dir in self.config_paths[file_type]:
                    for root, _, files in os.walk(config_dir):
                        for file in files:
                            if file.replace("(", "").replace(
                                ")", ""
                            ) == filename.replace("(", "").replace(")", ""):
                                file_path = os.path.join(root, file)
                                clean_name = file.replace("(", "").replace(")", "")
                                return func(file_path, clean_name, *args, **kwargs)

                abort(404, description="Файл не найден")

            except Exception as e:
                print(f"Аларм! ошибка: {str(e)}")
                abort(500)

        return wrapper


class QRGenerator:
    def __init__(self):
        pass

    def generate_qr_code(self, config_text):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(config_text)
        qr.make(fit=True)

        img = qr.make_image(
            fill_color="black", back_color="white", image_factory=PilImage
        )

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)

        return img_byte_arr


class FileEditor:
    def __init__(self):
        self.files = {
            "include_hosts": "/root/antizapret/config/include-hosts.txt",
            "exclude_hosts": "/root/antizapret/config/exclude-hosts.txt",
            "include_ips": "/root/antizapret/config/include-ips.txt",
        }

    def update_file_content(self, file_type, content):
        if file_type in self.files:
            try:
                with open(self.files[file_type], "w", encoding="utf-8") as f:
                    f.write(content)
                return True
            except Exception as e:
                print(f"Ошибка записи в файл: {str(e)}")
                return False
        return False

    def get_file_contents(self):
        file_contents = {}
        for key, path in self.files.items():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_contents[key] = f.read()
            except FileNotFoundError:
                file_contents[key] = ""
        return file_contents


class ServerMonitor:
    def __init__(self):
        pass

    def get_cpu_usage(self):
        return psutil.cpu_percent(interval=1)

    def get_memory_usage(self):
        memory = psutil.virtual_memory()
        return memory.percent

    def get_uptime(self):
        boot_time = psutil.boot_time()
        current_time = time.time()
        uptime_seconds = current_time - boot_time
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{int(days)}д {int(hours)}ч {int(minutes)}м"


# Инициализация классов
script_executor = ScriptExecutor()
config_file_handler = ConfigFileHandler(CONFIG_PATHS)
auth_manager = AuthenticationManager()
captcha_generator = CaptchaGenerator()
file_validator = FileValidator(CONFIG_PATHS)
qr_generator = QRGenerator()
file_editor = FileEditor()
server_monitor_proc = ServerMonitor()


# Главная страница
@app.route("/", methods=["GET", "POST"])
@auth_manager.login_required
def index():
    if request.method == "GET":
        openvpn_files, wg_files, amneziawg_files = (
            config_file_handler.get_config_files()
        )
        return render_template(
            "index.html",
            openvpn_files=openvpn_files,
            wg_files=wg_files,
            amneziawg_files=amneziawg_files,
        )

    if request.method == "POST":
        try:
            option = request.form.get("option")
            client_name = request.form.get("client-name", "").strip()
            cert_expire = request.form.get("work-term", "").strip()

            if not option or not client_name:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Не указаны обязательные параметры.",
                        }
                    ),
                    400,
                )

            stdout, stderr = script_executor.run_bash_script(
                option, client_name, cert_expire
            )
            return jsonify(
                {
                    "success": True,
                    "message": "Операция выполнена успешно.",
                    "output": stdout,
                }
            )
        except subprocess.CalledProcessError as e:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Ошибка выполнения скрипта: {e.stderr}",
                        "output": e.stdout,
                    }
                ),
                500,
            )
        except Exception as e:
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500


# Страница логина
@app.route("/login", methods=["GET", "POST"])
def login():
    if "captcha" not in session:
        session["captcha"] = captcha_generator.generate_captcha()

    if request.method == "POST":
        attempts = session.get("attempts", 0)
        attempts += 1
        session["attempts"] = attempts
        if attempts > 2:
            user_captcha = request.form.get("captcha", "").upper()
            correct_captcha = session.get("captcha", "")

            if user_captcha != correct_captcha:
                flash("Неверный код!", "error")
                session["captcha"] = captcha_generator.generate_captcha()
                return redirect(url_for("login"))

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["username"] = user.username
            session["attempts"] = 0
            return redirect(url_for("index"))
        flash("Неверные учетные данные. Попробуйте снова.", "error")
        return redirect(url_for("login"))
    return render_template("login.html", captcha=session["captcha"])


# Страница выхода
@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))


# Роут обновления капчи
@app.route("/refresh_captcha")
def refresh_captcha():
    session["captcha"] = captcha_generator.generate_captcha()
    return session["captcha"]


# Декоратор для капчи (графическое представление)
@app.route("/captcha.png")
def captcha():
    session["captcha"] = captcha_generator.generate_captcha()
    img_io = captcha_generator.generate_captcha_image()

    response = make_response(img_io.getvalue())
    response.headers.set("Content-Type", "image/png")
    return response


# Роут для скачивания конфигурационных файлов
@app.route("/download/<file_type>/<path:filename>")
@auth_manager.login_required
@file_validator.validate_file
def download(file_path, clean_name):
    try:
        base = os.path.basename(file_path)

        pattern = re.compile(
            r"^([^-]+)-(.+?)-\(.+\)(?:-(wg|am))?\.(ovpn|conf)$", re.IGNORECASE
        )
        m = pattern.match(base)

        if m:
            prefix, client, suffix, ext = (
                m.group(1).lower(),
                m.group(2),
                m.group(3).lower() if m.group(3) else None,
                m.group(4).lower(),
            )
            is_az = prefix == "antizapret"
            proto_prefix = ""
            if suffix == "wg":
                proto_prefix = "WG-"
            elif suffix == "am":
                proto_prefix = "AWG-"
            download_name = f"{proto_prefix}{client}{'-AZ' if is_az else ''}.{ext}"
        else:
            download_name = base
        return send_from_directory(
            os.path.dirname(file_path),
            base,
            as_attachment=True,
            download_name=download_name,
        )
    except Exception as e:
        print(f"Аларм! ошибка: {e}")
        abort(500)


# Роут для формирования QR кода
@app.route("/generate_qr/<file_type>/<path:filename>")
@auth_manager.login_required
@file_validator.validate_file
def generate_qr(file_path, clean_name):
    try:
        with open(file_path, "r") as file:
            config_text = file.read()

        img_byte_arr = qr_generator.generate_qr_code(config_text)

        return send_file(img_byte_arr, mimetype="image/png")
    except Exception as e:
        print(f"Аларм! ошибка: {str(e)}")
        abort(500)


# Роут для редактирования файлов конфигурации
@app.route("/edit-files", methods=["GET", "POST"])
@auth_manager.login_required
def edit_files():
    if request.method == "POST":
        file_type = request.form.get("file_type")
        content = request.form.get("content", "")

        if file_editor.update_file_content(file_type, content):
            try:
                result = subprocess.run(
                    ["/root/antizapret/doall.sh"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )
                return jsonify(
                    {
                        "success": True,
                        "message": "Файл успешно обновлен и изменения применены.",
                        "output": result.stdout,
                    }
                )
            except subprocess.CalledProcessError as e:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"Ошибка выполнения скрипта: {e.stderr}",
                            "output": e.stdout,
                        }
                    ),
                    500,
                )
            except Exception as e:
                return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

        return jsonify({"success": False, "message": "Неверный тип файла."}), 400

    file_contents = file_editor.get_file_contents()
    return render_template("edit_files.html", file_contents=file_contents)


# Роут для запуска скрипта doall.sh
@app.route("/run-doall", methods=["POST"])
@auth_manager.login_required
def run_doall():
    try:
        result = subprocess.run(
            ["/root/antizapret/doall.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return jsonify(
            {
                "success": True,
                "message": "Скрипт успешно выполнен.",
                "output": result.stdout,
            }
        )
    except subprocess.CalledProcessError as e:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Ошибка выполнения скрипта: {e.stderr}",
                    "output": e.stdout,
                }
            ),
            500,
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500


# Маршрут для страницы мониторинга и обновления данных
@app.route("/server_monitor", methods=["GET", "POST"])
@auth_manager.login_required
def server_monitor():
    iface = os.getenv("VNSTAT_IFACE", "ens3")

    if request.method == "GET":
        cpu_usage = server_monitor_proc.get_cpu_usage()
        memory_usage = server_monitor_proc.get_memory_usage()
        uptime = server_monitor_proc.get_uptime()
        return render_template(
            "server_monitor.html",
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            uptime=uptime,
            iface=iface,
        )
    elif request.method == "POST":
        try:
            cpu_usage = server_monitor_proc.get_cpu_usage()
            memory_usage = server_monitor_proc.get_memory_usage()
            uptime = server_monitor_proc.get_uptime()
            return jsonify(
                {"cpu_usage": cpu_usage, "memory_usage": memory_usage, "uptime": uptime}
            )
        except Exception as e:
            app.logger.error(f"Ошибка при обновлении данных мониторинга: {e}")
            return jsonify({"error": "Ошибка при обновлении данных мониторинга"}), 500


@app.route("/get_antizapret_settings")
@auth_manager.login_required
def get_antizapret_settings():
    try:
        with open("/root/antizapret/setup", "r") as f:
            content = f.read()

        settings = {
            "route_all": "n",
            "discord_include": "n",
            "cloudflare_include": "n",
            "amazon_include": "n",
            "hetzner_include": "n",
            "digitalocean_include": "n",
            "ovh_include": "n",
            "telegram_include": "n",
            "block_ads": "n",
            "akamai_include": "n",
            "google_include": "n",
            "openvpn_80_443_tcp": "n",
            "openvpn_80_443_udp": "n",
            "ssh_protection": "n",
            "attack_protection": "n",
            "torrent_guard": "n",
            "restrict_forward": "n",
            "openvpn_host": "",
            "wireguard_host": "",
            "clear_hosts": "n",
        }

        for param in settings.keys():
            if param in ["openvpn_host", "wireguard_host"]:
                match = re.search(f"^{param.upper()}=(.+)$", content, re.MULTILINE)
                if match:
                    settings[param] = match.group(1).strip()
            else:
                match = re.search(f"^{param.upper()}=([yn])", content, re.MULTILINE)
                if match:
                    settings[param] = match.group(1)

        return jsonify(settings)
    except Exception as e:
        app.logger.error(f"Ошибка чтения настроек: {str(e)}")
        return jsonify({"error": "Ошибка чтения файла настроек"}), 500


@app.route("/update_antizapret_settings", methods=["POST"])
@auth_manager.login_required
def update_antizapret_settings():
    try:
        new_settings = request.json

        with open("/root/antizapret/setup", "r") as f:
            lines = f.readlines()

        params_to_update = {
            "ROUTE_ALL": f"ROUTE_ALL={new_settings.get('route_all', 'n')}",
            "DISCORD_INCLUDE": f"DISCORD_INCLUDE={new_settings.get('discord_include', 'n')}",
            "CLOUDFLARE_INCLUDE": f"CLOUDFLARE_INCLUDE={new_settings.get('cloudflare_include', 'n')}",
            "AMAZON_INCLUDE": f"AMAZON_INCLUDE={new_settings.get('amazon_include', 'n')}",
            "HETZNER_INCLUDE": f"HETZNER_INCLUDE={new_settings.get('hetzner_include', 'n')}",
            "DIGITALOCEAN_INCLUDE": f"DIGITALOCEAN_INCLUDE={new_settings.get('digitalocean_include', 'n')}",
            "OVH_INCLUDE": f"OVH_INCLUDE={new_settings.get('ovh_include', 'n')}",
            "AKAMAI_INCLUDE": f"AKAMAI_INCLUDE={new_settings.get('akamai_include', 'n')}",
            "TELEGRAM_INCLUDE": f"TELEGRAM_INCLUDE={new_settings.get('telegram_include', 'n')}",
            "BLOCK_ADS": f"BLOCK_ADS={new_settings.get('block_ads', 'n')}",
            "GOOGLE_INCLUDE": f"GOOGLE_INCLUDE={new_settings.get('google_include', 'n')}",
            "OPENVPN_80_443_TCP": f"OPENVPN_80_443_TCP={new_settings.get('openvpn_80_443_tcp', 'n')}",
            "OPENVPN_80_443_UDP": f"OPENVPN_80_443_UDP={new_settings.get('openvpn_80_443_udp', 'n')}",
            "SSH_PROTECTION": f"SSH_PROTECTION={new_settings.get('ssh_protection', 'n')}",
            "ATTACK_PROTECTION": f"ATTACK_PROTECTION={new_settings.get('attack_protection', 'n')}",
            "TORRENT_GUARD": f"TORRENT_GUARD={new_settings.get('torrent_guard', 'n')}",
            "RESTRICT_FORWARD": f"RESTRICT_FORWARD={new_settings.get('restrict_forward', 'n')}",
            "CLEAR_HOSTS": f"CLEAR_HOSTS={new_settings.get('clear_hosts', 'n')}",
            "OPENVPN_HOST": f"OPENVPN_HOST={new_settings.get('openvpn_host', '')}",
            "WIREGUARD_HOST": f"WIREGUARD_HOST={new_settings.get('wireguard_host', '')}",
        }

        updated_lines = []
        found_params = set()

        for line in lines:
            line_stripped = line.strip()
            param_updated = False
            for param, new_value in params_to_update.items():
                if line_stripped.startswith(param + "="):
                    updated_lines.append(new_value + "\n")
                    found_params.add(param)
                    param_updated = True
                    break
            if not param_updated and line_stripped:
                updated_lines.append(line)

        for param, new_value in params_to_update.items():
            if param not in found_params:
                updated_lines.append(new_value + "\n")

        with open("/root/antizapret/setup", "w") as f:
            f.writelines(updated_lines)

        return jsonify(
            {
                "success": True,
                "message": "Настройки успешно сохранены",
                "needs_apply": True,
            }
        )

    except PermissionError:
        return (
            jsonify(
                {"success": False, "message": "Ошибка: Нет прав для записи в файл"}
            ),
            403,
        )
    except Exception as e:
        app.logger.error(f"Ошибка обновления настроек: {str(e)}")
        return (
            jsonify(
                {"success": False, "message": "Ошибка сервера при обновлении настроек"}
            ),
            500,
        )


@app.route("/settings", methods=["GET", "POST"])
@auth_manager.login_required
def settings():
    if request.method == "POST":
        new_port = request.form.get("port")
        if new_port and new_port.isdigit():
            with open(".env", "r") as file:
                lines = file.readlines()
            with open(".env", "w") as file:
                for line in lines:
                    if line.startswith("APP_PORT="):
                        file.write(f"APP_PORT={new_port}\n")
                    else:
                        file.write(line)
            flash("Порт успешно изменён. Перезапуск службы...", "success")

            try:
                if platform.system() == "Linux":
                    subprocess.run(
                        ["systemctl", "restart", "admin-antizapret.service"], check=True
                    )
            except subprocess.CalledProcessError as e:
                flash(f"Ошибка при перезапуске службы: {e}", "error")

        username = request.form.get("username")
        password = request.form.get("password")
        if username and password:
            if len(password) < 8:
                flash("Пароль должен содержать минимум 8 символов!", "error")
            else:
                with app.app_context():
                    if User.query.filter_by(username=username).first():
                        flash(f"Пользователь '{username}' уже существует!", "error")
                    else:
                        user = User(username=username)
                        user.set_password(password)
                        db.session.add(user)
                        db.session.commit()
                        flash(f"Пользователь '{username}' успешно добавлен!", "success")

        delete_username = request.form.get("delete_username")
        if delete_username:
            with app.app_context():
                user = User.query.filter_by(username=delete_username).first()
                if user:
                    db.session.delete(user)
                    db.session.commit()
                    flash(
                        f"Пользователь '{delete_username}' успешно удалён!", "success"
                    )
                else:
                    flash(f"Пользователь '{delete_username}' не найден!", "error")

        return redirect(url_for("settings"))
    current_port = os.getenv("APP_PORT", "5050")
    users = User.query.all()
    return render_template("settings.html", port=current_port, users=users)


# Трафик по 5-минуткам для графика (последние 24 часа)
@app.route("/api/bw")
@auth_manager.login_required
def api_bw():
    import json, subprocess, os
    from flask import request, jsonify

    # iface из ?iface=..., env или конфига
    iface = os.environ.get("VNSTAT_IFACE") or app.config.get("VNSTAT_IFACE")
    q_iface = request.args.get("iface")
    if q_iface:
        iface = q_iface

    # диапазон: 1d | 7d | 30d
    rng = request.args.get("range", "1d")
    if rng not in ("1d", "7d", "30d"):
        rng = "1d"

    vnstat_bin = os.environ.get("VNSTAT_BIN", "/usr/bin/vnstat")

    def _run(args):
        return subprocess.run(args, check=True, capture_output=True, text=True)

    try:
        # f — пяти минутки (для графика 1d)
        data_f = json.loads(_run([vnstat_bin, "--json", "f", "-i", iface]).stdout)
    except Exception:
        data_f = {}

    try:
        # d — по дням (для графиков 7/30d и сумм)
        data_d = json.loads(_run([vnstat_bin, "--json", "d", "-i", iface]).stdout)
    except Exception as e:
        # если даже дни не получилось — отдадим пустые данные
        return jsonify({"error": str(e), "iface": iface}), 500

    # --- Достаём нужные секции ---
    def get_iface_block(data):
        for it in data.get("interfaces") or []:
            if it.get("name") == iface:
                return it
        return {}

    it_f = get_iface_block(data_f)
    it_d = get_iface_block(data_d)

    traffic_f = it_f.get("traffic") or {}
    traffic_d = it_d.get("traffic") or {}

    fivemin = (
        traffic_f.get("fiveminute")
        or traffic_f.get("fiveMinute")
        or traffic_f.get("five_minutes")
        or []
    )

    days = traffic_d.get("day") or traffic_d.get("days") or []

    # --- helpers ---
    def sort_key_dt(h):
        d = h.get("date") or {}
        t = h.get("time") or {}
        return (
            d.get("year", 0),
            d.get("month", 0),
            d.get("day", 0),
            (t.get("hour", 0) if t else 0),
            (t.get("minute", 0) if t else 0),
        )

    def to_mbps_from_5min_bytes(b):  # байты за 5 минут -> Мбит/с
        return round((int(b) * 8) / (300 * 1_000_000), 3)

    def to_mbps_avg_per_day(bytes_val):  # байты за день -> средняя Мбит/с за сутки
        return round((int(bytes_val) * 8) / (86_400 * 1_000_000), 3)

    # --- формируем график под выбранный диапазон ---
    labels, rx_mbps, tx_mbps = [], [], []

    if rng == "1d":
        # последние 24 часа — 288 точек по 5 минут
        if fivemin:
            last288 = sorted(fivemin, key=sort_key_dt)[-288:]
            for m in last288:
                t = m.get("time") or {}
                labels.append(
                    f"{int(t.get('hour',0)):02d}:{int(t.get('minute',0)):02d}"
                )
                rx_mbps.append(to_mbps_from_5min_bytes(m.get("rx", 0)))
                tx_mbps.append(to_mbps_from_5min_bytes(m.get("tx", 0)))
        else:
            labels = [""] * 288
            rx_mbps = [0.0] * 288
            tx_mbps = [0.0] * 288
    else:
        # 7d / 30d: строим по дням (средняя скорость за день)
        need_days = 7 if rng == "7d" else 30
        use_days = sorted(days, key=sort_key_dt)[-need_days:]
        for d in use_days:
            date = d.get("date") or {}
            labels.append(
                f"{int(date.get('day',0)):02d}.{int(date.get('month',0)):02d}"
            )
            rx_mbps.append(to_mbps_avg_per_day(d.get("rx", 0)))
            tx_mbps.append(to_mbps_avg_per_day(d.get("tx", 0)))

        # если данных меньше N дней — добиваем пустыми слева
        if len(labels) < need_days:
            pad = need_days - len(labels)
            labels = [""] * pad + labels
            rx_mbps = [0.0] * pad + rx_mbps
            tx_mbps = [0.0] * pad + tx_mbps

    # --- считаем суммы за 1/7/30 дней (в байтах) ---
    days_sorted = sorted(days, key=sort_key_dt)

    def sum_days(n):
        chunk = days_sorted[-n:] if days_sorted else []
        rx_sum = sum(int(x.get("rx", 0)) for x in chunk)
        tx_sum = sum(int(x.get("tx", 0)) for x in chunk)
        return {"rx_bytes": rx_sum, "tx_bytes": tx_sum, "total_bytes": rx_sum + tx_sum}

    totals = {
        "1d": sum_days(1),
        "7d": sum_days(7),
        "30d": sum_days(30),
    }

    return jsonify(
        {
            "iface": iface,
            "range": rng,
            "labels": labels,
            "rx_mbps": rx_mbps,
            "tx_mbps": tx_mbps,
            "totals": totals,
        }
    )


@app.route("/update_system", methods=["POST"])
@auth_manager.login_required
def update_system():
    try:
        # Обновление панели
        panel_update = subprocess.run(
            ["/opt/AdminAntizapret/script_sh/adminpanel.sh", "--update"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Проверяем вывод на ключевые слова
        if "Система актуальна" in panel_update.stdout:
            msg = "Система актуальна"
        elif panel_update.returncode == 0:
            msg = "Обновление успешно выполнено"
        else:
            msg = "Ошибка при обновлении"
        return {"success": panel_update.returncode == 0, "message": msg}
    except Exception as e:
        return {"success": False, "message": f"Ошибка обновления: {str(e)}"}, 500
