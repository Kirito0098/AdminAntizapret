from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Callable

from flask import Request


def run_io_bound(io_executor, callback: Callable, *, timeout: int):
    if io_executor is None:
        return callback()

    future = io_executor.submit(callback)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError as e:
        raise ValueError("Операция Telegram API превысила лимит ожидания") from e


def telegram_bot_api_json(
    io_executor,
    bot_token: str,
    method_name: str,
    params: dict | None = None,
    timeout: int = 20,
) -> dict:
    api_url = f"https://api.telegram.org/bot{bot_token}/{method_name}"
    payload = urllib.parse.urlencode(params or {}).encode("utf-8")
    request_obj = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    def _request_callback():
        with urllib.request.urlopen(request_obj, timeout=timeout) as response:
            return response.read()

    try:
        response_bytes = run_io_bound(io_executor, _request_callback, timeout=max(timeout + 2, 5))
    except urllib.error.HTTPError as e:
        error_payload_raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        try:
            error_payload = json.loads(error_payload_raw) if error_payload_raw else {}
        except (TypeError, ValueError):
            error_payload = {}
        message = error_payload.get("description") or f"Telegram API error: HTTP {e.code}"
        raise ValueError(message)
    except urllib.error.URLError as e:
        raise ValueError(f"Не удалось связаться с Telegram API: {e}")

    try:
        parsed = json.loads(response_bytes.decode("utf-8", errors="replace"))
    except ValueError:
        raise ValueError("Telegram API вернул некорректный ответ")

    if not parsed.get("ok"):
        raise ValueError(parsed.get("description") or "Telegram API вернул ошибку")

    return parsed


def normalize_device_platform(raw_platform):
    value = (raw_platform or "").strip().lower()
    if value in {"android", "apple", "windows"}:
        return value
    if value in {"ios", "iphone", "ipad", "mac", "macos"}:
        return "apple"
    return ""


def detect_device_platform(request: Request, raw_platform):
    normalized = normalize_device_platform(raw_platform)
    if normalized:
        return normalized

    ua = (request.headers.get("User-Agent") or "").lower()
    if "android" in ua:
        return "android"
    if any(token in ua for token in ("iphone", "ipad", "ios", "mac os x", "macintosh")):
        return "apple"
    if any(token in ua for token in ("windows", "win64", "win32")):
        return "windows"
    return "unknown"


def normalize_config_kind(file_type_hint, file_path, file_name, get_config_type):
    kind_raw = (file_type_hint or "").strip().lower()
    kind_map = {
        "openvpn": "openvpn",
        "wg": "wireguard",
        "wireguard": "wireguard",
        "amneziawg": "amneziawg",
    }

    if kind_raw in kind_map:
        return kind_map[kind_raw]

    detected = (get_config_type(file_path) or "").strip().lower() if file_path else ""
    if detected in kind_map:
        return kind_map[detected]

    name = (file_name or "").strip().lower()
    if name.endswith(".ovpn"):
        return "openvpn"
    if name.endswith(".conf"):
        return "wireguard"

    return "openvpn"


def build_short_download_name(file_path: str) -> str:
    base = os.path.basename(file_path)
    pattern = re.compile(
        r"^(?P<prefix>antizapret|vpn)-(?P<client>[\w\-]+?)(?:_(?P<id>[\w\-]+))?(?:-\([^)]+\))?(?:-(?P<proto>udp|tcp))?(?:-(?P<suffix>wg|am))?\.(?P<ext>ovpn|conf)$",
        re.IGNORECASE,
    )
    match = pattern.match(base)

    if not match:
        return base

    prefix = (match.group("prefix") or "").lower()
    client = match.group("client") or "client"
    profile_id = match.group("id")
    proto = match.group("proto")
    ext = (match.group("ext") or "conf").lower()

    prefix_out = "az" if prefix == "antizapret" else "vpn"
    base_name = f"{prefix_out}-{client}_{profile_id}" if profile_id else f"{prefix_out}-{client}"
    if proto:
        return f"{base_name}-{proto}.{ext}"
    return f"{base_name}.{ext}"


def build_platform_instruction_caption(file_name, device_platform, config_kind):
    name = file_name or "config.ovpn"
    platform = (device_platform or "unknown").lower()
    kind = (config_kind or "openvpn").lower()

    lines = [f"📦 Ваш конфиг: {name}"]

    if kind == "wireguard":
        if platform == "android":
            lines.extend(
                [
                    "🛡 Клиент: WireGuard (Android)",
                    "🔗 Скачать: https://play.google.com/store/apps/details?id=com.wireguard.android",
                    "1) Установите WireGuard из Google Play.",
                    "2) В Telegram откройте файл .conf.",
                    "3) Выберите WireGuard в меню Открыть с помощью.",
                    "4) Нажмите Import и активируйте туннель.",
                ]
            )
        elif platform == "apple":
            lines.extend(
                [
                    "🛡 Клиент: WireGuard (iPhone/iPad)",
                    "🔗 Скачать: https://apps.apple.com/app/wireguard/id1441195209",
                    "1) Установите WireGuard из App Store.",
                    "2) В Telegram нажмите Поделиться -> Открыть в WireGuard.",
                    "3) Подтвердите Import tunnel.",
                    "4) Включите туннель переключателем Activate.",
                ]
            )
        elif platform == "windows":
            lines.extend(
                [
                    "🛡 Клиент: WireGuard (Windows)",
                    "🔗 Скачать: https://www.wireguard.com/install/",
                    "1) Установите WireGuard для Windows.",
                    "2) Откройте Import tunnel(s) from file.",
                    "3) Выберите полученный .conf файл.",
                    "4) Нажмите Activate для подключения.",
                ]
            )
        else:
            lines.extend(
                [
                    "🛡 Клиент: WireGuard",
                    "🔗 Сайт: https://www.wireguard.com/install/",
                    "1) Установите приложение WireGuard.",
                    "2) Импортируйте этот .conf файл.",
                    "3) Активируйте созданный туннель.",
                ]
            )

    elif kind == "amneziawg":
        if platform == "android":
            lines.extend(
                [
                    "🛰 Клиент: AmneziaVPN (Android)",
                    "🔗 Сайт: https://play.google.com/store/apps/details?id=org.amnezia.awg",
                    "1) Установите AmneziaVPN на Android.",
                    "2) Откройте .conf из Telegram.",
                    "3) Выберите Импорт в AmneziaVPN.",
                    "4) Включите профиль подключения.",
                ]
            )
        elif platform == "apple":
            lines.extend(
                [
                    "🛰 Клиент: AmneziaVPN (iPhone/iPad)",
                    "🔗 Сайт: https://apps.apple.com/ru/app/amneziawg/id6478942365",
                    "1) Установите AmneziaVPN на iOS.",
                    "2) В Telegram нажмите Поделиться -> Открыть в AmneziaVPN.",
                    "3) Подтвердите импорт профиля.",
                    "4) Включите подключение в приложении.",
                ]
            )
        elif platform == "windows":
            lines.extend(
                [
                    "🛰 Клиент: AmneziaVPN (Windows)",
                    "🔗 Сайт: https://github.com/amnezia-vpn/amneziawg-windows-client/releases",
                    "1) Установите клиент AmneziaVPN для Windows.",
                    "2) Импортируйте полученный .conf файл.",
                    "3) Выберите профиль в списке.",
                    "4) Запустите подключение кнопкой Connect.",
                ]
            )
        else:
            lines.extend(
                [
                    "🛰 Клиент: AmneziaVPN",
                    "🔗 Сайт: https://github.com/amnezia-vpn",
                    "1) Установите клиент AmneziaVPN.",
                    "2) Импортируйте этот .conf файл.",
                    "3) Активируйте профиль подключения.",
                ]
            )

    else:
        if platform == "android":
            lines.extend(
                [
                    "🔐 Клиент: OpenVPN Connect (Android)",
                    "🔗 Скачать: https://play.google.com/store/apps/details?id=net.openvpn.openvpn",
                    "1) Установите OpenVPN Connect из Google Play.",
                    "2) Откройте файл .ovpn из Telegram.",
                    "3) Выберите OpenVPN Connect.",
                    "4) Нажмите Add/Connect для подключения.",
                ]
            )
        elif platform == "apple":
            lines.extend(
                [
                    "🔐 Клиент: OpenVPN Connect (iPhone/iPad)",
                    "🔗 Скачать: https://apps.apple.com/app/openvpn-connect-openvpn-app/id590379981",
                    "1) Установите OpenVPN Connect из App Store.",
                    "2) В Telegram: Поделиться -> Открыть в OpenVPN.",
                    "3) Импортируйте профиль.",
                    "4) Нажмите Connect для подключения.",
                ]
            )
        elif platform == "windows":
            lines.extend(
                [
                    "🔐 Клиент: OpenVPN Connect (Windows)",
                    "🔗 Скачать: https://openvpn.net/client/client-connect-vpn-for-windows/",
                    "1) Установите OpenVPN Connect для Windows.",
                    "2) Нажмите Import Profile и выберите .ovpn.",
                    "3) Сохраните профиль.",
                    "4) Нажмите Connect для запуска VPN.",
                ]
            )
        else:
            lines.extend(
                [
                    "🔐 Клиент: OpenVPN Connect",
                    "🔗 Сайт: https://openvpn.net/client/",
                    "1) Установите OpenVPN Connect.",
                    "2) Импортируйте этот .ovpn файл.",
                    "3) Запустите подключение кнопкой Connect.",
                ]
            )

    lines.append("💡 Если импорт не открывается: сначала сохраните файл в Папку Файлы и импортируйте вручную.")
    caption = "\n".join(lines)

    if len(caption) > 1000:
        caption = caption[:997].rstrip() + "..."

    return caption


def send_document_via_telegram_bot(
    io_executor,
    bot_token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    telegram_filename: str = "",
) -> dict:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    filename = (telegram_filename or "").strip() or os.path.basename(file_path)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    with open(file_path, "rb") as src:
        file_bytes = src.read()

    boundary = f"----AdminAntizapret{hashlib.md5(os.urandom(16)).hexdigest()}"
    body = bytearray()

    def _append_field(name, value):
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    _append_field("chat_id", chat_id)
    if caption:
        _append_field("caption", caption)

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    request_obj = urllib.request.Request(
        api_url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    def _upload_callback():
        with urllib.request.urlopen(request_obj, timeout=35) as response:
            return response.read()

    try:
        response_bytes = run_io_bound(io_executor, _upload_callback, timeout=40)
    except urllib.error.HTTPError as e:
        error_payload_raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        try:
            error_payload = json.loads(error_payload_raw) if error_payload_raw else {}
        except (TypeError, ValueError):
            error_payload = {}
        message = error_payload.get("description") or f"Telegram API error: HTTP {e.code}"
        raise ValueError(message)
    except urllib.error.URLError as e:
        raise ValueError(f"Не удалось связаться с Telegram API: {e}")

    try:
        payload = json.loads(response_bytes.decode("utf-8", errors="replace"))
    except ValueError:
        raise ValueError("Telegram API вернул некорректный ответ")

    if not payload.get("ok"):
        raise ValueError(payload.get("description") or "Telegram API вернул ошибку")

    return payload


def check_viewer_config_access(user, file_path, viewer_config_access_model, get_config_type):
    if not user or user.role != "viewer":
        return None

    cfg_type = get_config_type(file_path)
    if cfg_type not in ("openvpn", "wg", "amneziawg"):
        return "Доступ запрещён"

    cfg_name = os.path.basename(file_path)
    access = viewer_config_access_model.query.filter_by(
        user_id=user.id,
        config_type=cfg_type,
        config_name=cfg_name,
    ).first()
    if not access:
        return "Доступ к конфигу запрещён"
    return None
