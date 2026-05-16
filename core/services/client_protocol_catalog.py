from collections import defaultdict
import os
import re


class ClientProtocolCatalogService:
    def __init__(
        self,
        *,
        openvpn_folders,
        config_paths,
        db,
        user_traffic_sample_model,
        human_bytes,
    ):
        self.openvpn_folders = openvpn_folders
        self.config_paths = config_paths
        self.db = db
        self.user_traffic_sample_model = user_traffic_sample_model
        self.human_bytes = human_bytes

    def normalize_traffic_client_identity(self, raw_name):
        """Единый ключ клиента для сопоставления конфигов и строк трафика в БД."""
        name = (raw_name or "").strip()
        if not name or name == "-":
            return ""
        normalized = re.sub(r"^(?:antizapret-|vpn-)", "", name, flags=re.IGNORECASE)
        normalized = re.sub(r"-(?:udp|tcp|wg|am)$", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"-\([^)]+\)$", "", normalized)
        return (normalized or name).strip().lower()

    def extract_client_name_from_config_file(self, file_path):
        filename = os.path.basename(file_path or "")
        stem = filename.rsplit(".", 1)[0]
        raw_name = re.sub(r"^(?:antizapret-|vpn-)", "", stem, flags=re.IGNORECASE)
        raw_name = re.sub(r"-(?:udp|tcp|wg|am)$", "", raw_name, flags=re.IGNORECASE)
        raw_name = re.sub(r"-\([^)]+\)$", "", raw_name)
        return (raw_name or "").strip()

    def collect_existing_config_client_names(self):
        names = set()

        for base_dir in self.openvpn_folders:
            if not os.path.exists(base_dir):
                continue

            for root, _, files in os.walk(base_dir):
                for filename in files:
                    if not filename.lower().endswith(".ovpn"):
                        continue
                    client_name = self.extract_client_name_from_config_file(filename)
                    if client_name:
                        names.add(client_name.strip())

        for config_type in ("wg", "amneziawg"):
            for base_dir in self.config_paths.get(config_type, []):
                if not os.path.exists(base_dir):
                    continue
                for root, _, files in os.walk(base_dir):
                    for filename in files:
                        if not filename.lower().endswith(".conf"):
                            continue
                        client_name = self.extract_client_name_from_config_file(filename)
                        if client_name:
                            names.add(client_name.strip())

        return names

    def collect_config_protocols_by_client(self):
        protocols_by_client = defaultdict(set)

        for base_dir in self.openvpn_folders:
            if not os.path.exists(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for filename in files:
                    if not filename.lower().endswith(".ovpn"):
                        continue
                    client_name = self.extract_client_name_from_config_file(filename)
                    if client_name:
                        protocols_by_client[client_name.strip().lower()].add("OpenVPN")

        for config_type in ("wg", "amneziawg"):
            for base_dir in self.config_paths.get(config_type, []):
                if not os.path.exists(base_dir):
                    continue
                for root, _, files in os.walk(base_dir):
                    for filename in files:
                        if not filename.lower().endswith(".conf"):
                            continue
                        client_name = self.extract_client_name_from_config_file(filename)
                        if client_name:
                            protocols_by_client[client_name.strip().lower()].add("WireGuard")

        return protocols_by_client

    def collect_sample_protocols_by_client(self):
        protocols_by_client = defaultdict(set)

        delta_total_expr = (
            self.user_traffic_sample_model.delta_received
            + self.user_traffic_sample_model.delta_sent
        )
        rows = self.db.session.query(
            self.user_traffic_sample_model.common_name.label("common_name"),
            self.user_traffic_sample_model.protocol_type.label("protocol_type"),
            self.db.func.sum(delta_total_expr).label("total_bytes"),
        ).group_by(
            self.user_traffic_sample_model.common_name,
            self.user_traffic_sample_model.protocol_type,
        ).all()

        for row in rows:
            client_name = (row.common_name or "").strip().lower()
            if not client_name:
                continue

            if int(row.total_bytes or 0) <= 0:
                continue

            protocol = (row.protocol_type or "openvpn").strip().lower()
            protocol_label = "WireGuard" if protocol == "wireguard" else "OpenVPN"
            protocols_by_client[client_name].add(protocol_label)

        return protocols_by_client

    def split_persisted_traffic_rows_by_config(self, persisted_rows):
        existing_client_names = self.collect_existing_config_client_names()
        existing_client_names_lower = {name.lower() for name in existing_client_names if name}

        regular_rows = []
        deleted_rows = []
        for row in persisted_rows:
            common_name = (row.get("common_name") or "").strip()
            if common_name and common_name.lower() in existing_client_names_lower:
                regular_rows.append(row)
            else:
                deleted_rows.append(row)

        deleted_rows = self.aggregate_persisted_traffic_rows_by_client_identity(deleted_rows)

        deleted_total_bytes = sum(int(item.get("total_bytes") or 0) for item in deleted_rows)
        deleted_unique_clients = {
            self.normalize_traffic_client_identity(item.get("common_name") or "")
            for item in deleted_rows
            if self.normalize_traffic_client_identity(item.get("common_name") or "")
        }
        deleted_summary = {
            "users_count": len(deleted_unique_clients),
            "total_bytes": deleted_total_bytes,
            "total_bytes_human": self.human_bytes(deleted_total_bytes),
        }
        return regular_rows, deleted_rows, deleted_summary

    def aggregate_persisted_traffic_rows_by_client_identity(self, rows):
        """Сводит строки трафика (по протоколам/профилям) в одну запись на клиента."""
        grouped = {}

        def _pick_display_name(current, candidate):
            if not current:
                return candidate
            if not candidate:
                return current

            def _score(name):
                value = (name or "").strip()
                penalty = 0
                if re.match(r"^(?:antizapret-|vpn-)", value, flags=re.IGNORECASE):
                    penalty += 100
                if re.match(r"^(?:antizapret|vpn)-", value, flags=re.IGNORECASE):
                    penalty += 50
                return penalty + len(value)

            return candidate if _score(candidate) < _score(current) else current

        for row in rows:
            common_name = (row.get("common_name") or "").strip()
            identity = self.normalize_traffic_client_identity(common_name)
            if not identity:
                continue

            bucket = grouped.get(identity)
            if bucket is None:
                bucket = {
                    "common_name": common_name,
                    "protocol_type": row.get("protocol_type"),
                    "protocol_label": row.get("protocol_label"),
                    "display_name": row.get("display_name") or common_name,
                    "protocols": set(),
                    "total_received": 0,
                    "total_sent": 0,
                    "total_bytes": 0,
                    "total_received_vpn": 0,
                    "total_sent_vpn": 0,
                    "total_bytes_vpn": 0,
                    "total_received_antizapret": 0,
                    "total_sent_antizapret": 0,
                    "total_bytes_antizapret": 0,
                    "traffic_1d": 0,
                    "traffic_7d": 0,
                    "traffic_30d": 0,
                    "total_sessions": 0,
                    "first_seen_at": row.get("first_seen_at"),
                    "last_seen_at": row.get("last_seen_at"),
                    "is_active": bool(row.get("is_active")),
                }
                grouped[identity] = bucket
            else:
                bucket["common_name"] = _pick_display_name(bucket.get("common_name"), common_name)
                if row.get("is_active"):
                    bucket["is_active"] = True

            for protocol_token in str(row.get("protocols") or "").split(","):
                token = protocol_token.strip()
                if token and token != "-":
                    bucket["protocols"].add(token)

            bucket["total_received"] += int(row.get("total_received") or 0)
            bucket["total_sent"] += int(row.get("total_sent") or 0)
            bucket["total_bytes"] += int(row.get("total_bytes") or 0)
            bucket["total_received_vpn"] += int(row.get("total_received_vpn") or 0)
            bucket["total_sent_vpn"] += int(row.get("total_sent_vpn") or 0)
            bucket["total_bytes_vpn"] += int(row.get("total_bytes_vpn") or 0)
            bucket["total_received_antizapret"] += int(row.get("total_received_antizapret") or 0)
            bucket["total_sent_antizapret"] += int(row.get("total_sent_antizapret") or 0)
            bucket["total_bytes_antizapret"] += int(row.get("total_bytes_antizapret") or 0)
            bucket["traffic_1d"] += int(row.get("traffic_1d") or 0)
            bucket["traffic_7d"] += int(row.get("traffic_7d") or 0)
            bucket["traffic_30d"] += int(row.get("traffic_30d") or 0)
            bucket["total_sessions"] += int(row.get("total_sessions") or 0)

            row_last_seen = row.get("last_seen_at")
            if row_last_seen and (not bucket.get("last_seen_at") or str(row_last_seen) > str(bucket["last_seen_at"])):
                bucket["last_seen_at"] = row_last_seen

        result = []
        for bucket in grouped.values():
            protocols = sorted(bucket.pop("protocols", set()))
            bucket["protocols"] = ", ".join(protocols) if protocols else "-"
            if not bucket.get("protocol_label") and protocols:
                bucket["protocol_label"] = protocols[0] if len(protocols) == 1 else "Mixed"
            rx = int(bucket["total_received"])
            tx = int(bucket["total_sent"])
            rx_vpn = int(bucket["total_received_vpn"])
            tx_vpn = int(bucket["total_sent_vpn"])
            rx_az = int(bucket["total_received_antizapret"])
            tx_az = int(bucket["total_sent_antizapret"])
            bucket["total_received_human"] = self.human_bytes(rx)
            bucket["total_sent_human"] = self.human_bytes(tx)
            bucket["total_bytes_human"] = self.human_bytes(int(bucket["total_bytes"]))
            bucket["total_received_vpn_human"] = self.human_bytes(rx_vpn)
            bucket["total_sent_vpn_human"] = self.human_bytes(tx_vpn)
            bucket["total_bytes_vpn_human"] = self.human_bytes(int(bucket["total_bytes_vpn"]))
            bucket["total_received_antizapret_human"] = self.human_bytes(rx_az)
            bucket["total_sent_antizapret_human"] = self.human_bytes(tx_az)
            bucket["total_bytes_antizapret_human"] = self.human_bytes(int(bucket["total_bytes_antizapret"]))
            bucket["traffic_1d_human"] = self.human_bytes(int(bucket["traffic_1d"]))
            bucket["traffic_7d_human"] = self.human_bytes(int(bucket["traffic_7d"]))
            bucket["traffic_30d_human"] = self.human_bytes(int(bucket["traffic_30d"]))
            bucket["display_name"] = bucket["common_name"]
            result.append(bucket)

        result.sort(key=lambda item: (item.get("common_name") or "").lower())
        return result
