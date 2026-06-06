import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from flask import Flask

from core.models import UserTrafficSample, UserTrafficStatProtocol, db
from core.services.traffic_limit import (
    format_traffic_limit_period_label,
    format_traffic_limit_unblock_at,
    get_client_consumed_traffic_bytes,
    get_traffic_limit_period_bounds,
    get_traffic_limit_period_start,
    resolve_traffic_limit_state,
)


class TrafficLimitPeriodBoundsTests(unittest.TestCase):
    def test_daily_period_bounds(self):
        now = datetime(2026, 6, 6, 15, 30, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(1, now=now)

        self.assertEqual(start, datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 6, 7, 0, 0, tzinfo=timezone.utc))

    def test_weekly_period_bounds_monday(self):
        now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(7, now=now)

        self.assertEqual(start, datetime(2026, 6, 8, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc))

    def test_weekly_period_bounds_sunday(self):
        now = datetime(2026, 6, 14, 23, 59, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(7, now=now)

        self.assertEqual(start, datetime(2026, 6, 8, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc))

    def test_monthly_period_bounds(self):
        now = datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(30, now=now)

        self.assertEqual(start, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc))

    def test_monthly_period_bounds_december(self):
        now = datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc)
        start, end = get_traffic_limit_period_bounds(30, now=now)

        self.assertEqual(start, datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc))

    def test_period_labels(self):
        self.assertEqual(format_traffic_limit_period_label(1), "за сутки (календарный день)")
        self.assertEqual(format_traffic_limit_period_label(7), "за неделю (пн–вс)")
        self.assertEqual(format_traffic_limit_period_label(30), "за месяц")

    def test_unblock_at_daily(self):
        now = datetime(2026, 6, 6, 15, 30, tzinfo=timezone.utc)
        unblock_at, label = format_traffic_limit_unblock_at(1, now=now)

        self.assertEqual(unblock_at, "2026-06-07 00:00:00")
        self.assertEqual(label, "Авторазблокировка: 07.06.2026 00:00 UTC")

    def test_unblock_at_weekly(self):
        now = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
        unblock_at, label = format_traffic_limit_unblock_at(7, now=now)

        self.assertEqual(unblock_at, "2026-06-15 00:00:00")
        self.assertIn("15.06.2026 00:00 UTC", label)
        self.assertIn("(пн)", label)

    def test_unblock_at_monthly(self):
        now = datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc)
        unblock_at, label = format_traffic_limit_unblock_at(30, now=now)

        self.assertEqual(unblock_at, "2026-07-01 00:00:00")
        self.assertEqual(label, "Авторазблокировка: 01.07.2026 00:00 UTC")

    def test_resolve_traffic_limit_state_includes_unblock_label(self):
        state = resolve_traffic_limit_state(
            traffic_limit_bytes=1024,
            traffic_limit_period_days=7,
            consumed_bytes=2048,
        )

        self.assertTrue(state["traffic_limit_exceeded"])
        self.assertIsNotNone(state["traffic_limit_unblock_at"])
        self.assertTrue(state["traffic_limit_unblock_label"].startswith("Авторазблокировка:"))


class TrafficLimitConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "traffic_limit.sqlite")

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp_dir.cleanup()

    def _add_sample(self, *, common_name, created_at, delta_received=0, delta_sent=0):
        sample = UserTrafficSample(
            common_name=common_name,
            network_type="vpn",
            protocol_type="openvpn",
            delta_received=delta_received,
            delta_sent=delta_sent,
            created_at=created_at,
        )
        db.session.add(sample)
        db.session.commit()

    def test_daily_consumption_ignores_previous_day(self):
        now = datetime(2026, 6, 6, 1, 0, tzinfo=timezone.utc)
        with self.app.app_context():
            self._add_sample(
                common_name="alice",
                created_at=datetime(2026, 6, 5, 23, 0),
                delta_received=900,
                delta_sent=100,
            )
            self._add_sample(
                common_name="alice",
                created_at=datetime(2026, 6, 6, 0, 30),
                delta_received=300,
                delta_sent=50,
            )
            consumed = get_client_consumed_traffic_bytes(
                db=db,
                user_traffic_stat_protocol_model=UserTrafficStatProtocol,
                user_traffic_sample_model=UserTrafficSample,
                client_name="alice",
                normalize_identity=lambda value: (value or "").strip().lower(),
                period_days=1,
                now=now,
            )

        self.assertEqual(consumed, 350)

    def test_weekly_consumption_ignores_previous_week(self):
        now = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)
        with self.app.app_context():
            self._add_sample(
                common_name="bob",
                created_at=datetime(2026, 6, 7, 23, 0),
                delta_received=5000,
            )
            self._add_sample(
                common_name="bob",
                created_at=datetime(2026, 6, 8, 10, 0),
                delta_received=200,
                delta_sent=50,
            )
            consumed = get_client_consumed_traffic_bytes(
                db=db,
                user_traffic_stat_protocol_model=UserTrafficStatProtocol,
                user_traffic_sample_model=UserTrafficSample,
                client_name="bob",
                normalize_identity=lambda value: (value or "").strip().lower(),
                period_days=7,
                now=now,
            )

        self.assertEqual(consumed, 250)

    def test_monthly_consumption_ignores_previous_month(self):
        now = datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc)
        with self.app.app_context():
            self._add_sample(
                common_name="carol",
                created_at=datetime(2026, 6, 30, 22, 0),
                delta_received=8000,
            )
            self._add_sample(
                common_name="carol",
                created_at=datetime(2026, 7, 1, 9, 0),
                delta_received=100,
            )
            consumed = get_client_consumed_traffic_bytes(
                db=db,
                user_traffic_stat_protocol_model=UserTrafficStatProtocol,
                user_traffic_sample_model=UserTrafficSample,
                client_name="carol",
                normalize_identity=lambda value: (value or "").strip().lower(),
                period_days=30,
                now=now,
            )

        self.assertEqual(consumed, 100)

    def test_period_start_midnight_boundary(self):
        old_period = datetime(2026, 6, 5, 23, 59, tzinfo=timezone.utc)
        new_period = datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc)

        old_start = get_traffic_limit_period_start(1, now=old_period)
        new_start = get_traffic_limit_period_start(1, now=new_period)

        self.assertNotEqual(old_start, new_start)
        self.assertEqual(new_start, datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
