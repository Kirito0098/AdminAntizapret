from core.services.http_security import (
    apply_security_headers,
    build_robots_txt,
    build_security_txt,
    get_panel_branding,
    should_noindex_path,
)


def test_should_noindex_sensitive_paths():
    assert should_noindex_path("/login")
    assert should_noindex_path("/qr_download/abc")
    assert should_noindex_path("/public_download/ips")
    assert not should_noindex_path("/")


def test_apply_security_headers_sets_csp_and_noindex_for_login():
    class Response:
        headers = {}

        def headers_set(self, k, v):
            self.headers[k] = v

    response = type("R", (), {"headers": {}})()

    class H(dict):
        def setdefault(self, k, v):
            if k not in self:
                self[k] = v
            return self[k]

    response.headers = H()
    apply_security_headers(response, "/login")
    assert "Content-Security-Policy" in response.headers
    assert response.headers.get("X-Robots-Tag") == "noindex, nofollow, noarchive"


def test_build_robots_txt_blocks_download_paths():
    body = build_robots_txt()
    assert "Disallow: /login" in body
    assert "Disallow: /qr_download/" in body
    assert "Disallow: /download/" in body
    assert "Disallow: /ip-blocked" in body


def test_build_security_txt_has_no_vpn_wording():
    body = build_security_txt({"panel_base_url": "https://panel.example.com"})
    assert "VPN" not in body
    assert "vpn" not in body
    assert "Private administration panel" in body
    assert "https://panel.example.com" in body


def test_get_panel_branding_uses_domain_only():
    branding = get_panel_branding(
        {
            "DOMAIN": "admin.example.com",
            "PANEL_BRAND_NAME": "",
        }
    )
    assert branding["panel_brand_name"] == "Admin Panel"
    assert branding["panel_host"] == "admin.example.com"
    assert branding["panel_base_url"] == "https://admin.example.com"
