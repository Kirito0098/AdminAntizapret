from unittest.mock import MagicMock, patch

from utils.traffic_sync import (
    _traffic_limit_reconcile_enabled,
    run_sync,
    run_traffic_limit_reconcile,
)


def test_traffic_limit_reconcile_enabled_by_default():
    with patch.dict("os.environ", {}, clear=True):
        assert _traffic_limit_reconcile_enabled() is True


def test_traffic_limit_reconcile_disabled_by_env():
    with patch.dict("os.environ", {"TRAFFIC_LIMIT_RECONCILE_AFTER_SYNC": "false"}, clear=True):
        assert _traffic_limit_reconcile_enabled() is False


def test_traffic_limit_reconcile_skipped_with_cli_flag():
    assert _traffic_limit_reconcile_enabled(cli_skip=True) is False
    result = run_traffic_limit_reconcile(skip=True)
    assert result == {"traffic_limit_reconcile": "skipped"}


def test_run_traffic_limit_reconcile_success():
    reconcile_mock = MagicMock()
    with patch("utils.traffic_limit_reconcile.reconcile_traffic_limit_policies", reconcile_mock):
        result = run_traffic_limit_reconcile()
    assert result == {"traffic_limit_reconcile": "ok"}
    reconcile_mock.assert_called_once_with()


def test_run_traffic_limit_reconcile_error_is_non_fatal():
    with patch(
        "utils.traffic_limit_reconcile.reconcile_traffic_limit_policies",
        side_effect=RuntimeError("boom"),
    ):
        result = run_traffic_limit_reconcile()
    assert result["traffic_limit_reconcile"] == "error"
    assert "boom" in result["traffic_limit_reconcile_error"]


def test_run_sync_no_reconcile_skips_hook():
    fake_conn = MagicMock()
    with patch("utils.traffic_sync.resolve_db_path", return_value=MagicMock(exists=lambda: True)):
        with patch("utils.traffic_sync.connect_db", return_value=fake_conn):
            with patch("utils.traffic_sync.collect_status_rows_for_snapshot", return_value=[]):
                with patch(
                    "utils.traffic_sync.persist_traffic_snapshot",
                    return_value={"status_rows": 0},
                ):
                    with patch("utils.traffic_sync.run_traffic_limit_reconcile") as reconcile:
                        exit_code = run_sync(["--json", "--no-reconcile"])
    assert exit_code == 0
    reconcile.assert_called_once_with(skip=True)
