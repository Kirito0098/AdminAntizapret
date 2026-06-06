"""Application factory для AdminAntiZapret.

Отделяет конфигурацию и инициализацию расширений (Flask, SQLAlchemy, CSRF,
WebSocket, rate limiter, WAL-режим SQLite) от регистрации сервисов и роутов,
которые остаются в app.py. Gunicorn по-прежнему запускает объект `app:app`,
который app.py создаёт через create_app() на уровне модуля.
"""

import os
import sqlite3 as _sqlite3

from flask import Flask, request
from flask_sock import Sock
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event as _sa_event
from sqlalchemy.engine import Engine as _SAEngine

from core.models import db
from core.services.session_security import build_session_security_config
from utils.ip_restriction import ip_restriction

try:
    from flask_limiter import Limiter
except ImportError:
    Limiter = None

# Абсолютный путь к корню приложения (каталог с app.py / templates / static).
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@_sa_event.listens_for(_SAEngine, "connect")
def _set_sqlite_wal(dbapi_conn, _conn_record):
    """WAL-режим SQLite — позволяет читать БД во время длинных write-транзакций."""
    if isinstance(dbapi_conn, _sqlite3.Connection):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def _get_client_ip():
    """Единая точка определения IP клиента с учётом TRUSTED_PROXY_IPS."""
    try:
        return ip_restriction.get_client_ip() or (request.remote_addr or "127.0.0.1")
    except Exception:
        return request.remote_addr or "127.0.0.1"


def _rate_limit_key_func():
    # Доверяем X-Forwarded-For только от доверенных прокси (TRUSTED_PROXY_IPS),
    # иначе лимиты можно было бы обойти подменой заголовка.
    return _get_client_ip()


def _build_limiter(app):
    """Создаёт Flask-Limiter (если доступен) и логирует предупреждения о backend."""
    if Limiter is None:
        # Flask-Limiter не установлен: auth- и public-эндпоинты остаются без
        # rate limiting. Явно предупреждаем при старте, т.к. это риск brute-force.
        app.logger.warning(
            "Flask-Limiter недоступен — rate limiting ОТКЛЮЧЁН. Auth- и public-"
            "эндпоинты не защищены от перебора. Установите flask-limiter и при "
            "необходимости задайте RATELIMIT_STORAGE_URI."
        )
        return None

    # storage_uri настраивается через env (RATELIMIT_STORAGE_URI), чтобы в
    # production можно было указать общий backend (например Redis). По
    # умолчанию используется in-memory (подходит только для single-process).
    storage_uri = (os.getenv("RATELIMIT_STORAGE_URI") or "memory://").strip() or "memory://"
    limiter = Limiter(
        key_func=_rate_limit_key_func,
        app=app,
        default_limits=[],
        storage_uri=storage_uri,
    )
    if storage_uri.startswith("memory://"):
        app.logger.warning(
            "Rate limiting использует in-memory storage (memory://). Лимиты не "
            "разделяются между процессами/воркерами Gunicorn — в production "
            "укажите общий backend через RATELIMIT_STORAGE_URI (например Redis)."
        )
    return limiter


def create_app():
    """Создаёт и конфигурирует Flask-приложение и его расширения.

    Возвращает кортеж (app, sock, csrf, limiter). Регистрация сервисов и
    маршрутов выполняется в app.py после вызова этой фабрики.
    """
    app = Flask("app", root_path=APP_ROOT)

    app.secret_key = os.getenv("SECRET_KEY")
    if not app.secret_key:
        raise ValueError("SECRET_KEY is not set in .env!")
    app.config.update(build_session_security_config(os.environ))

    # Настройка БД
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"timeout": 30},
    }

    csrf = CSRFProtect(app)
    sock = Sock(app)
    ip_restriction.init_app(app)
    db.init_app(app)

    limiter = _build_limiter(app)
    return app, sock, csrf, limiter
