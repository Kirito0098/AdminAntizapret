import logging

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text


logger = logging.getLogger(__name__)


class DatabaseMigrationService:
    def __init__(self, *, app, db):
        self.app = app
        self.db = db

    def run_db_migrations(self):
        """Apply incremental DB schema migrations."""
        with self.app.app_context():
            self.db.create_all()
            try:
                insp = sa_inspect(self.db.engine)
                cols = [c["name"] for c in insp.get_columns("user")]
                if "role" not in cols:
                    with self.db.engine.connect() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE \"user\" ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'"
                            )
                        )
                        conn.commit()

                if "telegram_id" not in cols:
                    with self.db.engine.connect() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE \"user\" ADD COLUMN telegram_id VARCHAR(32)"
                            )
                        )
                        conn.commit()

                with self.db.engine.connect() as conn:
                    conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_telegram_id ON \"user\" (telegram_id)"
                        )
                    )
                    conn.commit()

                if insp.has_table("user_traffic_stat"):
                    traffic_cols = {c["name"] for c in insp.get_columns("user_traffic_stat")}
                    traffic_missing = {
                        "total_received_vpn": "ALTER TABLE user_traffic_stat ADD COLUMN total_received_vpn BIGINT NOT NULL DEFAULT 0",
                        "total_sent_vpn": "ALTER TABLE user_traffic_stat ADD COLUMN total_sent_vpn BIGINT NOT NULL DEFAULT 0",
                        "total_received_antizapret": "ALTER TABLE user_traffic_stat ADD COLUMN total_received_antizapret BIGINT NOT NULL DEFAULT 0",
                        "total_sent_antizapret": "ALTER TABLE user_traffic_stat ADD COLUMN total_sent_antizapret BIGINT NOT NULL DEFAULT 0",
                    }
                    with self.db.engine.connect() as conn:
                        for col_name, alter_sql in traffic_missing.items():
                            if col_name not in traffic_cols:
                                conn.execute(text(alter_sql))
                        conn.commit()

                if insp.has_table("user_traffic_sample"):
                    sample_cols = {c["name"] for c in insp.get_columns("user_traffic_sample")}
                    sample_missing = {
                        "protocol_type": "ALTER TABLE user_traffic_sample ADD COLUMN protocol_type VARCHAR(20) NOT NULL DEFAULT 'openvpn'",
                    }
                    with self.db.engine.connect() as conn:
                        for col_name, alter_sql in sample_missing.items():
                            if col_name not in sample_cols:
                                conn.execute(text(alter_sql))
                        conn.commit()

                if insp.has_table("qr_download_token"):
                    qr_cols = {c["name"] for c in insp.get_columns("qr_download_token")}
                    qr_missing = {
                        "max_downloads": "ALTER TABLE qr_download_token ADD COLUMN max_downloads INTEGER NOT NULL DEFAULT 1",
                        "download_count": "ALTER TABLE qr_download_token ADD COLUMN download_count INTEGER NOT NULL DEFAULT 0",
                        "pin_hash": "ALTER TABLE qr_download_token ADD COLUMN pin_hash VARCHAR(64)",
                    }
                    with self.db.engine.connect() as conn:
                        for col_name, alter_sql in qr_missing.items():
                            if col_name not in qr_cols:
                                conn.execute(text(alter_sql))
                        conn.commit()
            except Exception as exc:
                logger.warning("DB migration warning: %s", exc, exc_info=True)
