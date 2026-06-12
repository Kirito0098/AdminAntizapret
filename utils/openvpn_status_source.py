"""Lightweight OpenVPN status source for cron traffic_sync (no Flask)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from utils.openvpn_socket_reader import OpenVPNSocketReaderService

DEFAULT_OPENVPN_SOCKET_DIR = "/run/openvpn-server"
DEFAULT_OPENVPN_SOCKET_TIMEOUT = 2.5
DEFAULT_OPENVPN_SOCKET_IDLE_TIMEOUT = 0.12

_reader: Optional[OpenVPNSocketReaderService] = None


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return float(default)


def _get_reader() -> OpenVPNSocketReaderService:
    global _reader
    if _reader is None:
        _reader = OpenVPNSocketReaderService(
            openvpn_socket_dir=os.getenv("OPENVPN_SOCKET_DIR", DEFAULT_OPENVPN_SOCKET_DIR),
            openvpn_socket_timeout=_env_float("OPENVPN_SOCKET_TIMEOUT", DEFAULT_OPENVPN_SOCKET_TIMEOUT),
            openvpn_socket_idle_timeout=_env_float(
                "OPENVPN_SOCKET_IDLE_TIMEOUT",
                DEFAULT_OPENVPN_SOCKET_IDLE_TIMEOUT,
            ),
            openvpn_log_tail_lines=0,
            openvpn_event_max_response_bytes=0,
        )
    return _reader


def read_openvpn_status_socket_only(profile_key: str) -> Dict[str, Any]:
    """Query management socket without file fallback (PRE-FLIGHT comparison)."""
    reader = _get_reader()
    socket_path = reader.openvpn_socket_path(profile_key)
    raw_mgmt = reader.query_openvpn_management_socket(socket_path, "status 3")
    payload = reader.extract_status_payload_from_management(raw_mgmt)
    if payload:
        return {
            "raw": payload,
            "source_name": os.path.basename(socket_path),
            "exists": True,
            "updated_at_ts": int(time.time()),
            "source_type": "socket",
        }

    return {
        "raw": "",
        "source_name": os.path.basename(socket_path),
        "exists": False,
        "updated_at_ts": 0,
        "source_type": "socket",
    }


def read_openvpn_status_source(profile_key: str, fallback_path: str) -> Dict[str, Any]:
    mode = (os.getenv("TRAFFIC_SYNC_OPENVPN_SOURCE") or "socket").strip().lower()
    if mode == "file":
        from utils.traffic_sync import read_status_file

        result = read_status_file(profile_key, fallback_path)
        raw = result.get("raw", "")
        result["source_type"] = "file"
        result["exists"] = bool(raw)
        return result

    return _get_reader().read_status_source(profile_key, fallback_path)
