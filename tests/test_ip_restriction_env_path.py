import os
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from utils.ip_restriction import IPRestriction


class IPRestrictionEnvPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_allowed_ips = os.environ.get("ALLOWED_IPS")

    def tearDown(self) -> None:
        if self._prev_allowed_ips is None:
            os.environ.pop("ALLOWED_IPS", None)
        else:
            os.environ["ALLOWED_IPS"] = self._prev_allowed_ips

    def test_init_app_uses_project_root_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            project_root.mkdir(parents=True, exist_ok=True)

            app = Flask(__name__, root_path=str(project_root))
            restriction = IPRestriction()
            restriction.init_app(app)

            self.assertEqual(restriction._resolve_env_file(), project_root / ".env")

    def test_save_to_env_writes_allowed_ips_to_project_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            project_root.mkdir(parents=True, exist_ok=True)
            parent_env = Path(tmp_dir) / ".env"

            app = Flask(__name__, root_path=str(project_root))
            restriction = IPRestriction()
            restriction.init_app(app)

            restriction.allowed_ips = {"1.1.1.1", "10.0.0.0/24"}
            restriction.enabled = True
            restriction.save_to_env()

            project_env = project_root / ".env"
            self.assertTrue(project_env.exists())
            env_text = project_env.read_text(encoding="utf-8")
            self.assertIn("ALLOWED_IPS=", env_text)
            self.assertIn("1.1.1.1", env_text)
            self.assertIn("10.0.0.0/24", env_text)
            self.assertFalse(parent_env.exists())


if __name__ == "__main__":
    unittest.main()
