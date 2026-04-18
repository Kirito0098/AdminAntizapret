from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

_DEV_ENV_VALUES = {"dev", "development", "local", "test", "testing"}
_ALLOWED_SAMESITE_VALUES = {"Lax", "Strict", "None"}


def parse_bool_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clamp_int_env(
    value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int((value or "").strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def normalize_samesite(value: str | None, *, secure_cookie: bool) -> str:
    normalized = (value or "Lax").strip().capitalize()
    if normalized not in _ALLOWED_SAMESITE_VALUES:
        return "Lax"

    # SameSite=None без Secure отклоняется современными браузерами.
    if normalized == "None" and not secure_cookie:
        return "Lax"

    return normalized


def build_session_security_config(environ: Mapping[str, str]) -> dict[str, Any]:
    app_env = (environ.get("APP_ENV") or environ.get("FLASK_ENV") or "").strip().lower()
    use_https_raw = environ.get("USE_HTTPS")
    has_explicit_https_flag = use_https_raw is not None
    has_ssl_material = bool(
        (environ.get("SSL_CERT") or "").strip()
        and (environ.get("SSL_KEY") or "").strip()
    )

    if has_explicit_https_flag:
        default_secure_cookie = parse_bool_env(use_https_raw, default=False)
    elif has_ssl_material:
        default_secure_cookie = True
    elif app_env in _DEV_ENV_VALUES:
        default_secure_cookie = False
    else:
        # Для старых HTTP-инсталляций без USE_HTTPS избегаем silent регрессии логина.
        default_secure_cookie = False

    session_cookie_secure = parse_bool_env(
        environ.get("SESSION_COOKIE_SECURE"),
        default=default_secure_cookie,
    )
    same_site = normalize_samesite(
        environ.get("SESSION_COOKIE_SAMESITE"),
        secure_cookie=session_cookie_secure,
    )
    remember_me_days = clamp_int_env(
        environ.get("REMEMBER_ME_DAYS"),
        default=30,
        minimum=1,
        maximum=365,
    )
    session_lifetime_days = clamp_int_env(
        environ.get("PERMANENT_SESSION_LIFETIME_DAYS"),
        default=remember_me_days,
        minimum=1,
        maximum=365,
    )

    cookie_name = (environ.get("SESSION_COOKIE_NAME") or "").strip() or "AdminAntizapretSession"
    cookie_domain = (environ.get("SESSION_COOKIE_DOMAIN") or "").strip()

    config: dict[str, Any] = {
        "SESSION_COOKIE_NAME": cookie_name,
        "SESSION_COOKIE_PATH": "/",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": same_site,
        "SESSION_COOKIE_SECURE": session_cookie_secure,
        "REMEMBER_COOKIE_HTTPONLY": True,
        "REMEMBER_COOKIE_SAMESITE": same_site,
        "REMEMBER_COOKIE_SECURE": session_cookie_secure,
        "REMEMBER_COOKIE_DURATION": timedelta(days=remember_me_days),
        "PERMANENT_SESSION_LIFETIME": timedelta(days=session_lifetime_days),
        "SESSION_REFRESH_EACH_REQUEST": False,
        "REMEMBER_ME_DAYS": remember_me_days,
        "WTF_CSRF_SSL_STRICT": parse_bool_env(
            environ.get("WTF_CSRF_SSL_STRICT"),
            default=session_cookie_secure,
        ),
    }

    if cookie_domain:
        config["SESSION_COOKIE_DOMAIN"] = cookie_domain

    return config
