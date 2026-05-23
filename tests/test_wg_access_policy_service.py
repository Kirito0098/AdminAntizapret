import os
import tempfile
import unittest
from datetime import datetime, timedelta

from flask import Flask

from core.models import WgAccessPolicy, db
from core.services.wg_access_policy import (
    EXPIRED_REQUIRES_EXTEND_CODE,
    ExpiredRequiresExtendError,
    WgAccessPolicyService,
)


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

        self.service = WgAccessPolicyService(
            db=db,
            policy_model=WgAccessPolicy,
            runtime_enforcer=None,
            use_subprocess_runtime=False,
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


if __name__ == "__main__":
    unittest.main()
