import unittest

from flask import Flask

from routes.settings_routes import register_settings_routes


class FakeAuthManager:
    def admin_required(self, fn):
        return fn


class FakeDbSession:
    def add(self, _obj):
        return None

    def commit(self):
        return None

    def delete(self, _obj):
        return None


class FakeDb:
    def __init__(self):
        self.session = FakeDbSession()


class FakeUserQuery:
    def filter_by(self, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return None

    def all(self):
        return []


class FakeUserModel:
    query = FakeUserQuery()

    def __init__(self, username=None, role=None, telegram_id=None):
        self.username = username
        self.role = role
        self.telegram_id = telegram_id

    def set_password(self, _password):
        return None


class FakeCountQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return 0


class FakeActiveWebSessionModel:
    query = FakeCountQuery()
    last_seen_at = 0


class FakeAuditOrder:
    def limit(self, _n):
        return self

    def all(self):
        return []


class FakeAuditQuery:
    def order_by(self, *_args, **_kwargs):
        return FakeAuditOrder()


class FakeAuditModel:
    query = FakeAuditQuery()
    created_at = 0


class FakeIpRestriction:
    def __init__(self):
        self.allowed_ips = {"10.0.0.1"}
        self.enabled = True
        self.save_calls = 0
        self.clear_scanner_calls = 0

    def add_ip(self, _ip):
        return True

    def remove_ip(self, _ip):
        return False

    def clear_all(self):
        self.allowed_ips.clear()
        self.enabled = False

    def get_allowed_ips(self):
        return sorted(self.allowed_ips)

    def is_enabled(self):
        return self.enabled

    def get_client_ip(self):
        return "127.0.0.1"

    def save_to_env(self):
        self.save_calls += 1

    def clear_scanner_bans(self):
        self.clear_scanner_calls += 1

    def get_scanner_settings(self):
        return {
            "enabled": False,
            "max_attempts": 5,
            "window_seconds": 60,
            "ban_seconds": 3600,
            "block_ip_blocked_dwell": True,
            "ip_blocked_dwell_seconds": 120,
            "strikes_for_year": 5,
            "year_ban_seconds": 365 * 86400,
            "unban_grace_seconds": 1800,
            "firewall_enabled": True,
            "active_bans": [{"ip": "1.2.3.4", "strikes": 1, "long_term": False, "remaining_seconds": 60}],
            "grace_entries": [{"ip": "5.6.7.8", "strikes": 0, "grace_remaining_seconds": 900}],
            "has_firewall_entries": True,
        }


class FakeConfigFileHandler:
    def __init__(self):
        self.config_paths = {"openvpn": []}

    def get_config_files(self):
        return ([], [], [])


class FakeCidrDbUpdaterService:
    def get_db_status(self):
        return {"providers": {}, "alerts": [], "total_cidrs": 0}

    def get_refresh_history(self, limit=10):
        return []

    def refresh_all_providers(self, **_kwargs):
        return {"success": True, "status": "ok", "providers_updated": 0, "providers_failed": 0, "total_cidrs": 0, "per_provider": {}}

    def get_presets(self):
        return []

    def create_preset(self, **_kwargs):
        return None

    def update_preset(self, *_args, **_kwargs):
        return None

    def delete_preset(self, *_args, **_kwargs):
        return False, "not-found"

    def reset_builtin_preset(self, *_args, **_kwargs):
        return None


class SettingsSecurityTabTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["TESTING"] = True

        self.ip_restriction = FakeIpRestriction()
        self.logged_events = []

        register_settings_routes(
            self.app,
            auth_manager=FakeAuthManager(),
            db=FakeDb(),
            user_model=FakeUserModel,
            active_web_session_model=FakeActiveWebSessionModel,
            qr_download_audit_log_model=FakeAuditModel,
            telegram_mini_audit_log_model=FakeAuditModel,
            user_action_log_model=FakeAuditModel,
            ip_restriction=self.ip_restriction,
            ip_manager=type(
                "FakeIpManager",
                (),
                {
                    "add_from_file": staticmethod(lambda _name: 0),
                    "enable_file": staticmethod(lambda _name: 0),
                    "disable_file": staticmethod(lambda _name: 0),
                    "sync_enabled": staticmethod(lambda: None),
                    "list_ip_files": staticmethod(lambda: {}),
                    "get_file_states": staticmethod(lambda: {}),
                },
            )(),
            collect_all_openvpn_files_for_access=lambda: [],
            build_openvpn_access_groups=lambda _items: [],
            config_file_handler=FakeConfigFileHandler(),
            group_folders={},
            build_conf_access_groups=lambda _items, _kind: [],
            enqueue_background_task=lambda *_args, **_kwargs: type("T", (), {"id": "task-id"})(),
            task_restart_service=lambda: None,
            set_env_value=lambda *_args, **_kwargs: None,
            get_env_value=lambda *_args, **_kwargs: "",
            to_bool=lambda value, default=True: default if value is None else str(value).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            },
            is_valid_cron_expression=lambda _value: True,
            ensure_nightly_idle_restart_cron=lambda: (True, "ok"),
            get_nightly_idle_restart_settings=lambda: (True, "0 4 * * *"),
            set_nightly_idle_restart_settings=lambda *_args, **_kwargs: None,
            get_active_web_session_settings=lambda: (180, 30),
            set_active_web_session_settings=lambda *_args, **_kwargs: None,
            get_public_download_enabled=lambda: False,
            log_telegram_audit_event=lambda *_args, **_kwargs: None,
            log_user_action_event=lambda *args, **kwargs: self.logged_events.append((args, kwargs)),
            cidr_db_updater_service=FakeCidrDbUpdaterService(),
        )

    def test_enable_ips_rejects_invalid_entries_without_overwriting_existing_state(self):
        with self.app.test_client() as client:
            response = client.post(
                "/settings",
                data={
                    "ip_action": "enable_ips",
                    "ips_text": "bad_ip, 999.999.1.1",
                },
            )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.ip_restriction.allowed_ips, {"10.0.0.1"})
            self.assertTrue(self.ip_restriction.enabled)
            self.assertEqual(self.ip_restriction.save_calls, 0)
            self.assertEqual(self.logged_events, [])

            with client.session_transaction() as session_state:
                flashes = session_state.get("_flashes", [])

            self.assertTrue(any(category == "error" and "некорректные IP/подсети" in message for category, message in flashes))

    def test_enable_ips_normalizes_and_deduplicates_valid_entries(self):
        with self.app.test_client() as client:
            response = client.post(
                "/settings",
                data={
                    "ip_action": "enable_ips",
                    "ips_text": "192.168.1.1, 192.168.1.1, 10.0.0.5/24",
                },
            )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.ip_restriction.allowed_ips, {"192.168.1.1", "10.0.0.0/24"})
            self.assertTrue(self.ip_restriction.enabled)
            self.assertEqual(self.ip_restriction.save_calls, 1)
            self.assertEqual(len(self.logged_events), 1)

            args, kwargs = self.logged_events[0]
            self.assertEqual(args[0], "settings_ip_bulk_enable")
            self.assertEqual(kwargs.get("details"), "entries=2")

            with client.session_transaction() as session_state:
                flashes = session_state.get("_flashes", [])

            self.assertTrue(any(category == "success" and "IP ограничения включены" in message for category, message in flashes))

    def test_clear_scanner_bans_action(self):
        with self.app.test_client() as client:
            response = client.post(
                "/settings",
                data={"ip_action": "clear_scanner_bans"},
            )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.ip_restriction.clear_scanner_calls, 1)

            with client.session_transaction() as session_state:
                flashes = session_state.get("_flashes", [])

            self.assertTrue(
                any(
                    category == "success" and "баны сканеров сброшены" in message.lower()
                    for category, message in flashes
                )
            )


if __name__ == "__main__":
    unittest.main()
