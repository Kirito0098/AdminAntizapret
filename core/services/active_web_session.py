import secrets
import time
from datetime import datetime, timedelta


class ActiveWebSessionService:
    def __init__(
        self,
        *,
        active_web_session_model,
        get_active_web_session_settings,
        session_id_key="auth_sid",
        touch_ts_key="_active_session_touch_ts",
    ):
        self.active_web_session_model = active_web_session_model
        self.get_active_web_session_settings = get_active_web_session_settings
        self.session_id_key = session_id_key
        self.touch_ts_key = touch_ts_key

    def get_or_create_auth_session_id(self, session_obj):
        sid = (session_obj.get(self.session_id_key) or "").strip()
        if sid:
            return sid

        sid = secrets.token_hex(16)
        session_obj[self.session_id_key] = sid
        session_obj.modified = True
        return sid

    def cleanup_stale_active_web_sessions(self, now=None):
        now = now or datetime.utcnow()
        ttl_seconds, _ = self.get_active_web_session_settings()
        cutoff = now - timedelta(seconds=max(int(ttl_seconds) * 2, 300))
        self.active_web_session_model.query.filter(
            self.active_web_session_model.last_seen_at < cutoff
        ).delete(synchronize_session=False)

    def touch_active_web_session(self, username, *, session_obj, request_obj, db_session, force=False):
        username = (username or "").strip()
        if not username:
            return

        now = datetime.utcnow()
        now_ts = int(time.time())
        _, touch_interval_seconds = self.get_active_web_session_settings()

        if not force and int(touch_interval_seconds) > 0:
            last_touch_ts = int(session_obj.get(self.touch_ts_key) or 0)
            if last_touch_ts and (now_ts - last_touch_ts) < int(touch_interval_seconds):
                return

        sid = self.get_or_create_auth_session_id(session_obj)
        remote_addr = ((request_obj.headers.get("X-Forwarded-For") or request_obj.remote_addr or "").split(",", 1)[0]).strip()
        user_agent = (request_obj.headers.get("User-Agent") or "")[:255]

        row = self.active_web_session_model.query.filter_by(session_id=sid).first()
        if row is None:
            db_session.add(
                self.active_web_session_model(
                    session_id=sid,
                    username=username,
                    remote_addr=remote_addr,
                    user_agent=user_agent,
                    created_at=now,
                    last_seen_at=now,
                )
            )
        else:
            row.username = username
            row.remote_addr = remote_addr
            row.user_agent = user_agent
            row.last_seen_at = now

        self.cleanup_stale_active_web_sessions(now=now)
        db_session.commit()
        session_obj[self.touch_ts_key] = now_ts

    def remove_active_web_session(self, *, session_obj, db_session):
        sid = (session_obj.get(self.session_id_key) or "").strip()
        if not sid:
            return

        self.active_web_session_model.query.filter_by(session_id=sid).delete(synchronize_session=False)
        db_session.commit()
