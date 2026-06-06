"""Helpers for traffic-based client access limits."""

from datetime import datetime, timedelta, timezone

from core.services.time_utils import as_utc

TRAFFIC_LIMIT_EXCEEDED_MESSAGE = (
    "Клиент отключён по превышению лимита трафика. "
    "Для разблокировки увеличьте лимит, снимите его или очистите статистику трафика."
)
TRAFFIC_LIMIT_EXCEEDED_CODE = "traffic_limit_exceeded"

TRAFFIC_LIMIT_UNITS = {
    "b": 1,
    "kb": 1024,
    "mb": 1024 ** 2,
    "gb": 1024 ** 3,
    "tb": 1024 ** 4,
}

TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED = (1, 7, 30)


class TrafficLimitExceededError(ValueError):
    error_code = TRAFFIC_LIMIT_EXCEEDED_CODE

    def __init__(self, message=TRAFFIC_LIMIT_EXCEEDED_MESSAGE):
        super().__init__(message)


def normalize_traffic_limit_unit(unit):
    normalized = (unit or "mb").strip().lower()
    if normalized in ("byte", "bytes"):
        return "b"
    return normalized


def parse_traffic_limit_bytes(value, unit="mb"):
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректное значение лимита трафика.") from exc

    if amount <= 0:
        raise ValueError("Лимит трафика должен быть больше 0.")

    normalized_unit = normalize_traffic_limit_unit(unit)
    multiplier = TRAFFIC_LIMIT_UNITS.get(normalized_unit)
    if multiplier is None:
        raise ValueError("Единица лимита трафика должна быть одной из: B, KB, MB, GB, TB.")

    limit_bytes = int(amount * multiplier)
    if limit_bytes < 1:
        raise ValueError("Лимит трафика должен быть не меньше 1 байта.")
    return limit_bytes


def parse_traffic_limit_period_days(value):
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    try:
        period_days = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Период лимита трафика должен быть 1, 7 или 30 дней.") from exc

    if period_days not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        raise ValueError("Период лимита трафика должен быть 1, 7 или 30 дней.")
    return period_days


def format_traffic_limit_period_label(period_days):
    if period_days == 1:
        return "за сутки (календарный день)"
    if period_days == 7:
        return "за неделю (пн–вс)"
    if period_days == 30:
        return "за месяц"
    if period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        return f"{period_days} дн."
    if period_days is None:
        return "всё время"
    return f"{period_days} дн."


def get_traffic_limit_period_bounds(period_days, now=None):
    """Return (start, end) for the current traffic-limit period in UTC.

    ``start`` is inclusive, ``end`` is exclusive. Periods are calendar-based:
    - 1 day: 00:00–23:59:59 UTC of the current day
    - 7 days: Monday 00:00 through Sunday 23:59:59 UTC (ISO week)
    - 30 days: 1st 00:00 through last day 23:59:59 UTC of the current month
    """
    if period_days not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        return None, None

    now = as_utc(now) or datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period_days == 1:
        return day_start, day_start + timedelta(days=1)

    if period_days == 7:
        week_start = day_start - timedelta(days=now.weekday())
        return week_start, week_start + timedelta(days=7)

    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)
    return month_start, month_end


def get_traffic_limit_period_start(period_days, now=None):
    period_start, _period_end = get_traffic_limit_period_bounds(period_days, now=now)
    return period_start


def get_traffic_limit_period_unblock_at(period_days, now=None):
    """Return UTC datetime when the current traffic-limit period ends (auto-unblock)."""
    _period_start, period_end = get_traffic_limit_period_bounds(period_days, now=now)
    return period_end


_WEEKDAY_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def format_traffic_limit_unblock_at(period_days, now=None):
    """Return (iso_datetime, human_label) for the next traffic-limit auto-unblock."""
    if period_days not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        return None, None

    unblock_at = get_traffic_limit_period_unblock_at(period_days, now=now)
    if unblock_at is None:
        return None, None

    formatted_at = unblock_at.strftime("%Y-%m-%d %H:%M:%S")
    display_date = unblock_at.strftime("%d.%m.%Y")
    display_time = unblock_at.strftime("%H:%M")

    if period_days == 1:
        label = f"Авторазблокировка: {display_date} {display_time} UTC"
    elif period_days == 7:
        weekday = _WEEKDAY_RU[unblock_at.weekday()]
        label = f"Авторазблокировка: {display_date} {display_time} UTC ({weekday})"
    elif period_days == 30:
        label = f"Авторазблокировка: {display_date} {display_time} UTC"
    else:
        label = f"Авторазблокировка: {display_date} {display_time} UTC"

    return formatted_at, label


def _match_client_identities(*, db, name_model, client_name, normalize_identity):
    target_identity = normalize_identity(client_name)
    if not target_identity:
        return []

    matched_names = []
    for (stored_name,) in db.session.query(name_model).distinct().all():
        candidate = (stored_name or "").strip()
        if not candidate:
            continue
        if normalize_identity(candidate) == target_identity:
            matched_names.append(candidate)
    return matched_names


def get_client_consumed_traffic_bytes(
    *,
    db,
    user_traffic_stat_protocol_model,
    client_name,
    normalize_identity,
    period_days=None,
    user_traffic_sample_model=None,
    now=None,
):
    if period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        if user_traffic_sample_model is None:
            return 0

        matched_names = _match_client_identities(
            db=db,
            name_model=user_traffic_sample_model.common_name,
            client_name=client_name,
            normalize_identity=normalize_identity,
        )
        if not matched_names:
            return 0

        now = now or datetime.now(timezone.utc)
        period_start, period_end = get_traffic_limit_period_bounds(period_days, now=now)
        since_dt = as_utc(period_start).replace(tzinfo=None)
        until_dt = as_utc(period_end).replace(tzinfo=None)
        total = 0
        rows = (
            user_traffic_sample_model.query.filter(
                user_traffic_sample_model.common_name.in_(matched_names),
                user_traffic_sample_model.created_at >= since_dt,
                user_traffic_sample_model.created_at < until_dt,
            ).all()
        )
        for row in rows:
            total += int(row.delta_received or 0) + int(row.delta_sent or 0)
        return total

    matched_names = _match_client_identities(
        db=db,
        name_model=user_traffic_stat_protocol_model.common_name,
        client_name=client_name,
        normalize_identity=normalize_identity,
    )
    if not matched_names:
        return 0

    total = 0
    for candidate in matched_names:
        rows = user_traffic_stat_protocol_model.query.filter_by(common_name=candidate).all()
        for row in rows:
            total += int(row.total_received or 0) + int(row.total_sent or 0)
    return total


def resolve_traffic_limit_state(*, traffic_limit_bytes, traffic_limit_period_days=None, consumed_bytes):
    limit = int(traffic_limit_bytes) if traffic_limit_bytes is not None else None
    consumed = max(int(consumed_bytes or 0), 0)
    period_days = (
        int(traffic_limit_period_days)
        if traffic_limit_period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED
        else None
    )
    if limit is None or limit < 1:
        return {
            "traffic_limit_bytes": None,
            "traffic_limit_period_days": None,
            "traffic_limit_period_label": None,
            "traffic_limit_unblock_at": None,
            "traffic_limit_unblock_label": None,
            "traffic_consumed_bytes": consumed,
            "traffic_bytes_left": None,
            "traffic_limit_exceeded": False,
        }

    exceeded = consumed >= limit
    unblock_at, unblock_label = (
        format_traffic_limit_unblock_at(period_days) if period_days else (None, None)
    )
    return {
        "traffic_limit_bytes": limit,
        "traffic_limit_period_days": period_days,
        "traffic_limit_period_label": format_traffic_limit_period_label(period_days),
        "traffic_limit_unblock_at": unblock_at,
        "traffic_limit_unblock_label": unblock_label,
        "traffic_consumed_bytes": consumed,
        "traffic_bytes_left": 0 if exceeded else max(limit - consumed, 0),
        "traffic_limit_exceeded": exceeded,
    }
