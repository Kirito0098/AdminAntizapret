import unittest
from dataclasses import dataclass
from typing import Any

from flask import Flask, jsonify

from routes.admin_routes import register_admin_routes


class FakeAuthManager:
    def admin_required(self, fn):
        return fn

    def login_required(self, fn):
        return fn


@dataclass
class FakeTask:
    id: str
    task_type: str
    status: str
    message: str = "queued"
    error: str | None = None
    finished_at: Any = None


class FakeSessionDb:
    def __init__(self):
        self.storage: dict[str, Any] = {}

    def get(self, _model, key: str):
        return self.storage.get(str(key))

    def commit(self) -> None:
        return None


class FakeDb:
    def __init__(self):
        self.session = FakeSessionDb()


class FakeViewerAccessQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return []

    def delete(self, synchronize_session: bool = False):
        _ = synchronize_session
        return 0


class FakeViewerAccessModel:
    query = FakeViewerAccessQuery()

    def __init__(self, user_id: int, config_type: str, config_name: str):
        self.user_id = user_id
        self.config_type = config_type
        self.config_name = config_name


class FakeUserModel:
    pass


class AdminRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["TESTING"] = True

        self.db = FakeDb()
        self.db.session.storage["task-1"] = FakeTask(id="task-1", task_type="restart_service", status="queued")

        def _task_accepted_response(task, message):
            payload = {"success": True, "queued": True, "task_id": task.id, "message": message}
            return jsonify(payload), 202

        def _enqueue_background_task(_task_type, _target, created_by_username=None, queued_message=None):
            _ = created_by_username
            _ = queued_message
            return FakeTask(id="task-new", task_type="update_system", status="queued")

        register_admin_routes(
            self.app,
            auth_manager=FakeAuthManager(),
            db=self.db,
            app_root="/opt/AdminAntizapret",
            background_task_model=FakeTask,
            user_model=FakeUserModel,
            viewer_config_access_model=FakeViewerAccessModel,
            collect_all_configs_for_access=lambda _config_type: [],
            normalize_openvpn_group_key=lambda value: value,
            normalize_conf_group_key=lambda value, _config_type: value,
            serialize_background_task=lambda task: {"task_id": task.id, "status": task.status},
            run_checked_command=lambda *_args, **_kwargs: ("", ""),
            enqueue_background_task=_enqueue_background_task,
            task_update_system=lambda: {"message": "ok"},
            task_restart_service=lambda: {"message": "ok"},
            task_accepted_response=_task_accepted_response,
            log_user_action_event=lambda *args, **kwargs: None,
        )

    def test_api_task_status_returns_404_for_unknown_task(self) -> None:
        with self.app.test_client() as client:
            response = client.get("/api/tasks/missing")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json().get("success", True))

    def test_api_task_status_returns_payload_for_existing_task(self) -> None:
        with self.app.test_client() as client:
            response = client.get("/api/tasks/task-1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("task_id"), "task-1")

    def test_update_system_returns_accepted_task_response(self) -> None:
        with self.app.test_client() as client:
            with client.session_transaction() as session_state:
                session_state["username"] = "admin"
            response = client.post("/update_system")

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertTrue(payload.get("queued"))
        self.assertEqual(payload.get("task_id"), "task-new")

    def test_viewer_access_validates_missing_json_payload(self) -> None:
        with self.app.test_client() as client:
            response = client.post("/api/viewer-access", json={})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json().get("success", True))


if __name__ == "__main__":
    unittest.main()
