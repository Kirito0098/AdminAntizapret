import re


def parse_wireguard_config_peer_rows(config_path, interface_name):
    rows = []
    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as handle:
            raw_lines = handle.readlines()
    except OSError:
        return rows

    pending_client_name = ""
    current_peer = None

    def _flush_peer(peer_state):
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
                "preshared_key": (peer_state.get("preshared_key") or "").strip() or None,
                "allowed_ips": (peer_state.get("allowed_ips") or "").strip() or None,
            }
        )

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue

        match_client = re.match(r"^#\s*Client\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if match_client:
            pending_client_name = (match_client.group(1) or "").strip()
            continue

        if re.match(r"^\[Peer\]$", line, flags=re.IGNORECASE):
            _flush_peer(current_peer)
            current_peer = {
                "client_name": pending_client_name,
                "peer_public_key": "",
                "preshared_key": "",
                "allowed_ips": "",
            }
            pending_client_name = ""
            continue

        if line.startswith("[") and line.endswith("]"):
            _flush_peer(current_peer)
            current_peer = None
            continue

        if current_peer is None:
            continue

        match_pub = re.match(r"^PublicKey\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if match_pub:
            current_peer["peer_public_key"] = (match_pub.group(1) or "").strip()
            continue

        match_psk = re.match(r"^PresharedKey\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if match_psk:
            current_peer["preshared_key"] = (match_psk.group(1) or "").strip()
            continue

        match_allowed = re.match(r"^AllowedIPs\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if match_allowed:
            current_peer["allowed_ips"] = (match_allowed.group(1) or "").strip()

    _flush_peer(current_peer)
    return rows


def collect_client_peer_specs(wireguard_config_files, client_name):
    normalized = (client_name or "").strip().lower()
    if not normalized:
        return []

    specs = []
    for interface_name, config_path in (wireguard_config_files or {}).items():
        path = (config_path or "").strip()
        if not path:
            continue
        for row in parse_wireguard_config_peer_rows(path, interface_name):
            if (row.get("client_name") or "").strip().lower() != normalized:
                continue
            specs.append(row)
    return specs
