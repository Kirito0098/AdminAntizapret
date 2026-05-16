def build_client_details_payload(
    visible_client_names,
    *,
    get_logs_dashboard_data_cached,
    session_username,
    human_bytes,
    logger=None,
):
    client_details_payload = {"connected": {}, "traffic": {}}

    try:
        dashboard_data = get_logs_dashboard_data_cached(created_by_username=session_username)
        connected_clients = dashboard_data.get("connected_clients", []) or []
        persisted_traffic_rows = dashboard_data.get("persisted_traffic_rows", []) or []

        if visible_client_names:
            connected_clients = [
                item
                for item in connected_clients
                if (item.get("common_name") or "") in visible_client_names
            ]
            persisted_traffic_rows = [
                row
                for row in persisted_traffic_rows
                if (row.get("common_name") or "") in visible_client_names
            ]

        for item in connected_clients:
            name = (item.get("common_name") or "").strip()
            if not name:
                continue
            client_details_payload["connected"][name] = {
                "common_name": name,
                "sessions": int(item.get("sessions") or 0),
                "profiles": item.get("profiles") or "-",
                "bytes_received_human": item.get("bytes_received_human") or "0 B",
                "bytes_sent_human": item.get("bytes_sent_human") or "0 B",
                "total_bytes_human": item.get("total_bytes_human") or "0 B",
                "ip_device_map": item.get("ip_device_map") or [],
            }

        for row in persisted_traffic_rows:
            name = (row.get("common_name") or "").strip()
            if not name:
                continue

            entry = client_details_payload["traffic"].setdefault(
                name,
                {
                    "traffic_1d": 0,
                    "traffic_7d": 0,
                    "traffic_30d": 0,
                    "total_bytes_vpn": 0,
                    "total_bytes_antizapret": 0,
                    "total_bytes": 0,
                    "last_seen_at": "-",
                    "is_active": False,
                },
            )

            entry["traffic_1d"] += int(row.get("traffic_1d") or 0)
            entry["traffic_7d"] += int(row.get("traffic_7d") or 0)
            entry["traffic_30d"] += int(row.get("traffic_30d") or 0)
            entry["total_bytes_vpn"] += int(row.get("total_bytes_vpn") or 0)
            entry["total_bytes_antizapret"] += int(row.get("total_bytes_antizapret") or 0)
            entry["total_bytes"] += int(row.get("total_bytes") or 0)

            row_last_seen = (row.get("last_seen_at") or "-").strip() or "-"
            if row_last_seen != "-" and (
                entry.get("last_seen_at") in (None, "-")
                or row_last_seen > str(entry.get("last_seen_at") or "-")
            ):
                entry["last_seen_at"] = row_last_seen

            if bool(row.get("is_active")):
                entry["is_active"] = True

        for entry in client_details_payload["traffic"].values():
            entry["traffic_1d_human"] = human_bytes(int(entry.get("traffic_1d") or 0))
            entry["traffic_7d_human"] = human_bytes(int(entry.get("traffic_7d") or 0))
            entry["traffic_30d_human"] = human_bytes(int(entry.get("traffic_30d") or 0))
            entry["total_bytes_vpn_human"] = human_bytes(int(entry.get("total_bytes_vpn") or 0))
            entry["total_bytes_antizapret_human"] = human_bytes(int(entry.get("total_bytes_antizapret") or 0))
            entry["total_bytes_human"] = human_bytes(int(entry.get("total_bytes") or 0))
    except Exception as exc:
        if logger is not None:
            logger.warning("Не удалось подготовить client_details_payload для index: %s", exc)

    return client_details_payload
