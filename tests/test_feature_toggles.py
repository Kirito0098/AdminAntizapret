import unittest
from unittest.mock import MagicMock, patch

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.services.feature_guards import (
    ENDPOINT_TO_MODULE,
    ENDPOINT_TO_MODULES,
    check_endpoint_access,
    check_index_post_option,
)
from core.services.feature_toggles import (
    FEATURE_TOGGLES,
    RESOURCE_IMPACT_LEVELS,
    apply_feature_toggle_settings,
    build_feature_toggles_page_groups,
    build_feature_toggles_page_items,
    get_app_module_states,
    get_feature_toggle_values,
    is_app_module_enabled,
    is_feature_enabled,
)
from core.services.maintenance_scheduler import MaintenanceSchedulerService
from core.services.settings.post_handlers.feature_toggles import handle_feature_toggles_settings
from utils.wg_runtime_subprocess import trigger_wg_policy_sync_background


class FeatureTogglesServiceTests(unittest.TestCase):
    def test_get_feature_toggle_values_defaults_true(self):
        values = get_feature_toggle_values(get_env_value=lambda key, default=None: default)
        self.assertTrue(all(values[item.key] for item in FEATURE_TOGGLES))

    def test_is_feature_enabled_reads_env(self):
        self.assertFalse(
            is_feature_enabled(
                "MONITOR_ENABLED",
                get_env_value=lambda key, default=None: "false",
            )
        )

    def test_is_app_module_enabled_reads_env(self):
        self.assertFalse(
            is_app_module_enabled(
                "routing",
                get_env_value=lambda key, default=None: {
                    "FEATURE_ROUTING_ENABLED": "false",
                }.get(key, default),
            )
        )

    def test_get_app_module_states_only_app_modules(self):
        states = get_app_module_states(
            get_env_value=lambda key, default=None: {
                "FEATURE_ROUTING_ENABLED": "false",
            }.get(key, default)
        )
        self.assertFalse(states["routing"])
        self.assertTrue(states["openvpn"])
        self.assertNotIn("traffic_sync", states)

    def test_build_feature_toggles_page_items(self):
        items = build_feature_toggles_page_items(
            get_env_value=lambda key, default=None: {
                "TRAFFIC_SYNC_ENABLED": "false",
            }.get(key, default)
        )
        traffic = next(item for item in items if item["key"] == "traffic_sync")
        self.assertFalse(traffic["enabled"])
        self.assertEqual(traffic["group"], "background")
        self.assertEqual(traffic["icon"], "📊")
        self.assertIn("Трафик (БД)", traffic["disable_hint"])
        self.assertEqual(traffic["group_badge"], "Фоновая задача")
        self.assertEqual(traffic["resource_impact_level"], "high")
        self.assertEqual(traffic["resource_impact_label"], "высокая")
        self.assertIn("cron каждую минуту", traffic["resource_savings"])

    def test_all_feature_toggles_have_resource_metadata(self):
        for item in FEATURE_TOGGLES:
            self.assertIn(item.resource_impact_level, RESOURCE_IMPACT_LEVELS)
            self.assertTrue(item.resource_savings.strip(), msg=item.key)

    def test_build_feature_toggles_page_groups(self):
        groups = build_feature_toggles_page_groups(
            get_env_value=lambda key, default=None: {
                "FEATURE_LOGS_DASHBOARD_ENABLED": "false",
            }.get(key, default)
        )
        self.assertEqual(len(groups), 2)
        app_group = next(group for group in groups if group["key"] == "app_module")
        logs = next(item for item in app_group["items"] if item["key"] == "logs_dashboard")
        self.assertFalse(logs["enabled"])
        self.assertEqual(app_group["badge"], "Раздел приложения")
        self.assertEqual(app_group["disabled_count"], 1)
        self.assertEqual(app_group["total_count"], len(app_group["items"]))

    def test_apply_feature_toggle_settings_updates_scheduler_and_cron(self):
        scheduler = MagicMock()
        scheduler.traffic_sync_enabled = True
        scheduler.wg_policy_sync_enabled = True
        scheduler.runtime_backup_cleanup_enabled = True
        runtime = {}

        ok, details = apply_feature_toggle_settings(
            form_values={item.key: item.default for item in FEATURE_TOGGLES}
            | {
                "traffic_sync": False,
                "runtime_backup_cleanup": False,
                "backups": False,
            },
            set_env_value=MagicMock(),
            runtime_set=lambda key, value: runtime.__setitem__(key, value),
            maintenance_scheduler_service=scheduler,
            ensure_traffic_sync_cron=MagicMock(return_value=(True, "traffic ok")),
            ensure_wg_policy_sync_cron=MagicMock(return_value=(True, "wg ok")),
            ensure_runtime_backup_cleanup_cron=MagicMock(return_value=(True, "cleanup ok")),
            ensure_app_backup_cron=MagicMock(return_value=(True, "backup ok")),
        )

        self.assertTrue(ok)
        self.assertFalse(scheduler.traffic_sync_enabled)
        self.assertFalse(scheduler.runtime_backup_cleanup_enabled)
        self.assertFalse(runtime["TRAFFIC_SYNC_ENABLED"])
        self.assertFalse(runtime["APP_BACKUP_ENABLED"])
        self.assertIn("traffic_sync=выкл", details)
        self.assertIn("авто-бэкап: backup ok", details)

    def test_endpoint_registry_covers_app_modules(self):
        app_module_endpoints = {
            endpoint
            for item in FEATURE_TOGGLES
            if item.group == "app_module"
            for endpoint in item.endpoints
        }
        self.assertTrue(app_module_endpoints.issubset(set(ENDPOINT_TO_MODULE.keys())))

    def test_new_app_modules_default_enabled(self):
        for key in (
            "user_management",
            "security",
            "action_logs",
            "system_updates",
            "diagnostics_tests",
            "qr_downloads",
            "vpn_network",
            "maintenance",
        ):
            self.assertTrue(
                is_app_module_enabled(key, get_env_value=lambda env_key, default=None: default)
            )


class FeatureGuardsTests(unittest.TestCase):
    def test_check_endpoint_access_allows_settings(self):
        self.assertIsNone(
            check_endpoint_access(
                "settings",
                get_env_value=lambda key, default=None: {
                    "FEATURE_ROUTING_ENABLED": "false",
                }.get(key, default),
            )
        )

    def test_check_endpoint_access_blocks_disabled_module(self):
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context("/routing"):
            with patch("core.services.feature_guards.render_template") as render_template:
                render_template.return_value = "blocked"
                blocked = check_endpoint_access(
                    "routing",
                    get_env_value=lambda key, default=None: {
                        "FEATURE_ROUTING_ENABLED": "false",
                    }.get(key, default),
                )
            self.assertIsNotNone(blocked)
            self.assertEqual(blocked[1], 403)

    def test_check_index_post_option_blocks_openvpn(self):
        with patch("core.services.feature_guards.jsonify") as jsonify:
            jsonify.return_value = {"success": False}
            blocked = check_index_post_option(
                "1",
                get_env_value=lambda key, default=None: {
                    "FEATURE_OPENVPN_ENABLED": "false",
                }.get(key, default),
            )
        self.assertIsNotNone(blocked)

    def test_check_index_post_option_allows_wg_when_one_protocol_enabled(self):
        self.assertIsNone(
            check_index_post_option(
                "4",
                get_env_value=lambda key, default=None: {
                    "FEATURE_WIREGUARD_ENABLED": "false",
                    "FEATURE_AMNEZIAWG_ENABLED": "true",
                }.get(key, default),
            )
        )

    def test_check_endpoint_access_allows_shared_endpoint_when_any_module_enabled(self):
        self.assertIn("api_cidr_task_status", ENDPOINT_TO_MODULES)
        self.assertIsNone(
            check_endpoint_access(
                "api_cidr_task_status",
                get_env_value=lambda key, default=None: {
                    "FEATURE_ROUTING_ENABLED": "false",
                    "FEATURE_DIAGNOSTICS_TESTS_ENABLED": "true",
                }.get(key, default),
            )
        )

    def test_check_endpoint_access_blocks_qr_downloads(self):
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context("/download/wg/example.conf"):
            with patch("core.services.feature_guards.render_template") as render_template:
                render_template.return_value = "blocked"
                blocked = check_endpoint_access(
                    "download",
                    get_env_value=lambda key, default=None: {
                        "FEATURE_QR_DOWNLOADS_ENABLED": "false",
                    }.get(key, default),
                )
            self.assertIsNotNone(blocked)
            self.assertEqual(blocked[1], 403)


class FeatureTogglesPostHandlerTests(unittest.TestCase):
    def test_handle_feature_toggles_settings_success(self):
        flash = MagicMock()
        scheduler = MagicMock()
        runtime_set = MagicMock()
        set_env_value = MagicMock()
        log_user_action_event = MagicMock()

        form = {"feature_toggles_action": "save"}
        for item in FEATURE_TOGGLES:
            form[f"feature_toggle_{item.key}"] = "true"
        form["feature_toggle_traffic_sync"] = "false"

        handle_feature_toggles_settings(
            form,
            flash=flash,
            to_bool=lambda value, default=False: str(value).lower() == "true",
            set_env_value=set_env_value,
            runtime_set=runtime_set,
            maintenance_scheduler_service=scheduler,
            ensure_traffic_sync_cron=MagicMock(return_value=(True, "ok")),
            ensure_wg_policy_sync_cron=MagicMock(return_value=(True, "ok")),
            ensure_runtime_backup_cleanup_cron=MagicMock(return_value=(True, "ok")),
            ensure_app_backup_cron=MagicMock(return_value=(True, "ok")),
            log_user_action_event=log_user_action_event,
        )

        flash.assert_called_once_with("Настройки модулей сохранены", "success")
        log_user_action_event.assert_called_once()
        self.assertTrue(any(call.args[0] == "TRAFFIC_SYNC_ENABLED" for call in set_env_value.call_args_list))


class FeatureTogglesTemplateTests(unittest.TestCase):
    def test_feature_toggles_tab_renders(self):
        env = Environment(
            loader=FileSystemLoader("templates/partials/settings"),
            autoescape=select_autoescape(["html", "xml"]),
        )
        groups = build_feature_toggles_page_groups(
            get_env_value=lambda key, default=None: default
        )
        items = build_feature_toggles_page_items(
            get_env_value=lambda key, default=None: default
        )
        html = env.get_template("_tab_feature_toggles.html").render(
            feature_toggles=items,
            feature_toggle_groups=groups,
            csrf_token=lambda: "test-token",
        )
        self.assertIn("Модули и задачи", html)
        self.assertIn("Фоновые задачи", html)
        self.assertIn("Разделы приложения", html)
        self.assertIn('name="feature_toggle_traffic_sync"', html)
        self.assertIn("При отключении", html)
        self.assertIn("Нагрузка при включении", html)
        self.assertIn("feature-toggle-card__resource--high", html)
        self.assertIn("feature-toggles-kpi-note", html)
        self.assertIn("feature-toggle-card__effect--critical", html)
        self.assertIn('name="feature_toggle_user_management"', html)
        self.assertIn("Пользователи и доступ", html)
        self.assertNotIn("group.items", html)

    def test_settings_tab_state_visible_in_scripts_block(self):
        with open("templates/settings.html", encoding="utf-8") as handle:
            content = handle.read()
        tab_state_pos = content.index("{% set tab_state = namespace(first='') %}")
        content_block_pos = content.index("{% block content %}")
        scripts_block_pos = content.index("{% block scripts %}")
        self.assertLess(tab_state_pos, content_block_pos)
        self.assertIn("tab_state.first | tojson", content[scripts_block_pos:])


class MaintenanceSchedulerRuntimeCleanupTests(unittest.TestCase):
    def _build_service(self, *, cleanup_enabled=True):
        return MaintenanceSchedulerService(
            app_root="/opt/AdminAntizapret",
            logs_dir="/tmp",
            python_executable="python3",
            status_log_cleanup_marker="# cleanup",
            status_log_cleanup_periods={"daily": ("0 3 * * *", "daily")},
            traffic_sync_cron_marker="# t",
            traffic_sync_cron_expr="*/1 * * * *",
            traffic_sync_enabled=True,
            wg_policy_sync_cron_marker="# wg",
            wg_policy_sync_cron_expr="*/2 * * * *",
            wg_policy_sync_enabled=True,
            nightly_idle_restart_marker="# nightly",
            app_backup_cron_marker="# app-backup",
            runtime_backup_cleanup_marker="# runtime",
            runtime_backup_cleanup_cron_expr="0 * * * *",
            runtime_backup_root="/tmp/runtime",
            runtime_backup_retention_hours=12,
            runtime_backup_cleanup_enabled=cleanup_enabled,
            is_valid_cron_expression=lambda expr: True,
            get_nightly_idle_restart_settings=lambda: (True, "0 4 * * *"),
            get_backup_settings=lambda: {"enabled": False, "interval_days": 1, "time_hhmm": "03:00"},
        )

    def test_runtime_backup_cleanup_cron_removed_when_disabled(self):
        service = self._build_service(cleanup_enabled=False)
        service.read_crontab_lines = MagicMock(return_value=["0 * * * * find # runtime"])
        service.write_crontab_lines = MagicMock()
        ok, _ = service.ensure_runtime_backup_cleanup_cron()
        self.assertTrue(ok)
        written_lines = service.write_crontab_lines.call_args.args[0]
        self.assertFalse(any("# runtime" in line for line in written_lines))


class WgPolicySyncBackgroundTests(unittest.TestCase):
    def test_trigger_skips_when_disabled(self):
        with patch.dict("os.environ", {"WG_POLICY_SYNC_ENABLED": "false"}, clear=False):
            with patch("utils.wg_runtime_subprocess.os.path.isfile", return_value=True):
                self.assertIsNone(trigger_wg_policy_sync_background())


if __name__ == "__main__":
    unittest.main()
