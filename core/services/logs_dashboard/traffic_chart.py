from collections import defaultdict
from datetime import datetime, timedelta, timezone


def fetch_user_traffic_chart(
    *,
    client,
    range_key,
    protocol_filter,
    collect_config_protocols_by_client,
    user_traffic_sample_model,
    human_bytes,
):
    client = (client or "").strip()
    range_key = (range_key or "7d").strip().lower()
    protocol_filter = (protocol_filter or "all").strip().lower()

    if not client:
        return {"error": "Параметр client обязателен"}, 400

    if range_key == "24h":
        range_key = "1d"

    if range_key not in ("1h", "1d", "7d", "30d", "all"):
        range_key = "7d"
    if protocol_filter not in ("all", "openvpn", "wireguard"):
        protocol_filter = "all"

    client_protocols_map = collect_config_protocols_by_client()
    client_protocols = set(client_protocols_map.get(client.lower(), set()))
    is_wireguard_only_client = (
        bool(client_protocols) and "WireGuard" in client_protocols and "OpenVPN" not in client_protocols
    )

    now = datetime.utcnow()
    since_dt = None
    bucket = "day"

    if range_key == "1h":
        since_dt = now - timedelta(hours=1)
        bucket = "minute5"
    elif range_key == "1d":
        since_dt = now - timedelta(hours=24)
        bucket = "hour"
    elif range_key == "7d":
        since_dt = now - timedelta(days=7)
        bucket = "day"
    elif range_key == "30d":
        since_dt = now - timedelta(days=30)
        bucket = "day"
    else:
        bucket = "month"

    query = user_traffic_sample_model.query.filter_by(common_name=client)
    if since_dt is not None:
        query = query.filter(user_traffic_sample_model.created_at >= since_dt)

    samples = query.order_by(user_traffic_sample_model.created_at.asc()).all()

    grouped = defaultdict(lambda: {"vpn": 0, "antizapret": 0, "openvpn": 0, "wireguard": 0})

    def format_bucket_dt_utc(dt_value, bucket_name):
        if not dt_value:
            return None

        if bucket_name == "minute5":
            aligned = dt_value.replace(minute=(dt_value.minute // 5) * 5, second=0, microsecond=0)
        elif bucket_name == "hour":
            aligned = dt_value.replace(minute=0, second=0, microsecond=0)
        elif bucket_name == "day":
            aligned = dt_value.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            aligned = dt_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if aligned.tzinfo is None:
            aligned = aligned.replace(tzinfo=timezone.utc)
        else:
            aligned = aligned.astimezone(timezone.utc)

        return aligned.isoformat().replace("+00:00", "Z")

    for item in samples:
        dt = item.created_at
        if not dt:
            continue

        label_dt_utc = format_bucket_dt_utc(dt, bucket)

        if bucket == "minute5":
            minute = (dt.minute // 5) * 5
            bucket_key = dt.strftime("%Y-%m-%d %H") + f":{minute:02d}"
            label = dt.strftime("%H") + f":{minute:02d}"
        elif bucket == "hour":
            bucket_key = dt.strftime("%Y-%m-%d %H")
            label = dt.strftime("%d.%m %H:00")
        elif bucket == "day":
            bucket_key = dt.strftime("%Y-%m-%d")
            label = dt.strftime("%d.%m")
        else:
            bucket_key = dt.strftime("%Y-%m")
            label = dt.strftime("%Y-%m")

        total_delta = int(item.delta_received or 0) + int(item.delta_sent or 0)
        net = "antizapret" if item.network_type == "antizapret" else "vpn"
        protocol = (item.protocol_type or "openvpn").strip().lower()
        if protocol not in ("openvpn", "wireguard"):
            protocol = "openvpn"
        if is_wireguard_only_client and protocol == "openvpn":
            protocol = "wireguard"

        if protocol_filter != "all" and protocol != protocol_filter:
            continue

        grouped[bucket_key]["label"] = label
        if label_dt_utc and "label_dt_utc" not in grouped[bucket_key]:
            grouped[bucket_key]["label_dt_utc"] = label_dt_utc
        grouped[bucket_key][net] += total_delta
        grouped[bucket_key][protocol] += total_delta

    ordered_keys = sorted(grouped.keys())
    labels = [grouped[key].get("label", key) for key in ordered_keys]
    label_datetimes_utc = [grouped[key].get("label_dt_utc") for key in ordered_keys]
    vpn_bytes = [int(grouped[key].get("vpn", 0)) for key in ordered_keys]
    antizapret_bytes = [int(grouped[key].get("antizapret", 0)) for key in ordered_keys]
    openvpn_bytes = [int(grouped[key].get("openvpn", 0)) for key in ordered_keys]
    wireguard_bytes = [int(grouped[key].get("wireguard", 0)) for key in ordered_keys]

    total_vpn = sum(vpn_bytes)
    total_antizapret = sum(antizapret_bytes)
    total_openvpn = sum(openvpn_bytes)
    total_wireguard = sum(wireguard_bytes)

    def window_totals(since_window):
        win_query = user_traffic_sample_model.query.filter_by(common_name=client)
        if since_window is not None:
            win_query = win_query.filter(user_traffic_sample_model.created_at >= since_window)

        totals = {"vpn": 0, "antizapret": 0, "openvpn": 0, "wireguard": 0}
        for row in win_query.all():
            delta_total = int(row.delta_received or 0) + int(row.delta_sent or 0)
            network_name = "antizapret" if row.network_type == "antizapret" else "vpn"
            protocol_name = (row.protocol_type or "openvpn").strip().lower()
            if protocol_name not in ("openvpn", "wireguard"):
                protocol_name = "openvpn"
            if is_wireguard_only_client and protocol_name == "openvpn":
                protocol_name = "wireguard"

            if protocol_filter != "all" and protocol_name != protocol_filter:
                continue

            totals[network_name] += delta_total
            totals[protocol_name] += delta_total

        totals["total"] = totals["vpn"] + totals["antizapret"]
        return totals

    totals_1h = window_totals(now - timedelta(hours=1))
    totals_1d = window_totals(now - timedelta(hours=24))

    return {
        "client": client,
        "range": range_key,
        "bucket": bucket,
        "protocol_filter": protocol_filter,
        "labels": labels,
        "label_datetimes_utc": label_datetimes_utc,
        "vpn_bytes": vpn_bytes,
        "antizapret_bytes": antizapret_bytes,
        "openvpn_bytes": openvpn_bytes,
        "wireguard_bytes": wireguard_bytes,
        "total_vpn": total_vpn,
        "total_antizapret": total_antizapret,
        "total_openvpn": total_openvpn,
        "total_wireguard": total_wireguard,
        "total": total_vpn + total_antizapret,
        "total_vpn_human": human_bytes(total_vpn),
        "total_antizapret_human": human_bytes(total_antizapret),
        "total_openvpn_human": human_bytes(total_openvpn),
        "total_wireguard_human": human_bytes(total_wireguard),
        "total_human": human_bytes(total_vpn + total_antizapret),
        "total_1h": int(totals_1h["total"]),
        "total_1d": int(totals_1d["total"]),
        "total_1h_human": human_bytes(int(totals_1h["total"])),
        "total_1d_human": human_bytes(int(totals_1d["total"])),
    }, 200
