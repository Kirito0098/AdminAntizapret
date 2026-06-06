import unittest
from types import SimpleNamespace

from flask import Flask

from routes.index.routes import register_index_routes


class FakeAuthManager:
    def admin_required(self, fn):
        return fn

    def login_required(self, fn):
        return fn


class FakeSession:
    def rollback(self):
        return None


class FakeDb:
    def __init__(self):
        self.session = FakeSession()


class IndexRoutesWgAccessTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["TESTING"] = True

        self.calls = []

        def wg_set_temp_block_days(client_name, days, actor_username=None):
            self.calls.append(("temp_block", client_name, days, actor_username))
            return SimpleNamespace(expires_at=None, block_until=None)

        def wg_clear_temp_block(client_name, actor_username=None):
            self.calls.append(("unblock", client_name, actor_username))
            return SimpleNamespace(expires_at=None, block_until=None)

        def wg_set_permanent_block(client_name, actor_username=None):
            self.calls.append(("permanent_block", client_name, actor_username))
            return SimpleNamespace(expires_at=None, block_until=None)

        def wg_set_expiry_days(client_name, days, actor_username=None, extend=False):
            self.calls.append(("extend", client_name, days, actor_username, extend))
            return SimpleNamespace(expires_at=None, block_until=None)

        register_index_routes(
            self.app,
            auth_manager=FakeAuthManager(),
            get_env_value=lambda key, default="": default,
            db=FakeDb(),
            user_model=SimpleNamespace(),
            config_file_handler=SimpleNamespace(),
            file_validator=SimpleNamespace(),
            group_folders={},
            read_banned_clients=lambda: set(),
            openvpn_build_status_map=lambda names: {},
            openvpn_reconcile_all_policies=lambda: None,
            extract_client_name_from_config_file=lambda _path: "",
            get_logs_dashboard_data_cached=lambda created_by_username=None: {},
            human_bytes=lambda value: str(value),
            script_executor=SimpleNamespace(run_bash_script=lambda *_args, **_kwargs: ("", "")),
            sync_wireguard_peer_cache_from_configs=lambda force=False: 0,
            wg_build_status_map=lambda names: {},
            wg_set_expiry_days=wg_set_expiry_days,
            wg_set_temp_block_days=wg_set_temp_block_days,
            wg_set_permanent_block=wg_set_permanent_block,
            wg_clear_temp_block=wg_clear_temp_block,
            wg_set_traffic_limit_bytes=lambda *args, **kwargs: SimpleNamespace(
                expires_at=None, block_until=None
            ),
            wg_clear_traffic_limit=lambda *args, **kwargs: SimpleNamespace(
                expires_at=None, block_until=None
            ),
            wg_reconcile_client_policy=lambda client_name, apply_runtime=True: {
                "state": {
                    "is_blocked": client_name == "alice",
                    "reason": "manual_temp",
                    "access_days_left": 12,
                    "blocked_days_left": 3,
                    "block_mode": "temp",
                    "block_duration_days": 5,
                    "block_started_at": None,
                }
            },
            wg_reconcile_all_policies=lambda apply_runtime=True: None,
            log_telegram_audit_event=lambda *args, **kwargs: None,
            log_user_action_event=lambda *args, **kwargs: None,
            send_tg_admin_notification=lambda *args, **kwargs: None,
        )

    def test_wg_temp_block_api_success(self):
        with self.app.test_client() as client:
            with client.session_transaction() as session_state:
                session_state["username"] = "admin"
            response = client.post(
                "/api/wg/client-access",
                data={"client_name": "alice", "action": "temp_block", "days": "5"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(self.calls[0][0], "temp_block")
        self.assertIn("block_mode", payload)
        self.assertIn("access_days_left", payload)

    def test_wg_permanent_block_api_success(self):
        with self.app.test_client() as client:
            with client.session_transaction() as session_state:
                session_state["username"] = "admin"
            response = client.post(
                "/api/wg/client-access",
                data={"client_name": "alice", "action": "permanent_block"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(self.calls[0][0], "permanent_block")

    def test_wg_api_rejects_invalid_action(self):
        with self.app.test_client() as client:
            response = client.post(
                "/api/wg/client-access",
                data={"client_name": "alice", "action": "unknown"},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])

    def test_wg_unblock_expired_returns_409(self):
        from core.services.wg_access_policy import ExpiredRequiresExtendError

        def wg_clear_temp_block_raises(client_name, actor_username=None):
            self.calls.append(("unblock", client_name, actor_username))
            raise ExpiredRequiresExtendError()

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["TESTING"] = True
        register_index_routes(
            app,
            auth_manager=FakeAuthManager(),
            get_env_value=lambda key, default="": default,
            db=FakeDb(),
            user_model=SimpleNamespace(),
            config_file_handler=SimpleNamespace(),
            file_validator=SimpleNamespace(),
            group_folders={},
            read_banned_clients=lambda: set(),
            openvpn_build_status_map=lambda names: {},
            openvpn_reconcile_all_policies=lambda: None,
            extract_client_name_from_config_file=lambda _path: "",
            get_logs_dashboard_data_cached=lambda created_by_username=None: {},
            human_bytes=lambda value: str(value),
            script_executor=SimpleNamespace(run_bash_script=lambda *_args, **_kwargs: ("", "")),
            sync_wireguard_peer_cache_from_configs=lambda force=False: 0,
            wg_build_status_map=lambda names: {},
            wg_set_expiry_days=lambda *args, **kwargs: SimpleNamespace(expires_at=None, block_until=None),
            wg_set_temp_block_days=lambda *args, **kwargs: SimpleNamespace(expires_at=None, block_until=None),
            wg_set_permanent_block=lambda *args, **kwargs: SimpleNamespace(expires_at=None, block_until=None),
            wg_clear_temp_block=wg_clear_temp_block_raises,
            wg_set_traffic_limit_bytes=lambda *args, **kwargs: SimpleNamespace(
                expires_at=None, block_until=None
            ),
            wg_clear_traffic_limit=lambda *args, **kwargs: SimpleNamespace(
                expires_at=None, block_until=None
            ),
            wg_reconcile_client_policy=lambda *args, **kwargs: {"state": {}},
            wg_reconcile_all_policies=lambda apply_runtime=True: None,
            log_telegram_audit_event=lambda *args, **kwargs: None,
            log_user_action_event=lambda *args, **kwargs: None,
            send_tg_admin_notification=lambda *args, **kwargs: None,
        )

        with app.test_client() as client:
            with client.session_transaction() as session_state:
                session_state["username"] = "admin"
            response = client.post(
                "/api/wg/client-access",
                data={"client_name": "expired-user", "action": "unblock"},
            )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "expired_requires_extend")


if __name__ == "__main__":
    unittest.main()

