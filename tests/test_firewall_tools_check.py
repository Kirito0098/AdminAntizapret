"""Тесты проверки iptables/ipset."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from core.services.firewall_tools_check import (
    apt_install_hint,
    check_firewall_tools,
    missing_firewall_commands,
    probe_firewall_tools,
)


class FirewallToolsCheckTests(unittest.TestCase):
    def test_missing_commands(self):
        with patch(
            "core.services.firewall_tools_check.shutil.which",
            side_effect=lambda name: None if name in ("iptables", "ipset") else "/usr/bin/" + name,
        ):
            self.assertEqual(missing_firewall_commands(), ["iptables", "ipset"])

    def test_probe_ok(self):
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess:
            key = " ".join(args)
            if key == "iptables -L INPUT -n":
                return subprocess.CompletedProcess(args, 0, "", "")
            if key == "ipset version":
                return subprocess.CompletedProcess(args, 0, "ipset v7.0", "")
            return subprocess.CompletedProcess(args, 1, "", "fail")

        with patch(
            "core.services.firewall_tools_check.shutil.which",
            return_value="/usr/bin/x",
        ):
            ok, detail = probe_firewall_tools(run_cmd=runner)
        self.assertTrue(ok)
        self.assertIn("отвечают", detail)

    def test_probe_iptables_fails(self):
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args, 1, "", "Permission denied")

        with patch(
            "core.services.firewall_tools_check.shutil.which",
            return_value="/usr/bin/x",
        ):
            ok, detail = probe_firewall_tools(run_cmd=runner)
        self.assertFalse(ok)
        self.assertIn("iptables", detail)

    def test_check_fully_ready(self):
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess:
            if args[:2] == ["dpkg", "-s"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[0] == "iptables":
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[0] == "ipset":
                return subprocess.CompletedProcess(args, 0, "v7", "")
            return subprocess.CompletedProcess(args, 1, "", "")

        with patch(
            "core.services.firewall_tools_check.shutil.which",
            side_effect=lambda name: f"/usr/bin/{name}",
        ):
            status = check_firewall_tools(run_cmd=runner)
        self.assertTrue(status.fully_ready)

    def test_apt_install_hint(self):
        self.assertEqual(apt_install_hint(["iptables"]), "apt install -y iptables")
        self.assertIn("ipset", apt_install_hint(()))
