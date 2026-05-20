import os
import subprocess
import tempfile

from sqlalchemy import func

from utils.wg_config_peers import collect_client_peer_specs


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

    def _peer_specs_for_client(self, client_name):
        return collect_client_peer_specs(self.wireguard_config_files, client_name)

    def _collect_client_peers(self, client_name):
        normalized = self._normalize_client_name(client_name)
        if not normalized:
            return []
        model = self.wireguard_peer_cache_model
        try:
            rows = model.query.filter(func.lower(model.client_name) == normalized).all()
        except (AttributeError, TypeError):
            rows = [
                row
                for row in model.query.all()
                if (getattr(row, "client_name", "") or "").strip().lower() == normalized
            ]
        peers = []
        for row in rows:
            iface = (getattr(row, "interface_name", "") or "").strip()
            key = (getattr(row, "peer_public_key", "") or "").strip()
            if iface and key:
                peers.append((iface, key))
        if peers:
            return peers
        return [
            (spec["interface_name"], spec["peer_public_key"])
            for spec in self._peer_specs_for_client(client_name)
            if spec.get("interface_name") and spec.get("peer_public_key")
        ]

    def _sync_interface_from_stripped_config(self, interface_name):
        strip_result = self._run(["wg-quick", "strip", interface_name])
        if strip_result.returncode != 0:
            return False, (strip_result.stderr or "").strip()

        stripped_config = strip_result.stdout or ""
        if not stripped_config.strip():
            return False, "empty stripped config"

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
                temp_file.write(stripped_config)
                temp_path = temp_file.name
            sync_result = self._run(["wg", "syncconf", interface_name, temp_path])
            if sync_result.returncode == 0:
                return True, ""
            return False, (sync_result.stderr or "").strip()
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _restore_peer_spec(self, spec):
        interface_name = (spec.get("interface_name") or "").strip()
        peer_public_key = (spec.get("peer_public_key") or "").strip()
        if not interface_name or not peer_public_key:
            return False, "missing interface or public key"

        args = ["wg", "set", interface_name, "peer", peer_public_key]
        allowed_ips = (spec.get("allowed_ips") or "").strip()
        if allowed_ips:
            args.extend(["allowed-ips", allowed_ips])

        preshared_key = (spec.get("preshared_key") or "").strip()
        psk_path = None
        try:
            if preshared_key:
                with tempfile.NamedTemporaryFile(mode="wb", suffix=".psk", delete=False) as psk_file:
                    psk_file.write(preshared_key.encode("ascii"))
                    psk_path = psk_file.name
                args.extend(["preshared-key", psk_path])

            result = self._run(args)
            if result.returncode == 0:
                return True, ""
            return False, (result.stderr or "").strip()
        finally:
            if psk_path:
                try:
                    os.unlink(psk_path)
                except OSError:
                    pass

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
        specs = self._peer_specs_for_client(client_name)
        restored = []
        errors = []

        if specs:
            for spec in specs:
                ok, stderr = self._restore_peer_spec(spec)
                if ok:
                    restored.append(spec["interface_name"])
                else:
                    errors.append(
                        {
                            "interface": spec.get("interface_name"),
                            "stderr": stderr,
                        }
                    )
            return {
                "synced_count": len(restored),
                "error_count": len(errors),
                "errors": errors,
            }

        peers = self._collect_client_peers(client_name)
        interfaces = sorted({iface for iface, _ in peers if iface})
        if not interfaces:
            interfaces = sorted(self.wireguard_config_files.keys())

        synced = []
        for interface_name in interfaces:
            if not (self.wireguard_config_files.get(interface_name) or "").strip():
                continue
            ok, stderr = self._sync_interface_from_stripped_config(interface_name)
            if ok:
                synced.append(interface_name)
            else:
                errors.append(
                    {
                        "interface": interface_name,
                        "stderr": stderr,
                    }
                )
        return {
            "synced_count": len(synced),
            "error_count": len(errors),
            "errors": errors,
        }
