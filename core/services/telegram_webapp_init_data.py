"""Проверка Telegram.WebApp.initData по документации Telegram Bot API (Mini Apps).

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Алгоритм:
1. Разобрать query-string в пары ключ-значение.
2. Собрать data_check_string из всех пар, **кроме** ``hash``, в алфавитном порядке
   ключей, формат ``key=value``, разделитель — символ перевода строки ``\\n``.
3. ``secret_key = HMAC_SHA256(key=WebAppData, msg=bot_token)`` (константа ``WebAppData`` — ключ).
4. Сравнить ``hash`` из initData с ``hex(HMAC_SHA256(key=secret_key, msg=data_check_string))``.

Из строки для HMAC исключается только поле ``hash``. Остальные поля из ``initData``
(включая ``signature``, если его прислал клиент) участвуют в подписи так же, как в
официальных клиентах Telegram — иначе проверка не совпадает с переданным ``hash``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

# Только hash не входит в data_check_string; остальные пары — как у Telegram.
_INIT_DATA_HASH_ONLY_KEYS = frozenset({"hash"})


def verify_telegram_webapp_init_data(
    init_data_raw: str,
    *,
    bot_token: str,
    max_age_seconds: int,
) -> tuple[bool, str | None, dict[str, str] | None]:
    """
    Проверяет целостность и срок действия ``initData``.

    Возвращает ``(True, None, enriched_payload)`` или ``(False, error_message, None)``.
    В enriched_payload добавлены ключи ``id``, ``telegram_username``, ``telegram_display_name``
    для совместимости с существующим кодом авторизации.
    """
    if not (bot_token or "").strip():
        return False, "Telegram авторизация не настроена (нет токена бота).", None

    init_data = (init_data_raw or "").strip()
    if not init_data:
        return False, "Отсутствуют initData Telegram Mini App.", None

    try:
        payload: dict[str, str] = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return False, "Некорректный формат initData Telegram Mini App.", None

    received_hash = (payload.get("hash") or "").strip()
    auth_date_raw = (payload.get("auth_date") or "").strip()
    if not received_hash or not auth_date_raw:
        return False, "Некорректные данные Telegram Mini App авторизации.", None

    if not auth_date_raw.isdigit():
        return False, "Некорректная дата Telegram Mini App авторизации.", None

    auth_date = int(auth_date_raw)
    max_age = max(30, min(int(max_age_seconds or 300), 86400))
    now_ts = int(time.time())
    if abs(now_ts - auth_date) > max_age:
        return False, "Время Telegram Mini App авторизации истекло. Повторите вход.", None

    check_pairs = {k: v for k, v in payload.items() if k not in _INIT_DATA_HASH_ONLY_KEYS}
    data_check_string = "\n".join(f"{k}={check_pairs[k]}" for k in sorted(check_pairs.keys()))

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    received_norm = received_hash.lower()
    expected_norm = expected_hash.lower()
    if len(received_norm) != len(expected_norm) or not hmac.compare_digest(
        expected_norm, received_norm
    ):
        return False, "Проверка подписи Telegram Mini App не пройдена.", None

    telegram_id = (payload.get("id") or "").strip()
    telegram_username = ""
    telegram_display_name = ""
    user_raw = payload.get("user")
    if user_raw:
        try:
            user_payload: dict[str, Any] = json.loads(user_raw)
            if not telegram_id:
                telegram_id = str(user_payload.get("id") or "").strip()
            telegram_username = str(user_payload.get("username") or "").strip()
            first_name = str(user_payload.get("first_name") or "").strip()
            last_name = str(user_payload.get("last_name") or "").strip()
            telegram_display_name = " ".join(
                part for part in (first_name, last_name) if part
            ).strip()
        except Exception:
            telegram_username = ""
            telegram_display_name = ""

    if not telegram_id:
        return False, "В initData отсутствует Telegram ID пользователя.", None

    enriched = dict(payload)
    enriched["id"] = telegram_id
    enriched["telegram_username"] = telegram_username
    enriched["telegram_display_name"] = telegram_display_name
    return True, None, enriched
