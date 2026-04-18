from flask import g, session


def _query_user(user_model, username):
    return user_model.query.filter_by(username=username).first()


def _model_cache_key(user_model):
    return f"{getattr(user_model, '__module__', '')}.{getattr(user_model, '__name__', '')}"


def get_user_by_username(user_model, username):
    normalized = (username or "").strip()
    if not normalized:
        return None

    try:
        cache = getattr(g, "_request_user_cache", None)
        if cache is None:
            cache = {}
            g._request_user_cache = cache
    except RuntimeError:
        return _query_user(user_model, normalized)

    key = (_model_cache_key(user_model), normalized)
    if key not in cache:
        cache[key] = _query_user(user_model, normalized)
    return cache[key]


def get_current_user(user_model):
    try:
        username = session.get("username")
    except RuntimeError:
        return None
    return get_user_by_username(user_model, username)
