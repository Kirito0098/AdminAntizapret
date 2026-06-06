from unittest.mock import MagicMock, patch

import urllib.error

from script_sh.safe_browsing_status_cli import fetch_site_status, parse_status_payload


def test_parse_status_payload_extracts_threat_flag():
    raw = (
        ")]}'\n\n"
        '[["sb.ssr",2,false,false,true,false,false,1779153594802,"admin.vpn.claymore-it.ru"]]\n'
    )
    parsed = parse_status_payload(raw)
    assert parsed["site"] == "admin.vpn.claymore-it.ru"
    assert parsed["status_code"] == 2
    assert parsed["threat_flag"] is True


def test_parse_status_payload_for_safe_site():
    raw = (
        ")]}'\n\n"
        '[["sb.ssr",4,false,false,false,false,false,1767633340523,"google.com"]]\n'
    )
    parsed = parse_status_payload(raw)
    assert parsed["site"] == "google.com"
    assert parsed["status_code"] == 4
    assert parsed["threat_flag"] is False


def _http_response(*, status_code: int, body: str) -> MagicMock:
    response = MagicMock()
    response.status = status_code
    response.getcode.return_value = status_code
    response.headers = {}
    response.read.return_value = body.encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_fetch_site_status_retries_and_sets_user_agent():
    success_response = _http_response(
        status_code=200,
        body=(
            ")]}'\n\n"
            '[["sb.ssr",4,false,false,false,false,false,1767633340523,"google.com"]]\n'
        ),
    )

    with patch("script_sh.safe_browsing_status_cli.urllib.request.urlopen") as urlopen:
        urlopen.side_effect = [
            urllib.error.URLError("temporary"),
            success_response,
        ]
        with patch("script_sh.safe_browsing_status_cli.time.sleep") as sleep:
            parsed = fetch_site_status("google.com", retries=2)

    assert parsed["site"] == "google.com"
    assert urlopen.call_count == 2
    sleep.assert_called_once()
    request = urlopen.call_args_list[-1].args[0]
    assert request.get_header("User-agent").startswith("AdminAntizapret-SafeBrowsingMonitor/")


def test_fetch_site_status_rejects_non_200_status():
    error_response = _http_response(status_code=503, body="")

    with patch(
        "script_sh.safe_browsing_status_cli.urllib.request.urlopen",
        return_value=error_response,
    ):
        try:
            fetch_site_status("google.com", retries=1)
        except urllib.error.HTTPError as exc:
            assert exc.code == 503
        else:
            raise AssertionError("Expected HTTPError for non-200 response")
