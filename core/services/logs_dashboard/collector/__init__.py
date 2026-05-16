from collections import Counter, defaultdict
from datetime import datetime
import os

from .events import (
    build_peer_info_context,
    collect_event_rows,
    enrich_client_aggregate_from_events,
)


def collect_logs_dashboard_data(
    *,
    app,
    db,
    _collect_status_rows_for_snapshot,
    _persist_traffic_snapshot,
    _parse_event_log,
    EVENT_LOG_FILES,
    _persist_peer_info_cache,
    _load_peer_info_history_map,
    _load_peer_info_cache_map,
    _collect_persisted_traffic_data,
    _split_persisted_traffic_rows_by_config,
    _collect_config_protocols_by_client,
    _collect_sample_protocols_by_client,
    _normalize_traffic_protocol_type,
    _protocol_label_from_type,
    _openvpn_socket_path,
    _human_bytes,
    _human_device_type,
    _normalize_openvpn_endpoint,
):
    status_rows = _collect_status_rows_for_snapshot()

    _persist_traffic_snapshot(status_rows)

    event_rows = collect_event_rows(_parse_event_log=_parse_event_log, EVENT_LOG_FILES=EVENT_LOG_FILES)

    peer_ctx = build_peer_info_context(
        app=app,
        db=db,
        event_rows=event_rows,
        _persist_peer_info_cache=_persist_peer_info_cache,
        _load_peer_info_history_map=_load_peer_info_history_map,
        _load_peer_info_cache_map=_load_peer_info_cache_map,
    )

    total_active_clients = sum(item["client_count"] for item in status_rows)
    total_received = sum(item["total_received"] for item in status_rows)
    total_sent = sum(item["total_sent"] for item in status_rows)
    total_openvpn_sessions = sum(
        int(item.get("client_count") or 0)
        for item in status_rows
        if ((item.get("protocol") or "OpenVPN").strip() or "OpenVPN") == "OpenVPN"
    )
    total_wireguard_sessions = sum(
        int(item.get("client_count") or 0)
        for item in status_rows
        if ((item.get("protocol") or "OpenVPN").strip() or "OpenVPN") == "WireGuard"
    )

    unique_client_names = set()
    unique_ips = set()
    client_aggregate = defaultdict(
        lambda: {
            "bytes_received": 0,
            "bytes_sent": 0,
            "sessions": 0,
            "profiles": set(),
            "protocols": set(),
            "ips": set(),
            "versions": set(),
            "platforms": set(),
            "ip_details": {},
            "ip_profiles": {},
            "session_connections": [],
        }
    )

    for item in status_rows:
        for client in item["clients"]:
            name = client["common_name"]
            unique_client_names.add(name)
            if client.get("real_ip"):
                unique_ips.add(client["real_ip"])

            client_aggregate[name]["bytes_received"] += client["bytes_received"]
            client_aggregate[name]["bytes_sent"] += client["bytes_sent"]
            client_aggregate[name]["sessions"] += 1
            client_aggregate[name]["profiles"].add(item["label"])
            client_aggregate[name]["protocols"].add((item.get("protocol") or "OpenVPN").strip() or "OpenVPN")
            if client.get("real_ip"):
                client_aggregate[name]["ips"].add(client["real_ip"])
                client_aggregate[name]["ip_profiles"].setdefault(client["real_ip"], set()).add(item["profile"])
                normalized_real_address = _normalize_openvpn_endpoint(client.get("real_address") or "")
                client_aggregate[name]["session_connections"].append(
                    {
                        "ip": client["real_ip"],
                        "real_address": (normalized_real_address or client["real_ip"]),
                        "connected_since_ts": int(client.get("connected_since_ts") or 0),
                        "profile_key": (item.get("profile") or "").strip(),
                        "profile_label": (item.get("label") or "-").strip() or "-",
                        "protocol": (item.get("protocol") or "OpenVPN").strip() or "OpenVPN",
                    }
                )
                if client["real_ip"] not in client_aggregate[name]["ip_details"]:
                    client_aggregate[name]["ip_details"][client["real_ip"]] = {
                        "version": None,
                        "platform": None,
                        "rank": -1,
                    }

    enrich_client_aggregate_from_events(client_aggregate, event_rows, peer_ctx)

    connected_clients = []
    for name, stats in client_aggregate.items():
        total_bytes = stats["bytes_received"] + stats["bytes_sent"]
        ip_device_map = []
        client_versions_set = set()
        client_platforms_set = set()
        session_connections = sorted(
            stats.get("session_connections", []),
            key=lambda item: (
                int(item.get("connected_since_ts") or 0),
                (item.get("profile_label") or ""),
                (item.get("real_address") or item.get("ip") or ""),
            ),
        )

        session_key_counts = Counter()
        session_key_latest = {}
        for conn in session_connections:
            ip = (conn.get("ip") or "").strip()
            profile_key = (conn.get("profile_key") or "").strip()
            if not ip or not profile_key:
                continue

            key = (profile_key, ip)
            session_key_counts[key] += 1

            current_ts = int(conn.get("connected_since_ts") or 0)
            current_addr = (conn.get("real_address") or "").strip() or ip
            prev = session_key_latest.get(key)
            prev_ts = int(prev.get("connected_since_ts") or 0) if prev else -1
            prev_addr = (prev.get("real_address") or "").strip() if prev else ""
            if prev is None or current_ts > prev_ts or (current_ts == prev_ts and current_addr > prev_addr):
                session_key_latest[key] = {
                    "connected_since_ts": current_ts,
                    "real_address": current_addr,
                }

        if session_connections:
            for conn in session_connections:
                ip = (conn.get("ip") or "").strip()
                if not ip:
                    continue
                details = stats["ip_details"].get(ip, {"version": None, "platform": None})
                real_address = (conn.get("real_address") or "").strip() or ip
                profile_key = (conn.get("profile_key") or "").strip()
                profile_label = (conn.get("profile_label") or "-").strip() or "-"
                protocol_label = (conn.get("protocol") or "OpenVPN").strip() or "OpenVPN"
                is_openvpn_protocol = protocol_label == "OpenVPN"
                if is_openvpn_protocol:
                    platform_str = _human_device_type(details.get("platform")) if details.get("platform") else "Не определено"
                    version_str = details.get("version") or "Не определено"
                else:
                    platform_str = None
                    version_str = None
                is_stale_candidate = False

                if profile_key:
                    key = (profile_key, ip)
                    if int(session_key_counts.get(key, 0)) > 1:
                        latest = session_key_latest.get(key) or {}
                        latest_ts = int(latest.get("connected_since_ts") or 0)
                        latest_addr = (latest.get("real_address") or "").strip() or ip
                        current_ts = int(conn.get("connected_since_ts") or 0)
                        if real_address != latest_addr or current_ts < latest_ts:
                            is_stale_candidate = True

                if is_openvpn_protocol and version_str != "Не определено":
                    client_versions_set.add(version_str)
                if is_openvpn_protocol and platform_str != "Не определено":
                    client_platforms_set.add(platform_str)

                ip_device_map.append(
                    {
                        "ip": ip,
                        "real_address": real_address,
                        "show_real_address": real_address != ip,
                        "profile_label": profile_label,
                        "protocol": protocol_label,
                        "platform": platform_str,
                        "version": version_str,
                        "show_client_meta": is_openvpn_protocol,
                        "stale_candidate": is_stale_candidate,
                    }
                )
        else:
            has_openvpn_protocol = "OpenVPN" in (stats.get("protocols") or set())
            for ip in sorted(stats["ips"]):
                details = stats["ip_details"].get(ip, {"version": None, "platform": None})
                if has_openvpn_protocol:
                    platform_str = _human_device_type(details.get("platform")) if details.get("platform") else "Не определено"
                    version_str = details.get("version") or "Не определено"
                else:
                    platform_str = None
                    version_str = None

                if has_openvpn_protocol and version_str != "Не определено":
                    client_versions_set.add(version_str)
                if has_openvpn_protocol and platform_str != "Не определено":
                    client_platforms_set.add(platform_str)

                ip_device_map.append({
                    "ip": ip,
                    "real_address": ip,
                    "show_real_address": False,
                    "profile_label": "-",
                    "protocol": ", ".join(sorted(stats.get("protocols") or [])) if stats.get("protocols") else "-",
                    "platform": platform_str,
                    "version": version_str,
                    "show_client_meta": has_openvpn_protocol,
                    "stale_candidate": False,
                })

        protocols_sorted = sorted(stats.get("protocols") or [])
        is_wireguard_only = bool(protocols_sorted) and all(proto == "WireGuard" for proto in protocols_sorted)

        connected_clients.append(
            {
                "common_name": name,
                "bytes_received": stats["bytes_received"],
                "bytes_sent": stats["bytes_sent"],
                "total_bytes": total_bytes,
                "bytes_received_human": _human_bytes(stats["bytes_received"]),
                "bytes_sent_human": _human_bytes(stats["bytes_sent"]),
                "total_bytes_human": _human_bytes(total_bytes),
                "sessions": stats["sessions"],
                "profiles": ", ".join(sorted(stats["profiles"])),
                "protocols": ", ".join(sorted(stats["protocols"])) if stats.get("protocols") else "-",
                "ips": ", ".join(sorted(stats["ips"])) if stats["ips"] else "-",
                "client_versions": ", ".join(sorted(client_versions_set)) if client_versions_set else "-",
                "device_types": (
                    ", ".join(sorted(client_platforms_set))
                    if client_platforms_set
                    else ("WireGuard (без данных устройства)" if is_wireguard_only else "Не определено")
                ),
                "ip_device_map": ip_device_map,
            }
        )

    connected_clients.sort(key=lambda item: item["common_name"].lower())

    active_protocol_identities = set()
    for client_name, stats in client_aggregate.items():
        protocols = set(stats.get("protocols") or set())
        if "OpenVPN" in protocols:
            active_protocol_identities.add((client_name, "openvpn"))
        if "WireGuard" in protocols:
            active_protocol_identities.add((client_name, "wireguard"))

    persisted_traffic_rows, persisted_traffic_summary = _collect_persisted_traffic_data(
        active_names=unique_client_names,
        active_protocol_identities=active_protocol_identities,
    )
    persisted_traffic_rows, deleted_persisted_traffic_rows, deleted_persisted_traffic_summary = _split_persisted_traffic_rows_by_config(
        persisted_traffic_rows
    )

    config_protocols_map = _collect_config_protocols_by_client()
    sample_protocols_map = _collect_sample_protocols_by_client()

    for row in persisted_traffic_rows:
        row_protocol_type = _normalize_traffic_protocol_type(row.get("protocol_type"), fallback="openvpn")
        row_protocols = [_protocol_label_from_type(row_protocol_type)]
        if not row_protocols:
            common_name = (row.get("common_name") or "").strip().lower()
            row_protocols = sorted(
                sample_protocols_map.get(common_name, set())
                or config_protocols_map.get(common_name, set())
            )
        row["protocols"] = ", ".join(row_protocols) if row_protocols else "-"

    for row in deleted_persisted_traffic_rows:
        row_protocol_type = _normalize_traffic_protocol_type(row.get("protocol_type"), fallback="openvpn")
        row_protocols = [_protocol_label_from_type(row_protocol_type)]
        if not row_protocols:
            common_name = (row.get("common_name") or "").strip().lower()
            row_protocols = sorted(
                sample_protocols_map.get(common_name, set())
                or config_protocols_map.get(common_name, set())
            )
        row["protocols"] = ", ".join(row_protocols) if row_protocols else "-"

    total_event_lines = sum(item["line_count"] for item in event_rows)
    total_event_counts = Counter()
    for item in event_rows:
        total_event_counts.update(item.get("event_counts", {}))

    status_exists_map = {item.get("profile"): bool(item.get("exists")) for item in status_rows}
    event_exists_map = {item.get("profile"): bool(item.get("exists")) for item in event_rows}

    status_data_available = any(bool(item.get("exists")) for item in status_rows)
    event_data_available = any(bool(item.get("exists")) for item in event_rows)
    openvpn_logging_enabled = status_data_available or event_data_available

    missing_event_log_files = []
    if not openvpn_logging_enabled:
        for profile_key in EVENT_LOG_FILES.keys():
            socket_path = _openvpn_socket_path(profile_key)
            socket_name = os.path.basename(socket_path)
            socket_exists = os.path.exists(socket_path)
            profile_has_data = status_exists_map.get(profile_key, False) or event_exists_map.get(profile_key, False)

            if profile_has_data:
                continue

            if not socket_exists:
                missing_event_log_files.append(f"{socket_name} (не найден)")
            else:
                missing_event_log_files.append(f"{socket_name} (нет ответа на status/log)")

    grouped_status_map = {
        "Antizapret": {
            "network": "Antizapret",
            "files": [],
            "snapshot_times": [],
            "updated_values": [],
            "client_count": 0,
            "total_received": 0,
            "total_sent": 0,
            "real_ips": set(),
            "transport_clients": {"TCP": 0, "UDP": 0},
            "protocol_clients": Counter(),
        },
        "VPN": {
            "network": "VPN",
            "files": [],
            "snapshot_times": [],
            "updated_values": [],
            "client_count": 0,
            "total_received": 0,
            "total_sent": 0,
            "real_ips": set(),
            "transport_clients": {"TCP": 0, "UDP": 0},
            "protocol_clients": Counter(),
        },
    }

    for row in status_rows:
        network = "Antizapret" if row["profile"].startswith("antizapret") else "VPN"
        transport = "TCP" if row["profile"].endswith("-tcp") else "UDP"
        group = grouped_status_map[network]

        if row.get("filename"):
            group["files"].append(row["filename"])
        if row.get("snapshot_time") and row["snapshot_time"] != "-":
            group["snapshot_times"].append(row["snapshot_time"])
        if row.get("updated_at") and row["updated_at"] != "-":
            group["updated_values"].append(row["updated_at"])

        group["client_count"] += row.get("client_count", 0)
        group["total_received"] += row.get("total_received", 0)
        group["total_sent"] += row.get("total_sent", 0)
        group["transport_clients"][transport] += row.get("client_count", 0)
        protocol = ((row.get("protocol") or "OpenVPN").strip() or "OpenVPN")
        group["protocol_clients"][protocol] += row.get("client_count", 0)

        for client in row.get("clients", []):
            if client.get("real_ip"):
                group["real_ips"].add(client["real_ip"])

    grouped_status_rows = []
    for network in ("Antizapret", "VPN"):
        group = grouped_status_map[network]
        total_traffic = group["total_received"] + group["total_sent"]
        protocol_split = (
            f"OpenVPN: {int(group['protocol_clients'].get('OpenVPN', 0))}, "
            f"WireGuard: {int(group['protocol_clients'].get('WireGuard', 0))}"
        )
        grouped_status_rows.append(
            {
                "network": network,
                "files": ", ".join(sorted(set(group["files"]))),
                "snapshot_times": ", ".join(sorted(set(group["snapshot_times"]))),
                "updated_at": max(group["updated_values"]) if group["updated_values"] else "-",
                "client_count": group["client_count"],
                "unique_real_ips": len(group["real_ips"]),
                "protocol_split": protocol_split,
                "transport_split": f"TCP: {group['transport_clients']['TCP']}, UDP: {group['transport_clients']['UDP']}",
                "total_received": group["total_received"],
                "total_sent": group["total_sent"],
                "total_traffic": total_traffic,
                "total_received_human": _human_bytes(group["total_received"]),
                "total_sent_human": _human_bytes(group["total_sent"]),
                "total_traffic_human": _human_bytes(total_traffic),
            }
        )

    grouped_event_map = {
        "Antizapret": {
            "network": "Antizapret",
            "files": [],
            "updated_values": [],
            "line_count": 0,
            "event_counts": Counter(),
            "peer_connected": Counter(),
            "recent_lines": [],
        },
        "VPN": {
            "network": "VPN",
            "files": [],
            "updated_values": [],
            "line_count": 0,
            "event_counts": Counter(),
            "peer_connected": Counter(),
            "recent_lines": [],
        },
    }

    for row in event_rows:
        network = "Antizapret" if row["profile"].startswith("antizapret") else "VPN"
        transport = "TCP" if row["profile"].endswith("-tcp") else "UDP"
        group = grouped_event_map[network]

        if row.get("filename"):
            group["files"].append(row["filename"])
        if row.get("updated_at") and row["updated_at"] != "-":
            group["updated_values"].append(row["updated_at"])

        group["line_count"] += row.get("line_count", 0)
        group["event_counts"].update(row.get("event_counts", {}))
        group["peer_connected"].update(dict(row.get("peer_connected_clients", [])))

        for line in row.get("recent_lines", []):
            group["recent_lines"].append(f"[{transport}] {line}")

    grouped_event_rows = []
    for network in ("Antizapret", "VPN"):
        group = grouped_event_map[network]
        grouped_event_rows.append(
            {
                "network": network,
                "files": ", ".join(sorted(set(group["files"]))),
                "updated_at": max(group["updated_values"]) if group["updated_values"] else "-",
                "line_count": group["line_count"],
                "event_counts": dict(group["event_counts"]),
                "peer_connected_clients": group["peer_connected"].most_common(10),
                "recent_lines": group["recent_lines"][-10:],
            }
        )

    return {
        "status_rows": status_rows,
        "event_rows": event_rows,
        "grouped_status_rows": grouped_status_rows,
        "grouped_event_rows": grouped_event_rows,
        "openvpn_logging_enabled": openvpn_logging_enabled,
        "missing_event_log_files": missing_event_log_files,
        "summary": {
            "total_active_clients": total_active_clients,
            "unique_client_names": len(unique_client_names),
            "unique_ips": len(unique_ips),
            "total_received": total_received,
            "total_sent": total_sent,
            "total_received_human": _human_bytes(total_received),
            "total_sent_human": _human_bytes(total_sent),
            "total_traffic_human": _human_bytes(total_received + total_sent),
            "total_openvpn_sessions": total_openvpn_sessions,
            "total_wireguard_sessions": total_wireguard_sessions,
            "total_event_lines": total_event_lines,
            "total_event_counts": dict(total_event_counts),
        },
        "connected_clients": connected_clients,
        "persisted_traffic_rows": persisted_traffic_rows,
        "deleted_persisted_traffic_rows": deleted_persisted_traffic_rows,
        "persisted_traffic_summary": persisted_traffic_summary,
        "deleted_persisted_traffic_summary": deleted_persisted_traffic_summary,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


