from flask import Blueprint

bp = Blueprint(
    "ip_blocked",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/ip-blocked/assets",
)
