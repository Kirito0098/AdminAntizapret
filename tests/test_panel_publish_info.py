import unittest

from core.services.panel_publish_info import build_panel_publish_context


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


if __name__ == "__main__":
    unittest.main()
