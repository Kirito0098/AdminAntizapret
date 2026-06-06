#!/usr/bin/env python3
"""Check Google Transparency Report Safe Browsing flag for a domain."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = (
    "https://transparencyreport.google.com/transparencyreport/api/v3/safebrowsing/status?site={site}"
)
XSSI_PREFIX = ")]}'"
USER_AGENT = "AdminAntizapret-SafeBrowsingMonitor/1.0 (+https://github.com/AdminAntizapret)"
DEFAULT_RETRIES = 3
BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def _strip_xssi(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith(XSSI_PREFIX):
        parts = text.splitlines()
        return "\n".join(parts[1:]).strip()
    return text


def parse_status_payload(raw_text: str) -> dict[str, object]:
    cleaned = _strip_xssi(raw_text)
    payload = json.loads(cleaned)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("Unexpected Safe Browsing payload format.")

    row = payload[0]
    if len(row) < 9:
        raise ValueError("Safe Browsing payload row is too short.")

    checked_at_iso = None
    checked_ms = row[7]
    if isinstance(checked_ms, (int, float)):
        checked_at_iso = dt.datetime.fromtimestamp(checked_ms / 1000, tz=dt.timezone.utc).isoformat()

    return {
        "record_type": row[0],
        "status_code": row[1],
        "threat_flag": bool(row[4]),
        "checked_at_ms": checked_ms,
        "checked_at_utc": checked_at_iso,
        "site": row[8],
        "raw_row": row,
    }


def fetch_site_status(
    site: str,
    *,
    timeout_seconds: int = 20,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, object]:
    target_url = API_URL.format(site=urllib.parse.quote(site))
    last_error: Exception | None = None

    for attempt in range(max(1, retries)):
        if attempt > 0:
            time.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])

        try:
            request = urllib.request.Request(
                target_url,
                headers={"User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw_status = getattr(response, "status", None)
                status_code = raw_status if isinstance(raw_status, int) else response.getcode()
                if status_code != 200:
                    raise urllib.error.HTTPError(
                        target_url,
                        status_code,
                        f"Unexpected HTTP status {status_code}",
                        response.headers,
                        None,
                    )
                raw = response.read().decode("utf-8", "replace")
            return parse_status_payload(raw)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc

    if last_error is None:
        raise RuntimeError("Failed to query Safe Browsing status.")
    raise last_error


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query Google Transparency Report Safe Browsing status for one site."
    )
    parser.add_argument("site", help="Host or domain (for example: admin.example.com)")
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    site = (args.site or "").strip()
    if not site:
        print("Site is required.", file=sys.stderr)
        return 1

    try:
        result = fetch_site_status(site)
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        RuntimeError,
    ) as exc:
        print(f"Failed to query Safe Browsing status: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"site={result['site']}")
        print(f"status_code={result['status_code']}")
        print(f"threat_flag={result['threat_flag']}")
        print(f"checked_at_utc={result['checked_at_utc']}")

    return 2 if result["threat_flag"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
