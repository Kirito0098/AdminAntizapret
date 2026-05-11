import hashlib
import json
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Callable

from flask import (
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    render_template_string,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import case
from werkzeug.exceptions import HTTPException

from core.services.request_user import get_current_user
from core.services.telegram_mini_session import enforce_telegram_mini_session, has_telegram_mini_session


def register_config_routes(
    app,
    *,
    auth_manager,
    file_validator,
    db,
    user_model,
    viewer_config_access_model,
    qr_download_token_model,
    client_name_pattern,
    group_folders,
    result_dir_files,
    ensure_client_connect_ban_check_block,
    read_banned_clients,
    write_banned_clients,
    get_config_type,
    resolve_config_file,
    create_one_time_download_url,
    log_qr_event,
    qr_generator,
    file_editor,
    enqueue_background_task,
    task_run_doall,
    task_accepted_response,
    io_executor,
    set_env_value,
    get_public_download_enabled,
    set_public_download_enabled,
    log_telegram_audit_event,
    log_user_action_event,
) -> None:
    def _run_io_bound(callback: Callable, *, timeout: int):
        if io_executor is None:
            return callback()

        future = io_executor.submit(callback)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as e:
            raise ValueError("Операция Telegram API превысила лимит ожидания") from e

    def _build_short_download_name(file_path: str) -> str:
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

    def _has_telegram_mini_session() -> bool:
        return has_telegram_mini_session(session)

    def _enforce_telegram_mini_api_access():
        return enforce_telegram_mini_session(session, api_request=True)

    def _telegram_bot_api_json(
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
            response_bytes = _run_io_bound(_request_callback, timeout=max(timeout + 2, 5))
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

    def _normalize_device_platform(raw_platform):
        value = (raw_platform or "").strip().lower()
        if value in {"android", "apple", "windows"}:
            return value
        if value in {"ios", "iphone", "ipad", "mac", "macos"}:
            return "apple"
        return ""

    def _detect_device_platform(raw_platform):
        normalized = _normalize_device_platform(raw_platform)
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

    def _normalize_config_kind(file_type_hint, file_path, file_name):
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

    def _validate_editor_content(content):
        value = content or ""
        if "\x00" in value:
            return False, "Содержимое файла содержит недопустимый нулевой байт"
        if len(value.encode("utf-8")) > 1024 * 1024:
            return False, "Содержимое файла превышает допустимый размер 1 MiB"
        return True, ""

    def _build_platform_instruction_caption(file_name, device_platform, config_kind):
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

        # Telegram ограничивает подпись документа 1024 символами.
        if len(caption) > 1000:
            caption = caption[:997].rstrip() + "..."

        return caption

    def _send_document_via_telegram_bot(
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
            response_bytes = _run_io_bound(_upload_callback, timeout=40)
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

    @app.route("/api/openvpn/client-block", methods=["POST"])
    @auth_manager.admin_required
    def api_openvpn_client_block():
        client_name = request.form.get("client_name", "").strip()
        blocked_raw = (request.form.get("blocked", "").strip().lower())

        if not client_name_pattern.fullmatch(client_name):
            return jsonify({"success": False, "message": "Некорректный CN клиента."}), 400

        should_block = blocked_raw in {"1", "true", "yes", "on"}

        try:
            ensure_client_connect_ban_check_block()
            banned_clients = read_banned_clients()

            if should_block:
                banned_clients.add(client_name)
            else:
                banned_clients.discard(client_name)

            write_banned_clients(banned_clients)
            is_tg_mini_action = _has_telegram_mini_session()
            details_text = f"blocked={1 if should_block else 0}"
            if is_tg_mini_action:
                log_telegram_audit_event(
                    "mini_openvpn_block_toggle",
                    config_name=client_name,
                    details=details_text,
                )
                details_text += " via=tg-mini"

            log_user_action_event(
                "openvpn_client_block_toggle",
                target_type="openvpn",
                target_name=client_name,
                details=details_text,
            )
            return jsonify(
                {
                    "success": True,
                    "client_name": client_name,
                    "blocked": should_block,
                    "message": "Клиент заблокирован." if should_block else "Блокировка снята.",
                }
            )
        except PermissionError:
            return jsonify({"success": False, "message": "Нет прав на запись banned_clients."}), 500
        except OSError as e:
            return jsonify({"success": False, "message": f"Ошибка работы с banned_clients: {e}"}), 500

    @app.route("/set_openvpn_group", methods=["POST"])
    @auth_manager.login_required
    def set_openvpn_group():
        grp = request.form.get("group", "GROUP_UDP\\TCP")
        if grp not in group_folders:
            grp = "GROUP_UDP\\TCP"
        session["openvpn_group"] = grp
        return redirect(url_for("index"))

    @app.route("/qr_download/<token>", methods=["GET", "POST"])
    def one_time_qr_download(token):
        if not token or len(token) < 16:
            abort(404)

        now = datetime.utcnow()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        pin_page_tpl = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Введите PIN</title>
  <style>
    body { font-family: sans-serif; background: #101722; color: #e6edf3; margin: 0; }
    .wrap { max-width: 420px; margin: 60px auto; padding: 24px; border-radius: 12px; background: #162133; }
        h2 { margin-top: 0; }
    input { width: 100%; box-sizing: border-box; padding: 12px; border-radius: 8px; border: 1px solid #2d3d56; background: #0f1725; color: #fff; }
    button { margin-top: 12px; width: 100%; padding: 12px; border: none; border-radius: 8px; background: #2c84ff; color: #fff; cursor: pointer; }
    .hint { color: #9fb3c8; font-size: 0.92rem; margin-top: 8px; }
    .error { color: #ff8b8b; margin-top: 10px; }
  </style>
</head>
<body>
  <div class="wrap">
        <h2>PIN для скачивания</h2>
                <form method="POST" autocomplete="off">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
      <input type="password" name="pin" inputmode="numeric" pattern="[0-9]*" placeholder="Введите PIN" autofocus required />
      <button type="submit">Скачать файл</button>
    </form>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <div class="hint">Осталось скачиваний: {{ remaining }}</div>
  </div>
</body>
</html>
        """

        def _render_pin_page(error=None, remaining=0, status_code=200):
            response = make_response(
                render_template_string(pin_page_tpl, error=error, remaining=remaining),
                status_code,
            )
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        try:
            token_row = qr_download_token_model.query.filter_by(token_hash=token_hash).first()
            if not token_row:
                log_qr_event("download_not_found", details="token_not_found")
                abort(410, description="Ссылка истекла или уже использована")

            if token_row.expires_at < now:
                log_qr_event("download_expired", token_row=token_row, details="token_expired")
                abort(410, description="Ссылка истекла или уже использована")

            if token_row.download_count >= token_row.max_downloads:
                log_qr_event("download_limit_reached", token_row=token_row, details="limit_reached")
                abort(410, description="Ссылка истекла или уже использована")

            if token_row.pin_hash:
                remaining = max(token_row.max_downloads - token_row.download_count, 0)
                if request.method != "POST":
                    return _render_pin_page(error=None, remaining=remaining)

                pin = (request.form.get("pin") or "").strip()
                if not pin:
                    return _render_pin_page(error="Введите PIN", remaining=remaining, status_code=400)

                pin_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
                if pin_hash != token_row.pin_hash:
                    log_qr_event("download_pin_invalid", token_row=token_row, details="invalid_pin")
                    return _render_pin_page(error="Неверный PIN", remaining=remaining, status_code=403)

            updated = db.session.query(qr_download_token_model).filter(
                qr_download_token_model.id == token_row.id,
                qr_download_token_model.expires_at >= now,
                qr_download_token_model.download_count < qr_download_token_model.max_downloads,
            ).update(
                {
                    "used_at": case((qr_download_token_model.used_at.is_(None), now), else_=qr_download_token_model.used_at),
                    "download_count": qr_download_token_model.download_count + 1,
                },
                synchronize_session=False,
            )

            if updated != 1:
                db.session.rollback()
                log_qr_event("download_limit_reached", token_row=token_row, details="race_limit_reached")
                abort(410, description="Ссылка уже использована")

            db.session.commit()
            log_qr_event("download_success", token_row=token_row, details=f"count+1/{token_row.max_downloads}")

            file_path, _ = resolve_config_file(token_row.config_type, token_row.config_name)
            if not file_path:
                log_qr_event("download_file_missing", token_row=token_row, details="file_not_found")
                abort(404, description="Файл не найден")

            base = os.path.basename(file_path)
            log_user_action_event(
                "config_download",
                target_type=str(token_row.config_type or "config"),
                target_name=base,
                details="channel=qr_one_time",
            )
            return send_from_directory(
                os.path.dirname(file_path),
                base,
                as_attachment=True,
                download_name=base,
            )
        except HTTPException:
            raise

    @app.route("/download/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def download(file_path, clean_name):
        _ = clean_name
        user = get_current_user(user_model)
        if user and user.role == "viewer":
            cfg_type = get_config_type(file_path)
            if cfg_type not in ("openvpn", "wg", "amneziawg"):
                abort(403)
            cfg_name = os.path.basename(file_path)
            access = viewer_config_access_model.query.filter_by(
                user_id=user.id,
                config_type=cfg_type,
                config_name=cfg_name,
            ).first()
            if not access:
                abort(403)

        base = os.path.basename(file_path)
        download_name = _build_short_download_name(file_path)
        log_user_action_event(
            "config_download",
            target_type=str(get_config_type(file_path) or "config"),
            target_name=base,
            details=f"channel=web filename={download_name}",
        )
        return send_from_directory(
            os.path.dirname(file_path),
            base,
            as_attachment=True,
            download_name=download_name,
        )

    @app.route("/api/tg-mini/send-config", methods=["POST"])
    @auth_manager.login_required
    def api_tg_mini_send_config():
        denied = _enforce_telegram_mini_api_access()
        if denied is not None:
            return denied

        user = get_current_user(user_model)
        if not user:
            return jsonify({"success": False, "message": "Пользователь не найден"}), 403

        bot_token = (os.getenv("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
        if not bot_token:
            return jsonify({"success": False, "message": "Telegram бот не настроен на сервере"}), 400

        telegram_chat_id = str(
            session.get("telegram_mini_id")
            or getattr(user, "telegram_id", "")
            or ""
        ).strip()
        if not telegram_chat_id or not re.fullmatch(r"^[1-9][0-9]{4,20}$", telegram_chat_id):
            return jsonify({"success": False, "message": "Не удалось определить Telegram chat id пользователя"}), 400

        payload = request.get_json(silent=True) or {}
        download_url = (payload.get("download_url") or "").strip()
        device_platform = _detect_device_platform(payload.get("device_platform"))
        if not download_url:
            return jsonify({"success": False, "message": "Не передан URL конфига"}), 400

        parsed = urllib.parse.urlparse(download_url)
        path = parsed.path or ""
        match = re.fullmatch(r"^/download/([^/]+)/(.+)$", path)
        if not match:
            return jsonify({"success": False, "message": "Некорректный URL конфига"}), 400

        file_type = urllib.parse.unquote(match.group(1))
        filename = urllib.parse.unquote(match.group(2))
        file_path, clean_name = resolve_config_file(file_type, filename)
        if not file_path:
            return jsonify({"success": False, "message": "Файл конфига не найден"}), 404

        if user.role == "viewer":
            cfg_type = get_config_type(file_path)
            if cfg_type not in ("openvpn", "wg", "amneziawg"):
                return jsonify({"success": False, "message": "Доступ запрещён"}), 403
            cfg_name = os.path.basename(file_path)
            access = viewer_config_access_model.query.filter_by(
                user_id=user.id,
                config_type=cfg_type,
                config_name=cfg_name,
            ).first()
            if not access:
                return jsonify({"success": False, "message": "Доступ к конфигу запрещён"}), 403

        file_name = _build_short_download_name(file_path)
        config_kind = _normalize_config_kind(file_type, file_path, file_name)
        caption = _build_platform_instruction_caption(file_name, device_platform, config_kind)

        try:
            _send_document_via_telegram_bot(
                bot_token,
                telegram_chat_id,
                file_path,
                caption,
                telegram_filename=file_name,
            )
            log_telegram_audit_event(
                "mini_send_config",
                config_name=file_name,
                details=f"kind={config_kind}",
            )
            log_user_action_event(
                "config_send_telegram",
                target_type=str(config_kind or "config"),
                target_name=file_name,
                details=f"kind={config_kind} via=tg-mini",
            )
            return jsonify(
                {
                    "success": True,
                    "message": "Конфиг отправлен в чат Telegram",
                    "file_name": file_name,
                }
            )
        except ValueError as e:
            log_telegram_audit_event(
                "mini_send_config_failed",
                config_name=file_name,
                details=str(e),
            )
            log_user_action_event(
                "config_send_telegram",
                target_type=str(config_kind or "config"),
                target_name=file_name,
                details="result=failed via=tg-mini",
                status="error",
            )
            return jsonify({"success": False, "message": str(e)}), 502
        except (OSError, RuntimeError) as e:
            app.logger.exception("Ошибка отправки конфига в Telegram: %s", e)
            log_telegram_audit_event(
                "mini_send_config_failed",
                config_name=file_name,
                details="internal_error",
            )
            log_user_action_event(
                "config_send_telegram",
                target_type=str(config_kind or "config"),
                target_name=file_name,
                details="result=failed via=tg-mini",
                status="error",
            )
            return jsonify({"success": False, "message": "Внутренняя ошибка отправки в Telegram"}), 500

    @app.route("/api/tg-mini/check-bot-delivery", methods=["POST"])
    @auth_manager.login_required
    def api_tg_mini_check_bot_delivery():
        denied = _enforce_telegram_mini_api_access()
        if denied is not None:
            return denied

        user = get_current_user(user_model)
        if not user:
            return jsonify({"success": False, "message": "Пользователь не найден"}), 403

        bot_token = (os.getenv("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
        if not bot_token:
            return jsonify({"success": False, "message": "Telegram бот не настроен на сервере"}), 400

        telegram_chat_id = str(
            session.get("telegram_mini_id")
            or getattr(user, "telegram_id", "")
            or ""
        ).strip()
        if not telegram_chat_id or not re.fullmatch(r"^[1-9][0-9]{4,20}$", telegram_chat_id):
            return jsonify({"success": False, "message": "Не удалось определить Telegram chat id пользователя"}), 400

        try:
            _telegram_bot_api_json(
                bot_token,
                "sendChatAction",
                {
                    "chat_id": telegram_chat_id,
                    "action": "typing",
                },
            )
            log_telegram_audit_event(
                "mini_check_bot_delivery",
                details="ok",
            )
            log_user_action_event(
                "telegram_bot_delivery_check",
                target_type="telegram",
                target_name="bot_delivery",
                details="result=ok via=tg-mini",
            )
            return jsonify(
                {
                    "success": True,
                    "message": "Связь с ботом в порядке: отправка в чат доступна",
                }
            )
        except ValueError as e:
            error_text = str(e)
            lower_error = error_text.lower()
            if (
                "bot can't initiate conversation" in lower_error
                or "forbidden" in lower_error
                or "chat not found" in lower_error
            ):
                user_message = "Бот не может написать вам первым. Откройте бота и нажмите Start, затем повторите проверку."
            else:
                user_message = f"Проверка не пройдена: {error_text}"
            log_telegram_audit_event(
                "mini_check_bot_delivery_failed",
                details=error_text,
            )
            log_user_action_event(
                "telegram_bot_delivery_check",
                target_type="telegram",
                target_name="bot_delivery",
                details="result=failed via=tg-mini",
                status="error",
            )
            return jsonify({"success": False, "message": user_message}), 400
        except (OSError, RuntimeError) as e:
            app.logger.exception("Ошибка проверки связи mini app с Telegram bot: %s", e)
            log_telegram_audit_event(
                "mini_check_bot_delivery_failed",
                details="internal_error",
            )
            log_user_action_event(
                "telegram_bot_delivery_check",
                target_type="telegram",
                target_name="bot_delivery",
                details="result=failed via=tg-mini",
                status="error",
            )
            return jsonify({"success": False, "message": "Внутренняя ошибка проверки Telegram"}), 500

    @app.route("/public_download/<router>")
    def public_download(router):
        if not get_public_download_enabled():
            abort(404)
        filename = result_dir_files.get(router)
        if not filename:
            abort(404)

        log_user_action_event(
            "config_download",
            target_type="public",
            target_name=filename,
            details=f"channel=public router={router}",
        )

        return send_from_directory("/root/antizapret/result", filename, as_attachment=True)

    @app.route("/toggle_public_download", methods=["POST"])
    @auth_manager.admin_required
    def toggle_public_download():
        enabled_value = request.form.get("enabled", "").lower()
        current_state = get_public_download_enabled()
        if enabled_value in ("true", "false"):
            next_state = enabled_value == "true"
        else:
            next_state = not current_state

        set_public_download_enabled(next_state)
        env_value = "true" if next_state else "false"
        set_env_value("PUBLIC_DOWNLOAD_ENABLED", env_value)
        os.environ["PUBLIC_DOWNLOAD_ENABLED"] = env_value
        log_user_action_event(
            "settings_public_download_toggle",
            target_type="public_download",
            target_name="PUBLIC_DOWNLOAD_ENABLED",
            details=f"{'вкл' if current_state else 'выкл'} → {'вкл' if next_state else 'выкл'}",
        )

        flash(
            "Публичный доступ к файлам включен." if next_state else "Публичный доступ к файлам выключен.",
            "success",
        )
        return_to = request.form.get("return_to", "edit_files")
        if return_to not in ("edit_files", "settings"):
            return_to = "edit_files"
        return redirect(url_for(return_to))

    @app.route("/generate_qr/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def generate_qr(file_path, clean_name):
        _ = clean_name
        user = get_current_user(user_model)
        if user and user.role == "viewer":
            cfg_type = get_config_type(file_path)
            if cfg_type not in ("openvpn", "wg", "amneziawg"):
                abort(403)
            cfg_name = os.path.basename(file_path)
            access = viewer_config_access_model.query.filter_by(
                user_id=user.id,
                config_type=cfg_type,
                config_name=cfg_name,
            ).first()
            if not access:
                abort(403)
        with open(file_path, "r") as file:
            config_text = file.read()

        config_type = get_config_type(file_path)
        force_download_url_qr = (
            config_type == "amneziawg" and len(config_text.encode("utf-8")) > 2200
        )

        if force_download_url_qr:
            download_url = create_one_time_download_url(file_path)
            img_byte_arr = qr_generator.generate_qr_for_download_url(download_url)
            response = send_file(img_byte_arr, mimetype="image/png")
            response.headers["X-QR-Mode"] = "download-url"
            response.headers["X-QR-Message-Code"] = "CONFIG_TOO_LARGE_USE_DOWNLOAD"
            response.headers["X-QR-Download-Url"] = download_url
            return response

        try:
            img_byte_arr = qr_generator.generate_qr_code(config_text)
            response = send_file(img_byte_arr, mimetype="image/png")
            response.headers["X-QR-Mode"] = "config"
            return response
        except ValueError as qr_error:
            if "слишком длинная" in str(qr_error):
                download_url = create_one_time_download_url(file_path)
                img_byte_arr = qr_generator.generate_qr_for_download_url(download_url)
                response = send_file(img_byte_arr, mimetype="image/png")
                response.headers["X-QR-Mode"] = "download-url"
                response.headers["X-QR-Message-Code"] = "CONFIG_OVERFLOW_USE_DOWNLOAD"
                response.headers["X-QR-Download-Url"] = download_url
                return response
            raise

    @app.route("/generate_one_time_download/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def generate_one_time_download(file_path, clean_name):
        _ = clean_name
        user = get_current_user(user_model)
        if not user or user.role != "admin":
            return jsonify({"success": False, "message": "Доступ запрещён."}), 403

        try:
            download_url = create_one_time_download_url(file_path)
            return jsonify(
                {
                    "success": True,
                    "download_url": download_url,
                }
            )
        except HTTPException:
            raise
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400

    @app.route("/edit-files", methods=["GET", "POST"])
    @auth_manager.admin_required
    def edit_files():
        if request.method == "POST":
            file_type = request.form.get("file_type")
            content = request.form.get("content", "")
            content_ok, content_error = _validate_editor_content(content)
            if not content_ok:
                return jsonify({"success": False, "message": content_error}), 400

            if file_editor.update_file_content(file_type, content):
                try:
                    task = enqueue_background_task(
                        "run_doall",
                        task_run_doall,
                        created_by_username=session.get("username"),
                        queued_message="Применение изменений запущено в фоне",
                    )
                    return task_accepted_response(
                        task,
                        "Файл сохранен. Применение изменений выполняется в фоне.",
                    )
                except (RuntimeError, ValueError, OSError) as e:
                    return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

            return jsonify({"success": False, "message": "Неверный тип файла."}), 400

        file_contents = file_editor.get_file_contents()
        file_display_titles = file_editor.get_file_display_titles()
        return render_template(
            "edit_files.html",
            file_contents=file_contents,
            file_display_titles=file_display_titles,
            public_download_enabled=get_public_download_enabled(),
        )

    @app.route("/run-doall", methods=["POST"])
    @auth_manager.admin_required
    def run_doall():
        try:
            task = enqueue_background_task(
                "run_doall",
                task_run_doall,
                created_by_username=session.get("username"),
                queued_message="Запуск doall поставлен в очередь",
            )
            is_tg_mini_action = _has_telegram_mini_session()
            details_text = f"task_id={task.id}"
            if is_tg_mini_action:
                log_telegram_audit_event(
                    "mini_run_doall",
                    details=details_text,
                )
                details_text += " via=tg-mini"

            log_user_action_event(
                "settings_run_doall",
                target_type="maintenance",
                target_name="doall",
                details="запущен скрипт doall.sh",
            )
            return task_accepted_response(
                task,
                "Скрипт doall запущен в фоне.",
            )
        except (RuntimeError, ValueError, OSError) as e:
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
