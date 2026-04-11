from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for


class AuthenticationManager:
    def __init__(self, user_model, ip_restriction_service):
        self.user_model = user_model
        self.ip_restriction = ip_restriction_service

    def login_required(self, f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "username" in session:
                if self.ip_restriction.is_enabled():
                    client_ip = self.ip_restriction.get_client_ip()
                    if not self.ip_restriction.is_ip_allowed(client_ip):
                        session.clear()
                        flash(
                            f"Доступ запрещен с вашего IP-адреса ({client_ip}). Обратитесь к администратору.",
                            "error",
                        )
                        return redirect(url_for("ip_blocked"))
            if "username" not in session:
                flash(
                    "Пожалуйста, войдите в систему для доступа к этой странице.", "info"
                )
                return redirect(url_for("login"))
            return f(*args, **kwargs)

        return decorated_function

    def admin_required(self, f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "username" not in session:
                flash("Пожалуйста, войдите в систему.", "info")
                return redirect(url_for("login"))
            user = self.user_model.query.filter_by(username=session["username"]).first()
            if not user or user.role != "admin":
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"success": False, "message": "Доступ запрещён (403)"}), 403
                flash("Доступ запрещён. Недостаточно прав.", "error")
                return redirect(url_for("index"))
            return f(*args, **kwargs)

        return decorated_function
