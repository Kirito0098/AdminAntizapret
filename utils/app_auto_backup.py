#!/usr/bin/env python3
import os
import sys

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from core.services.backup_telegram_job import (  # noqa: E402
    load_admin_chat_ids,
    run_backup_job,
)


def main():
    result = run_backup_job(APP_ROOT, trigger="auto", require_auto_enabled=True)
    if result.get("skipped"):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Re-export for tests
_load_admin_chat_ids = load_admin_chat_ids
