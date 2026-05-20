import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils.wg_awg_runtime_enforcer import WgAwgRuntimeEnforcer


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

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
        run_mock.return_value = SimpleNamespace(returncode=0, stderr="", stdout="")
        result = self.enforcer.block_client_runtime("Alice")

        self.assertEqual(result["removed_count"], 2)
        self.assertEqual(result["error_count"], 0)
        called = [tuple(call.args[0]) for call in run_mock.call_args_list]
        self.assertIn(("wg", "set", "antizapret", "peer", "k1", "remove"), called)
        self.assertIn(("wg", "set", "vpn", "peer", "k2", "remove"), called)

    @patch("utils.wg_awg_runtime_enforcer.collect_client_peer_specs")
    @patch("utils.wg_awg_runtime_enforcer.subprocess.run")
    def test_unblock_client_runtime_restores_only_client_peers(self, run_mock, specs_mock):
        specs_mock.return_value = [
            {
                "interface_name": "antizapret",
                "peer_public_key": "k1",
                "client_name": "alice",
                "preshared_key": "psk1",
                "allowed_ips": "172.29.8.2/32",
            },
            {
                "interface_name": "vpn",
                "peer_public_key": "k2",
                "client_name": "alice",
                "preshared_key": "psk2",
                "allowed_ips": "172.28.8.2/32",
            },
        ]
        run_mock.return_value = SimpleNamespace(returncode=0, stderr="", stdout="")
        result = self.enforcer.unblock_client_runtime("alice")

        self.assertEqual(result["synced_count"], 2)
        self.assertEqual(result["error_count"], 0)
        called = [tuple(call.args[0]) for call in run_mock.call_args_list]
        restore_calls = [c for c in called if c[:4] == ("wg", "set", "antizapret", "peer")]
        self.assertEqual(len(restore_calls), 1)
        self.assertIn("k1", restore_calls[0])
        self.assertIn("allowed-ips", restore_calls[0])
        self.assertIn("preshared-key", restore_calls[0])
        self.assertNotIn(("wg-quick", "strip", "antizapret"), [c[:3] for c in called])

    @patch("utils.wg_awg_runtime_enforcer.collect_client_peer_specs", return_value=[])
    @patch("utils.wg_awg_runtime_enforcer.subprocess.run")
    def test_unblock_client_runtime_skips_syncconf_when_strip_fails(self, run_mock, _specs_mock):
        def _run_side_effect(args, **_kwargs):
            if list(args[:3]) == ["wg-quick", "strip", "antizapret"]:
                return SimpleNamespace(returncode=1, stderr="strip failed", stdout="")
            if list(args[:3]) == ["wg-quick", "strip", "vpn"]:
                return SimpleNamespace(returncode=1, stderr="strip failed", stdout="")
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        run_mock.side_effect = _run_side_effect
        result = self.enforcer.unblock_client_runtime("alice")

        self.assertEqual(result["synced_count"], 0)
        self.assertEqual(result["error_count"], 2)
        called = [tuple(call.args[0]) for call in run_mock.call_args_list]
        self.assertTrue(all(args[:2] != ("wg", "syncconf") for args in called))


if __name__ == "__main__":
    unittest.main()
