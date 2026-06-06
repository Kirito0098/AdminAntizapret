#!/usr/bin/env python3
"""Reconcile traffic-limit policies after cron traffic sync.

Uses ADMIN_ANTIZAPRET_SKIP_APP_BOOTSTRAP to avoid startup cron/bootstrap work
while still reusing the same reconcile logic as the web app.
"""

from __future__ import annotations

import logging
import os
import sys

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)
os.environ.setdefault("ADMIN_ANTIZAPRET_SKIP_APP_BOOTSTRAP", "1")


def reconcile_traffic_limit_policies() -> None:
    from app import app, _reconcile_traffic_limit_policies

    with app.app_context():
        _reconcile_traffic_limit_policies()


def main() -> int:
    try:
        reconcile_traffic_limit_policies()
        return 0
    except Exception as exc:
        logging.exception("Traffic limit reconcile failed: %s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())
