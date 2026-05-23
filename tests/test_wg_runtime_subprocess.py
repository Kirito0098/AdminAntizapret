import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils.wg_runtime_subprocess import apply_wg_client_runtime, trigger_wg_policy_sync_background


class WgRuntimeSubprocessTests(unittest.TestCase):
    @patch("utils.wg_runtime_subprocess.subprocess.run")
    def test_apply_wg_client_runtime_unblock_parses_json(self, run_mock):
        run_mock.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"synced_count": 2, "error_count": 0, "errors": []}),
            stderr="",
        )
        result = apply_wg_client_runtime("Test", is_blocked=False, timeout_seconds=15)

        self.assertEqual(result["synced_count"], 2)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[-1], "unblock")
        self.assertIn("--client", command)
        self.assertIn("--action", command)

    @patch("utils.wg_runtime_subprocess.subprocess.run")
    def test_apply_wg_client_runtime_block_action(self, run_mock):
        run_mock.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"removed_count": 1, "error_count": 0, "errors": []}),
            stderr="",
        )
        apply_wg_client_runtime("alice", is_blocked=True)

        command = run_mock.call_args.args[0]
        self.assertEqual(command[-1], "block")

    @patch("utils.wg_runtime_subprocess.subprocess.run")
    def test_apply_wg_client_runtime_raises_on_fatal_exit(self, run_mock):
        run_mock.return_value = SimpleNamespace(
            returncode=2,
            stdout=json.dumps({"error": "import failed"}),
            stderr="",
        )
        with self.assertRaises(RuntimeError):
            apply_wg_client_runtime("alice", is_blocked=False)

    @patch("utils.wg_runtime_subprocess.subprocess.run")
    def test_apply_wg_client_runtime_returns_payload_with_runtime_errors(self, run_mock):
        run_mock.return_value = SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"synced_count": 0, "error_count": 1, "errors": [{"interface": "vpn"}]}),
            stderr="",
        )
        result = apply_wg_client_runtime("alice", is_blocked=False)

        self.assertEqual(result["error_count"], 1)

    @patch("utils.wg_runtime_subprocess.subprocess.Popen")
    def test_trigger_wg_policy_sync_background_starts_process(self, popen_mock):
        popen_mock.return_value = SimpleNamespace(pid=12345)
        process = trigger_wg_policy_sync_background()

        self.assertIsNotNone(process)
        command = popen_mock.call_args.args[0]
        self.assertTrue(command[-1].endswith("wg_awg_policy_sync.py"))
        self.assertEqual(os.path.basename(command[-1]), "wg_awg_policy_sync.py")


if __name__ == "__main__":
    unittest.main()
