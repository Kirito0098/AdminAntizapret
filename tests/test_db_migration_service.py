import os
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine.base import Connection

from core.models import db
from core.services.db_migration import DatabaseMigrationService


class DatabaseMigrationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "migration_test.sqlite")

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

        self.service = DatabaseMigrationService(app=self.app, db=db)

    def tearDown(self) -> None:
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp_dir.cleanup()

    def _prepare_legacy_viewer_access_table(self) -> None:
        with self.app.app_context():
            with db.engine.connect() as conn:
                conn.execute(text("DELETE FROM viewer_config_access"))
                conn.execute(
                    text(
                        "INSERT OR REPLACE INTO \"user\" (id, username, password_hash, role) "
                        "VALUES (1, 'viewer', 'hash', 'viewer')"
                    )
                )
                conn.execute(text("DROP TABLE viewer_config_access"))
                conn.execute(
                    text(
                        "CREATE TABLE viewer_config_access ("
                        "id INTEGER NOT NULL PRIMARY KEY, "
                        "user_id INTEGER NOT NULL, "
                        "config_name VARCHAR(255) NOT NULL, "
                        "FOREIGN KEY(user_id) REFERENCES \"user\" (id), "
                        "UNIQUE(user_id, config_name)"
                        ")"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO viewer_config_access (id, user_id, config_name) "
                        "VALUES (1, 1, 'client.conf')"
                    )
                )
                conn.commit()

    def test_viewer_access_migration_recovers_from_stale_temp_table(self) -> None:
        self._prepare_legacy_viewer_access_table()

        with self.app.app_context():
            with db.engine.connect() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE viewer_config_access_new ("
                        "id INTEGER NOT NULL PRIMARY KEY, "
                        "user_id INTEGER NOT NULL, "
                        "config_type VARCHAR(20) NOT NULL, "
                        "config_name VARCHAR(255) NOT NULL"
                        ")"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO viewer_config_access_new (id, user_id, config_type, config_name) "
                        "VALUES (1, 1, 'openvpn', 'stale.conf')"
                    )
                )
                conn.commit()

        self.service.run_db_migrations()

        with self.app.app_context():
            insp = sa_inspect(db.engine)
            cols = {col["name"] for col in insp.get_columns("viewer_config_access")}
            self.assertIn("config_type", cols)
            self.assertFalse(insp.has_table("viewer_config_access_new"))

            with db.engine.connect() as conn:
                migrated_rows = conn.execute(
                    text(
                        "SELECT user_id, config_type, config_name "
                        "FROM viewer_config_access ORDER BY id"
                    )
                ).fetchall()
                index_rows = conn.execute(text("PRAGMA index_list('viewer_config_access')")).fetchall()

        self.assertEqual([tuple(row) for row in migrated_rows], [(1, "openvpn", "client.conf")])
        self.assertIn("unique_user_config_type", {row[1] for row in index_rows})

    def test_viewer_access_migration_reenables_foreign_keys_after_error(self) -> None:
        self._prepare_legacy_viewer_access_table()

        executed_sql: list[str] = []
        original_execute = Connection.execute
        fail_once = {"value": True}

        def _execute_with_forced_insert_error(connection, statement, *args, **kwargs):
            sql = str(statement)
            executed_sql.append(sql)
            if fail_once["value"] and "INSERT INTO viewer_config_access_new" in sql:
                fail_once["value"] = False
                raise RuntimeError("forced insert failure")
            return original_execute(connection, statement, *args, **kwargs)

        with patch("sqlalchemy.engine.base.Connection.execute", new=_execute_with_forced_insert_error):
            self.service.run_db_migrations()

        off_index = next(i for i, sql in enumerate(executed_sql) if "PRAGMA foreign_keys=OFF" in sql)
        on_index = next(i for i, sql in enumerate(executed_sql) if "PRAGMA foreign_keys=ON" in sql)
        self.assertGreater(on_index, off_index)

        # Повторный запуск после частичного сбоя должен завершаться успешно.
        self.service.run_db_migrations()

        with self.app.app_context():
            cols = {col["name"] for col in sa_inspect(db.engine).get_columns("viewer_config_access")}
        self.assertIn("config_type", cols)


if __name__ == "__main__":
    unittest.main()
