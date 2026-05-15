import secrets
import time
import hashlib
import hmac
import os
import json
from urllib.parse import parse_qsl, urlsplit
from datetime import timedelta
from typing import Any, Callable

from flask import (
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
)


def register_auth_routes(
    app,
    *,
    auth_manager,
    captcha_generator,
    ip_restriction,
    limiter,
    db,
    user_model,
    touch_active_web_session,
    remove_active_web_session,
    log_telegram_audit_event,
    log_user_action_event=None,
    send_tg_admin_notification=None,
    app_name: str = "AdminAntizapret",
) -> None:
    def _limit(rule: str) -> Callable:
        if limiter is None:
            return lambda fn: fn
        return limiter.limit(rule)

    def _get_remember_me_days() -> int:
        configured_value = app.config.get("REMEMBER_ME_DAYS")
        if isinstance(configured_value, int):
            return max(1, min(configured_value, 365))

        if configured_value is None:
            raw_value = (os.getenv("REMEMBER_ME_DAYS", "30") or "").strip()
        else:
            raw_value = str(configured_value).strip()

        try:
            return max(1, min(int(raw_value), 365))
        except (TypeError, ValueError):
            return 30

    def _get_telegram_bot_username() -> str:
        return (os.getenv("TELEGRAM_AUTH_BOT_USERNAME", "") or "").strip()

    def _get_telegram_bot_token() -> str:
        return (os.getenv("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()

    def _get_telegram_auth_max_age_seconds() -> int:
        raw_value = (os.getenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300") or "").strip()
        try:
            return max(30, min(int(raw_value), 86400))
        except (TypeError, ValueError):
            return 300

    def _is_telegram_auth_enabled() -> bool:
        return bool(_get_telegram_bot_username() and _get_telegram_bot_token())

    def _safe_internal_next_url(raw_next_url: str, default_endpoint: str = "tg_mini_app") -> str:
        value = (raw_next_url or "").strip()
        if not value:
            return url_for(default_endpoint)

        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            return url_for(default_endpoint)

        if not value.startswith("/") or value.startswith("//"):
            return url_for(default_endpoint)

        return value

    def _verify_telegram_auth(payload: dict[str, str]) -> tuple[bool, str | None]:
        bot_token = _get_telegram_bot_token()
        if not bot_token:
            return False, "Telegram авторизация не настроена (нет токена бота)."

        received_hash = (payload.get("hash") or "").strip().lower()
        auth_date_raw = (payload.get("auth_date") or "").strip()
        telegram_id = (payload.get("id") or "").strip()

        if not received_hash or not auth_date_raw or not telegram_id:
            return False, "Некорректные данные Telegram авторизации."

        if not auth_date_raw.isdigit():
            return False, "Некорректная дата Telegram авторизации."

        auth_date = int(auth_date_raw)
        max_age_seconds = _get_telegram_auth_max_age_seconds()
        now_ts = int(time.time())
        if abs(now_ts - auth_date) > max_age_seconds:
            return False, "Время Telegram авторизации истекло. Повторите вход."

        data_parts = []
        for key in sorted(payload.keys()):
            if key == "hash":
                continue
            value = payload.get(key)
            if value is None:
                continue
            data_parts.append(f"{key}={value}")

        data_check_string = "\n".join(data_parts)
        secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, received_hash):
            return False, "Проверка подписи Telegram не пройдена."

        return True, None

    def _verify_telegram_webapp_init_data(
        init_data_raw: str,
    ) -> tuple[bool, str | None, dict[str, str] | None]:
        bot_token = _get_telegram_bot_token()
        if not bot_token:
            return False, "Telegram авторизация не настроена (нет токена бота).", None

        init_data = (init_data_raw or "").strip()
        if not init_data:
            return False, "Отсутствуют initData Telegram Mini App.", None

        try:
            payload = dict(parse_qsl(init_data, keep_blank_values=True))
        except Exception:
            return False, "Некорректный формат initData Telegram Mini App.", None

        received_hash = (payload.get("hash") or "").strip().lower()
        auth_date_raw = (payload.get("auth_date") or "").strip()
        if not received_hash or not auth_date_raw:
            return False, "Некорректные данные Telegram Mini App авторизации.", None

        if not auth_date_raw.isdigit():
            return False, "Некорректная дата Telegram Mini App авторизации.", None

        auth_date = int(auth_date_raw)
        max_age_seconds = _get_telegram_auth_max_age_seconds()
        now_ts = int(time.time())
        if abs(now_ts - auth_date) > max_age_seconds:
            return False, "Время Telegram Mini App авторизации истекло. Повторите вход.", None

        check_payload = {k: v for k, v in payload.items() if k != "hash"}
        data_parts = []
        for key in sorted(check_payload.keys()):
            value = check_payload.get(key)
            if value is None:
                continue
            data_parts.append(f"{key}={value}")

        data_check_string = "\n".join(data_parts)
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

        if not hmac.compare_digest(expected_hash, received_hash):
            return False, "Проверка подписи Telegram Mini App не пройдена.", None

        telegram_id = (payload.get("id") or "").strip()
        telegram_username = ""
        telegram_display_name = ""
        user_raw = payload.get("user")
        if user_raw:
            try:
                user_payload = json.loads(user_raw)
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

        payload["id"] = telegram_id
        payload["telegram_username"] = telegram_username
        payload["telegram_display_name"] = telegram_display_name
        return True, None, payload

    def _finish_telegram_login(
        user: Any,
        *,
        mini: bool = False,
        telegram_id: str = "",
        telegram_username: str = "",
        telegram_display_name: str = "",
    ) -> None:
        session["username"] = user.username
        session["user_role"] = user.role
        session["auth_sid"] = secrets.token_hex(16)
        session.pop("_active_session_touch_ts", None)
        session["attempts"] = 0

        if mini:
            session["telegram_mini_auth"] = True
            session["telegram_mini_username"] = user.username
            session["telegram_mini_id"] = str(telegram_id or "").strip()
            session["telegram_mini_tg_username"] = str(telegram_username or "").strip()
            session["telegram_mini_tg_display_name"] = str(telegram_display_name or "").strip()
            session["telegram_mini_fresh_login"] = True
            session.permanent = False
        else:
            session.pop("telegram_mini_auth", None)
            session.pop("telegram_mini_username", None)
            session.pop("telegram_mini_id", None)
            session.pop("telegram_mini_tg_username", None)
            session.pop("telegram_mini_tg_display_name", None)
            session.pop("telegram_mini_fresh_login", None)

        try:
            touch_active_web_session(user.username, force=True)
        except Exception as e:
            db.session.rollback()
            app.logger.warning("Не удалось обновить активную сессию при Telegram логине: %s", e)

    @app.route("/login", methods=["GET", "POST"])
    @_limit("15 per minute;120 per hour")
    def login():
        if ip_restriction.is_enabled():
            client_ip = ip_restriction.get_client_ip()
            if not ip_restriction.is_ip_allowed(client_ip):
                return redirect(url_for("ip_blocked"))

        if "captcha" not in session:
            session["captcha"] = captcha_generator.generate_captcha()

        if request.method == "POST":
            attempts = session.get("attempts", 0)
            attempts += 1
            session["attempts"] = attempts
            if attempts > 2:
                user_captcha = request.form.get("captcha", "").upper()
                correct_captcha = session.get("captcha", "")

                if user_captcha != correct_captcha:
                    flash("Неверный код!", "error")
                    session["captcha"] = captcha_generator.generate_captcha()
                    return redirect(url_for("login"))

            username = request.form["username"]
            password = request.form["password"]
            remember_me = (request.form.get("remember_me") or "").strip().lower() in {
                "1",
                "true",
                "on",
                "yes",
            }

            user = user_model.query.filter_by(username=username).first()
            if user and user.check_password(password):
                if remember_me:
                    app.permanent_session_lifetime = timedelta(days=_get_remember_me_days())
                    session.permanent = True
                else:
                    session.permanent = False

                _finish_telegram_login(user, mini=False)
                if callable(send_tg_admin_notification):
                    _lip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",", 1)[0].strip()
                    send_tg_admin_notification("login_success", actor_username=username, remote_addr=_lip)
                return redirect(url_for("index"))
            if callable(log_user_action_event):
                log_user_action_event(
                    "login_failed",
                    target_type="user",
                    target_name=username[:255] if username else None,
                    status="error",
                    details="invalid_credentials",
                )
            if callable(send_tg_admin_notification):
                client_ip = (
                    request.headers.get("X-Forwarded-For", "") or request.remote_addr or ""
                ).split(",", 1)[0].strip()
                send_tg_admin_notification(
                    "login_failed",
                    actor_username=username[:64] if username else None,
                    remote_addr=client_ip,
                )
            flash("Неверные учетные данные. Попробуйте снова.", "error")
            return redirect(url_for("login"))
        return render_template(
            "login.html",
            captcha=session["captcha"],
            telegram_login_enabled=_is_telegram_auth_enabled(),
            telegram_bot_username=_get_telegram_bot_username(),
            remember_me_days=_get_remember_me_days(),
        )

    @app.route("/auth/telegram", methods=["GET"])
    @_limit("30 per minute;300 per hour")
    def auth_telegram():
        if ip_restriction.is_enabled():
            client_ip = ip_restriction.get_client_ip()
            if not ip_restriction.is_ip_allowed(client_ip):
                return redirect(url_for("ip_blocked"))

        if not _is_telegram_auth_enabled():
            flash("Telegram авторизация не настроена на сервере.", "error")
            return redirect(url_for("login"))

        payload = {k: v for k, v in request.args.items()}
        verified, error_message = _verify_telegram_auth(payload)
        if not verified:
            log_telegram_audit_event(
                "telegram_login_failed",
                details=error_message or "verification_failed",
                telegram_id=(payload.get("id") or "").strip(),
            )
            flash(error_message or "Ошибка Telegram авторизации.", "error")
            return redirect(url_for("login"))

        telegram_id = (payload.get("id") or "").strip()
        user = user_model.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            log_telegram_audit_event(
                "telegram_login_unlinked",
                details="telegram_id_not_bound",
                telegram_id=telegram_id,
            )
            if callable(send_tg_admin_notification):
                client_ip = (
                    request.headers.get("X-Forwarded-For", "") or request.remote_addr or ""
                ).split(",", 1)[0].strip()
                send_tg_admin_notification(
                    "tg_login_unlinked",
                    target_name=telegram_id,
                    remote_addr=client_ip,
                )
            flash("Этот Telegram аккаунт не привязан ни к одному пользователю панели.", "error")
            return redirect(url_for("login"))

        _finish_telegram_login(user, mini=False)
        log_telegram_audit_event(
            "telegram_login_success",
            details="web_login",
            actor_username=user.username,
            telegram_id=telegram_id,
        )
        if callable(send_tg_admin_notification):
            _lip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",", 1)[0].strip()
            send_tg_admin_notification("login_success", actor_username=user.username, remote_addr=_lip)

        return redirect(url_for("index"))

    @app.route("/auth/telegram-mini", methods=["POST"])
    @_limit("30 per minute;300 per hour")
    def auth_telegram_mini():
        if ip_restriction.is_enabled():
            client_ip = ip_restriction.get_client_ip()
            if not ip_restriction.is_ip_allowed(client_ip):
                return redirect(url_for("ip_blocked"))

        if not _is_telegram_auth_enabled():
            flash("Telegram авторизация не настроена на сервере.", "error")
            return redirect(url_for("login"))

        init_data = request.form.get("init_data", "")
        verified, error_message, payload = _verify_telegram_webapp_init_data(init_data)
        if not verified:
            log_telegram_audit_event(
                "telegram_mini_login_failed",
                details=error_message or "mini_verification_failed",
            )
            flash(error_message or "Ошибка Telegram Mini App авторизации.", "error")
            return redirect(url_for("login"))

        telegram_id = (payload or {}).get("id", "")
        telegram_username = (payload or {}).get("telegram_username", "")
        telegram_display_name = (payload or {}).get("telegram_display_name", "")
        user = user_model.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            log_telegram_audit_event(
                "telegram_mini_login_unlinked",
                details="telegram_id_not_bound",
                telegram_id=telegram_id,
            )
            if callable(send_tg_admin_notification):
                client_ip = (
                    request.headers.get("X-Forwarded-For", "") or request.remote_addr or ""
                ).split(",", 1)[0].strip()
                send_tg_admin_notification(
                    "tg_mini_login_unlinked",
                    target_name=telegram_id,
                    remote_addr=client_ip,
                )
            flash("Этот Telegram аккаунт не привязан ни к одному пользователю панели.", "error")
            return redirect(url_for("login"))

        _finish_telegram_login(
            user,
            mini=True,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            telegram_display_name=telegram_display_name,
        )
        log_telegram_audit_event(
            "telegram_mini_login_success",
            details="mini_app_login",
            actor_username=user.username,
            telegram_id=telegram_id,
        )
        if callable(send_tg_admin_notification):
            _lip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",", 1)[0].strip()
            send_tg_admin_notification("login_success", actor_username=user.username, remote_addr=_lip)

        next_url = _safe_internal_next_url(request.form.get("next", ""))
        return redirect(next_url)

    @app.route("/logout")
    def logout():
        try:
            remove_active_web_session()
        except Exception as e:
            db.session.rollback()
            app.logger.warning("Не удалось удалить активную сессию при logout: %s", e)

        session.pop("auth_sid", None)
        session.pop("_active_session_touch_ts", None)
        session.pop("username", None)
        session.pop("telegram_mini_auth", None)
        session.pop("telegram_mini_username", None)
        session.pop("telegram_mini_id", None)
        session.pop("telegram_mini_tg_username", None)
        session.pop("telegram_mini_tg_display_name", None)
        session.pop("telegram_mini_fresh_login", None)
        return redirect(url_for("login"))

    @app.route("/api/session-heartbeat", methods=["GET"])
    @auth_manager.login_required
    def api_session_heartbeat():
        try:
            username = session.get("username")
            if username:
                touch_active_web_session(username, force=True)
            return jsonify({"success": True})
        except Exception as e:
            db.session.rollback()
            app.logger.warning("Ошибка heartbeat активной сессии: %s", e)
            return jsonify({"success": False}), 500

    @app.route("/refresh_captcha")
    def refresh_captcha():
        session["captcha"] = captcha_generator.generate_captcha()
        return session["captcha"]

    @app.route("/captcha.png")
    def captcha():
        session["captcha"] = captcha_generator.generate_captcha()
        img_io = captcha_generator.generate_captcha_image()

        response = make_response(img_io.getvalue())
        response.headers.set("Content-Type", "image/png")
        return response

    @app.before_request
    def check_ip_access():
        if request.endpoint == "static":
            return

        if not ip_restriction.is_enabled():
            return

        client_ip = ip_restriction.get_client_ip()

        if ip_restriction.is_ip_allowed(client_ip):
            ip_restriction.release_firewall_for_ip(client_ip)
            return

        if not ip_restriction.is_ip_allowed(client_ip):
            if ip_restriction.should_count_denied_access(client_ip, request.endpoint):
                ip_restriction.record_denied_access(client_ip)

            if ip_restriction.should_hard_deny(client_ip):
                if request.is_json:
                    return ip_restriction.build_denied_json_response(client_ip)
                return ip_restriction.build_hard_deny_response()

            if request.endpoint in ("ip_blocked", "ip_blocked_ping"):
                return

            if request.is_json:
                return ip_restriction.build_denied_json_response(client_ip)

            return redirect(url_for("ip_blocked"))

    @app.before_request
    def track_active_web_session():
        if request.endpoint == "static":
            return

        username = (session.get("username") or "").strip()
        if not username:
            return

        try:
            touch_active_web_session(username, force=False)
        except Exception as e:
            db.session.rollback()
            app.logger.warning("Не удалось обновить активную сессию: %s", e)

    @app.route("/ip-blocked")
    def ip_blocked():
        if not ip_restriction.is_enabled():
            return redirect(url_for("login"))

        client_ip = ip_restriction.get_client_ip()
        if ip_restriction.is_ip_allowed(client_ip):
            return redirect(url_for("login"))

        dwell_status = ip_restriction.touch_ip_blocked_presence(client_ip)
        if dwell_status.get("banned"):
            return ip_restriction.build_hard_deny_response()

        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        request_path = request.headers.get("Referer", request.path)

        return render_template(
            "ip_blocked.html",
            client_ip=client_ip,
            current_time=current_time,
            request_path=request_path,
            app_name=app_name,
            ip_blocked_dwell_tracking=ip_restriction.block_ip_blocked_dwell,
            ip_blocked_dwell_seconds=ip_restriction.ip_blocked_dwell_seconds,
        )

    @app.route("/ip-blocked/ping", methods=["GET", "POST"])
    def ip_blocked_ping():
        if not ip_restriction.is_enabled():
            return jsonify({"success": False, "message": "IP-ограничения выключены"}), 404

        client_ip = ip_restriction.get_client_ip()
        if ip_restriction.is_ip_allowed(client_ip):
            return jsonify({"banned": False, "tracking": False})

        dwell_status = ip_restriction.touch_ip_blocked_presence(client_ip)
        if dwell_status.get("banned"):
            return ip_restriction.build_denied_json_response(client_ip)

        return jsonify({"success": True, **dwell_status})
