import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils.wg_awg_runtime_enforcer import WgAwgRuntimeEnforcer


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeModel:
    query = _FakeQuery([])


class WgAwgRuntimeEnforcerTests(unittest.TestCase):
    def setUp(self):
        rows = [
            SimpleNamespace(interface_name="antizapret", peer_public_key="k1", client_name="alice"),
            SimpleNamespace(interface_name="vpn", peer_public_key="k2", client_name="alice"),
            SimpleNamespace(interface_name="vpn", peer_public_key="k3", client_name="bob"),
        ]
        _FakeModel.query = _FakeQuery(rows)
        self.enforcer = WgAwgRuntimeEnforcer(
            wireguard_peer_cache_model=_FakeModel,
            wireguard_config_files={"antizapret": "/etc/wireguard/antizapret.conf", "vpn": "/etc/wireguard/vpn.conf"},
            command_timeout_seconds=3,
        )

    @patch("utils.wg_awg_runtime_enforcer.subprocess.run")
    def test_block_client_runtime_removes_all_client_peers(self, run_mock):
        run_mock.return_value = SimpleNamespace(returncode=0, stderr="")
        result = self.enforcer.block_client_runtime("Alice")

        self.assertEqual(result["removed_count"], 2)
        self.assertEqual(result["error_count"], 0)
        called = [tuple(call.args[0]) for call in run_mock.call_args_list]
        self.assertIn(("wg", "set", "antizapret", "peer", "k1", "remove"), called)
        self.assertIn(("wg", "set", "vpn", "peer", "k2", "remove"), called)

    @patch("utils.wg_awg_runtime_enforcer.subprocess.run")
    def test_unblock_client_runtime_syncs_client_interfaces(self, run_mock):
        run_mock.return_value = SimpleNamespace(returncode=0, stderr="")
        result = self.enforcer.unblock_client_runtime("alice")

        self.assertEqual(result["synced_count"], 2)
        called = [tuple(call.args[0]) for call in run_mock.call_args_list]
        self.assertIn(("wg", "syncconf", "antizapret", "/etc/wireguard/antizapret.conf"), called)
        self.assertIn(("wg", "syncconf", "vpn", "/etc/wireguard/vpn.conf"), called)


if __name__ == "__main__":
    unittest.main()

