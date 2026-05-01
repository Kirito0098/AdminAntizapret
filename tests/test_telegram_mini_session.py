import unittest

from flask import Flask

from core.services.telegram_mini_session import enforce_telegram_mini_session, has_telegram_mini_session


class TelegramMiniSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)

        @self.app.route("/tg-mini/open")
        def tg_mini_open():
            return "mini-open"

    def test_has_telegram_mini_session_true_when_usernames_match(self) -> None:
        session_state = {
            "telegram_mini_auth": True,
            "telegram_mini_username": "admin",
            "username": "admin",
        }
        self.assertTrue(has_telegram_mini_session(session_state))

    def test_enforce_telegram_mini_session_api_mode_denies_without_session(self) -> None:
        with self.app.test_request_context("/api/tg-mini/dashboard"):
            denied = enforce_telegram_mini_session({}, api_request=True)

        self.assertIsNotNone(denied)
        response, status_code = denied
        self.assertEqual(status_code, 403)
        self.assertIn("Mini App API", response.get_json().get("message", ""))

    def test_enforce_telegram_mini_session_web_mode_redirects_without_session(self) -> None:
        with self.app.test_request_context("/tg-mini"):
            denied = enforce_telegram_mini_session({}, api_request=False, redirect_endpoint="tg_mini_open")

        self.assertIsNotNone(denied)
        self.assertEqual(denied.status_code, 302)
        self.assertTrue(denied.location.endswith("/tg-mini/open"))


if __name__ == "__main__":
    unittest.main()
