import os
import subprocess
from datetime import datetime, timezone


class ConfigFileHandler:
    def __init__(self, config_paths):
        self.config_paths = config_paths

    def _collect_files(self, paths, extension):
        collected = []
        for directory in paths:
            if os.path.exists(directory):
                for root, _, files in os.walk(directory):
                    collected.extend(
                        os.path.join(root, f) for f in files if f.endswith(extension)
                    )
        return collected

    def get_config_files(self):
        openvpn_files = self._collect_files(self.config_paths["openvpn"], ".ovpn")
        wg_files = self._collect_files(self.config_paths["wg"], ".conf")
        amneziawg_files = self._collect_files(self.config_paths["amneziawg"], ".conf")
        return openvpn_files, wg_files, amneziawg_files

    def get_openvpn_cert_expiry(self):
        expiry = {}
        cert_keys_dir = "/etc/openvpn/client/keys"

        for base_dir in self.config_paths["openvpn"]:
            if not os.path.exists(base_dir):
                continue

            for root, _, files in os.walk(base_dir):
                for filename in files:
                    if not filename.endswith(".ovpn"):
                        continue

                    client_name = self._extract_client_name_from_ovpn(filename)
                    if not client_name:
                        continue

                    possible_crt_names = [
                        f"{client_name}.crt",
                        f"{client_name.replace('-', '_')}.crt",
                        f"client-{client_name}.crt",
                    ]

                    crt_path = None
                    for crt_name in possible_crt_names:
                        candidate = os.path.join(cert_keys_dir, crt_name)
                        if os.path.exists(candidate):
                            crt_path = candidate
                            break

                    if not crt_path:
                        expiry[client_name] = {
                            "days_left": None,
                            "expires_at": None,
                        }
                        continue

                    try:
                        result = subprocess.run(
                            ["openssl", "x509", "-in", crt_path, "-noout", "-enddate"],
                            capture_output=True,
                            text=True,
                            check=True,
                        )

                        line = result.stdout.strip()
                        if not line.startswith("notAfter="):
                            expiry[client_name] = {
                                "days_left": None,
                                "expires_at": None,
                            }
                            continue

                        date_str = line.split("=", 1)[1].strip()
                        expiry_date = datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z")
                        expiry_date = expiry_date.replace(tzinfo=timezone.utc)

                        now = datetime.now(timezone.utc)
                        days_left = (expiry_date - now).days

                        expiry[client_name] = {
                            "days_left": days_left,
                            "expires_at": expiry_date.strftime("%Y-%m-%d %H:%M UTC"),
                        }

                    except Exception:
                        expiry[client_name] = {
                            "days_left": None,
                            "expires_at": None,
                        }

        return expiry

    def _extract_client_name_from_ovpn(self, filename):
        name = os.path.splitext(filename)[0]

        prefixes = ["antizapret-", "vpn-", ""]
        for prefix in prefixes:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
                break

        if "-(" in name:
            name = name.split("-(")[0]

        name = name.strip("- ")

        return name if len(name) >= 2 else None
