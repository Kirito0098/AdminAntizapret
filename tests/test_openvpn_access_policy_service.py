import os
import tempfile
import unittest
from datetime import datetime, timedelta

from flask import Flask

from core.models import OpenVpnAccessPolicy, db
from core.services.openvpn_access_policy import OpenVpnAccessPolicyService


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
        self.service = OpenVpnAccessPolicyService(
            db=db,
            policy_model=OpenVpnAccessPolicy,
            read_banned_clients=lambda: set(self.banlist),
            write_banned_clients=lambda clients: self.banlist.clear() or self.banlist.update(set(clients)),
            ensure_client_connect_ban_check_block=lambda: None,
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


if __name__ == "__main__":
    unittest.main()
