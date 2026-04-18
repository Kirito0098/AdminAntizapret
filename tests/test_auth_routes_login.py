import unittest
from io import BytesIO
from typing import Any

from flask import Flask

from routes.auth_routes import register_auth_routes


class FakeUser:
    def __init__(self, username: str, password: str, role: str = "admin", telegram_id: str | None = None):
        self.username = username
        self.role = role
        self._password = password
        self.telegram_id = telegram_id

    def check_password(self, password: str) -> bool:
        return self._password == password


class FakeQuery:
    def __init__(self, users: dict[str, FakeUser]):
        self._users_by_username = users
        self._users_by_telegram = {
            str(user.telegram_id): user for user in users.values() if user.telegram_id
        }
        self._last_filters: dict[str, str] = {}

    def filter_by(self, **kwargs: str) -> "FakeQuery":
        self._last_filters = kwargs
        return self

    def first(self) -> FakeUser | None:
        if "username" in self._last_filters:
            return self._users_by_username.get(self._last_filters["username"])
        if "telegram_id" in self._last_filters:
            return self._users_by_telegram.get(self._last_filters["telegram_id"])
        return None


class FakeUserModel:
    query: FakeQuery


class FakeIpRestriction:
    def is_enabled(self) -> bool:
        return False

    def get_client_ip(self) -> str:
        return "127.0.0.1"

    def is_ip_allowed(self, _: str) -> bool:
        return True


class FakeCaptchaGenerator:
    def generate_captcha(self) -> str:
        return "ABCD"

    def generate_captcha_image(self) -> BytesIO:
        return BytesIO(b"fake-image")


class FakeAuthManager:
    def login_required(self, fn):
        return fn


class FakeDbSession:
    def __init__(self):
        self.rollback_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1


class FakeDb:
    def __init__(self):
        self.session = FakeDbSession()


def build_test_app(remember_days: int | None = None) -> tuple[Flask, list[tuple[str, bool]]]:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["TESTING"] = True
    if remember_days is not None:
        app.config["REMEMBER_ME_DAYS"] = remember_days

    @app.route("/")
    def index():
        return "index"

    @app.route("/tg-mini")
    def tg_mini_app():
        return "tg-mini"

    users = {"admin": FakeUser(username="admin", password="password123", role="admin")}
    FakeUserModel.query = FakeQuery(users)

    touch_calls: list[tuple[str, bool]] = []

    def touch_active_web_session(username: str, force: bool = False) -> None:
        touch_calls.append((username, force))

    register_auth_routes(
        app,
        auth_manager=FakeAuthManager(),
        captcha_generator=FakeCaptchaGenerator(),
        ip_restriction=FakeIpRestriction(),
        limiter=None,
        db=FakeDb(),
        user_model=FakeUserModel,
        touch_active_web_session=touch_active_web_session,
        remove_active_web_session=lambda: None,
        log_telegram_audit_event=lambda *args, **kwargs: None,
    )
    return app, touch_calls


class AuthRoutesLoginTests(unittest.TestCase):
    def test_login_success_without_remember_me(self) -> None:
        app, touch_calls = build_test_app()

        with app.test_client() as client:
            response = client.post(
                "/login",
                data={"username": "admin", "password": "password123"},
            )

            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/"))
            self.assertEqual(touch_calls, [("admin", True)])

            with client.session_transaction() as session_state:
                self.assertEqual(session_state.get("username"), "admin")
                self.assertFalse(session_state.permanent)
                self.assertEqual(session_state.get("attempts"), 0)

    def test_login_success_with_remember_me_uses_config_days(self) -> None:
        app, _ = build_test_app(remember_days=45)

        with app.test_client() as client:
            response = client.post(
                "/login",
                data={"username": "admin", "password": "password123", "remember_me": "on"},
            )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(app.permanent_session_lifetime.days, 45)

            with client.session_transaction() as session_state:
                self.assertTrue(session_state.permanent)

    def test_login_failure_increments_attempts(self) -> None:
        app, _ = build_test_app()

        with app.test_client() as client:
            response = client.post(
                "/login",
                data={"username": "admin", "password": "wrong-password"},
            )

            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/login"))

            with client.session_transaction() as session_state:
                self.assertEqual(session_state.get("attempts"), 1)
                self.assertIsNone(session_state.get("username"))


if __name__ == "__main__":
    unittest.main()
