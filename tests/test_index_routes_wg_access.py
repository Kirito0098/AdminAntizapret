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

        def wg_set_expiry_days(client_name, days, actor_username=None, extend=False):
            self.calls.append(("extend", client_name, days, actor_username, extend))
            return SimpleNamespace(expires_at=None, block_until=None)

        register_index_routes(
            self.app,
            auth_manager=FakeAuthManager(),
            db=FakeDb(),
            user_model=SimpleNamespace(),
            config_file_handler=SimpleNamespace(),
            file_validator=SimpleNamespace(),
            group_folders={},
            read_banned_clients=lambda: set(),
            extract_client_name_from_config_file=lambda _path: "",
            get_logs_dashboard_data_cached=lambda created_by_username=None: {},
            human_bytes=lambda value: str(value),
            script_executor=SimpleNamespace(run_bash_script=lambda *_args, **_kwargs: ("", "")),
            sync_wireguard_peer_cache_from_configs=lambda force=False: 0,
            wg_build_status_map=lambda names: {},
            wg_set_expiry_days=wg_set_expiry_days,
            wg_set_temp_block_days=wg_set_temp_block_days,
            wg_clear_temp_block=wg_clear_temp_block,
            wg_reconcile_client_policy=lambda client_name, apply_runtime=True: {
                "state": {"is_blocked": client_name == "alice", "reason": "manual_temp"}
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

    def test_wg_api_rejects_invalid_action(self):
        with self.app.test_client() as client:
            response = client.post(
                "/api/wg/client-access",
                data={"client_name": "alice", "action": "unknown"},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])


if __name__ == "__main__":
    unittest.main()

