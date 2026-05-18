"""iptables whitelist для порта панели."""

import tempfile
import unittest
from unittest.mock import patch

from utils.panel_port_firewall import (
    CHAIN_V4,
    COMMENT_JUMP_V4,
    IPSET_ALLOW_V4,
    PanelPortFirewall,
)


class PanelPortFirewallTests(unittest.TestCase):
    def test_sync_dry_run_accepts_entries(self) -> None:
        fw = PanelPortFirewall(firewall_enabled=True, dry_run=True)
        self.assertTrue(fw.sync(["10.0.0.1", "192.168.0.0/24"], port=5050))
        self.assertEqual(fw._active_port, 5050)

    def test_disable_dry_run(self) -> None:
        fw = PanelPortFirewall(dry_run=True)
        fw.sync(["10.0.0.1"], port=5050)
        self.assertTrue(fw.disable())

    @patch.object(PanelPortFirewall, "_run_command", return_value=(True, ""))
    def test_sync_calls_ipset_and_jump(self, run_mock) -> None:
        fw = PanelPortFirewall(firewall_enabled=True, dry_run=False)
        self.assertTrue(fw.sync(["203.0.113.10", "10.0.0.0/8"], port=5050))

        args_list = [call.args[0] for call in run_mock.call_args_list]
        joined = [" ".join(args) for args in args_list]
        self.assertTrue(any("ipset" in line and IPSET_ALLOW_V4 in line for line in joined))
        self.assertTrue(any(CHAIN_V4 in line for line in joined))
        self.assertTrue(any(COMMENT_JUMP_V4 in line for line in joined))
        self.assertTrue(any("--dport" in line and "5050" in line for line in joined))

    def test_ipv6_entries_ignored(self) -> None:
        fw = PanelPortFirewall(dry_run=True)
        entries = fw._ipv4_entries(["10.0.0.1", "2001:db8::1"])
        self.assertEqual(entries, ["10.0.0.1/32"])

    @patch.object(PanelPortFirewall, "_run_command", return_value=(True, ""))
    def test_sync_does_not_create_ipv6_chain(self, run_mock) -> None:
        fw = PanelPortFirewall(firewall_enabled=True, dry_run=False)
        fw.sync(["10.0.0.1", "2001:db8::1"], port=5050)
        args_list = [call.args[0] for call in run_mock.call_args_list]
        joined = [" ".join(args) for args in args_list]
        self.assertFalse(any("ip6tables" in line and " -N " in line for line in joined))
        self.assertFalse(any("aa-panel-port-jump-v6" in line for line in joined))


if __name__ == "__main__":
    unittest.main()
