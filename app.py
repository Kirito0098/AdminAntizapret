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
from flask_sock import Sock
import subprocess
import os
import re
import io
import glob
import hashlib
import secrets
import qrcode
from qrcode.exceptions import DataOverflowError
import random
import string
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from qrcode.image.pil import PilImage
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from functools import wraps
import shlex
import psutil
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import time
import platform

#Импорт файла с параметрами
from utils.ip_restriction import ip_restriction
from config.antizapret_params import ANTIZAPRET_PARAMS
from ips import ip_manager
from routes.settings_antizapret import init_antizapret

# Загрузка переменных окружения из .env файла
load_dotenv()

port = int(os.getenv("APP_PORT", "5050"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise ValueError("SECRET_KEY is not set in .env!")
app.config['SESSION_COOKIE_NAME'] = 'AdminAntizapretSession'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

csrf = CSRFProtect(app)
sock = Sock(app)
ip_restriction.init_app(app)
init_antizapret(app)

#   hostname/public_download/
RESULT_DIR_FILES = {
    "keenetic": "keenetic-wireguard-routes.txt",
    "mikrotik": "mikrotik-wireguard-routes.txt",
    "ips": "route-ips.txt",
    "tplink": "tp-link-openvpn-routes.txt"
}

PUBLIC_DOWNLOAD_ENABLED = os.getenv("PUBLIC_DOWNLOAD_ENABLED", "false").lower() == "true"


def _set_env_value(key, value):
    """Update or append env key in local .env file."""
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

OPENVPN_FOLDERS = [
    "/root/antizapret/client/openvpn/antizapret",
    "/root/antizapret/client/openvpn/antizapret-tcp",
    "/root/antizapret/client/openvpn/antizapret-udp",
    "/root/antizapret/client/openvpn/vpn",
    "/root/antizapret/client/openvpn/vpn-tcp",
    "/root/antizapret/client/openvpn/vpn-udp",
]

GROUP_FOLDERS = {
    'GROUP_UDP\\TCP': [OPENVPN_FOLDERS[0], OPENVPN_FOLDERS[3]],  # UDP AND tcp
    'GROUP_UDP':  [OPENVPN_FOLDERS[2], OPENVPN_FOLDERS[5]],  # UDP only
    'GROUP_TCP':  [OPENVPN_FOLDERS[1], OPENVPN_FOLDERS[4]],  # TCP only
}

CONFIG_PATHS = {
    "openvpn": GROUP_FOLDERS["GROUP_UDP\\TCP"],
    "wg": [
        "/root/antizapret/client/wireguard/antizapret",
        "/root/antizapret/client/wireguard/vpn",
    ],
    "amneziawg": [
        "/root/antizapret/client/amneziawg/antizapret",
        "/root/antizapret/client/amneziawg/vpn",
    ],
    "antizapret_result": [
        "/root/antizapret/result"
    ],
}

OPENVPN_BANNED_CLIENTS_FILE = "/etc/openvpn/server/banned_clients"
OPENVPN_CLIENT_CONNECT_SCRIPT = "/etc/openvpn/server/scripts/client-connect.sh"
CLIENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

CLIENT_CONNECT_BAN_CHECK_BLOCK = (
    "BANNED=\"/etc/openvpn/server/banned_clients\"\n\n"
    "if [ -f \"$BANNED\" ]; then\n"
    "    if grep -q \"^$common_name$\" \"$BANNED\"; then\n"
    "        echo \"Client $common_name banned\" >&2\n"
    "        exit 1\n"
    "    fi\n"
    "fi\n"
)


def _read_banned_clients():
    banned = set()
    try:
        with open(OPENVPN_BANNED_CLIENTS_FILE, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                banned.add(line)
    except FileNotFoundError:
        return set()
    return banned


def _write_banned_clients(clients):
    ordered = sorted(set(clients), key=str.lower)
    with open(OPENVPN_BANNED_CLIENTS_FILE, "w", encoding="utf-8") as f:
        if ordered:
            f.write("\n".join(ordered) + "\n")


def _ensure_client_connect_ban_check_block():
    """Гарантирует наличие проверки banned_clients в client-connect.sh."""
    try:
        with open(OPENVPN_CLIENT_CONNECT_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    if CLIENT_CONNECT_BAN_CHECK_BLOCK in content:
        return

    if content.startswith("#!"):
        first_line_end = content.find("\n")
        if first_line_end == -1:
            shebang_line = content + "\n"
            rest = ""
        else:
            shebang_line = content[: first_line_end + 1]
            rest = content[first_line_end + 1 :]
        new_content = shebang_line + "\n" + CLIENT_CONNECT_BAN_CHECK_BLOCK + "\n" + rest.lstrip("\n")
    else:
        new_content = CLIENT_CONNECT_BAN_CHECK_BLOCK + "\n" + content.lstrip("\n")

    with open(OPENVPN_CLIENT_CONNECT_SCRIPT, "w", encoding="utf-8") as f:
        f.write(new_content)


def normalize_openvpn_group_key(filename):
    """Нормализует имя .ovpn в ключ группы для UI доступа viewer."""
    base_name = os.path.basename(filename)
    stem, ext = os.path.splitext(base_name)
    if ext.lower() != ".ovpn":
        return stem.lower().strip() or stem.lower()

    normalized = stem.strip()
    lowered = normalized.lower()

    for prefix in ("antizapret-", "vpn-"):
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    # Протокол и IP-метка являются вариациями одного и того же конфига.
    normalized = re.sub(r"-(udp|tcp)$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"-\([^)]+\)$", "", normalized)

    cleaned = normalized.strip("-_ ")
    return cleaned.lower() if cleaned else stem.lower()


def get_openvpn_group_display_name(filename):
    """Возвращает отображаемое имя группы OpenVPN без префиксов/вариантов."""
    base_name = os.path.basename(filename)
    stem, _ = os.path.splitext(base_name)

    display = stem.strip()
    lowered = display.lower()

    for prefix in ("antizapret-", "vpn-"):
        if lowered.startswith(prefix):
            display = display[len(prefix):]
            break

    display = re.sub(r"-(udp|tcp)$", "", display, flags=re.IGNORECASE)
    display = re.sub(r"-\([^)]+\)$", "", display)
    display = display.strip("-_ ")
    return display or stem


def collect_all_openvpn_files_for_access():
    """Собирает все OpenVPN конфиги из всех групповых директорий."""
    original_paths = config_file_handler.config_paths["openvpn"]
    try:
        config_file_handler.config_paths["openvpn"] = [
            directory for folders in GROUP_FOLDERS.values() for directory in folders
        ]
        all_openvpn, _, _ = config_file_handler.get_config_files()
        return all_openvpn
    finally:
        config_file_handler.config_paths["openvpn"] = original_paths


def build_openvpn_access_groups(openvpn_paths):
    """Группирует .ovpn файлы по одному логическому конфигу."""
    grouped = {}
    for file_path in openvpn_paths:
        file_name = os.path.basename(file_path)
        group_key = normalize_openvpn_group_key(file_name)
        if group_key not in grouped:
            grouped[group_key] = {
                "group_key": group_key,
                "display_name": get_openvpn_group_display_name(file_name),
                "files": [],
            }
        grouped[group_key]["files"].append(file_name)

    for item in grouped.values():
        item["files"] = sorted(set(item["files"]), key=str.lower)

    return [grouped[k] for k in sorted(grouped.keys())]


def normalize_conf_group_key(filename, config_type):
    """Нормализует имя .conf в ключ группы (WG/AmneziaWG)."""
    base_name = os.path.basename(filename)
    stem, ext = os.path.splitext(base_name)
    if ext.lower() != ".conf":
        return stem.lower().strip() or stem.lower()

    normalized = stem.strip()
    lowered = normalized.lower()

    for prefix in ("antizapret-", "vpn-"):
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    # Варианты -am/-wg и IP-метка не меняют логический конфиг.
    if config_type == "amneziawg":
        normalized = re.sub(r"-am$", "", normalized, flags=re.IGNORECASE)
    elif config_type == "wg":
        normalized = re.sub(r"-wg$", "", normalized, flags=re.IGNORECASE)

    normalized = re.sub(r"-\([^)]+\)$", "", normalized)
    cleaned = normalized.strip("-_ ")
    return cleaned.lower() if cleaned else stem.lower()


def get_conf_group_display_name(filename, config_type):
    """Отображаемое имя группы для WG/AmneziaWG без служебных суффиксов."""
    base_name = os.path.basename(filename)
    stem, _ = os.path.splitext(base_name)

    display = stem.strip()
    lowered = display.lower()

    for prefix in ("antizapret-", "vpn-"):
        if lowered.startswith(prefix):
            display = display[len(prefix):]
            break

    if config_type == "amneziawg":
        display = re.sub(r"-am$", "", display, flags=re.IGNORECASE)
    elif config_type == "wg":
        display = re.sub(r"-wg$", "", display, flags=re.IGNORECASE)

    display = re.sub(r"-\([^)]+\)$", "", display)
    display = display.strip("-_ ")
    return display or stem


def build_conf_access_groups(conf_paths, config_type):
    """Группирует .conf файлы WG/AmneziaWG по одному логическому конфигу."""
    grouped = {}
    for file_path in conf_paths:
        file_name = os.path.basename(file_path)
        group_key = normalize_conf_group_key(file_name, config_type)
        if group_key not in grouped:
            grouped[group_key] = {
                "group_key": group_key,
                "display_name": get_conf_group_display_name(file_name, config_type),
                "files": [],
            }
        grouped[group_key]["files"].append(file_name)

    for item in grouped.values():
        item["files"] = sorted(set(item["files"]), key=str.lower)

    return [grouped[k] for k in sorted(grouped.keys())]


def collect_all_configs_for_access(config_type):
    """Возвращает список файлов выбранного типа для управления доступом."""
    if config_type == "openvpn":
        return collect_all_openvpn_files_for_access()

    extension = ".conf" if config_type in ("wg", "amneziawg") else None
    if not extension or config_type not in config_file_handler.config_paths:
        return []

    return config_file_handler._collect_files(
        config_file_handler.config_paths[config_type], extension
    )

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
    role = db.Column(db.String(20), nullable=False, default='admin')  # 'admin' или 'viewer'
    allowed_configs = db.relationship('ViewerConfigAccess', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'


class QrDownloadToken(db.Model):
    """Одноразовый токен для короткоживущей ссылки на скачивание конфига."""
    __tablename__ = 'qr_download_token'

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    config_type = db.Column(db.String(20), nullable=False)
    config_name = db.Column(db.String(255), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True, index=True)


class ViewerConfigAccess(db.Model):
    """Доступ viewer к конкретным конфигам."""
    __tablename__ = 'viewer_config_access'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    config_type = db.Column(db.String(20), nullable=False)   # 'openvpn', 'wg', 'amneziawg'
    config_name = db.Column(db.String(255), nullable=False)  # basename файла
    __table_args__ = (
        db.UniqueConstraint('user_id', 'config_name', name='unique_user_config'),
    )


class UserTrafficStat(db.Model):
    """Накопленный трафик по пользователю (CN)."""
    __tablename__ = 'user_traffic_stat'

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    total_received = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent = db.Column(db.BigInteger, nullable=False, default=0)
    total_received_vpn = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent_vpn = db.Column(db.BigInteger, nullable=False, default=0)
    total_received_antizapret = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent_antizapret = db.Column(db.BigInteger, nullable=False, default=0)
    total_sessions = db.Column(db.Integer, nullable=False, default=0)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrafficSessionState(db.Model):
    """Последнее состояние активной сессии из *-status.log для расчета дельты."""
    __tablename__ = 'traffic_session_state'

    id = db.Column(db.Integer, primary_key=True)
    session_key = db.Column(db.String(512), unique=True, nullable=False, index=True)
    profile = db.Column(db.String(64), nullable=False)
    common_name = db.Column(db.String(255), nullable=False, index=True)
    real_address = db.Column(db.String(255), nullable=True)
    virtual_address = db.Column(db.String(255), nullable=True)
    connected_since_ts = db.Column(db.BigInteger, nullable=False, default=0)
    last_bytes_received = db.Column(db.BigInteger, nullable=False, default=0)
    last_bytes_sent = db.Column(db.BigInteger, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)


class UserTrafficSample(db.Model):
    """Дельта трафика пользователя по сети за конкретный снимок."""
    __tablename__ = 'user_traffic_sample'

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(255), nullable=False, index=True)
    network_type = db.Column(db.String(20), nullable=False, index=True)  # vpn | antizapret
    delta_received = db.Column(db.BigInteger, nullable=False, default=0)
    delta_sent = db.Column(db.BigInteger, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


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

    def get_openvpn_cert_expiry(self):
        expiry = {}
        CERT_KEYS_DIR = "/etc/openvpn/client/keys"

        for base_dir in self.config_paths["openvpn"]:
            if not os.path.exists(base_dir):
                continue

            for root, _, files in os.walk(base_dir):
                for filename in files:
                    if not filename.endswith('.ovpn'):
                        continue

                    client_name = self._extract_client_name_from_ovpn(filename)
                    if not client_name:
                        continue

                    possible_crt_names = [
                        f"{client_name}.crt",
                        f"{client_name.replace('-', '_')}.crt",
                        f"client-{client_name}.crt",
                    ]

                    crt_path = None
                    for crt_name in possible_crt_names:
                        candidate = os.path.join(CERT_KEYS_DIR, crt_name)
                        if os.path.exists(candidate):
                            crt_path = candidate
                            break

                    if not crt_path:
                        expiry[client_name] = {
                            "days_left": None,
                            "expires_at": None,
                        }
                        continue

                    try:
                        result = subprocess.run(
                            ["openssl", "x509", "-in", crt_path, "-noout", "-enddate"],
                            capture_output=True,
                            text=True,
                            check=True
                        )

                        line = result.stdout.strip()
                        if not line.startswith("notAfter="):
                            expiry[client_name] = {
                                "days_left": None,
                                "expires_at": None,
                            }
                            continue

                        date_str = line.split("=", 1)[1].strip()
                        expiry_date = datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z")
                        expiry_date = expiry_date.replace(tzinfo=timezone.utc)

                        now = datetime.now(timezone.utc)
                        days_left = (expiry_date - now).days

                        expiry[client_name] = {
                            "days_left": days_left,
                            "expires_at": expiry_date.strftime("%Y-%m-%d %H:%M UTC"),
                        }

                    except Exception as e:
                        expiry[client_name] = {
                            "days_left": None,
                            "expires_at": None,
                        }

        return expiry

    def _extract_client_name_from_ovpn(self, filename):
        name = os.path.splitext(filename)[0]

        prefixes = ['antizapret-', 'vpn-', '']
        for prefix in prefixes:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
                break

        if '-(' in name:
            name = name.split('-(')[0]

        name = name.strip('- ')

        return name if len(name) >= 2 else None

class AuthenticationManager:
    def __init__(self):
        pass

    def login_required(self, f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "username" in session:
                if ip_restriction.is_enabled():
                    client_ip = ip_restriction.get_client_ip()
                    if not ip_restriction.is_ip_allowed(client_ip):
                        session.clear()
                        flash(
                            f"Доступ запрещен с вашего IP-адреса ({client_ip}). Обратитесь к администратору.",
                            "error",
                        )
                        return redirect(url_for("ip_blocked"))
            if "username" not in session:
                flash(
                    "Пожалуйста, войдите в систему для доступа к этой странице.", "info"
                )
                return redirect(url_for("login"))
            return f(*args, **kwargs)

        return decorated_function

    def admin_required(self, f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "username" not in session:
                flash("Пожалуйста, войдите в систему.", "info")
                return redirect(url_for("login"))
            _user = User.query.filter_by(username=session["username"]).first()
            if not _user or _user.role != 'admin':
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': 'Доступ запрещён (403)'}), 403
                flash("Доступ запрещён. Недостаточно прав.", "error")
                return redirect(url_for("index"))
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
                def _scan(dirs):
                    for config_dir in dirs:
                        for root, _, files in os.walk(config_dir):
                            for file in files:
                                if file.replace("(", "").replace(")", "") == filename.replace("(", "").replace(")", ""):
                                    return os.path.join(root, file), file.replace("(", "").replace(")", "")
                    return None, None
                file_path, clean_name = _scan(self.config_paths[file_type])
                if not file_path and file_type == "openvpn":
                    file_path, clean_name = _scan(OPENVPN_FOLDERS)
                if file_path:
                    return func(file_path, clean_name, *args, **kwargs)
                abort(404, description="Файл не найден")
            except HTTPException:
                raise
            except Exception as e:
                print(f"Аларм! ошибка: {str(e)}")
                abort(500)

        return wrapper

class QRGenerator:
    def __init__(self):
        pass

    def generate_qr_code(self, config_text):
        # Для длинных конфигов сначала пробуем высокий уровень коррекции,
        # затем снижаем его, чтобы поместить данные в максимально допустимую версию QR (40).
        correction_levels = (
            qrcode.constants.ERROR_CORRECT_H,
            qrcode.constants.ERROR_CORRECT_Q,
            qrcode.constants.ERROR_CORRECT_M,
            qrcode.constants.ERROR_CORRECT_L,
        )

        qr = None
        last_error = None
        for correction_level in correction_levels:
            try:
                candidate = qrcode.QRCode(
                    version=None,
                    error_correction=correction_level,
                    box_size=10,
                    border=4,
                )
                candidate.add_data(config_text)
                candidate.make(fit=True)
                qr = candidate
                break
            except (DataOverflowError, ValueError) as e:
                last_error = e

        if qr is None:
            raise ValueError(f"Конфигурация слишком длинная для QR-кода: {last_error}")

        img = qr.make_image(
            fill_color="black", back_color="white", image_factory=PilImage
        )

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)

        return img_byte_arr

    def generate_qr_for_download_url(self, download_url):
        """Генерирует QR с URL скачивания как fallback для слишком длинных конфигов."""
        return self.generate_qr_code(download_url)


class FileEditor:
    def __init__(self):  # если это не в __init__, перенеси туда
        self.files = {
            "include_hosts":          "/root/antizapret/config/include-hosts.txt",
            "exclude_hosts":          "/root/antizapret/config/exclude-hosts.txt",
            "include_ips":            "/root/antizapret/config/include-ips.txt",
            "allow-ips":              "/root/antizapret/config/allow-ips.txt",
            "exclude-ips":            "/root/antizapret/config/exclude-ips.txt",
            "forward-ips":            "/root/antizapret/config/forward-ips.txt",
            "include-adblock-hosts":  "/root/antizapret/config/include-adblock-hosts.txt",   # ← вот этого не хватало
            "exclude-adblock-hosts":  "/root/antizapret/config/exclude-adblock-hosts.txt",
            "remove-hosts":           "/root/antizapret/config/remove-hosts.txt",
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

    def get_system_info(self):
        """Получить системную информацию"""
        try:
            import socket
            return {
                "os": platform.system(),
                "os_release": platform.release(),
                "kernel": platform.platform(),
                "hostname": socket.gethostname(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
            }
        except Exception as e:
            app.logger.error(f"Ошибка при получении системной информации: {e}")
            return {}

    def get_disk_usage(self):
        """Получить использование диска"""
        try:
            disk = psutil.disk_usage("/")
            return {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            }
        except Exception as e:
            app.logger.error(f"Ошибка при получении информации о диске: {e}")
            return {}

    def get_load_average(self):
        """Получить load average"""
        try:
            load = os.getloadavg() if hasattr(os, "getloadavg") else psutil.getloadavg()
            cpu_count = psutil.cpu_count()
            return {
                "load_1m": round(load[0], 2),
                "load_5m": round(load[1], 2),
                "load_15m": round(load[2], 2),
                "cpu_count": cpu_count,
            }
        except Exception as e:
            app.logger.error(f"Ошибка при получении load average: {e}")
            return {}

    def get_status_color(self, value, thresholds=None):
        """
        Определить цвет статуса на основе значения
        thresholds: {"yellow": 70, "red": 90}
        """
        if thresholds is None:
            thresholds = {"yellow": 70, "red": 90}

        if value >= thresholds.get("red", 90):
            return "red"
        elif value >= thresholds.get("yellow", 70):
            return "yellow"
        else:
            return "green"


# Инициализация классов
script_executor = ScriptExecutor()
config_file_handler = ConfigFileHandler(CONFIG_PATHS)
auth_manager = AuthenticationManager()
captcha_generator = CaptchaGenerator()
file_validator = FileValidator(CONFIG_PATHS)
qr_generator = QRGenerator()
file_editor = FileEditor()
server_monitor_proc = ServerMonitor()

# Защита antizapret-роутов после полной инициализации
app.view_functions['get_antizapret_settings'] = auth_manager.admin_required(
    app.view_functions['get_antizapret_settings']
)
app.view_functions['update_antizapret_settings'] = auth_manager.admin_required(
    app.view_functions['update_antizapret_settings']
)
app.view_functions['antizapret_settings_schema'] = auth_manager.admin_required(
    app.view_functions['antizapret_settings_schema']
)


def _get_config_type(file_path):
    """Define config type by directory path."""
    p = file_path.lower()
    if '/openvpn/' in p:
        return 'openvpn'
    elif '/wireguard/' in p:
        return 'wg'
    elif '/amneziawg/' in p:
        return 'amneziawg'
    return None


def _resolve_config_file(file_type, filename):
    """Находит путь к конфигу по типу и имени файла."""
    if file_type not in CONFIG_PATHS:
        return None, None

    def _scan(dirs):
        for config_dir in dirs:
            for root, _, files in os.walk(config_dir):
                for file in files:
                    if file.replace("(", "").replace(")", "") == filename.replace("(", "").replace(")", ""):
                        return os.path.join(root, file), file.replace("(", "").replace(")", "")
        return None, None

    file_path, clean_name = _scan(CONFIG_PATHS[file_type])
    if not file_path and file_type == "openvpn":
        file_path, clean_name = _scan(OPENVPN_FOLDERS)
    return file_path, clean_name


def _create_one_time_download_url(file_path):
    """Создаёт одноразовую ссылку на скачивание с TTL."""
    config_type = _get_config_type(file_path)
    if config_type not in CONFIG_PATHS:
        raise ValueError("Невозможно определить тип конфигурации для одноразовой ссылки")

    ttl_seconds = int(os.getenv("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600"))
    # Защита от слишком маленького/большого значения из окружения.
    ttl_seconds = max(60, min(ttl_seconds, 3600))

    now = datetime.utcnow()
    token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    creator_id = None
    username = session.get("username")
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            creator_id = user.id

    token_row = QrDownloadToken(
        token_hash=token_hash,
        config_type=config_type,
        config_name=os.path.basename(file_path),
        created_by_user_id=creator_id,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.session.add(token_row)

    # Периодическая чистка старых токенов.
    stale_threshold = now - timedelta(days=1)
    db.session.query(QrDownloadToken).filter(
        (QrDownloadToken.expires_at < stale_threshold)
        | (QrDownloadToken.used_at.isnot(None) & (QrDownloadToken.used_at < stale_threshold))
    ).delete(synchronize_session=False)

    db.session.commit()
    return url_for("one_time_qr_download", token=token, _external=True)


def _run_db_migrations():
    """Apply incremental DB schema migrations."""
    from sqlalchemy import text
    from sqlalchemy import inspect as sa_inspect
    with app.app_context():
        db.create_all()  # Создаёт новые таблицы
        try:
            insp = sa_inspect(db.engine)
            cols = [c['name'] for c in insp.get_columns('user')]
            if 'role' not in cols:
                with db.engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE \"user\" ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'"
                    ))
                    conn.commit()

            if insp.has_table('user_traffic_stat'):
                traffic_cols = {c['name'] for c in insp.get_columns('user_traffic_stat')}
                traffic_missing = {
                    'total_received_vpn': "ALTER TABLE user_traffic_stat ADD COLUMN total_received_vpn BIGINT NOT NULL DEFAULT 0",
                    'total_sent_vpn': "ALTER TABLE user_traffic_stat ADD COLUMN total_sent_vpn BIGINT NOT NULL DEFAULT 0",
                    'total_received_antizapret': "ALTER TABLE user_traffic_stat ADD COLUMN total_received_antizapret BIGINT NOT NULL DEFAULT 0",
                    'total_sent_antizapret': "ALTER TABLE user_traffic_stat ADD COLUMN total_sent_antizapret BIGINT NOT NULL DEFAULT 0",
                }
                with db.engine.connect() as conn:
                    for col_name, alter_sql in traffic_missing.items():
                        if col_name not in traffic_cols:
                            conn.execute(text(alter_sql))
                    conn.commit()
        except Exception as e:
            print(f"DB migration warning: {e}")


_run_db_migrations()


@app.context_processor
def inject_current_user():
    user = None
    if "username" in session:
        user = User.query.filter_by(username=session["username"]).first()
    return {'current_user': user}


LOGS_DIR = "/etc/openvpn/server/logs"

STATUS_LOG_FILES = {
    "antizapret-tcp": os.path.join(LOGS_DIR, "antizapret-tcp-status.log"),
    "antizapret-udp": os.path.join(LOGS_DIR, "antizapret-udp-status.log"),
    "vpn-tcp": os.path.join(LOGS_DIR, "vpn-tcp-status.log"),
    "vpn-udp": os.path.join(LOGS_DIR, "vpn-udp-status.log"),
}

EVENT_LOG_FILES = {
    "antizapret-tcp": os.path.join(LOGS_DIR, "antizapret-tcp.log"),
    "antizapret-udp": os.path.join(LOGS_DIR, "antizapret-udp.log"),
    "vpn-tcp": os.path.join(LOGS_DIR, "vpn-tcp.log"),
    "vpn-udp": os.path.join(LOGS_DIR, "vpn-udp.log"),
}

STATUS_LOG_CLEANUP_MARKER = "# adminantizapret-status-cleanup"
STATUS_LOG_CLEANUP_PERIODS = {
    "daily": ("0 3 * * *", "Ежедневно"),
    "weekly": ("0 3 * * 0", "Еженедельно"),
    "monthly": ("0 3 1 * *", "Ежемесячно"),
}


def _status_log_cleanup_command():
    quoted_logs_dir = shlex.quote(LOGS_DIR)
    return (
        f"find {quoted_logs_dir} -maxdepth 1 -type f "
        "-name '*.log' ! -name '*-status.log' -delete >/dev/null 2>&1"
    )


def _read_crontab_lines():
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    # Если crontab отсутствует у пользователя, считаем что список пустой.
    if result.returncode != 0:
        stderr = (result.stderr or "").strip().lower()
        if "no crontab for" in stderr:
            return []
        return None

    lines = [line.rstrip("\n") for line in result.stdout.splitlines()]
    return lines


def _write_crontab_lines(lines):
    payload = "\n".join(lines).strip()
    if payload:
        payload += "\n"

    subprocess.run(
        ["crontab", "-"],
        input=payload,
        text=True,
        check=True,
    )


def _strip_status_cleanup_jobs(lines):
    return [line for line in lines if STATUS_LOG_CLEANUP_MARKER not in line]


def _get_status_cleanup_schedule():
    lines = _read_crontab_lines()
    if lines is None:
        return {
            "period": "none",
            "label": "Недоступно (cron не найден)",
            "available": False,
        }

    for line in lines:
        if STATUS_LOG_CLEANUP_MARKER not in line:
            continue

        marker_part = line.split(STATUS_LOG_CLEANUP_MARKER, 1)[-1].strip()
        period = "none"
        if marker_part.startswith(":"):
            period = marker_part[1:]

        period = period if period in STATUS_LOG_CLEANUP_PERIODS else "none"
        label = STATUS_LOG_CLEANUP_PERIODS.get(period, (None, "Выключено"))[1]
        return {"period": period, "label": label, "available": True}

    return {"period": "none", "label": "Выключено", "available": True}


def _set_status_cleanup_schedule(period):
    lines = _read_crontab_lines()
    if lines is None:
        return False, "Не удалось прочитать crontab (cron недоступен)."

    lines = _strip_status_cleanup_jobs(lines)

    if period in STATUS_LOG_CLEANUP_PERIODS:
        cron_expr, _ = STATUS_LOG_CLEANUP_PERIODS[period]
        cmd = _status_log_cleanup_command()
        lines.append(f"{cron_expr} {cmd} {STATUS_LOG_CLEANUP_MARKER}:{period}")

    try:
        _write_crontab_lines(lines)
    except Exception as e:
        return False, f"Ошибка записи crontab: {e}"

    if period in STATUS_LOG_CLEANUP_PERIODS:
        return True, f"Расписание очистки *.log (кроме *-status.log) установлено: {STATUS_LOG_CLEANUP_PERIODS[period][1]}"
    return True, "Расписание очистки *.log (кроме *-status.log) отключено"


def _cleanup_status_logs_now():
    pattern = os.path.join(LOGS_DIR, "*.log")
    deleted = 0
    failed = []

    for file_path in glob.glob(pattern):
        try:
            # Не трогаем status-логи, удаляем только обычные .log
            if os.path.isfile(file_path) and not file_path.endswith("-status.log"):
                os.remove(file_path)
                deleted += 1
        except Exception:
            failed.append(os.path.basename(file_path))

    if failed:
        return False, f"Удалено обычных .log: {deleted}. Ошибки: {', '.join(failed)}"
    return True, f"Удалено обычных .log (без *-status.log): {deleted}"


def _reset_persisted_traffic_data():
    """Полностью сбрасывает накопленную статистику трафика и ставит baseline по активным сессиям."""
    try:
        UserTrafficSample.query.delete()
        TrafficSessionState.query.delete()
        UserTrafficStat.query.delete()

        status_rows = [
            _parse_status_log(profile_key, filename)
            for profile_key, filename in STATUS_LOG_FILES.items()
        ]

        now = datetime.utcnow()
        seeded_sessions = 0
        seeded_users = set()
        seen_session_keys = set()

        for status_row in status_rows:
            profile = status_row.get("profile", "unknown")
            for client in status_row.get("clients", []):
                common_name = (client.get("common_name") or "-").strip()
                if not common_name or common_name == "-":
                    continue

                session_key = _build_session_key(profile, client)
                if session_key in seen_session_keys:
                    continue
                seen_session_keys.add(session_key)

                current_rx = int(client.get("bytes_received") or 0)
                current_tx = int(client.get("bytes_sent") or 0)

                db.session.add(
                    TrafficSessionState(
                        session_key=session_key,
                        profile=profile,
                        common_name=common_name,
                        real_address=(client.get("real_address") or "").strip() or None,
                        virtual_address=(client.get("virtual_address") or "").strip() or None,
                        connected_since_ts=int(client.get("connected_since_ts") or 0),
                        last_bytes_received=current_rx,
                        last_bytes_sent=current_tx,
                        is_active=True,
                        last_seen_at=now,
                        ended_at=None,
                    )
                )
                seeded_sessions += 1

                if common_name not in seeded_users:
                    db.session.add(
                        UserTrafficStat(
                            common_name=common_name,
                            total_received=0,
                            total_sent=0,
                            total_received_vpn=0,
                            total_sent_vpn=0,
                            total_received_antizapret=0,
                            total_sent_antizapret=0,
                            total_sessions=0,
                            first_seen_at=now,
                            last_seen_at=now,
                        )
                    )
                    seeded_users.add(common_name)

        db.session.commit()
        return True, (
            "Накопленная статистика трафика очищена. "
            f"Точка отсчета установлена: пользователей {len(seeded_users)}, активных сессий {seeded_sessions}."
        )
    except Exception as e:
        db.session.rollback()
        return False, f"Ошибка сброса статистики трафика: {e}"


def _read_log_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _human_bytes(value):
    size = float(value or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    precision = 0 if idx == 0 else (2 if size < 10 else 1)
    return f"{size:.{precision}f} {units[idx]}"


def _human_device_type(platform):
    if not platform:
        return "Не определено"

    key = str(platform).strip().lower()
    mapping = {
        "win": "Windows",
        "windows": "Windows",
        "ios": "iOS (iPhone/iPad)",
        "android": "Android",
        "mac": "macOS",
        "macos": "macOS",
        "darwin": "macOS",
        "linux": "Linux",
    }
    return mapping.get(key, platform)


def _normalize_openvpn_endpoint(endpoint):
    """Remove OpenVPN transport prefixes from endpoint token."""
    if not endpoint:
        return endpoint
    return re.sub(r"^(?:tcp|udp)\d(?:-server)?:", "", endpoint.strip(), flags=re.IGNORECASE)


def _extract_ip_from_openvpn_address(address):
    """Extract host/IP from OpenVPN real address token."""
    normalized = _normalize_openvpn_endpoint(address)
    if not normalized:
        return normalized

    if normalized.startswith("["):
        m_v6 = re.match(r"^\[([^\]]+)\](?::\d+)?$", normalized)
        if m_v6:
            return m_v6.group(1)

    if ":" in normalized:
        host_part, maybe_port = normalized.rsplit(":", 1)
        if maybe_port.isdigit():
            return host_part

    return normalized


def _profile_meta(profile_key):
    is_antizapret = profile_key.startswith("antizapret")
    is_tcp = "-tcp" in profile_key
    return {
        "network": "Antizapret" if is_antizapret else "VPN",
        "transport": "TCP" if is_tcp else "UDP",
    }


def _format_dt(dt_obj):
    if not dt_obj:
        return "-"
    try:
        return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def _build_session_key(profile, client):
    common_name = (client.get("common_name") or "-").strip()
    real_address = (client.get("real_address") or "-").strip()
    virtual_address = (client.get("virtual_address") or "-").strip()
    connected_since_ts = int(client.get("connected_since_ts") or 0)
    return f"{profile}|{common_name}|{real_address}|{virtual_address}|{connected_since_ts}"


def _persist_traffic_snapshot(status_rows):
    """Сохраняет дельту трафика из текущего снимка *-status.log в БД."""
    now = datetime.utcnow()

    sessions_by_key = {
        row.session_key: row
        for row in TrafficSessionState.query.all()
    }
    previously_active_keys = {
        key for key, row in sessions_by_key.items() if bool(row.is_active)
    }
    stats_by_user = {
        row.common_name: row
        for row in UserTrafficStat.query.all()
    }

    seen_keys = set()

    for status_row in status_rows:
        profile = status_row.get("profile", "unknown")
        for client in status_row.get("clients", []):
            session_key = _build_session_key(profile, client)
            seen_keys.add(session_key)

            current_rx = int(client.get("bytes_received") or 0)
            current_tx = int(client.get("bytes_sent") or 0)
            common_name = (client.get("common_name") or "-").strip()
            is_antizapret_profile = str(profile).startswith("antizapret")

            session_state = sessions_by_key.get(session_key)
            is_new_session = session_state is None

            if is_new_session:
                session_state = TrafficSessionState(
                    session_key=session_key,
                    profile=profile,
                    common_name=common_name,
                    real_address=(client.get("real_address") or "").strip() or None,
                    virtual_address=(client.get("virtual_address") or "").strip() or None,
                    connected_since_ts=int(client.get("connected_since_ts") or 0),
                    last_bytes_received=current_rx,
                    last_bytes_sent=current_tx,
                    is_active=True,
                    last_seen_at=now,
                    ended_at=None,
                )
                db.session.add(session_state)
                sessions_by_key[session_key] = session_state
                delta_rx = max(current_rx, 0)
                delta_tx = max(current_tx, 0)
            else:
                delta_rx = current_rx - int(session_state.last_bytes_received or 0)
                delta_tx = current_tx - int(session_state.last_bytes_sent or 0)

                # Если счётчик сбросился, учитываем текущее значение как новую дельту.
                if delta_rx < 0:
                    delta_rx = max(current_rx, 0)
                if delta_tx < 0:
                    delta_tx = max(current_tx, 0)

                session_state.last_bytes_received = current_rx
                session_state.last_bytes_sent = current_tx
                session_state.last_seen_at = now
                session_state.is_active = True
                session_state.ended_at = None

            user_stat = stats_by_user.get(common_name)
            if user_stat is None:
                user_stat = UserTrafficStat(
                    common_name=common_name,
                    total_received=0,
                    total_sent=0,
                    total_received_vpn=0,
                    total_sent_vpn=0,
                    total_received_antizapret=0,
                    total_sent_antizapret=0,
                    total_sessions=0,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                db.session.add(user_stat)
                stats_by_user[common_name] = user_stat

            user_stat.total_received = int(user_stat.total_received or 0) + max(delta_rx, 0)
            user_stat.total_sent = int(user_stat.total_sent or 0) + max(delta_tx, 0)

            if max(delta_rx, 0) > 0 or max(delta_tx, 0) > 0:
                db.session.add(
                    UserTrafficSample(
                        common_name=common_name,
                        network_type="antizapret" if is_antizapret_profile else "vpn",
                        delta_received=max(delta_rx, 0),
                        delta_sent=max(delta_tx, 0),
                        created_at=now,
                    )
                )

            if is_antizapret_profile:
                user_stat.total_received_antizapret = int(user_stat.total_received_antizapret or 0) + max(delta_rx, 0)
                user_stat.total_sent_antizapret = int(user_stat.total_sent_antizapret or 0) + max(delta_tx, 0)
            else:
                user_stat.total_received_vpn = int(user_stat.total_received_vpn or 0) + max(delta_rx, 0)
                user_stat.total_sent_vpn = int(user_stat.total_sent_vpn or 0) + max(delta_tx, 0)
            user_stat.last_seen_at = now
            if is_new_session:
                user_stat.total_sessions = int(user_stat.total_sessions or 0) + 1

    for session_key, session_state in sessions_by_key.items():
        if session_key in seen_keys or session_key not in previously_active_keys:
            continue
        if session_state.is_active:
            session_state.is_active = False
            session_state.ended_at = now

    db.session.commit()


def _collect_persisted_traffic_data(active_names):
    users = UserTrafficStat.query.all()
    now = datetime.utcnow()
    day_1_since = now - timedelta(days=1)
    day_7_since = now - timedelta(days=7)
    day_30_since = now - timedelta(days=30)

    recent_samples = UserTrafficSample.query.filter(
        UserTrafficSample.created_at >= day_30_since
    ).all()

    recent_usage = defaultdict(
        lambda: {"days_1": 0, "days_7": 0, "days_30": 0}
    )
    for sample in recent_samples:
        sample_time = sample.created_at
        if not sample_time:
            continue
        delta_total = int(sample.delta_received or 0) + int(sample.delta_sent or 0)
        if delta_total <= 0:
            continue

        user_bucket = recent_usage[sample.common_name]
        user_bucket["days_30"] += delta_total
        if sample_time >= day_7_since:
            user_bucket["days_7"] += delta_total
        if sample_time >= day_1_since:
            user_bucket["days_1"] += delta_total

    users_sorted = sorted(
        users,
        key=lambda row: (int(row.total_received or 0) + int(row.total_sent or 0)),
        reverse=True,
    )

    rows = []
    total_received = 0
    total_sent = 0
    total_received_vpn = 0
    total_sent_vpn = 0
    total_received_antizapret = 0
    total_sent_antizapret = 0

    for row in users_sorted:
        rx = int(row.total_received or 0)
        tx = int(row.total_sent or 0)
        rx_vpn = int(row.total_received_vpn or 0)
        tx_vpn = int(row.total_sent_vpn or 0)
        rx_antizapret = int(row.total_received_antizapret or 0)
        tx_antizapret = int(row.total_sent_antizapret or 0)
        total = rx + tx
        total_received += rx
        total_sent += tx
        total_received_vpn += rx_vpn
        total_sent_vpn += tx_vpn
        total_received_antizapret += rx_antizapret
        total_sent_antizapret += tx_antizapret

        recent = recent_usage.get(row.common_name, {"days_1": 0, "days_7": 0, "days_30": 0})
        traffic_1d = int(recent.get("days_1", 0))
        traffic_7d = int(recent.get("days_7", 0))
        traffic_30d = int(recent.get("days_30", 0))

        is_active = row.common_name in active_names
        rows.append(
            {
                "common_name": row.common_name,
                "total_received": rx,
                "total_sent": tx,
                "total_bytes": total,
                "total_received_vpn": rx_vpn,
                "total_sent_vpn": tx_vpn,
                "total_bytes_vpn": rx_vpn + tx_vpn,
                "total_received_antizapret": rx_antizapret,
                "total_sent_antizapret": tx_antizapret,
                "total_bytes_antizapret": rx_antizapret + tx_antizapret,
                "total_received_human": _human_bytes(rx),
                "total_sent_human": _human_bytes(tx),
                "total_bytes_human": _human_bytes(total),
                "total_received_vpn_human": _human_bytes(rx_vpn),
                "total_sent_vpn_human": _human_bytes(tx_vpn),
                "total_bytes_vpn_human": _human_bytes(rx_vpn + tx_vpn),
                "total_received_antizapret_human": _human_bytes(rx_antizapret),
                "total_sent_antizapret_human": _human_bytes(tx_antizapret),
                "total_bytes_antizapret_human": _human_bytes(rx_antizapret + tx_antizapret),
                "traffic_1d": traffic_1d,
                "traffic_7d": traffic_7d,
                "traffic_30d": traffic_30d,
                "traffic_1d_human": _human_bytes(traffic_1d),
                "traffic_7d_human": _human_bytes(traffic_7d),
                "traffic_30d_human": _human_bytes(traffic_30d),
                "total_sessions": int(row.total_sessions or 0),
                "first_seen_at": _format_dt(row.first_seen_at),
                "last_seen_at": _format_dt(row.last_seen_at),
                "is_active": is_active,
            }
        )

    summary = {
        "users_count": len(rows),
        "active_users_count": sum(1 for item in rows if item.get("is_active")),
        "offline_users_count": sum(1 for item in rows if not item.get("is_active")),
        "total_received": total_received,
        "total_sent": total_sent,
        "total_received_human": _human_bytes(total_received),
        "total_sent_human": _human_bytes(total_sent),
        "total_traffic_human": _human_bytes(total_received + total_sent),
        "total_received_vpn": total_received_vpn,
        "total_sent_vpn": total_sent_vpn,
        "total_received_antizapret": total_received_antizapret,
        "total_sent_antizapret": total_sent_antizapret,
        "total_received_vpn_human": _human_bytes(total_received_vpn),
        "total_sent_vpn_human": _human_bytes(total_sent_vpn),
        "total_traffic_vpn_human": _human_bytes(total_received_vpn + total_sent_vpn),
        "total_received_antizapret_human": _human_bytes(total_received_antizapret),
        "total_sent_antizapret_human": _human_bytes(total_sent_antizapret),
        "total_traffic_antizapret_human": _human_bytes(total_received_antizapret + total_sent_antizapret),
    }
    return rows, summary


def _parse_status_log(profile_key, filename):
    path = filename
    raw = _read_log_file(path)
    meta = _profile_meta(profile_key)

    if not raw:
        return {
            "profile": profile_key,
            "label": f"{meta['network']} {meta['transport']}",
            "filename": os.path.basename(path),
            "exists": False,
            "snapshot_time": "-",
            "updated_at": "-",
            "client_count": 0,
            "unique_real_ips": 0,
            "total_received": 0,
            "total_sent": 0,
            "total_received_human": _human_bytes(0),
            "total_sent_human": _human_bytes(0),
            "total_traffic_human": _human_bytes(0),
            "clients": [],
        }

    time_match = re.search(r"TIME,([^,\n]+),(\d{10,})", raw)
    if time_match:
        snapshot_time = time_match.group(1).strip()
    else:
        snapshot_time = "-"

    try:
        updated_at = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        updated_at = "-"

    client_pattern = re.compile(
        r"CLIENT_LIST,([^,\n]+),([^,\n]+),([^,\n]*),([^,\n]*),(\d+),(\d+),([^,\n]+),(\d+),([^,\n]*),([^,\n]*),([^,\n]*),([^,\n\r ]+)"
    )

    clients = []
    for match in client_pattern.finditer(raw):
        common_name = match.group(1).strip()
        real_address = match.group(2).strip()
        virtual_address = match.group(3).strip()
        bytes_received = int(match.group(5) or 0)
        bytes_sent = int(match.group(6) or 0)
        connected_since = match.group(7).strip()
        connected_since_ts = int(match.group(8) or 0)
        cipher = match.group(12).strip()

        ip_only = _extract_ip_from_openvpn_address(real_address)

        clients.append(
            {
                "common_name": common_name,
                "real_address": real_address,
                "real_ip": ip_only,
                "virtual_address": virtual_address,
                "bytes_received": bytes_received,
                "bytes_sent": bytes_sent,
                "total_bytes": bytes_received + bytes_sent,
                "bytes_received_human": _human_bytes(bytes_received),
                "bytes_sent_human": _human_bytes(bytes_sent),
                "total_bytes_human": _human_bytes(bytes_received + bytes_sent),
                "connected_since": connected_since,
                "connected_since_ts": connected_since_ts,
                "cipher": cipher,
            }
        )

    clients.sort(key=lambda x: x["total_bytes"], reverse=True)

    total_received = sum(c["bytes_received"] for c in clients)
    total_sent = sum(c["bytes_sent"] for c in clients)
    unique_real_ips = len({c["real_ip"] for c in clients if c.get("real_ip")})

    return {
        "profile": profile_key,
        "label": f"{meta['network']} {meta['transport']}",
        "filename": os.path.basename(path),
        "exists": True,
        "snapshot_time": snapshot_time,
        "updated_at": updated_at,
        "client_count": len(clients),
        "unique_real_ips": unique_real_ips,
        "total_received": total_received,
        "total_sent": total_sent,
        "total_received_human": _human_bytes(total_received),
        "total_sent_human": _human_bytes(total_sent),
        "total_traffic_human": _human_bytes(total_received + total_sent),
        "clients": clients,
    }


def _parse_event_log(profile_key, filename):
    path = filename
    raw = _read_log_file(path)
    meta = _profile_meta(profile_key)

    if not raw:
        return {
            "profile": profile_key,
            "label": f"{meta['network']} {meta['transport']}",
            "filename": os.path.basename(path),
            "exists": False,
            "updated_at": "-",
            "updated_at_ts": 0,
            "line_count": 0,
            "event_counts": {},
            "peer_connected_clients": [],
            "client_sessions": [],
            "recent_lines": [],
        }

    try:
        updated_at_ts = int(os.path.getmtime(path))
        updated_at = datetime.fromtimestamp(updated_at_ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        updated_at_ts = 0
        updated_at = "-"

    line_count = len(raw.splitlines())
    event_patterns = {
        "peer_connection": r"Peer Connection Initiated",
        "push_request": r"PUSH_REQUEST",
        "push_reply": r"PUSH_REPLY",
        "tls_events": r"\bTLS:",
        "multi_create": r"MULTI_sva|MULTI: multi_create_instance called",
        "sigterm": r"\bSIGTERM\b",
    }
    event_counts = {
        key: len(re.findall(pattern, raw)) for key, pattern in event_patterns.items()
    }

    peer_clients = re.findall(r"\[([^\]]+)\] Peer Connection Initiated", raw)
    peer_connected = Counter(peer_clients).most_common(10)

    # Извлекаем сведения о клиенте: endpoint/IP, версия (IV_VER), платформа (IV_PLAT)
    endpoint_info = {}

    for line_no, line in enumerate(raw.splitlines()):
        line = line.strip()
        if not line:
            continue

        # Привязка CN к endpoint по строке VERIFY OK depth=0
        m_verify = re.search(r"^([^\s]+:\d+)\s+VERIFY OK: depth=0, CN=([^\s]+)", line)
        if m_verify:
            endpoint = _normalize_openvpn_endpoint(m_verify.group(1))
            client_name = m_verify.group(2)
            endpoint_info.setdefault(
                endpoint,
                {
                    "client": "-",
                    "ip": _extract_ip_from_openvpn_address(endpoint),
                    "version": None,
                    "platform": None,
                    "last_order": -1,
                },
            )
            endpoint_info[endpoint]["client"] = client_name

        # Альтернативная привязка из Peer Connection Initiated
        m_peer = re.search(r"\[([^\]]+)\] Peer Connection Initiated with \[AF_INET\]([^\s]+:\d+)", line)
        if m_peer:
            client_name = m_peer.group(1)
            endpoint = _normalize_openvpn_endpoint(m_peer.group(2))
            endpoint_info.setdefault(
                endpoint,
                {
                    "client": "-",
                    "ip": _extract_ip_from_openvpn_address(endpoint),
                    "version": None,
                    "platform": None,
                    "last_order": -1,
                },
            )
            endpoint_info[endpoint]["client"] = client_name

        # Привязка из строк вида ClientName/ip:port ...
        m_name_endpoint = re.search(r"([A-Za-z0-9_.\-]+)/([^\s,]+:\d+)", line)
        if m_name_endpoint:
            client_name = m_name_endpoint.group(1)
            endpoint = _normalize_openvpn_endpoint(m_name_endpoint.group(2))
            endpoint_info.setdefault(
                endpoint,
                {
                    "client": "-",
                    "ip": _extract_ip_from_openvpn_address(endpoint),
                    "version": None,
                    "platform": None,
                    "last_order": -1,
                },
            )
            if endpoint_info[endpoint]["client"] == "-":
                endpoint_info[endpoint]["client"] = client_name

        # Версия и платформа клиента (peer info)
        m_peer_info = re.search(r"^([^\s]+:\d+)\s+peer info: (IV_VER|IV_PLAT)=([^\s]+)", line)
        if m_peer_info:
            endpoint = _normalize_openvpn_endpoint(m_peer_info.group(1))
            key = m_peer_info.group(2)
            val = m_peer_info.group(3)
            endpoint_info.setdefault(
                endpoint,
                {
                    "client": "-",
                    "ip": _extract_ip_from_openvpn_address(endpoint),
                    "version": None,
                    "platform": None,
                    "last_order": -1,
                },
            )
            if key == "IV_VER":
                endpoint_info[endpoint]["version"] = val
                endpoint_info[endpoint]["last_order"] = line_no
            elif key == "IV_PLAT":
                endpoint_info[endpoint]["platform"] = val
                endpoint_info[endpoint]["last_order"] = line_no

    client_sessions = []
    for endpoint, info in endpoint_info.items():
        client_sessions.append(
            {
                "client": info["client"],
                "endpoint": endpoint,
                "ip": info["ip"],
                "version": info.get("version"),
                "platform": info.get("platform"),
                "last_order": info.get("last_order", -1),
            }
        )

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    recent_lines = [line[:220] for line in lines[-8:]]

    return {
        "profile": profile_key,
        "label": f"{meta['network']} {meta['transport']}",
        "filename": os.path.basename(path),
        "exists": True,
        "updated_at": updated_at,
        "updated_at_ts": updated_at_ts,
        "line_count": line_count,
        "event_counts": event_counts,
        "peer_connected_clients": peer_connected,
        "client_sessions": client_sessions,
        "recent_lines": recent_lines,
    }


def _collect_logs_dashboard_data():
    status_rows = [
        _parse_status_log(profile_key, filename)
        for profile_key, filename in STATUS_LOG_FILES.items()
    ]

    _persist_traffic_snapshot(status_rows)

    event_rows = [
        _parse_event_log(profile_key, filename)
        for profile_key, filename in EVENT_LOG_FILES.items()
    ]

    total_active_clients = sum(item["client_count"] for item in status_rows)
    total_received = sum(item["total_received"] for item in status_rows)
    total_sent = sum(item["total_sent"] for item in status_rows)

    unique_client_names = set()
    unique_ips = set()
    client_aggregate = defaultdict(
        lambda: {
            "bytes_received": 0,
            "bytes_sent": 0,
            "sessions": 0,
            "profiles": set(),
            "ips": set(),
            "versions": set(),
            "platforms": set(),
            "ip_details": {},
        }
    )

    for item in status_rows:
        for client in item["clients"]:
            name = client["common_name"]
            unique_client_names.add(name)
            if client.get("real_ip"):
                unique_ips.add(client["real_ip"])

            client_aggregate[name]["bytes_received"] += client["bytes_received"]
            client_aggregate[name]["bytes_sent"] += client["bytes_sent"]
            client_aggregate[name]["sessions"] += 1
            client_aggregate[name]["profiles"].add(item["label"])
            if client.get("real_ip"):
                client_aggregate[name]["ips"].add(client["real_ip"])
                if client["real_ip"] not in client_aggregate[name]["ip_details"]:
                    client_aggregate[name]["ip_details"][client["real_ip"]] = {
                        "version": None,
                        "platform": None,
                        "rank": -1,
                    }

    # Дополняем версии/платформы и IP из event-логов
    for event in event_rows:
        for sess in event.get("client_sessions", []):
            client_name = sess.get("client")
            if not client_name or client_name == "-":
                continue

            # Подключенные клиенты формируются только из *-status.log.
            # Event-логи лишь дополняют метаданные уже активных клиентов.
            if client_name not in client_aggregate:
                continue

            sess_ip = sess.get("ip")
            if not sess_ip:
                continue

            # Привязываем версию/платформу только к активным IP из status-логов.
            if sess_ip not in client_aggregate[client_name]["ips"]:
                continue

            if sess_ip not in client_aggregate[client_name]["ip_details"]:
                client_aggregate[client_name]["ip_details"][sess_ip] = {
                        "version": None,
                        "platform": None,
                        "rank": -1,
                    }

            # Для активного IP берём только наиболее актуальные данные из event-логов.
            event_rank = int(event.get("updated_at_ts", 0)) * 1000000 + int(sess.get("last_order", -1))
            current_rank = int(client_aggregate[client_name]["ip_details"][sess_ip].get("rank", -1))
            if event_rank >= current_rank:
                client_aggregate[client_name]["ip_details"][sess_ip]["version"] = sess.get("version")
                client_aggregate[client_name]["ip_details"][sess_ip]["platform"] = sess.get("platform")
                client_aggregate[client_name]["ip_details"][sess_ip]["rank"] = event_rank

    connected_clients = []
    for name, stats in client_aggregate.items():
        total_bytes = stats["bytes_received"] + stats["bytes_sent"]
        ip_device_map = []
        client_versions_set = set()
        client_platforms_set = set()
        for ip in sorted(stats["ips"]):
            details = stats["ip_details"].get(ip, {"version": None, "platform": None})
            platform_str = _human_device_type(details.get("platform")) if details.get("platform") else "Не определено"
            version_str = details.get("version") or "Не определено"

            if version_str != "Не определено":
                client_versions_set.add(version_str)
            if platform_str != "Не определено":
                client_platforms_set.add(platform_str)

            ip_device_map.append({
                "ip": ip,
                "platform": platform_str,
                "version": version_str,
            })

        connected_clients.append(
            {
                "common_name": name,
                "bytes_received": stats["bytes_received"],
                "bytes_sent": stats["bytes_sent"],
                "total_bytes": total_bytes,
                "bytes_received_human": _human_bytes(stats["bytes_received"]),
                "bytes_sent_human": _human_bytes(stats["bytes_sent"]),
                "total_bytes_human": _human_bytes(total_bytes),
                "sessions": stats["sessions"],
                "profiles": ", ".join(sorted(stats["profiles"])),
                "ips": ", ".join(sorted(stats["ips"])) if stats["ips"] else "-",
                "client_versions": ", ".join(sorted(client_versions_set)) if client_versions_set else "-",
                "device_types": ", ".join(sorted(client_platforms_set)) if client_platforms_set else "Не определено",
                "ip_device_map": ip_device_map,
            }
        )

    connected_clients.sort(key=lambda item: item["common_name"].lower())

    persisted_traffic_rows, persisted_traffic_summary = _collect_persisted_traffic_data(
        active_names=unique_client_names
    )

    total_event_lines = sum(item["line_count"] for item in event_rows)
    total_event_counts = Counter()
    for item in event_rows:
        total_event_counts.update(item.get("event_counts", {}))

    required_event_log_files = sorted(EVENT_LOG_FILES.values())
    existing_event_log_files = [
        filename
        for filename in required_event_log_files
        if os.path.exists(filename)
    ]
    missing_event_log_files = [
        os.path.basename(filename) for filename in required_event_log_files if filename not in existing_event_log_files
    ]
    openvpn_logging_enabled = len(existing_event_log_files) > 0

    grouped_status_map = {
        "Antizapret": {
            "network": "Antizapret",
            "files": [],
            "snapshot_times": [],
            "updated_values": [],
            "client_count": 0,
            "total_received": 0,
            "total_sent": 0,
            "real_ips": set(),
            "transport_clients": {"TCP": 0, "UDP": 0},
        },
        "VPN": {
            "network": "VPN",
            "files": [],
            "snapshot_times": [],
            "updated_values": [],
            "client_count": 0,
            "total_received": 0,
            "total_sent": 0,
            "real_ips": set(),
            "transport_clients": {"TCP": 0, "UDP": 0},
        },
    }

    for row in status_rows:
        network = "Antizapret" if row["profile"].startswith("antizapret") else "VPN"
        transport = "TCP" if row["profile"].endswith("-tcp") else "UDP"
        group = grouped_status_map[network]

        if row.get("filename"):
            group["files"].append(row["filename"])
        if row.get("snapshot_time") and row["snapshot_time"] != "-":
            group["snapshot_times"].append(row["snapshot_time"])
        if row.get("updated_at") and row["updated_at"] != "-":
            group["updated_values"].append(row["updated_at"])

        group["client_count"] += row.get("client_count", 0)
        group["total_received"] += row.get("total_received", 0)
        group["total_sent"] += row.get("total_sent", 0)
        group["transport_clients"][transport] += row.get("client_count", 0)

        for client in row.get("clients", []):
            if client.get("real_ip"):
                group["real_ips"].add(client["real_ip"])

    grouped_status_rows = []
    for network in ("Antizapret", "VPN"):
        group = grouped_status_map[network]
        total_traffic = group["total_received"] + group["total_sent"]
        grouped_status_rows.append(
            {
                "network": network,
                "files": ", ".join(sorted(set(group["files"]))),
                "snapshot_times": ", ".join(sorted(set(group["snapshot_times"]))),
                "updated_at": max(group["updated_values"]) if group["updated_values"] else "-",
                "client_count": group["client_count"],
                "unique_real_ips": len(group["real_ips"]),
                "transport_split": f"TCP: {group['transport_clients']['TCP']}, UDP: {group['transport_clients']['UDP']}",
                "total_received": group["total_received"],
                "total_sent": group["total_sent"],
                "total_traffic": total_traffic,
                "total_received_human": _human_bytes(group["total_received"]),
                "total_sent_human": _human_bytes(group["total_sent"]),
                "total_traffic_human": _human_bytes(total_traffic),
            }
        )

    grouped_event_map = {
        "Antizapret": {
            "network": "Antizapret",
            "files": [],
            "updated_values": [],
            "line_count": 0,
            "event_counts": Counter(),
            "peer_connected": Counter(),
            "recent_lines": [],
        },
        "VPN": {
            "network": "VPN",
            "files": [],
            "updated_values": [],
            "line_count": 0,
            "event_counts": Counter(),
            "peer_connected": Counter(),
            "recent_lines": [],
        },
    }

    for row in event_rows:
        network = "Antizapret" if row["profile"].startswith("antizapret") else "VPN"
        transport = "TCP" if row["profile"].endswith("-tcp") else "UDP"
        group = grouped_event_map[network]

        if row.get("filename"):
            group["files"].append(row["filename"])
        if row.get("updated_at") and row["updated_at"] != "-":
            group["updated_values"].append(row["updated_at"])

        group["line_count"] += row.get("line_count", 0)
        group["event_counts"].update(row.get("event_counts", {}))
        group["peer_connected"].update(dict(row.get("peer_connected_clients", [])))

        for line in row.get("recent_lines", []):
            group["recent_lines"].append(f"[{transport}] {line}")

    grouped_event_rows = []
    for network in ("Antizapret", "VPN"):
        group = grouped_event_map[network]
        grouped_event_rows.append(
            {
                "network": network,
                "files": ", ".join(sorted(set(group["files"]))),
                "updated_at": max(group["updated_values"]) if group["updated_values"] else "-",
                "line_count": group["line_count"],
                "event_counts": dict(group["event_counts"]),
                "peer_connected_clients": group["peer_connected"].most_common(10),
                "recent_lines": group["recent_lines"][-10:],
            }
        )

    return {
        "status_rows": status_rows,
        "event_rows": event_rows,
        "grouped_status_rows": grouped_status_rows,
        "grouped_event_rows": grouped_event_rows,
        "openvpn_logging_enabled": openvpn_logging_enabled,
        "missing_event_log_files": missing_event_log_files,
        "summary": {
            "total_active_clients": total_active_clients,
            "unique_client_names": len(unique_client_names),
            "unique_ips": len(unique_ips),
            "total_received": total_received,
            "total_sent": total_sent,
            "total_received_human": _human_bytes(total_received),
            "total_sent_human": _human_bytes(total_sent),
            "total_traffic_human": _human_bytes(total_received + total_sent),
            "total_event_lines": total_event_lines,
            "total_event_counts": dict(total_event_counts),
        },
        "connected_clients": connected_clients,
        "persisted_traffic_rows": persisted_traffic_rows,
        "persisted_traffic_summary": persisted_traffic_summary,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# Главная страница
@app.route("/", methods=["GET", "POST"])
@auth_manager.login_required
def index():
    if request.method == "GET":
        _idx_user = User.query.filter_by(username=session["username"]).first()
        group = session.get("openvpn_group", "GROUP_UDP\\TCP")
        if group not in GROUP_FOLDERS:
            group = "GROUP_UDP\\TCP"
        folders = GROUP_FOLDERS[group]
        config_file_handler.config_paths["openvpn"] = folders
        file_validator.config_paths["openvpn"] = folders
        openvpn_files, wg_files, amneziawg_files = config_file_handler.get_config_files()
        cert_expiry = config_file_handler.get_openvpn_cert_expiry()
        raw_banned_clients = _read_banned_clients()
        banned_clients = set()

        for file_path in openvpn_files:
            filename = os.path.basename(file_path)
            client_name = config_file_handler._extract_client_name_from_ovpn(filename)
            if client_name and client_name in raw_banned_clients:
                banned_clients.add(client_name)

        if _idx_user and _idx_user.role == 'viewer':
            _allowed = {acc.config_name for acc in _idx_user.allowed_configs}
            openvpn_files = [f for f in openvpn_files if os.path.basename(f) in _allowed]
            wg_files = [f for f in wg_files if os.path.basename(f) in _allowed]
            amneziawg_files = [f for f in amneziawg_files if os.path.basename(f) in _allowed]

        return render_template(
            "index.html",
            openvpn_files=openvpn_files,
            wg_files=wg_files,
            amneziawg_files=amneziawg_files,
            cert_expiry=cert_expiry,
            banned_clients=banned_clients,
            current_openvpn_group=group,
            current_openvpn_folders=folders,
        )

    if request.method == "POST":
        _post_user = User.query.filter_by(username=session["username"]).first()
        if not _post_user or _post_user.role != 'admin':
            return jsonify({"success": False, "message": "Доступ запрещён."}), 403
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


@app.route("/api/openvpn/client-block", methods=["POST"])
@auth_manager.admin_required
def api_openvpn_client_block():
    client_name = request.form.get("client_name", "").strip()
    blocked_raw = (request.form.get("blocked", "").strip().lower())

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректный CN клиента."}), 400

    should_block = blocked_raw in {"1", "true", "yes", "on"}

    try:
        _ensure_client_connect_ban_check_block()
        banned_clients = _read_banned_clients()

        if should_block:
            banned_clients.add(client_name)
        else:
            banned_clients.discard(client_name)

        _write_banned_clients(banned_clients)
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "blocked": should_block,
                "message": "Клиент заблокирован." if should_block else "Блокировка снята.",
            }
        )
    except PermissionError:
        return jsonify({"success": False, "message": "Нет прав на запись banned_clients."}), 500
    except OSError as e:
        return jsonify({"success": False, "message": f"Ошибка работы с banned_clients: {e}"}), 500


@app.route("/set_openvpn_group", methods=["POST"])
@auth_manager.login_required
def set_openvpn_group():
    grp = request.form.get("group", "GROUP_UDP\\TCP")
    if grp not in GROUP_FOLDERS:
        grp = "GROUP_UDP\\TCP"
    session["openvpn_group"] = grp
    return redirect(url_for("index"))

# Страница логина
@app.route("/login", methods=["GET", "POST"])
def login():
    # Если IP ограничения включены и IP не разрешен - показываем страницу блокировки
    if ip_restriction.is_enabled():
        client_ip = ip_restriction.get_client_ip()
        if not ip_restriction.is_ip_allowed(client_ip):
            return redirect(url_for("ip_blocked"))

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
            session["user_role"] = user.role
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
@app.route("/qr_download/<token>")
def one_time_qr_download(token):
    if not token or len(token) < 16:
        abort(404)

    now = datetime.utcnow()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    try:
        token_row = QrDownloadToken.query.filter_by(token_hash=token_hash).first()
        if not token_row or token_row.used_at is not None or token_row.expires_at < now:
            abort(410, description="Ссылка истекла или уже использована")

        updated = db.session.query(QrDownloadToken).filter(
            QrDownloadToken.id == token_row.id,
            QrDownloadToken.used_at.is_(None),
            QrDownloadToken.expires_at >= now,
        ).update({"used_at": now}, synchronize_session=False)

        if updated != 1:
            db.session.rollback()
            abort(410, description="Ссылка уже использована")

        db.session.commit()

        file_path, _ = _resolve_config_file(token_row.config_type, token_row.config_name)
        if not file_path:
            abort(404, description="Файл не найден")

        base = os.path.basename(file_path)
        return send_from_directory(
            os.path.dirname(file_path),
            base,
            as_attachment=True,
            download_name=base,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Аларм! ошибка: {str(e)}")
        abort(500)


@app.route("/download/<file_type>/<path:filename>")
@auth_manager.login_required
@file_validator.validate_file
def download(file_path, clean_name):
    # Проверка доступа viewer
    _dl_user = User.query.filter_by(username=session["username"]).first()
    if _dl_user and _dl_user.role == 'viewer':
        _cfg_type = _get_config_type(file_path)
        if _cfg_type not in ('openvpn', 'wg', 'amneziawg'):
            abort(403)
        _cfg_name = os.path.basename(file_path)
        _access = ViewerConfigAccess.query.filter_by(
            user_id=_dl_user.id, config_name=_cfg_name
        ).first()
        if not _access:
            abort(403)
    try:
        base = os.path.basename(file_path)

        # Новый паттерн для преобразования имени файла
        # Универсальный паттерн для всех случаев
        pattern = re.compile(
            r"^(?P<prefix>antizapret|vpn)-(?P<client>[\w\-]+?)(?:_(?P<id>[\w\-]+))?(?:-\([^)]+\))?(?:-(?P<proto>udp|tcp))?(?:-(?P<suffix>wg|am))?\.(?P<ext>ovpn|conf)$",
            re.IGNORECASE,
        )
        m = pattern.match(base)

        if m:
            prefix = m.group('prefix').lower()
            client = m.group('client')
            id_ = m.group('id')
            proto = m.group('proto')
            ext = m.group('ext').lower()
            # Формируем имя: az-<client>[-<id>][-<proto>].<ext> или vpn-<client>[-<id>][-<proto>].<ext>
            if prefix == 'antizapret':
                prefix_out = 'az'
            else:
                prefix_out = 'vpn'
            if id_:
                base_name = f"{prefix_out}-{client}_{id_}"
            else:
                base_name = f"{prefix_out}-{client}"
            if proto:
                download_name = f"{base_name}-{proto}.{ext}"
            else:
                download_name = f"{base_name}.{ext}"
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

# Роут для публичного скачивания файлов
@app.route("/public_download/<router>")
def public_download(router):
    if not PUBLIC_DOWNLOAD_ENABLED:
        abort(404)
    filename = RESULT_DIR_FILES.get(router)
    if not filename:
        abort(404)

    return send_from_directory("/root/antizapret/result", filename, as_attachment=True)


@app.route("/toggle_public_download", methods=["POST"])
@auth_manager.admin_required
def toggle_public_download():
    global PUBLIC_DOWNLOAD_ENABLED

    enabled_value = request.form.get("enabled", "").lower()
    if enabled_value in ("true", "false"):
        next_state = enabled_value == "true"
    else:
        next_state = not PUBLIC_DOWNLOAD_ENABLED

    PUBLIC_DOWNLOAD_ENABLED = next_state
    env_value = "true" if next_state else "false"
    _set_env_value("PUBLIC_DOWNLOAD_ENABLED", env_value)
    os.environ["PUBLIC_DOWNLOAD_ENABLED"] = env_value

    flash(
        "Публичный доступ к файлам включен." if next_state else "Публичный доступ к файлам выключен.",
        "success",
    )
    return_to = request.form.get("return_to", "edit_files")
    if return_to not in ("edit_files", "settings"):
        return_to = "edit_files"
    return redirect(url_for(return_to))

# Роут для формирования QR кода
@app.route("/generate_qr/<file_type>/<path:filename>")
@auth_manager.login_required
@file_validator.validate_file
def generate_qr(file_path, clean_name):
    # Проверка доступа viewer
    _qr_user = User.query.filter_by(username=session["username"]).first()
    if _qr_user and _qr_user.role == 'viewer':
        _cfg_type = _get_config_type(file_path)
        if _cfg_type not in ('openvpn', 'wg', 'amneziawg'):
            abort(403)
        _cfg_name = os.path.basename(file_path)
        _access = ViewerConfigAccess.query.filter_by(
            user_id=_qr_user.id, config_name=_cfg_name
        ).first()
        if not _access:
            abort(403)
    try:
        with open(file_path, "r") as file:
            config_text = file.read()

        config_type = _get_config_type(file_path)

        # AmneziaWG конфиги часто слишком плотные для стабильного сканирования,
        # даже когда формально помещаются в QR. Для крупных конфигов сразу
        # отдаём QR со ссылкой на скачивание.
        force_download_url_qr = (
            config_type == "amneziawg" and len(config_text.encode("utf-8")) > 2200
        )

        if force_download_url_qr:
            download_url = _create_one_time_download_url(file_path)
            img_byte_arr = qr_generator.generate_qr_for_download_url(download_url)
            response = send_file(img_byte_arr, mimetype="image/png")
            response.headers["X-QR-Mode"] = "download-url"
            response.headers["X-QR-Message-Code"] = "CONFIG_TOO_LARGE_USE_DOWNLOAD"
            response.headers["X-QR-Download-Url"] = download_url
            return response

        try:
            img_byte_arr = qr_generator.generate_qr_code(config_text)
            response = send_file(img_byte_arr, mimetype="image/png")
            response.headers["X-QR-Mode"] = "config"
            return response
        except ValueError as qr_error:
            # Для конфигов, которые не помещаются в QR, отдаём QR со ссылкой на скачивание.
            if "слишком длинная" in str(qr_error):
                download_url = _create_one_time_download_url(file_path)
                img_byte_arr = qr_generator.generate_qr_for_download_url(download_url)
                response = send_file(img_byte_arr, mimetype="image/png")
                response.headers["X-QR-Mode"] = "download-url"
                response.headers["X-QR-Message-Code"] = "CONFIG_OVERFLOW_USE_DOWNLOAD"
                response.headers["X-QR-Download-Url"] = download_url
                return response
            raise
    except Exception as e:
        print(f"Аларм! ошибка: {str(e)}")
        abort(500)


@app.route("/generate_one_time_download/<file_type>/<path:filename>")
@auth_manager.login_required
@file_validator.validate_file
def generate_one_time_download(file_path, clean_name):
    _url_user = User.query.filter_by(username=session["username"]).first()
    if not _url_user or _url_user.role != 'admin':
        return jsonify({"success": False, "message": "Доступ запрещён."}), 403

    try:
        download_url = _create_one_time_download_url(file_path)
        return jsonify(
            {
                "success": True,
                "download_url": download_url,
            }
        )
    except HTTPException:
        raise
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        print(f"Аларм! ошибка: {str(e)}")
        abort(500)


# Роут для редактирования файлов конфигурации
@app.route("/edit-files", methods=["GET", "POST"])
@auth_manager.admin_required
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
                    timeout=290,
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
    return render_template(
        "edit_files.html",
        file_contents=file_contents,
        public_download_enabled=PUBLIC_DOWNLOAD_ENABLED,
    )


# Роут для запуска скрипта doall.sh
@app.route("/run-doall", methods=["POST"])
@auth_manager.admin_required
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


# Маршрут для страницы мониторинга
@app.route("/server_monitor", methods=["GET"])
@auth_manager.login_required
def server_monitor():
    iface = os.getenv("VNSTAT_IFACE", "ens3")
    cpu_usage = server_monitor_proc.get_cpu_usage()
    memory_usage = server_monitor_proc.get_memory_usage()
    return render_template(
        "server_monitor.html",
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        iface=iface,
    )


@app.route("/logs_dashboard", methods=["GET"])
@auth_manager.login_required
def logs_dashboard():
    dashboard_data = _collect_logs_dashboard_data()
    cleanup_schedule = _get_status_cleanup_schedule()
    cleanup_notice = request.args.get("cleanup_notice", "")
    cleanup_notice_kind = request.args.get("cleanup_notice_kind", "info")
    return render_template(
        "logs_dashboard.html",
        status_rows=dashboard_data["status_rows"],
        event_rows=dashboard_data["event_rows"],
        grouped_status_rows=dashboard_data["grouped_status_rows"],
        grouped_event_rows=dashboard_data["grouped_event_rows"],
        openvpn_logging_enabled=dashboard_data["openvpn_logging_enabled"],
        missing_event_log_files=dashboard_data["missing_event_log_files"],
        summary=dashboard_data["summary"],
        connected_clients=dashboard_data["connected_clients"],
        persisted_traffic_rows=dashboard_data["persisted_traffic_rows"],
        persisted_traffic_summary=dashboard_data["persisted_traffic_summary"],
        generated_at=dashboard_data["generated_at"],
        cleanup_schedule=cleanup_schedule,
        cleanup_notice=cleanup_notice,
        cleanup_notice_kind=cleanup_notice_kind,
    )


@app.route("/logs_dashboard/cleanup_status_now", methods=["POST"])
@auth_manager.admin_required
def logs_cleanup_status_now():
    ok, message = _cleanup_status_logs_now()
    return redirect(
        url_for(
            "logs_dashboard",
            cleanup_notice=message,
            cleanup_notice_kind="success" if ok else "error",
        )
    )


@app.route("/logs_dashboard/cleanup_status_schedule", methods=["POST"])
@auth_manager.admin_required
def logs_cleanup_status_schedule():
    period = (request.form.get("cleanup_period") or "none").strip().lower()
    if period not in ("none", "daily", "weekly", "monthly"):
        period = "none"

    ok, message = _set_status_cleanup_schedule(period)
    return redirect(
        url_for(
            "logs_dashboard",
            cleanup_notice=message,
            cleanup_notice_kind="success" if ok else "error",
        )
    )


@app.route("/logs_dashboard/reset_persisted_traffic", methods=["POST"])
@auth_manager.admin_required
def logs_reset_persisted_traffic():
    ok, message = _reset_persisted_traffic_data()
    return redirect(
        url_for(
            "logs_dashboard",
            cleanup_notice=message,
            cleanup_notice_kind="success" if ok else "error",
        )
    )


@app.route("/settings", methods=["GET", "POST"])
@auth_manager.admin_required
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

        ttl_raw = request.form.get("qr_download_token_ttl_seconds", "").strip()
        if ttl_raw:
            if ttl_raw.isdigit():
                ttl_value = int(ttl_raw)
                if 60 <= ttl_value <= 3600:
                    _set_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", str(ttl_value))
                    os.environ["QR_DOWNLOAD_TOKEN_TTL_SECONDS"] = str(ttl_value)
                    flash("TTL одноразовой QR-ссылки обновлен", "success")
                else:
                    flash("TTL QR-ссылки должен быть в диапазоне 60..3600 секунд", "error")
            else:
                flash("TTL QR-ссылки должен быть целым числом", "error")

        # --- Добавить пользователя ---
        username = request.form.get("username")
        password = request.form.get("password")
        if username and password:
            if len(password) < 8:
                flash("Пароль должен содержать минимум 8 символов!", "error")
            else:
                role = request.form.get("role", "admin")
                if role not in ('admin', 'viewer'):
                    role = 'admin'
                with app.app_context():
                    if User.query.filter_by(username=username).first():
                        flash(f"Пользователь '{username}' уже существует!", "error")
                    else:
                        user = User(username=username, role=role)
                        user.set_password(password)
                        db.session.add(user)
                        db.session.commit()
                        flash(f"Пользователь '{username}' ({role}) успешно добавлен!", "success")

        # --- Удалить пользователя ---
        delete_username = request.form.get("delete_username")
        if delete_username:
            if delete_username == session.get("username"):
                flash("Нельзя удалить собственный аккаунт!", "error")
            else:
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

        # --- Изменить роль ---
        change_role_username = request.form.get("change_role_username")
        new_role = request.form.get("new_role")
        if change_role_username and new_role:
            if new_role not in ('admin', 'viewer'):
                flash("Неверная роль!", "error")
            elif change_role_username == session.get("username"):
                flash("Нельзя изменить собственную роль!", "error")
            else:
                _role_user = User.query.filter_by(username=change_role_username).first()
                if _role_user:
                    _role_user.role = new_role
                    db.session.commit()
                    flash(f"Роль пользователя '{change_role_username}' изменена на '{new_role}'!", "success")
                else:
                    flash(f"Пользователь '{change_role_username}' не найден!", "error")

        # --- Изменить пароль ---
        change_password_username = request.form.get("change_password_username")
        new_password = request.form.get("new_password")
        if change_password_username and new_password:
            if len(new_password) < 8:
                flash("Пароль должен содержать минимум 8 символов!", "error")
            else:
                _pw_user = User.query.filter_by(username=change_password_username).first()
                if _pw_user:
                    _pw_user.set_password(new_password)
                    db.session.commit()
                    flash(f"Пароль пользователя '{change_password_username}' изменён!", "success")
                else:
                    flash(f"Пользователь '{change_password_username}' не найден!", "error")

        ip_action = request.form.get("ip_action")

        if ip_action == "add_ip":
            new_ip = request.form.get("new_ip", "").strip()
            if new_ip:
                if ip_restriction.add_ip(new_ip):
                    flash(f"IP {new_ip} добавлен", "success")
                else:
                    flash("Неверный формат IP", "error")

        elif ip_action == "remove_ip":
            ip_to_remove = request.form.get("ip_to_remove", "").strip()
            if ip_to_remove:
                if ip_restriction.remove_ip(ip_to_remove):
                    flash(f"IP {ip_to_remove} удален", "success")
                else:
                    flash("IP не найден", "error")

        elif ip_action == "clear_all_ips":
            ip_restriction.clear_all()
            flash("Все IP ограничения сброшены (доступ разрешен всем)", "success")

        elif ip_action == "enable_ips":
            ips_text = request.form.get("ips_text", "").strip()
            if ips_text:
                ip_restriction.clear_all()
                for ip in ips_text.split(","):
                    ip_restriction.add_ip(ip.strip())
                flash("IP ограничения включены", "success")
            else:
                flash("Укажите хотя бы один IP-адрес", "error")

        file_action = request.form.get("file_action")

        if file_action == "add_from_file":
            ip_file = request.form.get("ip_file", "").strip()
            if ip_file:
                try:
                    added_count = ip_manager.add_from_file(ip_file)
                    flash(f"Добавлено {added_count} IP из файла {ip_file}", "success")
                except FileNotFoundError:
                    flash("Файл не найден", "error")
                except Exception as e:
                    flash(f"Ошибка при добавлении IP: {e}", "error")
            else:
                flash("Выберите файл", "error")

        elif file_action in ("enable_file", "disable_file"):
            ip_file = request.form.get("ip_file", "").strip()
            if ip_file:
                try:
                    if file_action == "enable_file":
                        cnt = ip_manager.enable_file(ip_file)
                        flash(f"Добавлено {cnt} IP из файла {ip_file}", "success")
                    else:
                        cnt = ip_manager.disable_file(ip_file)
                        flash(f"Удалено {cnt} IP из файла {ip_file}", "success")
                except FileNotFoundError:
                    flash("Файл не найден", "error")
                except Exception as e:
                    flash(f"Ошибка при обработке файла: {e}", "error")
            else:
                flash("Не указан файл", "error")

        # ДОБАВЬТЕ ЭТО ВНУТРЬ POST БЛОКА:
        restart_action = request.form.get("restart_action")

        if restart_action == "restart_service":
            try:
                # Искусственная задержка 5 секунд для визуального эффекта
                time.sleep(5)

                # Выполняем команду перезапуска
                result = subprocess.run(
                    ["/opt/AdminAntizapret/script_sh/adminpanel.sh", "--restart"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    flash(
                        "✅ Служба успешно перезапущена! Изменения IP ограничений применены.",
                        "success",
                    )
                else:
                    flash(f"❌ Ошибка при перезапуске: {result.stderr[:100]}", "error")

            except subprocess.TimeoutExpired:
                flash("⏱️ Таймаут при перезапуске службы", "error")
            except Exception as e:
                flash(f"❌ Ошибка: {str(e)}", "error")

        return redirect(url_for("settings"))

    # GET запрос - отображение страницы
    current_port = os.getenv("APP_PORT", "5050")
    qr_download_token_ttl_seconds = os.getenv("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600")
    users = User.query.all()
    viewer_users = User.query.filter_by(role='viewer').all()

    # Собираем все конфиги для управления доступом viewer
    all_openvpn = collect_all_openvpn_files_for_access()
    openvpn_access_groups = build_openvpn_access_groups(all_openvpn)

    _orig_paths = config_file_handler.config_paths["openvpn"]
    try:
        config_file_handler.config_paths["openvpn"] = [d for g in GROUP_FOLDERS.values() for d in g]
        _, all_wg, all_amneziawg = config_file_handler.get_config_files()
    finally:
        config_file_handler.config_paths["openvpn"] = _orig_paths

    wg_access_groups = build_conf_access_groups(all_wg, "wg")
    amneziawg_access_groups = build_conf_access_groups(all_amneziawg, "amneziawg")

    # Карта доступа: {user_id: set(файлнаймы)}
    viewer_access = {vu.id: {acc.config_name for acc in vu.allowed_configs} for vu in viewer_users}

    # Добавляем данные об IP ограничениях
    allowed_ips = ip_restriction.get_allowed_ips()
    ip_enabled = ip_restriction.is_enabled()
    current_ip = ip_restriction.get_client_ip()

    # синхронизируем список адресов и получаем текущее состояние
    include_ips_set = ip_manager.sync_enabled()
    ip_files = ip_manager.list_ip_files()
    ip_file_states = ip_manager.get_file_states()
    return render_template(
        "settings.html",
        port=current_port,
        users=users,
        viewer_users=viewer_users,
        allowed_ips=allowed_ips,
        ip_enabled=ip_enabled,
        current_ip=current_ip,
        ip_files=ip_files,
        ip_file_states=ip_file_states,
        all_openvpn=all_openvpn,
        openvpn_access_groups=openvpn_access_groups,
        all_wg=all_wg,
        all_amneziawg=all_amneziawg,
        wg_access_groups=wg_access_groups,
        amneziawg_access_groups=amneziawg_access_groups,
        viewer_access=viewer_access,
        public_download_enabled=PUBLIC_DOWNLOAD_ENABLED,
        qr_download_token_ttl_seconds=qr_download_token_ttl_seconds,
    )


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


@app.route("/api/user-traffic-chart")
@auth_manager.login_required
def api_user_traffic_chart():
    client = (request.args.get("client") or "").strip()
    range_key = (request.args.get("range") or "7d").strip().lower()

    if not client:
        return jsonify({"error": "Параметр client обязателен"}), 400

    if range_key not in ("1h", "24h", "7d", "30d", "all"):
        range_key = "7d"

    now = datetime.utcnow()
    since_dt = None
    bucket = "day"

    if range_key == "1h":
        since_dt = now - timedelta(hours=1)
        bucket = "minute5"
    elif range_key == "24h":
        since_dt = now - timedelta(hours=24)
        bucket = "hour"
    elif range_key == "7d":
        since_dt = now - timedelta(days=7)
        bucket = "day"
    elif range_key == "30d":
        since_dt = now - timedelta(days=30)
        bucket = "day"
    else:
        bucket = "month"

    query = UserTrafficSample.query.filter_by(common_name=client)
    if since_dt is not None:
        query = query.filter(UserTrafficSample.created_at >= since_dt)

    samples = query.order_by(UserTrafficSample.created_at.asc()).all()

    grouped = defaultdict(lambda: {"vpn": 0, "antizapret": 0})

    for item in samples:
        dt = item.created_at
        if not dt:
            continue

        if bucket == "minute5":
            minute = (dt.minute // 5) * 5
            bucket_key = dt.strftime("%Y-%m-%d %H") + f":{minute:02d}"
            label = dt.strftime("%H") + f":{minute:02d}"
        elif bucket == "hour":
            bucket_key = dt.strftime("%Y-%m-%d %H")
            label = dt.strftime("%d.%m %H:00")
        elif bucket == "day":
            bucket_key = dt.strftime("%Y-%m-%d")
            label = dt.strftime("%d.%m")
        else:
            bucket_key = dt.strftime("%Y-%m")
            label = dt.strftime("%Y-%m")

        total_delta = int(item.delta_received or 0) + int(item.delta_sent or 0)
        net = "antizapret" if item.network_type == "antizapret" else "vpn"

        grouped[bucket_key]["label"] = label
        grouped[bucket_key][net] += total_delta

    ordered_keys = sorted(grouped.keys())
    labels = [grouped[key].get("label", key) for key in ordered_keys]
    vpn_bytes = [int(grouped[key].get("vpn", 0)) for key in ordered_keys]
    antizapret_bytes = [int(grouped[key].get("antizapret", 0)) for key in ordered_keys]

    total_vpn = sum(vpn_bytes)
    total_antizapret = sum(antizapret_bytes)

    return jsonify(
        {
            "client": client,
            "range": range_key,
            "bucket": bucket,
            "labels": labels,
            "vpn_bytes": vpn_bytes,
            "antizapret_bytes": antizapret_bytes,
            "total_vpn": total_vpn,
            "total_antizapret": total_antizapret,
            "total": total_vpn + total_antizapret,
            "total_vpn_human": _human_bytes(total_vpn),
            "total_antizapret_human": _human_bytes(total_antizapret),
            "total_human": _human_bytes(total_vpn + total_antizapret),
        }
    )


@app.route("/api/system-info")
@auth_manager.login_required
def api_system_info():
    """API для получения информации о системе"""
    try:
        cpu_usage = server_monitor_proc.get_cpu_usage()
        memory_usage = server_monitor_proc.get_memory_usage()
        disk_usage = server_monitor_proc.get_disk_usage()
        load_avg = server_monitor_proc.get_load_average()
        system_info = server_monitor_proc.get_system_info()
        uptime = server_monitor_proc.get_uptime()

        return jsonify({
            "cpu": {
                "usage": cpu_usage,
                "color": server_monitor_proc.get_status_color(cpu_usage),
            },
            "memory": {
                "usage": memory_usage,
                "color": server_monitor_proc.get_status_color(memory_usage),
            },
            "disk": {
                "usage_percent": disk_usage.get("percent", 0),
                "used_gb": round(disk_usage.get("used", 0) / (1024**3), 2),
                "total_gb": round(disk_usage.get("total", 0) / (1024**3), 2),
                "color": server_monitor_proc.get_status_color(disk_usage.get("percent", 0)),
            },
            "load_average": load_avg,
            "system_info": system_info,
            "uptime": uptime,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        app.logger.error(f"Ошибка при получении информации о системе: {e}")
        return jsonify({"error": "Ошибка при получении информации о системе"}), 500


@sock.route("/ws/monitor")
def monitor_websocket(ws):
    """WebSocket для реал-тайм мониторинга сервера"""
    try:
        # Проверить авторизацию
        if 'username' not in session:
            ws.close(code=1008, message="Unauthorized")
            return

        # Отправлять обновления каждые 2 секунды
        import json
        while True:
            time.sleep(2)
            try:
                cpu_usage = server_monitor_proc.get_cpu_usage()
                memory_usage = server_monitor_proc.get_memory_usage()

                message = json.dumps({
                    'type': 'monitor_update',
                    'cpu': round(cpu_usage, 1),
                    'memory': round(memory_usage, 1),
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                })
                ws.send(message)
            except Exception as e:
                app.logger.error(f"Ошибка при отправке WebSocket сообщения: {e}")
                break
    except Exception as e:
        app.logger.error(f"Ошибка WebSocket подключения: {e}")
        try:
            ws.close()
        except:
            pass


@app.route("/check_updates", methods=["GET"])
@auth_manager.admin_required
def check_updates():
    try:
        result = subprocess.run(
            """
            cd /opt/AdminAntizapret &&
            git fetch origin main --quiet &&
            LOCAL=$(git rev-parse HEAD) &&
            REMOTE=$(git rev-parse origin/main) &&
            if [ "$LOCAL" = "$REMOTE" ]; then
                echo "up_to_date"
            else
                echo "update_available"
            fi
            """,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
        )

        status = result.stdout.strip()
        if status == "update_available":
            return {"update_available": True, "message": "Доступно обновление!"}, 200
        else:
            return {"update_available": False, "message": "У вас последняя версия"}, 200

    except:
        return {
            "update_available": False,
            "message": "Не удалось проверить обновления",
        }, 200


@app.route("/update_system", methods=["POST"])
@auth_manager.admin_required
def update_system():
    try:
        subprocess.run(
            """
            cd /opt/AdminAntizapret &&
            git fetch origin main --quiet &&
            git reset --hard origin/main --quiet &&
            git clean -fd --quiet &&
            /opt/AdminAntizapret/venv/bin/pip install -q -r requirements.txt > /dev/null 2>&1 &&
            systemctl restart admin-antizapret.service > /dev/null 2>&1 || true
            """,
            shell=True,
            timeout=600,
            check=False,
        )
        return {"success": True, "message": "Панель успешно обновлена!"}, 200
    except Exception as e:
        return {
            "success": True,
            "message": "Панель обновлена (перезагрузите страницу)",
        }, 200


@app.before_request
def check_ip_access():
    """Проверяет доступ по IP"""
    # Разрешаем доступ к статическим файлам всегда
    if request.endpoint == "static":
        return

    # Если ограничения выключены - разрешаем все
    if not ip_restriction.is_enabled():
        return

    client_ip = ip_restriction.get_client_ip()

    # Проверяем IP для всех остальных страниц
    if not ip_restriction.is_ip_allowed(client_ip):
        # Разрешаем доступ к самой странице блокировки
        if request.endpoint == "ip_blocked":
            return

        # Для API запросов возвращаем JSON ошибку
        if request.is_json:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Доступ запрещен с вашего IP-адреса: {client_ip}",
                    }
                ),
                403,
            )

        # Для всех остальных запросов перенаправляем на страницу блокировки
        return redirect(url_for("ip_blocked"))


@app.route("/ip-blocked")
def ip_blocked():
    """Страница блокировки по IP"""
    client_ip = ip_restriction.get_client_ip()
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    request_path = request.headers.get("Referer", request.path)

    return render_template(
        "ip_blocked.html",
        client_ip=client_ip,
        current_time=current_time,
        request_path=request_path,
        app_name="AdminAntizapret",
    )


@app.route("/api/restart-service", methods=["POST"])
@auth_manager.admin_required
def api_restart_service():
    """API для перезапуска службы"""
    try:
        # Выполняем команду перезапуска
        result = subprocess.run(
            ["/opt/AdminAntizapret/script_sh/adminpanel.sh", "--restart"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return jsonify(
                {
                    "success": True,
                    "message": "✅ Служба успешно перезапущена",
                    "output": result.stdout,
                }
            )
        else:
            app.logger.error(f"Ошибка перезапуска: {result.stderr}")
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "❌ Ошибка при перезапуске службы",
                        "output": result.stderr,
                    }
                ),
                500,
            )

    except subprocess.TimeoutExpired:
        app.logger.error("Таймаут при перезапуске службы")
        return (
            jsonify({"success": False, "message": "⏱️ Таймаут при перезапуске службы"}),
            500,
        )
    except Exception as e:
        app.logger.error(f"Ошибка: {str(e)}")
        return jsonify({"success": False, "message": f"❌ Ошибка: {str(e)}"}), 500


@app.route("/api/viewer-access", methods=["POST"])
@auth_manager.admin_required
def api_viewer_access():
    """API управления доступом viewer к конфигам."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверный запрос'}), 400

    user_id = data.get('user_id')
    config_name = data.get('config_name')
    config_type = data.get('config_type')
    action = data.get('action')

    if not all([user_id, config_name, config_type, action]):
        return jsonify({'success': False, 'message': 'Неверные параметры'}), 400

    target_user = db.session.get(User, user_id)
    if not target_user or target_user.role != 'viewer':
        return jsonify({'success': False, 'message': 'Пользователь не найден или не является viewer'}), 404

    target_config_names = [config_name]
    if config_type in ('openvpn', 'wg', 'amneziawg'):
        all_configs = collect_all_configs_for_access(config_type)
        grouped_names = {
            os.path.basename(path)
            for path in all_configs
            if (
                normalize_openvpn_group_key(os.path.basename(path)) == config_name
                if config_type == 'openvpn'
                else normalize_conf_group_key(os.path.basename(path), config_type) == config_name
            )
        }
        if grouped_names:
            target_config_names = sorted(grouped_names, key=str.lower)

    if action == 'grant':
        existing_names = {
            row.config_name
            for row in ViewerConfigAccess.query.filter(
                ViewerConfigAccess.user_id == user_id,
                ViewerConfigAccess.config_name.in_(target_config_names),
            ).all()
        }
        for target_name in target_config_names:
            if target_name in existing_names:
                continue
            access = ViewerConfigAccess(
                user_id=user_id, config_type=config_type, config_name=target_name
            )
            db.session.add(access)
        db.session.commit()
    elif action == 'revoke':
        ViewerConfigAccess.query.filter(
            ViewerConfigAccess.user_id == user_id,
            ViewerConfigAccess.config_name.in_(target_config_names),
        ).delete(synchronize_session=False)
        db.session.commit()
    else:
        return jsonify({'success': False, 'message': 'Неверное действие'}), 400

    return jsonify({'success': True})
