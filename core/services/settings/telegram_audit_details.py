from __future__ import annotations


def _safe_token(value: str | None, fallback: str = "-") -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return fallback
    return "".join(ch if ch.isalnum() or ch in {"_", "-", ".", "@", ","} else "_" for ch in cleaned)


def _normalized_changed_fields(changed_fields: list[str] | tuple[str, ...] | None) -> str:
    if not changed_fields:
        return "-"
    items: list[str] = []
    for field in changed_fields:
        token = _safe_token(field, fallback="")
        if token and token not in items:
            items.append(token)
    return ",".join(items) if items else "-"


def build_telegram_auth_audit_details(
    *,
    source: str,
    status: str,
    bot_username: str | None,
    max_age_seconds: int | str,
    changed_fields: list[str] | tuple[str, ...] | None = None,
    token_updated: bool = False,
) -> str:
    bot = _safe_token(bot_username, fallback="-")
    source_token = _safe_token(source, fallback="unknown")
    status_token = _safe_token(status, fallback="unknown")
    max_age = str(max_age_seconds).strip() or "-"
    changed = _normalized_changed_fields(changed_fields)
    return (
        f"source={source_token} "
        f"status={status_token} "
        f"bot={bot} "
        f"max_age={max_age} "
        f"changed={changed} "
        f"token_updated={1 if token_updated else 0}"
    )
