import unittest
from unittest.mock import MagicMock

from core.services.maintenance_scheduler import MaintenanceSchedulerService


class MaintenanceSchedulerBackupTests(unittest.TestCase):
    def _build_service(self, enabled=True, interval_days=7, time_hhmm="03:30"):
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
            is_valid_cron_expression=lambda expr: True,
            get_nightly_idle_restart_settings=lambda: (True, "0 4 * * *"),
            get_backup_settings=lambda: {
                "enabled": enabled,
                "interval_days": interval_days,
                "time_hhmm": time_hhmm,
            },
        )

    def test_ensure_app_backup_cron_adds_line(self):
        service = self._build_service(enabled=True, interval_days=7, time_hhmm="04:20")
        service.read_crontab_lines = MagicMock(return_value=["0 1 * * * echo hi # old"])
        service.write_crontab_lines = MagicMock()
        ok, _ = service.ensure_app_backup_cron()
        self.assertTrue(ok)
        written_lines = service.write_crontab_lines.call_args.args[0]
        self.assertTrue(any("# app-backup" in line for line in written_lines))

    def test_ensure_app_backup_cron_removes_when_disabled(self):
        service = self._build_service(enabled=False)
        service.read_crontab_lines = MagicMock(return_value=["20 4 */7 * * run # app-backup"])
        service.write_crontab_lines = MagicMock()
        ok, _ = service.ensure_app_backup_cron()
        self.assertTrue(ok)
        written_lines = service.write_crontab_lines.call_args.args[0]
        self.assertFalse(any("# app-backup" in line for line in written_lines))


if __name__ == "__main__":
    unittest.main()
