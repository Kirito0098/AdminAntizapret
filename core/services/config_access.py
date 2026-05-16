import os
import re


class ConfigAccessService:
    def __init__(self, *, config_file_handler, group_folders, config_paths, openvpn_folders):
        self.config_file_handler = config_file_handler
        self.group_folders = group_folders
        self.config_paths = config_paths
        self.openvpn_folders = openvpn_folders

    def normalize_openvpn_group_key(self, filename):
        base_name = os.path.basename(filename)
        stem, ext = os.path.splitext(base_name)
        if ext.lower() != ".ovpn":
            return stem.lower().strip() or stem.lower()

        normalized = stem.strip()
        lowered = normalized.lower()

        for prefix in ("antizapret-", "vpn-"):
            if lowered.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        normalized = re.sub(r"-(udp|tcp)$", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"-\([^)]+\)$", "", normalized)

        cleaned = normalized.strip("-_ ")
        return cleaned.lower() if cleaned else stem.lower()

    def get_openvpn_group_display_name(self, filename):
        base_name = os.path.basename(filename)
        stem, _ = os.path.splitext(base_name)

        display = stem.strip()
        lowered = display.lower()

        for prefix in ("antizapret-", "vpn-"):
            if lowered.startswith(prefix):
                display = display[len(prefix):]
                break

        display = re.sub(r"-(udp|tcp)$", "", display, flags=re.IGNORECASE)
        display = re.sub(r"-\([^)]+\)$", "", display)
        display = display.strip("-_ ")
        return display or stem

    def collect_all_openvpn_files_for_access(self):
        original_paths = self.config_file_handler.config_paths["openvpn"]
        try:
            self.config_file_handler.config_paths["openvpn"] = [
                directory for folders in self.group_folders.values() for directory in folders
            ]
            all_openvpn, _, _ = self.config_file_handler.get_config_files()
            return all_openvpn
        finally:
            self.config_file_handler.config_paths["openvpn"] = original_paths

    def build_openvpn_access_groups(self, openvpn_paths):
        grouped = {}
        for file_path in openvpn_paths:
            file_name = os.path.basename(file_path)
            group_key = self.normalize_openvpn_group_key(file_name)
            if group_key not in grouped:
                grouped[group_key] = {
                    "group_key": group_key,
                    "display_name": self.get_openvpn_group_display_name(file_name),
                    "files": [],
                }
            grouped[group_key]["files"].append(file_name)

        for item in grouped.values():
            item["files"] = sorted(set(item["files"]), key=str.lower)

        return [grouped[k] for k in sorted(grouped.keys())]

    def normalize_conf_group_key(self, filename, config_type):
        base_name = os.path.basename(filename)
        stem, ext = os.path.splitext(base_name)
        if ext.lower() != ".conf":
            return stem.lower().strip() or stem.lower()

        normalized = stem.strip()
        lowered = normalized.lower()

        for prefix in ("antizapret-", "vpn-"):
            if lowered.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        if config_type == "amneziawg":
            normalized = re.sub(r"-am$", "", normalized, flags=re.IGNORECASE)
        elif config_type == "wg":
            normalized = re.sub(r"-wg$", "", normalized, flags=re.IGNORECASE)

        normalized = re.sub(r"-\([^)]+\)$", "", normalized)
        cleaned = normalized.strip("-_ ")
        return cleaned.lower() if cleaned else stem.lower()

    def get_conf_group_display_name(self, filename, config_type):
        base_name = os.path.basename(filename)
        stem, _ = os.path.splitext(base_name)

        display = stem.strip()
        lowered = display.lower()

        for prefix in ("antizapret-", "vpn-"):
            if lowered.startswith(prefix):
                display = display[len(prefix):]
                break

        if config_type == "amneziawg":
            display = re.sub(r"-am$", "", display, flags=re.IGNORECASE)
        elif config_type == "wg":
            display = re.sub(r"-wg$", "", display, flags=re.IGNORECASE)

        display = re.sub(r"-\([^)]+\)$", "", display)
        display = display.strip("-_ ")
        return display or stem

    def build_conf_access_groups(self, conf_paths, config_type):
        grouped = {}
        for file_path in conf_paths:
            file_name = os.path.basename(file_path)
            group_key = self.normalize_conf_group_key(file_name, config_type)
            if group_key not in grouped:
                grouped[group_key] = {
                    "group_key": group_key,
                    "display_name": self.get_conf_group_display_name(file_name, config_type),
                    "files": [],
                }
            grouped[group_key]["files"].append(file_name)

        for item in grouped.values():
            item["files"] = sorted(set(item["files"]), key=str.lower)

        return [grouped[k] for k in sorted(grouped.keys())]

    def collect_all_configs_for_access(self, config_type):
        if config_type == "openvpn":
            return self.collect_all_openvpn_files_for_access()

        extension = ".conf" if config_type in ("wg", "amneziawg") else None
        if not extension or config_type not in self.config_file_handler.config_paths:
            return []

        return self.config_file_handler._collect_files(
            self.config_file_handler.config_paths[config_type], extension
        )
