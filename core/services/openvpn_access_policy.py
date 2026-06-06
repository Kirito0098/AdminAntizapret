from datetime import datetime, timedelta, timezone

from core.services.time_utils import as_utc
from core.services.traffic_limit import (
    TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED,
    TrafficLimitExceededError,
    resolve_traffic_limit_state,
)


class OpenVpnAccessPolicyService:
    def __init__(
        self,
        *,
        db,
        policy_model,
        read_banned_clients,
        write_banned_clients,
        ensure_client_connect_ban_check_block,
        get_consumed_traffic_bytes=None,
    ):
        self.db = db
        self.policy_model = policy_model
        self.read_banned_clients = read_banned_clients
        self.write_banned_clients = write_banned_clients
        self.ensure_client_connect_ban_check_block = ensure_client_connect_ban_check_block
        self.get_consumed_traffic_bytes = get_consumed_traffic_bytes or (lambda _client_name: 0)

    def _now(self):
        return datetime.now(timezone.utc)

    def normalize_client_name(self, client_name):
        return (client_name or "").strip()

    def _get_or_create(self, client_name):
        normalized = self.normalize_client_name(client_name)
        if not normalized:
            return None
        row = self.policy_model.query.filter_by(client_name=normalized).first()
        if row is None:
            row = self.policy_model(client_name=normalized)
            self.db.session.add(row)
        return row

    def set_temp_block_days(self, client_name, days, *, actor_username=None):
        if int(days) < 1:
            raise ValueError("Срок блокировки должен быть не меньше 1 дня")
        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")
        now = self._now()
        row.is_temp_blocked = True
        row.is_permanent_blocked = False
        row.block_reason = "manual_temp"
        row.block_started_at = now
        row.block_days = int(days)
        row.block_until = now + timedelta(days=int(days))
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name)
        return row

    def set_permanent_block(self, client_name, *, actor_username=None):
        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")
        now = self._now()
        row.is_temp_blocked = False
        row.is_permanent_blocked = True
        row.block_reason = "manual_permanent"
        row.block_started_at = now
        row.block_days = None
        row.block_until = None
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name)
        return row

    def _resolve_traffic_state(self, row):
        consumed_bytes = self.get_consumed_traffic_bytes(
            row.client_name,
            period_days=row.traffic_limit_period_days,
        )
        return resolve_traffic_limit_state(
            traffic_limit_bytes=row.traffic_limit_bytes,
            traffic_limit_period_days=row.traffic_limit_period_days,
            consumed_bytes=consumed_bytes,
        )

    def _is_traffic_limit_exceeded(self, row, traffic_state=None):
        traffic_state = traffic_state or self._resolve_traffic_state(row)
        return bool(traffic_state.get("traffic_limit_exceeded"))

    def set_traffic_limit_bytes(self, client_name, limit_bytes, *, period_days=None, actor_username=None):
        if int(limit_bytes) < 1:
            raise ValueError("Лимит трафика должен быть не меньше 1 байта")

        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")

        row.traffic_limit_bytes = int(limit_bytes)
        if period_days is not None:
            period_days = int(period_days)
            if period_days not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
                raise ValueError("Период лимита трафика должен быть 1, 7 или 30 дней.")
        row.traffic_limit_period_days = period_days
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name)
        return row

    def clear_traffic_limit(self, client_name, *, actor_username=None):
        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")

        row.traffic_limit_bytes = None
        row.traffic_limit_period_days = None
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name)
        return row

    def clear_block(self, client_name, *, actor_username=None):
        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")

        traffic_state = self._resolve_traffic_state(row)
        if self._is_traffic_limit_exceeded(row, traffic_state):
            raise TrafficLimitExceededError()

        row.is_temp_blocked = False
        row.is_permanent_blocked = False
        row.block_reason = None
        row.block_started_at = None
        row.block_days = None
        row.block_until = None
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name)
        return row

    def _resolve_days_left(self, target_dt, now):
        if not target_dt:
            return None
        try:
            return (as_utc(target_dt) - as_utc(now)).days
        except Exception:
            return None

    def _resolve_effective_state(self, row, now=None):
        now = as_utc(now) or self._now()
        temp_blocked = bool(row.is_temp_blocked and row.block_until and as_utc(row.block_until) > now)
        permanent_blocked = bool(row.is_permanent_blocked)
        traffic_state = self._resolve_traffic_state(row)
        traffic_exceeded = bool(traffic_state.get("traffic_limit_exceeded"))
        if permanent_blocked:
            reason = "manual_permanent"
            block_mode = "permanent"
        elif temp_blocked:
            reason = "manual_temp"
            block_mode = "temp"
        elif traffic_exceeded:
            reason = "traffic_limit"
            block_mode = "traffic_limit"
        else:
            reason = None
            block_mode = "none"
        is_blocked = permanent_blocked or temp_blocked or traffic_exceeded
        return {
            "is_blocked": is_blocked,
            "reason": reason,
            "temp_blocked": temp_blocked,
            "permanent_blocked": permanent_blocked,
            "traffic_limit_exceeded": traffic_exceeded,
            "block_mode": block_mode,
            "blocked_days_left": self._resolve_days_left(row.block_until, now) if temp_blocked else None,
            "block_duration_days": int(row.block_days) if row.block_days is not None else None,
            "block_started_at": row.block_started_at,
            **traffic_state,
        }

    def _cleanup_expired_temp_block(self, row, now):
        if row.is_temp_blocked and row.block_until and as_utc(row.block_until) <= as_utc(now):
            row.is_temp_blocked = False
            row.block_reason = None
            row.block_started_at = None
            row.block_days = None
            row.block_until = None
            return True
        return False

    def _sync_banlist_from_policy(self):
        self.ensure_client_connect_ban_check_block()
        now = self._now()
        rows = self.policy_model.query.all()
        changed = False
        blocked_clients = set()
        for row in rows:
            if self._cleanup_expired_temp_block(row, now):
                changed = True
            traffic_state = self._resolve_traffic_state(row)
            if bool(traffic_state.get("traffic_limit_exceeded")) and row.is_permanent_blocked and not row.is_temp_blocked:
                if not (row.updated_by or "").strip():
                    row.is_permanent_blocked = False
                    row.block_started_at = None
                    row.block_days = None
                    row.block_until = None
                    changed = True
            state = self._resolve_effective_state(row, now=now)
            if row.block_reason != state["reason"]:
                row.block_reason = state["reason"]
                changed = True
            if state["is_blocked"]:
                blocked_clients.add(row.client_name)
        if changed:
            self.db.session.commit()
        self.write_banned_clients(blocked_clients)
        return blocked_clients

    def reconcile_client_policy(self, client_name):
        normalized = self.normalize_client_name(client_name)
        if not normalized:
            return None
        self._sync_banlist_from_policy()
        row = self.policy_model.query.filter_by(client_name=normalized).first()
        if row is None:
            return None
        return {"row": row, "state": self._resolve_effective_state(row)}

    def reconcile_all(self):
        banlist_clients = self.read_banned_clients() or set()
        changed = False
        for client_name in sorted(banlist_clients):
            row = self._get_or_create(client_name)
            if row is None:
                continue
            traffic_state = self._resolve_traffic_state(row)
            if bool(traffic_state.get("traffic_limit_exceeded")):
                continue
            if not row.is_temp_blocked and not row.is_permanent_blocked:
                row.is_permanent_blocked = True
                row.block_reason = "manual_permanent"
                row.block_started_at = self._now()
                row.block_days = None
                row.block_until = None
                changed = True
        if changed:
            self.db.session.commit()
        blocked_clients = self._sync_banlist_from_policy()
        return {"blocked_clients": sorted(blocked_clients)}

    def build_status_map(self, client_names):
        normalized = {self.normalize_client_name(name) for name in (client_names or []) if (name or "").strip()}
        if not normalized:
            return {}
        now = self._now()
        rows = self.policy_model.query.filter(self.policy_model.client_name.in_(sorted(normalized))).all()
        by_name = {row.client_name: row for row in rows}
        status_map = {}
        for name in normalized:
            row = by_name.get(name)
            if row is None:
                status_map[name] = {
                    "is_blocked": False,
                    "reason": None,
                    "block_until": None,
                    "blocked_days_left": None,
                    "block_mode": "none",
                    "block_duration_days": None,
                    "block_started_at": None,
                    "traffic_limit_bytes": None,
                    "traffic_limit_period_days": None,
                    "traffic_limit_period_label": None,
                    "traffic_limit_unblock_at": None,
                    "traffic_limit_unblock_label": None,
                    "traffic_consumed_bytes": 0,
                    "traffic_bytes_left": None,
                    "traffic_limit_exceeded": False,
                }
                continue
            state = self._resolve_effective_state(row, now=now)
            status_map[name] = {
                "is_blocked": bool(state["is_blocked"]),
                "reason": state["reason"],
                "block_until": row.block_until,
                "blocked_days_left": state["blocked_days_left"],
                "block_mode": state["block_mode"],
                "block_duration_days": state["block_duration_days"],
                "block_started_at": state["block_started_at"],
                "traffic_limit_bytes": state.get("traffic_limit_bytes"),
                "traffic_limit_period_days": state.get("traffic_limit_period_days"),
                "traffic_limit_period_label": state.get("traffic_limit_period_label"),
                "traffic_limit_unblock_at": state.get("traffic_limit_unblock_at"),
                "traffic_limit_unblock_label": state.get("traffic_limit_unblock_label"),
                "traffic_consumed_bytes": state.get("traffic_consumed_bytes"),
                "traffic_bytes_left": state.get("traffic_bytes_left"),
                "traffic_limit_exceeded": bool(state.get("traffic_limit_exceeded")),
            }
        return status_map
