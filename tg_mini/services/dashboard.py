from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any


def build_tg_mini_dashboard_payload(
    *,
    dashboard_data: dict[str, Any],
    user_traffic_sample_model,
    human_bytes,
) -> dict[str, Any]:
    connected_clients = dashboard_data.get("connected_clients") or []
    grouped_status_rows = dashboard_data.get("grouped_status_rows") or []
    persisted_rows = dashboard_data.get("persisted_traffic_rows") or []
    summary = dashboard_data.get("summary") or {}

    top_connected = sorted(
        connected_clients,
        key=lambda item: (
            int(item.get("sessions") or 0),
            int(item.get("total_bytes") or 0),
        ),
        reverse=True,
    )

    one_hour_since = datetime.utcnow() - timedelta(hours=1)
    one_hour_rows = user_traffic_sample_model.query.filter(
        user_traffic_sample_model.created_at >= one_hour_since
    ).all()
    one_hour_by_client = defaultdict(int)
    for sample in one_hour_rows:
        common_name = (sample.common_name or "").strip()
        if not common_name:
            continue
        one_hour_by_client[common_name] += int(sample.delta_received or 0) + int(sample.delta_sent or 0)

    traffic_by_client: dict[str, dict[str, Any]] = {}
    for row in persisted_rows:
        common_name = (row.get("common_name") or "").strip()
        if not common_name:
            continue

        item = traffic_by_client.setdefault(
            common_name,
            {
                "common_name": common_name,
                "traffic_1h": 0,
                "traffic_1d": 0,
                "traffic_7d": 0,
                "traffic_30d": 0,
                "total_bytes": 0,
                "is_active": False,
                "last_seen_at": "-",
            },
        )

        item["traffic_1d"] += int(row.get("traffic_1d") or 0)
        item["traffic_7d"] += int(row.get("traffic_7d") or 0)
        item["traffic_30d"] += int(row.get("traffic_30d") or 0)
        item["total_bytes"] += int(row.get("total_bytes") or 0)
        item["is_active"] = bool(item["is_active"] or row.get("is_active"))

        row_last_seen = (row.get("last_seen_at") or "-").strip() or "-"
        if row_last_seen != "-" and (
            item["last_seen_at"] in (None, "-")
            or str(row_last_seen) > str(item["last_seen_at"])
        ):
            item["last_seen_at"] = row_last_seen

    for client_name, bytes_total in one_hour_by_client.items():
        if client_name not in traffic_by_client:
            continue
        traffic_by_client[client_name]["traffic_1h"] = int(bytes_total or 0)

    top_traffic = sorted(
        traffic_by_client.values(),
        key=lambda item: int(item.get("total_bytes") or 0),
        reverse=True,
    )

    for item in top_traffic:
        item["traffic_1h_human"] = human_bytes(int(item.get("traffic_1h") or 0))
        item["traffic_1d_human"] = human_bytes(int(item.get("traffic_1d") or 0))
        item["traffic_7d_human"] = human_bytes(int(item.get("traffic_7d") or 0))
        item["traffic_30d_human"] = human_bytes(int(item.get("traffic_30d") or 0))
        item["total_bytes_human"] = human_bytes(int(item.get("total_bytes") or 0))

    top_networks = sorted(
        grouped_status_rows,
        key=lambda item: int(item.get("client_count") or 0),
        reverse=True,
    )[:10]

    return {
        "success": True,
        "generated_at": dashboard_data.get("generated_at"),
        "cache_meta": dashboard_data.get("cache_meta", {}),
        "summary": {
            "total_active_clients": int(summary.get("total_active_clients") or 0),
            "unique_client_names": int(summary.get("unique_client_names") or 0),
            "unique_ips": int(summary.get("unique_ips") or 0),
            "total_openvpn_sessions": int(summary.get("total_openvpn_sessions") or 0),
            "total_wireguard_sessions": int(summary.get("total_wireguard_sessions") or 0),
            "total_traffic_human": summary.get("total_traffic_human") or "0 B",
        },
        "top_connected": [
            {
                "common_name": item.get("common_name") or "-",
                "sessions": int(item.get("sessions") or 0),
                "profiles": item.get("profiles") or "-",
                "protocols": item.get("protocols") or "-",
                "bytes_received_human": item.get("bytes_received_human") or "0 B",
                "bytes_sent_human": item.get("bytes_sent_human") or "0 B",
                "total_bytes_human": item.get("total_bytes_human") or "0 B",
            }
            for item in top_connected
        ],
        "top_networks": [
            {
                "network": item.get("network") or "-",
                "client_count": int(item.get("client_count") or 0),
                "unique_real_ips": int(item.get("unique_real_ips") or 0),
                "total_traffic_human": item.get("total_traffic_human") or "0 B",
            }
            for item in top_networks
        ],
        "top_traffic": top_traffic,
        "traffic_clients": sorted(traffic_by_client.keys(), key=str.lower),
        "top_connected_count": len(top_connected),
        "top_traffic_count": len(top_traffic),
    }
