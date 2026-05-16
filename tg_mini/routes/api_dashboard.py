from flask import jsonify, session

from tg_mini.services.dashboard import build_tg_mini_dashboard_payload
from tg_mini.session import enforce_telegram_mini_session


def register_tg_mini_dashboard_api_routes(
    app,
    *,
    auth_manager,
    get_logs_dashboard_data_cached,
    user_traffic_sample_model,
    human_bytes,
):
    def _enforce_telegram_mini_api_access():
        return enforce_telegram_mini_session(session, api_request=True)

    @app.route("/api/tg-mini/dashboard", methods=["GET"], endpoint="api_tg_mini_dashboard")
    @auth_manager.login_required
    def api_tg_mini_dashboard():
        denied = _enforce_telegram_mini_api_access()
        if denied is not None:
            return denied

        dashboard_data = get_logs_dashboard_data_cached(created_by_username=session.get("username"))
        return jsonify(
            build_tg_mini_dashboard_payload(
                dashboard_data=dashboard_data,
                user_traffic_sample_model=user_traffic_sample_model,
                human_bytes=human_bytes,
            )
        )
