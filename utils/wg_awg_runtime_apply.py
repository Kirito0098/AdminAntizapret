#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

# Не запускать reconcile/cron при импорте app.py — иначе CLI блокируется на десятки секунд.
os.environ.setdefault("ADMIN_ANTIZAPRET_SKIP_APP_BOOTSTRAP", "1")


def _build_parser():
    parser = argparse.ArgumentParser(description="Apply WG/AWG runtime block or unblock for one client.")
    parser.add_argument("--client", required=True, help="WireGuard client name")
    parser.add_argument(
        "--action",
        required=True,
        choices=("block", "unblock"),
        help="Runtime action to apply",
    )
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    client_name = (args.client or "").strip()
    action = (args.action or "").strip().lower()

    if not client_name:
        logging.error("Client name is required")
        print(json.dumps({"error": "client name is required"}, ensure_ascii=False))
        return 2

    try:
        from app import wg_awg_runtime_enforcer
    except Exception as exc:
        logging.exception("Failed to import WG runtime enforcer: %s", exc)
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    try:
        from app import app

        with app.app_context():
            normalized = client_name.strip().lower()
            if action == "block":
                result = wg_awg_runtime_enforcer.block_client_runtime(normalized)
            else:
                result = wg_awg_runtime_enforcer.unblock_client_runtime(normalized)
    except Exception as exc:
        logging.exception("WG runtime apply failed for client=%s action=%s: %s", client_name, action, exc)
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    payload = {
        "client_name": client_name,
        "action": action,
        **(result or {}),
    }
    print(json.dumps(payload, ensure_ascii=False))
    error_count = int((result or {}).get("error_count") or 0)
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())
