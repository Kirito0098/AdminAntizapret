import hashlib
import os
import secrets
from datetime import datetime, timedelta

from flask import request, session, url_for

from core.services.request_user import get_current_user, get_user_by_username


class QrDownloadTokenService:
    def __init__(
        self,
        *,
        db,
        config_paths,
        user_model,
        qr_download_token_model,
        qr_download_audit_log_model,
        logger,
    ):
        self.db = db
        self.config_paths = config_paths
        self.user_model = user_model
        self.qr_download_token_model = qr_download_token_model
        self.qr_download_audit_log_model = qr_download_audit_log_model
        self.logger = logger

    def get_config_type(self, file_path):
        p = (file_path or "").lower()
        if "/openvpn/" in p:
            return "openvpn"
        if "/wireguard/" in p:
            return "wg"
        if "/amneziawg/" in p:
            return "amneziawg"
        return None

    def create_one_time_download_url(self, file_path, get_env_value):
        """Создаёт одноразовую ссылку на скачивание с TTL."""
        config_type = self.get_config_type(file_path)
        if config_type not in self.config_paths:
            raise ValueError("Невозможно определить тип конфигурации для одноразовой ссылки")

        ttl_seconds = int(get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600"))
        ttl_seconds = max(60, min(ttl_seconds, 3600))

        max_downloads = int(get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1"))
        if max_downloads not in (1, 3, 5):
            max_downloads = 1

        pin_raw = (get_env_value("QR_DOWNLOAD_PIN", "") or "").strip()
        pin_hash = hashlib.sha256(pin_raw.encode("utf-8")).hexdigest() if pin_raw else None

        now = datetime.utcnow()
        token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        creator_id = None
        username = session.get("username")
        if username:
            user = get_current_user(self.user_model)
            if user:
                creator_id = user.id

        token_row = self.qr_download_token_model(
            token_hash=token_hash,
            config_type=config_type,
            config_name=os.path.basename(file_path),
            created_by_user_id=creator_id,
            expires_at=now + timedelta(seconds=ttl_seconds),
            max_downloads=max_downloads,
            pin_hash=pin_hash,
        )
        self.db.session.add(token_row)
        self.db.session.flush()

        stale_threshold = now - timedelta(days=1)
        self.db.session.query(self.qr_download_token_model).filter(
            (self.qr_download_token_model.expires_at < stale_threshold)
            | (
                (self.qr_download_token_model.used_at.isnot(None))
                & (self.qr_download_token_model.used_at < stale_threshold)
                & (self.qr_download_token_model.download_count >= self.qr_download_token_model.max_downloads)
            )
        ).delete(synchronize_session=False)

        remote_addr = ((request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",", 1)[0]).strip()
        user_agent = (request.headers.get("User-Agent") or "")[:255]
        self.db.session.add(
            self.qr_download_audit_log_model(
                token_id=token_row.id,
                event_type="generated",
                actor_user_id=creator_id,
                actor_username=username,
                remote_addr=remote_addr,
                user_agent=user_agent,
                details=f"cfg={config_type}/{os.path.basename(file_path)} ttl={ttl_seconds}s max={max_downloads} pin={'y' if pin_hash else 'n'}",
            )
        )

        self.db.session.commit()
        return url_for("one_time_qr_download", token=token, _external=True)

    def log_qr_event(self, event_type, token_row=None, details=None):
        """Пишет событие в журнал QR-ссылок без влияния на основной сценарий."""
        try:
            username = session.get("username")
            actor_user_id = None
            if username:
                actor = get_user_by_username(self.user_model, username)
                if actor:
                    actor_user_id = actor.id

            remote_addr = ((request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",", 1)[0]).strip()
            user_agent = (request.headers.get("User-Agent") or "")[:255]

            self.db.session.add(
                self.qr_download_audit_log_model(
                    token_id=token_row.id if token_row else None,
                    event_type=event_type,
                    actor_user_id=actor_user_id,
                    actor_username=username,
                    remote_addr=remote_addr,
                    user_agent=user_agent,
                    details=(details or "")[:255],
                )
            )
            self.db.session.commit()
        except Exception as e:
            self.db.session.rollback()
            self.logger.warning("Не удалось записать событие QR-журнала: %s", e)
