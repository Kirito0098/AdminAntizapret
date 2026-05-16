import json
import os
import re
import subprocess


def collect_interface_groups():
    default_groups = {
        "vpn": ["vpn", "vpn-udp", "vpn-tcp"],
        "antizapret": ["antizapret", "antizapret-udp", "antizapret-tcp"],
    }
    default_protocol_groups = {
        "openvpn": ["vpn-udp", "vpn-tcp", "antizapret-udp", "antizapret-tcp"],
        "wireguard": ["vpn", "antizapret"],
    }

    candidates = set()
    for values in default_groups.values():
        candidates.update(values)

    vnstat_bin = os.environ.get("VNSTAT_BIN", "/usr/bin/vnstat")
    try:
        vn_json = subprocess.run(
            [vnstat_bin, "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=4,
        )
        parsed = json.loads(vn_json.stdout or "{}")
        for item in parsed.get("interfaces") or []:
            name = str(item.get("name") or "").strip()
            if name:
                candidates.add(name)
    except Exception:
        pass

    wg_interfaces = set()
    try:
        wg_out = subprocess.run(
            ["wg", "show", "interfaces"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        for token in re.split(r"\s+", (wg_out.stdout or "").strip()):
            name = token.strip()
            if name:
                wg_interfaces.add(name)
                candidates.add(name)
    except Exception:
        pass

    try:
        ip_out = subprocess.run(
            ["ip", "-o", "link", "show", "type", "wireguard"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in (ip_out.stdout or "").splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                name = parts[1].strip()
                if name:
                    wg_interfaces.add(name)
                    candidates.add(name)
    except Exception:
        pass

    vpn_group = []
    antizapret_group = []
    openvpn_group = []
    wireguard_group = []

    def _add_unique(target, value):
        if value and value not in target:
            target.append(value)

    for iface in sorted(candidates):
        lowered = iface.lower()
        if not any(k in lowered for k in ("vpn", "wg", "wireguard", "awg", "amnezia", "antizapret")):
            continue

        is_wireguard_iface = iface in wg_interfaces or any(
            k in lowered for k in ("wg", "wireguard", "awg", "amnezia")
        )

        if "antizapret" in lowered:
            _add_unique(antizapret_group, iface)
        else:
            _add_unique(vpn_group, iface)

        if is_wireguard_iface:
            _add_unique(wireguard_group, iface)
        else:
            _add_unique(openvpn_group, iface)

    for fallback_iface in default_groups["vpn"]:
        _add_unique(vpn_group, fallback_iface)
    for fallback_iface in default_groups["antizapret"]:
        _add_unique(antizapret_group, fallback_iface)

    for fallback_iface in default_protocol_groups["openvpn"]:
        _add_unique(openvpn_group, fallback_iface)

    for fallback_iface in default_protocol_groups["wireguard"]:
        _add_unique(wireguard_group, fallback_iface)

    return {
        "vpn": vpn_group,
        "antizapret": antizapret_group,
        "openvpn": openvpn_group,
        "wireguard": wireguard_group,
    }


def resolve_bw_iface(request_iface, *, env_iface=None, config_iface=None, default="ens3"):
    iface = env_iface or config_iface or default
    if request_iface:
        iface = request_iface
    return (iface or "").strip()


def fetch_bandwidth_chart(iface, range_key="1d"):
    iface = (iface or "").strip()
    if not iface:
        return {"error": "Не задан сетевой интерфейс", "iface": iface}, 400

    rng = range_key if range_key in ("1d", "7d", "30d") else "1d"

    vnstat_bin = os.environ.get("VNSTAT_BIN", "/usr/bin/vnstat")

    def _run(args):
        return subprocess.run(args, check=True, capture_output=True, text=True)

    try:
        data_f = json.loads(_run([vnstat_bin, "--json", "f", "-i", iface]).stdout)
    except Exception:
        data_f = {}

    try:
        data_d = json.loads(_run([vnstat_bin, "--json", "d", "-i", iface]).stdout)
    except Exception as e:
        return {"error": str(e), "iface": iface}, 500

    def get_iface_block(data):
        for it in data.get("interfaces") or []:
            if it.get("name") == iface:
                return it
        return {}

    it_f = get_iface_block(data_f)
    it_d = get_iface_block(data_d)

    traffic_f = it_f.get("traffic") or {}
    traffic_d = it_d.get("traffic") or {}

    fivemin = (
        traffic_f.get("fiveminute")
        or traffic_f.get("fiveMinute")
        or traffic_f.get("five_minutes")
        or []
    )

    days = traffic_d.get("day") or traffic_d.get("days") or []

    def sort_key_dt(h):
        d = h.get("date") or {}
        t = h.get("time") or {}
        return (
            d.get("year", 0),
            d.get("month", 0),
            d.get("day", 0),
            (t.get("hour", 0) if t else 0),
            (t.get("minute", 0) if t else 0),
        )

    def to_mbps_from_5min_bytes(b):
        return round((int(b) * 8) / (300 * 1_000_000), 3)

    def to_mbps_avg_per_day(bytes_val):
        return round((int(bytes_val) * 8) / (86_400 * 1_000_000), 3)

    labels, rx_mbps, tx_mbps = [], [], []

    if rng == "1d":
        if fivemin:
            last288 = sorted(fivemin, key=sort_key_dt)[-288:]
            for m in last288:
                t = m.get("time") or {}
                labels.append(
                    f"{int(t.get('hour', 0)):02d}:{int(t.get('minute', 0)):02d}"
                )
                rx_mbps.append(to_mbps_from_5min_bytes(m.get("rx", 0)))
                tx_mbps.append(to_mbps_from_5min_bytes(m.get("tx", 0)))
        else:
            labels = [""] * 288
            rx_mbps = [0.0] * 288
            tx_mbps = [0.0] * 288
    else:
        need_days = 7 if rng == "7d" else 30
        use_days = sorted(days, key=sort_key_dt)[-need_days:]
        for d in use_days:
            date = d.get("date") or {}
            labels.append(
                f"{int(date.get('day', 0)):02d}.{int(date.get('month', 0)):02d}"
            )
            rx_mbps.append(to_mbps_avg_per_day(d.get("rx", 0)))
            tx_mbps.append(to_mbps_avg_per_day(d.get("tx", 0)))

        if len(labels) < need_days:
            pad = need_days - len(labels)
            labels = [""] * pad + labels
            rx_mbps = [0.0] * pad + rx_mbps
            tx_mbps = [0.0] * pad + tx_mbps

    days_sorted = sorted(days, key=sort_key_dt)

    def sum_days(n):
        chunk = days_sorted[-n:] if days_sorted else []
        rx_sum = sum(int(x.get("rx", 0)) for x in chunk)
        tx_sum = sum(int(x.get("tx", 0)) for x in chunk)
        return {"rx_bytes": rx_sum, "tx_bytes": tx_sum, "total_bytes": rx_sum + tx_sum}

    totals = {
        "1d": sum_days(1),
        "7d": sum_days(7),
        "30d": sum_days(30),
    }

    return {
        "iface": iface,
        "range": rng,
        "labels": labels,
        "rx_mbps": rx_mbps,
        "tx_mbps": tx_mbps,
        "totals": totals,
    }, 200
