from flask import (
    Flask,
    render_template,
    render_template_string,
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
import json
import glob
import socket
import sys
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
from sqlalchemy import case
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import time
import platform
from sqlalchemy.exc import IntegrityError
from concurrent.futures import ThreadPoolExecutor

#Импорт файла с параметрами
from utils.ip_restriction import ip_restriction
from config.antizapret_params import ANTIZAPRET_PARAMS
from ips import ip_manager
from routes.settings_antizapret import init_antizapret

# Абсолютный путь к корню приложения и .env (не зависит от рабочего каталога процесса).
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_FILE_PATH = os.path.join(APP_ROOT, ".env")

# Загрузка переменных окружения из .env файла
load_dotenv(dotenv_path=ENV_FILE_PATH)

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

try:
    BACKGROUND_TASK_WORKERS = max(1, int(os.getenv("BACKGROUND_TASK_WORKERS", "2")))
except (TypeError, ValueError):
    BACKGROUND_TASK_WORKERS = 2

BACKGROUND_TASK_MAX_OUTPUT_CHARS = 12000
background_task_executor = ThreadPoolExecutor(
    max_workers=BACKGROUND_TASK_WORKERS,
    thread_name_prefix="adminantizapret-task",
)


def _set_env_value(key, value):
    """Update or append env key in local .env file."""
    env_path = ENV_FILE_PATH
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


def _get_env_value(key, default=""):
    """Reads env value from .env first, then from process env as fallback."""
    env_path = ENV_FILE_PATH
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip()
    return os.getenv(key, default)


def _to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_valid_cron_expression(expr):
    value = (expr or "").strip()
    parts = value.split()
    if len(parts) != 5:
        return False
    token_pattern = re.compile(r"^[0-9*/,\-]+$")
    return all(token_pattern.fullmatch(part or "") for part in parts)

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
    max_downloads = db.Column(db.Integer, nullable=False, default=1)
    download_count = db.Column(db.Integer, nullable=False, default=0)
    pin_hash = db.Column(db.String(64), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True, index=True)


class QrDownloadAuditLog(db.Model):
    """Журнал событий для одноразовых QR-ссылок."""
    __tablename__ = 'qr_download_audit_log'

    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.Integer, db.ForeignKey('qr_download_token.id'), nullable=True, index=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    actor_username = db.Column(db.String(80), nullable=True, index=True)
    remote_addr = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    details = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


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


class UserTrafficStatProtocol(db.Model):
    """Накопленный трафик по пользователю с разделением по протоколу."""
    __tablename__ = 'user_traffic_stat_protocol'

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(255), nullable=False, index=True)
    protocol_type = db.Column(db.String(20), nullable=False, default='openvpn', index=True)
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

    __table_args__ = (
        db.UniqueConstraint('common_name', 'protocol_type', name='uq_user_traffic_stat_protocol_name_type'),
    )


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
    protocol_type = db.Column(db.String(20), nullable=False, default='openvpn', index=True)  # openvpn | wireguard
    delta_received = db.Column(db.BigInteger, nullable=False, default=0)
    delta_sent = db.Column(db.BigInteger, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class OpenVPNPeerInfoCache(db.Model):
    """Кэш последней версии/платформы OpenVPN-клиента для быстрого отображения из БД."""
    __tablename__ = 'openvpn_peer_info_cache'

    id = db.Column(db.Integer, primary_key=True)
    profile = db.Column(db.String(64), nullable=False, index=True)
    client_name = db.Column(db.String(255), nullable=False, index=True)
    ip = db.Column(db.String(64), nullable=False, index=True)
    endpoint = db.Column(db.String(255), nullable=True)
    version = db.Column(db.String(128), nullable=True)
    platform = db.Column(db.String(64), nullable=True)
    last_event_rank = db.Column(db.BigInteger, nullable=False, default=0, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('profile', 'client_name', 'ip', name='uq_openvpn_peer_info_profile_client_ip'),
    )


class OpenVPNPeerInfoHistory(db.Model):
    """История версии/платформы OpenVPN-клиента для fallback за последние дни."""
    __tablename__ = 'openvpn_peer_info_history'

    id = db.Column(db.Integer, primary_key=True)
    profile = db.Column(db.String(64), nullable=False, index=True)
    client_name = db.Column(db.String(255), nullable=False, index=True)
    ip = db.Column(db.String(64), nullable=False, index=True)
    endpoint = db.Column(db.String(255), nullable=True)
    version = db.Column(db.String(128), nullable=True)
    platform = db.Column(db.String(64), nullable=True)
    event_rank = db.Column(db.BigInteger, nullable=False, default=0, index=True)
    observed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint('profile', 'client_name', 'ip', 'event_rank', name='uq_openvpn_peer_info_history_event'),
    )


class WireGuardPeerCache(db.Model):
    """Кэш соответствия WireGuard peer public key -> имя клиента (из /etc/wireguard/*.conf)."""
    __tablename__ = 'wireguard_peer_cache'

    id = db.Column(db.Integer, primary_key=True)
    interface_name = db.Column(db.String(32), nullable=False, index=True)
    peer_public_key = db.Column(db.String(128), nullable=False, index=True)
    client_name = db.Column(db.String(255), nullable=False, index=True)
    allowed_ips = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('interface_name', 'peer_public_key', name='uq_wireguard_peer_iface_key'),
    )


class ActiveWebSession(db.Model):
    """Активные веб-сессии для безопасного ночного рестарта."""
    __tablename__ = 'active_web_session'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), nullable=False, index=True)
    remote_addr = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class BackgroundTask(db.Model):
    """Состояние фоновой административной задачи."""
    __tablename__ = 'background_task'

    id = db.Column(db.String(32), primary_key=True)
    task_type = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    created_by_username = db.Column(db.String(80), nullable=True, index=True)
    message = db.Column(db.String(255), nullable=True)
    output = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)


class LogsDashboardCache(db.Model):
    """Кэш последнего снимка logs_dashboard для быстрой отдачи из БД."""
    __tablename__ = 'logs_dashboard_cache'

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(32), unique=True, nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_error = db.Column(db.String(255), nullable=True)


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


def _collect_bw_interface_groups():
    """Collect available interfaces for BW charts and map them to vpn/antizapret groups."""
    default_groups = {
        "vpn": ["vpn", "vpn-udp", "vpn-tcp"],
        "antizapret": ["antizapret", "antizapret-udp", "antizapret-tcp"],
    }
    default_protocol_groups = {
        "openvpn": ["vpn-udp", "vpn-tcp", "antizapret-udp", "antizapret-tcp"],
        "wireguard": ["vpn", "antizapret"],
    }

    candidates = set()
    for values in default_groups.values():
        candidates.update(values)

    vnstat_bin = os.environ.get("VNSTAT_BIN", "/usr/bin/vnstat")
    try:
        vn_json = subprocess.run(
            [vnstat_bin, "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=4,
        )
        parsed = json.loads(vn_json.stdout or "{}")
        for item in parsed.get("interfaces") or []:
            name = str(item.get("name") or "").strip()
            if name:
                candidates.add(name)
    except Exception:
        pass

    wg_interfaces = set()
    try:
        wg_out = subprocess.run(
            ["wg", "show", "interfaces"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        for token in re.split(r"\s+", (wg_out.stdout or "").strip()):
            name = token.strip()
            if name:
                wg_interfaces.add(name)
                candidates.add(name)
    except Exception:
        pass

    try:
        ip_out = subprocess.run(
            ["ip", "-o", "link", "show", "type", "wireguard"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in (ip_out.stdout or "").splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                name = parts[1].strip()
                if name:
                    wg_interfaces.add(name)
                    candidates.add(name)
    except Exception:
        pass

    vpn_group = []
    antizapret_group = []
    openvpn_group = []
    wireguard_group = []

    def _add_unique(target, value):
        if value and value not in target:
            target.append(value)

    for iface in sorted(candidates):
        lowered = iface.lower()
        if not any(k in lowered for k in ("vpn", "wg", "wireguard", "awg", "amnezia", "antizapret")):
            continue

        is_wireguard_iface = iface in wg_interfaces or any(
            k in lowered for k in ("wg", "wireguard", "awg", "amnezia")
        )

        if "antizapret" in lowered:
            _add_unique(antizapret_group, iface)
        else:
            _add_unique(vpn_group, iface)

        if is_wireguard_iface:
            _add_unique(wireguard_group, iface)
        else:
            _add_unique(openvpn_group, iface)

    for fallback_iface in default_groups["vpn"]:
        _add_unique(vpn_group, fallback_iface)
    for fallback_iface in default_groups["antizapret"]:
        _add_unique(antizapret_group, fallback_iface)

    for fallback_iface in default_protocol_groups["openvpn"]:
        _add_unique(openvpn_group, fallback_iface)

    for fallback_iface in default_protocol_groups["wireguard"]:
        _add_unique(wireguard_group, fallback_iface)

    return {
        "vpn": vpn_group,
        "antizapret": antizapret_group,
        "openvpn": openvpn_group,
        "wireguard": wireguard_group,
    }


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

    ttl_seconds = int(_get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600"))
    # Защита от слишком маленького/большого значения из окружения.
    ttl_seconds = max(60, min(ttl_seconds, 3600))

    max_downloads = int(_get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1"))
    if max_downloads not in (1, 3, 5):
        max_downloads = 1

    pin_raw = (_get_env_value("QR_DOWNLOAD_PIN", "") or "").strip()
    pin_hash = hashlib.sha256(pin_raw.encode("utf-8")).hexdigest() if pin_raw else None

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
        max_downloads=max_downloads,
        pin_hash=pin_hash,
    )
    db.session.add(token_row)
    db.session.flush()

    # Периодическая чистка старых токенов.
    stale_threshold = now - timedelta(days=1)
    db.session.query(QrDownloadToken).filter(
        (QrDownloadToken.expires_at < stale_threshold)
        | (
            (QrDownloadToken.used_at.isnot(None))
            & (QrDownloadToken.used_at < stale_threshold)
            & (QrDownloadToken.download_count >= QrDownloadToken.max_downloads)
        )
    ).delete(synchronize_session=False)

    remote_addr = ((request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",", 1)[0]).strip()
    user_agent = (request.headers.get("User-Agent") or "")[:255]
    db.session.add(
        QrDownloadAuditLog(
            token_id=token_row.id,
            event_type="generated",
            actor_user_id=creator_id,
            actor_username=username,
            remote_addr=remote_addr,
            user_agent=user_agent,
            details=f"cfg={config_type}/{os.path.basename(file_path)} ttl={ttl_seconds}s max={max_downloads} pin={'y' if pin_hash else 'n'}",
        )
    )

    db.session.commit()
    return url_for("one_time_qr_download", token=token, _external=True)


def _log_qr_event(event_type, token_row=None, details=None):
    """Пишет событие в журнал QR-ссылок без влияния на основной сценарий."""
    try:
        username = session.get("username")
        actor_user_id = None
        if username:
            actor = User.query.filter_by(username=username).first()
            if actor:
                actor_user_id = actor.id

        remote_addr = ((request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",", 1)[0]).strip()
        user_agent = (request.headers.get("User-Agent") or "")[:255]

        db.session.add(
            QrDownloadAuditLog(
                token_id=token_row.id if token_row else None,
                event_type=event_type,
                actor_user_id=actor_user_id,
                actor_username=username,
                remote_addr=remote_addr,
                user_agent=user_agent,
                details=(details or "")[:255],
            )
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Не удалось записать событие QR-журнала: {e}")


def _trim_background_task_text(value):
    text = (value or "").strip()
    if len(text) <= BACKGROUND_TASK_MAX_OUTPUT_CHARS:
        return text
    return text[:BACKGROUND_TASK_MAX_OUTPUT_CHARS] + "\n...[truncated]"


def _serialize_background_task(task):
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "message": task.message,
        "output": task.output,
        "error": task.error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def _update_background_task(task_id, **fields):
    with app.app_context():
        task = db.session.get(BackgroundTask, task_id)
        if not task:
            return

        for key, value in fields.items():
            setattr(task, key, value)

        db.session.commit()


def _run_background_task(task_id, task_callable):
    _update_background_task(
        task_id,
        status="running",
        started_at=datetime.utcnow(),
        message="Задача выполняется",
    )

    try:
        with app.app_context():
            result = task_callable() or {}
        _update_background_task(
            task_id,
            status="completed",
            finished_at=datetime.utcnow(),
            message=(result.get("message") or "Задача выполнена")[:255],
            output=_trim_background_task_text(result.get("output", "")),
            error=None,
        )
    except Exception as e:
        app.logger.exception(f"Ошибка фоновой задачи {task_id}: {e}")
        try:
            with app.app_context():
                db.session.rollback()
        except Exception:
            pass
        _update_background_task(
            task_id,
            status="failed",
            finished_at=datetime.utcnow(),
            message="Задача завершилась с ошибкой",
            error=_trim_background_task_text(str(e)),
        )


def _enqueue_background_task(task_type, task_callable, created_by_username=None, queued_message=None):
    task = BackgroundTask(
        id=secrets.token_hex(16),
        task_type=task_type,
        status="queued",
        created_by_username=created_by_username,
        message=(queued_message or "Задача поставлена в очередь")[:255],
    )
    db.session.add(task)
    db.session.commit()

    background_task_executor.submit(_run_background_task, task.id, task_callable)
    return task


def _task_accepted_response(task, message):
    payload = _serialize_background_task(task)
    payload.update(
        {
            "success": True,
            "queued": True,
            "message": message,
            "status_url": url_for("api_task_status", task_id=task.id),
        }
    )
    return jsonify(payload), 202


def _run_checked_command(args, cwd=None, timeout=120):
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(f"Команда {' '.join(args)} завершилась с кодом {result.returncode}. {stderr or stdout}")
    return stdout, stderr


def _task_run_doall():
    stdout, stderr = _run_checked_command(["/root/antizapret/doall.sh"], timeout=900)
    try:
        _sync_wireguard_peer_cache_from_configs(force=True)
    except Exception as e:
        db.session.rollback()
        app.logger.warning("Не удалось синхронизировать wireguard_peer_cache после doall: %s", e)
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()
    return {
        "message": "Скрипт doall выполнен успешно",
        "output": combined,
    }


def _task_restart_service():
    stdout, stderr = _run_checked_command(
        ["/opt/AdminAntizapret/script_sh/adminpanel.sh", "--restart"],
        timeout=120,
    )
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()
    return {
        "message": "Служба успешно перезапущена",
        "output": combined,
    }


def _task_update_system():
    output_parts = []
    repo_dir = APP_ROOT
    pip_path = os.path.join(APP_ROOT, "venv", "bin", "pip")
    if not os.path.exists(pip_path):
        pip_path = "pip3"

    commands = [
        (["git", "fetch", "origin", "main", "--quiet"], 90),
        (["git", "reset", "--hard", "origin/main", "--quiet"], 90),
        (["git", "clean", "-fd", "--quiet"], 90),
        ([pip_path, "install", "-q", "-r", "requirements.txt"], 300),
    ]

    for cmd, timeout in commands:
        stdout, stderr = _run_checked_command(cmd, cwd=repo_dir, timeout=timeout)
        output_parts.extend([part for part in [stdout, stderr] if part])

    return {
        "message": "Обновление завершено. Выполните перезапуск службы отдельно.",
        "output": "\n".join(output_parts).strip(),
    }


def _logs_dashboard_cache_row():
    return LogsDashboardCache.query.filter_by(cache_key="main").first()


def _save_logs_dashboard_cache_payload(payload, last_error=None):
    row = _logs_dashboard_cache_row()
    if row is None:
        row = LogsDashboardCache(cache_key="main")

    row.payload_json = json.dumps(payload, ensure_ascii=False)
    row.generated_at = datetime.utcnow()
    row.last_error = (last_error or "").strip()[:255] or None
    db.session.add(row)
    db.session.commit()
    return row


def _load_logs_dashboard_cache_payload():
    row = _logs_dashboard_cache_row()
    if row is None or not row.payload_json:
        return None, row

    try:
        payload = json.loads(row.payload_json)
    except Exception:
        return None, row

    if not isinstance(payload, dict):
        return None, row

    return payload, row


def _build_empty_logs_dashboard_payload(reason_message=None):
    reason = (reason_message or "Данные временно недоступны").strip()
    return {
        "status_rows": [],
        "event_rows": [],
        "grouped_status_rows": [
            {
                "network": "Antizapret",
                "files": "-",
                "snapshot_times": "-",
                "updated_at": "-",
                "client_count": 0,
                "unique_real_ips": 0,
                "transport_split": "TCP: 0, UDP: 0",
                "total_received": 0,
                "total_sent": 0,
                "total_traffic": 0,
                "total_received_human": _human_bytes(0),
                "total_sent_human": _human_bytes(0),
                "total_traffic_human": _human_bytes(0),
            },
            {
                "network": "VPN",
                "files": "-",
                "snapshot_times": "-",
                "updated_at": "-",
                "client_count": 0,
                "unique_real_ips": 0,
                "transport_split": "TCP: 0, UDP: 0",
                "total_received": 0,
                "total_sent": 0,
                "total_traffic": 0,
                "total_received_human": _human_bytes(0),
                "total_sent_human": _human_bytes(0),
                "total_traffic_human": _human_bytes(0),
            },
        ],
        "grouped_event_rows": [],
        "openvpn_logging_enabled": False,
        "missing_event_log_files": [reason],
        "summary": {
            "total_active_clients": 0,
            "unique_client_names": 0,
            "unique_ips": 0,
            "total_received": 0,
            "total_sent": 0,
            "total_received_human": _human_bytes(0),
            "total_sent_human": _human_bytes(0),
            "total_traffic_human": _human_bytes(0),
            "total_event_lines": 0,
            "total_event_counts": {},
        },
        "connected_clients": [],
        "persisted_traffic_rows": [],
        "deleted_persisted_traffic_rows": [],
        "persisted_traffic_summary": {
            "users_count": 0,
            "active_users_count": 0,
            "offline_users_count": 0,
            "total_received_human": _human_bytes(0),
            "total_sent_human": _human_bytes(0),
            "total_traffic_human": _human_bytes(0),
            "latest_sample_at": "-",
            "latest_stat_seen_at": "-",
            "db_age_seconds": None,
            "db_age_human": "-",
            "db_is_stale": False,
        },
        "deleted_persisted_traffic_summary": {
            "users_count": 0,
            "total_bytes": 0,
            "total_bytes_human": _human_bytes(0),
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _is_logs_dashboard_refresh_in_progress():
    return _get_logs_dashboard_refresh_task() is not None


def _get_logs_dashboard_refresh_task():
    return (
        BackgroundTask.query.filter(
            BackgroundTask.task_type == "logs_dashboard_refresh",
            BackgroundTask.status.in_(["queued", "running"]),
        )
        .order_by(BackgroundTask.created_at.desc())
        .first()
    )


def _task_refresh_logs_dashboard_cache():
    try:
        payload = _collect_logs_dashboard_data()
        _save_logs_dashboard_cache_payload(payload, last_error=None)
        return {
            "message": "Кэш dashboard обновлен",
            "output": f"generated_at={payload.get('generated_at', '-')}",
        }
    except Exception as exc:
        db.session.rollback()
        row = _logs_dashboard_cache_row()
        if row is not None:
            row.last_error = str(exc)[:255]
            db.session.commit()
        raise


def _queue_logs_dashboard_refresh_if_needed(created_by_username=None):
    existing_task = _get_logs_dashboard_refresh_task()
    if existing_task is not None:
        return False

    _enqueue_background_task(
        "logs_dashboard_refresh",
        _task_refresh_logs_dashboard_cache,
        created_by_username=created_by_username,
        queued_message="Обновление кэша dashboard поставлено в очередь",
    )
    return True


def _get_logs_dashboard_data_cached(created_by_username=None):
    payload, row = _load_logs_dashboard_cache_payload()
    now = datetime.utcnow()

    if payload is not None and row is not None and row.generated_at is not None:
        age_seconds = max(int((now - row.generated_at).total_seconds()), 0)
        is_stale = age_seconds > LOGS_DASHBOARD_CACHE_TTL_SECONDS
        refresh_task = _get_logs_dashboard_refresh_task()

        if is_stale:
            if refresh_task is None:
                _queue_logs_dashboard_refresh_if_needed(created_by_username=created_by_username)
                refresh_task = _get_logs_dashboard_refresh_task()

        payload["cache_meta"] = {
            "from_cache": True,
            "is_stale": is_stale,
            "age_seconds": age_seconds,
            "refresh_in_progress": refresh_task is not None,
            "refresh_task_id": refresh_task.id if refresh_task is not None else None,
            "ttl_seconds": LOGS_DASHBOARD_CACHE_TTL_SECONDS,
            "last_error": (row.last_error or "").strip() or None,
        }
        return payload

    try:
        fresh_payload = _collect_logs_dashboard_data()
        _save_logs_dashboard_cache_payload(fresh_payload, last_error=None)
        fresh_payload["cache_meta"] = {
            "from_cache": False,
            "is_stale": False,
            "age_seconds": 0,
            "refresh_in_progress": False,
            "refresh_task_id": None,
            "ttl_seconds": LOGS_DASHBOARD_CACHE_TTL_SECONDS,
            "last_error": None,
        }
        return fresh_payload
    except Exception as exc:
        db.session.rollback()
        _queue_logs_dashboard_refresh_if_needed(created_by_username=created_by_username)
        refresh_task = _get_logs_dashboard_refresh_task()
        fallback_payload = _build_empty_logs_dashboard_payload(str(exc))
        fallback_payload["cache_meta"] = {
            "from_cache": False,
            "is_stale": True,
            "age_seconds": None,
            "refresh_in_progress": refresh_task is not None,
            "refresh_task_id": refresh_task.id if refresh_task is not None else None,
            "ttl_seconds": LOGS_DASHBOARD_CACHE_TTL_SECONDS,
            "last_error": str(exc),
        }
        return fallback_payload


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

            if insp.has_table('user_traffic_sample'):
                sample_cols = {c['name'] for c in insp.get_columns('user_traffic_sample')}
                sample_missing = {
                    'protocol_type': "ALTER TABLE user_traffic_sample ADD COLUMN protocol_type VARCHAR(20) NOT NULL DEFAULT 'openvpn'",
                }
                with db.engine.connect() as conn:
                    for col_name, alter_sql in sample_missing.items():
                        if col_name not in sample_cols:
                            conn.execute(text(alter_sql))
                    conn.commit()

            if insp.has_table('qr_download_token'):
                qr_cols = {c['name'] for c in insp.get_columns('qr_download_token')}
                qr_missing = {
                    'max_downloads': "ALTER TABLE qr_download_token ADD COLUMN max_downloads INTEGER NOT NULL DEFAULT 1",
                    'download_count': "ALTER TABLE qr_download_token ADD COLUMN download_count INTEGER NOT NULL DEFAULT 0",
                    'pin_hash': "ALTER TABLE qr_download_token ADD COLUMN pin_hash VARCHAR(64)",
                }
                with db.engine.connect() as conn:
                    for col_name, alter_sql in qr_missing.items():
                        if col_name not in qr_cols:
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
OPENVPN_SOCKET_DIR = _get_env_value("OPENVPN_SOCKET_DIR", "/run/openvpn-server")
OPENVPN_SOCKET_TIMEOUT = 2.5
OPENVPN_SOCKET_IDLE_TIMEOUT = 0.12
try:
    OPENVPN_LOG_TAIL_LINES = int(_get_env_value("OPENVPN_LOG_TAIL_LINES", "2000"))
except (TypeError, ValueError):
    OPENVPN_LOG_TAIL_LINES = 2000
if OPENVPN_LOG_TAIL_LINES < 0:
    OPENVPN_LOG_TAIL_LINES = 0

try:
    OPENVPN_EVENT_MAX_RESPONSE_BYTES = int(
        _get_env_value("OPENVPN_EVENT_MAX_RESPONSE_BYTES", "1048576")
    )
except (TypeError, ValueError):
    OPENVPN_EVENT_MAX_RESPONSE_BYTES = 1048576
if OPENVPN_EVENT_MAX_RESPONSE_BYTES < 0:
    OPENVPN_EVENT_MAX_RESPONSE_BYTES = 0

try:
    OPENVPN_PEER_INFO_CACHE_TTL_SECONDS = int(_get_env_value("OPENVPN_PEER_INFO_CACHE_TTL_SECONDS", "604800"))
except (TypeError, ValueError):
    OPENVPN_PEER_INFO_CACHE_TTL_SECONDS = 604800
if OPENVPN_PEER_INFO_CACHE_TTL_SECONDS < 0:
    OPENVPN_PEER_INFO_CACHE_TTL_SECONDS = 0

try:
    OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS = int(
        _get_env_value("OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS", "604800")
    )
except (TypeError, ValueError):
    OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS = 604800
if OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS < 0:
    OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS = 0

try:
    TRAFFIC_DB_STALE_SECONDS = int(_get_env_value("TRAFFIC_DB_STALE_SECONDS", "600"))
except (TypeError, ValueError):
    TRAFFIC_DB_STALE_SECONDS = 600
if TRAFFIC_DB_STALE_SECONDS < 0:
    TRAFFIC_DB_STALE_SECONDS = 0

TRAFFIC_SYNC_CRON_MARKER = "# adminantizapret-traffic-sync"
TRAFFIC_SYNC_CRON_EXPR = (_get_env_value("TRAFFIC_SYNC_CRON", "*/1 * * * *") or "*/1 * * * *").strip()
TRAFFIC_SYNC_ENABLED = _get_env_value("TRAFFIC_SYNC_ENABLED", "true").strip().lower() == "true"

NIGHTLY_IDLE_RESTART_MARKER = "# adminantizapret-nightly-idle-restart"
NIGHTLY_IDLE_RESTART_CRON_EXPR = (
    _get_env_value("NIGHTLY_IDLE_RESTART_CRON", "0 4 * * *") or "0 4 * * *"
).strip()
NIGHTLY_IDLE_RESTART_ENABLED = (
    _get_env_value("NIGHTLY_IDLE_RESTART_ENABLED", "true").strip().lower() == "true"
)

try:
    ACTIVE_WEB_SESSION_TTL_SECONDS = int(
        _get_env_value("ACTIVE_WEB_SESSION_TTL_SECONDS", "180")
    )
except (TypeError, ValueError):
    ACTIVE_WEB_SESSION_TTL_SECONDS = 180
if ACTIVE_WEB_SESSION_TTL_SECONDS < 30:
    ACTIVE_WEB_SESSION_TTL_SECONDS = 30

try:
    ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS = int(
        _get_env_value("ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", "30")
    )
except (TypeError, ValueError):
    ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS = 30
if ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS < 1:
    ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS = 1

try:
    LOGS_DASHBOARD_CACHE_TTL_SECONDS = int(
        _get_env_value("LOGS_DASHBOARD_CACHE_TTL_SECONDS", "45")
    )
except (TypeError, ValueError):
    LOGS_DASHBOARD_CACHE_TTL_SECONDS = 45
if LOGS_DASHBOARD_CACHE_TTL_SECONDS < 5:
    LOGS_DASHBOARD_CACHE_TTL_SECONDS = 5

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

WIREGUARD_CONFIG_FILES = {
    "antizapret": "/etc/wireguard/antizapret.conf",
    "vpn": "/etc/wireguard/vpn.conf",
}

try:
    WIREGUARD_ACTIVE_HANDSHAKE_SECONDS = int(
        _get_env_value("WIREGUARD_ACTIVE_HANDSHAKE_SECONDS", "180")
    )
except (TypeError, ValueError):
    WIREGUARD_ACTIVE_HANDSHAKE_SECONDS = 180
if WIREGUARD_ACTIVE_HANDSHAKE_SECONDS < 0:
    WIREGUARD_ACTIVE_HANDSHAKE_SECONDS = 0

try:
    WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS = int(
        _get_env_value("WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS", "300")
    )
except (TypeError, ValueError):
    WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS = 300
if WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS < 0:
    WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS = 0

_wireguard_peer_cache_last_sync_ts = 0

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


def _traffic_sync_command():
    python_bin = shlex.quote(sys.executable or "python3")
    script_path = shlex.quote(os.path.join(APP_ROOT, "utils", "traffic_sync.py"))
    return f"{python_bin} {script_path} >/dev/null 2>&1"


def _nightly_idle_restart_command():
    python_bin = shlex.quote(sys.executable or "python3")
    script_path = shlex.quote(os.path.join(APP_ROOT, "utils", "nightly_idle_restart.py"))
    return f"{python_bin} {script_path} >/dev/null 2>&1"


def _is_systemd_traffic_sync_timer_enabled():
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", "admin-antizapret-traffic-sync.timer"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def _ensure_traffic_sync_cron():
    lines = _read_crontab_lines()
    if lines is None:
        return False, "Не удалось прочитать crontab для авто-синхронизации трафика."

    lines = [line for line in lines if TRAFFIC_SYNC_CRON_MARKER not in line]

    # Если installer уже включил systemd timer sync, не дублируем cron-задачу.
    if _is_systemd_traffic_sync_timer_enabled():
        try:
            _write_crontab_lines(lines)
        except Exception as e:
            return False, f"Ошибка очистки cron sync при активном timer: {e}"
        return True, "Systemd timer sync активен, cron sync не требуется"

    if TRAFFIC_SYNC_ENABLED:
        command = _traffic_sync_command()
        lines.append(f"{TRAFFIC_SYNC_CRON_EXPR} {command} {TRAFFIC_SYNC_CRON_MARKER}")

    try:
        _write_crontab_lines(lines)
    except Exception as e:
        return False, f"Ошибка записи cron sync: {e}"

    if TRAFFIC_SYNC_ENABLED:
        return True, "Cron sync трафика включен"
    return True, "Cron sync трафика отключен"


def _ensure_nightly_idle_restart_cron():
    lines = _read_crontab_lines()
    if lines is None:
        return False, "Не удалось прочитать crontab для ночного рестарта сайта."

    if NIGHTLY_IDLE_RESTART_ENABLED and not _is_valid_cron_expression(NIGHTLY_IDLE_RESTART_CRON_EXPR):
        return False, "Некорректное cron-выражение для ночного рестарта."

    lines = [line for line in lines if NIGHTLY_IDLE_RESTART_MARKER not in line]

    if NIGHTLY_IDLE_RESTART_ENABLED:
        command = _nightly_idle_restart_command()
        lines.append(
            f"{NIGHTLY_IDLE_RESTART_CRON_EXPR} {command} {NIGHTLY_IDLE_RESTART_MARKER}"
        )

    try:
        _write_crontab_lines(lines)
    except Exception as e:
        return False, f"Ошибка записи cron ночного рестарта: {e}"

    if NIGHTLY_IDLE_RESTART_ENABLED:
        return True, "Cron ночного рестарта включен"
    return True, "Cron ночного рестарта отключен"


def _get_or_create_auth_session_id():
    sid = (session.get("auth_sid") or "").strip()
    if sid:
        return sid

    sid = secrets.token_hex(16)
    session["auth_sid"] = sid
    session.modified = True
    return sid


def _cleanup_stale_active_web_sessions(now=None):
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=max(ACTIVE_WEB_SESSION_TTL_SECONDS * 2, 300))
    ActiveWebSession.query.filter(
        ActiveWebSession.last_seen_at < cutoff
    ).delete(synchronize_session=False)


def _touch_active_web_session(username, force=False):
    username = (username or "").strip()
    if not username:
        return

    now = datetime.utcnow()
    now_ts = int(time.time())

    if not force and ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS > 0:
        last_touch_ts = int(session.get("_active_session_touch_ts") or 0)
        if last_touch_ts and (now_ts - last_touch_ts) < ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS:
            return

    sid = _get_or_create_auth_session_id()
    remote_addr = ((request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",", 1)[0]).strip()
    user_agent = (request.headers.get("User-Agent") or "")[:255]

    row = ActiveWebSession.query.filter_by(session_id=sid).first()
    if row is None:
        db.session.add(
            ActiveWebSession(
                session_id=sid,
                username=username,
                remote_addr=remote_addr,
                user_agent=user_agent,
                created_at=now,
                last_seen_at=now,
            )
        )
    else:
        row.username = username
        row.remote_addr = remote_addr
        row.user_agent = user_agent
        row.last_seen_at = now

    _cleanup_stale_active_web_sessions(now=now)
    db.session.commit()
    session["_active_session_touch_ts"] = now_ts


def _remove_active_web_session():
    sid = (session.get("auth_sid") or "").strip()
    if not sid:
        return

    ActiveWebSession.query.filter_by(session_id=sid).delete(synchronize_session=False)
    db.session.commit()


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


try:
    _sync_ok, _sync_msg = _ensure_traffic_sync_cron()
    if not _sync_ok:
        app.logger.warning(_sync_msg)
except Exception as e:
    app.logger.warning(f"Не удалось инициализировать cron sync трафика: {e}")

try:
    _idle_restart_ok, _idle_restart_msg = _ensure_nightly_idle_restart_cron()
    if not _idle_restart_ok:
        app.logger.warning(_idle_restart_msg)
except Exception as e:
    app.logger.warning(f"Не удалось инициализировать cron ночного рестарта: {e}")


def _normalize_traffic_protocol_scope(protocol_scope):
    scope = (protocol_scope or "all").strip().lower()
    if scope not in ("all", "openvpn", "wireguard"):
        return "all"
    return scope


def _normalize_traffic_protocol_type(protocol_type, fallback="openvpn"):
    protocol = (protocol_type or fallback).strip().lower()
    if protocol not in ("openvpn", "wireguard"):
        protocol = fallback if fallback in ("openvpn", "wireguard") else "openvpn"
    return protocol


def _profile_matches_protocol_scope(profile, protocol_scope):
    scope = _normalize_traffic_protocol_scope(protocol_scope)
    is_wireguard_profile = str(profile or "").strip().lower().endswith("-wg")
    if scope == "wireguard":
        return is_wireguard_profile
    if scope == "openvpn":
        return not is_wireguard_profile
    return True


def _collect_wireguard_only_client_names_lower():
    protocols_by_client = _collect_config_protocols_by_client()
    result = set()
    for client_name, protocols in protocols_by_client.items():
        normalized = {
            str(protocol or "").strip()
            for protocol in (protocols or set())
            if str(protocol or "").strip()
        }
        if normalized == {"WireGuard"}:
            name = (client_name or "").strip().lower()
            if name:
                result.add(name)
    return result


def _delete_persisted_traffic_rows_by_scope(protocol_scope):
    scope = _normalize_traffic_protocol_scope(protocol_scope)

    if scope == "all":
        deleted_samples = UserTrafficSample.query.delete(synchronize_session=False)
        deleted_sessions = TrafficSessionState.query.delete(synchronize_session=False)
        return {
            "scope": scope,
            "deleted_samples": int(deleted_samples or 0),
            "deleted_sessions": int(deleted_sessions or 0),
        }

    if scope == "openvpn":
        deleted_samples = UserTrafficSample.query.filter(
            UserTrafficSample.protocol_type != "wireguard"
        ).delete(synchronize_session=False)
        deleted_sessions = TrafficSessionState.query.filter(
            TrafficSessionState.profile.notlike("%-wg")
        ).delete(synchronize_session=False)
        return {
            "scope": scope,
            "deleted_samples": int(deleted_samples or 0),
            "deleted_sessions": int(deleted_sessions or 0),
        }

    wireguard_only_clients = _collect_wireguard_only_client_names_lower()
    sample_query = UserTrafficSample.query.filter(UserTrafficSample.protocol_type == "wireguard")
    if wireguard_only_clients:
        sample_query = UserTrafficSample.query.filter(
            (UserTrafficSample.protocol_type == "wireguard")
            | (
                (UserTrafficSample.protocol_type != "wireguard")
                & db.func.lower(UserTrafficSample.common_name).in_(sorted(wireguard_only_clients))
            )
        )

    deleted_samples = sample_query.delete(synchronize_session=False)
    deleted_sessions = TrafficSessionState.query.filter(
        TrafficSessionState.profile.like("%-wg")
    ).delete(synchronize_session=False)

    return {
        "scope": scope,
        "deleted_samples": int(deleted_samples or 0),
        "deleted_sessions": int(deleted_sessions or 0),
    }


def _seed_traffic_session_baseline_for_scope(status_rows, protocol_scope, now=None):
    scope = _normalize_traffic_protocol_scope(protocol_scope)
    now = now or datetime.utcnow()

    sessions_by_key = {
        row.session_key: row
        for row in TrafficSessionState.query.all()
    }

    seen_scope_keys = set()
    seeded_users = set()
    inserted_sessions = 0
    updated_sessions = 0
    deactivated_sessions = 0

    for status_row in (status_rows or []):
        profile = status_row.get("profile", "unknown")
        if not _profile_matches_protocol_scope(profile, scope):
            continue

        for client in status_row.get("traffic_clients", status_row.get("clients", [])):
            common_name = (client.get("common_name") or "-").strip()
            if not common_name or common_name == "-":
                continue

            session_key = _build_session_key(profile, client)
            if session_key in seen_scope_keys:
                continue
            seen_scope_keys.add(session_key)

            current_rx = int(client.get("bytes_received") or 0)
            current_tx = int(client.get("bytes_sent") or 0)

            session_state = sessions_by_key.get(session_key)
            if session_state is None:
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
                inserted_sessions += 1
            else:
                session_state.profile = profile
                session_state.common_name = common_name
                session_state.real_address = (client.get("real_address") or "").strip() or None
                session_state.virtual_address = (client.get("virtual_address") or "").strip() or None
                session_state.connected_since_ts = int(client.get("connected_since_ts") or 0)
                session_state.last_bytes_received = current_rx
                session_state.last_bytes_sent = current_tx
                session_state.is_active = True
                session_state.last_seen_at = now
                session_state.ended_at = None
                updated_sessions += 1

            seeded_users.add(common_name)

    for session_key, session_state in sessions_by_key.items():
        if not _profile_matches_protocol_scope(session_state.profile, scope):
            continue
        if session_key in seen_scope_keys:
            continue
        if session_state.is_active:
            session_state.is_active = False
            session_state.ended_at = now
            deactivated_sessions += 1

    return {
        "scope": scope,
        "seeded_users": seeded_users,
        "active_sessions": len(seen_scope_keys),
        "inserted_sessions": inserted_sessions,
        "updated_sessions": updated_sessions,
        "deactivated_sessions": deactivated_sessions,
    }


def _rebuild_user_traffic_stats_from_samples(seed_users=None, now=None):
    now = now or datetime.utcnow()
    UserTrafficStat.query.delete(synchronize_session=False)
    UserTrafficStatProtocol.query.delete(synchronize_session=False)

    stats_map = {}
    stats_map_by_protocol = {}
    wireguard_only_clients = _collect_wireguard_only_client_names_lower()

    for sample in UserTrafficSample.query.order_by(UserTrafficSample.created_at.asc()).all():
        common_name = (sample.common_name or "").strip()
        if not common_name:
            continue

        normalized_protocol = _normalize_traffic_protocol_type(sample.protocol_type, fallback="openvpn")
        if normalized_protocol == "openvpn" and common_name.strip().lower() in wireguard_only_clients:
            normalized_protocol = "wireguard"

        stat = stats_map.get(common_name)
        sample_dt = sample.created_at or now
        if stat is None:
            stat = {
                "total_received": 0,
                "total_sent": 0,
                "total_received_vpn": 0,
                "total_sent_vpn": 0,
                "total_received_antizapret": 0,
                "total_sent_antizapret": 0,
                "first_seen_at": sample_dt,
                "last_seen_at": sample_dt,
            }
            stats_map[common_name] = stat

        protocol_key = (common_name, normalized_protocol)
        protocol_stat = stats_map_by_protocol.get(protocol_key)
        if protocol_stat is None:
            protocol_stat = {
                "total_received": 0,
                "total_sent": 0,
                "total_received_vpn": 0,
                "total_sent_vpn": 0,
                "total_received_antizapret": 0,
                "total_sent_antizapret": 0,
                "first_seen_at": sample_dt,
                "last_seen_at": sample_dt,
            }
            stats_map_by_protocol[protocol_key] = protocol_stat

        delta_rx = max(int(sample.delta_received or 0), 0)
        delta_tx = max(int(sample.delta_sent or 0), 0)
        network_type = (sample.network_type or "vpn").strip().lower()

        stat["total_received"] += delta_rx
        stat["total_sent"] += delta_tx
        if network_type == "antizapret":
            stat["total_received_antizapret"] += delta_rx
            stat["total_sent_antizapret"] += delta_tx
        else:
            stat["total_received_vpn"] += delta_rx
            stat["total_sent_vpn"] += delta_tx

        protocol_stat["total_received"] += delta_rx
        protocol_stat["total_sent"] += delta_tx
        if network_type == "antizapret":
            protocol_stat["total_received_antizapret"] += delta_rx
            protocol_stat["total_sent_antizapret"] += delta_tx
        else:
            protocol_stat["total_received_vpn"] += delta_rx
            protocol_stat["total_sent_vpn"] += delta_tx

        if sample_dt < stat["first_seen_at"]:
            stat["first_seen_at"] = sample_dt
        if sample_dt > stat["last_seen_at"]:
            stat["last_seen_at"] = sample_dt

        if sample_dt < protocol_stat["first_seen_at"]:
            protocol_stat["first_seen_at"] = sample_dt
        if sample_dt > protocol_stat["last_seen_at"]:
            protocol_stat["last_seen_at"] = sample_dt

    for common_name, stat in stats_map.items():
        db.session.add(
            UserTrafficStat(
                common_name=common_name,
                total_received=stat["total_received"],
                total_sent=stat["total_sent"],
                total_received_vpn=stat["total_received_vpn"],
                total_sent_vpn=stat["total_sent_vpn"],
                total_received_antizapret=stat["total_received_antizapret"],
                total_sent_antizapret=stat["total_sent_antizapret"],
                total_sessions=0,
                first_seen_at=stat["first_seen_at"] or now,
                last_seen_at=stat["last_seen_at"] or now,
            )
        )

    for (common_name, protocol_type), stat in stats_map_by_protocol.items():
        db.session.add(
            UserTrafficStatProtocol(
                common_name=common_name,
                protocol_type=protocol_type,
                total_received=stat["total_received"],
                total_sent=stat["total_sent"],
                total_received_vpn=stat["total_received_vpn"],
                total_sent_vpn=stat["total_sent_vpn"],
                total_received_antizapret=stat["total_received_antizapret"],
                total_sent_antizapret=stat["total_sent_antizapret"],
                total_sessions=0,
                first_seen_at=stat["first_seen_at"] or now,
                last_seen_at=stat["last_seen_at"] or now,
            )
        )

    seeded_only = 0
    seeded_only_protocol_rows = 0
    seed_names = sorted({(name or "").strip() for name in (seed_users or set()) if (name or "").strip()})
    seed_protocols_by_name = defaultdict(set)
    if seed_names:
        seed_sessions = TrafficSessionState.query.filter(
            TrafficSessionState.common_name.in_(seed_names)
        ).all()
        for state_row in seed_sessions:
            protocol_type = "wireguard" if str(state_row.profile or "").strip().lower().endswith("-wg") else "openvpn"
            seed_protocols_by_name[(state_row.common_name or "").strip()].add(protocol_type)

    for common_name in seed_names:
        if common_name in stats_map:
            continue
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
        seeded_only += 1

        protocol_candidates = seed_protocols_by_name.get(common_name, set()) or {"openvpn"}
        for protocol_type in sorted(protocol_candidates):
            if (common_name, protocol_type) in stats_map_by_protocol:
                continue
            db.session.add(
                UserTrafficStatProtocol(
                    common_name=common_name,
                    protocol_type=protocol_type,
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
            seeded_only_protocol_rows += 1

    return {
        "rebuilt_users": len(stats_map),
        "rebuilt_users_protocol_rows": len(stats_map_by_protocol),
        "seeded_only_users": seeded_only,
        "seeded_only_protocol_rows": seeded_only_protocol_rows,
    }


def _reset_persisted_traffic_data(protocol_scope="all"):
    """Сбрасывает накопленную статистику трафика полностью или по протоколу (openvpn/wireguard)."""
    scope = _normalize_traffic_protocol_scope(protocol_scope)
    scope_human = {
        "all": "вся статистика",
        "openvpn": "OpenVPN",
        "wireguard": "WireGuard/AWG",
    }

    try:
        now = datetime.utcnow()
        status_rows = _collect_status_rows_for_snapshot()

        deleted_info = _delete_persisted_traffic_rows_by_scope(scope)
        baseline_info = _seed_traffic_session_baseline_for_scope(status_rows, scope, now=now)
        rebuilt_info = _rebuild_user_traffic_stats_from_samples(
            seed_users=baseline_info.get("seeded_users", set()),
            now=now,
        )

        db.session.commit()

        if scope == "all":
            return True, (
                "Накопленная статистика трафика очищена. "
                f"Точка отсчета установлена: пользователей {len(baseline_info.get('seeded_users', set()))}, "
                f"активных сессий {baseline_info.get('active_sessions', 0)}."
            )

        return True, (
            f"Статистика {scope_human.get(scope, scope)} очищена. "
            f"Удалено записей: samples={deleted_info.get('deleted_samples', 0)}, "
            f"sessions={deleted_info.get('deleted_sessions', 0)}. "
            f"Обновлен baseline активных сессий: {baseline_info.get('active_sessions', 0)}. "
            f"Пользователей в БД: {int(rebuilt_info.get('rebuilt_users', 0)) + int(rebuilt_info.get('seeded_only_users', 0))}."
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


def _openvpn_socket_path(profile_key):
    return os.path.join(OPENVPN_SOCKET_DIR, f"{profile_key}.sock")


def _query_openvpn_management_socket(socket_path, command, max_response_bytes=0):
    if not socket_path or not os.path.exists(socket_path):
        return ""

    cmd = (command or "").strip()
    if not cmd:
        return ""

    max_response_bytes = int(max_response_bytes or 0)
    received_bytes = 0

    def _append_chunk(raw_bytes, target):
        nonlocal received_bytes
        if not raw_bytes:
            return False

        if max_response_bytes > 0:
            remaining = max_response_bytes - received_bytes
            if remaining <= 0:
                return True
            if len(raw_bytes) > remaining:
                raw_bytes = raw_bytes[:remaining]
                target.append(raw_bytes.decode("utf-8", errors="ignore"))
                received_bytes += len(raw_bytes)
                return True

        target.append(raw_bytes.decode("utf-8", errors="ignore"))
        received_bytes += len(raw_bytes)
        return False

    chunks = []
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock_conn:
            sock_conn.settimeout(OPENVPN_SOCKET_TIMEOUT)
            sock_conn.connect(socket_path)

            # Считываем приветствие management-интерфейса до отправки команды.
            try:
                banner = sock_conn.recv(65536)
                if banner:
                    if _append_chunk(banner, chunks):
                        return "".join(chunks)
            except socket.timeout:
                pass

            sock_conn.sendall((cmd + "\n").encode("utf-8", errors="ignore"))

            idle_timeout = OPENVPN_SOCKET_IDLE_TIMEOUT
            is_status_cmd = cmd.lower().startswith("status")
            read_deadline = time.monotonic() + (1.4 if is_status_cmd else 0.9)
            got_payload = False
            timeout_streak = 0
            end_probe = ""

            while time.monotonic() < read_deadline:
                try:
                    sock_conn.settimeout(idle_timeout)
                    data = sock_conn.recv(65536)
                except socket.timeout:
                    timeout_streak += 1
                    if got_payload and timeout_streak >= 2:
                        break
                    continue
                if not data:
                    break
                hit_limit = _append_chunk(data, chunks)
                text_chunk = chunks[-1] if chunks else ""
                got_payload = True
                timeout_streak = 0
                if is_status_cmd:
                    end_probe = (end_probe + text_chunk)[-256:]
                    if re.search(r"(^|\n)END(\n|$)", end_probe):
                        break
                if hit_limit:
                    break

            try:
                sock_conn.sendall(b"quit\n")
            except Exception:
                pass

            # Быстро дочитываем хвост после quit, если OpenVPN уже отправил оставшиеся байты.
            try:
                sock_conn.settimeout(0.05)
                while True:
                    tail = sock_conn.recv(65536)
                    if not tail:
                        break
                    if _append_chunk(tail, chunks):
                        break
            except Exception:
                pass
    except Exception:
        return ""

    return "".join(chunks)


def _extract_status_payload_from_management(raw):
    lines = []
    for raw_line in (raw or "").splitlines():
        line = raw_line.strip("\r")
        if not line:
            continue
        if (
            line.startswith("TITLE,")
            or line.startswith("TIME,")
            or line.startswith("HEADER,")
            or line.startswith("TITLE\t")
            or line.startswith("TIME\t")
            or line.startswith("HEADER\t")
            or line.startswith("TITLE ")
            or line.startswith("TIME ")
            or line.startswith("HEADER ")
        ):
            lines.append(line)
            continue
        if (
            line.startswith("CLIENT_LIST,")
            or line.startswith("ROUTING_TABLE,")
            or line.startswith("GLOBAL_STATS,")
            or line.startswith("CLIENT_LIST\t")
            or line.startswith("ROUTING_TABLE\t")
            or line.startswith("GLOBAL_STATS\t")
            or line.startswith("CLIENT_LIST ")
            or line.startswith("ROUTING_TABLE ")
            or line.startswith("GLOBAL_STATS ")
        ):
            lines.append(line)
            continue
        if line == "END":
            lines.append(line)

    return "\n".join(lines)


def _extract_event_payload_from_management(raw):
    lines = []
    for raw_line in (raw or "").splitlines():
        line = raw_line.strip("\r")
        if not line:
            continue

        if line.startswith(">LOG:"):
            parts = line.split(",", 2)
            msg = parts[2] if len(parts) >= 3 else ""
            msg = msg.strip()
            if msg:
                lines.append(msg)
            continue

        if any(token in line for token in ("Peer Connection Initiated", "VERIFY OK", "peer info:")):
            lines.append(line)

    return "\n".join(lines)


def _read_status_source(profile_key, fallback_path):
    _ = fallback_path
    socket_path = _openvpn_socket_path(profile_key)
    raw_mgmt = _query_openvpn_management_socket(socket_path, "status 3")
    payload = _extract_status_payload_from_management(raw_mgmt)
    if payload:
        return {
            "raw": payload,
            "source_name": os.path.basename(socket_path),
            "exists": True,
            "updated_at_ts": int(time.time()),
            "source_type": "socket",
        }

    return {
        "raw": "",
        "source_name": os.path.basename(socket_path),
        "exists": False,
        "updated_at_ts": 0,
        "source_type": "socket",
    }


def _read_event_source(profile_key, fallback_path):
    _ = fallback_path
    socket_path = _openvpn_socket_path(profile_key)
    log_cmd = "log all" if OPENVPN_LOG_TAIL_LINES == 0 else f"log {OPENVPN_LOG_TAIL_LINES}"
    raw_mgmt = _query_openvpn_management_socket(
        socket_path,
        log_cmd,
        max_response_bytes=OPENVPN_EVENT_MAX_RESPONSE_BYTES,
    )
    payload = _extract_event_payload_from_management(raw_mgmt)
    if payload:
        return {
            "raw": payload,
            "source_name": os.path.basename(socket_path),
            "exists": True,
            "updated_at_ts": int(time.time()),
            "source_type": "socket",
        }

    return {
        "raw": "",
        "source_name": os.path.basename(socket_path),
        "exists": False,
        "updated_at_ts": 0,
        "source_type": "socket",
    }


def _persist_peer_info_cache(event_rows):
    """Сохраняет версию/платформу клиентов в БД, чтобы UI мог брать данные из кэша."""
    best_rows = {}
    now = datetime.utcnow()

    for event in event_rows:
        profile = event.get("profile") or ""

        for sess in event.get("client_sessions", []):
            client_name = (sess.get("client") or "").strip()
            ip = (sess.get("ip") or "").strip()
            if not client_name or client_name == "-" or not ip:
                continue

            version = (sess.get("version") or "").strip() or None
            platform = (sess.get("platform") or "").strip() or None
            if not version and not platform:
                continue

            event_ts = int(sess.get("event_ts") or 0)
            if event_ts <= 0:
                event_ts = int(event.get("updated_at_ts", 0))

            endpoint = (sess.get("endpoint") or "").strip() or None
            rank = int(event_ts) * 1000000 + int(sess.get("last_order", -1))
            key = (profile, client_name, ip)
            prev = best_rows.get(key)
            if prev is None or rank >= int(prev.get("rank", -1)):
                best_rows[key] = {
                    "rank": rank,
                    "version": version,
                    "platform": platform,
                    "endpoint": endpoint,
                }

    if not best_rows:
        deleted_history = _prune_peer_info_history()
        if deleted_history > 0:
            db.session.commit()
        return

    cache_changed = False
    history_changed = False
    for (profile, client_name, ip), data in best_rows.items():
        row = OpenVPNPeerInfoCache.query.filter_by(
            profile=profile,
            client_name=client_name,
            ip=ip,
        ).first()

        if row is None:
            db.session.add(
                OpenVPNPeerInfoCache(
                    profile=profile,
                    client_name=client_name,
                    ip=ip,
                    endpoint=data.get("endpoint"),
                    version=data.get("version"),
                    platform=data.get("platform"),
                    last_event_rank=int(data.get("rank", 0)),
                    last_seen_at=now,
                )
            )
            cache_changed = True
        else:
            incoming_rank = int(data.get("rank", 0))
            current_rank = int(row.last_event_rank or 0)
            if incoming_rank >= current_rank:
                row.last_event_rank = incoming_rank
                row.last_seen_at = now
                if data.get("endpoint"):
                    row.endpoint = data.get("endpoint")
                if data.get("version"):
                    row.version = data.get("version")
                if data.get("platform"):
                    row.platform = data.get("platform")
                cache_changed = True

        incoming_rank = int(data.get("rank", 0))
        existing_history = OpenVPNPeerInfoHistory.query.filter_by(
            profile=profile,
            client_name=client_name,
            ip=ip,
            event_rank=incoming_rank,
        ).first()
        if existing_history is None:
            db.session.add(
                OpenVPNPeerInfoHistory(
                    profile=profile,
                    client_name=client_name,
                    ip=ip,
                    endpoint=data.get("endpoint"),
                    version=data.get("version"),
                    platform=data.get("platform"),
                    event_rank=incoming_rank,
                    observed_at=now,
                )
            )
            history_changed = True

    deleted_history = _prune_peer_info_history()
    if cache_changed or history_changed or deleted_history > 0:
        db.session.commit()


def _prune_peer_info_history():
    if OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS <= 0:
        return 0

    cutoff = datetime.utcnow() - timedelta(seconds=OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS)
    deleted = OpenVPNPeerInfoHistory.query.filter(
        OpenVPNPeerInfoHistory.observed_at < cutoff
    ).delete(synchronize_session=False)
    return int(deleted or 0)


def _load_peer_info_cache_map(include_stale=False):
    """Возвращает map (profile, client_name, ip) -> последняя версия/платформа из БД."""
    query = OpenVPNPeerInfoCache.query
    if OPENVPN_PEER_INFO_CACHE_TTL_SECONDS > 0 and not include_stale:
        cutoff = datetime.utcnow() - timedelta(seconds=OPENVPN_PEER_INFO_CACHE_TTL_SECONDS)
        query = query.filter(OpenVPNPeerInfoCache.last_seen_at >= cutoff)

    rows = query.order_by(OpenVPNPeerInfoCache.last_event_rank.desc()).all()
    out = {}
    for row in rows:
        key = ((row.profile or "").strip(), (row.client_name or "").strip(), (row.ip or "").strip())
        if not key[0] or not key[1] or not key[2] or key in out:
            continue
        out[key] = {
            "version": (row.version or "").strip() or None,
            "platform": (row.platform or "").strip() or None,
            "rank": int(row.last_event_rank or 0),
        }
    return out


def _load_peer_info_history_map(include_stale=False):
    """Возвращает map (profile, client_name, ip) -> последнее значение из истории peer info."""
    query = OpenVPNPeerInfoHistory.query
    if OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS > 0 and not include_stale:
        cutoff = datetime.utcnow() - timedelta(seconds=OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS)
        query = query.filter(OpenVPNPeerInfoHistory.observed_at >= cutoff)

    rows = query.order_by(OpenVPNPeerInfoHistory.event_rank.desc(), OpenVPNPeerInfoHistory.observed_at.desc()).all()
    out = {}
    for row in rows:
        key = ((row.profile or "").strip(), (row.client_name or "").strip(), (row.ip or "").strip())
        if not key[0] or not key[1] or not key[2] or key in out:
            continue
        out[key] = {
            "version": (row.version or "").strip() or None,
            "platform": (row.platform or "").strip() or None,
            "rank": int(row.event_rank or 0),
        }
    return out


def _human_bytes(value):
    size = float(value or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    precision = 0 if idx == 0 else (2 if size < 10 else 1)
    return f"{size:.{precision}f} {units[idx]}"


def _human_seconds(seconds_value):
    value = int(seconds_value or 0)
    if value < 60:
        return f"{value} сек"
    if value < 3600:
        return f"{value // 60} мин"
    if value < 86400:
        return f"{value // 3600} ч"
    return f"{value // 86400} д"


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
    is_wireguard = profile_key.endswith("-wg")
    return {
        "network": "Antizapret" if is_antizapret else "VPN",
        "transport": "TCP" if is_tcp else "UDP",
        "protocol": "WireGuard" if is_wireguard else "OpenVPN",
    }


def _format_dt(dt_obj):
    if not dt_obj:
        return "-"
    try:
        return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def _extract_client_name_from_config_file(file_path):
    filename = os.path.basename(file_path or "")
    stem = filename.rsplit('.', 1)[0]
    raw_name = re.sub(r"^(?:antizapret-|vpn-)", "", stem, flags=re.IGNORECASE)
    raw_name = re.sub(r"-(?:udp|tcp|wg|am)$", "", raw_name, flags=re.IGNORECASE)
    raw_name = re.sub(r"-\([^)]+\)$", "", raw_name)
    return (raw_name or "").strip()


def _collect_existing_config_client_names():
    """Собирает имена клиентов, для которых сейчас есть OpenVPN/WG/AmneziaWG-конфиги."""
    names = set()

    for base_dir in OPENVPN_FOLDERS:
        if not os.path.exists(base_dir):
            continue

        for root, _, files in os.walk(base_dir):
            for filename in files:
                if not filename.lower().endswith(".ovpn"):
                    continue
                client_name = _extract_client_name_from_config_file(filename)
                if client_name:
                    names.add(client_name.strip())

    for config_type in ("wg", "amneziawg"):
        for base_dir in CONFIG_PATHS.get(config_type, []):
            if not os.path.exists(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for filename in files:
                    if not filename.lower().endswith(".conf"):
                        continue
                    client_name = _extract_client_name_from_config_file(filename)
                    if client_name:
                        names.add(client_name.strip())

    return names


def _collect_config_protocols_by_client():
    """Возвращает map client_name(lower) -> set(protocol labels from existing config files)."""
    protocols_by_client = defaultdict(set)

    for base_dir in OPENVPN_FOLDERS:
        if not os.path.exists(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for filename in files:
                if not filename.lower().endswith(".ovpn"):
                    continue
                client_name = _extract_client_name_from_config_file(filename)
                if client_name:
                    protocols_by_client[client_name.strip().lower()].add("OpenVPN")

    for config_type in ("wg", "amneziawg"):
        for base_dir in CONFIG_PATHS.get(config_type, []):
            if not os.path.exists(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for filename in files:
                    if not filename.lower().endswith(".conf"):
                        continue
                    client_name = _extract_client_name_from_config_file(filename)
                    if client_name:
                        protocols_by_client[client_name.strip().lower()].add("WireGuard")

    return protocols_by_client


def _collect_sample_protocols_by_client():
    """Возвращает map client_name(lower) -> set(protocol labels from persisted traffic samples)."""
    protocols_by_client = defaultdict(set)

    delta_total_expr = UserTrafficSample.delta_received + UserTrafficSample.delta_sent
    rows = db.session.query(
        UserTrafficSample.common_name.label("common_name"),
        UserTrafficSample.protocol_type.label("protocol_type"),
        db.func.sum(delta_total_expr).label("total_bytes"),
    ).group_by(
        UserTrafficSample.common_name,
        UserTrafficSample.protocol_type,
    ).all()

    for row in rows:
        client_name = (row.common_name or "").strip().lower()
        if not client_name:
            continue

        if int(row.total_bytes or 0) <= 0:
            continue

        protocol = (row.protocol_type or "openvpn").strip().lower()
        protocol_label = "WireGuard" if protocol == "wireguard" else "OpenVPN"
        protocols_by_client[client_name].add(protocol_label)

    return protocols_by_client


def _split_persisted_traffic_rows_by_config(persisted_rows):
    existing_client_names = _collect_existing_config_client_names()
    existing_client_names_lower = {name.lower() for name in existing_client_names if name}

    regular_rows = []
    deleted_rows = []
    for row in persisted_rows:
        common_name = (row.get("common_name") or "").strip()
        if common_name and common_name.lower() in existing_client_names_lower:
            regular_rows.append(row)
        else:
            deleted_rows.append(row)

    deleted_total_bytes = sum(int(item.get("total_bytes") or 0) for item in deleted_rows)
    deleted_unique_clients = {
        (item.get("common_name") or "").strip().lower()
        for item in deleted_rows
        if (item.get("common_name") or "").strip()
    }
    deleted_summary = {
        "users_count": len(deleted_unique_clients),
        "total_bytes": deleted_total_bytes,
        "total_bytes_human": _human_bytes(deleted_total_bytes),
    }
    return regular_rows, deleted_rows, deleted_summary


def _build_session_key(profile, client):
    session_kind = (client.get("session_kind") or "").strip().lower()
    if session_kind == "wireguard" or str(profile or "").endswith("-wg"):
        common_name = (client.get("common_name") or "-").strip()
        peer_public_key = (client.get("peer_public_key") or "-").strip()
        virtual_address = (client.get("virtual_address") or "-").strip()
        # Для WG ключ сессии должен быть стабильным между handshake, иначе дельта удваивается.
        return f"{profile}|wg|{common_name}|{peer_public_key}|{virtual_address}"

    common_name = (client.get("common_name") or "-").strip()
    real_address = (client.get("real_address") or "-").strip()
    virtual_address = (client.get("virtual_address") or "-").strip()
    connected_since_ts = int(client.get("connected_since_ts") or 0)
    return f"{profile}|{common_name}|{real_address}|{virtual_address}|{connected_since_ts}"


def _is_retryable_snapshot_integrity_error(exc):
    error_text = str(getattr(exc, "orig", exc) or exc).lower()
    retryable_markers = (
        "unique constraint failed: traffic_session_state.session_key",
        "unique constraint failed: user_traffic_stat.common_name",
        "unique constraint failed: user_traffic_stat_protocol.common_name, user_traffic_stat_protocol.protocol_type",
    )
    return any(marker in error_text for marker in retryable_markers)


def _persist_traffic_snapshot(status_rows, _retry_on_integrity=True):
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
        ((row.common_name or "").strip(), _normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn")): row
        for row in UserTrafficStatProtocol.query.all()
    }

    seen_keys = set()

    for status_row in status_rows:
        profile = status_row.get("profile", "unknown")
        for client in status_row.get("traffic_clients", status_row.get("clients", [])):
            session_key = _build_session_key(profile, client)
            if session_key in seen_keys:
                continue
            seen_keys.add(session_key)

            current_rx = int(client.get("bytes_received") or 0)
            current_tx = int(client.get("bytes_sent") or 0)
            common_name = (client.get("common_name") or "-").strip()
            is_antizapret_profile = str(profile).startswith("antizapret")
            is_wireguard_profile = str(profile).endswith("-wg")
            protocol_type = "wireguard" if is_wireguard_profile else "openvpn"

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
                if is_wireguard_profile:
                    # Для нового WG-ключа считаем текущие байты baseline, чтобы не учитывать
                    # накопленные счетчики интерфейса как новый трафик клиента.
                    delta_rx = 0
                    delta_tx = 0
                else:
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

            user_stat = stats_by_user.get((common_name, protocol_type))
            if user_stat is None:
                user_stat = UserTrafficStatProtocol(
                    common_name=common_name,
                    protocol_type=protocol_type,
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
                stats_by_user[(common_name, protocol_type)] = user_stat

            user_stat.total_received = int(user_stat.total_received or 0) + max(delta_rx, 0)
            user_stat.total_sent = int(user_stat.total_sent or 0) + max(delta_tx, 0)

            if max(delta_rx, 0) > 0 or max(delta_tx, 0) > 0:
                db.session.add(
                    UserTrafficSample(
                        common_name=common_name,
                        network_type="antizapret" if is_antizapret_profile else "vpn",
                        protocol_type="wireguard" if is_wireguard_profile else "openvpn",
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

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if _retry_on_integrity and _is_retryable_snapshot_integrity_error(exc):
            app.logger.warning("Повтор сохранения traffic snapshot после конкурентного UNIQUE-конфликта: %s", exc)
            _persist_traffic_snapshot(status_rows, _retry_on_integrity=False)
            return
        raise


def _protocol_label_from_type(protocol_type):
    return "WireGuard" if _normalize_traffic_protocol_type(protocol_type, fallback="openvpn") == "wireguard" else "OpenVPN"


def _ensure_protocol_traffic_stats_backfilled(now=None):
    now = now or datetime.utcnow()
    sample_total_expr = UserTrafficSample.delta_received + UserTrafficSample.delta_sent
    protocol_total_expr = UserTrafficStatProtocol.total_received + UserTrafficStatProtocol.total_sent

    sample_total_bytes = int(
        db.session.query(db.func.coalesce(db.func.sum(sample_total_expr), 0)).scalar() or 0
    )
    if sample_total_bytes <= 0:
        return False

    has_protocol_stats = db.session.query(UserTrafficStatProtocol.id).limit(1).first() is not None
    protocol_total_bytes = int(
        db.session.query(db.func.coalesce(db.func.sum(protocol_total_expr), 0)).scalar() or 0
    )

    if has_protocol_stats and protocol_total_bytes >= int(sample_total_bytes * 0.999):
        return False

    seed_users = {
        (row.common_name or "").strip()
        for row in TrafficSessionState.query.with_entities(TrafficSessionState.common_name).all()
        if (row.common_name or "").strip()
    }

    rebuilt_info = _rebuild_user_traffic_stats_from_samples(seed_users=seed_users, now=now)
    db.session.commit()
    app.logger.info(
        "Выполнен авто-бэкфилл user_traffic_stat_protocol из sample: rows=%s, sample_total=%s, protocol_total_before=%s",
        int(rebuilt_info.get("rebuilt_users_protocol_rows", 0)),
        sample_total_bytes,
        protocol_total_bytes,
    )
    return True


def _collect_persisted_traffic_data(active_names=None, active_protocol_identities=None):
    try:
        _ensure_protocol_traffic_stats_backfilled()
    except Exception as exc:
        db.session.rollback()
        app.logger.warning("Не удалось выполнить авто-бэкфилл user_traffic_stat_protocol: %s", exc)

    users = UserTrafficStatProtocol.query.all()
    now = datetime.utcnow()
    active_names = set(active_names or set())
    active_protocol_identities = {
        ((name or "").strip(), _normalize_traffic_protocol_type(protocol, fallback="openvpn"))
        for name, protocol in (active_protocol_identities or set())
        if (name or "").strip()
    }
    day_1_since = now - timedelta(days=1)
    day_7_since = now - timedelta(days=7)
    day_30_since = now - timedelta(days=30)

    users_by_key = {
        ((row.common_name or "").strip(), _normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn")): row
        for row in users
    }
    for state_row in TrafficSessionState.query.with_entities(
        TrafficSessionState.common_name,
        TrafficSessionState.profile,
    ).all():
        common_name = (state_row.common_name or "").strip()
        if not common_name:
            continue
        protocol_type = "wireguard" if str(state_row.profile or "").strip().lower().endswith("-wg") else "openvpn"
        pair_key = (common_name, protocol_type)
        if pair_key in users_by_key:
            continue
        synthetic_row = UserTrafficStatProtocol(
            common_name=common_name,
            protocol_type=protocol_type,
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
        users.append(synthetic_row)
        users_by_key[pair_key] = synthetic_row

    delta_total_expr = UserTrafficSample.delta_received + UserTrafficSample.delta_sent
    recent_usage_rows = db.session.query(
        UserTrafficSample.common_name.label("common_name"),
        UserTrafficSample.protocol_type.label("protocol_type"),
        db.func.sum(
            case(
                (UserTrafficSample.created_at >= day_1_since, delta_total_expr),
                else_=0,
            )
        ).label("days_1"),
        db.func.sum(
            case(
                (UserTrafficSample.created_at >= day_7_since, delta_total_expr),
                else_=0,
            )
        ).label("days_7"),
        db.func.sum(delta_total_expr).label("days_30"),
    ).filter(
        UserTrafficSample.created_at >= day_30_since
    ).group_by(
        UserTrafficSample.common_name,
        UserTrafficSample.protocol_type,
    ).all()

    recent_usage = {
        (
            (row.common_name or "").strip(),
            _normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn"),
        ): {
            "days_1": int(row.days_1 or 0),
            "days_7": int(row.days_7 or 0),
            "days_30": int(row.days_30 or 0),
        }
        for row in recent_usage_rows
    }

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
        protocol_type = _normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn")
        protocol_label = _protocol_label_from_type(protocol_type)
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

        recent = recent_usage.get((row.common_name, protocol_type), {"days_1": 0, "days_7": 0, "days_30": 0})
        traffic_1d = int(recent.get("days_1", 0))
        traffic_7d = int(recent.get("days_7", 0))
        traffic_30d = int(recent.get("days_30", 0))

        is_active = ((row.common_name, protocol_type) in active_protocol_identities) or (row.common_name in active_names)
        rows.append(
            {
                "common_name": row.common_name,
                "protocol_type": protocol_type,
                "protocol_label": protocol_label,
                "display_name": f"{row.common_name} ({protocol_label})",
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

    latest_sample_dt = db.session.query(db.func.max(UserTrafficSample.created_at)).scalar()
    latest_stat_dt = db.session.query(db.func.max(UserTrafficStatProtocol.last_seen_at)).scalar()
    latest_dt_candidates = [dt for dt in (latest_sample_dt, latest_stat_dt) if dt is not None]
    latest_db_dt = max(latest_dt_candidates) if latest_dt_candidates else None
    db_age_seconds = None
    if latest_db_dt:
        try:
            db_age_seconds = max(int((now - latest_db_dt).total_seconds()), 0)
        except Exception:
            db_age_seconds = None

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
        "latest_sample_at": _format_dt(latest_sample_dt),
        "latest_stat_seen_at": _format_dt(latest_stat_dt),
        "db_age_seconds": db_age_seconds,
        "db_age_human": "-" if db_age_seconds is None else _human_seconds(db_age_seconds),
        "db_is_stale": False if db_age_seconds is None else (db_age_seconds > TRAFFIC_DB_STALE_SECONDS),
    }
    return rows, summary


def _delete_client_traffic_stats(common_name):
    """Удаляет накопленную статистику трафика для одного клиента."""
    target_name = (common_name or "").strip()
    if not target_name:
        return False, "Не указано имя клиента."

    try:
        deleted_samples = UserTrafficSample.query.filter(
            UserTrafficSample.common_name == target_name
        ).delete(synchronize_session=False)
        deleted_sessions = TrafficSessionState.query.filter(
            TrafficSessionState.common_name == target_name
        ).delete(synchronize_session=False)
        deleted_stats = UserTrafficStat.query.filter(
            UserTrafficStat.common_name == target_name
        ).delete(synchronize_session=False)
        deleted_protocol_stats = UserTrafficStatProtocol.query.filter(
            UserTrafficStatProtocol.common_name == target_name
        ).delete(synchronize_session=False)
        deleted_peer_cache = OpenVPNPeerInfoCache.query.filter(
            OpenVPNPeerInfoCache.client_name == target_name
        ).delete(synchronize_session=False)
        deleted_peer_history = OpenVPNPeerInfoHistory.query.filter(
            OpenVPNPeerInfoHistory.client_name == target_name
        ).delete(synchronize_session=False)

        db.session.commit()

        deleted_total = (
            int(deleted_samples or 0)
            + int(deleted_sessions or 0)
            + int(deleted_stats or 0)
            + int(deleted_protocol_stats or 0)
        )
        if deleted_total == 0 and int(deleted_peer_cache or 0) == 0 and int(deleted_peer_history or 0) == 0:
            return False, f"Для клиента '{target_name}' статистика не найдена."

        return True, (
            f"Статистика клиента '{target_name}' удалена "
            f"(stat={int(deleted_stats or 0)}, stat_protocol={int(deleted_protocol_stats or 0)}, "
            f"sessions={int(deleted_sessions or 0)}, samples={int(deleted_samples or 0)})."
        )
    except Exception as exc:
        db.session.rollback()
        return False, f"Ошибка удаления статистики клиента '{target_name}': {exc}"


def _normalize_wireguard_allowed_ip(token):
    value = (token or "").strip()
    if not value or value.lower() == "(none)":
        return ""
    return value.split("/", 1)[0].strip()


def _split_wireguard_allowed_ips(value):
    out = []
    for token in (value or "").split(","):
        ip = _normalize_wireguard_allowed_ip(token)
        if ip:
            out.append(ip)
    return out


def _extract_ip_from_wireguard_endpoint(endpoint):
    endpoint_value = (endpoint or "").strip()
    if not endpoint_value or endpoint_value == "(none)":
        return ""

    if endpoint_value.startswith("["):
        m_v6 = re.match(r"^\[([^\]]+)\](?::\d+)?$", endpoint_value)
        if m_v6:
            return m_v6.group(1)

    if ":" in endpoint_value:
        host_part, maybe_port = endpoint_value.rsplit(":", 1)
        if maybe_port.isdigit():
            return host_part

    return endpoint_value


def _parse_wireguard_config_peer_rows(config_path, interface_name):
    rows = []
    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_lines = f.readlines()
    except FileNotFoundError:
        return []
    except Exception:
        return []

    pending_client_name = ""
    current_peer = None

    def _flush_peer(peer_state):
        if not peer_state:
            return

        peer_key = (peer_state.get("peer_public_key") or "").strip()
        client_name = (peer_state.get("client_name") or "").strip()
        if not peer_key or not client_name:
            return

        rows.append(
            {
                "interface_name": interface_name,
                "peer_public_key": peer_key,
                "client_name": client_name,
                "allowed_ips": (peer_state.get("allowed_ips") or "").strip() or None,
            }
        )

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue

        m_client = re.match(r"^#\s*Client\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if m_client:
            pending_client_name = (m_client.group(1) or "").strip()
            continue

        if re.match(r"^\[Peer\]$", line, flags=re.IGNORECASE):
            _flush_peer(current_peer)
            current_peer = {
                "client_name": pending_client_name,
                "peer_public_key": "",
                "allowed_ips": "",
            }
            pending_client_name = ""
            continue

        if line.startswith("[") and line.endswith("]"):
            _flush_peer(current_peer)
            current_peer = None
            continue

        if current_peer is None:
            continue

        m_pub = re.match(r"^PublicKey\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if m_pub:
            current_peer["peer_public_key"] = (m_pub.group(1) or "").strip()
            continue

        m_allowed = re.match(r"^AllowedIPs\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if m_allowed:
            current_peer["allowed_ips"] = (m_allowed.group(1) or "").strip()

    _flush_peer(current_peer)
    return rows


def _sync_wireguard_peer_cache_from_configs(force=False):
    global _wireguard_peer_cache_last_sync_ts

    now_ts = int(time.time())
    if (
        not force
        and WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS > 0
        and (now_ts - int(_wireguard_peer_cache_last_sync_ts or 0)) < WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS
    ):
        return 0

    parsed_rows = []
    for interface_name, config_path in WIREGUARD_CONFIG_FILES.items():
        parsed_rows.extend(_parse_wireguard_config_peer_rows(config_path, interface_name))

    by_key = {}
    for row in parsed_rows:
        key = ((row.get("interface_name") or "").strip(), (row.get("peer_public_key") or "").strip())
        if not key[0] or not key[1]:
            continue
        by_key[key] = row

    existing_rows = WireGuardPeerCache.query.all()
    existing_by_key = {
        ((row.interface_name or "").strip(), (row.peer_public_key or "").strip()): row
        for row in existing_rows
    }

    changed = False
    for key, parsed in by_key.items():
        existing = existing_by_key.pop(key, None)
        parsed_name = (parsed.get("client_name") or "").strip()
        parsed_allowed = (parsed.get("allowed_ips") or "").strip() or None

        if existing is None:
            db.session.add(
                WireGuardPeerCache(
                    interface_name=key[0],
                    peer_public_key=key[1],
                    client_name=parsed_name,
                    allowed_ips=parsed_allowed,
                )
            )
            changed = True
            continue

        if (existing.client_name or "").strip() != parsed_name:
            existing.client_name = parsed_name
            changed = True
        if ((existing.allowed_ips or "").strip() or None) != parsed_allowed:
            existing.allowed_ips = parsed_allowed
            changed = True

    for stale_row in existing_by_key.values():
        db.session.delete(stale_row)
        changed = True

    if changed:
        db.session.commit()

    _wireguard_peer_cache_last_sync_ts = now_ts
    return len(by_key)


def _load_wireguard_peer_cache_maps():
    by_public_key = {}
    by_allowed_ip = {}

    for row in WireGuardPeerCache.query.all():
        interface_name = (row.interface_name or "").strip()
        peer_public_key = (row.peer_public_key or "").strip()
        client_name = (row.client_name or "").strip()
        if not interface_name or not client_name:
            continue

        if peer_public_key:
            by_public_key[(interface_name, peer_public_key)] = client_name

        for ip in _split_wireguard_allowed_ips(row.allowed_ips):
            by_allowed_ip[(interface_name, ip)] = client_name

    return by_public_key, by_allowed_ip


def _is_wireguard_peer_active(latest_handshake_ts):
    handshake_ts = int(latest_handshake_ts or 0)
    if handshake_ts <= 0:
        return False
    if WIREGUARD_ACTIVE_HANDSHAKE_SECONDS <= 0:
        return True
    return max(int(time.time()) - handshake_ts, 0) <= WIREGUARD_ACTIVE_HANDSHAKE_SECONDS


def _collect_wireguard_status_rows():
    status_rows = {
        "antizapret": {
            "profile": "antizapret-wg",
            "label": "Antizapret WG",
            "protocol": "WireGuard",
            "filename": "wg:antizapret",
            "exists": False,
            "snapshot_time": "-",
            "updated_at": "-",
            "clients": [],
            "traffic_clients": [],
        },
        "vpn": {
            "profile": "vpn-wg",
            "label": "VPN WG",
            "protocol": "WireGuard",
            "filename": "wg:vpn",
            "exists": False,
            "snapshot_time": "-",
            "updated_at": "-",
            "clients": [],
            "traffic_clients": [],
        },
    }

    try:
        result = subprocess.run(
            ["wg", "show", "all", "dump"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except Exception:
        result = None

    if result is None or result.returncode != 0:
        out_rows = []
        for interface_name in ("antizapret", "vpn"):
            row = status_rows[interface_name]
            row.update(
                {
                    "client_count": 0,
                    "unique_real_ips": 0,
                    "total_received": 0,
                    "total_sent": 0,
                    "total_received_human": _human_bytes(0),
                    "total_sent_human": _human_bytes(0),
                    "total_traffic_human": _human_bytes(0),
                }
            )
            out_rows.append(row)
        return out_rows

    now_dt = datetime.utcnow()
    snapshot_time = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    parsed_peers = []
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) == 5:
            interface_name = (parts[0] or "").strip()
            if interface_name in status_rows:
                status_rows[interface_name]["exists"] = True
                status_rows[interface_name]["snapshot_time"] = snapshot_time
                status_rows[interface_name]["updated_at"] = snapshot_time
            continue

        if len(parts) < 8:
            continue

        interface_name = (parts[0] or "").strip()
        if interface_name not in status_rows:
            continue

        status_rows[interface_name]["exists"] = True
        status_rows[interface_name]["snapshot_time"] = snapshot_time
        status_rows[interface_name]["updated_at"] = snapshot_time

        latest_handshake_ts = 0
        bytes_received = 0
        bytes_sent = 0
        try:
            latest_handshake_ts = int(parts[5] or 0)
        except (TypeError, ValueError):
            latest_handshake_ts = 0
        try:
            bytes_received = int(parts[6] or 0)
        except (TypeError, ValueError):
            bytes_received = 0
        try:
            bytes_sent = int(parts[7] or 0)
        except (TypeError, ValueError):
            bytes_sent = 0

        parsed_peers.append(
            {
                "interface": interface_name,
                "peer_public_key": (parts[1] or "").strip(),
                "endpoint": (parts[3] or "").strip(),
                "allowed_ips": (parts[4] or "").strip(),
                "latest_handshake_ts": latest_handshake_ts,
                "bytes_received": max(bytes_received, 0),
                "bytes_sent": max(bytes_sent, 0),
            }
        )

    by_public_key, by_allowed_ip = _load_wireguard_peer_cache_maps()
    missing_mapping = False
    for peer in parsed_peers:
        iface = peer.get("interface")
        key = (iface, (peer.get("peer_public_key") or "").strip())
        allowed_candidates = _split_wireguard_allowed_ips(peer.get("allowed_ips") or "")
        fallback_ip = allowed_candidates[0] if allowed_candidates else ""
        if key in by_public_key:
            continue
        if fallback_ip and (iface, fallback_ip) in by_allowed_ip:
            continue
        missing_mapping = True
        break

    if missing_mapping:
        try:
            _sync_wireguard_peer_cache_from_configs(force=False)
            by_public_key, by_allowed_ip = _load_wireguard_peer_cache_maps()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Не удалось обновить wireguard_peer_cache из конфигов: %s", exc)

    for peer in parsed_peers:
        interface_name = peer.get("interface")
        row = status_rows[interface_name]

        allowed_ips = _split_wireguard_allowed_ips(peer.get("allowed_ips") or "")
        preferred_allowed_ip = allowed_ips[0] if allowed_ips else ""
        peer_public_key = (peer.get("peer_public_key") or "").strip()

        common_name = by_public_key.get((interface_name, peer_public_key))
        if not common_name and preferred_allowed_ip:
            common_name = by_allowed_ip.get((interface_name, preferred_allowed_ip))
        if not common_name:
            if preferred_allowed_ip:
                common_name = f"{interface_name}-{preferred_allowed_ip}"
            elif peer_public_key:
                common_name = f"{interface_name}-{peer_public_key[:10]}"
            else:
                common_name = f"{interface_name}-peer"

        endpoint = (peer.get("endpoint") or "").strip()
        real_ip = _extract_ip_from_wireguard_endpoint(endpoint)
        latest_handshake_ts = int(peer.get("latest_handshake_ts") or 0)
        connected_since = "-"
        if latest_handshake_ts > 0:
            try:
                connected_since = datetime.fromtimestamp(latest_handshake_ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                connected_since = "-"

        client_payload = {
            "common_name": common_name,
            "real_address": endpoint if endpoint and endpoint != "(none)" else "-",
            "real_ip": real_ip,
            "virtual_address": preferred_allowed_ip or "-",
            "peer_public_key": peer_public_key,
            "session_kind": "wireguard",
            "bytes_received": int(peer.get("bytes_received") or 0),
            "bytes_sent": int(peer.get("bytes_sent") or 0),
            "total_bytes": int(peer.get("bytes_received") or 0) + int(peer.get("bytes_sent") or 0),
            "bytes_received_human": _human_bytes(peer.get("bytes_received") or 0),
            "bytes_sent_human": _human_bytes(peer.get("bytes_sent") or 0),
            "total_bytes_human": _human_bytes((peer.get("bytes_received") or 0) + (peer.get("bytes_sent") or 0)),
            "connected_since": connected_since,
            "connected_since_ts": latest_handshake_ts,
            "cipher": "WireGuard",
        }

        row["traffic_clients"].append(client_payload)
        if _is_wireguard_peer_active(latest_handshake_ts):
            row["clients"].append(client_payload)

    out_rows = []
    for interface_name in ("antizapret", "vpn"):
        row = status_rows[interface_name]
        row["clients"].sort(key=lambda item: int(item.get("total_bytes") or 0), reverse=True)

        total_received = sum(int(item.get("bytes_received") or 0) for item in row["clients"])
        total_sent = sum(int(item.get("bytes_sent") or 0) for item in row["clients"])
        unique_real_ips = len(
            {
                (item.get("real_ip") or "").strip()
                for item in row["clients"]
                if (item.get("real_ip") or "").strip()
            }
        )

        row.update(
            {
                "client_count": len(row["clients"]),
                "unique_real_ips": unique_real_ips,
                "total_received": total_received,
                "total_sent": total_sent,
                "total_received_human": _human_bytes(total_received),
                "total_sent_human": _human_bytes(total_sent),
                "total_traffic_human": _human_bytes(total_received + total_sent),
            }
        )
        out_rows.append(row)

    return out_rows


def _collect_status_rows_for_snapshot():
    rows = [
        _parse_status_log(profile_key, filename)
        for profile_key, filename in STATUS_LOG_FILES.items()
    ]
    rows.extend(_collect_wireguard_status_rows())
    return rows


def _parse_status_log(profile_key, filename):
    source = _read_status_source(profile_key, filename)
    raw = source.get("raw", "")
    meta = _profile_meta(profile_key)

    if not raw:
        return {
            "profile": profile_key,
            "label": f"{meta['network']} {meta['transport']}",
            "protocol": meta["protocol"],
            "filename": source.get("source_name", os.path.basename(filename)),
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
        time_match_tab = re.search(r"^TIME\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\d{10,})$", raw, re.MULTILINE)
        snapshot_time = time_match_tab.group(1).strip() if time_match_tab else "-"

    updated_ts = int(source.get("updated_at_ts") or 0)
    updated_at = datetime.fromtimestamp(updated_ts).strftime("%Y-%m-%d %H:%M:%S") if updated_ts > 0 else "-"

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
                "session_kind": "openvpn",
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

    # OpenVPN management может вернуть status 3 в табличном формате (без запятых).
    if not clients:
        client_pattern_tab = re.compile(
            r"^CLIENT_LIST\s+(\S+)\s+(\S+)\s+(\S+)\s+(?:(\S+)\s+)?(\d+)\s+(\d+)\s+"
            r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)",
            re.MULTILINE,
        )

        for match in client_pattern_tab.finditer(raw):
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
                    "session_kind": "openvpn",
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
        "protocol": meta["protocol"],
        "filename": source.get("source_name", os.path.basename(filename)),
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
    source = _read_event_source(profile_key, filename)
    raw = source.get("raw", "")
    meta = _profile_meta(profile_key)

    if not raw:
        return {
            "profile": profile_key,
            "label": f"{meta['network']} {meta['transport']}",
            "filename": source.get("source_name", os.path.basename(filename)),
            "exists": False,
            "updated_at": "-",
            "updated_at_ts": 0,
            "line_count": 0,
            "event_counts": {},
            "peer_connected_clients": [],
            "client_sessions": [],
            "recent_lines": [],
        }

    updated_at_ts = int(source.get("updated_at_ts") or 0)
    updated_at = datetime.fromtimestamp(updated_at_ts).strftime("%Y-%m-%d %H:%M:%S") if updated_at_ts > 0 else "-"

    raw_lines = raw.splitlines()
    line_count = len(raw_lines)
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

    for line_no, raw_line in enumerate(raw_lines):
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        line_ts = 0
        # Строки management часто приходят в формате: "<ts>,<level>,<message>".
        # Для регулярных выражений ниже используем message-часть.
        ts_match = re.match(r"^(\d+),[A-Z]?,(.*)$", raw_line)
        if ts_match:
            line_ts = int(ts_match.group(1) or 0)
            line = (ts_match.group(2) or "").strip()
        else:
            line = re.sub(r"^\d+,[A-Z]?,", "", raw_line, count=1).strip()
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
                    "last_ts": 0,
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
                    "last_ts": 0,
                },
            )
            endpoint_info[endpoint]["client"] = client_name

        # В management-логах встречается формат: "ip:port [Client] Peer Connection Initiated ..."
        m_peer_alt = re.search(r"^([^\s]+:\d+)\s+\[([^\]]+)\] Peer Connection Initiated with \[AF_INET\]([^\s]+:\d+)", line)
        if m_peer_alt:
            endpoint = _normalize_openvpn_endpoint(m_peer_alt.group(3))
            client_name = m_peer_alt.group(2)
            endpoint_info.setdefault(
                endpoint,
                {
                    "client": "-",
                    "ip": _extract_ip_from_openvpn_address(endpoint),
                    "version": None,
                    "platform": None,
                    "last_order": -1,
                    "last_ts": 0,
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
                    "last_ts": 0,
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
                    "last_ts": 0,
                },
            )
            if key == "IV_VER":
                endpoint_info[endpoint]["version"] = val
                endpoint_info[endpoint]["last_order"] = line_no
                if line_ts > 0:
                    endpoint_info[endpoint]["last_ts"] = line_ts
            elif key == "IV_PLAT":
                endpoint_info[endpoint]["platform"] = val
                endpoint_info[endpoint]["last_order"] = line_no
                if line_ts > 0:
                    endpoint_info[endpoint]["last_ts"] = line_ts

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
                "event_ts": int(info.get("last_ts") or 0),
            }
        )

    lines = [line.strip() for line in raw_lines if line.strip()]
    recent_lines = [line[:220] for line in lines[-8:]]

    return {
        "profile": profile_key,
        "label": f"{meta['network']} {meta['transport']}",
        "filename": source.get("source_name", os.path.basename(filename)),
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
    status_rows = _collect_status_rows_for_snapshot()

    _persist_traffic_snapshot(status_rows)

    event_rows = [
        _parse_event_log(profile_key, filename)
        for profile_key, filename in EVENT_LOG_FILES.items()
    ]

    try:
        _persist_peer_info_cache(event_rows)
    except Exception as e:
        db.session.rollback()
        app.logger.warning("Не удалось сохранить peer info cache/history: %s", e)
    peer_info_cache = _load_peer_info_history_map()
    peer_info_cache_stale = _load_peer_info_history_map(include_stale=True)

    # Мягкая миграция: пока history набирает данные, дополняем её legacy-кэшем,
    # чтобы не терять уже известные version/platform для активных клиентов.
    legacy_peer_info_cache = _load_peer_info_cache_map()
    legacy_peer_info_cache_stale = _load_peer_info_cache_map(include_stale=True)

    for key, cached in legacy_peer_info_cache.items():
        existing = peer_info_cache.get(key)
        if existing is None or int(cached.get("rank", -1)) > int(existing.get("rank", -1)):
            peer_info_cache[key] = cached

    for key, cached in legacy_peer_info_cache_stale.items():
        existing = peer_info_cache_stale.get(key)
        if existing is None or int(cached.get("rank", -1)) > int(existing.get("rank", -1)):
            peer_info_cache_stale[key] = cached
    peer_info_cache_by_client_ip = {}
    peer_info_cache_by_client = defaultdict(list)
    for (profile_key, client_name, ip), cached in peer_info_cache.items():
        if not client_name or not ip:
            continue
        key = (client_name, ip)
        prev = peer_info_cache_by_client_ip.get(key)
        if prev is None or int(cached.get("rank", -1)) > int(prev.get("rank", -1)):
            peer_info_cache_by_client_ip[key] = cached
        peer_info_cache_by_client[client_name].append(cached)

    peer_info_cache_stale_by_client_ip = {}
    peer_info_cache_stale_by_client = defaultdict(list)
    for (profile_key, client_name, ip), cached in peer_info_cache_stale.items():
        if not client_name or not ip:
            continue
        key = (client_name, ip)
        prev = peer_info_cache_stale_by_client_ip.get(key)
        if prev is None or int(cached.get("rank", -1)) > int(prev.get("rank", -1)):
            peer_info_cache_stale_by_client_ip[key] = cached
        peer_info_cache_stale_by_client[client_name].append(cached)

    total_active_clients = sum(item["client_count"] for item in status_rows)
    total_received = sum(item["total_received"] for item in status_rows)
    total_sent = sum(item["total_sent"] for item in status_rows)
    total_openvpn_sessions = sum(
        int(item.get("client_count") or 0)
        for item in status_rows
        if ((item.get("protocol") or "OpenVPN").strip() or "OpenVPN") == "OpenVPN"
    )
    total_wireguard_sessions = sum(
        int(item.get("client_count") or 0)
        for item in status_rows
        if ((item.get("protocol") or "OpenVPN").strip() or "OpenVPN") == "WireGuard"
    )

    unique_client_names = set()
    unique_ips = set()
    client_aggregate = defaultdict(
        lambda: {
            "bytes_received": 0,
            "bytes_sent": 0,
            "sessions": 0,
            "profiles": set(),
            "protocols": set(),
            "ips": set(),
            "versions": set(),
            "platforms": set(),
            "ip_details": {},
            "ip_profiles": {},
            "session_connections": [],
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
            client_aggregate[name]["protocols"].add((item.get("protocol") or "OpenVPN").strip() or "OpenVPN")
            if client.get("real_ip"):
                client_aggregate[name]["ips"].add(client["real_ip"])
                client_aggregate[name]["ip_profiles"].setdefault(client["real_ip"], set()).add(item["profile"])
                normalized_real_address = _normalize_openvpn_endpoint(client.get("real_address") or "")
                client_aggregate[name]["session_connections"].append(
                    {
                        "ip": client["real_ip"],
                        "real_address": (normalized_real_address or client["real_ip"]),
                        "connected_since_ts": int(client.get("connected_since_ts") or 0),
                        "profile_key": (item.get("profile") or "").strip(),
                        "profile_label": (item.get("label") or "-").strip() or "-",
                        "protocol": (item.get("protocol") or "OpenVPN").strip() or "OpenVPN",
                    }
                )
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

    # Для клиентов без свежего события подставляем последнее известное значение из БД.
    for client_name, stats in client_aggregate.items():
        for ip in sorted(stats.get("ips", set())):
            profile_candidates = sorted(stats.get("ip_profiles", {}).get(ip, set()))
            best_cached = None
            for profile_key in profile_candidates:
                cached = peer_info_cache.get((profile_key, client_name, ip))
                if not cached:
                    continue
                if best_cached is None or int(cached.get("rank", -1)) > int(best_cached.get("rank", -1)):
                    best_cached = cached

            # Если по текущему профилю не нашли, берём наиболее свежий кэш по client+ip.
            if not best_cached:
                best_cached = peer_info_cache_by_client_ip.get((client_name, ip))

            # Если IP сменился, но у клиента метаданные консистентны, берём их по имени.
            if not best_cached:
                cached_candidates = peer_info_cache_by_client.get(client_name, [])
                if cached_candidates:
                    unique_meta = {
                        ((item.get("version") or "").strip() or None, (item.get("platform") or "").strip() or None)
                        for item in cached_candidates
                        if (item.get("version") or item.get("platform"))
                    }
                    if len(unique_meta) == 1:
                        best_cached = max(
                            cached_candidates,
                            key=lambda item: int(item.get("rank", -1)),
                        )

            # Последний fallback: используем устаревший кэш, если свежих данных нет.
            if not best_cached:
                for profile_key in profile_candidates:
                    cached = peer_info_cache_stale.get((profile_key, client_name, ip))
                    if not cached:
                        continue
                    if best_cached is None or int(cached.get("rank", -1)) > int(best_cached.get("rank", -1)):
                        best_cached = cached

            if not best_cached:
                best_cached = peer_info_cache_stale_by_client_ip.get((client_name, ip))

            if not best_cached:
                cached_candidates = peer_info_cache_stale_by_client.get(client_name, [])
                if cached_candidates:
                    unique_meta = {
                        ((item.get("version") or "").strip() or None, (item.get("platform") or "").strip() or None)
                        for item in cached_candidates
                        if (item.get("version") or item.get("platform"))
                    }
                    if len(unique_meta) == 1:
                        best_cached = max(
                            cached_candidates,
                            key=lambda item: int(item.get("rank", -1)),
                        )

            if not best_cached:
                continue
            details = stats["ip_details"].setdefault(
                ip,
                {"version": None, "platform": None, "rank": -1},
            )
            if not details.get("version") and best_cached.get("version"):
                details["version"] = best_cached.get("version")
            if not details.get("platform") and best_cached.get("platform"):
                details["platform"] = best_cached.get("platform")

    connected_clients = []
    for name, stats in client_aggregate.items():
        total_bytes = stats["bytes_received"] + stats["bytes_sent"]
        ip_device_map = []
        client_versions_set = set()
        client_platforms_set = set()
        session_connections = sorted(
            stats.get("session_connections", []),
            key=lambda item: (
                int(item.get("connected_since_ts") or 0),
                (item.get("profile_label") or ""),
                (item.get("real_address") or item.get("ip") or ""),
            ),
        )

        session_key_counts = Counter()
        session_key_latest = {}
        for conn in session_connections:
            ip = (conn.get("ip") or "").strip()
            profile_key = (conn.get("profile_key") or "").strip()
            if not ip or not profile_key:
                continue

            key = (profile_key, ip)
            session_key_counts[key] += 1

            current_ts = int(conn.get("connected_since_ts") or 0)
            current_addr = (conn.get("real_address") or "").strip() or ip
            prev = session_key_latest.get(key)
            prev_ts = int(prev.get("connected_since_ts") or 0) if prev else -1
            prev_addr = (prev.get("real_address") or "").strip() if prev else ""
            if prev is None or current_ts > prev_ts or (current_ts == prev_ts and current_addr > prev_addr):
                session_key_latest[key] = {
                    "connected_since_ts": current_ts,
                    "real_address": current_addr,
                }

        if session_connections:
            for conn in session_connections:
                ip = (conn.get("ip") or "").strip()
                if not ip:
                    continue
                details = stats["ip_details"].get(ip, {"version": None, "platform": None})
                real_address = (conn.get("real_address") or "").strip() or ip
                profile_key = (conn.get("profile_key") or "").strip()
                profile_label = (conn.get("profile_label") or "-").strip() or "-"
                protocol_label = (conn.get("protocol") or "OpenVPN").strip() or "OpenVPN"
                is_openvpn_protocol = protocol_label == "OpenVPN"
                if is_openvpn_protocol:
                    platform_str = _human_device_type(details.get("platform")) if details.get("platform") else "Не определено"
                    version_str = details.get("version") or "Не определено"
                else:
                    platform_str = None
                    version_str = None
                is_stale_candidate = False

                if profile_key:
                    key = (profile_key, ip)
                    if int(session_key_counts.get(key, 0)) > 1:
                        latest = session_key_latest.get(key) or {}
                        latest_ts = int(latest.get("connected_since_ts") or 0)
                        latest_addr = (latest.get("real_address") or "").strip() or ip
                        current_ts = int(conn.get("connected_since_ts") or 0)
                        if real_address != latest_addr or current_ts < latest_ts:
                            is_stale_candidate = True

                if is_openvpn_protocol and version_str != "Не определено":
                    client_versions_set.add(version_str)
                if is_openvpn_protocol and platform_str != "Не определено":
                    client_platforms_set.add(platform_str)

                ip_device_map.append(
                    {
                        "ip": ip,
                        "real_address": real_address,
                        "show_real_address": real_address != ip,
                        "profile_label": profile_label,
                        "protocol": protocol_label,
                        "platform": platform_str,
                        "version": version_str,
                        "show_client_meta": is_openvpn_protocol,
                        "stale_candidate": is_stale_candidate,
                    }
                )
        else:
            has_openvpn_protocol = "OpenVPN" in (stats.get("protocols") or set())
            for ip in sorted(stats["ips"]):
                details = stats["ip_details"].get(ip, {"version": None, "platform": None})
                if has_openvpn_protocol:
                    platform_str = _human_device_type(details.get("platform")) if details.get("platform") else "Не определено"
                    version_str = details.get("version") or "Не определено"
                else:
                    platform_str = None
                    version_str = None

                if has_openvpn_protocol and version_str != "Не определено":
                    client_versions_set.add(version_str)
                if has_openvpn_protocol and platform_str != "Не определено":
                    client_platforms_set.add(platform_str)

                ip_device_map.append({
                    "ip": ip,
                    "real_address": ip,
                    "show_real_address": False,
                    "profile_label": "-",
                    "protocol": ", ".join(sorted(stats.get("protocols") or [])) if stats.get("protocols") else "-",
                    "platform": platform_str,
                    "version": version_str,
                    "show_client_meta": has_openvpn_protocol,
                    "stale_candidate": False,
                })

        protocols_sorted = sorted(stats.get("protocols") or [])
        is_wireguard_only = bool(protocols_sorted) and all(proto == "WireGuard" for proto in protocols_sorted)

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
                "protocols": ", ".join(sorted(stats["protocols"])) if stats.get("protocols") else "-",
                "ips": ", ".join(sorted(stats["ips"])) if stats["ips"] else "-",
                "client_versions": ", ".join(sorted(client_versions_set)) if client_versions_set else "-",
                "device_types": (
                    ", ".join(sorted(client_platforms_set))
                    if client_platforms_set
                    else ("WireGuard (без данных устройства)" if is_wireguard_only else "Не определено")
                ),
                "ip_device_map": ip_device_map,
            }
        )

    connected_clients.sort(key=lambda item: item["common_name"].lower())

    active_protocol_identities = set()
    for client_name, stats in client_aggregate.items():
        protocols = set(stats.get("protocols") or set())
        if "OpenVPN" in protocols:
            active_protocol_identities.add((client_name, "openvpn"))
        if "WireGuard" in protocols:
            active_protocol_identities.add((client_name, "wireguard"))

    persisted_traffic_rows, persisted_traffic_summary = _collect_persisted_traffic_data(
        active_names=unique_client_names,
        active_protocol_identities=active_protocol_identities,
    )
    persisted_traffic_rows, deleted_persisted_traffic_rows, deleted_persisted_traffic_summary = _split_persisted_traffic_rows_by_config(
        persisted_traffic_rows
    )

    config_protocols_map = _collect_config_protocols_by_client()
    sample_protocols_map = _collect_sample_protocols_by_client()

    for row in persisted_traffic_rows:
        row_protocol_type = _normalize_traffic_protocol_type(row.get("protocol_type"), fallback="openvpn")
        row_protocols = [_protocol_label_from_type(row_protocol_type)]
        if not row_protocols:
            common_name = (row.get("common_name") or "").strip().lower()
            row_protocols = sorted(
                sample_protocols_map.get(common_name, set())
                or config_protocols_map.get(common_name, set())
            )
        row["protocols"] = ", ".join(row_protocols) if row_protocols else "-"

    for row in deleted_persisted_traffic_rows:
        row_protocol_type = _normalize_traffic_protocol_type(row.get("protocol_type"), fallback="openvpn")
        row_protocols = [_protocol_label_from_type(row_protocol_type)]
        if not row_protocols:
            common_name = (row.get("common_name") or "").strip().lower()
            row_protocols = sorted(
                sample_protocols_map.get(common_name, set())
                or config_protocols_map.get(common_name, set())
            )
        row["protocols"] = ", ".join(row_protocols) if row_protocols else "-"

    total_event_lines = sum(item["line_count"] for item in event_rows)
    total_event_counts = Counter()
    for item in event_rows:
        total_event_counts.update(item.get("event_counts", {}))

    status_exists_map = {item.get("profile"): bool(item.get("exists")) for item in status_rows}
    event_exists_map = {item.get("profile"): bool(item.get("exists")) for item in event_rows}

    status_data_available = any(bool(item.get("exists")) for item in status_rows)
    event_data_available = any(bool(item.get("exists")) for item in event_rows)
    openvpn_logging_enabled = status_data_available or event_data_available

    missing_event_log_files = []
    if not openvpn_logging_enabled:
        for profile_key in EVENT_LOG_FILES.keys():
            socket_path = _openvpn_socket_path(profile_key)
            socket_name = os.path.basename(socket_path)
            socket_exists = os.path.exists(socket_path)
            profile_has_data = status_exists_map.get(profile_key, False) or event_exists_map.get(profile_key, False)

            if profile_has_data:
                continue

            if not socket_exists:
                missing_event_log_files.append(f"{socket_name} (не найден)")
            else:
                missing_event_log_files.append(f"{socket_name} (нет ответа на status/log)")

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
            "protocol_clients": Counter(),
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
            "protocol_clients": Counter(),
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
        protocol = ((row.get("protocol") or "OpenVPN").strip() or "OpenVPN")
        group["protocol_clients"][protocol] += row.get("client_count", 0)

        for client in row.get("clients", []):
            if client.get("real_ip"):
                group["real_ips"].add(client["real_ip"])

    grouped_status_rows = []
    for network in ("Antizapret", "VPN"):
        group = grouped_status_map[network]
        total_traffic = group["total_received"] + group["total_sent"]
        protocol_split = (
            f"OpenVPN: {int(group['protocol_clients'].get('OpenVPN', 0))}, "
            f"WireGuard: {int(group['protocol_clients'].get('WireGuard', 0))}"
        )
        grouped_status_rows.append(
            {
                "network": network,
                "files": ", ".join(sorted(set(group["files"]))),
                "snapshot_times": ", ".join(sorted(set(group["snapshot_times"]))),
                "updated_at": max(group["updated_values"]) if group["updated_values"] else "-",
                "client_count": group["client_count"],
                "unique_real_ips": len(group["real_ips"]),
                "protocol_split": protocol_split,
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
            "total_openvpn_sessions": total_openvpn_sessions,
            "total_wireguard_sessions": total_wireguard_sessions,
            "total_event_lines": total_event_lines,
            "total_event_counts": dict(total_event_counts),
        },
        "connected_clients": connected_clients,
        "persisted_traffic_rows": persisted_traffic_rows,
        "deleted_persisted_traffic_rows": deleted_persisted_traffic_rows,
        "persisted_traffic_summary": persisted_traffic_summary,
        "deleted_persisted_traffic_summary": deleted_persisted_traffic_summary,
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

        visible_client_names = set()
        for _file_list in (openvpn_files, wg_files, amneziawg_files):
            for _path in _file_list:
                _name = _extract_client_name_from_config_file(_path)
                if _name:
                    visible_client_names.add(_name)

        client_details_payload = {"connected": {}, "traffic": {}}
        try:
            dashboard_data = _get_logs_dashboard_data_cached(created_by_username=session.get("username"))
            connected_clients = dashboard_data.get("connected_clients", []) or []
            persisted_traffic_rows = dashboard_data.get("persisted_traffic_rows", []) or []

            if visible_client_names:
                connected_clients = [
                    item for item in connected_clients
                    if (item.get("common_name") or "") in visible_client_names
                ]
                persisted_traffic_rows = [
                    row for row in persisted_traffic_rows
                    if (row.get("common_name") or "") in visible_client_names
                ]

            for item in connected_clients:
                name = (item.get("common_name") or "").strip()
                if not name:
                    continue
                client_details_payload["connected"][name] = {
                    "common_name": name,
                    "sessions": int(item.get("sessions") or 0),
                    "profiles": item.get("profiles") or "-",
                    "bytes_received_human": item.get("bytes_received_human") or "0 B",
                    "bytes_sent_human": item.get("bytes_sent_human") or "0 B",
                    "total_bytes_human": item.get("total_bytes_human") or "0 B",
                    "ip_device_map": item.get("ip_device_map") or [],
                }

            for row in persisted_traffic_rows:
                name = (row.get("common_name") or "").strip()
                if not name:
                    continue

                entry = client_details_payload["traffic"].setdefault(
                    name,
                    {
                        "traffic_1d": 0,
                        "traffic_7d": 0,
                        "traffic_30d": 0,
                        "total_bytes_vpn": 0,
                        "total_bytes_antizapret": 0,
                        "total_bytes": 0,
                        "last_seen_at": "-",
                        "is_active": False,
                    },
                )

                entry["traffic_1d"] += int(row.get("traffic_1d") or 0)
                entry["traffic_7d"] += int(row.get("traffic_7d") or 0)
                entry["traffic_30d"] += int(row.get("traffic_30d") or 0)
                entry["total_bytes_vpn"] += int(row.get("total_bytes_vpn") or 0)
                entry["total_bytes_antizapret"] += int(row.get("total_bytes_antizapret") or 0)
                entry["total_bytes"] += int(row.get("total_bytes") or 0)

                row_last_seen = (row.get("last_seen_at") or "-").strip() or "-"
                if row_last_seen != "-" and (entry.get("last_seen_at") in (None, "-") or row_last_seen > str(entry.get("last_seen_at") or "-")):
                    entry["last_seen_at"] = row_last_seen

                if bool(row.get("is_active")):
                    entry["is_active"] = True

            for entry in client_details_payload["traffic"].values():
                entry["traffic_1d_human"] = _human_bytes(int(entry.get("traffic_1d") or 0))
                entry["traffic_7d_human"] = _human_bytes(int(entry.get("traffic_7d") or 0))
                entry["traffic_30d_human"] = _human_bytes(int(entry.get("traffic_30d") or 0))
                entry["total_bytes_vpn_human"] = _human_bytes(int(entry.get("total_bytes_vpn") or 0))
                entry["total_bytes_antizapret_human"] = _human_bytes(int(entry.get("total_bytes_antizapret") or 0))
                entry["total_bytes_human"] = _human_bytes(int(entry.get("total_bytes") or 0))
        except Exception as e:
            app.logger.warning("Не удалось подготовить client_details_payload для index: %s", e)

        return render_template(
            "index.html",
            openvpn_files=openvpn_files,
            wg_files=wg_files,
            amneziawg_files=amneziawg_files,
            cert_expiry=cert_expiry,
            banned_clients=banned_clients,
            current_openvpn_group=group,
            current_openvpn_folders=folders,
            client_details_payload=client_details_payload,
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

            if option in {"4", "5", "7"}:
                try:
                    _sync_wireguard_peer_cache_from_configs(force=True)
                except Exception as e:
                    db.session.rollback()
                    app.logger.warning(
                        "Не удалось синхронизировать wireguard_peer_cache после client.sh option=%s: %s",
                        option,
                        e,
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
            session["auth_sid"] = secrets.token_hex(16)
            session.pop("_active_session_touch_ts", None)
            session["attempts"] = 0
            try:
                _touch_active_web_session(user.username, force=True)
            except Exception as e:
                db.session.rollback()
                app.logger.warning(f"Не удалось обновить активную сессию при логине: {e}")
            return redirect(url_for("index"))
        flash("Неверные учетные данные. Попробуйте снова.", "error")
        return redirect(url_for("login"))
    return render_template("login.html", captcha=session["captcha"])


# Страница выхода
@app.route("/logout")
def logout():
    try:
        _remove_active_web_session()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Не удалось удалить активную сессию при logout: {e}")

    session.pop("auth_sid", None)
    session.pop("_active_session_touch_ts", None)
    session.pop("username", None)
    return redirect(url_for("login"))


@app.route("/api/session-heartbeat", methods=["GET"])
@auth_manager.login_required
def api_session_heartbeat():
    try:
        username = session.get("username")
        if username:
            _touch_active_web_session(username, force=True)
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Ошибка heartbeat активной сессии: {e}")
        return jsonify({"success": False}), 500


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
    pin_page_tpl = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Введите PIN</title>
  <style>
    body { font-family: sans-serif; background: #101722; color: #e6edf3; margin: 0; }
    .wrap { max-width: 420px; margin: 60px auto; padding: 24px; border-radius: 12px; background: #162133; }
    h2 { margin-top: 0; }
    input { width: 100%; box-sizing: border-box; padding: 12px; border-radius: 8px; border: 1px solid #2d3d56; background: #0f1725; color: #fff; }
    button { margin-top: 12px; width: 100%; padding: 12px; border: none; border-radius: 8px; background: #2c84ff; color: #fff; cursor: pointer; }
    .hint { color: #9fb3c8; font-size: 0.92rem; margin-top: 8px; }
    .error { color: #ff8b8b; margin-top: 10px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h2>PIN для скачивания</h2>
    <form method="GET">
      <input type="password" name="pin" inputmode="numeric" pattern="[0-9]*" placeholder="Введите PIN" autofocus required />
      <button type="submit">Скачать файл</button>
    </form>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <div class="hint">Осталось скачиваний: {{ remaining }}</div>
  </div>
</body>
</html>
    """

    try:
        token_row = QrDownloadToken.query.filter_by(token_hash=token_hash).first()
        if not token_row:
            _log_qr_event("download_not_found", details="token_not_found")
            abort(410, description="Ссылка истекла или уже использована")

        if token_row.expires_at < now:
            _log_qr_event("download_expired", token_row=token_row, details="token_expired")
            abort(410, description="Ссылка истекла или уже использована")

        if token_row.download_count >= token_row.max_downloads:
            _log_qr_event("download_limit_reached", token_row=token_row, details="limit_reached")
            abort(410, description="Ссылка истекла или уже использована")

        if token_row.pin_hash:
            pin = (request.args.get("pin") or "").strip()
            remaining = max(token_row.max_downloads - token_row.download_count, 0)
            if not pin:
                return render_template_string(pin_page_tpl, error=None, remaining=remaining)

            pin_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
            if pin_hash != token_row.pin_hash:
                _log_qr_event("download_pin_invalid", token_row=token_row, details="invalid_pin")
                return render_template_string(pin_page_tpl, error="Неверный PIN", remaining=remaining), 403

        updated = db.session.query(QrDownloadToken).filter(
            QrDownloadToken.id == token_row.id,
            QrDownloadToken.expires_at >= now,
            QrDownloadToken.download_count < QrDownloadToken.max_downloads,
        ).update(
            {
                "used_at": case((QrDownloadToken.used_at.is_(None), now), else_=QrDownloadToken.used_at),
                "download_count": QrDownloadToken.download_count + 1,
            },
            synchronize_session=False,
        )

        if updated != 1:
            db.session.rollback()
            _log_qr_event("download_limit_reached", token_row=token_row, details="race_limit_reached")
            abort(410, description="Ссылка уже использована")

        db.session.commit()
        _log_qr_event("download_success", token_row=token_row, details=f"count+1/{token_row.max_downloads}")

        file_path, _ = _resolve_config_file(token_row.config_type, token_row.config_name)
        if not file_path:
            _log_qr_event("download_file_missing", token_row=token_row, details="file_not_found")
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
                task = _enqueue_background_task(
                    "run_doall",
                    _task_run_doall,
                    created_by_username=session.get("username"),
                    queued_message="Применение изменений запущено в фоне",
                )
                return _task_accepted_response(
                    task,
                    "Файл сохранен. Применение изменений выполняется в фоне.",
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
        task = _enqueue_background_task(
            "run_doall",
            _task_run_doall,
            created_by_username=session.get("username"),
            queued_message="Запуск doall поставлен в очередь",
        )
        return _task_accepted_response(
            task,
            "Скрипт doall запущен в фоне.",
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500


# Маршрут для страницы мониторинга
@app.route("/server_monitor", methods=["GET"])
@auth_manager.login_required
def server_monitor():
    bw_iface_groups = _collect_bw_interface_groups()
    iface = os.getenv("VNSTAT_IFACE", "ens3")
    cpu_usage = server_monitor_proc.get_cpu_usage()
    memory_usage = server_monitor_proc.get_memory_usage()
    return render_template(
        "server_monitor.html",
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        iface=iface,
        bw_iface_groups=bw_iface_groups,
    )


@app.route("/logs_dashboard", methods=["GET"])
@auth_manager.login_required
def logs_dashboard():
    dashboard_data = _get_logs_dashboard_data_cached(created_by_username=session.get("username"))
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
        deleted_persisted_traffic_rows=dashboard_data["deleted_persisted_traffic_rows"],
        persisted_traffic_summary=dashboard_data["persisted_traffic_summary"],
        deleted_persisted_traffic_summary=dashboard_data["deleted_persisted_traffic_summary"],
        generated_at=dashboard_data["generated_at"],
        cache_meta=dashboard_data.get("cache_meta", {}),
        openvpn_log_tail_lines=OPENVPN_LOG_TAIL_LINES,
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
    protocol_scope = _normalize_traffic_protocol_scope(
        request.form.get("protocol_scope") or request.form.get("traffic_scope") or "all"
    )
    ok, message = _reset_persisted_traffic_data(protocol_scope=protocol_scope)
    return redirect(
        url_for(
            "logs_dashboard",
            cleanup_notice=message,
            cleanup_notice_kind="success" if ok else "error",
        )
    )


@app.route("/logs_dashboard/delete_deleted_client_traffic", methods=["POST"])
@auth_manager.admin_required
def logs_delete_deleted_client_traffic():
    client_name = (request.form.get("client_name") or "").strip()
    if not client_name:
        return redirect(
            url_for(
                "logs_dashboard",
                cleanup_notice="Не указано имя клиента для удаления статистики.",
                cleanup_notice_kind="error",
            )
        )

    existing_clients = {name.lower() for name in _collect_existing_config_client_names() if name}
    if client_name.lower() in existing_clients:
        return redirect(
            url_for(
                "logs_dashboard",
                cleanup_notice=f"У клиента '{client_name}' есть актуальный конфиг. Удаление статистики отменено.",
                cleanup_notice_kind="error",
            )
        )

    ok, message = _delete_client_traffic_stats(client_name)
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
    global NIGHTLY_IDLE_RESTART_ENABLED
    global NIGHTLY_IDLE_RESTART_CRON_EXPR
    global ACTIVE_WEB_SESSION_TTL_SECONDS
    global ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS

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

        max_downloads_raw = request.form.get("qr_download_token_max_downloads", "").strip()
        if max_downloads_raw:
            if max_downloads_raw.isdigit() and int(max_downloads_raw) in (1, 3, 5):
                _set_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", max_downloads_raw)
                os.environ["QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS"] = max_downloads_raw
                flash("Лимит скачиваний одноразовой ссылки обновлен", "success")
            else:
                flash("Лимит скачиваний должен быть одним из значений: 1, 3 или 5", "error")

        clear_pin = request.form.get("clear_qr_download_pin") == "on"
        pin_raw = (request.form.get("qr_download_pin") or "").strip()
        if clear_pin:
            _set_env_value("QR_DOWNLOAD_PIN", "")
            os.environ["QR_DOWNLOAD_PIN"] = ""
            flash("PIN для QR-ссылок очищен", "success")
        elif pin_raw:
            if pin_raw.isdigit() and 4 <= len(pin_raw) <= 12:
                _set_env_value("QR_DOWNLOAD_PIN", pin_raw)
                os.environ["QR_DOWNLOAD_PIN"] = pin_raw
                flash("PIN для QR-ссылок обновлен", "success")
            else:
                flash("PIN должен содержать только цифры и иметь длину от 4 до 12", "error")

        if request.form.get("nightly_settings_action") == "save":
            nightly_enabled_raw = (request.form.get("nightly_idle_restart_enabled") or "true").strip().lower()
            nightly_enabled = _to_bool(nightly_enabled_raw, default=True)

            ttl_raw = (request.form.get("active_web_session_ttl_seconds") or "").strip()
            touch_raw = (request.form.get("active_web_session_touch_interval_seconds") or "").strip()
            nightly_time_raw = (request.form.get("nightly_idle_restart_time") or "").strip()
            cron_expr_raw = (request.form.get("nightly_idle_restart_cron") or "").strip()

            has_error = False

            cron_expr = ""
            if nightly_time_raw:
                time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", nightly_time_raw)
                if time_match:
                    hour_value = int(time_match.group(1))
                    minute_value = int(time_match.group(2))
                    cron_expr = f"{minute_value} {hour_value} * * *"
                else:
                    flash("Укажите время в формате ЧЧ:ММ (например, 04:00)", "error")
                    has_error = True

            if not cron_expr:
                cron_expr = cron_expr_raw or "0 4 * * *"

            if not _is_valid_cron_expression(cron_expr):
                flash("Cron-выражение должно состоять из 5 полей и содержать только цифры и символы */,-", "error")
                has_error = True

            ttl_value = ACTIVE_WEB_SESSION_TTL_SECONDS
            if ttl_raw:
                if ttl_raw.isdigit() and 30 <= int(ttl_raw) <= 86400:
                    ttl_value = int(ttl_raw)
                else:
                    flash("TTL активной сессии должен быть целым числом в диапазоне 30..86400 секунд", "error")
                    has_error = True

            touch_value = ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS
            if touch_raw:
                if touch_raw.isdigit() and 1 <= int(touch_raw) <= 3600:
                    touch_value = int(touch_raw)
                else:
                    flash("Интервал heartbeat должен быть целым числом в диапазоне 1..3600 секунд", "error")
                    has_error = True

            if not has_error:
                NIGHTLY_IDLE_RESTART_ENABLED = nightly_enabled
                NIGHTLY_IDLE_RESTART_CRON_EXPR = cron_expr
                ACTIVE_WEB_SESSION_TTL_SECONDS = ttl_value
                ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS = touch_value

                env_enabled = "true" if nightly_enabled else "false"
                _set_env_value("NIGHTLY_IDLE_RESTART_ENABLED", env_enabled)
                _set_env_value("NIGHTLY_IDLE_RESTART_CRON", cron_expr)
                _set_env_value("ACTIVE_WEB_SESSION_TTL_SECONDS", str(ttl_value))
                _set_env_value("ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", str(touch_value))

                os.environ["NIGHTLY_IDLE_RESTART_ENABLED"] = env_enabled
                os.environ["NIGHTLY_IDLE_RESTART_CRON"] = cron_expr
                os.environ["ACTIVE_WEB_SESSION_TTL_SECONDS"] = str(ttl_value)
                os.environ["ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS"] = str(touch_value)

                cron_ok, cron_msg = _ensure_nightly_idle_restart_cron()
                if cron_ok:
                    flash("Настройки ночного рестарта сохранены", "success")
                else:
                    flash(cron_msg, "error")

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
                task = _enqueue_background_task(
                    "restart_service",
                    _task_restart_service,
                    created_by_username=session.get("username"),
                    queued_message="Перезапуск службы поставлен в очередь",
                )
                flash(
                    f"Перезапуск службы запущен в фоне (task: {task.id[:8]}). Обновите страницу через 10-20 секунд.",
                    "info",
                )
            except Exception as e:
                flash(f"Ошибка запуска фонового перезапуска: {str(e)}", "error")

        return redirect(url_for("settings"))

    # GET запрос - отображение страницы
    current_port = os.getenv("APP_PORT", "5050")
    qr_download_token_ttl_seconds = _get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600")
    qr_download_token_max_downloads = _get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1")
    qr_download_pin_set = bool((_get_env_value("QR_DOWNLOAD_PIN", "") or "").strip())
    nightly_idle_restart_enabled = NIGHTLY_IDLE_RESTART_ENABLED
    nightly_idle_restart_cron = NIGHTLY_IDLE_RESTART_CRON_EXPR
    nightly_idle_restart_time = "04:00"
    cron_parts = (nightly_idle_restart_cron or "").split()
    if len(cron_parts) == 5 and cron_parts[0].isdigit() and cron_parts[1].isdigit():
        minute_value = int(cron_parts[0])
        hour_value = int(cron_parts[1])
        if 0 <= minute_value <= 59 and 0 <= hour_value <= 23:
            nightly_idle_restart_time = f"{hour_value:02d}:{minute_value:02d}"

    active_web_session_ttl_seconds = ACTIVE_WEB_SESSION_TTL_SECONDS
    active_web_session_touch_interval_seconds = ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS
    active_web_sessions_count = ActiveWebSession.query.filter(
        ActiveWebSession.last_seen_at >= datetime.utcnow() - timedelta(seconds=ACTIVE_WEB_SESSION_TTL_SECONDS)
    ).count()
    qr_download_audit_logs = QrDownloadAuditLog.query.order_by(QrDownloadAuditLog.created_at.desc()).limit(100).all()
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
        qr_download_token_max_downloads=qr_download_token_max_downloads,
        qr_download_pin_set=qr_download_pin_set,
        nightly_idle_restart_enabled=nightly_idle_restart_enabled,
        nightly_idle_restart_cron=nightly_idle_restart_cron,
        nightly_idle_restart_time=nightly_idle_restart_time,
        active_web_session_ttl_seconds=active_web_session_ttl_seconds,
        active_web_session_touch_interval_seconds=active_web_session_touch_interval_seconds,
        active_web_sessions_count=active_web_sessions_count,
        qr_download_audit_logs=qr_download_audit_logs,
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
    protocol_filter = (request.args.get("protocol") or "all").strip().lower()

    if not client:
        return jsonify({"error": "Параметр client обязателен"}), 400

    if range_key not in ("1h", "24h", "7d", "30d", "all"):
        range_key = "7d"
    if protocol_filter not in ("all", "openvpn", "wireguard"):
        protocol_filter = "all"

    # Legacy fix: historical rows created before protocol split may have protocol_type='openvpn' by default.
    # If client currently has only WG/AWG configs, treat such rows as WireGuard for chart accuracy.
    client_protocols_map = _collect_config_protocols_by_client()
    client_protocols = set(client_protocols_map.get(client.lower(), set()))
    is_wireguard_only_client = bool(client_protocols) and "WireGuard" in client_protocols and "OpenVPN" not in client_protocols

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

    grouped = defaultdict(lambda: {"vpn": 0, "antizapret": 0, "openvpn": 0, "wireguard": 0})

    def format_bucket_dt_utc(dt_value, bucket_name):
        if not dt_value:
            return None

        if bucket_name == "minute5":
            aligned = dt_value.replace(minute=(dt_value.minute // 5) * 5, second=0, microsecond=0)
        elif bucket_name == "hour":
            aligned = dt_value.replace(minute=0, second=0, microsecond=0)
        elif bucket_name == "day":
            aligned = dt_value.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            aligned = dt_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if aligned.tzinfo is None:
            aligned = aligned.replace(tzinfo=timezone.utc)
        else:
            aligned = aligned.astimezone(timezone.utc)

        return aligned.isoformat().replace("+00:00", "Z")

    for item in samples:
        dt = item.created_at
        if not dt:
            continue

        label_dt_utc = format_bucket_dt_utc(dt, bucket)

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
        protocol = (item.protocol_type or "openvpn").strip().lower()
        if protocol not in ("openvpn", "wireguard"):
            protocol = "openvpn"
        if is_wireguard_only_client and protocol == "openvpn":
            protocol = "wireguard"

        if protocol_filter != "all" and protocol != protocol_filter:
            continue

        grouped[bucket_key]["label"] = label
        if label_dt_utc and "label_dt_utc" not in grouped[bucket_key]:
            grouped[bucket_key]["label_dt_utc"] = label_dt_utc
        grouped[bucket_key][net] += total_delta
        grouped[bucket_key][protocol] += total_delta

    ordered_keys = sorted(grouped.keys())
    labels = [grouped[key].get("label", key) for key in ordered_keys]
    label_datetimes_utc = [grouped[key].get("label_dt_utc") for key in ordered_keys]
    vpn_bytes = [int(grouped[key].get("vpn", 0)) for key in ordered_keys]
    antizapret_bytes = [int(grouped[key].get("antizapret", 0)) for key in ordered_keys]
    openvpn_bytes = [int(grouped[key].get("openvpn", 0)) for key in ordered_keys]
    wireguard_bytes = [int(grouped[key].get("wireguard", 0)) for key in ordered_keys]

    total_vpn = sum(vpn_bytes)
    total_antizapret = sum(antizapret_bytes)
    total_openvpn = sum(openvpn_bytes)
    total_wireguard = sum(wireguard_bytes)

    return jsonify(
        {
            "client": client,
            "range": range_key,
            "bucket": bucket,
            "protocol_filter": protocol_filter,
            "labels": labels,
            "label_datetimes_utc": label_datetimes_utc,
            "vpn_bytes": vpn_bytes,
            "antizapret_bytes": antizapret_bytes,
            "openvpn_bytes": openvpn_bytes,
            "wireguard_bytes": wireguard_bytes,
            "total_vpn": total_vpn,
            "total_antizapret": total_antizapret,
            "total_openvpn": total_openvpn,
            "total_wireguard": total_wireguard,
            "total": total_vpn + total_antizapret,
            "total_vpn_human": _human_bytes(total_vpn),
            "total_antizapret_human": _human_bytes(total_antizapret),
            "total_openvpn_human": _human_bytes(total_openvpn),
            "total_wireguard_human": _human_bytes(total_wireguard),
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
        _run_checked_command(["git", "fetch", "origin", "main", "--quiet"], cwd=APP_ROOT, timeout=30)
        local_commit, _ = _run_checked_command(["git", "rev-parse", "HEAD"], cwd=APP_ROOT, timeout=10)
        remote_commit, _ = _run_checked_command(["git", "rev-parse", "origin/main"], cwd=APP_ROOT, timeout=10)

        if local_commit.strip() != remote_commit.strip():
            return {"update_available": True, "message": "Доступно обновление!"}, 200
        return {"update_available": False, "message": "У вас последняя версия"}, 200

    except Exception:
        return {
            "update_available": False,
            "message": "Не удалось проверить обновления",
        }, 200


@app.route("/update_system", methods=["POST"])
@auth_manager.admin_required
def update_system():
    try:
        task = _enqueue_background_task(
            "update_system",
            _task_update_system,
            created_by_username=session.get("username"),
            queued_message="Обновление системы поставлено в очередь",
        )
        return _task_accepted_response(
            task,
            "Обновление системы запущено в фоне.",
        )
    except Exception:
        return {
            "success": False,
            "message": "Не удалось запустить фоновое обновление",
        }, 500


@app.route("/api/tasks/<task_id>", methods=["GET"])
@auth_manager.admin_required
def api_task_status(task_id):
    task = db.session.get(BackgroundTask, task_id)
    if not task:
        return jsonify({"success": False, "message": "Задача не найдена"}), 404

    payload = _serialize_background_task(task)
    payload["success"] = True
    return jsonify(payload)


@app.route("/api/logs_dashboard_refresh_status/<task_id>", methods=["GET"])
@auth_manager.login_required
def api_logs_dashboard_refresh_status(task_id):
    task = db.session.get(BackgroundTask, task_id)
    if not task or task.task_type != "logs_dashboard_refresh":
        return jsonify({"success": False, "message": "Задача обновления dashboard не найдена"}), 404

    return jsonify(
        {
            "success": True,
            "task_id": task.id,
            "status": task.status,
            "message": task.message,
            "error": task.error,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }
    )


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


@app.before_request
def track_active_web_session():
    if request.endpoint == "static":
        return

    username = (session.get("username") or "").strip()
    if not username:
        return

    try:
        _touch_active_web_session(username, force=False)
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Не удалось обновить активную сессию: {e}")


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
        task = _enqueue_background_task(
            "restart_service",
            _task_restart_service,
            created_by_username=session.get("username"),
            queued_message="Перезапуск службы поставлен в очередь",
        )
        return _task_accepted_response(task, "Перезапуск службы запущен в фоне.")
    except Exception as e:
        app.logger.error(f"Ошибка: {str(e)}")
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500


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
