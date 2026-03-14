#!/usr/bin/env python3
"""Background traffic snapshot sync for AdminAntizapret.

Reads OpenVPN *-status.log files and persists per-user traffic deltas
into SQLite so data is kept even after clients disconnect.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app, STATUS_LOG_FILES, _parse_status_log, _persist_traffic_snapshot


def run_sync() -> int:
    with app.app_context():
        status_rows = [
            _parse_status_log(profile_key, filename)
            for profile_key, filename in STATUS_LOG_FILES.items()
        ]
        _persist_traffic_snapshot(status_rows)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_sync())
    except Exception as exc:
        print(f"traffic_sync failed: {exc}", file=sys.stderr)
        sys.exit(1)
