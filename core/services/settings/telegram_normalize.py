import ipaddress
import re


def normalize_telegram_id(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return "", None
    if not re.fullmatch(r"^[1-9][0-9]{4,20}$", value):
        return None, "Telegram ID должен содержать только цифры (5..21 символ) и не начинаться с 0"
    return value, None


def normalize_telegram_bot_username(raw_value):
    value = (raw_value or "").strip().lstrip("@")
    if not value:
        return "", None
    if not re.fullmatch(r"^[A-Za-z0-9_]{5,64}$", value):
        return None, "Username Telegram-бота должен содержать 5..64 символа: латиница, цифры, _"
    return value, None


def normalize_telegram_bot_token(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return "", None
    if not re.fullmatch(r"^[0-9]{6,12}:[A-Za-z0-9_-]{20,}$", value):
        return None, "Неверный формат токена Telegram-бота"
    return value, None


def normalize_ip_entry(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        if "/" in value:
            return str(ipaddress.ip_network(value, strict=False))
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def nightly_time_from_cron(cron_expr):
    value = (cron_expr or "").strip()
    parts = value.split()
    if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit():
        minute_value = int(parts[0])
        hour_value = int(parts[1])
        if 0 <= minute_value <= 59 and 0 <= hour_value <= 23:
            return f"{hour_value:02d}:{minute_value:02d}"
    return "04:00"
