"""Тесты диагностики запуска сайта."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import core.services.site_diagnostics as site_diagnostics
from core.services.site_diagnostics import (
    CheckResult,
    DiagnosticsContext,
    decode_journal_line,
    run_site_diagnostics,
)


class DecodeJournalLineTests(unittest.TestCase):
    def test_address_already_in_use(self):
        line = "Error: [Errno 98] Address already in use"
        hint = decode_journal_line(line, app_port="5050")
        self.assertIsNotNone(hint)
        self.assertIn("5050", hint)

    def test_import_error(self):
        hint = decode_journal_line("ModuleNotFoundError: No module named 'flask'")
        self.assertIsNotNone(hint)
        self.assertIn("pip install", hint)

    def test_unknown_line_returns_none(self):
        self.assertIsNone(decode_journal_line("Started gunicorn normally"))

    def test_status_203_exec(self):
        hint = decode_journal_line("Main process exited, status=203/EXEC")
        self.assertIsNotNone(hint)
        self.assertIn("gunicorn", hint.lower())


class RunSiteDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install_dir = self.tmp.name
        self.ctx = DiagnosticsContext(
            install_dir=self.install_dir,
            service_name="admin-antizapret-test",
            venv_path=os.path.join(self.install_dir, "venv"),
        )
        os.makedirs(os.path.join(self.install_dir, "instance"), exist_ok=True)
        os.makedirs(os.path.join(self.ctx.resolved_venv(), "bin"), exist_ok=True)

        with open(os.path.join(self.install_dir, ".env"), "w", encoding="utf-8") as fh:
            fh.write("SECRET_KEY=abc\nAPP_PORT=5050\nBIND=127.0.0.1\n")

        gunicorn = os.path.join(self.ctx.resolved_venv(), "bin", "gunicorn")
        with open(gunicorn, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(gunicorn, 0o755)

        with open(os.path.join(self.install_dir, "gunicorn.conf.py"), "w", encoding="utf-8") as fh:
            fh.write("# test config\n")

        db_path = os.path.join(self.install_dir, "instance", "users.db")
        with open(db_path, "wb") as fh:
            fh.write(b"sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_run(self, mapping):
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess:
            key = " ".join(args)
            stdout, stderr, code = mapping.get(key, ("", "", 1))
            return subprocess.CompletedProcess(args, code, stdout, stderr)

        return runner

    def test_missing_unit_reports_fail(self):
        real_isfile = site_diagnostics.os.path.isfile

        def isfile(path: str) -> bool:
            if path.endswith(".service"):
                return False
            return real_isfile(path)

        with patch.object(site_diagnostics.os.path, "isfile", side_effect=isfile):
            report = run_site_diagnostics(
                self.ctx,
                run_cmd=self._fake_run(
                    {
                        f"systemctl is-enabled {self.ctx.service_name}": ("enabled", "", 0),
                        f"systemctl is-active {self.ctx.service_name}": ("inactive", "", 3),
                    }
                ),
            )
        titles = [r.title for r in report.results]
        self.assertTrue(any("не найден" in t for t in titles))
        self.assertTrue(report.has_failures())

    def test_active_service_and_files_ok(self):
        unit_path = f"/etc/systemd/system/{self.ctx.service_name}.service"
        real_isfile = site_diagnostics.os.path.isfile

        def isfile(path: str) -> bool:
            if path == unit_path:
                return True
            return real_isfile(path)

        with patch.object(site_diagnostics.os.path, "isfile", side_effect=isfile):
            report = run_site_diagnostics(
                self.ctx,
                run_cmd=self._fake_run(
                    {
                        f"systemctl is-enabled {self.ctx.service_name}": ("enabled", "", 0),
                        f"systemctl is-active {self.ctx.service_name}": ("active\n", "", 0),
                        f"journalctl -u {self.ctx.service_name} -n 30 --no-pager -o cat": (
                            "Listening at http://127.0.0.1:5050\n",
                            "",
                            0,
                        ),
                        "ss -tlnp": (
                            "LISTEN 0 128 127.0.0.1:5050 0.0.0.0:* users:((\"gunicorn\",pid=1))\n",
                            "",
                            0,
                        ),
                        "curl -sf --max-time 3 http://127.0.0.1:5050/": ("", "", 0),
                    }
                ),
            )

        self.assertGreater(report.ok_count, 0)
        self.assertFalse(
            any(r.status == "fail" and "users.db" in r.title for r in report.results)
        )

    def test_https_missing_certificates(self):
        with open(os.path.join(self.install_dir, ".env"), "a", encoding="utf-8") as fh:
            fh.write("USE_HTTPS=true\nSSL_CERT=/missing/cert.pem\nSSL_KEY=/missing/key.pem\n")

        unit_path = f"/etc/systemd/system/{self.ctx.service_name}.service"
        real_isfile = site_diagnostics.os.path.isfile

        def isfile(path: str) -> bool:
            if path in ("/missing/cert.pem", "/missing/key.pem"):
                return False
            if path == unit_path:
                return True
            return real_isfile(path)

        with patch.object(site_diagnostics.os.path, "isfile", side_effect=isfile):
            report = run_site_diagnostics(
                self.ctx,
                run_cmd=self._fake_run(
                    {
                        f"systemctl is-enabled {self.ctx.service_name}": ("enabled", "", 0),
                        f"systemctl is-active {self.ctx.service_name}": ("active", "", 0),
                        f"journalctl -u {self.ctx.service_name} -n 30 --no-pager -o cat": ("", "", 0),
                        "ss -tlnp": ("", "", 0),
                    }
                ),
            )

        https_fails = [
            r
            for r in report.results
            if r.status == "fail" and "HTTPS" in r.title
        ]
        self.assertEqual(len(https_fails), 1)

    def test_format_check_result_fields(self):
        item = CheckResult("warn", "Тест", detail="деталь", hint_ru="подсказка")
        self.assertEqual(item.status, "warn")
        self.assertEqual(item.detail, "деталь")
