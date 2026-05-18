"""Тесты предварительной проверки окружения."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from core.services.system_preflight import (
    PreflightContext,
    run_preflight_checks,
)


class SystemPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = self.tmp.name
        self.venv = os.path.join(self.install, "venv")
        os.makedirs(os.path.join(self.venv, "bin"), exist_ok=True)
        os.makedirs(os.path.join(self.install, "instance"), exist_ok=True)
        os.makedirs(os.path.join(self.install, "script_sh"), exist_ok=True)

        for name in (
            "utils",
            "ssl_setup",
            "backup_functions",
            "monitoring",
            "service_functions",
            "uninstall",
            "user_management",
            "unit_tests",
            "site_diagnostics",
            "panel_menus",
        ):
            open(os.path.join(self.install, "script_sh", f"{name}.sh"), "w", encoding="utf-8").close()

        with open(os.path.join(self.install, ".env"), "w", encoding="utf-8") as fh:
            fh.write("SECRET_KEY=secret\nVNSTAT_IFACE=eth0\n")
        with open(os.path.join(self.install, "instance", "users.db"), "wb") as fh:
            fh.write(b"db")
        with open(os.path.join(self.install, "requirements.txt"), "w", encoding="utf-8") as fh:
            fh.write("flask\n")
        with open(os.path.join(self.install, "gunicorn.conf.py"), "w", encoding="utf-8") as fh:
            fh.write("# ok\n")
        with open(os.path.join(self.install, "client.sh"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(os.path.join(self.install, "client.sh"), 0o755)

        gunicorn = os.path.join(self.venv, "bin", "gunicorn")
        with open(gunicorn, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(gunicorn, 0o755)

        self.ctx = PreflightContext(
            install_dir=self.install,
            venv_path=self.venv,
            antizapret_install_dir=os.path.join(self.install, "antizapret"),
        )
        os.makedirs(self.ctx.antizapret_install_dir, exist_ok=True)
        doall = os.path.join(self.ctx.antizapret_install_dir, "doall.sh")
        with open(doall, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(doall, 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_run(self, mapping):
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess:
            key = " ".join(args)
            stdout, stderr, code = mapping.get(key, ("", "", 0))
            return subprocess.CompletedProcess(args, code, stdout, stderr)

        return runner

    @patch("core.services.system_preflight.shutil.which")
    @patch("core.services.system_preflight._dpkg_installed", return_value=True)
    @patch("core.services.system_preflight._dnsutils_installed", return_value=True)
    def test_missing_python_dependency_fails(self, *_mocks):
        which_map = {
            "python3": "/usr/bin/python3",
            "pip3": "/usr/bin/pip3",
            "git": "/usr/bin/git",
            "wget": "/usr/bin/wget",
            "openssl": "/usr/bin/openssl",
            "systemctl": "/usr/bin/systemctl",
            "awk": "/usr/bin/awk",
            "sed": "/usr/bin/sed",
            "grep": "/usr/bin/grep",
            "ss": "/usr/bin/ss",
            "dig": "/usr/bin/dig",
            "iptables": "/usr/sbin/iptables",
            "ipset": "/usr/sbin/ipset",
        }
        _mocks[2].side_effect = lambda name: which_map.get(name)

        pip_bin = os.path.join(self.venv, "bin", "pip")
        with open(pip_bin, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(pip_bin, 0o755)
        py3 = os.path.join(self.venv, "bin", "python3")
        with open(py3, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(py3, 0o755)

        report = run_preflight_checks(
            self.ctx,
            run_cmd=self._fake_run(
                {
                    f"{pip_bin} list --format=freeze": ("otherpkg==1.0\n", "", 0),
                    f"{pip_bin} check": ("", "", 0),
                    "iptables -L INPUT -n": ("", "", 0),
                    "ipset version": ("v7\n", "", 0),
                }
            ),
        )
        dep_fails = [r for r in report.results if r.status == "fail" and "Python" in r.title]
        self.assertTrue(dep_fails)

    @patch("core.services.system_preflight.shutil.which")
    @patch("core.services.system_preflight._dpkg_installed", return_value=True)
    @patch("core.services.system_preflight._dnsutils_installed", return_value=True)
    def test_missing_script_module_fails(self, *_mocks):
        which_map = {
            c: f"/usr/bin/{c}"
            for c in (
                "python3",
                "pip3",
                "git",
                "wget",
                "openssl",
                "systemctl",
                "awk",
                "sed",
                "grep",
                "ss",
                "dig",
                "iptables",
                "ipset",
            )
        }
        _mocks[2].side_effect = lambda name: which_map.get(name)
        os.remove(os.path.join(self.install, "script_sh", "panel_menus.sh"))

        report = run_preflight_checks(
            self.ctx,
            run_cmd=self._fake_run(
                {
                    "iptables -L INPUT -n": ("", "", 0),
                    "ipset version": ("v7\n", "", 0),
                }
            ),
        )
        mod_fails = [r for r in report.results if "script_sh" in r.title and r.status == "fail"]
        self.assertEqual(len(mod_fails), 1)

    @patch("core.services.system_preflight.shutil.which")
    @patch("core.services.system_preflight._dpkg_installed", return_value=True)
    @patch("core.services.system_preflight._dnsutils_installed", return_value=True)
    def test_missing_iptables_warns(self, *_mocks):
        which_map = {c: f"/usr/bin/{c}" for c in ("python3", "pip3", "git", "wget", "openssl", "systemctl", "awk", "sed", "grep", "ss", "dig")}
        _mocks[2].side_effect = lambda name: which_map.get(name)

        report = run_preflight_checks(self.ctx, run_cmd=self._fake_run({}))
        fw_warns = [r for r in report.results if "iptables" in r.title.lower() and r.status == "warn"]
        self.assertEqual(len(fw_warns), 1)
        self.assertIn("iptables", fw_warns[0].detail)
