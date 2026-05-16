from ip_blocked.blueprint import bp
from ip_blocked.routes import register_ip_blocked_routes

__all__ = ["register_ip_blocked_routes", "bp"]
