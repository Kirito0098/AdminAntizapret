import secrets
import time

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

            user = user_model.query.filter_by(username=username).first()
            if user and user.check_password(password):
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
        return render_template("login.html", captcha=session["captcha"])

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
