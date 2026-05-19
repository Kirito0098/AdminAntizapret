from datetime import datetime, timedelta

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
    ):
        self.db = db
        self.policy_model = policy_model
        self.runtime_enforcer = runtime_enforcer

    def _now(self):
        return datetime.utcnow()

    def _is_access_expired(self, row, now=None):
        if row is None:
            return False
        expires_at = row.expires_at
        if not expires_at:
            return False
        now = now or self._now()
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

    def set_expiry_days(self, client_name, days, *, actor_username=None, extend=False):
        if int(days) < 1:
            raise ValueError("Срок должен быть не меньше 1 дня")

        row = self._get_or_create(client_name)
        if row is None:
            raise ValueError("Некорректное имя клиента")

        now = self._now()
        base_dt = now
        if extend and row.expires_at and row.expires_at > now:
            base_dt = row.expires_at
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
            return (target_dt - now).days
        except Exception:
            return None

    def _resolve_effective_state(self, row, now=None):
        now = now or self._now()
        expires_at = row.expires_at
        block_until = row.block_until
        permanent_blocked = bool(row.is_permanent_blocked)
        expired = bool(expires_at and expires_at <= now)
        temp_blocked = bool(row.is_temp_blocked and (block_until is None or block_until > now))
        is_blocked = expired or permanent_blocked or temp_blocked
        reason = "expired" if expired else ("manual_permanent" if permanent_blocked else ("manual_temp" if temp_blocked else None))
        if expired:
            block_mode = "expired"
        elif permanent_blocked:
            block_mode = "permanent"
        elif temp_blocked:
            block_mode = "temp"
        else:
            block_mode = "none"
        return {
            "is_blocked": is_blocked,
            "reason": reason,
            "expired": expired,
            "temp_blocked": temp_blocked,
            "permanent_blocked": permanent_blocked,
            "block_mode": block_mode,
            "access_days_left": self._resolve_days_left(expires_at, now),
            "blocked_days_left": self._resolve_days_left(block_until, now) if temp_blocked else None,
            "block_duration_days": int(row.block_days) if row.block_days is not None else None,
            "block_started_at": row.block_started_at,
        }

    def _cleanup_expired_temp_block(self, row, now):
        if row.is_temp_blocked and row.block_until and row.block_until <= now:
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
        if apply_runtime and self.runtime_enforcer is not None:
            if state["is_blocked"]:
                runtime_result = self.runtime_enforcer.block_client_runtime(normalized)
            else:
                runtime_result = self.runtime_enforcer.unblock_client_runtime(normalized)

        return {"row": row, "state": state, "runtime_result": runtime_result}

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
        if apply_runtime and self.runtime_enforcer is not None:
            for client_name in blocked_clients:
                runtime["blocked"].append(
                    {
                        "client_name": client_name,
                        "result": self.runtime_enforcer.block_client_runtime(client_name),
                    }
                )
            for client_name in unblocked_clients:
                runtime["unblocked"].append(
                    {
                        "client_name": client_name,
                        "result": self.runtime_enforcer.unblock_client_runtime(client_name),
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
            }
        return status_map

