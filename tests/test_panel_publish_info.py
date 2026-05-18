import unittest

from core.services.panel_publish_info import (
    build_panel_publish_context,
    is_whitelist_port_firewall_applicable,
    resolve_panel_publish_mode,
)


class PanelPublishInfoTests(unittest.TestCase):
    def test_reverse_proxy_with_domain(self):
        env = {
            "BIND": "127.0.0.1",
            "APP_PORT": "5050",
            "USE_HTTPS": "false",
            "DOMAIN": "panel.example.com",
            "SESSION_COOKIE_SECURE": "true",
            "TRUSTED_PROXY_IPS": "127.0.0.1,::1",
            "SSL_CERT": "",
            "SSL_KEY": "",
        }

        def get_env_value(key, default=""):
            return env.get(key, default)

        ctx = build_panel_publish_context(
            get_env_value=get_env_value,
            url_root="https://panel.example.com/settings",
        )
        self.assertEqual(ctx["mode_key"], "reverse_proxy")
        self.assertEqual(len(ctx["primary_urls"]), 1)
        self.assertEqual(ctx["primary_urls"][0]["url"], "https://panel.example.com/")

    def test_app_https_gunicorn(self):
        env = {
            "BIND": "0.0.0.0",
            "APP_PORT": "8443",
            "USE_HTTPS": "true",
            "DOMAIN": "",
            "SESSION_COOKIE_SECURE": "true",
            "TRUSTED_PROXY_IPS": "",
            "SSL_CERT": "/etc/ssl/fullchain.pem",
            "SSL_KEY": "/etc/ssl/privkey.pem",
        }

        def get_env_value(key, default=""):
            return env.get(key, default)

        ctx = build_panel_publish_context(
            get_env_value=get_env_value,
            url_root="https://10.0.0.1:8443/",
        )
        self.assertEqual(ctx["mode_key"], "app_https")
        self.assertIn("https://10.0.0.1:8443/", ctx["primary_urls"][0]["url"])

    def test_direct_http(self):
        env = {
            "BIND": "0.0.0.0",
            "APP_PORT": "5050",
            "USE_HTTPS": "false",
            "DOMAIN": "",
            "SESSION_COOKIE_SECURE": "false",
            "TRUSTED_PROXY_IPS": "",
            "SSL_CERT": "",
            "SSL_KEY": "",
        }

        def get_env_value(key, default=""):
            return env.get(key, default)

        ctx = build_panel_publish_context(
            get_env_value=get_env_value,
            url_root="http://192.0.2.1:5050/",
        )
        self.assertEqual(ctx["mode_key"], "direct_http")
        self.assertEqual(ctx["internal_url"], "http://0.0.0.0:5050/")

    def test_whitelist_firewall_applicable_without_nginx(self) -> None:
        self.assertTrue(
            is_whitelist_port_firewall_applicable(
                get_env_value=lambda k, d="": {
                    "BIND": "0.0.0.0",
                    "USE_HTTPS": "false",
                    "SSL_CERT": "",
                    "SSL_KEY": "",
                }.get(k, d)
            )
        )
        self.assertTrue(
            is_whitelist_port_firewall_applicable(
                get_env_value=lambda k, d="": {
                    "BIND": "0.0.0.0",
                    "USE_HTTPS": "true",
                    "SSL_CERT": "/c.pem",
                    "SSL_KEY": "/k.pem",
                }.get(k, d)
            )
        )
        self.assertTrue(
            is_whitelist_port_firewall_applicable(
                get_env_value=lambda k, d="": {
                    "BIND": "0.0.0.0",
                    "USE_HTTPS": "true",
                    "SSL_CERT": "",
                    "SSL_KEY": "",
                }.get(k, d)
            )
        )
        self.assertFalse(
            is_whitelist_port_firewall_applicable(
                get_env_value=lambda k, d="": {
                    "BIND": "127.0.0.1",
                    "USE_HTTPS": "false",
                }.get(k, d)
            )
        )
        self.assertFalse(
            is_whitelist_port_firewall_applicable(
                get_env_value=lambda k, d="": {
                    "BIND": "127.0.0.1",
                    "USE_HTTPS": "true",
                    "SSL_CERT": "/c.pem",
                    "SSL_KEY": "/k.pem",
                }.get(k, d)
            )
        )

    def test_resolve_panel_publish_mode(self) -> None:
        self.assertEqual(
            resolve_panel_publish_mode(bind="0.0.0.0", use_https=False),
            "direct_http",
        )
        self.assertEqual(
            resolve_panel_publish_mode(bind="127.0.0.1", use_https=False),
            "reverse_proxy",
        )
        self.assertEqual(
            resolve_panel_publish_mode(
                bind="0.0.0.0",
                use_https=True,
                ssl_cert="/c.pem",
                ssl_key="/k.pem",
            ),
            "app_https",
        )


if __name__ == "__main__":
    unittest.main()
