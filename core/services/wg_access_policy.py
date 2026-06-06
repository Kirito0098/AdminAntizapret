from datetime import datetime, timedelta, timezone

from core.services.time_utils import as_utc
from core.services.traffic_limit import (
    TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED,
    TrafficLimitExceededError,
    resolve_traffic_limit_state,
)

EXPIRED_REQUIRES_EXTEND_MESSAGE = (
    "Клиент отключён по истечении срока действия. Для разблокировки продлите срок WG/AWG."
)
EXPIRED_REQUIRES_EXTEND_CODE = "expired_requires_extend"


class ExpiredRequiresExtendError(ValueError):
    error_code = EXPIRED_REQUIRES_EXTEND_CODE

    def __init__(self, message=EXPIRED_REQUIRES_EXTEND_MESSAGE):
        super().__init__(message)


class WgAccessPolicyService:
    def __init__(
        self,
        *,
        db,
        policy_model,
        runtime_enforcer=None,
        use_subprocess_runtime=True,
        runtime_subprocess_timeout_seconds=60,
        get_consumed_traffic_bytes=None,
    ):
        self.db = db
        self.policy_model = policy_model
        self.runtime_enforcer = runtime_enforcer
        self.use_subprocess_runtime = bool(use_subprocess_runtime)
        self.runtime_subprocess_timeout_seconds = max(10, int(runtime_subprocess_timeout_seconds or 60))
        self.get_consumed_traffic_bytes = get_consumed_traffic_bytes or (lambda _client_name: 0)

    def _apply_client_runtime(self, client_name, *, is_blocked):
        if self.use_subprocess_runtime:
            from utils.wg_runtime_subprocess import apply_wg_client_runtime

            return apply_wg_client_runtime(
                client_name,
                is_blocked=is_blocked,
                timeout_seconds=self.runtime_subprocess_timeout_seconds,
            )
        if self.runtime_enforcer is None:
            return None
        normalized = self.normalize_client_name(client_name)
        if is_blocked:
            return self.runtime_enforcer.block_client_runtime(normalized)
        return self.runtime_enforcer.unblock_client_runtime(normalized)

    def _reapply_all_blocked_runtime(self):
        if not (self.use_subprocess_runtime or self.runtime_enforcer is not None):
            return []
        now = self._now()
        results = []
        for row in self.policy_model.query.all():
            state = self._resolve_effective_state(row, now=now)
            if not state["is_blocked"]:
                continue
            results.append(
                {
                    "client_name": row.client_name,
                    "result": self._apply_client_runtime(row.client_name, is_blocked=True),
                }
            )
        return results

    def _now(self):
        return datetime.now(timezone.utc)

    def _is_access_expired(self, row, now=None):
        if row is None:
            return False
        expires_at = as_utc(row.expires_at)
        if not expires_at:
            return False
        now = as_utc(now) or self._now()
        return expires_at <= now

    def normalize_client_name(self, client_name):
        return (client_name or "").strip().lower()

    def _get_or_create(self, client_name):
        normalized = self.normalize_client_name(client_name)
        if not normalized:
            return None
        row = self.policy_model.query.filter_by(client_name=normalized).first()
        if row is None:
            row = self.policy_model(client_name=normalized)
            self.db.session.add(row)
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
        self.reconcile_client_policy(client_name, apply_runtime=True)
        return row

    def clear_traffic_limit(self, client_name, *, actor_username=None):
        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")

        row.traffic_limit_bytes = None
        row.traffic_limit_period_days = None
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name, apply_runtime=True)
        return row

    def set_expiry_days(self, client_name, days, *, actor_username=None, extend=False):
        if int(days) < 1:
            raise ValueError("Срок должен быть не меньше 1 дня")

        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")

        now = self._now()
        base_dt = now
        existing_expiry = as_utc(row.expires_at)
        if extend and existing_expiry and existing_expiry > now:
            base_dt = existing_expiry
        row.expires_at = base_dt + timedelta(days=int(days))
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name, apply_runtime=True)
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
        self.reconcile_client_policy(client_name, apply_runtime=True)
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
        self.reconcile_client_policy(client_name, apply_runtime=True)
        return row

    def clear_block(self, client_name, *, actor_username=None):
        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")

        if self._is_access_expired(row):
            raise ExpiredRequiresExtendError()

        traffic_state = self._resolve_traffic_state(row)
        if self._is_traffic_limit_exceeded(row, traffic_state):
            raise TrafficLimitExceededError()

        row.is_temp_blocked = False
        row.is_permanent_blocked = False
        row.block_started_at = None
        row.block_days = None
        row.block_until = None
        if row.block_reason in {"manual_temp", "manual_permanent"}:
            row.block_reason = None
        row.updated_by = (actor_username or "").strip() or None
        self.db.session.commit()
        self.reconcile_client_policy(client_name, apply_runtime=True)
        return row

    def clear_temp_block(self, client_name, *, actor_username=None):
        return self.clear_block(client_name, actor_username=actor_username)

    def _resolve_days_left(self, target_dt, now):
        if not target_dt:
            return None
        try:
            return (as_utc(target_dt) - as_utc(now)).days
        except Exception:
            return None

    def _resolve_effective_state(self, row, now=None):
        now = as_utc(now) or self._now()
        expires_at = as_utc(row.expires_at)
        block_until = as_utc(row.block_until)
        permanent_blocked = bool(row.is_permanent_blocked)
        expired = bool(expires_at and expires_at <= now)
        temp_blocked = bool(row.is_temp_blocked and (block_until is None or block_until > now))
        traffic_state = self._resolve_traffic_state(row)
        traffic_exceeded = bool(traffic_state.get("traffic_limit_exceeded"))
        is_blocked = expired or permanent_blocked or temp_blocked or traffic_exceeded
        if expired:
            reason = "expired"
        elif permanent_blocked:
            reason = "manual_permanent"
        elif temp_blocked:
            reason = "manual_temp"
        elif traffic_exceeded:
            reason = "traffic_limit"
        else:
            reason = None
        if expired:
            block_mode = "expired"
        elif permanent_blocked:
            block_mode = "permanent"
        elif temp_blocked:
            block_mode = "temp"
        elif traffic_exceeded:
            block_mode = "traffic_limit"
        else:
            block_mode = "none"
        return {
            "is_blocked": is_blocked,
            "reason": reason,
            "expired": expired,
            "temp_blocked": temp_blocked,
            "permanent_blocked": permanent_blocked,
            "traffic_limit_exceeded": traffic_exceeded,
            "block_mode": block_mode,
            "access_days_left": self._resolve_days_left(expires_at, now),
            "blocked_days_left": self._resolve_days_left(block_until, now) if temp_blocked else None,
            "block_duration_days": int(row.block_days) if row.block_days is not None else None,
            "block_started_at": row.block_started_at,
            **traffic_state,
        }

    def _cleanup_expired_temp_block(self, row, now):
        if row.is_temp_blocked and row.block_until and as_utc(row.block_until) <= as_utc(now):
            row.is_temp_blocked = False
            row.block_started_at = None
            row.block_days = None
            row.block_until = None
            if row.block_reason == "manual_temp":
                row.block_reason = None
            return True
        return False

    def reconcile_client_policy(self, client_name, *, apply_runtime=False):
        normalized = self.normalize_client_name(client_name)
        if not normalized:
            return None
        row = self.policy_model.query.filter_by(client_name=normalized).first()
        if row is None:
            return None

        now = self._now()
        changed = self._cleanup_expired_temp_block(row, now)
        state = self._resolve_effective_state(row, now=now)

        target_reason = state["reason"]
        if row.block_reason != target_reason:
            row.block_reason = target_reason
            changed = True

        if changed:
            self.db.session.commit()

        runtime_result = None
        reapplied_blocked = []
        if apply_runtime and (self.use_subprocess_runtime or self.runtime_enforcer is not None):
            is_blocked = bool(state["is_blocked"])
            runtime_result = self._apply_client_runtime(normalized, is_blocked=is_blocked)
            if not is_blocked:
                reapplied_blocked = self._reapply_all_blocked_runtime()

        return {
            "row": row,
            "state": state,
            "runtime_result": runtime_result,
            "reapplied_blocked": reapplied_blocked,
        }

    def reconcile_all(self, *, apply_runtime=False):
        now = self._now()
        rows = self.policy_model.query.all()
        changed = False
        blocked_clients = []
        unblocked_clients = []
        for row in rows:
            if self._cleanup_expired_temp_block(row, now):
                changed = True

            state = self._resolve_effective_state(row, now=now)
            if row.block_reason != state["reason"]:
                row.block_reason = state["reason"]
                changed = True

            if state["is_blocked"]:
                blocked_clients.append(row.client_name)
            else:
                unblocked_clients.append(row.client_name)

        if changed:
            self.db.session.commit()

        runtime = {"blocked": [], "unblocked": []}
        if apply_runtime and (self.use_subprocess_runtime or self.runtime_enforcer is not None):
            for client_name in unblocked_clients:
                runtime["unblocked"].append(
                    {
                        "client_name": client_name,
                        "result": self._apply_client_runtime(client_name, is_blocked=False),
                    }
                )
            for client_name in blocked_clients:
                runtime["blocked"].append(
                    {
                        "client_name": client_name,
                        "result": self._apply_client_runtime(client_name, is_blocked=True),
                    }
                )

        return {"blocked_clients": blocked_clients, "unblocked_clients": unblocked_clients, "runtime": runtime}

    def build_status_map(self, client_names):
        now = self._now()
        normalized = {self.normalize_client_name(name) for name in (client_names or []) if (name or "").strip()}
        if not normalized:
            return {}

        rows = self.policy_model.query.filter(self.policy_model.client_name.in_(sorted(normalized))).all()
        by_name = {row.client_name: row for row in rows}

        status_map = {}
        for name in normalized:
            row = by_name.get(name)
            if row is None:
                status_map[name] = {
                    "is_blocked": False,
                    "reason": None,
                    "expires_at": None,
                    "block_until": None,
                    "access_days_left": None,
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
                "expires_at": row.expires_at,
                "block_until": row.block_until,
                "access_days_left": state["access_days_left"],
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

