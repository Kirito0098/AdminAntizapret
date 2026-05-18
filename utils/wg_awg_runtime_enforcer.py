import subprocess


class WgAwgRuntimeEnforcer:
    def __init__(
        self,
        *,
        wireguard_peer_cache_model,
        wireguard_config_files,
        command_timeout_seconds=4,
    ):
        self.wireguard_peer_cache_model = wireguard_peer_cache_model
        self.wireguard_config_files = dict(wireguard_config_files or {})
        self.command_timeout_seconds = max(1, int(command_timeout_seconds or 4))

    def _run(self, args):
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.command_timeout_seconds,
        )

    def _normalize_client_name(self, client_name):
        return (client_name or "").strip().lower()

    def _collect_client_peers(self, client_name):
        normalized = self._normalize_client_name(client_name)
        if not normalized:
            return []
        rows = self.wireguard_peer_cache_model.query.all()
        peers = []
        for row in rows:
            row_name = (getattr(row, "client_name", "") or "").strip().lower()
            iface = (getattr(row, "interface_name", "") or "").strip()
            key = (getattr(row, "peer_public_key", "") or "").strip()
            if row_name != normalized or not iface or not key:
                continue
            peers.append((iface, key))
        return peers

    def block_client_runtime(self, client_name):
        peers = self._collect_client_peers(client_name)
        removed = []
        errors = []
        for interface_name, peer_public_key in peers:
            result = self._run(["wg", "set", interface_name, "peer", peer_public_key, "remove"])
            if result.returncode == 0:
                removed.append((interface_name, peer_public_key))
            else:
                errors.append(
                    {
                        "interface": interface_name,
                        "peer_public_key": peer_public_key,
                        "stderr": (result.stderr or "").strip(),
                    }
                )
        return {
            "removed_count": len(removed),
            "error_count": len(errors),
            "errors": errors,
        }

    def unblock_client_runtime(self, client_name):
        peers = self._collect_client_peers(client_name)
        interfaces = sorted({iface for iface, _ in peers if iface})
        if not interfaces:
            interfaces = sorted(self.wireguard_config_files.keys())

        synced = []
        errors = []
        for interface_name in interfaces:
            config_path = (self.wireguard_config_files.get(interface_name) or "").strip()
            if not config_path:
                continue
            result = self._run(["wg", "syncconf", interface_name, config_path])
            if result.returncode == 0:
                synced.append(interface_name)
            else:
                errors.append(
                    {
                        "interface": interface_name,
                        "stderr": (result.stderr or "").strip(),
                    }
                )
        return {
            "synced_count": len(synced),
            "error_count": len(errors),
            "errors": errors,
        }

