import glob
import os
import shlex
import subprocess


class MaintenanceSchedulerService:
    def __init__(
        self,
        *,
        app_root,
        logs_dir,
        python_executable,
        status_log_cleanup_marker,
        status_log_cleanup_periods,
        traffic_sync_cron_marker,
        traffic_sync_cron_expr,
        traffic_sync_enabled,
        nightly_idle_restart_marker,
        is_valid_cron_expression,
        get_nightly_idle_restart_settings,
    ):
        self.app_root = app_root
        self.logs_dir = logs_dir
        self.python_executable = python_executable or "python3"
        self.status_log_cleanup_marker = status_log_cleanup_marker
        self.status_log_cleanup_periods = status_log_cleanup_periods
        self.traffic_sync_cron_marker = traffic_sync_cron_marker
        self.traffic_sync_cron_expr = traffic_sync_cron_expr
        self.traffic_sync_enabled = bool(traffic_sync_enabled)
        self.nightly_idle_restart_marker = nightly_idle_restart_marker
        self.is_valid_cron_expression = is_valid_cron_expression
        self.get_nightly_idle_restart_settings = get_nightly_idle_restart_settings

    def status_log_cleanup_command(self):
        quoted_logs_dir = shlex.quote(self.logs_dir)
        return (
            f"find {quoted_logs_dir} -maxdepth 1 -type f "
            "-name '*.log' ! -name '*-status.log' -delete >/dev/null 2>&1"
        )

    def read_crontab_lines(self):
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return None

        if result.returncode != 0:
            stderr = (result.stderr or "").strip().lower()
            if "no crontab for" in stderr:
                return []
            return None

        return [line.rstrip("\n") for line in result.stdout.splitlines()]

    def write_crontab_lines(self, lines):
        payload = "\n".join(lines).strip()
        if payload:
            payload += "\n"

        subprocess.run(
            ["crontab", "-"],
            input=payload,
            text=True,
            check=True,
        )

    def strip_status_cleanup_jobs(self, lines):
        return [line for line in lines if self.status_log_cleanup_marker not in line]

    def traffic_sync_command(self):
        python_bin = shlex.quote(self.python_executable)
        script_path = shlex.quote(os.path.join(self.app_root, "utils", "traffic_sync.py"))
        return f"{python_bin} {script_path} >/dev/null 2>&1"

    def nightly_idle_restart_command(self):
        python_bin = shlex.quote(self.python_executable)
        script_path = shlex.quote(os.path.join(self.app_root, "utils", "nightly_idle_restart.py"))
        return f"{python_bin} {script_path} >/dev/null 2>&1"

    def is_systemd_traffic_sync_timer_enabled(self):
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "admin-antizapret-traffic-sync.timer"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def ensure_traffic_sync_cron(self):
        lines = self.read_crontab_lines()
        if lines is None:
            return False, "Не удалось прочитать crontab для авто-синхронизации трафика."

        lines = [line for line in lines if self.traffic_sync_cron_marker not in line]

        if self.is_systemd_traffic_sync_timer_enabled():
            try:
                self.write_crontab_lines(lines)
            except Exception as e:
                return False, f"Ошибка очистки cron sync при активном timer: {e}"
            return True, "Systemd timer sync активен, cron sync не требуется"

        if self.traffic_sync_enabled:
            command = self.traffic_sync_command()
            lines.append(f"{self.traffic_sync_cron_expr} {command} {self.traffic_sync_cron_marker}")

        try:
            self.write_crontab_lines(lines)
        except Exception as e:
            return False, f"Ошибка записи cron sync: {e}"

        if self.traffic_sync_enabled:
            return True, "Cron sync трафика включен"
        return True, "Cron sync трафика отключен"

    def ensure_nightly_idle_restart_cron(self):
        lines = self.read_crontab_lines()
        if lines is None:
            return False, "Не удалось прочитать crontab для ночного рестарта сайта."

        nightly_enabled, nightly_cron_expr = self.get_nightly_idle_restart_settings()
        if nightly_enabled and not self.is_valid_cron_expression(nightly_cron_expr):
            return False, "Некорректное cron-выражение для ночного рестарта."

        lines = [line for line in lines if self.nightly_idle_restart_marker not in line]

        if nightly_enabled:
            command = self.nightly_idle_restart_command()
            lines.append(f"{nightly_cron_expr} {command} {self.nightly_idle_restart_marker}")

        try:
            self.write_crontab_lines(lines)
        except Exception as e:
            return False, f"Ошибка записи cron ночного рестарта: {e}"

        if nightly_enabled:
            return True, "Cron ночного рестарта включен"
        return True, "Cron ночного рестарта отключен"

    def get_status_cleanup_schedule(self):
        lines = self.read_crontab_lines()
        if lines is None:
            return {
                "period": "none",
                "label": "Недоступно (cron не найден)",
                "available": False,
            }

        for line in lines:
            if self.status_log_cleanup_marker not in line:
                continue

            marker_part = line.split(self.status_log_cleanup_marker, 1)[-1].strip()
            period = "none"
            if marker_part.startswith(":"):
                period = marker_part[1:]

            period = period if period in self.status_log_cleanup_periods else "none"
            label = self.status_log_cleanup_periods.get(period, (None, "Выключено"))[1]
            return {"period": period, "label": label, "available": True}

        return {"period": "none", "label": "Выключено", "available": True}

    def set_status_cleanup_schedule(self, period):
        lines = self.read_crontab_lines()
        if lines is None:
            return False, "Не удалось прочитать crontab (cron недоступен)."

        lines = self.strip_status_cleanup_jobs(lines)

        if period in self.status_log_cleanup_periods:
            cron_expr, _ = self.status_log_cleanup_periods[period]
            cmd = self.status_log_cleanup_command()
            lines.append(f"{cron_expr} {cmd} {self.status_log_cleanup_marker}:{period}")

        try:
            self.write_crontab_lines(lines)
        except Exception as e:
            return False, f"Ошибка записи crontab: {e}"

        if period in self.status_log_cleanup_periods:
            return True, f"Расписание очистки *.log (кроме *-status.log) установлено: {self.status_log_cleanup_periods[period][1]}"
        return True, "Расписание очистки *.log (кроме *-status.log) отключено"

    def cleanup_status_logs_now(self):
        pattern = os.path.join(self.logs_dir, "*.log")
        deleted = 0
        failed = []

        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path) and not file_path.endswith("-status.log"):
                    os.remove(file_path)
                    deleted += 1
            except Exception:
                failed.append(os.path.basename(file_path))

        if failed:
            return False, f"Удалено обычных .log: {deleted}. Ошибки: {', '.join(failed)}"
        return True, f"Удалено обычных .log (без *-status.log): {deleted}"
