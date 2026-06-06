import os
import unittest
from unittest.mock import patch

from core.services.script_executor import ScriptExecutor


class ScriptExecutorTests(unittest.TestCase):
    def test_run_bash_script_uses_client_sh_cwd(self):
        executor = ScriptExecutor(client_sh_cwd="/custom/antizapret")
        with patch("core.services.script_executor.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "ok"
            run_mock.return_value.stderr = ""
            executor.run_bash_script("1", "client-a", "365")
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.kwargs["cwd"], "/custom/antizapret")
        self.assertEqual(run_mock.call_args.args[0], ["./client.sh", "1", "client-a", "365"])

    def test_default_cwd_from_env(self):
        with patch.dict(os.environ, {"ANTIZAPRET_INSTALL_DIR": "/env/az"}, clear=False):
            executor = ScriptExecutor()
        self.assertEqual(executor.client_sh_cwd, os.path.abspath("/env/az"))


if __name__ == "__main__":
    unittest.main()
