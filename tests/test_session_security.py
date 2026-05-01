import unittest

from core.services.session_security import build_session_security_config


class SessionSecurityConfigTests(unittest.TestCase):
    def test_default_without_https_uses_insecure_cookie(self) -> None:
        config = build_session_security_config({})

        self.assertFalse(config["SESSION_COOKIE_SECURE"])
        self.assertFalse(config["REMEMBER_COOKIE_SECURE"])
        self.assertEqual(config["REMEMBER_COOKIE_SAMESITE"], "Lax")
        self.assertEqual(config["SESSION_COOKIE_PATH"], "/")
        self.assertFalse(config["SESSION_REFRESH_EACH_REQUEST"])
        self.assertFalse(config["WTF_CSRF_SSL_STRICT"])
        self.assertEqual(config["SESSION_COOKIE_SAMESITE"], "Lax")

    def test_use_https_enables_secure_cookie(self) -> None:
        config = build_session_security_config({"USE_HTTPS": "true"})

        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertTrue(config["REMEMBER_COOKIE_SECURE"])
        self.assertTrue(config["WTF_CSRF_SSL_STRICT"])

    def test_ssl_material_enables_secure_cookie(self) -> None:
        config = build_session_security_config(
            {
                "SSL_CERT": "/etc/ssl/certs/panel.crt",
                "SSL_KEY": "/etc/ssl/private/panel.key",
            }
        )

        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertTrue(config["REMEMBER_COOKIE_SECURE"])

    def test_development_default_allows_insecure_cookie(self) -> None:
        config = build_session_security_config({"APP_ENV": "development"})

        self.assertFalse(config["SESSION_COOKIE_SECURE"])
        self.assertFalse(config["REMEMBER_COOKIE_SECURE"])

    def test_samesite_none_falls_back_to_lax_without_secure(self) -> None:
        config = build_session_security_config(
            {
                "APP_ENV": "development",
                "SESSION_COOKIE_SECURE": "false",
                "SESSION_COOKIE_SAMESITE": "None",
            }
        )

        self.assertFalse(config["SESSION_COOKIE_SECURE"])
        self.assertEqual(config["SESSION_COOKIE_SAMESITE"], "Lax")

    def test_remember_me_and_session_lifetime_are_clamped(self) -> None:
        config = build_session_security_config(
            {
                "REMEMBER_ME_DAYS": "999",
                "PERMANENT_SESSION_LIFETIME_DAYS": "0",
            }
        )

        self.assertEqual(config["REMEMBER_ME_DAYS"], 365)
        self.assertEqual(config["REMEMBER_COOKIE_DURATION"].days, 365)
        self.assertEqual(config["PERMANENT_SESSION_LIFETIME"].days, 1)


if __name__ == "__main__":
    unittest.main()
