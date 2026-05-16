from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import jsonify, redirect, url_for
from werkzeug.wrappers.response import Response

TELEGRAM_MINI_API_DENIED_MESSAGE = "Доступ к Mini App API разрешён только из Telegram Mini App."


def has_telegram_mini_session(session_obj: Mapping[str, Any]) -> bool:
    username = str(session_obj.get("username") or "").strip()
    mini_username = str(session_obj.get("telegram_mini_username") or "").strip()
    mini_auth = bool(session_obj.get("telegram_mini_auth"))
    return bool(mini_auth and mini_username and mini_username == username)


def enforce_telegram_mini_session(
    session_obj: Mapping[str, Any],
    *,
    api_request: bool = True,
    redirect_endpoint: str = "tg_mini_open",
    denied_message: str = TELEGRAM_MINI_API_DENIED_MESSAGE,
) -> tuple[Response, int] | Response | None:
    if has_telegram_mini_session(session_obj):
        return None

    if api_request:
        return jsonify({"success": False, "message": denied_message}), 403

    return redirect(url_for(redirect_endpoint))
