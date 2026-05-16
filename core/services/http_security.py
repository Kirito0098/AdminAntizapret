"""Security headers and crawl policy for the admin panel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

NOINDEX_PATH_PREFIXES = (
    "/login",
    "/qr_download/",
    "/public_download/",
    "/captcha.png",
    "/auth/",
    "/ip_blocked",
)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self'; "
    "object-src 'none'; "
    "script-src 'self' https://telegram.org https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline'; "
    "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-src https://oauth.telegram.org https://telegram.org;"
)


def should_noindex_path(path: str) -> bool:
    if not path:
        return False
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in NOINDEX_PATH_PREFIXES)


def apply_security_headers(response, path: str) -> None:
    """Apply headers that reduce deceptive-site heuristics and harden the panel."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)

    if should_noindex_path(path):
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")


def build_robots_txt() -> str:
    return """User-agent: *
Disallow: /login
Disallow: /qr_download/
Disallow: /public_download/
Disallow: /generate_one_time_download/
Disallow: /download/
Disallow: /captcha.png
Disallow: /auth/
Disallow: /ip_blocked
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
