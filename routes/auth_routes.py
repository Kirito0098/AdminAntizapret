import secrets
import time
import hashlib
import hmac
import os
from datetime import timedelta

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
    db,
    user_model,
    touch_active_web_session,
    remove_active_web_session,
    app_name="AdminAntizapret",
):
    def _get_remember_me_days():
        raw_value = (os.getenv("REMEMBER_ME_DAYS", "30") or "").strip()
        try:
            return max(1, min(int(raw_value), 365))
        except (TypeError, ValueError):
            return 30

    def _get_telegram_bot_username():
        return (os.getenv("TELEGRAM_AUTH_BOT_USERNAME", "") or "").strip()

    def _get_telegram_bot_token():
        return (os.getenv("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()

    def _get_telegram_auth_max_age_seconds():
        raw_value = (os.getenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "300") or "").strip()
        try:
            return max(30, min(int(raw_value), 86400))
        except (TypeError, ValueError):
            return 300

    def _is_telegram_auth_enabled():
        return bool(_get_telegram_bot_username() and _get_telegram_bot_token())

    def _verify_telegram_auth(payload):
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

    @app.route("/login", methods=["GET", "POST"])
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

                session["username"] = user.username
                session["user_role"] = user.role
                session["auth_sid"] = secrets.token_hex(16)
                session.pop("_active_session_touch_ts", None)
                session["attempts"] = 0
                try:
                    touch_active_web_session(user.username, force=True)
                except Exception as e:
                    db.session.rollback()
                    app.logger.warning("Не удалось обновить активную сессию при логине: %s", e)
                return redirect(url_for("index"))
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
            flash(error_message or "Ошибка Telegram авторизации.", "error")
            return redirect(url_for("login"))

        telegram_id = (payload.get("id") or "").strip()
        user = user_model.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            flash("Этот Telegram аккаунт не привязан ни к одному пользователю панели.", "error")
            return redirect(url_for("login"))

        session["username"] = user.username
        session["user_role"] = user.role
        session["auth_sid"] = secrets.token_hex(16)
        session.pop("_active_session_touch_ts", None)
        session["attempts"] = 0

        try:
            touch_active_web_session(user.username, force=True)
        except Exception as e:
            db.session.rollback()
            app.logger.warning("Не удалось обновить активную сессию при Telegram логине: %s", e)

        return redirect(url_for("index"))

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

        if not ip_restriction.is_ip_allowed(client_ip):
            if request.endpoint == "ip_blocked":
                return

            if request.is_json:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"Доступ запрещен с вашего IP-адреса: {client_ip}",
                        }
                    ),
                    403,
                )

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
        client_ip = ip_restriction.get_client_ip()
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        request_path = request.headers.get("Referer", request.path)

        return render_template(
            "ip_blocked.html",
            client_ip=client_ip,
            current_time=current_time,
            request_path=request_path,
            app_name=app_name,
        )
