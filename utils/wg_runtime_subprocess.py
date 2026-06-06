import json
import os
import subprocess
import sys
from subprocess import TimeoutExpired


def _app_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _runtime_apply_script_path():
    return os.path.join(_app_root(), "utils", "wg_awg_runtime_apply.py")


def _policy_sync_script_path():
    return os.path.join(_app_root(), "utils", "wg_awg_policy_sync.py")


def apply_wg_client_runtime(client_name, *, is_blocked, timeout_seconds=60):
    normalized = (client_name or "").strip()
    if not normalized:
        raise ValueError("Некорректное имя клиента")

    action = "block" if is_blocked else "unblock"
    command = [
        sys.executable,
        _runtime_apply_script_path(),
        "--client",
        normalized,
        "--action",
        action,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(10, int(timeout_seconds or 60)),
            cwd=_app_root(),
        )
    except TimeoutExpired as exc:
        raise RuntimeError(
            f"Превышено время ожидания применения WG/AWG ({exc.timeout}s) для клиента {normalized}"
        ) from exc
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    payload = None
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            payload = None

    if result.returncode == 2 or payload is None:
        message = stderr or stdout or f"WG runtime apply failed with exit code {result.returncode}"
        if isinstance(payload, dict) and payload.get("error"):
            message = str(payload.get("error"))
        raise RuntimeError(message)

    if not isinstance(payload, dict):
        raise RuntimeError("WG runtime apply returned invalid payload")

    return payload


def trigger_wg_policy_sync_background():
    enabled = (os.getenv("WG_POLICY_SYNC_ENABLED", "true") or "true").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return None
    script_path = _policy_sync_script_path()
    if not os.path.isfile(script_path):
        return None
    return subprocess.Popen(
        [sys.executable, script_path],
        cwd=_app_root(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
