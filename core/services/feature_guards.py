"""Route guards and access checks for disabled application modules."""

from __future__ import annotations

from flask import jsonify, render_template, request

from core.services.feature_toggles import (
    FEATURE_TOGGLE_BY_KEY,
    FEATURE_TOGGLES,
    OPENVPN_INDEX_SCRIPT_OPTIONS,
    WG_AWG_INDEX_SCRIPT_OPTIONS,
    is_app_module_enabled,
)

ALWAYS_ALLOWED_ENDPOINTS = frozenset(
    {
        None,
        "static",
        "login",
        "logout",
        "refresh_captcha",
        "captcha",
        "settings",
        "feature_disabled",
        "robots_txt",
        "security_txt",
        "api_session_heartbeat",
        "index",
        "api_index_client_details",
    }
)

ENDPOINT_TO_MODULES: dict[str, tuple[str, ...]] = {}
for _item in FEATURE_TOGGLES:
    if _item.group != "app_module":
        continue
    for _endpoint in _item.endpoints:
        existing = ENDPOINT_TO_MODULES.get(_endpoint, ())
        if _item.key not in existing:
            ENDPOINT_TO_MODULES[_endpoint] = existing + (_item.key,)

# Backward-compatible alias for tests and callers expecting a single owner per endpoint.
ENDPOINT_TO_MODULE: dict[str, str] = {
    endpoint: modules[0] for endpoint, modules in ENDPOINT_TO_MODULES.items()
}

WG_ACCESS_ENDPOINTS = frozenset({"api_wg_client_access"})


def _module_label(module_key: str) -> str:
    item = FEATURE_TOGGLE_BY_KEY.get(module_key)
    return item.label if item is not None else module_key


def _blocked_payload(*, module_key: str, as_json: bool):
    label = _module_label(module_key)
    message = f'Раздел «{label}» отключён администратором.'
    if as_json:
        return jsonify({"success": False, "error": message, "feature_disabled": module_key}), 403
    return (
        render_template(
            "feature_disabled.html",
            module_key=module_key,
            module_label=label,
        ),
        403,
    )


def check_endpoint_access(endpoint: str | None, *, get_env_value):
    if endpoint in ALWAYS_ALLOWED_ENDPOINTS:
        return None

    if endpoint in WG_ACCESS_ENDPOINTS:
        if is_app_module_enabled("wireguard", get_env_value=get_env_value) or is_app_module_enabled(
            "amneziawg", get_env_value=get_env_value
        ):
            return None
        module_key = "wireguard"
    else:
        module_keys = ENDPOINT_TO_MODULES.get(endpoint or "")
        if not module_keys:
            return None
        if any(is_app_module_enabled(key, get_env_value=get_env_value) for key in module_keys):
            return None
        module_key = module_keys[0]

    as_json = (
        request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
        or request.is_json
    )
    return _blocked_payload(module_key=module_key, as_json=as_json)


def check_index_post_option(option: str | None, *, get_env_value):
    opt = str(option or "").strip()
    if not opt:
        return None

    if opt in OPENVPN_INDEX_SCRIPT_OPTIONS and not is_app_module_enabled(
        "openvpn", get_env_value=get_env_value
    ):
        return _blocked_payload(module_key="openvpn", as_json=True)

    if opt in WG_AWG_INDEX_SCRIPT_OPTIONS:
        wg_enabled = is_app_module_enabled("wireguard", get_env_value=get_env_value)
        awg_enabled = is_app_module_enabled("amneziawg", get_env_value=get_env_value)
        if not wg_enabled and not awg_enabled:
            return _blocked_payload(module_key="wireguard", as_json=True)

    return None


def register_feature_guards(app, *, get_env_value):
    @app.route("/feature-disabled", methods=["GET"], endpoint="feature_disabled")
    def feature_disabled_page():
        module_key = (request.args.get("module") or "").strip()
        label = _module_label(module_key) if module_key else "Модуль"
        return render_template(
            "feature_disabled.html",
            module_key=module_key or None,
            module_label=label,
        )

    @app.before_request
    def _enforce_feature_modules():
        blocked = check_endpoint_access(request.endpoint, get_env_value=get_env_value)
        if blocked is not None:
            return blocked
