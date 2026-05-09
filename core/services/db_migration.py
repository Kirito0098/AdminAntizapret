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
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_user_role ON \"user\" (role)"
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
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_user_traffic_sample_common_name_created_at "
                                "ON user_traffic_sample (common_name, created_at)"
                            )
                        )
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_user_traffic_sample_created_at_common_name_protocol_type "
                                "ON user_traffic_sample (created_at, common_name, protocol_type)"
                            )
                        )
                        conn.commit()

                if insp.has_table("background_task"):
                    with self.db.engine.connect() as conn:
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_background_task_task_type_status_created_at "
                                "ON background_task (task_type, status, created_at)"
                            )
                        )
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

                if insp.has_table("viewer_config_access"):
                    viewer_cols = {c["name"] for c in insp.get_columns("viewer_config_access")}
                    viewer_uniques = insp.get_unique_constraints("viewer_config_access") or []

                    has_legacy_unique = any(
                        set(cons.get("column_names") or []) == {"user_id", "config_name"}
                        for cons in viewer_uniques
                    )
                    has_new_unique = any(
                        set(cons.get("column_names") or []) == {"user_id", "config_type", "config_name"}
                        for cons in viewer_uniques
                    )

                    with self.db.engine.connect() as conn:
                        if "config_type" not in viewer_cols:
                            conn.execute(
                                text(
                                    "ALTER TABLE viewer_config_access "
                                    "ADD COLUMN config_type VARCHAR(20) NOT NULL DEFAULT 'openvpn'"
                                )
                            )
                            conn.commit()

                        # SQLite не умеет удалять legacy UNIQUE constraint через ALTER TABLE,
                        # поэтому пересоздаем таблицу при переходе на протокольную уникальность.
                        if has_legacy_unique and not has_new_unique:
                            fk_disabled = False
                            migration_error = None
                            try:
                                conn.execute(text("PRAGMA foreign_keys=OFF"))
                                fk_disabled = True
                                # На случай частичного падения прошлого запуска всегда собираем
                                # временную таблицу заново, чтобы избежать PK-конфликтов.
                                conn.execute(text("DROP TABLE IF EXISTS viewer_config_access_new"))
                                conn.execute(
                                    text(
                                        "CREATE TABLE viewer_config_access_new ("
                                        "id INTEGER NOT NULL PRIMARY KEY, "
                                        "user_id INTEGER NOT NULL, "
                                        "config_type VARCHAR(20) NOT NULL, "
                                        "config_name VARCHAR(255) NOT NULL, "
                                        "FOREIGN KEY(user_id) REFERENCES \"user\" (id)"
                                        ")"
                                    )
                                )
                                conn.execute(
                                    text(
                                        "INSERT INTO viewer_config_access_new (id, user_id, config_type, config_name) "
                                        "SELECT id, user_id, COALESCE(NULLIF(config_type, ''), 'openvpn'), config_name "
                                        "FROM viewer_config_access"
                                    )
                                )
                                conn.execute(text("DROP TABLE viewer_config_access"))
                                conn.execute(text("ALTER TABLE viewer_config_access_new RENAME TO viewer_config_access"))
                            except Exception as exc:
                                migration_error = exc
                            finally:
                                if fk_disabled:
                                    conn.execute(text("PRAGMA foreign_keys=ON"))
                                conn.commit()
                            if migration_error is not None:
                                raise migration_error

                    with self.db.engine.connect() as conn:
                        conn.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS unique_user_config_type "
                                "ON viewer_config_access (user_id, config_type, config_name)"
                            )
                        )
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_viewer_config_access_user_id "
                                "ON viewer_config_access (user_id)"
                            )
                        )
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_viewer_config_access_user_type_name "
                                "ON viewer_config_access (user_id, config_type, config_name)"
                            )
                        )
                        conn.commit()

                if insp.has_table("provider_meta"):
                    provider_meta_cols = {c["name"] for c in insp.get_columns("provider_meta")}
                    provider_meta_missing = {
                        "expected_asn_min": "ALTER TABLE provider_meta ADD COLUMN expected_asn_min INTEGER NOT NULL DEFAULT 0",
                        "asn_count": "ALTER TABLE provider_meta ADD COLUMN asn_count INTEGER NOT NULL DEFAULT 0",
                        "active_asn_count": "ALTER TABLE provider_meta ADD COLUMN active_asn_count INTEGER NOT NULL DEFAULT 0",
                        "anomaly_level": "ALTER TABLE provider_meta ADD COLUMN anomaly_level VARCHAR(16) NOT NULL DEFAULT 'none'",
                        "anomaly_reason": "ALTER TABLE provider_meta ADD COLUMN anomaly_reason VARCHAR(512)",
                    }
                    with self.db.engine.connect() as conn:
                        for col_name, alter_sql in provider_meta_missing.items():
                            if col_name not in provider_meta_cols:
                                conn.execute(text(alter_sql))
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_provider_meta_anomaly_level "
                                "ON provider_meta (anomaly_level)"
                            )
                        )
                        conn.commit()

                if insp.has_table("provider_asn"):
                    with self.db.engine.connect() as conn:
                        conn.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_asn_key_asn "
                                "ON provider_asn (provider_key, asn)"
                            )
                        )
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_provider_asn_provider_active "
                                "ON provider_asn (provider_key, active)"
                            )
                        )
                        conn.commit()

                if insp.has_table("provider_asn_snapshot"):
                    with self.db.engine.connect() as conn:
                        conn.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_asn_snapshot "
                                "ON provider_asn_snapshot (refresh_log_id, provider_key, asn)"
                            )
                        )
                        conn.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS ix_provider_asn_snapshot_provider_refresh "
                                "ON provider_asn_snapshot (provider_key, refresh_log_id)"
                            )
                        )
                        conn.commit()
            except Exception as exc:
                logger.warning("DB migration warning: %s", exc, exc_info=True)
