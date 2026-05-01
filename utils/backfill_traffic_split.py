#!/usr/bin/env python3
"""Backfill per-network traffic split counters in user_traffic_stat.

This utility reconciles historical rows created before split counters
(`total_*_vpn`, `total_*_antizapret`) were introduced.

Strategy:
- Compute missing received/sent bytes compared to total counters.
- If a row has zero Antizapret counters, assign missing bytes to VPN.
- Keep totals intact and never subtract existing counters.

By default runs in dry-run mode.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app, db, UserTrafficStat  # noqa: E402


logger = logging.getLogger(__name__)


def _row_missing_parts(row: UserTrafficStat) -> tuple[int, int]:
    total_rx = int(row.total_received or 0)
    total_tx = int(row.total_sent or 0)

    split_rx = int(row.total_received_vpn or 0) + int(row.total_received_antizapret or 0)
    split_tx = int(row.total_sent_vpn or 0) + int(row.total_sent_antizapret or 0)

    return max(total_rx - split_rx, 0), max(total_tx - split_tx, 0)


def _split_proportionally(missing: int, vpn_part: int, ant_part: int) -> tuple[int, int]:
    if missing <= 0:
        return 0, 0

    base = vpn_part + ant_part
    if base <= 0:
        return missing, 0

    vpn_add = int((missing * vpn_part) / base)
    ant_add = missing - vpn_add
    return vpn_add, ant_add


def backfill(apply_changes: bool, include_mixed_antizapret: bool = False) -> int:
    users = UserTrafficStat.query.yield_per(500)
    affected = 0
    skipped_nonzero_antizapret = 0
    pending_updates = 0

    for row in users:
        missing_rx, missing_tx = _row_missing_parts(row)
        if missing_rx == 0 and missing_tx == 0:
            continue

        ant_rx = int(row.total_received_antizapret or 0)
        ant_tx = int(row.total_sent_antizapret or 0)

        has_antizapret_data = ant_rx > 0 or ant_tx > 0
        if has_antizapret_data and not include_mixed_antizapret:
            # Conservative rule: if Antizapret already has values, skip auto-distribution.
            skipped_nonzero_antizapret += 1
            logger.info(
                f"SKIP {row.common_name}: missing_rx={missing_rx}, missing_tx={missing_tx}, "
                f"ant_rx={ant_rx}, ant_tx={ant_tx}"
            )
            continue

        affected += 1

        before_vpn_rx = int(row.total_received_vpn or 0)
        before_vpn_tx = int(row.total_sent_vpn or 0)
        before_ant_rx = int(row.total_received_antizapret or 0)
        before_ant_tx = int(row.total_sent_antizapret or 0)

        if has_antizapret_data:
            add_vpn_rx, add_ant_rx = _split_proportionally(missing_rx, before_vpn_rx, before_ant_rx)
            add_vpn_tx, add_ant_tx = _split_proportionally(missing_tx, before_vpn_tx, before_ant_tx)
        else:
            add_vpn_rx, add_ant_rx = missing_rx, 0
            add_vpn_tx, add_ant_tx = missing_tx, 0

        after_vpn_rx = before_vpn_rx + add_vpn_rx
        after_vpn_tx = before_vpn_tx + add_vpn_tx
        after_ant_rx = before_ant_rx + add_ant_rx
        after_ant_tx = before_ant_tx + add_ant_tx

        logger.info(
            f"{'APPLY' if apply_changes else 'DRY'} {row.common_name}: "
            f"vpn_rx {before_vpn_rx} -> {after_vpn_rx}, "
            f"vpn_tx {before_vpn_tx} -> {after_vpn_tx}, "
            f"ant_rx {before_ant_rx} -> {after_ant_rx}, "
            f"ant_tx {before_ant_tx} -> {after_ant_tx}"
        )

        if apply_changes:
            row.total_received_vpn = after_vpn_rx
            row.total_sent_vpn = after_vpn_tx
            row.total_received_antizapret = after_ant_rx
            row.total_sent_antizapret = after_ant_tx
            pending_updates += 1

            if pending_updates >= 500:
                db.session.commit()
                pending_updates = 0

    if apply_changes and pending_updates > 0:
        db.session.commit()

    logger.info("Affected rows: %s", affected)
    logger.info("Skipped rows (non-zero antizapret split): %s", skipped_nonzero_antizapret)
    return affected


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Backfill VPN/Antizapret split traffic counters from total counters"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to database. Without this flag, runs dry-run.",
    )
    parser.add_argument(
        "--include-mixed-antizapret",
        action="store_true",
        help=(
            "Also backfill rows with existing Antizapret counters using proportional "
            "distribution between VPN and Antizapret."
        ),
    )
    args = parser.parse_args()

    with app.app_context():
        backfill(
            apply_changes=args.apply,
            include_mixed_antizapret=args.include_mixed_antizapret,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
