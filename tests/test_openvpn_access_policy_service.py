import os
import tempfile
import unittest
from datetime import datetime, timedelta

from flask import Flask

from core.models import OpenVpnAccessPolicy, db
from core.services.openvpn_access_policy import OpenVpnAccessPolicyService
from core.services.traffic_limit import TrafficLimitExceededError


class OpenVpnAccessPolicyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "openvpn_policy.sqlite")

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

        self.banlist = set()
        self.consumed_by_client = {}

        def get_consumed(client_name, period_days=None):
            key = (client_name, period_days)
            if key in self.consumed_by_client:
                return int(self.consumed_by_client[key])
            return int(self.consumed_by_client.get(client_name, 0))

        self.service = OpenVpnAccessPolicyService(
            db=db,
            policy_model=OpenVpnAccessPolicy,
            read_banned_clients=lambda: set(self.banlist),
            write_banned_clients=lambda clients: self.banlist.clear() or self.banlist.update(set(clients)),
            ensure_client_connect_ban_check_block=lambda: None,
            get_consumed_traffic_bytes=get_consumed,
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp_dir.cleanup()

    def test_temp_block_reapplies_from_now(self):
        with self.app.app_context():
            self.service.set_temp_block_days("alice", 1, actor_username="admin")
            first = OpenVpnAccessPolicy.query.filter_by(client_name="alice").first()
            first_until = first.block_until

            self.service.set_temp_block_days("alice", 10, actor_username="admin")
            second = OpenVpnAccessPolicy.query.filter_by(client_name="alice").first()

        self.assertIsNotNone(first_until)
        self.assertIsNotNone(second.block_until)
        self.assertGreater(second.block_until, first_until)
        self.assertLessEqual(second.block_until, datetime.utcnow() + timedelta(days=10, minutes=1))
        self.assertIn("alice", self.banlist)

    def test_permanent_to_temp_switch(self):
        with self.app.app_context():
            self.service.set_permanent_block("bob", actor_username="admin")
            self.service.set_temp_block_days("bob", 3, actor_username="admin")
            row = OpenVpnAccessPolicy.query.filter_by(client_name="bob").first()

        self.assertTrue(row.is_temp_blocked)
        self.assertFalse(row.is_permanent_blocked)
        self.assertEqual(row.block_reason, "manual_temp")
        self.assertIsNotNone(row.block_until)

    def test_unblock_clears_banlist(self):
        with self.app.app_context():
            self.service.set_permanent_block("carol", actor_username="admin")
            self.assertIn("carol", self.banlist)
            self.service.clear_block("carol", actor_username="admin")
            row = OpenVpnAccessPolicy.query.filter_by(client_name="carol").first()

        self.assertFalse(row.is_temp_blocked)
        self.assertFalse(row.is_permanent_blocked)
        self.assertIsNone(row.block_reason)
        self.assertNotIn("carol", self.banlist)

    def test_traffic_limit_blocks_client(self):
        self.consumed_by_client["dave"] = 2048
        with self.app.app_context():
            self.service.set_traffic_limit_bytes("dave", 1024, actor_username="admin")
            result = self.service.reconcile_client_policy("dave")
            state = result["state"]

        self.assertTrue(state["is_blocked"])
        self.assertEqual(state["reason"], "traffic_limit")
        self.assertIn("dave", self.banlist)

    def test_reconcile_all_does_not_mark_traffic_limit_as_permanent(self):
        self.consumed_by_client["dave"] = 2048
        with self.app.app_context():
            self.service.set_traffic_limit_bytes("dave", 1024, actor_username="admin")
            self.service.reconcile_all()
            row = OpenVpnAccessPolicy.query.filter_by(client_name="dave").first()
            state = self.service._resolve_effective_state(row)

        self.assertFalse(row.is_permanent_blocked)
        self.assertEqual(state["reason"], "traffic_limit")
        self.assertEqual(state["block_mode"], "traffic_limit")

    def test_clear_block_rejects_traffic_limit(self):
        self.consumed_by_client["dave"] = 2048
        with self.app.app_context():
            self.service.set_traffic_limit_bytes("dave", 1024, actor_username="admin")
            with self.assertRaises(TrafficLimitExceededError):
                self.service.clear_block("dave", actor_username="admin")

    def test_traffic_limit_period_blocks_by_window(self):
        self.consumed_by_client[("dave", 1)] = 2048
        with self.app.app_context():
            self.service.set_traffic_limit_bytes(
                "dave",
                1024,
                period_days=1,
                actor_username="admin",
            )
            result = self.service.reconcile_client_policy("dave")
            state = result["state"]

        self.assertTrue(state["is_blocked"])
        self.assertEqual(state["traffic_limit_period_days"], 1)
        self.assertEqual(state["traffic_limit_period_label"], "за сутки (календарный день)")

    def test_traffic_limit_auto_unblocks_on_new_period(self):
        self.consumed_by_client[("dave", 7)] = 5000
        with self.app.app_context():
            self.service.set_traffic_limit_bytes(
                "dave",
                1024,
                period_days=7,
                actor_username="admin",
            )
            blocked = self.service.reconcile_client_policy("dave")
            self.assertTrue(blocked["state"]["is_blocked"])
            self.assertIn("dave", self.banlist)

            self.consumed_by_client[("dave", 7)] = 0
            unblocked = self.service.reconcile_client_policy("dave")
            state = unblocked["state"]

        self.assertFalse(state["is_blocked"])
        self.assertIsNone(state["reason"])
        self.assertNotIn("dave", self.banlist)


if __name__ == "__main__":
    unittest.main()
