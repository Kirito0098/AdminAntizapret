"""Security headers and crawl policy for the admin panel."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

try:  # Flask доступен в рантайме приложения, но модуль должен импортироваться и без него.
    from flask import g, has_request_context
except Exception:  # pragma: no cover - defensive
    g = None

    def has_request_context() -> bool:
        return False

NOINDEX_PATH_PREFIXES = (
    "/",
    "/login",
    "/settings",
    "/routing",
    "/server_monitor",
    "/logs_dashboard",
    "/edit-files",
    "/feature-disabled",
    "/tg-mini",
    "/qr_download/",
    "/public_download/",
    "/captcha.png",
    "/auth/",
    "/ip-blocked",
    "/api/",
)

_CSP_NONCE_ATTR = "_csp_nonce"


def get_csp_nonce() -> str:
    """Возвращает per-request CSP nonce, создавая его при первом обращении.

    Один и тот же объект запроса (flask.g) гарантирует, что nonce в заголовке
    Content-Security-Policy совпадёт с nonce, проброшенным в шаблоны через
    context processor. Вне контекста запроса возвращает пустую строку.
    """
    if g is None or not has_request_context():
        return ""
    nonce = getattr(g, _CSP_NONCE_ATTR, None)
    if not nonce:
        nonce = secrets.token_urlsafe(16)
        setattr(g, _CSP_NONCE_ATTR, nonce)
    return nonce


def build_content_security_policy(nonce: str | None = None) -> str:
    """Собирает CSP. При наличии nonce script-src использует его вместо
    'unsafe-inline' (браузеры игнорируют 'unsafe-inline' при наличии nonce)."""
    script_src = "script-src 'self' https://telegram.org https://cdn.jsdelivr.net"
    if nonce:
        script_src += f" 'nonce-{nonce}'"
    else:
        # Без активного запроса (например, в тестах или фоновых ответах без
        # рендера шаблонов) nonce не нужен — inline-скриптов в таких ответах нет.
        script_src += " 'nonce-disabled'"
    return (
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        f"{script_src}; "
        # style-src сохраняет 'unsafe-inline': inline style="" атрибуты широко
        # используются в шаблонах; перевод на nonce/hash отложен (см. отчёт).
        "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-src https://oauth.telegram.org https://telegram.org;"
    )


# Backward-compatible статический CSP (без nonce) для возможных внешних импортов.
CONTENT_SECURITY_POLICY = build_content_security_policy()


def should_noindex_path(path: str) -> bool:
    if not path:
        return False
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in NOINDEX_PATH_PREFIXES)


def apply_security_headers(response, path: str, nonce: str | None = None) -> None:
    """Apply headers that reduce deceptive-site heuristics and harden the panel."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    if nonce is None:
        nonce = get_csp_nonce()
    response.headers.setdefault("Content-Security-Policy", build_content_security_policy(nonce))

    if should_noindex_path(path):
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")


def build_robots_txt() -> str:
    return """User-agent: *
Disallow: /
Disallow: /login
Disallow: /settings
Disallow: /routing
Disallow: /server_monitor
Disallow: /logs_dashboard
Disallow: /edit-files
Disallow: /feature-disabled
Disallow: /qr_download/
Disallow: /public_download/
Disallow: /generate_one_time_download/
Disallow: /download/
Disallow: /captcha.png
Disallow: /auth/
Disallow: /ip-blocked
Disallow: /tg-mini
Disallow: /api/
"""


def build_security_txt(branding: Mapping[str, Any] | None = None) -> str:
    """RFC 9116 contact file — neutral wording (no service type hints for crawlers)."""
    info = dict(branding or get_panel_branding())
    panel_url = info.get("panel_base_url") or "https://localhost"
    return (
        f"Contact: {panel_url}\n"
        "Preferred-Languages: ru, en\n"
        f"Canonical: {panel_url}\n"
        "Policy: Private administration panel. Authorized access only. Not a bank or email login.\n"
    )


def get_panel_branding(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Branding for login / one-time download — only the admin panel host (DOMAIN), no external site."""
    import os

    getter = environ if environ is not None else os.environ
    domain = (getter.get("DOMAIN", "") or "").strip()
    brand = (getter.get("PANEL_BRAND_NAME", "") or "").strip() or "Admin Panel"
    panel_base_url = None
    if domain:
        host = domain.split(":")[0]
        panel_base_url = f"https://{host}"
    return {
        "panel_brand_name": brand,
        "panel_host": domain or None,
        "panel_base_url": panel_base_url,
    }
