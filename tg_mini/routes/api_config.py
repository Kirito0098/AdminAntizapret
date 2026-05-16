import os
import re
import urllib.parse

from flask import jsonify, request, session

from core.services.request_user import get_current_user
from tg_mini.services.config_delivery import (
    build_platform_instruction_caption,
    build_short_download_name,
    check_viewer_config_access,
    detect_device_platform,
    normalize_config_kind,
    send_document_via_telegram_bot,
    telegram_bot_api_json,
)
from tg_mini.session import enforce_telegram_mini_session


def register_tg_mini_config_api_routes(
    app,
    *,
    auth_manager,
    user_model,
    viewer_config_access_model,
    resolve_config_file,
    get_config_type,
    io_executor,
    log_telegram_audit_event,
    log_user_action_event,
):
    def _enforce_telegram_mini_api_access():
        return enforce_telegram_mini_session(session, api_request=True)

    @app.route("/api/tg-mini/send-config", methods=["POST"], endpoint="api_tg_mini_send_config")
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
        device_platform = detect_device_platform(request, payload.get("device_platform"))
        if not download_url:
            return jsonify({"success": False, "message": "Не передан URL конфига"}), 400

        parsed = urllib.parse.urlparse(download_url)
        path = parsed.path or ""
        match = re.fullmatch(r"^/download/([^/]+)/(.+)$", path)
        if not match:
            return jsonify({"success": False, "message": "Некорректный URL конфига"}), 400

        file_type = urllib.parse.unquote(match.group(1))
        filename = urllib.parse.unquote(match.group(2))
        file_path, _clean_name = resolve_config_file(file_type, filename)
        if not file_path:
            return jsonify({"success": False, "message": "Файл конфига не найден"}), 404

        access_error = check_viewer_config_access(
            user, file_path, viewer_config_access_model, get_config_type
        )
        if access_error:
            return jsonify({"success": False, "message": access_error}), 403

        file_name = build_short_download_name(file_path)
        config_kind = normalize_config_kind(file_type, file_path, file_name, get_config_type)
        caption = build_platform_instruction_caption(file_name, device_platform, config_kind)

        try:
            send_document_via_telegram_bot(
                io_executor,
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

    @app.route("/api/tg-mini/check-bot-delivery", methods=["POST"], endpoint="api_tg_mini_check_bot_delivery")
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
            telegram_bot_api_json(
                io_executor,
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
