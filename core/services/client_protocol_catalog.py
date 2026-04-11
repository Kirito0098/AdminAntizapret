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

        deleted_total_bytes = sum(int(item.get("total_bytes") or 0) for item in deleted_rows)
        deleted_unique_clients = {
            (item.get("common_name") or "").strip().lower()
            for item in deleted_rows
            if (item.get("common_name") or "").strip()
        }
        deleted_summary = {
            "users_count": len(deleted_unique_clients),
            "total_bytes": deleted_total_bytes,
            "total_bytes_human": self.human_bytes(deleted_total_bytes),
        }
        return regular_rows, deleted_rows, deleted_summary
