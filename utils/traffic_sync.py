#!/usr/bin/env python3
"""Background traffic snapshot sync for AdminAntizapret.

Reads OpenVPN *-status.log files and persists per-user traffic deltas
into SQLite so data is kept even after clients disconnect.
"""

import sys
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app, _collect_status_rows_for_snapshot, _persist_traffic_snapshot


logger = logging.getLogger(__name__)


def run_sync() -> int:
    with app.app_context():
        status_rows = _collect_status_rows_for_snapshot()
        _persist_traffic_snapshot(status_rows)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_sync())
    except Exception as exc:
        logger.exception("traffic_sync failed: %s", exc)
        sys.exit(1)
