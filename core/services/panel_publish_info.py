"""Сводка по публикации веб-панели (порт, HTTPS, Nginx / reverse proxy)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from core.services.session_security import parse_bool_env


def _basename(path: str) -> str:
    value = (path or "").strip()
    if not value:
        return "—"
    return os.path.basename(value)


def build_panel_publish_context(*, get_env_value, url_root: str | None) -> dict:
    """
    Строит данные для блока «как открыта панель» в настройках.

    get_env_value — как в маршрутах настроек (чтение .env / окружения).
    url_root — request.url_root из Flask (схема и хост текущего запроса).
    """

    def gv(key: str, default: str = "") -> str:
        return str(get_env_value(key, default) or default or "").strip()

    bind = gv("BIND", "0.0.0.0") or "0.0.0.0"
    port = gv("APP_PORT", "5050") or "5050"
    use_https = parse_bool_env(gv("USE_HTTPS", "false"), default=False)
    domain = gv("DOMAIN", "")
    cert = gv("SSL_CERT", "")
    key = gv("SSL_KEY", "")
    cookie_secure = parse_bool_env(gv("SESSION_COOKIE_SECURE", "false"), default=False)
    trusted = gv("TRUSTED_PROXY_IPS", "")

    loopback = bind in {"127.0.0.1", "localhost", "::1"}
    has_ssl_material = bool(cert and key)

    internal_scheme = "https" if use_https else "http"
    internal_url = f"{internal_scheme}://{bind}:{port}/"

    parsed = urlparse(url_root or "")
    current_url = ""
    if parsed.scheme and parsed.netloc:
        current_url = f"{parsed.scheme}://{parsed.netloc}/"

    primary_urls: list[dict[str, str]] = []
    if current_url:
        primary_urls.append({"label": "Текущий адрес в браузере", "url": current_url.rstrip("/") + "/"})

    bullet_points: list[str] = []

    if use_https:
        if has_ssl_material:
            mode_key = "app_https"
            mode_title = "HTTPS на стороне приложения (Gunicorn)"
            bullet_points.append("TLS завершает сам процесс панели; в .env заданы SSL_CERT и SSL_KEY.")
            bullet_points.append(f"Слушает: <code>{internal_url}</code> (см. BIND и APP_PORT).")
            if not current_url:
                bullet_points.append(f"Обычно панель открывают как <code>https://&lt;хост&gt;:{port}/</code>.")
        else:
            mode_key = "app_https_incomplete"
            mode_title = "HTTPS включён, сертификаты не настроены"
            bullet_points.append("USE_HTTPS=true, но не заданы оба пути SSL_CERT и SSL_KEY — проверьте .env и перезапуск службы.")
    elif loopback:
        mode_key = "reverse_proxy"
        mode_title = "За reverse proxy (часто Nginx + HTTPS)"
        bullet_points.append(
            "Приложение слушает только loopback — снаружи доступ обычно через Nginx или другой прокси с TLS."
        )
        bullet_points.append(f"Внутренний upstream: <code>http://{bind}:{port}/</code> (proxy_pass к APP_PORT).")
        if domain:
            guess = f"https://{domain}/"
            primary_urls.append({"label": "Типичный публичный URL (HTTPS на nginx, порты 80/443)", "url": guess})
            bullet_points.append(
                f"В .env указан DOMAIN — ожидаемый внешний адрес: <code>{guess}</code> (если nginx на стандартном 443, порт в URL не указывается)."
            )
        else:
            bullet_points.append(
                "DOMAIN в .env пуст — внешний URL зависит от конфига nginx; ориентируйтесь на адрес, по которому заходите сейчас."
            )
        if cookie_secure:
            bullet_points.append("SESSION_COOKIE_SECURE=true — типично для схемы «HTTPS снаружи, HTTP внутри».")
        if trusted:
            bullet_points.append(f"Доверенные прокси (TRUSTED_PROXY_IPS): <code>{trusted}</code>.")
    else:
        mode_key = "direct_http"
        mode_title = "Прямой HTTP к приложению"
        bullet_points.append(f"Панель слушает <code>http://{bind}:{port}/</code> без TLS на этом уровне (BIND не loopback).")
        bullet_points.append("Если снаружи используется HTTPS, его завершает другой узел — это не отражено в USE_HTTPS данного сервиса.")

    env_rows = [
        {"label": "APP_PORT (порт процесса панели)", "value": port, "mono": True},
        {"label": "BIND", "value": bind, "mono": True},
        {"label": "USE_HTTPS (TLS в Gunicorn)", "value": "да" if use_https else "нет", "mono": False},
        {"label": "DOMAIN (для nginx / подсказок)", "value": domain or "—", "mono": bool(domain)},
        {"label": "SESSION_COOKIE_SECURE", "value": "да" if cookie_secure else "нет", "mono": False},
        {"label": "TRUSTED_PROXY_IPS", "value": trusted or "—", "mono": True},
        {"label": "SSL_CERT (файл)", "value": _basename(cert), "mono": True},
        {"label": "SSL_KEY (файл)", "value": _basename(key), "mono": True},
    ]

    dedup_urls: list[dict[str, str]] = []
    seen_url: set[str] = set()
    for entry in primary_urls:
        u = entry.get("url") or ""
        if not u or u in seen_url:
            continue
        seen_url.add(u)
        dedup_urls.append(entry)

    return {
        "mode_key": mode_key,
        "mode_title": mode_title,
        "bullet_points": bullet_points,
        "primary_urls": dedup_urls,
        "internal_url": internal_url,
        "env_rows": env_rows,
    }
