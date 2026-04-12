import os
import subprocess
import time
from datetime import datetime, timezone


class ConfigFileHandler:
    _CERT_EXPIRY_CACHE = {}
    try:
        _CERT_EXPIRY_CACHE_TTL_SECONDS = max(
            1,
            int(os.getenv("OPENVPN_CERT_EXPIRY_CACHE_TTL_SECONDS", "300")),
        )
    except (TypeError, ValueError):
        _CERT_EXPIRY_CACHE_TTL_SECONDS = 300

    def __init__(self, config_paths):
        self.config_paths = config_paths

    @classmethod
    def clear_openvpn_cert_expiry_cache(cls):
        cls._CERT_EXPIRY_CACHE.clear()

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
        unique_client_names = set()

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

                    unique_client_names.add(client_name)

        for client_name in sorted(unique_client_names):
            crt_path = self._resolve_crt_path_for_client(client_name, cert_keys_dir)
            if not crt_path:
                expiry[client_name] = {
                    "days_left": None,
                    "expires_at": None,
                }
                continue

            expiry[client_name] = self._read_cached_openvpn_cert_expiry(crt_path)

        return expiry

    def _resolve_crt_path_for_client(self, client_name, cert_keys_dir):
        possible_crt_names = [
            f"{client_name}.crt",
            f"{client_name.replace('-', '_')}.crt",
            f"client-{client_name}.crt",
        ]

        for crt_name in possible_crt_names:
            candidate = os.path.join(cert_keys_dir, crt_name)
            if os.path.exists(candidate):
                return candidate

        return None

    def _read_cached_openvpn_cert_expiry(self, crt_path):
        try:
            mtime = os.path.getmtime(crt_path)
        except OSError:
            return {
                "days_left": None,
                "expires_at": None,
            }

        now_ts = time.time()
        cached = self.__class__._CERT_EXPIRY_CACHE.get(crt_path)

        if (
            cached
            and float(cached.get("mtime", -1.0)) == float(mtime)
            and (now_ts - float(cached.get("cached_at", 0.0)))
            <= float(self.__class__._CERT_EXPIRY_CACHE_TTL_SECONDS)
        ):
            cached_value = cached.get("value") or {}
            return {
                "days_left": cached_value.get("days_left"),
                "expires_at": cached_value.get("expires_at"),
            }

        value = self._read_openvpn_cert_expiry(crt_path)

        self.__class__._CERT_EXPIRY_CACHE[crt_path] = {
            "mtime": float(mtime),
            "cached_at": now_ts,
            "value": {
                "days_left": value.get("days_left"),
                "expires_at": value.get("expires_at"),
            },
        }

        # Hard cap to avoid unbounded growth in long-running workers.
        if len(self.__class__._CERT_EXPIRY_CACHE) > 4096:
            self.__class__._CERT_EXPIRY_CACHE.clear()

        return value

    def _read_openvpn_cert_expiry(self, crt_path):
        try:
            result = subprocess.run(
                ["openssl", "x509", "-in", crt_path, "-noout", "-enddate"],
                capture_output=True,
                text=True,
                check=True,
            )

            line = result.stdout.strip()
            if not line.startswith("notAfter="):
                return {
                    "days_left": None,
                    "expires_at": None,
                }

            date_str = line.split("=", 1)[1].strip()
            expiry_date = datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z")
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            days_left = (expiry_date - now).days

            return {
                "days_left": days_left,
                "expires_at": expiry_date.strftime("%Y-%m-%d %H:%M UTC"),
            }
        except Exception:
            return {
                "days_left": None,
                "expires_at": None,
            }

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
