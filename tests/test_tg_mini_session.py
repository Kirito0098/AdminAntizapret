import unittest

from flask import Flask

from tg_mini.session import enforce_telegram_mini_session, has_telegram_mini_session


class TelegramMiniSessionTests(unittest.TestCase):
    def test_has_telegram_mini_session_requires_matching_username(self):
        session = {
            "username": "admin",
            "telegram_mini_username": "admin",
            "telegram_mini_auth": True,
        }
        self.assertTrue(has_telegram_mini_session(session))

        mismatched = dict(session)
        mismatched["telegram_mini_username"] = "other"
        self.assertFalse(has_telegram_mini_session(mismatched))

    def test_enforce_telegram_mini_session_api_denied(self):
        app = Flask(__name__)
        with app.app_context():
            denied = enforce_telegram_mini_session({}, api_request=True)
        self.assertIsNotNone(denied)
        response, status = denied
        self.assertEqual(status, 403)
        with app.app_context():
            self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
