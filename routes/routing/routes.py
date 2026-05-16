from flask import render_template

from core.services.routing.page_context import build_routing_page_context


def register_routing_routes(
    app,
    *,
    auth_manager,
    ip_manager,
    get_env_value,
):
    @app.route("/routing", methods=["GET"])
    @auth_manager.admin_required
    def routing():
        return render_template(
            "routing.html",
            **build_routing_page_context(ip_manager=ip_manager, get_env_value=get_env_value),
        )
