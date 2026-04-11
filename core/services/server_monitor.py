import logging
import os
import platform
import time

import psutil


logger = logging.getLogger(__name__)


class ServerMonitor:
    def __init__(self):
        pass

    def get_cpu_usage(self):
        return psutil.cpu_percent(interval=1)

    def get_memory_usage(self):
        memory = psutil.virtual_memory()
        return memory.percent

    def get_uptime(self):
        boot_time = psutil.boot_time()
        current_time = time.time()
        uptime_seconds = current_time - boot_time
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{int(days)}д {int(hours)}ч {int(minutes)}м"

    def get_system_info(self):
        """Получить системную информацию."""
        try:
            return {
                "os": platform.system(),
                "os_release": platform.release(),
                "kernel": platform.platform(),
                "hostname": platform.node(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
            }
        except Exception as e:
            logger.error("Ошибка при получении системной информации: %s", e)
            return {}

    def get_disk_usage(self):
        """Получить использование диска."""
        try:
            disk = psutil.disk_usage("/")
            return {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            }
        except Exception as e:
            logger.error("Ошибка при получении информации о диске: %s", e)
            return {}

    def get_load_average(self):
        """Получить load average."""
        try:
            load = os.getloadavg() if hasattr(os, "getloadavg") else psutil.getloadavg()
            cpu_count = psutil.cpu_count()
            return {
                "load_1m": round(load[0], 2),
                "load_5m": round(load[1], 2),
                "load_15m": round(load[2], 2),
                "cpu_count": cpu_count,
            }
        except Exception as e:
            logger.error("Ошибка при получении load average: %s", e)
            return {}

    def get_status_color(self, value, thresholds=None):
        if thresholds is None:
            thresholds = {"yellow": 70, "red": 90}

        if value >= thresholds.get("red", 90):
            return "red"
        if value >= thresholds.get("yellow", 70):
            return "yellow"
        return "green"
