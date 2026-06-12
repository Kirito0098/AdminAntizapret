#!/usr/bin/env python3
"""Fast traffic snapshot sync for AdminAntizapret.

This is a lightweight replacement for utils/traffic_sync.py.

It intentionally does NOT import app.py, Flask, SQLAlchemy, routes, schedulers,
or the full services bundle for the traffic snapshot itself. It reads OpenVPN status
via management socket (`status 3`, file fallback) and `wg show all dump`, persists
traffic deltas directly into SQLite, then
optionally runs a lightweight traffic-limit reconcile via utils.traffic_limit_reconcile
(ADMIN_ANTIZAPRET_SKIP_APP_BOOTSTRAP).

Default DB path matches Flask-SQLAlchemy sqlite:///users.db:
    /opt/AdminAntizapret/instance/users.db

Exit codes:
    0 - success
    1 - runtime error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import warnings

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.openvpn_status_source import read_openvpn_status_source

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r"datetime\.datetime\.utcnow\(\) is deprecated.*",
)
INSTANCE_DB = ROOT_DIR / "instance" / "users.db"
FALLBACK_DB = ROOT_DIR / "users.db"

DEFAULT_LOGS_DIR = "/etc/openvpn/server/logs"
DEFAULT_STATUS_LOG_FILES = {
    "antizapret-tcp": os.path.join(DEFAULT_LOGS_DIR, "antizapret-tcp-status.log"),
    "antizapret-udp": os.path.join(DEFAULT_LOGS_DIR, "antizapret-udp-status.log"),
    "vpn-tcp": os.path.join(DEFAULT_LOGS_DIR, "vpn-tcp-status.log"),
    "vpn-udp": os.path.join(DEFAULT_LOGS_DIR, "vpn-udp-status.log"),
}
DEFAULT_WIREGUARD_CONFIG_FILES = {
    "antizapret": "/etc/wireguard/antizapret.conf",
    "vpn": "/etc/wireguard/vpn.conf",
}
DEFAULT_WIREGUARD_ACTIVE_HANDSHAKE_SECONDS = 180
DEFAULT_WIREGUARD_PEER_CACHE_SYNC_MIN_INTERVAL_SECONDS = 300


def utcnow_sql() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def dt_sql(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S.%f")


def env_int(key: str, default: int, min_value: Optional[int] = None) -> int:
    try:
        value = int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        value = int(default)
    if min_value is not None and value < int(min_value):
        value = int(min_value)
    return value


def resolve_db_path(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_db = (os.getenv("ADMIN_ANTIZAPRET_DB_PATH") or os.getenv("SQLITE_DB_PATH") or "").strip()
    if env_db:
        return Path(env_db).expanduser().resolve()
    if INSTANCE_DB.exists():
        return INSTANCE_DB
    return FALLBACK_DB


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def human_bytes(value: int) -> str:
    size = float(value or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    precision = 0 if idx == 0 else (2 if size < 10 else 1)
    return f"{size:.{precision}f} {units[idx]}"


def normalize_openvpn_endpoint(endpoint: str) -> str:
    return re.sub(r"^(?:tcp|udp)\d(?:-server)?:", "", (endpoint or "").strip(), flags=re.IGNORECASE)


def extract_ip_from_openvpn_address(address: str) -> str:
    normalized = normalize_openvpn_endpoint(address)
    if not normalized:
        return normalized

    if normalized.startswith("["):
        m_v6 = re.match(r"^\[([^\]]+)\](?::\d+)?$", normalized)
        if m_v6:
            return m_v6.group(1)

    if ":" in normalized:
        host_part, maybe_port = normalized.rsplit(":", 1)
        if maybe_port.isdigit():
            return host_part

    return normalized


def extract_ip_from_wireguard_endpoint(endpoint: str) -> str:
    value = (endpoint or "").strip()
    if not value or value == "(none)":
        return ""

    if value.startswith("["):
        m_v6 = re.match(r"^\[([^\]]+)\](?::\d+)?$", value)
        if m_v6:
            return m_v6.group(1)

    if ":" in value:
        host_part, maybe_port = value.rsplit(":", 1)
        if maybe_port.isdigit():
            return host_part

    return value


def profile_meta(profile_key: str) -> Dict[str, str]:
    is_antizapret = profile_key.startswith("antizapret")
    is_tcp = "-tcp" in profile_key
    is_wireguard = profile_key.endswith("-wg")
    return {
        "network": "Antizapret" if is_antizapret else "VPN",
        "transport": "TCP" if is_tcp else "UDP",
        "protocol": "WireGuard" if is_wireguard else "OpenVPN",
    }


def normalize_wireguard_allowed_ip(token: str) -> str:
    value = (token or "").strip()
    if not value or value.lower() == "(none)":
        return ""
    return value.split("/", 1)[0].strip()


def split_wireguard_allowed_ips(value: str) -> List[str]:
    out: List[str] = []
    for token in (value or "").split(","):
        ip = normalize_wireguard_allowed_ip(token)
        if ip:
            out.append(ip)
    return out


def is_wireguard_peer_active(latest_handshake_ts: int, active_seconds: int) -> bool:
    handshake_ts = int(latest_handshake_ts or 0)
    if handshake_ts <= 0:
        return False
    if active_seconds <= 0:
        return True
    return max(int(time.time()) - handshake_ts, 0) <= active_seconds


def read_status_file(profile_key: str, filename: str) -> Dict[str, Any]:
    path = Path(filename)
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        raw = ""
    except OSError:
        raw = ""

    updated_at_ts = 0
    try:
        updated_at_ts = int(path.stat().st_mtime) if path.exists() else 0
    except OSError:
        updated_at_ts = 0

    return {
        "raw": raw,
        "updated_at_ts": updated_at_ts,
        "source_name": path.name,
    }


def parse_status_from_source(
    profile_key: str,
    filename: str,
    source: Dict[str, Any],
) -> Dict[str, Any]:
    raw = source.get("raw", "")
    meta = profile_meta(profile_key)

    if not raw:
        return {
            "profile": profile_key,
            "label": f"{meta['network']} {meta['transport']}",
            "protocol": meta["protocol"],
            "filename": source.get("source_name", os.path.basename(filename)),
            "exists": False,
            "snapshot_time": "-",
            "updated_at": "-",
            "client_count": 0,
            "unique_real_ips": 0,
            "total_received": 0,
            "total_sent": 0,
            "clients": [],
        }

    time_match = re.search(r"TIME,([^,\n]+),(\d{10,})", raw)
    if time_match:
        snapshot_time = time_match.group(1).strip()
    else:
        time_match_tab = re.search(
            r"^TIME\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\d{10,})$",
            raw,
            re.MULTILINE,
        )
        snapshot_time = time_match_tab.group(1).strip() if time_match_tab else "-"

    updated_ts = int(source.get("updated_at_ts") or 0)
    updated_at = datetime.fromtimestamp(updated_ts).strftime("%Y-%m-%d %H:%M:%S") if updated_ts > 0 else "-"

    clients: List[Dict[str, Any]] = []

    client_pattern = re.compile(
        r"CLIENT_LIST,([^,\n]+),([^,\n]+),([^,\n]*),([^,\n]*),(\d+),(\d+),([^,\n]+),(\d+),([^,\n]*),([^,\n]*),([^,\n]*),([^,\n\r ]+)"
    )

    for match in client_pattern.finditer(raw):
        common_name = match.group(1).strip()
        real_address = match.group(2).strip()
        virtual_address = match.group(3).strip()
        bytes_received = int(match.group(5) or 0)
        bytes_sent = int(match.group(6) or 0)
        connected_since = match.group(7).strip()
        connected_since_ts = int(match.group(8) or 0)
        cipher = match.group(12).strip()

        clients.append(
            {
                "common_name": common_name,
                "real_address": real_address,
                "real_ip": extract_ip_from_openvpn_address(real_address),
                "virtual_address": virtual_address,
                "session_kind": "openvpn",
                "bytes_received": bytes_received,
                "bytes_sent": bytes_sent,
                "total_bytes": bytes_received + bytes_sent,
                "connected_since": connected_since,
                "connected_since_ts": connected_since_ts,
                "cipher": cipher,
            }
        )

    if not clients:
        client_pattern_tab = re.compile(
            r"^CLIENT_LIST\s+(\S+)\s+(\S+)\s+(\S+)\s+(?:(\S+)\s+)?(\d+)\s+(\d+)\s+"
            r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)",
            re.MULTILINE,
        )

        for match in client_pattern_tab.finditer(raw):
            common_name = match.group(1).strip()
            real_address = match.group(2).strip()
            virtual_address = match.group(3).strip()
            bytes_received = int(match.group(5) or 0)
            bytes_sent = int(match.group(6) or 0)
            connected_since = match.group(7).strip()
            connected_since_ts = int(match.group(8) or 0)
            cipher = match.group(12).strip()

            clients.append(
                {
                    "common_name": common_name,
                    "real_address": real_address,
                    "real_ip": extract_ip_from_openvpn_address(real_address),
                    "virtual_address": virtual_address,
                    "session_kind": "openvpn",
                    "bytes_received": bytes_received,
                    "bytes_sent": bytes_sent,
                    "total_bytes": bytes_received + bytes_sent,
                    "connected_since": connected_since,
                    "connected_since_ts": connected_since_ts,
                    "cipher": cipher,
                }
            )

    clients.sort(key=lambda x: int(x.get("total_bytes") or 0), reverse=True)

    total_received = sum(int(c.get("bytes_received") or 0) for c in clients)
    total_sent = sum(int(c.get("bytes_sent") or 0) for c in clients)
    unique_real_ips = len({c.get("real_ip") for c in clients if c.get("real_ip")})

    return {
        "profile": profile_key,
        "label": f"{meta['network']} {meta['transport']}",
        "protocol": meta["protocol"],
        "filename": source.get("source_name", os.path.basename(filename)),
        "exists": True,
        "snapshot_time": snapshot_time,
        "updated_at": updated_at,
        "client_count": len(clients),
        "unique_real_ips": unique_real_ips,
        "total_received": total_received,
        "total_sent": total_sent,
        "clients": clients,
    }


def parse_status_log(profile_key: str, filename: str) -> Dict[str, Any]:
    source = read_openvpn_status_source(profile_key, filename)
    return parse_status_from_source(profile_key, filename, source)


def parse_wireguard_config_peer_rows(config_path: str, interface_name: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        raw_lines = Path(config_path).read_text(encoding="utf-8", errors="ignore").splitlines()
    except FileNotFoundError:
        return []
    except OSError:
        return []

    pending_client_name = ""
    current_peer: Optional[Dict[str, str]] = None

    def flush_peer(peer_state: Optional[Dict[str, str]]) -> None:
        if not peer_state:
            return
        peer_key = (peer_state.get("peer_public_key") or "").strip()
        client_name = (peer_state.get("client_name") or "").strip()
        if not peer_key or not client_name:
            return
        rows.append(
            {
                "interface_name": interface_name,
                "peer_public_key": peer_key,
                "client_name": client_name,
                "allowed_ips": (peer_state.get("allowed_ips") or "").strip() or None,
            }
        )

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue

        m_client = re.match(r"^#\s*Client\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if m_client:
            pending_client_name = (m_client.group(1) or "").strip()
            continue

        if re.match(r"^\[Peer\]$", line, flags=re.IGNORECASE):
            flush_peer(current_peer)
            current_peer = {
                "client_name": pending_client_name,
                "peer_public_key": "",
                "allowed_ips": "",
            }
            pending_client_name = ""
            continue

        if line.startswith("[") and line.endswith("]"):
            flush_peer(current_peer)
            current_peer = None
            continue

        if current_peer is None:
            continue

        m_pub = re.match(r"^PublicKey\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if m_pub:
            current_peer["peer_public_key"] = (m_pub.group(1) or "").strip()
            continue

        m_allowed = re.match(r"^AllowedIPs\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if m_allowed:
            current_peer["allowed_ips"] = (m_allowed.group(1) or "").strip()

    flush_peer(current_peer)
    return rows


def load_wireguard_peer_cache_maps(conn: sqlite3.Connection) -> Tuple[Dict[Tuple[str, str], str], Dict[Tuple[str, str], str]]:
    by_public_key: Dict[Tuple[str, str], str] = {}
    by_allowed_ip: Dict[Tuple[str, str], str] = {}

    try:
        rows = conn.execute(
            "SELECT interface_name, peer_public_key, client_name, allowed_ips FROM wireguard_peer_cache"
        ).fetchall()
    except sqlite3.Error:
        rows = []

    for row in rows:
        interface_name = (row["interface_name"] or "").strip()
        peer_public_key = (row["peer_public_key"] or "").strip()
        client_name = (row["client_name"] or "").strip()
        if not interface_name or not client_name:
            continue

        if peer_public_key:
            by_public_key[(interface_name, peer_public_key)] = client_name

        for ip in split_wireguard_allowed_ips(row["allowed_ips"] or ""):
            by_allowed_ip[(interface_name, ip)] = client_name

    return by_public_key, by_allowed_ip


def sync_wireguard_peer_cache_from_configs(conn: sqlite3.Connection, wireguard_config_files: Dict[str, str]) -> int:
    parsed_rows: List[Dict[str, Any]] = []
    for interface_name, config_path in wireguard_config_files.items():
        parsed_rows.extend(parse_wireguard_config_peer_rows(config_path, interface_name))

    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in parsed_rows:
        key = ((row.get("interface_name") or "").strip(), (row.get("peer_public_key") or "").strip())
        if not key[0] or not key[1]:
            continue
        by_key[key] = row

    existing_rows = conn.execute(
        "SELECT id, interface_name, peer_public_key, client_name, allowed_ips FROM wireguard_peer_cache"
    ).fetchall()
    existing_by_key = {
        ((row["interface_name"] or "").strip(), (row["peer_public_key"] or "").strip()): row
        for row in existing_rows
    }

    for key, parsed in by_key.items():
        existing = existing_by_key.pop(key, None)
        parsed_name = (parsed.get("client_name") or "").strip()
        parsed_allowed = (parsed.get("allowed_ips") or "").strip() or None
        now = utcnow_sql()

        if existing is None:
            conn.execute(
                """
                INSERT INTO wireguard_peer_cache
                    (interface_name, peer_public_key, client_name, allowed_ips, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key[0], key[1], parsed_name, parsed_allowed, now),
            )
            continue

        if (
            ((existing["client_name"] or "").strip() != parsed_name)
            or (((existing["allowed_ips"] or "").strip() or None) != parsed_allowed)
        ):
            conn.execute(
                """
                UPDATE wireguard_peer_cache
                SET client_name = ?, allowed_ips = ?, updated_at = ?
                WHERE id = ?
                """,
                (parsed_name, parsed_allowed, now, existing["id"]),
            )

    for stale_row in existing_by_key.values():
        conn.execute("DELETE FROM wireguard_peer_cache WHERE id = ?", (stale_row["id"],))

    return len(by_key)


def collect_wireguard_status_rows(
    conn: sqlite3.Connection,
    wireguard_config_files: Dict[str, str],
    active_handshake_seconds: int,
) -> List[Dict[str, Any]]:
    status_rows = {
        "antizapret": {
            "profile": "antizapret-wg",
            "label": "Antizapret WG",
            "protocol": "WireGuard",
            "filename": "wg:antizapret",
            "exists": False,
            "clients": [],
            "traffic_clients": [],
        },
        "vpn": {
            "profile": "vpn-wg",
            "label": "VPN WG",
            "protocol": "WireGuard",
            "filename": "wg:vpn",
            "exists": False,
            "clients": [],
            "traffic_clients": [],
        },
    }

    try:
        result = subprocess.run(
            ["wg", "show", "all", "dump"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except Exception:
        result = None

    if result is None or result.returncode != 0:
        return list(status_rows.values())

    now_dt = datetime.utcnow()
    snapshot_time = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    parsed_peers: List[Dict[str, Any]] = []
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) == 5:
            interface_name = (parts[0] or "").strip()
            if interface_name in status_rows:
                status_rows[interface_name]["exists"] = True
                status_rows[interface_name]["snapshot_time"] = snapshot_time
                status_rows[interface_name]["updated_at"] = snapshot_time
            continue

        if len(parts) < 8:
            continue

        interface_name = (parts[0] or "").strip()
        if interface_name not in status_rows:
            continue

        status_rows[interface_name]["exists"] = True
        status_rows[interface_name]["snapshot_time"] = snapshot_time
        status_rows[interface_name]["updated_at"] = snapshot_time

        try:
            latest_handshake_ts = int(parts[5] or 0)
        except (TypeError, ValueError):
            latest_handshake_ts = 0
        try:
            bytes_received = int(parts[6] or 0)
        except (TypeError, ValueError):
            bytes_received = 0
        try:
            bytes_sent = int(parts[7] or 0)
        except (TypeError, ValueError):
            bytes_sent = 0

        parsed_peers.append(
            {
                "interface": interface_name,
                "peer_public_key": (parts[1] or "").strip(),
                "endpoint": (parts[3] or "").strip(),
                "allowed_ips": (parts[4] or "").strip(),
                "latest_handshake_ts": latest_handshake_ts,
                "bytes_received": max(bytes_received, 0),
                "bytes_sent": max(bytes_sent, 0),
            }
        )

    by_public_key, by_allowed_ip = load_wireguard_peer_cache_maps(conn)
    missing_mapping = False
    for peer in parsed_peers:
        iface = peer.get("interface")
        key = (iface, (peer.get("peer_public_key") or "").strip())
        allowed_candidates = split_wireguard_allowed_ips(peer.get("allowed_ips") or "")
        fallback_ip = allowed_candidates[0] if allowed_candidates else ""
        if key in by_public_key:
            continue
        if fallback_ip and (iface, fallback_ip) in by_allowed_ip:
            continue
        missing_mapping = True
        break

    if missing_mapping:
        sync_wireguard_peer_cache_from_configs(conn, wireguard_config_files)
        by_public_key, by_allowed_ip = load_wireguard_peer_cache_maps(conn)

    for peer in parsed_peers:
        interface_name = peer.get("interface")
        row = status_rows[interface_name]

        allowed_ips = split_wireguard_allowed_ips(peer.get("allowed_ips") or "")
        preferred_allowed_ip = allowed_ips[0] if allowed_ips else ""
        peer_public_key = (peer.get("peer_public_key") or "").strip()

        common_name = by_public_key.get((interface_name, peer_public_key))
        if not common_name and preferred_allowed_ip:
            common_name = by_allowed_ip.get((interface_name, preferred_allowed_ip))
        if not common_name:
            if preferred_allowed_ip:
                common_name = f"{interface_name}-{preferred_allowed_ip}"
            elif peer_public_key:
                common_name = f"{interface_name}-{peer_public_key[:10]}"
            else:
                common_name = f"{interface_name}-peer"

        endpoint = (peer.get("endpoint") or "").strip()
        real_ip = extract_ip_from_wireguard_endpoint(endpoint)
        latest_handshake_ts = int(peer.get("latest_handshake_ts") or 0)
        connected_since = "-"
        if latest_handshake_ts > 0:
            try:
                connected_since = datetime.fromtimestamp(latest_handshake_ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                connected_since = "-"

        client_payload = {
            "common_name": common_name,
            "real_address": endpoint if endpoint and endpoint != "(none)" else "-",
            "real_ip": real_ip,
            "virtual_address": preferred_allowed_ip or "-",
            "peer_public_key": peer_public_key,
            "session_kind": "wireguard",
            "bytes_received": int(peer.get("bytes_received") or 0),
            "bytes_sent": int(peer.get("bytes_sent") or 0),
            "total_bytes": int(peer.get("bytes_received") or 0) + int(peer.get("bytes_sent") or 0),
            "connected_since": connected_since,
            "connected_since_ts": latest_handshake_ts,
            "cipher": "WireGuard",
        }

        row["traffic_clients"].append(client_payload)
        if is_wireguard_peer_active(latest_handshake_ts, active_handshake_seconds):
            row["clients"].append(client_payload)

    return [status_rows["antizapret"], status_rows["vpn"]]


def collect_status_rows_for_snapshot(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    logs_dir = os.getenv("LOGS_DIR", DEFAULT_LOGS_DIR)
    status_log_files = {
        "antizapret-tcp": os.path.join(logs_dir, "antizapret-tcp-status.log"),
        "antizapret-udp": os.path.join(logs_dir, "antizapret-udp-status.log"),
        "vpn-tcp": os.path.join(logs_dir, "vpn-tcp-status.log"),
        "vpn-udp": os.path.join(logs_dir, "vpn-udp-status.log"),
    }

    wireguard_config_files = dict(DEFAULT_WIREGUARD_CONFIG_FILES)
    active_seconds = env_int(
        "WIREGUARD_ACTIVE_HANDSHAKE_SECONDS",
        DEFAULT_WIREGUARD_ACTIVE_HANDSHAKE_SECONDS,
        min_value=0,
    )

    rows = [parse_status_log(profile_key, filename) for profile_key, filename in status_log_files.items()]
    rows.extend(collect_wireguard_status_rows(conn, wireguard_config_files, active_seconds))
    return rows


def normalize_traffic_protocol_type(protocol_type: str, fallback: str = "openvpn") -> str:
    value = (protocol_type or fallback or "openvpn").strip().lower()
    if value in {"wg", "wireguard", "amneziawg", "awg"}:
        return "wireguard"
    if value in {"openvpn", "ovpn"}:
        return "openvpn"
    return fallback


def build_session_key(profile: str, client: Dict[str, Any]) -> str:
    session_kind = (client.get("session_kind") or "").strip().lower()
    if session_kind == "wireguard" or str(profile or "").endswith("-wg"):
        common_name = (client.get("common_name") or "-").strip()
        peer_public_key = (client.get("peer_public_key") or "-").strip()
        virtual_address = (client.get("virtual_address") or "-").strip()
        return f"{profile}|wg|{common_name}|{peer_public_key}|{virtual_address}"

    common_name = (client.get("common_name") or "-").strip()
    real_address = (client.get("real_address") or "-").strip()
    virtual_address = (client.get("virtual_address") or "-").strip()
    connected_since_ts = int(client.get("connected_since_ts") or 0)
    return f"{profile}|{common_name}|{real_address}|{virtual_address}|{connected_since_ts}"


def load_sessions_by_key(conn: sqlite3.Connection) -> Dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT id, session_key, profile, common_name, real_address, virtual_address,
               connected_since_ts, last_bytes_received, last_bytes_sent, is_active,
               last_seen_at, ended_at
        FROM traffic_session_state
        """
    ).fetchall()
    return {row["session_key"]: row for row in rows}


def load_stats_by_user(conn: sqlite3.Connection) -> Dict[Tuple[str, str], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT id, common_name, protocol_type, total_received, total_sent,
               total_received_vpn, total_sent_vpn,
               total_received_antizapret, total_sent_antizapret,
               total_sessions, first_seen_at, last_seen_at
        FROM user_traffic_stat_protocol
        """
    ).fetchall()
    return {
        (
            (row["common_name"] or "").strip(),
            normalize_traffic_protocol_type(row["protocol_type"], fallback="openvpn"),
        ): row
        for row in rows
    }


def insert_session_state(
    conn: sqlite3.Connection,
    *,
    session_key: str,
    profile: str,
    common_name: str,
    client: Dict[str, Any],
    current_rx: int,
    current_tx: int,
    now: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO traffic_session_state
            (session_key, profile, common_name, real_address, virtual_address,
             connected_since_ts, last_bytes_received, last_bytes_sent,
             is_active, last_seen_at, ended_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL)
        """,
        (
            session_key,
            profile,
            common_name,
            (client.get("real_address") or "").strip() or None,
            (client.get("virtual_address") or "").strip() or None,
            int(client.get("connected_since_ts") or 0),
            current_rx,
            current_tx,
            now,
        ),
    )
    return int(cur.lastrowid)


def update_session_state(
    conn: sqlite3.Connection,
    *,
    row_id: int,
    current_rx: int,
    current_tx: int,
    now: str,
) -> None:
    conn.execute(
        """
        UPDATE traffic_session_state
        SET last_bytes_received = ?,
            last_bytes_sent = ?,
            last_seen_at = ?,
            is_active = 1,
            ended_at = NULL
        WHERE id = ?
        """,
        (current_rx, current_tx, now, row_id),
    )


def insert_stat_protocol(
    conn: sqlite3.Connection,
    *,
    common_name: str,
    protocol_type: str,
    now: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO user_traffic_stat_protocol
            (common_name, protocol_type, total_received, total_sent,
             total_received_vpn, total_sent_vpn,
             total_received_antizapret, total_sent_antizapret,
             total_sessions, first_seen_at, last_seen_at, updated_at)
        VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, ?, ?, ?)
        """,
        (common_name, protocol_type, now, now, now),
    )
    return int(cur.lastrowid)


def update_stat_protocol(
    conn: sqlite3.Connection,
    *,
    row_id: int,
    delta_rx: int,
    delta_tx: int,
    is_antizapret_profile: bool,
    is_new_session: bool,
    now: str,
) -> None:
    if is_antizapret_profile:
        conn.execute(
            """
            UPDATE user_traffic_stat_protocol
            SET total_received = COALESCE(total_received, 0) + ?,
                total_sent = COALESCE(total_sent, 0) + ?,
                total_received_antizapret = COALESCE(total_received_antizapret, 0) + ?,
                total_sent_antizapret = COALESCE(total_sent_antizapret, 0) + ?,
                total_sessions = COALESCE(total_sessions, 0) + ?,
                last_seen_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (delta_rx, delta_tx, delta_rx, delta_tx, 1 if is_new_session else 0, now, now, row_id),
        )
    else:
        conn.execute(
            """
            UPDATE user_traffic_stat_protocol
            SET total_received = COALESCE(total_received, 0) + ?,
                total_sent = COALESCE(total_sent, 0) + ?,
                total_received_vpn = COALESCE(total_received_vpn, 0) + ?,
                total_sent_vpn = COALESCE(total_sent_vpn, 0) + ?,
                total_sessions = COALESCE(total_sessions, 0) + ?,
                last_seen_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (delta_rx, delta_tx, delta_rx, delta_tx, 1 if is_new_session else 0, now, now, row_id),
        )


def insert_traffic_sample(
    conn: sqlite3.Connection,
    *,
    common_name: str,
    network_type: str,
    protocol_type: str,
    delta_rx: int,
    delta_tx: int,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO user_traffic_sample
            (common_name, network_type, protocol_type, delta_received, delta_sent, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (common_name, network_type, protocol_type, delta_rx, delta_tx, now),
    )


def mark_inactive_sessions(
    conn: sqlite3.Connection,
    *,
    active_before: Iterable[str],
    seen_keys: Iterable[str],
    now: str,
) -> int:
    active_before_set = set(active_before)
    seen_set = set(seen_keys)
    to_end = sorted(active_before_set - seen_set)
    if not to_end:
        return 0

    conn.executemany(
        """
        UPDATE traffic_session_state
        SET is_active = 0,
            ended_at = ?
        WHERE session_key = ? AND is_active = 1
        """,
        [(now, key) for key in to_end],
    )
    return len(to_end)


def persist_traffic_snapshot(conn: sqlite3.Connection, status_rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    now = utcnow_sql()

    sessions_by_key = load_sessions_by_key(conn)
    previously_active_keys = {
        key for key, row in sessions_by_key.items() if bool(row["is_active"])
    }
    stats_by_user = load_stats_by_user(conn)

    seen_keys = set()
    samples_inserted = 0
    sessions_created = 0
    sessions_updated = 0
    stats_created = 0

    for status_row in status_rows:
        profile = status_row.get("profile", "unknown")
        clients = status_row.get("traffic_clients", status_row.get("clients", []))
        for client in clients:
            session_key = build_session_key(profile, client)
            if session_key in seen_keys:
                continue
            seen_keys.add(session_key)

            current_rx = int(client.get("bytes_received") or 0)
            current_tx = int(client.get("bytes_sent") or 0)
            common_name = (client.get("common_name") or "-").strip()
            is_antizapret_profile = str(profile).startswith("antizapret")
            is_wireguard_profile = str(profile).endswith("-wg")
            protocol_type = "wireguard" if is_wireguard_profile else "openvpn"

            session_state = sessions_by_key.get(session_key)
            is_new_session = session_state is None

            if is_new_session:
                row_id = insert_session_state(
                    conn,
                    session_key=session_key,
                    profile=profile,
                    common_name=common_name,
                    client=client,
                    current_rx=current_rx,
                    current_tx=current_tx,
                    now=now,
                )
                # Keep lightweight cache in sync for duplicate detection in the same run.
                sessions_by_key[session_key] = {
                    "id": row_id,
                    "last_bytes_received": current_rx,
                    "last_bytes_sent": current_tx,
                    "is_active": 1,
                }
                sessions_created += 1

                if is_wireguard_profile:
                    # Same as original service: for a new WG key, current counters are baseline.
                    delta_rx = 0
                    delta_tx = 0
                else:
                    delta_rx = max(current_rx, 0)
                    delta_tx = max(current_tx, 0)
            else:
                delta_rx = current_rx - int(session_state["last_bytes_received"] or 0)
                delta_tx = current_tx - int(session_state["last_bytes_sent"] or 0)

                if delta_rx < 0:
                    delta_rx = max(current_rx, 0)
                if delta_tx < 0:
                    delta_tx = max(current_tx, 0)

                update_session_state(
                    conn,
                    row_id=int(session_state["id"]),
                    current_rx=current_rx,
                    current_tx=current_tx,
                    now=now,
                )
                sessions_updated += 1

            delta_rx = max(delta_rx, 0)
            delta_tx = max(delta_tx, 0)

            stat_key = (common_name, protocol_type)
            user_stat = stats_by_user.get(stat_key)
            if user_stat is None:
                stat_id = insert_stat_protocol(
                    conn,
                    common_name=common_name,
                    protocol_type=protocol_type,
                    now=now,
                )
                user_stat = {"id": stat_id}
                stats_by_user[stat_key] = user_stat
                stats_created += 1

            update_stat_protocol(
                conn,
                row_id=int(user_stat["id"]),
                delta_rx=delta_rx,
                delta_tx=delta_tx,
                is_antizapret_profile=is_antizapret_profile,
                is_new_session=is_new_session,
                now=now,
            )

            if delta_rx > 0 or delta_tx > 0:
                insert_traffic_sample(
                    conn,
                    common_name=common_name,
                    network_type="antizapret" if is_antizapret_profile else "vpn",
                    protocol_type=protocol_type,
                    delta_rx=delta_rx,
                    delta_tx=delta_tx,
                    now=now,
                )
                samples_inserted += 1

    sessions_marked_inactive = mark_inactive_sessions(
        conn,
        active_before=previously_active_keys,
        seen_keys=seen_keys,
        now=now,
    )

    return {
        "status_rows": len(status_rows),
        "seen_sessions": len(seen_keys),
        "sessions_created": sessions_created,
        "sessions_updated": sessions_updated,
        "sessions_marked_inactive": sessions_marked_inactive,
        "stats_created": stats_created,
        "samples_inserted": samples_inserted,
    }


def _traffic_limit_reconcile_enabled(*, cli_skip: bool = False) -> bool:
    if cli_skip:
        return False
    enabled = (os.getenv("TRAFFIC_LIMIT_RECONCILE_AFTER_SYNC", "true") or "true").strip().lower()
    return enabled in {"1", "true", "yes", "on"}


def run_traffic_limit_reconcile(*, skip: bool = False) -> Dict[str, Any]:
    """Reconcile traffic-limit policies after persisting traffic deltas."""
    if not _traffic_limit_reconcile_enabled(cli_skip=skip):
        return {"traffic_limit_reconcile": "skipped"}

    root = str(ROOT_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from utils.traffic_limit_reconcile import reconcile_traffic_limit_policies

        reconcile_traffic_limit_policies()
        return {"traffic_limit_reconcile": "ok"}
    except Exception as exc:
        return {
            "traffic_limit_reconcile": "error",
            "traffic_limit_reconcile_error": str(exc),
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fast AdminAntizapret traffic snapshot sync.")
    parser.add_argument("--db", default="", help="Path to users.db. Defaults to instance/users.db.")
    parser.add_argument("--json", action="store_true", help="Print a compact JSON summary.")
    parser.add_argument("--no-wg", action="store_true", help="Skip WireGuard status collection.")
    parser.add_argument("--no-openvpn", action="store_true", help="Skip OpenVPN status log collection.")
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        help="Skip post-sync traffic-limit policy reconcile.",
    )
    return parser


def run_sync(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    db_path = resolve_db_path(args.db)

    if not db_path.exists():
        print(json.dumps({"error": f"database not found: {db_path}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    conn = connect_db(db_path)
    try:
        if args.no_openvpn and args.no_wg:
            status_rows: List[Dict[str, Any]] = []
        else:
            if args.no_wg:
                logs_dir = os.getenv("LOGS_DIR", DEFAULT_LOGS_DIR)
                status_log_files = {
                    "antizapret-tcp": os.path.join(logs_dir, "antizapret-tcp-status.log"),
                    "antizapret-udp": os.path.join(logs_dir, "antizapret-udp-status.log"),
                    "vpn-tcp": os.path.join(logs_dir, "vpn-tcp-status.log"),
                    "vpn-udp": os.path.join(logs_dir, "vpn-udp-status.log"),
                }
                status_rows = [parse_status_log(profile_key, filename) for profile_key, filename in status_log_files.items()]
            elif args.no_openvpn:
                status_rows = collect_wireguard_status_rows(
                    conn,
                    DEFAULT_WIREGUARD_CONFIG_FILES,
                    env_int(
                        "WIREGUARD_ACTIVE_HANDSHAKE_SECONDS",
                        DEFAULT_WIREGUARD_ACTIVE_HANDSHAKE_SECONDS,
                        min_value=0,
                    ),
                )
            else:
                status_rows = collect_status_rows_for_snapshot(conn)

        with conn:
            summary = persist_traffic_snapshot(conn, status_rows)

        reconcile_summary = run_traffic_limit_reconcile(skip=bool(args.no_reconcile))

        if args.json:
            print(
                json.dumps(
                    {"ok": True, "db": str(db_path), **summary, **reconcile_summary},
                    ensure_ascii=False,
                )
            )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        sys.exit(run_sync())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
