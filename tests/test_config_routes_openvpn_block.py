import unittest
from types import SimpleNamespace

from flask import Flask

from routes.config_routes import register_config_routes


class FakeAuthManager:
    def admin_required(self, fn):
        return fn

    def login_required(self, fn):
        return fn


class ConfigRoutesOpenVpnBlockTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["TESTING"] = True
        self.calls = []

        def ovpn_temp(client_name, days, actor_username=None):
            self.calls.append(("temp_block", client_name, days, actor_username))
            return SimpleNamespace(block_until=None)

        def ovpn_perm(client_name, actor_username=None):
            self.calls.append(("permanent_block", client_name, actor_username))
            return SimpleNamespace(block_until=None)

        def ovpn_unblock(client_name, actor_username=None):
            self.calls.append(("unblock", client_name, actor_username))
            return SimpleNamespace(block_until=None)

        def ovpn_set_traffic_limit(client_name, limit_bytes, actor_username=None):
            self.calls.append(("set_traffic_limit", client_name, limit_bytes, actor_username))
            return SimpleNamespace()

        def ovpn_clear_traffic_limit(client_name, actor_username=None):
            self.calls.append(("clear_traffic_limit", client_name, actor_username))
            return SimpleNamespace()

        register_config_routes(
            self.app,
            auth_manager=FakeAuthManager(),
            file_validator=SimpleNamespace(validate_file=lambda fn: fn),
            db=SimpleNamespace(),
            user_model=SimpleNamespace(),
            viewer_config_access_model=SimpleNamespace(),
            qr_download_token_model=SimpleNamespace(),
            client_name_pattern=__import__("re").compile(r"^[A-Za-z0-9_-]{1,64}$"),
            group_folders={},
            result_dir_files={},
            ensure_client_connect_ban_check_block=lambda: None,
            openvpn_set_temp_block_days=ovpn_temp,
            openvpn_set_permanent_block=ovpn_perm,
            openvpn_clear_block=ovpn_unblock,
            openvpn_set_traffic_limit_bytes=ovpn_set_traffic_limit,
            openvpn_clear_traffic_limit=ovpn_clear_traffic_limit,
            human_bytes=lambda value: f"{value} B",
            openvpn_reconcile_client_policy=lambda _name: {
                "state": {
                    "is_blocked": True,
                    "reason": "manual_temp",
                    "block_mode": "temp",
                    "blocked_days_left": 5,
                    "block_duration_days": 7,
                }
            },
            get_config_type=lambda _path: "openvpn",
            resolve_config_file=lambda *_args, **_kwargs: (None, None),
            create_one_time_download_url=lambda _path: "https://example.test/download",
            log_qr_event=lambda *args, **kwargs: None,
            qr_generator=SimpleNamespace(),
            enqueue_background_task=lambda *args, **kwargs: None,
            task_run_doall=lambda: None,
            task_accepted_response=lambda *args, **kwargs: None,
            io_executor=SimpleNamespace(),
            set_env_value=lambda *args, **kwargs: None,
            get_public_download_enabled=lambda: False,
            set_public_download_enabled=lambda *_args, **_kwargs: None,
            log_telegram_audit_event=lambda *args, **kwargs: None,
            log_user_action_event=lambda *args, **kwargs: None,
        )

    def test_temp_block_action(self):
        with self.app.test_client() as client:
            with client.session_transaction() as session_state:
                session_state["username"] = "admin"
            response = client.post(
                "/api/openvpn/client-block",
                data={"client_name": "alice", "action": "temp_block", "days": "7"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(self.calls[0][0], "temp_block")

    def test_legacy_blocked_flag_maps_to_permanent_block(self):
        with self.app.test_client() as client:
            with client.session_transaction() as session_state:
                session_state["username"] = "admin"
            response = client.post(
                "/api/openvpn/client-block",
                data={"client_name": "alice", "blocked": "1"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(self.calls[0][0], "permanent_block")


if __name__ == "__main__":
    unittest.main()
