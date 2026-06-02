import unittest
from unittest.mock import MagicMock

from flask import Flask

from routes.settings.api import register_settings_api_routes


class _AuthManagerStub:
    @staticmethod
    def admin_required(fn):
        return fn


def _register_routes(app, log_user_action_event):
    register_settings_api_routes(
        app,
        auth_manager=_AuthManagerStub(),
        db=MagicMock(),
        user_model=MagicMock(),
        user_action_log_model=MagicMock(),
        ip_manager=MagicMock(),
        enqueue_background_task=MagicMock(),
        task_restart_service=MagicMock(),
        set_env_value=MagicMock(),
        get_env_value=MagicMock(return_value="900"),
        to_bool=MagicMock(),
        is_valid_cron_expression=MagicMock(return_value=True),
        ensure_nightly_idle_restart_cron=MagicMock(),
        get_nightly_idle_restart_settings=MagicMock(return_value=(False, "0 3 * * *")),
        set_nightly_idle_restart_settings=MagicMock(),
        get_active_web_session_settings=MagicMock(return_value=(300, 60)),
        set_active_web_session_settings=MagicMock(),
        log_telegram_audit_event=MagicMock(),
        log_user_action_event=log_user_action_event,
        cidr_db_updater_service=MagicMock(),
    )


class SettingsApiCidrGamesTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.log_user_action_event = MagicMock()
        _register_routes(self.app, self.log_user_action_event)
        self.client = self.app.test_client()

    def test_preview_games_sync_rejects_invalid_keys(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={"action": "preview_games_sync", "include_game_keys": ["lol", "unknown_game"]},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("invalid_game_keys", payload)
        self.assertIn("unknown_game", payload["invalid_game_keys"])

    def test_preview_games_sync_rejects_conflicted_include_exclude_keys(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={
                "action": "preview_games_sync",
                "include_game_keys": ["lol"],
                "exclude_game_keys": ["lol"],
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        conflicted = payload.get("conflicted_provider_keys") or payload.get("conflicted_game_keys") or []
        self.assertIn("riot_games", conflicted)

    def test_preview_games_sync_returns_preview_payload(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={"action": "preview_games_sync", "include_game_keys": ["lol"], "include_game_domains": True},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("preview", payload)
        self.assertIn("selected_game_count", payload["preview"])
        self.assertIn("overlap_summary", payload["preview"])
        self.assertTrue(payload["preview"]["include_game_domains"])
        self.assertIn("per_game_stats", payload["preview"])
        self.assertIn("domains_to_add", payload["preview"])
        self.assertGreaterEqual(len(payload["preview"]["domains_to_add"]), 1)

    def test_preview_games_sync_hides_domains_list_when_disabled(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={"action": "preview_games_sync", "include_game_keys": ["lol"], "include_game_domains": False},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["preview"]["domains_to_add"], [])

    def test_sync_games_hosts_supports_include_game_domains_flag(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={"action": "sync_games_hosts", "include_game_keys": ["lol"], "include_game_domains": False},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("game_ips_filter", payload)

    def test_preview_games_exclude_rejects_invalid_keys(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={"action": "preview_games_exclude", "include_game_keys": ["lol", "unknown_game"]},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("invalid_game_keys", payload)
        self.assertIn("unknown_game", payload["invalid_game_keys"])

    def test_preview_games_exclude_returns_preview_payload(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={"action": "preview_games_exclude", "include_game_keys": ["lol"], "include_game_domains": True},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("preview", payload)
        self.assertIn("selected_game_count", payload["preview"])
        self.assertIn("overlap_summary", payload["preview"])
        self.assertTrue(payload["preview"]["include_game_domains"])
        self.assertIn("per_game_stats", payload["preview"])
        self.assertIn("domains_to_add", payload["preview"])
        self.assertGreaterEqual(len(payload["preview"]["domains_to_add"]), 1)

    def test_sync_games_exclude_supports_include_game_domains_flag(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={"action": "sync_games_exclude", "include_game_keys": ["lol"], "include_game_domains": False},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("game_ips_filter", payload)

    def test_sync_games_routes_applies_include_and_exclude(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={
                "action": "sync_games_routes",
                "include_provider_keys": ["riot_games"],
                "exclude_provider_keys": ["valve"],
                "include_game_domains": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("changed", payload)
        self.assertIn("game_ips_filter", payload)
        self.assertIn("game_exclude_ips_filter", payload)

    def test_sync_games_routes_rejects_same_provider_conflict(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={
                "action": "sync_games_routes",
                "include_game_keys": ["lol"],
                "exclude_game_keys": ["valorant"],
                "include_game_domains": False,
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        conflicted = payload.get("conflicted_provider_keys") or payload.get("conflicted_game_keys") or []
        self.assertIn("riot_games", conflicted)

    def test_sync_games_hosts_skips_audit_when_unchanged(self):
        self.client.post(
            "/api/cidr-lists",
            json={"action": "sync_games_hosts", "include_game_keys": [], "include_game_domains": False},
        )
        first_count = self.log_user_action_event.call_count
        self.client.post(
            "/api/cidr-lists",
            json={"action": "sync_games_hosts", "include_game_keys": [], "include_game_domains": False},
        )
        self.assertEqual(self.log_user_action_event.call_count, first_count)

        response = self.client.post(
            "/api/cidr-lists",
            json={
                "action": "sync_games_exclude",
                "include_game_keys": ["lol"],
                "exclude_game_keys": ["lol"],
                "include_game_domains": False,
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("conflicted_game_keys", payload)

    def test_get_cidr_lists_returns_provider_catalog(self):
        response = self.client.get("/api/cidr-lists")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        riot = next(item for item in payload["provider_filters"] if item["key"] == "riot_games")
        self.assertEqual(riot["title"], "Riot Games")
        self.assertIn("lol", riot["game_keys"])
        self.assertGreaterEqual(riot["game_count"], 1)
        lol = next(item for item in payload["game_filters"] if item["key"] == "lol")
        self.assertEqual(lol["source_type"], "servers")
        self.assertGreater(lol["server_ip_count"], 0)
        self.assertIn("game_filter_route_limit_settings", payload)
        self.assertIn("route_limit_enforced", payload["game_filter_route_limit_settings"])

    def test_set_game_filter_route_limit_requires_risk_ack(self):
        response = self.client.post(
            "/api/cidr-lists",
            json={
                "action": "set_game_filter_route_limit",
                "disable_route_limit": True,
                "route_limit_risk_ack": False,
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])

    def test_set_game_filter_route_limit_saves_settings(self):
        from unittest.mock import patch

        set_env_value = MagicMock()
        with patch("routes.settings.api.set_env_value", set_env_value), patch(
            "routes.settings.api.get_game_filter_route_limit_settings",
            return_value={
                "disable_route_limit": True,
                "route_limit_risk_ack": True,
                "route_limit_enforced": False,
            },
        ):
            response = self.client.post(
                "/api/cidr-lists",
                json={
                    "action": "set_game_filter_route_limit",
                    "disable_route_limit": True,
                    "route_limit_risk_ack": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertFalse(payload["game_filter_route_limit_settings"]["route_limit_enforced"])
        set_env_value.assert_any_call("AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT", "true")
        set_env_value.assert_any_call("AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK", "true")


if __name__ == "__main__":
    unittest.main()
