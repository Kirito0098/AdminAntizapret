from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    abort,
)
from flask_sock import Sock
import subprocess
import os
import re
import json
import glob
import socket
import sys
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
import shlex
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import time
from sqlalchemy.exc import IntegrityError
from concurrent.futures import ThreadPoolExecutor

#Импорт файла с параметрами
from utils.ip_restriction import ip_restriction
from config.antizapret_params import ANTIZAPRET_PARAMS
from ips import ip_manager
from routes.route_wiring import register_all_routes
from routes.settings_antizapret import init_antizapret
from core.models import (
    ActiveWebSession,
    BackgroundTask,
    LogsDashboardCache,
    OpenVPNPeerInfoCache,
    OpenVPNPeerInfoHistory,
    QrDownloadAuditLog,
    QrDownloadToken,
    TelegramMiniAuditLog,
    TrafficSessionState,
    User,
    UserTrafficSample,
    UserTrafficStat,
    UserTrafficStatProtocol,
    ViewerConfigAccess,
    WireGuardPeerCache,
    db,
)
from core.services.logs_dashboard_collector import collect_logs_dashboard_data as collect_logs_dashboard_data_service
from core.services import (
    ActiveWebSessionService,
    AuthenticationManager,
    BackgroundTaskService,
    CaptchaGenerator,
    ClientProtocolCatalogService,
    ConfigAccessService,
    ConfigFileHandler,
    DatabaseMigrationService,
    EnvFileService,
    FileEditor,
    FileValidator,
    LogsDashboardCacheService,
    MaintenanceSchedulerService,
    NetworkStatusCollectorService,
    OpenVPNBanlistService,
    OpenVPNSocketReaderService,
    PeerInfoCacheService,
    QrDownloadTokenService,
    QRGenerator,
    RuntimeSettingsService,
    ScriptExecutor,
    ServerMonitor,
    build_services,
    TrafficMaintenanceService,
    TrafficPersistenceService,
    register_current_user_context_processor,
)

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


def _get_public_download_enabled():
    return PUBLIC_DOWNLOAD_ENABLED


def _set_public_download_enabled(value):
    global PUBLIC_DOWNLOAD_ENABLED
    PUBLIC_DOWNLOAD_ENABLED = bool(value)

try:
    BACKGROUND_TASK_WORKERS = max(1, int(os.getenv("BACKGROUND_TASK_WORKERS", "2")))
except (TypeError, ValueError):
    BACKGROUND_TASK_WORKERS = 2

BACKGROUND_TASK_MAX_OUTPUT_CHARS = 12000
background_task_executor = ThreadPoolExecutor(
    max_workers=BACKGROUND_TASK_WORKERS,
    thread_name_prefix="adminantizapret-task",
)

env_file_service = EnvFileService(ENV_FILE_PATH)


def _set_env_value(key, value):
    return env_file_service.set_env_value(key, value)


def _get_env_value(key, default=""):
    return env_file_service.get_env_value(key, default=default)


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

openvpn_banlist_service = OpenVPNBanlistService(
    banned_clients_file=OPENVPN_BANNED_CLIENTS_FILE,
    client_connect_script=OPENVPN_CLIENT_CONNECT_SCRIPT,
    client_connect_ban_check_block=CLIENT_CONNECT_BAN_CHECK_BLOCK,
)


def _read_banned_clients():
    return openvpn_banlist_service.read_banned_clients()


def _write_banned_clients(clients):
    return openvpn_banlist_service.write_banned_clients(clients)


def _ensure_client_connect_ban_check_block():
    return openvpn_banlist_service.ensure_client_connect_ban_check_block()


def normalize_openvpn_group_key(filename):
    return config_access_service.normalize_openvpn_group_key(filename)


def get_openvpn_group_display_name(filename):
    return config_access_service.get_openvpn_group_display_name(filename)


def collect_all_openvpn_files_for_access():
    return config_access_service.collect_all_openvpn_files_for_access()


def build_openvpn_access_groups(openvpn_paths):
    return config_access_service.build_openvpn_access_groups(openvpn_paths)


def normalize_conf_group_key(filename, config_type):
    return config_access_service.normalize_conf_group_key(filename, config_type)


def get_conf_group_display_name(filename, config_type):
    return config_access_service.get_conf_group_display_name(filename, config_type)


def build_conf_access_groups(conf_paths, config_type):
    return config_access_service.build_conf_access_groups(conf_paths, config_type)


def collect_all_configs_for_access(config_type):
    return config_access_service.collect_all_configs_for_access(config_type)

MIN_CERT_EXPIRE = 1
MAX_CERT_EXPIRE = 3650

# Настройка БД
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def _collect_bw_interface_groups():
    return config_access_service.collect_bw_interface_groups()


# Инициализация классов
script_executor = ScriptExecutor(
    min_cert_expire=MIN_CERT_EXPIRE,
    max_cert_expire=MAX_CERT_EXPIRE,
)
config_file_handler = ConfigFileHandler(CONFIG_PATHS)
config_access_service = ConfigAccessService(
    config_file_handler=config_file_handler,
    group_folders=GROUP_FOLDERS,
    config_paths=CONFIG_PATHS,
    openvpn_folders=OPENVPN_FOLDERS,
)
auth_manager = AuthenticationManager(User, ip_restriction)
captcha_generator = CaptchaGenerator()
file_validator = FileValidator(CONFIG_PATHS, fallback_openvpn_folders=OPENVPN_FOLDERS)
qr_generator = QRGenerator()
file_editor = FileEditor()
server_monitor_proc = ServerMonitor()
client_protocol_catalog_service = ClientProtocolCatalogService(
    openvpn_folders=OPENVPN_FOLDERS,
    config_paths=CONFIG_PATHS,
    db=db,
    user_traffic_sample_model=UserTrafficSample,
    human_bytes=lambda value: _human_bytes(value),
)

qr_download_token_service = QrDownloadTokenService(
    db=db,
    config_paths=CONFIG_PATHS,
    user_model=User,
    qr_download_token_model=QrDownloadToken,
    qr_download_audit_log_model=QrDownloadAuditLog,
    logger=app.logger,
)

database_migration_service = DatabaseMigrationService(
    app=app,
    db=db,
)

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
    return qr_download_token_service.create_one_time_download_url(
        file_path,
        get_env_value=_get_env_value,
    )


def _log_qr_event(event_type, token_row=None, details=None):
    return qr_download_token_service.log_qr_event(
        event_type,
        token_row=token_row,
        details=details,
    )


def _log_telegram_audit_event(event_type, config_name=None, details=None, actor_username=None, telegram_id=None):
    """Writes Telegram/Mini App audit events without affecting primary workflow."""
    try:
        username = str(actor_username or session.get("username") or "").strip() or None
        actor_user_id = None
        resolved_telegram_id = str(telegram_id or session.get("telegram_mini_id") or "").strip()

        if username:
            actor = User.query.filter_by(username=username).first()
            if actor:
                actor_user_id = actor.id
                if not resolved_telegram_id:
                    resolved_telegram_id = str(getattr(actor, "telegram_id", "") or "").strip()

        remote_addr = ((request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",", 1)[0]).strip()
        user_agent = (request.headers.get("User-Agent") or "")[:255]

        db.session.add(
            TelegramMiniAuditLog(
                actor_user_id=actor_user_id,
                actor_username=username,
                telegram_id=(resolved_telegram_id or None),
                event_type=str(event_type or "unknown")[:64],
                config_name=(str(config_name or "").strip() or None),
                details=(str(details or "")[:255] or None),
                remote_addr=(remote_addr or None),
                user_agent=(user_agent or None),
            )
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning("Не удалось записать событие Telegram audit: %s", e)


app.config["TELEGRAM_AUDIT_LOGGER"] = _log_telegram_audit_event


background_task_service = BackgroundTaskService(
    app=app,
    db=db,
    background_task_model=BackgroundTask,
    executor=background_task_executor,
    max_output_chars=BACKGROUND_TASK_MAX_OUTPUT_CHARS,
    app_root=APP_ROOT,
)


def _trim_background_task_text(value):
    return background_task_service.trim_background_task_text(value)


def _serialize_background_task(task):
    return background_task_service.serialize_background_task(task)


def _update_background_task(task_id, **fields):
    return background_task_service.update_background_task(task_id, **fields)


def _run_background_task(task_id, task_callable):
    return background_task_service.run_background_task(task_id, task_callable)


def _enqueue_background_task(task_type, task_callable, created_by_username=None, queued_message=None):
    return background_task_service.enqueue_background_task(
        task_type,
        task_callable,
        created_by_username=created_by_username,
        queued_message=queued_message,
    )


def _task_accepted_response(task, message):
    return background_task_service.task_accepted_response(
        task,
        message,
        status_endpoint="api_task_status",
    )


def _run_checked_command(args, cwd=None, timeout=120):
    return background_task_service.run_checked_command(args, cwd=cwd, timeout=timeout)


def _task_run_doall():
    return background_task_service.task_run_doall(
        sync_wireguard_peer_cache_callback=_sync_wireguard_peer_cache_from_configs,
    )


def _task_restart_service():
    return background_task_service.task_restart_service()


def _task_update_system():
    return background_task_service.task_update_system()


def _logs_dashboard_cache_row():
    return logs_dashboard_cache_service.logs_dashboard_cache_row()


def _save_logs_dashboard_cache_payload(payload, last_error=None):
    return logs_dashboard_cache_service.save_logs_dashboard_cache_payload(payload, last_error=last_error)


def _load_logs_dashboard_cache_payload():
    return logs_dashboard_cache_service.load_logs_dashboard_cache_payload()


def _build_empty_logs_dashboard_payload(reason_message=None):
    return logs_dashboard_cache_service.build_empty_logs_dashboard_payload(reason_message=reason_message)


def _is_logs_dashboard_refresh_in_progress():
    return logs_dashboard_cache_service.is_logs_dashboard_refresh_in_progress()


def _get_logs_dashboard_refresh_task():
    return logs_dashboard_cache_service.get_logs_dashboard_refresh_task()


def _task_refresh_logs_dashboard_cache():
    return logs_dashboard_cache_service.task_refresh_logs_dashboard_cache()


def _queue_logs_dashboard_refresh_if_needed(created_by_username=None):
    return logs_dashboard_cache_service.queue_logs_dashboard_refresh_if_needed(created_by_username=created_by_username)


def _get_logs_dashboard_data_cached(created_by_username=None):
    return logs_dashboard_cache_service.get_logs_dashboard_data_cached(created_by_username=created_by_username)

def _run_db_migrations():
    return database_migration_service.run_db_migrations()


_run_db_migrations()


register_current_user_context_processor(app, session, User)

runtime_settings_service = RuntimeSettingsService(
    get_env_value=_get_env_value,
    logs_dir="/etc/openvpn/server/logs",
)
runtime_settings = runtime_settings_service.load()

LOGS_DIR = runtime_settings["LOGS_DIR"]
OPENVPN_SOCKET_DIR = runtime_settings["OPENVPN_SOCKET_DIR"]
OPENVPN_SOCKET_TIMEOUT = runtime_settings["OPENVPN_SOCKET_TIMEOUT"]
OPENVPN_SOCKET_IDLE_TIMEOUT = runtime_settings["OPENVPN_SOCKET_IDLE_TIMEOUT"]
OPENVPN_LOG_TAIL_LINES = runtime_settings["OPENVPN_LOG_TAIL_LINES"]
OPENVPN_EVENT_MAX_RESPONSE_BYTES = runtime_settings["OPENVPN_EVENT_MAX_RESPONSE_BYTES"]
OPENVPN_PEER_INFO_CACHE_TTL_SECONDS = runtime_settings["OPENVPN_PEER_INFO_CACHE_TTL_SECONDS"]
OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS = runtime_settings["OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS"]
TRAFFIC_DB_STALE_SECONDS = runtime_settings["TRAFFIC_DB_STALE_SECONDS"]
TRAFFIC_SYNC_CRON_MARKER = runtime_settings["TRAFFIC_SYNC_CRON_MARKER"]
TRAFFIC_SYNC_CRON_EXPR = runtime_settings["TRAFFIC_SYNC_CRON_EXPR"]
TRAFFIC_SYNC_ENABLED = runtime_settings["TRAFFIC_SYNC_ENABLED"]
NIGHTLY_IDLE_RESTART_MARKER = runtime_settings["NIGHTLY_IDLE_RESTART_MARKER"]
NIGHTLY_IDLE_RESTART_CRON_EXPR = runtime_settings["NIGHTLY_IDLE_RESTART_CRON_EXPR"]
NIGHTLY_IDLE_RESTART_ENABLED = runtime_settings["NIGHTLY_IDLE_RESTART_ENABLED"]
ACTIVE_WEB_SESSION_TTL_SECONDS = runtime_settings["ACTIVE_WEB_SESSION_TTL_SECONDS"]
ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS = runtime_settings["ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS"]


def _get_nightly_idle_restart_settings():
    return NIGHTLY_IDLE_RESTART_ENABLED, NIGHTLY_IDLE_RESTART_CRON_EXPR


def _set_nightly_idle_restart_settings(enabled, cron_expr):
    global NIGHTLY_IDLE_RESTART_ENABLED
    global NIGHTLY_IDLE_RESTART_CRON_EXPR
    NIGHTLY_IDLE_RESTART_ENABLED = bool(enabled)
    NIGHTLY_IDLE_RESTART_CRON_EXPR = (cron_expr or "0 4 * * *").strip()


def _get_active_web_session_settings():
    return ACTIVE_WEB_SESSION_TTL_SECONDS, ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS


def _set_active_web_session_settings(ttl_seconds, touch_interval_seconds):
    global ACTIVE_WEB_SESSION_TTL_SECONDS
    global ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS
    ACTIVE_WEB_SESSION_TTL_SECONDS = max(30, int(ttl_seconds))
    ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS = max(1, int(touch_interval_seconds))

LOGS_DASHBOARD_CACHE_TTL_SECONDS = runtime_settings["LOGS_DASHBOARD_CACHE_TTL_SECONDS"]
STATUS_LOG_FILES = runtime_settings["STATUS_LOG_FILES"]
EVENT_LOG_FILES = runtime_settings["EVENT_LOG_FILES"]
WIREGUARD_CONFIG_FILES = runtime_settings["WIREGUARD_CONFIG_FILES"]
WIREGUARD_ACTIVE_HANDSHAKE_SECONDS = runtime_settings["WIREGUARD_ACTIVE_HANDSHAKE_SECONDS"]
WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS = runtime_settings[
    "WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS"
]
STATUS_LOG_CLEANUP_MARKER = runtime_settings["STATUS_LOG_CLEANUP_MARKER"]
STATUS_LOG_CLEANUP_PERIODS = runtime_settings["STATUS_LOG_CLEANUP_PERIODS"]


def _status_log_cleanup_command():
    return maintenance_scheduler_service.status_log_cleanup_command()


def _read_crontab_lines():
    return maintenance_scheduler_service.read_crontab_lines()


def _write_crontab_lines(lines):
    maintenance_scheduler_service.write_crontab_lines(lines)


def _strip_status_cleanup_jobs(lines):
    return maintenance_scheduler_service.strip_status_cleanup_jobs(lines)


def _traffic_sync_command():
    return maintenance_scheduler_service.traffic_sync_command()


def _nightly_idle_restart_command():
    return maintenance_scheduler_service.nightly_idle_restart_command()


def _is_systemd_traffic_sync_timer_enabled():
    return maintenance_scheduler_service.is_systemd_traffic_sync_timer_enabled()


def _ensure_traffic_sync_cron():
    return maintenance_scheduler_service.ensure_traffic_sync_cron()


def _ensure_nightly_idle_restart_cron():
    return maintenance_scheduler_service.ensure_nightly_idle_restart_cron()


_services = build_services(
    app=app,
    db=db,
    app_root=APP_ROOT,
    logs_dir=LOGS_DIR,
    status_log_cleanup_marker=STATUS_LOG_CLEANUP_MARKER,
    status_log_cleanup_periods=STATUS_LOG_CLEANUP_PERIODS,
    traffic_sync_cron_marker=TRAFFIC_SYNC_CRON_MARKER,
    traffic_sync_cron_expr=TRAFFIC_SYNC_CRON_EXPR,
    traffic_sync_enabled=TRAFFIC_SYNC_ENABLED,
    nightly_idle_restart_marker=NIGHTLY_IDLE_RESTART_MARKER,
    openvpn_socket_dir=OPENVPN_SOCKET_DIR,
    openvpn_socket_timeout=OPENVPN_SOCKET_TIMEOUT,
    openvpn_socket_idle_timeout=OPENVPN_SOCKET_IDLE_TIMEOUT,
    openvpn_log_tail_lines=OPENVPN_LOG_TAIL_LINES,
    openvpn_event_max_response_bytes=OPENVPN_EVENT_MAX_RESPONSE_BYTES,
    wireguard_config_files=WIREGUARD_CONFIG_FILES,
    wireguard_active_handshake_seconds=WIREGUARD_ACTIVE_HANDSHAKE_SECONDS,
    wireguard_peer_cache_sync_min_interval_seconds=WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS,
    status_log_files=STATUS_LOG_FILES,
    traffic_db_stale_seconds=TRAFFIC_DB_STALE_SECONDS,
    openvpn_peer_info_cache_ttl_seconds=OPENVPN_PEER_INFO_CACHE_TTL_SECONDS,
    openvpn_peer_info_history_retention_seconds=OPENVPN_PEER_INFO_HISTORY_RETENTION_SECONDS,
    logs_dashboard_cache_ttl_seconds=LOGS_DASHBOARD_CACHE_TTL_SECONDS,
    active_web_session_model=ActiveWebSession,
    user_traffic_sample_model=UserTrafficSample,
    traffic_session_state_model=TrafficSessionState,
    user_traffic_stat_model=UserTrafficStat,
    user_traffic_stat_protocol_model=UserTrafficStatProtocol,
    openvpn_peer_info_cache_model=OpenVPNPeerInfoCache,
    openvpn_peer_info_history_model=OpenVPNPeerInfoHistory,
    wireguard_peer_cache_model=WireGuardPeerCache,
    logs_dashboard_cache_model=LogsDashboardCache,
    background_task_model=BackgroundTask,
    integrity_error_cls=IntegrityError,
    is_valid_cron_expression=_is_valid_cron_expression,
    get_nightly_idle_restart_settings=lambda: _get_nightly_idle_restart_settings(),
    get_active_web_session_settings=lambda: _get_active_web_session_settings(),
    collect_config_protocols_by_client=lambda: _collect_config_protocols_by_client(),
    build_session_key=lambda profile, client: _build_session_key(profile, client),
    collect_status_rows_for_snapshot=lambda: _collect_status_rows_for_snapshot(),
    human_bytes=lambda value: _human_bytes(value),
    extract_ip_from_openvpn_address=lambda value: _extract_ip_from_openvpn_address(value),
    profile_meta=lambda profile_key: _profile_meta(profile_key),
    read_status_source=lambda profile_key, fallback_path: _read_status_source(profile_key, fallback_path),
    read_event_source=lambda profile_key, fallback_path: _read_event_source(profile_key, fallback_path),
    normalize_openvpn_endpoint=lambda endpoint: _normalize_openvpn_endpoint(endpoint),
    normalize_traffic_protocol_type=lambda protocol_type, fallback="openvpn": _normalize_traffic_protocol_type(protocol_type, fallback=fallback),
    rebuild_user_traffic_stats_from_samples=lambda seed_users=None, now=None: _rebuild_user_traffic_stats_from_samples(seed_users=seed_users, now=now),
    human_seconds=lambda value: _human_seconds(value),
    format_dt=lambda dt_obj: _format_dt(dt_obj),
    collect_logs_dashboard_data=lambda: _collect_logs_dashboard_data(),
    enqueue_background_task=lambda task_type, target_func, created_by_username=None, queued_message=None: _enqueue_background_task(
        task_type,
        target_func,
        created_by_username=created_by_username,
        queued_message=queued_message,
    ),
)

maintenance_scheduler_service = _services["maintenance_scheduler_service"]
active_web_session_service = _services["active_web_session_service"]
traffic_maintenance_service = _services["traffic_maintenance_service"]
openvpn_socket_reader_service = _services["openvpn_socket_reader_service"]
network_status_collector_service = _services["network_status_collector_service"]
traffic_persistence_service = _services["traffic_persistence_service"]
peer_info_cache_service = _services["peer_info_cache_service"]
logs_dashboard_cache_service = _services["logs_dashboard_cache_service"]


def _get_or_create_auth_session_id():
    return active_web_session_service.get_or_create_auth_session_id(session)


def _cleanup_stale_active_web_sessions(now=None):
    active_web_session_service.cleanup_stale_active_web_sessions(now=now)


def _touch_active_web_session(username, force=False):
    active_web_session_service.touch_active_web_session(
        username,
        session_obj=session,
        request_obj=request,
        db_session=db.session,
        force=force,
    )


def _remove_active_web_session():
    active_web_session_service.remove_active_web_session(
        session_obj=session,
        db_session=db.session,
    )


def _get_status_cleanup_schedule():
    return maintenance_scheduler_service.get_status_cleanup_schedule()


def _set_status_cleanup_schedule(period):
    return maintenance_scheduler_service.set_status_cleanup_schedule(period)


def _cleanup_status_logs_now():
    return maintenance_scheduler_service.cleanup_status_logs_now()


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
    return traffic_maintenance_service.normalize_traffic_protocol_scope(protocol_scope)


def _normalize_traffic_protocol_type(protocol_type, fallback="openvpn"):
    return traffic_maintenance_service.normalize_traffic_protocol_type(protocol_type, fallback=fallback)


def _profile_matches_protocol_scope(profile, protocol_scope):
    return traffic_maintenance_service.profile_matches_protocol_scope(profile, protocol_scope)


def _collect_wireguard_only_client_names_lower():
    return traffic_maintenance_service.collect_wireguard_only_client_names_lower()


def _delete_persisted_traffic_rows_by_scope(protocol_scope):
    return traffic_maintenance_service.delete_persisted_traffic_rows_by_scope(protocol_scope)


def _seed_traffic_session_baseline_for_scope(status_rows, protocol_scope, now=None):
    return traffic_maintenance_service.seed_traffic_session_baseline_for_scope(
        status_rows,
        protocol_scope,
        now=now,
    )


def _rebuild_user_traffic_stats_from_samples(seed_users=None, now=None):
    return traffic_maintenance_service.rebuild_user_traffic_stats_from_samples(
        seed_users=seed_users,
        now=now,
    )


def _reset_persisted_traffic_data(protocol_scope="all"):
    return traffic_maintenance_service.reset_persisted_traffic_data(protocol_scope=protocol_scope)


def _read_log_file(path):
    return openvpn_socket_reader_service.read_log_file(path)


def _openvpn_socket_path(profile_key):
    return openvpn_socket_reader_service.openvpn_socket_path(profile_key)


def _query_openvpn_management_socket(socket_path, command, max_response_bytes=0):
    return openvpn_socket_reader_service.query_openvpn_management_socket(
        socket_path,
        command,
        max_response_bytes=max_response_bytes,
    )


def _extract_status_payload_from_management(raw):
    return openvpn_socket_reader_service.extract_status_payload_from_management(raw)


def _extract_event_payload_from_management(raw):
    return openvpn_socket_reader_service.extract_event_payload_from_management(raw)


def _read_status_source(profile_key, fallback_path):
    return openvpn_socket_reader_service.read_status_source(profile_key, fallback_path)


def _read_event_source(profile_key, fallback_path):
    return openvpn_socket_reader_service.read_event_source(profile_key, fallback_path)


def _persist_peer_info_cache(event_rows):
    return peer_info_cache_service.persist_peer_info_cache(event_rows)


def _prune_peer_info_history():
    return peer_info_cache_service.prune_peer_info_history()


def _load_peer_info_cache_map(include_stale=False):
    return peer_info_cache_service.load_peer_info_cache_map(include_stale=include_stale)


def _load_peer_info_history_map(include_stale=False):
    return peer_info_cache_service.load_peer_info_history_map(include_stale=include_stale)


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
    return peer_info_cache_service.human_device_type(platform)


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
    return client_protocol_catalog_service.extract_client_name_from_config_file(file_path)


def _collect_existing_config_client_names():
    return client_protocol_catalog_service.collect_existing_config_client_names()


def _collect_config_protocols_by_client():
    return client_protocol_catalog_service.collect_config_protocols_by_client()


def _collect_sample_protocols_by_client():
    return client_protocol_catalog_service.collect_sample_protocols_by_client()


def _split_persisted_traffic_rows_by_config(persisted_rows):
    return client_protocol_catalog_service.split_persisted_traffic_rows_by_config(persisted_rows)


def _build_session_key(profile, client):
    return traffic_persistence_service.build_session_key(profile, client)


def _is_retryable_snapshot_integrity_error(exc):
    return traffic_persistence_service.is_retryable_snapshot_integrity_error(exc)


def _persist_traffic_snapshot(status_rows, _retry_on_integrity=True):
    return traffic_persistence_service.persist_traffic_snapshot(status_rows, retry_on_integrity=_retry_on_integrity)


def _protocol_label_from_type(protocol_type):
    return traffic_persistence_service.protocol_label_from_type(protocol_type)


def _ensure_protocol_traffic_stats_backfilled(now=None):
    return traffic_persistence_service.ensure_protocol_traffic_stats_backfilled(now=now)


def _collect_persisted_traffic_data(active_names=None, active_protocol_identities=None):
    return traffic_persistence_service.collect_persisted_traffic_data(active_names=active_names, active_protocol_identities=active_protocol_identities)


def _delete_client_traffic_stats(common_name):
    return traffic_persistence_service.delete_client_traffic_stats(common_name)

def _normalize_wireguard_allowed_ip(token):
    return network_status_collector_service.normalize_wireguard_allowed_ip(token)


def _split_wireguard_allowed_ips(value):
    return network_status_collector_service.split_wireguard_allowed_ips(value)


def _extract_ip_from_wireguard_endpoint(endpoint):
    return network_status_collector_service.extract_ip_from_wireguard_endpoint(endpoint)


def _parse_wireguard_config_peer_rows(config_path, interface_name):
    return network_status_collector_service.parse_wireguard_config_peer_rows(config_path, interface_name)


def _sync_wireguard_peer_cache_from_configs(force=False):
    return network_status_collector_service.sync_wireguard_peer_cache_from_configs(force=force)


def _load_wireguard_peer_cache_maps():
    return network_status_collector_service.load_wireguard_peer_cache_maps()


def _is_wireguard_peer_active(latest_handshake_ts):
    return network_status_collector_service.is_wireguard_peer_active(latest_handshake_ts)


def _collect_wireguard_status_rows():
    return network_status_collector_service.collect_wireguard_status_rows()


def _collect_status_rows_for_snapshot():
    return network_status_collector_service.collect_status_rows_for_snapshot()


def _parse_status_log(profile_key, filename):
    return network_status_collector_service.parse_status_log(profile_key, filename)


def _parse_event_log(profile_key, filename):
    return network_status_collector_service.parse_event_log(profile_key, filename)

def _collect_logs_dashboard_data():
    return collect_logs_dashboard_data_service(
        app=app,
        db=db,
        _collect_status_rows_for_snapshot=_collect_status_rows_for_snapshot,
        _persist_traffic_snapshot=_persist_traffic_snapshot,
        _parse_event_log=_parse_event_log,
        EVENT_LOG_FILES=EVENT_LOG_FILES,
        _persist_peer_info_cache=_persist_peer_info_cache,
        _load_peer_info_history_map=_load_peer_info_history_map,
        _load_peer_info_cache_map=_load_peer_info_cache_map,
        _collect_persisted_traffic_data=_collect_persisted_traffic_data,
        _split_persisted_traffic_rows_by_config=_split_persisted_traffic_rows_by_config,
        _collect_config_protocols_by_client=_collect_config_protocols_by_client,
        _collect_sample_protocols_by_client=_collect_sample_protocols_by_client,
        _normalize_traffic_protocol_type=_normalize_traffic_protocol_type,
        _protocol_label_from_type=_protocol_label_from_type,
        _openvpn_socket_path=_openvpn_socket_path,
        _human_bytes=_human_bytes,
        _human_device_type=_human_device_type,
        _normalize_openvpn_endpoint=_normalize_openvpn_endpoint,
    )


register_all_routes(app, sock, locals())


