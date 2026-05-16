from flask import make_response, redirect, session, url_for

from tg_mini.blueprint import bp
from tg_mini.session import enforce_telegram_mini_session


def register_tg_mini_page_routes(app, *, auth_manager):
    def _enforce_page_session():
        return enforce_telegram_mini_session(
            session,
            api_request=False,
            redirect_endpoint="tg_mini_open",
        )

    @app.route("/tg-mini", methods=["GET"], endpoint="tg_mini_app")
    @auth_manager.login_required
    def tg_mini_app():
        denied = _enforce_page_session()
        if denied is not None:
            return denied

        fresh_login = bool(session.pop("telegram_mini_fresh_login", False))
        if not fresh_login:
            return redirect(url_for("tg_mini_open"))

        response = make_response(
            bp.render_template(
                "app.html",
                panel_username=str(session.get("username") or "").strip(),
                telegram_mini_id=str(session.get("telegram_mini_id") or "").strip(),
                telegram_mini_tg_username=str(session.get("telegram_mini_tg_username") or "").strip(),
                telegram_mini_tg_display_name=str(session.get("telegram_mini_tg_display_name") or "").strip(),
            )
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.route("/tg-mini/open", methods=["GET"], endpoint="tg_mini_open")
    def tg_mini_open():
        response = make_response(bp.render_template("open.html"))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response
