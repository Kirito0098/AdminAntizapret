import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.openvpn_socket_reader import OpenVPNSocketReaderService
from utils.openvpn_status_source import read_openvpn_status_source
from utils.traffic_sync import build_session_key, parse_status_from_source, parse_status_log

STATUS3_SAMPLE = """\
TITLE\tOpenVPN 2.6.12
TIME\t2026-06-09 12:00:00\t1749470400
HEADER\tCLIENT_LIST\tCommon Name\tReal Address\tVirtual Address\tVirtual IPv6 Address\tBytes Received\tBytes Sent\tConnected Since\tConnected Since (time_t)\tUsername\tClient ID\tPeer ID\tData Channel Cipher
CLIENT_LIST\talice\t1.2.3.4:12345\t10.8.0.2\t\t1024\t2048\t2026-06-09 11:00:00\t1749466800\tUNDEF\t1\t0\tAES-256-GCM
END
"""

CSV_SAMPLE = """\
TITLE,OpenVPN 2.6.12
TIME,2026-06-09 12:00:00,1749470400
CLIENT_LIST,alice,1.2.3.4:12345,10.8.0.2,,1024,2048,2026-06-09 11:00:00,1749466800,UNDEF,1,0,AES-256-GCM
END
"""


@pytest.fixture(autouse=True)
def reset_reader_singleton():
    import utils.openvpn_status_source as mod

    mod._reader = None
    yield
    mod._reader = None


def test_parse_status_from_source_status3_format():
    source = {
        "raw": STATUS3_SAMPLE,
        "source_name": "antizapret-tcp.sock",
        "updated_at_ts": 1749470400,
        "source_type": "socket",
    }
    row = parse_status_from_source("antizapret-tcp", "/tmp/antizapret-tcp-status.log", source)
    assert row["exists"] is True
    assert row["client_count"] == 1
    client = row["clients"][0]
    assert client["common_name"] == "alice"
    assert client["bytes_received"] == 1024
    assert client["bytes_sent"] == 2048
    assert client["connected_since_ts"] == 1749466800


def test_session_key_stable_across_file_and_socket_formats():
    file_source = {"raw": CSV_SAMPLE, "source_name": "vpn-tcp-status.log", "updated_at_ts": 1}
    socket_source = {"raw": STATUS3_SAMPLE, "source_name": "vpn-tcp.sock", "updated_at_ts": 2}

    file_row = parse_status_from_source("vpn-tcp", "/tmp/vpn-tcp-status.log", file_source)
    socket_row = parse_status_from_source("vpn-tcp", "/tmp/vpn-tcp-status.log", socket_source)

    file_key = build_session_key("vpn-tcp", file_row["clients"][0])
    socket_key = build_session_key("vpn-tcp", socket_row["clients"][0])
    assert file_key == socket_key


def test_socket_reader_fallback_to_file(tmp_path):
    status_file = tmp_path / "antizapret-tcp-status.log"
    status_file.write_text(CSV_SAMPLE, encoding="utf-8")

    reader = OpenVPNSocketReaderService(
        openvpn_socket_dir=str(tmp_path),
        openvpn_socket_timeout=0.5,
        openvpn_socket_idle_timeout=0.05,
        openvpn_log_tail_lines=0,
        openvpn_event_max_response_bytes=0,
    )

    with patch.object(reader, "query_openvpn_management_socket", return_value=""):
        source = reader.read_status_source("antizapret-tcp", str(status_file))

    assert source["source_type"] == "file"
    assert source["exists"] is True
    assert "CLIENT_LIST" in source["raw"]


def test_socket_reader_no_fallback_when_file_has_no_clients(tmp_path):
    status_file = tmp_path / "antizapret-tcp-status.log"
    status_file.write_text("TITLE,OpenVPN\nEND\n", encoding="utf-8")

    reader = OpenVPNSocketReaderService(
        openvpn_socket_dir=str(tmp_path),
        openvpn_socket_timeout=0.5,
        openvpn_socket_idle_timeout=0.05,
        openvpn_log_tail_lines=0,
        openvpn_event_max_response_bytes=0,
    )

    with patch.object(reader, "query_openvpn_management_socket", return_value=""):
        source = reader.read_status_source("antizapret-tcp", str(status_file))

    assert source["source_type"] == "socket"
    assert source["exists"] is False
    assert source["raw"] == ""


def test_read_openvpn_status_source_file_mode_skips_socket(tmp_path):
    status_file = tmp_path / "vpn-udp-status.log"
    status_file.write_text(CSV_SAMPLE, encoding="utf-8")

    with patch.dict(os.environ, {"TRAFFIC_SYNC_OPENVPN_SOURCE": "file"}, clear=False):
        with patch("utils.openvpn_status_source._get_reader") as get_reader:
            source = read_openvpn_status_source("vpn-udp", str(status_file))

    get_reader.assert_not_called()
    assert source["source_type"] == "file"
    assert source["exists"] is True
    assert "alice" in source["raw"]


def test_read_openvpn_status_source_socket_success():
    reader = MagicMock()
    reader.read_status_source.return_value = {
        "raw": STATUS3_SAMPLE,
        "source_name": "antizapret-udp.sock",
        "exists": True,
        "updated_at_ts": 1,
        "source_type": "socket",
    }

    with patch.dict(os.environ, {"TRAFFIC_SYNC_OPENVPN_SOURCE": "socket"}, clear=False):
        with patch("utils.openvpn_status_source._get_reader", return_value=reader):
            source = read_openvpn_status_source("antizapret-udp", "/tmp/antizapret-udp-status.log")

    reader.read_status_source.assert_called_once_with("antizapret-udp", "/tmp/antizapret-udp-status.log")
    assert source["source_type"] == "socket"


def test_parse_status_log_empty_socket_and_empty_file(tmp_path):
    status_file = tmp_path / "vpn-tcp-status.log"
    status_file.write_text("", encoding="utf-8")

    reader = MagicMock()
    reader.read_status_source.return_value = {
        "raw": "",
        "source_name": "vpn-tcp.sock",
        "exists": False,
        "updated_at_ts": 0,
        "source_type": "socket",
    }

    with patch("utils.openvpn_status_source._get_reader", return_value=reader):
        row = parse_status_log("vpn-tcp", str(status_file))

    assert row["exists"] is False
    assert row["client_count"] == 0
    assert row["clients"] == []


def test_traffic_sync_does_not_import_flask():
    loaded = set(sys.modules)
    import utils.traffic_sync  # noqa: F401

    new_modules = set(sys.modules) - loaded
    forbidden = {name for name in new_modules if name == "app" or name.startswith("flask")}
    assert not forbidden
