import os
import tempfile
import unittest
from datetime import datetime, timedelta

from flask import Flask

from core.models import WgAccessPolicy, db
from core.services.traffic_limit import (
    TrafficLimitExceededError,
    parse_traffic_limit_bytes,
    parse_traffic_limit_period_days,
)
from core.services.wg_access_policy import (
    EXPIRED_REQUIRES_EXTEND_CODE,
    ExpiredRequiresExtendError,
    WgAccessPolicyService,
)


class TrafficLimitUtilsTests(unittest.TestCase):
    def test_parse_traffic_limit_bytes(self):
        self.assertEqual(parse_traffic_limit_bytes(10, "mb"), 10 * 1024 * 1024)
        self.assertEqual(parse_traffic_limit_bytes(2, "gb"), 2 * 1024 * 1024 * 1024)

    def test_parse_traffic_limit_period_days(self):
        self.assertEqual(parse_traffic_limit_period_days("7"), 7)
        self.assertEqual(parse_traffic_limit_period_days(30), 30)
        with self.assertRaises(ValueError):
            parse_traffic_limit_period_days("14")


class WgAccessPolicyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "wg_policy.sqlite")

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

        self.consumed_by_client = {}

        def get_consumed(client_name, period_days=None):
            key = (client_name, period_days)
            if key in self.consumed_by_client:
                return int(self.consumed_by_client[key])
            return int(self.consumed_by_client.get(client_name, 0))

        self.service = WgAccessPolicyService(
            db=db,
            policy_model=WgAccessPolicy,
            runtime_enforcer=None,
            use_subprocess_runtime=False,
            get_consumed_traffic_bytes=get_consumed,
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp_dir.cleanup()

    def test_clear_block_rejects_expired_access(self):
        with self.app.app_context():
            row = WgAccessPolicy(
                client_name="expired-user",
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            db.session.add(row)
            db.session.commit()

            with self.assertRaises(ExpiredRequiresExtendError) as ctx:
                self.service.clear_block("expired-user", actor_username="admin")

        self.assertEqual(ctx.exception.error_code, EXPIRED_REQUIRES_EXTEND_CODE)

    def test_extend_after_expiry_unblocks_client(self):
        with self.app.app_context():
            row = WgAccessPolicy(
                client_name="renew-user",
                expires_at=datetime.utcnow() - timedelta(hours=2),
            )
            db.session.add(row)
            db.session.commit()

            self.service.set_expiry_days("renew-user", 30, actor_username="admin", extend=True)
            result = self.service.reconcile_client_policy("renew-user", apply_runtime=False)
            state = result["state"]

        self.assertFalse(state["is_blocked"])
        self.assertIsNone(state["reason"])
        self.assertEqual(state["block_mode"], "none")

    def test_traffic_limit_blocks_client(self):
        self.consumed_by_client["traffic-user"] = 1500
        with self.app.app_context():
            self.service.set_traffic_limit_bytes("traffic-user", 1000, actor_username="admin")
            result = self.service.reconcile_client_policy("traffic-user", apply_runtime=False)
            state = result["state"]

        self.assertTrue(state["is_blocked"])
        self.assertEqual(state["reason"], "traffic_limit")
        self.assertEqual(state["block_mode"], "traffic_limit")

    def test_clear_block_rejects_traffic_limit(self):
        self.consumed_by_client["traffic-user"] = 1500
        with self.app.app_context():
            self.service.set_traffic_limit_bytes("traffic-user", 1000, actor_username="admin")
            with self.assertRaises(TrafficLimitExceededError):
                self.service.clear_block("traffic-user", actor_username="admin")

    def test_increasing_traffic_limit_unblocks_client(self):
        self.consumed_by_client["traffic-user"] = 1500
        with self.app.app_context():
            self.service.set_traffic_limit_bytes("traffic-user", 1000, actor_username="admin")
            self.service.set_traffic_limit_bytes("traffic-user", 2000, actor_username="admin")
            result = self.service.reconcile_client_policy("traffic-user", apply_runtime=False)
            state = result["state"]

        self.assertFalse(state["is_blocked"])
        self.assertIsNone(state["reason"])

    def test_traffic_limit_stores_period_days(self):
        self.consumed_by_client[("period-user", 7)] = 500
        with self.app.app_context():
            self.service.set_traffic_limit_bytes(
                "period-user",
                1000,
                period_days=7,
                actor_username="admin",
            )
            row = WgAccessPolicy.query.filter_by(client_name="period-user").first()
            result = self.service.reconcile_client_policy("period-user", apply_runtime=False)
            state = result["state"]

        self.assertEqual(row.traffic_limit_period_days, 7)
        self.assertEqual(state["traffic_limit_period_days"], 7)
        self.assertEqual(state["traffic_limit_period_label"], "за неделю (пн–вс)")
        self.assertFalse(state["is_blocked"])

    def test_traffic_limit_auto_unblocks_on_new_period(self):
        self.consumed_by_client[("traffic-user", 1)] = 1500
        with self.app.app_context():
            self.service.set_traffic_limit_bytes(
                "traffic-user",
                1000,
                period_days=1,
                actor_username="admin",
            )
            blocked = self.service.reconcile_client_policy("traffic-user", apply_runtime=False)
            self.assertTrue(blocked["state"]["is_blocked"])

            self.consumed_by_client[("traffic-user", 1)] = 0
            unblocked = self.service.reconcile_client_policy("traffic-user", apply_runtime=False)
            state = unblocked["state"]

        self.assertFalse(state["is_blocked"])
        self.assertIsNone(state["reason"])
        self.assertEqual(state["block_mode"], "none")


if __name__ == "__main__":
    unittest.main()
