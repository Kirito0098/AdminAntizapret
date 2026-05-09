#!/usr/bin/env python3
"""Nightly CIDR database refresh script.

Called by cron at 2-3 AM. Downloads fresh CIDR data from all providers
and stores it in the database. Does NOT update the .txt route files.
"""

import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app, db
from core.services.cidr_db_updater import CidrDbUpdaterService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [cidr-db-refresh] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def run_refresh():
    with app.app_context():
        svc = CidrDbUpdaterService(db=db)
        logger.info("Запуск обновления CIDR БД (cron)")
        result = svc.refresh_all_providers(triggered_by="cron")
        logger.info(
            "Обновление завершено: status=%s updated=%d failed=%d total_cidrs=%d",
            result["status"],
            result["providers_updated"],
            result["providers_failed"],
            result["total_cidrs"],
        )
        for provider, info in result.get("per_provider", {}).items():
            if info.get("status") == "error":
                logger.warning("  %s: ОШИБКА — %s", provider, info.get("error"))
            else:
                logger.info("  %s: %d CIDR", provider, info.get("cidr_count", 0))
        return 0 if result["status"] in ("ok", "partial") else 1


if __name__ == "__main__":
    try:
        sys.exit(run_refresh())
    except Exception as exc:
        logger.exception("Критическая ошибка при обновлении CIDR БД: %s", exc)
        sys.exit(1)
