from collections import Counter
from datetime import datetime
import os
import re
import subprocess
import time


class NetworkStatusCollectorService:
    def __init__(
        self,
        *,
        app,
        db,
        wireguard_peer_cache_model,
        wireguard_config_files,
        wireguard_active_handshake_seconds,
        wireguard_peer_cache_sync_min_interval_seconds,
        status_log_files,
        human_bytes,
        extract_ip_from_openvpn_address,
        profile_meta,
        read_status_source,
        read_event_source,
        normalize_openvpn_endpoint,
    ):
        self.app = app
        self.db = db
        self.wireguard_peer_cache_model = wireguard_peer_cache_model
        self.wireguard_config_files = wireguard_config_files
        self.wireguard_active_handshake_seconds = wireguard_active_handshake_seconds
        self.wireguard_peer_cache_sync_min_interval_seconds = wireguard_peer_cache_sync_min_interval_seconds
        self.status_log_files = status_log_files
        self.human_bytes = human_bytes
        self.extract_ip_from_openvpn_address = extract_ip_from_openvpn_address
        self.profile_meta = profile_meta
        self.read_status_source = read_status_source
        self.read_event_source = read_event_source
        self.normalize_openvpn_endpoint = normalize_openvpn_endpoint
        self._wireguard_peer_cache_last_sync_ts = 0

    def normalize_wireguard_allowed_ip(self, token):
        value = (token or "").strip()
        if not value or value.lower() == "(none)":
            return ""
        return value.split("/", 1)[0].strip()

    def split_wireguard_allowed_ips(self, value):
        out = []
        for token in (value or "").split(","):
            ip = self.normalize_wireguard_allowed_ip(token)
            if ip:
                out.append(ip)
        return out

    def extract_ip_from_wireguard_endpoint(self, endpoint):
        endpoint_value = (endpoint or "").strip()
        if not endpoint_value or endpoint_value == "(none)":
            return ""

        if endpoint_value.startswith("["):
            m_v6 = re.match(r"^\[([^\]]+)\](?::\d+)?$", endpoint_value)
            if m_v6:
                return m_v6.group(1)

        if ":" in endpoint_value:
            host_part, maybe_port = endpoint_value.rsplit(":", 1)
            if maybe_port.isdigit():
                return host_part

        return endpoint_value

    def parse_wireguard_config_peer_rows(self, config_path, interface_name):
        rows = []
        try:
            with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_lines = f.readlines()
        except FileNotFoundError:
            return []
        except Exception:
            return []

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
                _flush_peer(current_peer)
                current_peer = {
                    "client_name": pending_client_name,
                    "peer_public_key": "",
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

            m_pub = re.match(r"^PublicKey\s*=\s*(.+)$", line, flags=re.IGNORECASE)
            if m_pub:
                current_peer["peer_public_key"] = (m_pub.group(1) or "").strip()
                continue

            m_allowed = re.match(r"^AllowedIPs\s*=\s*(.+)$", line, flags=re.IGNORECASE)
            if m_allowed:
                current_peer["allowed_ips"] = (m_allowed.group(1) or "").strip()

        _flush_peer(current_peer)
        return rows

    def sync_wireguard_peer_cache_from_configs(self, force=False):
        now_ts = int(time.time())
        if (
            not force
            and self.wireguard_peer_cache_sync_min_interval_seconds > 0
            and (now_ts - int(self._wireguard_peer_cache_last_sync_ts or 0))
            < self.wireguard_peer_cache_sync_min_interval_seconds
        ):
            return 0

        parsed_rows = []
        for interface_name, config_path in self.wireguard_config_files.items():
            parsed_rows.extend(self.parse_wireguard_config_peer_rows(config_path, interface_name))

        by_key = {}
        for row in parsed_rows:
            key = ((row.get("interface_name") or "").strip(), (row.get("peer_public_key") or "").strip())
            if not key[0] or not key[1]:
                continue
            by_key[key] = row

        existing_rows = self.wireguard_peer_cache_model.query.all()
        existing_by_key = {
            ((row.interface_name or "").strip(), (row.peer_public_key or "").strip()): row
            for row in existing_rows
        }

        changed = False
        for key, parsed in by_key.items():
            existing = existing_by_key.pop(key, None)
            parsed_name = (parsed.get("client_name") or "").strip()
            parsed_allowed = (parsed.get("allowed_ips") or "").strip() or None

            if existing is None:
                self.db.session.add(
                    self.wireguard_peer_cache_model(
                        interface_name=key[0],
                        peer_public_key=key[1],
                        client_name=parsed_name,
                        allowed_ips=parsed_allowed,
                    )
                )
                changed = True
                continue

            if (existing.client_name or "").strip() != parsed_name:
                existing.client_name = parsed_name
                changed = True
            if ((existing.allowed_ips or "").strip() or None) != parsed_allowed:
                existing.allowed_ips = parsed_allowed
                changed = True

        for stale_row in existing_by_key.values():
            self.db.session.delete(stale_row)
            changed = True

        if changed:
            self.db.session.commit()

        self._wireguard_peer_cache_last_sync_ts = now_ts
        return len(by_key)

    def load_wireguard_peer_cache_maps(self):
        by_public_key = {}
        by_allowed_ip = {}

        for row in self.wireguard_peer_cache_model.query.all():
            interface_name = (row.interface_name or "").strip()
            peer_public_key = (row.peer_public_key or "").strip()
            client_name = (row.client_name or "").strip()
            if not interface_name or not client_name:
                continue

            if peer_public_key:
                by_public_key[(interface_name, peer_public_key)] = client_name

            for ip in self.split_wireguard_allowed_ips(row.allowed_ips):
                by_allowed_ip[(interface_name, ip)] = client_name

        return by_public_key, by_allowed_ip

    def is_wireguard_peer_active(self, latest_handshake_ts):
        handshake_ts = int(latest_handshake_ts or 0)
        if handshake_ts <= 0:
            return False
        if self.wireguard_active_handshake_seconds <= 0:
            return True
        return max(int(time.time()) - handshake_ts, 0) <= self.wireguard_active_handshake_seconds

    def collect_wireguard_status_rows(self):
        status_rows = {
            "antizapret": {
                "profile": "antizapret-wg",
                "label": "Antizapret WG",
                "protocol": "WireGuard",
                "filename": "wg:antizapret",
                "exists": False,
                "snapshot_time": "-",
                "updated_at": "-",
                "clients": [],
                "traffic_clients": [],
            },
            "vpn": {
                "profile": "vpn-wg",
                "label": "VPN WG",
                "protocol": "WireGuard",
                "filename": "wg:vpn",
                "exists": False,
                "snapshot_time": "-",
                "updated_at": "-",
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
            out_rows = []
            for interface_name in ("antizapret", "vpn"):
                row = status_rows[interface_name]
                row.update(
                    {
                        "client_count": 0,
                        "unique_real_ips": 0,
                        "total_received": 0,
                        "total_sent": 0,
                        "total_received_human": self.human_bytes(0),
                        "total_sent_human": self.human_bytes(0),
                        "total_traffic_human": self.human_bytes(0),
                    }
                )
                out_rows.append(row)
            return out_rows

        now_dt = datetime.utcnow()
        snapshot_time = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        parsed_peers = []
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

            latest_handshake_ts = 0
            bytes_received = 0
            bytes_sent = 0
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

        by_public_key, by_allowed_ip = self.load_wireguard_peer_cache_maps()
        missing_mapping = False
        for peer in parsed_peers:
            iface = peer.get("interface")
            key = (iface, (peer.get("peer_public_key") or "").strip())
            allowed_candidates = self.split_wireguard_allowed_ips(peer.get("allowed_ips") or "")
            fallback_ip = allowed_candidates[0] if allowed_candidates else ""
            if key in by_public_key:
                continue
            if fallback_ip and (iface, fallback_ip) in by_allowed_ip:
                continue
            missing_mapping = True
            break

        if missing_mapping:
            try:
                self.sync_wireguard_peer_cache_from_configs(force=False)
                by_public_key, by_allowed_ip = self.load_wireguard_peer_cache_maps()
            except Exception as exc:
                self.db.session.rollback()
                self.app.logger.warning("Не удалось обновить wireguard_peer_cache из конфигов: %s", exc)

        for peer in parsed_peers:
            interface_name = peer.get("interface")
            row = status_rows[interface_name]

            allowed_ips = self.split_wireguard_allowed_ips(peer.get("allowed_ips") or "")
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
            real_ip = self.extract_ip_from_wireguard_endpoint(endpoint)
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
                "bytes_received_human": self.human_bytes(peer.get("bytes_received") or 0),
                "bytes_sent_human": self.human_bytes(peer.get("bytes_sent") or 0),
                "total_bytes_human": self.human_bytes((peer.get("bytes_received") or 0) + (peer.get("bytes_sent") or 0)),
                "connected_since": connected_since,
                "connected_since_ts": latest_handshake_ts,
                "cipher": "WireGuard",
            }

            row["traffic_clients"].append(client_payload)
            if self.is_wireguard_peer_active(latest_handshake_ts):
                row["clients"].append(client_payload)

        out_rows = []
        for interface_name in ("antizapret", "vpn"):
            row = status_rows[interface_name]
            row["clients"].sort(key=lambda item: int(item.get("total_bytes") or 0), reverse=True)

            total_received = sum(int(item.get("bytes_received") or 0) for item in row["clients"])
            total_sent = sum(int(item.get("bytes_sent") or 0) for item in row["clients"])
            unique_real_ips = len(
                {
                    (item.get("real_ip") or "").strip()
                    for item in row["clients"]
                    if (item.get("real_ip") or "").strip()
                }
            )

            row.update(
                {
                    "client_count": len(row["clients"]),
                    "unique_real_ips": unique_real_ips,
                    "total_received": total_received,
                    "total_sent": total_sent,
                    "total_received_human": self.human_bytes(total_received),
                    "total_sent_human": self.human_bytes(total_sent),
                    "total_traffic_human": self.human_bytes(total_received + total_sent),
                }
            )
            out_rows.append(row)

        return out_rows

    def collect_status_rows_for_snapshot(self):
        rows = [
            self.parse_status_log(profile_key, filename)
            for profile_key, filename in self.status_log_files.items()
        ]
        rows.extend(self.collect_wireguard_status_rows())
        return rows

    def parse_status_log(self, profile_key, filename):
        source = self.read_status_source(profile_key, filename)
        raw = source.get("raw", "")
        meta = self.profile_meta(profile_key)

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
                "total_received_human": self.human_bytes(0),
                "total_sent_human": self.human_bytes(0),
                "total_traffic_human": self.human_bytes(0),
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

        client_pattern = re.compile(
            r"CLIENT_LIST,([^,\n]+),([^,\n]+),([^,\n]*),([^,\n]*),(\d+),(\d+),([^,\n]+),(\d+),([^,\n]*),([^,\n]*),([^,\n]*),([^,\n\r ]+)"
        )

        clients = []
        for match in client_pattern.finditer(raw):
            common_name = match.group(1).strip()
            real_address = match.group(2).strip()
            virtual_address = match.group(3).strip()
            bytes_received = int(match.group(5) or 0)
            bytes_sent = int(match.group(6) or 0)
            connected_since = match.group(7).strip()
            connected_since_ts = int(match.group(8) or 0)
            cipher = match.group(12).strip()

            ip_only = self.extract_ip_from_openvpn_address(real_address)

            clients.append(
                {
                    "common_name": common_name,
                    "real_address": real_address,
                    "real_ip": ip_only,
                    "virtual_address": virtual_address,
                    "session_kind": "openvpn",
                    "bytes_received": bytes_received,
                    "bytes_sent": bytes_sent,
                    "total_bytes": bytes_received + bytes_sent,
                    "bytes_received_human": self.human_bytes(bytes_received),
                    "bytes_sent_human": self.human_bytes(bytes_sent),
                    "total_bytes_human": self.human_bytes(bytes_received + bytes_sent),
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

                ip_only = self.extract_ip_from_openvpn_address(real_address)

                clients.append(
                    {
                        "common_name": common_name,
                        "real_address": real_address,
                        "real_ip": ip_only,
                        "virtual_address": virtual_address,
                        "session_kind": "openvpn",
                        "bytes_received": bytes_received,
                        "bytes_sent": bytes_sent,
                        "total_bytes": bytes_received + bytes_sent,
                        "bytes_received_human": self.human_bytes(bytes_received),
                        "bytes_sent_human": self.human_bytes(bytes_sent),
                        "total_bytes_human": self.human_bytes(bytes_received + bytes_sent),
                        "connected_since": connected_since,
                        "connected_since_ts": connected_since_ts,
                        "cipher": cipher,
                    }
                )

        clients.sort(key=lambda x: x["total_bytes"], reverse=True)

        total_received = sum(c["bytes_received"] for c in clients)
        total_sent = sum(c["bytes_sent"] for c in clients)
        unique_real_ips = len({c["real_ip"] for c in clients if c.get("real_ip")})

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
            "total_received_human": self.human_bytes(total_received),
            "total_sent_human": self.human_bytes(total_sent),
            "total_traffic_human": self.human_bytes(total_received + total_sent),
            "clients": clients,
        }

    def parse_event_log(self, profile_key, filename):
        source = self.read_event_source(profile_key, filename)
        raw = source.get("raw", "")
        meta = self.profile_meta(profile_key)

        if not raw:
            return {
                "profile": profile_key,
                "label": f"{meta['network']} {meta['transport']}",
                "filename": source.get("source_name", os.path.basename(filename)),
                "exists": False,
                "updated_at": "-",
                "updated_at_ts": 0,
                "line_count": 0,
                "event_counts": {},
                "peer_connected_clients": [],
                "client_sessions": [],
                "recent_lines": [],
            }

        updated_at_ts = int(source.get("updated_at_ts") or 0)
        updated_at = datetime.fromtimestamp(updated_at_ts).strftime("%Y-%m-%d %H:%M:%S") if updated_at_ts > 0 else "-"

        raw_lines = raw.splitlines()
        line_count = len(raw_lines)
        event_patterns = {
            "peer_connection": r"Peer Connection Initiated",
            "push_request": r"PUSH_REQUEST",
            "push_reply": r"PUSH_REPLY",
            "tls_events": r"\bTLS:",
            "multi_create": r"MULTI_sva|MULTI: multi_create_instance called",
            "sigterm": r"\bSIGTERM\b",
        }
        event_counts = {
            key: len(re.findall(pattern, raw)) for key, pattern in event_patterns.items()
        }

        peer_clients = re.findall(r"\[([^\]]+)\] Peer Connection Initiated", raw)
        peer_connected = Counter(peer_clients).most_common(10)

        endpoint_info = {}

        for line_no, raw_line in enumerate(raw_lines):
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            line_ts = 0
            ts_match = re.match(r"^(\d+),[A-Z]?,(.*)$", raw_line)
            if ts_match:
                line_ts = int(ts_match.group(1) or 0)
                line = (ts_match.group(2) or "").strip()
            else:
                line = re.sub(r"^\d+,[A-Z]?,", "", raw_line, count=1).strip()
            if not line:
                continue

            m_verify = re.search(r"^([^\s]+:\d+)\s+VERIFY OK: depth=0, CN=([^\s]+)", line)
            if m_verify:
                endpoint = self.normalize_openvpn_endpoint(m_verify.group(1))
                client_name = m_verify.group(2)
                endpoint_info.setdefault(
                    endpoint,
                    {
                        "client": "-",
                        "ip": self.extract_ip_from_openvpn_address(endpoint),
                        "version": None,
                        "platform": None,
                        "last_order": -1,
                        "last_ts": 0,
                    },
                )
                endpoint_info[endpoint]["client"] = client_name

            m_peer = re.search(r"\[([^\]]+)\] Peer Connection Initiated with \[AF_INET\]([^\s]+:\d+)", line)
            if m_peer:
                client_name = m_peer.group(1)
                endpoint = self.normalize_openvpn_endpoint(m_peer.group(2))
                endpoint_info.setdefault(
                    endpoint,
                    {
                        "client": "-",
                        "ip": self.extract_ip_from_openvpn_address(endpoint),
                        "version": None,
                        "platform": None,
                        "last_order": -1,
                        "last_ts": 0,
                    },
                )
                endpoint_info[endpoint]["client"] = client_name

            m_peer_alt = re.search(r"^([^\s]+:\d+)\s+\[([^\]]+)\] Peer Connection Initiated with \[AF_INET\]([^\s]+:\d+)", line)
            if m_peer_alt:
                endpoint = self.normalize_openvpn_endpoint(m_peer_alt.group(3))
                client_name = m_peer_alt.group(2)
                endpoint_info.setdefault(
                    endpoint,
                    {
                        "client": "-",
                        "ip": self.extract_ip_from_openvpn_address(endpoint),
                        "version": None,
                        "platform": None,
                        "last_order": -1,
                        "last_ts": 0,
                    },
                )
                endpoint_info[endpoint]["client"] = client_name

            m_name_endpoint = re.search(r"([A-Za-z0-9_.\-]+)/([^\s,]+:\d+)", line)
            if m_name_endpoint:
                client_name = m_name_endpoint.group(1)
                endpoint = self.normalize_openvpn_endpoint(m_name_endpoint.group(2))
                endpoint_info.setdefault(
                    endpoint,
                    {
                        "client": "-",
                        "ip": self.extract_ip_from_openvpn_address(endpoint),
                        "version": None,
                        "platform": None,
                        "last_order": -1,
                        "last_ts": 0,
                    },
                )
                if endpoint_info[endpoint]["client"] == "-":
                    endpoint_info[endpoint]["client"] = client_name

            m_peer_info = re.search(r"^([^\s]+:\d+)\s+peer info: (IV_VER|IV_PLAT)=([^\s]+)", line)
            if m_peer_info:
                endpoint = self.normalize_openvpn_endpoint(m_peer_info.group(1))
                key = m_peer_info.group(2)
                val = m_peer_info.group(3)
                endpoint_info.setdefault(
                    endpoint,
                    {
                        "client": "-",
                        "ip": self.extract_ip_from_openvpn_address(endpoint),
                        "version": None,
                        "platform": None,
                        "last_order": -1,
                        "last_ts": 0,
                    },
                )
                if key == "IV_VER":
                    endpoint_info[endpoint]["version"] = val
                    endpoint_info[endpoint]["last_order"] = line_no
                    if line_ts > 0:
                        endpoint_info[endpoint]["last_ts"] = line_ts
                elif key == "IV_PLAT":
                    endpoint_info[endpoint]["platform"] = val
                    endpoint_info[endpoint]["last_order"] = line_no
                    if line_ts > 0:
                        endpoint_info[endpoint]["last_ts"] = line_ts

        client_sessions = []
        for endpoint, info in endpoint_info.items():
            client_sessions.append(
                {
                    "client": info["client"],
                    "endpoint": endpoint,
                    "ip": info["ip"],
                    "version": info.get("version"),
                    "platform": info.get("platform"),
                    "last_order": info.get("last_order", -1),
                    "event_ts": int(info.get("last_ts") or 0),
                }
            )

        lines = [line.strip() for line in raw_lines if line.strip()]
        recent_lines = [line[:220] for line in lines[-8:]]

        return {
            "profile": profile_key,
            "label": f"{meta['network']} {meta['transport']}",
            "filename": source.get("source_name", os.path.basename(filename)),
            "exists": True,
            "updated_at": updated_at,
            "updated_at_ts": updated_at_ts,
            "line_count": line_count,
            "event_counts": event_counts,
            "peer_connected_clients": peer_connected,
            "client_sessions": client_sessions,
            "recent_lines": recent_lines,
        }
