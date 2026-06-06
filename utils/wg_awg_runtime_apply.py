#!/usr/bin/env python3
"""Fast WG/AWG runtime block/unblock CLI.

This entrypoint intentionally does NOT import app.py, Flask, Flask-SQLAlchemy,
route wiring, schedulers, migrations, monitors, or the big service container.

It only needs:
  * client name/action from CLI;
  * WireGuard config file locations;
  * optional peer cache from SQLite table wireguard_peer_cache;
  * peer specs parsed from existing wg/awg config files;
  * wg/wg-quick subprocess calls.
"""

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

ENV_FILE_PATH = APP_ROOT / ".env"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 4

# Keep these defaults aligned with RuntimeSettingsService.WIREGUARD_CONFIG_FILES.
DEFAULT_WIREGUARD_CONFIG_FILES = {
    "antizapret": "/etc/wireguard/antizapret.conf",
    "vpn": "/etc/wireguard/vpn.conf",
}


def _load_dotenv_light(path: Path) -> None:
    """Tiny .env loader to avoid importing python-dotenv just for this CLI."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError as exc:
        logging.warning("Could not read .env file %s: %s", path, exc)
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _env_int(key: str, default: int, *, min_value: int | None = None) -> int:
    try:
        value = int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        value = int(default)
    if min_value is not None and value < min_value:
        value = min_value
    return value


def _resolve_sqlite_db_path() -> Path:
    """Resolve Flask-SQLAlchemy sqlite:///users.db path without creating Flask app.

    Flask-SQLAlchemy resolves relative sqlite paths under app.instance_path by
    default, so /opt/AdminAntizapret/instance/users.db is the expected path.
    A fallback to APP_ROOT/users.db is kept for older/manual deployments.
    """
    env_url = (os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL") or "").strip()
    if env_url.startswith("sqlite:////"):
        return Path(env_url.removeprefix("sqlite:///"))
    if env_url.startswith("sqlite:///"):
        rel = env_url.removeprefix("sqlite:///")
        # Match Flask-SQLAlchemy's behavior for relative sqlite paths.
        return APP_ROOT / "instance" / rel

    candidates = [
        APP_ROOT / "instance" / "users.db",
        APP_ROOT / "users.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _run(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _normalize_client_name(client_name: str) -> str:
    return (client_name or "").strip().lower()


def _wireguard_config_files() -> dict[str, str]:
    """Return WireGuard/AWG config files.

    RuntimeSettingsService currently returns static paths for this setting, so
    importing it would be unnecessary overhead. Optional env overrides are here
    for safe future customization without app.py imports.
    """
    return {
        "antizapret": os.getenv("WIREGUARD_ANTIZAPRET_CONFIG", DEFAULT_WIREGUARD_CONFIG_FILES["antizapret"]),
        "vpn": os.getenv("WIREGUARD_VPN_CONFIG", DEFAULT_WIREGUARD_CONFIG_FILES["vpn"]),
    }


def _collect_peer_specs_from_configs(wireguard_config_files: dict[str, str], client_name: str) -> list[dict]:
    try:
        from utils.wg_config_peers import collect_client_peer_specs
    except Exception as exc:
        logging.warning("Could not import utils.wg_config_peers: %s", exc)
        return []

    try:
        return list(collect_client_peer_specs(wireguard_config_files, client_name) or [])
    except Exception as exc:
        logging.warning("Could not collect peer specs from configs for %s: %s", client_name, exc)
        return []


def _collect_client_peers_from_cache(client_name: str) -> list[tuple[str, str]]:
    normalized = _normalize_client_name(client_name)
    if not normalized:
        return []

    db_path = _resolve_sqlite_db_path()
    if not db_path.exists():
        logging.warning("SQLite DB not found at %s; falling back to config parsing", db_path)
        return []

    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        try:
            rows = conn.execute(
                """
                SELECT interface_name, peer_public_key
                FROM wireguard_peer_cache
                WHERE lower(client_name) = ?
                """,
                (normalized,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logging.warning("Could not read wireguard_peer_cache from %s: %s", db_path, exc)
        return []

    peers: list[tuple[str, str]] = []
    for interface_name, peer_public_key in rows:
        iface = (interface_name or "").strip()
        key = (peer_public_key or "").strip()
        if iface and key:
            peers.append((iface, key))
    return peers


def _collect_client_peers(client_name: str, wireguard_config_files: dict[str, str]) -> list[tuple[str, str]]:
    peers = _collect_client_peers_from_cache(client_name)
    if peers:
        return peers

    return [
        (spec["interface_name"], spec["peer_public_key"])
        for spec in _collect_peer_specs_from_configs(wireguard_config_files, client_name)
        if spec.get("interface_name") and spec.get("peer_public_key")
    ]


def _sync_interface_from_stripped_config(interface_name: str, *, timeout: int) -> tuple[bool, str]:
    strip_result = _run(["wg-quick", "strip", interface_name], timeout=timeout)
    if strip_result.returncode != 0:
        return False, (strip_result.stderr or "").strip()

    stripped_config = strip_result.stdout or ""
    if not stripped_config.strip():
        return False, "empty stripped config"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
            temp_file.write(stripped_config)
            temp_path = temp_file.name
        sync_result = _run(["wg", "syncconf", interface_name, temp_path], timeout=timeout)
        if sync_result.returncode == 0:
            return True, ""
        return False, (sync_result.stderr or "").strip()
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _restore_peer_spec(spec: dict, *, timeout: int) -> tuple[bool, str]:
    interface_name = (spec.get("interface_name") or "").strip()
    peer_public_key = (spec.get("peer_public_key") or "").strip()
    if not interface_name or not peer_public_key:
        return False, "missing interface or public key"

    args = ["wg", "set", interface_name, "peer", peer_public_key]
    allowed_ips = (spec.get("allowed_ips") or "").strip()
    if allowed_ips:
        args.extend(["allowed-ips", allowed_ips])

    preshared_key = (spec.get("preshared_key") or "").strip()
    psk_path = None
    try:
        if preshared_key:
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".psk", delete=False) as psk_file:
                psk_file.write(preshared_key.encode("ascii"))
                psk_path = psk_file.name
            args.extend(["preshared-key", psk_path])

        result = _run(args, timeout=timeout)
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or "").strip()
    finally:
        if psk_path:
            try:
                os.unlink(psk_path)
            except OSError:
                pass


def block_client_runtime(client_name: str, *, wireguard_config_files: dict[str, str], timeout: int) -> dict:
    peers = _collect_client_peers(client_name, wireguard_config_files)
    removed = []
    errors = []

    for interface_name, peer_public_key in peers:
        result = _run(["wg", "set", interface_name, "peer", peer_public_key, "remove"], timeout=timeout)
        if result.returncode == 0:
            removed.append((interface_name, peer_public_key))
        else:
            errors.append(
                {
                    "interface": interface_name,
                    "peer_public_key": peer_public_key,
                    "stderr": (result.stderr or "").strip(),
                }
            )

    return {
        "removed_count": len(removed),
        "error_count": len(errors),
        "errors": errors,
    }


def unblock_client_runtime(client_name: str, *, wireguard_config_files: dict[str, str], timeout: int) -> dict:
    specs = _collect_peer_specs_from_configs(wireguard_config_files, client_name)
    restored = []
    errors = []

    if specs:
        for spec in specs:
            ok, stderr = _restore_peer_spec(spec, timeout=timeout)
            if ok:
                restored.append(spec.get("interface_name"))
            else:
                errors.append(
                    {
                        "interface": spec.get("interface_name"),
                        "stderr": stderr,
                    }
                )
        return {
            "synced_count": len(restored),
            "error_count": len(errors),
            "errors": errors,
        }

    peers = _collect_client_peers(client_name, wireguard_config_files)
    interfaces = sorted({iface for iface, _ in peers if iface})
    if not interfaces:
        interfaces = sorted(wireguard_config_files.keys())

    synced = []
    for interface_name in interfaces:
        if not (wireguard_config_files.get(interface_name) or "").strip():
            continue
        ok, stderr = _sync_interface_from_stripped_config(interface_name, timeout=timeout)
        if ok:
            synced.append(interface_name)
        else:
            errors.append(
                {
                    "interface": interface_name,
                    "stderr": stderr,
                }
            )

    return {
        "synced_count": len(synced),
        "error_count": len(errors),
        "errors": errors,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply WG/AWG runtime block or unblock for one client without importing app.py.")
    parser.add_argument("--client", required=True, help="WireGuard client name")
    parser.add_argument(
        "--action",
        required=True,
        choices=("block", "unblock"),
        help="Runtime action to apply",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        help="Timeout in seconds for each wg/wg-quick command",
    )
    return parser


def main(argv=None) -> int:
    _load_dotenv_light(ENV_FILE_PATH)

    args = _build_parser().parse_args(argv)
    client_name = (args.client or "").strip()
    action = (args.action or "").strip().lower()
    timeout = max(1, int(args.timeout or DEFAULT_COMMAND_TIMEOUT_SECONDS))

    if not client_name:
        logging.error("Client name is required")
        print(json.dumps({"error": "client name is required"}, ensure_ascii=False))
        return 2

    wireguard_config_files = _wireguard_config_files()

    try:
        normalized = _normalize_client_name(client_name)
        if action == "block":
            result = block_client_runtime(normalized, wireguard_config_files=wireguard_config_files, timeout=timeout)
        else:
            result = unblock_client_runtime(normalized, wireguard_config_files=wireguard_config_files, timeout=timeout)
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
