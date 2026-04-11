import json
import os
import re
import subprocess


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

    def collect_bw_interface_groups(self):
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
