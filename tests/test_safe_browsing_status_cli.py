from script_sh.safe_browsing_status_cli import parse_status_payload


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
