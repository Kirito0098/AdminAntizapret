from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    telegram_id = db.Column(db.String(32), unique=True, nullable=True, index=True)
    role = db.Column(db.String(20), nullable=False, default="admin", index=True)
    allowed_configs = db.relationship(
        "ViewerConfigAccess",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == "admin"


class QrDownloadToken(db.Model):
    __tablename__ = "qr_download_token"

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    config_type = db.Column(db.String(20), nullable=False)
    config_name = db.Column(db.String(255), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    max_downloads = db.Column(db.Integer, nullable=False, default=1)
    download_count = db.Column(db.Integer, nullable=False, default=0)
    pin_hash = db.Column(db.String(64), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True, index=True)


class QrDownloadAuditLog(db.Model):
    __tablename__ = "qr_download_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.Integer, db.ForeignKey("qr_download_token.id"), nullable=True, index=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    actor_username = db.Column(db.String(80), nullable=True, index=True)
    remote_addr = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    details = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class TelegramMiniAuditLog(db.Model):
    __tablename__ = "telegram_mini_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    actor_username = db.Column(db.String(80), nullable=True, index=True)
    telegram_id = db.Column(db.String(32), nullable=True, index=True)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    config_name = db.Column(db.String(255), nullable=True)
    details = db.Column(db.String(255), nullable=True)
    remote_addr = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class UserActionLog(db.Model):
    __tablename__ = "user_action_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    actor_username = db.Column(db.String(80), nullable=True, index=True)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    target_type = db.Column(db.String(32), nullable=True, index=True)
    target_name = db.Column(db.String(255), nullable=True, index=True)
    status = db.Column(db.String(16), nullable=False, default="success", index=True)
    details = db.Column(db.String(255), nullable=True)
    remote_addr = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class ViewerConfigAccess(db.Model):
    __tablename__ = "viewer_config_access"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    config_type = db.Column(db.String(20), nullable=False)
    config_name = db.Column(db.String(255), nullable=False)
    __table_args__ = (
        db.UniqueConstraint("user_id", "config_type", "config_name", name="unique_user_config_type"),
    )


class UserTrafficStat(db.Model):
    __tablename__ = "user_traffic_stat"

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    total_received = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent = db.Column(db.BigInteger, nullable=False, default=0)
    total_received_vpn = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent_vpn = db.Column(db.BigInteger, nullable=False, default=0)
    total_received_antizapret = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent_antizapret = db.Column(db.BigInteger, nullable=False, default=0)
    total_sessions = db.Column(db.Integer, nullable=False, default=0)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserTrafficStatProtocol(db.Model):
    __tablename__ = "user_traffic_stat_protocol"

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(255), nullable=False, index=True)
    protocol_type = db.Column(db.String(20), nullable=False, default="openvpn", index=True)
    total_received = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent = db.Column(db.BigInteger, nullable=False, default=0)
    total_received_vpn = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent_vpn = db.Column(db.BigInteger, nullable=False, default=0)
    total_received_antizapret = db.Column(db.BigInteger, nullable=False, default=0)
    total_sent_antizapret = db.Column(db.BigInteger, nullable=False, default=0)
    total_sessions = db.Column(db.Integer, nullable=False, default=0)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "common_name",
            "protocol_type",
            name="uq_user_traffic_stat_protocol_name_type",
        ),
    )


class TrafficSessionState(db.Model):
    __tablename__ = "traffic_session_state"

    id = db.Column(db.Integer, primary_key=True)
    session_key = db.Column(db.String(512), unique=True, nullable=False, index=True)
    profile = db.Column(db.String(64), nullable=False)
    common_name = db.Column(db.String(255), nullable=False, index=True)
    real_address = db.Column(db.String(255), nullable=True)
    virtual_address = db.Column(db.String(255), nullable=True)
    connected_since_ts = db.Column(db.BigInteger, nullable=False, default=0)
    last_bytes_received = db.Column(db.BigInteger, nullable=False, default=0)
    last_bytes_sent = db.Column(db.BigInteger, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)


class UserTrafficSample(db.Model):
    __tablename__ = "user_traffic_sample"

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(255), nullable=False, index=True)
    network_type = db.Column(db.String(20), nullable=False, index=True)
    protocol_type = db.Column(db.String(20), nullable=False, default="openvpn", index=True)
    delta_received = db.Column(db.BigInteger, nullable=False, default=0)
    delta_sent = db.Column(db.BigInteger, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index(
            "ix_user_traffic_sample_common_name_created_at",
            "common_name",
            "created_at",
        ),
        db.Index(
            "ix_user_traffic_sample_created_at_common_name_protocol_type",
            "created_at",
            "common_name",
            "protocol_type",
        ),
    )


class OpenVPNPeerInfoCache(db.Model):
    __tablename__ = "openvpn_peer_info_cache"

    id = db.Column(db.Integer, primary_key=True)
    profile = db.Column(db.String(64), nullable=False, index=True)
    client_name = db.Column(db.String(255), nullable=False, index=True)
    ip = db.Column(db.String(64), nullable=False, index=True)
    endpoint = db.Column(db.String(255), nullable=True)
    version = db.Column(db.String(128), nullable=True)
    platform = db.Column(db.String(64), nullable=True)
    last_event_rank = db.Column(db.BigInteger, nullable=False, default=0, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "profile",
            "client_name",
            "ip",
            name="uq_openvpn_peer_info_profile_client_ip",
        ),
    )


class OpenVPNPeerInfoHistory(db.Model):
    __tablename__ = "openvpn_peer_info_history"

    id = db.Column(db.Integer, primary_key=True)
    profile = db.Column(db.String(64), nullable=False, index=True)
    client_name = db.Column(db.String(255), nullable=False, index=True)
    ip = db.Column(db.String(64), nullable=False, index=True)
    endpoint = db.Column(db.String(255), nullable=True)
    version = db.Column(db.String(128), nullable=True)
    platform = db.Column(db.String(64), nullable=True)
    event_rank = db.Column(db.BigInteger, nullable=False, default=0, index=True)
    observed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint(
            "profile",
            "client_name",
            "ip",
            "event_rank",
            name="uq_openvpn_peer_info_history_event",
        ),
    )


class WireGuardPeerCache(db.Model):
    __tablename__ = "wireguard_peer_cache"

    id = db.Column(db.Integer, primary_key=True)
    interface_name = db.Column(db.String(32), nullable=False, index=True)
    peer_public_key = db.Column(db.String(128), nullable=False, index=True)
    client_name = db.Column(db.String(255), nullable=False, index=True)
    allowed_ips = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "interface_name",
            "peer_public_key",
            name="uq_wireguard_peer_iface_key",
        ),
    )


class ActiveWebSession(db.Model):
    __tablename__ = "active_web_session"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), nullable=False, index=True)
    remote_addr = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class BackgroundTask(db.Model):
    __tablename__ = "background_task"

    id = db.Column(db.String(32), primary_key=True)
    task_type = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="queued", index=True)
    created_by_username = db.Column(db.String(80), nullable=True, index=True)
    message = db.Column(db.String(255), nullable=True)
    output = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index(
            "ix_background_task_task_type_status_created_at",
            "task_type",
            "status",
            "created_at",
        ),
    )


class LogsDashboardCache(db.Model):
    __tablename__ = "logs_dashboard_cache"

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(32), unique=True, nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_error = db.Column(db.String(255), nullable=True)
