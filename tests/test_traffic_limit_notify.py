import os
import tempfile
import unittest
from unittest.mock import MagicMock

from core.models import OpenVpnAccessPolicy, WgAccessPolicy, db
from core.services.traffic_limit_notify import TrafficLimitNotifyService


class TrafficLimitNotifyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "traffic_limit_notify.sqlite")
        from flask import Flask

        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(self.app)

        with self.app.app_context():
            db.create_all()

        self.consumed_by_client = {}
        self.sent_events = []

        def _get_consumed(client_name, period_days=None):
            key = (client_name, period_days) if period_days else client_name
            return int(self.consumed_by_client.get(key, 0))

        from core.services.wg_access_policy import WgAccessPolicyService
        from core.services.openvpn_access_policy import OpenVpnAccessPolicyService

        self.wg_service = WgAccessPolicyService(
            db=db,
            policy_model=WgAccessPolicy,
            use_subprocess_runtime=False,
            get_consumed_traffic_bytes=_get_consumed,
        )
        self.ovpn_service = OpenVpnAccessPolicyService(
            db=db,
            policy_model=OpenVpnAccessPolicy,
            read_banned_clients=lambda: set(),
            write_banned_clients=lambda _clients: None,
            ensure_client_connect_ban_check_block=lambda: None,
            get_consumed_traffic_bytes=_get_consumed,
        )

        admin_notify = MagicMock()
        admin_notify.send = lambda event_type, **kwargs: self.sent_events.append(
            {"event_type": event_type, **kwargs}
        )

        self.notify_service = TrafficLimitNotifyService(
            admin_notify_service=admin_notify,
            wg_access_policy_service=self.wg_service,
            openvpn_access_policy_service=self.ovpn_service,
            config_paths={"wg": [], "amneziawg": [], "openvpn": []},
            extract_client_name_from_config_file=lambda _path: "",
            logger=MagicMock(),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_block_notification_on_first_exceed(self):
        self.consumed_by_client["notify-user"] = 2000
        with self.app.app_context():
            self.wg_service.set_traffic_limit_bytes("notify-user", 1000, actor_username="admin")
            self.sent_events.clear()
            self.notify_service.process_client(protocol_scope="wg", client_name="notify-user")

        self.assertEqual(len(self.sent_events), 1)
        self.assertEqual(self.sent_events[0]["event_type"], "traffic_limit_block")
        self.assertEqual(self.sent_events[0]["target_name"], "notify-user")

    def test_block_notification_not_repeated_on_reconcile(self):
        self.consumed_by_client["notify-user"] = 2000
        with self.app.app_context():
            self.wg_service.set_traffic_limit_bytes("notify-user", 1000, actor_username="admin")
            self.sent_events.clear()
            self.notify_service.process_client(protocol_scope="wg", client_name="notify-user")
            self.notify_service.process_client(protocol_scope="wg", client_name="notify-user")
            self.notify_service.process_client(protocol_scope="wg", client_name="notify-user")

        self.assertEqual(len(self.sent_events), 1)

    def test_block_notification_after_service_restart_is_deduped(self):
        self.consumed_by_client["notify-user"] = 2000
        with self.app.app_context():
            self.wg_service.set_traffic_limit_bytes("notify-user", 1000, actor_username="admin")
            self.sent_events.clear()
            fresh_service = TrafficLimitNotifyService(
                admin_notify_service=MagicMock(
                    send=lambda event_type, **kwargs: self.sent_events.append(
                        {"event_type": event_type, **kwargs}
                    )
                ),
                wg_access_policy_service=self.wg_service,
                openvpn_access_policy_service=self.ovpn_service,
                config_paths={"wg": [], "amneziawg": [], "openvpn": []},
                extract_client_name_from_config_file=lambda _path: "",
                logger=MagicMock(),
            )
            fresh_service.process_client(protocol_scope="wg", client_name="notify-user")
            fresh_service.process_client(protocol_scope="wg", client_name="notify-user")

        self.assertEqual(len(self.sent_events), 1)
        self.assertEqual(self.sent_events[0]["event_type"], "traffic_limit_block")

    def test_auto_unblock_notification_on_new_period(self):
        self.consumed_by_client[("period-user", 1)] = 2000
        with self.app.app_context():
            self.wg_service.set_traffic_limit_bytes(
                "period-user",
                1000,
                period_days=1,
                actor_username="admin",
            )
            self.notify_service.process_client(protocol_scope="wg", client_name="period-user")
            self.assertEqual(len(self.sent_events), 1)
            self.assertEqual(self.sent_events[0]["event_type"], "traffic_limit_block")
            self.sent_events.clear()

            self.consumed_by_client[("period-user", 1)] = 0
            with self.notify_service._lock:
                cached = self.notify_service._client_state[("wg", "period-user")]
                cached["last_period_start"] = "2000-01-01T00:00:00+00:00"

            self.sent_events.clear()
            self.notify_service.process_client(protocol_scope="wg", client_name="period-user")

        self.assertEqual(len(self.sent_events), 1)
        self.assertEqual(self.sent_events[0]["event_type"], "traffic_limit_unblock")

    def test_no_unblock_notification_when_limit_increased_same_period(self):
        self.consumed_by_client["notify-user"] = 2000
        with self.app.app_context():
            self.wg_service.set_traffic_limit_bytes("notify-user", 1000, actor_username="admin")
            self.notify_service.process_client(protocol_scope="wg", client_name="notify-user")
            self.sent_events.clear()
            self.wg_service.set_traffic_limit_bytes("notify-user", 3000, actor_username="admin")
            self.notify_service.process_client(protocol_scope="wg", client_name="notify-user")

        unblock_events = [e for e in self.sent_events if e["event_type"] == "traffic_limit_unblock"]
        self.assertEqual(unblock_events, [])


if __name__ == "__main__":
    unittest.main()
