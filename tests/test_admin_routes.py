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


@dataclass
class FakeUser:
    id: int
    username: str
    role: str


@dataclass
class FakeViewerAccessRow:
    user_id: int
    config_type: str
    config_name: str


class FakeViewerAccessFilteredQuery:
    def __init__(self, parent: "FakeViewerAccessQuery", criteria: dict[str, Any]):
        self.parent = parent
        self.criteria = criteria

    def _match(self, row: FakeViewerAccessRow) -> bool:
        for key, value in self.criteria.items():
            if getattr(row, key) != value:
                return False
        return True

    def all(self) -> list[FakeViewerAccessRow]:
        return [row for row in self.parent.rows if self._match(row)]

    def first(self) -> FakeViewerAccessRow | None:
        rows = self.all()
        return rows[0] if rows else None

    def delete(self, synchronize_session: bool = False) -> int:
        _ = synchronize_session
        kept: list[FakeViewerAccessRow] = []
        deleted = 0
        for row in self.parent.rows:
            if self._match(row):
                deleted += 1
                continue
            kept.append(row)
        self.parent.rows = kept
        return deleted


class FakeViewerAccessQuery:
    def __init__(self, rows: list[FakeViewerAccessRow] | None = None):
        self.rows = list(rows or [])

    def filter_by(self, **kwargs: Any) -> FakeViewerAccessFilteredQuery:
        return FakeViewerAccessFilteredQuery(self, kwargs)


class FakeViewerAccessModel:
    query = FakeViewerAccessQuery()

    def __init__(self, user_id: int, config_type: str, config_name: str):
        self.user_id = user_id
        self.config_type = config_type
        self.config_name = config_name


class FakeUserModel:
    pass


class FakeSessionDb:
    def __init__(self):
        self.tasks: dict[str, FakeTask] = {}
        self.users: dict[int, FakeUser] = {}

    def get(self, model: Any, key: str | int):
        if model is FakeTask:
            return self.tasks.get(str(key))
        if model is FakeUserModel:
            return self.users.get(int(key))
        return None

    def add(self, obj: Any) -> None:
        if isinstance(obj, FakeViewerAccessModel):
            FakeViewerAccessModel.query.rows.append(
                FakeViewerAccessRow(
                    user_id=obj.user_id,
                    config_type=obj.config_type,
                    config_name=obj.config_name,
                )
            )

    def commit(self) -> None:
        return None


class FakeDb:
    def __init__(self):
        self.session = FakeSessionDb()


class AdminRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["TESTING"] = True

        self.db = FakeDb()
        self.db.session.tasks["task-1"] = FakeTask(id="task-1", task_type="restart_service", status="queued")
        self.db.session.users[1] = FakeUser(id=1, username="viewer1", role="viewer")

        FakeViewerAccessModel.query = FakeViewerAccessQuery()

        def _task_accepted_response(task, message):
            payload = {"success": True, "queued": True, "task_id": task.id, "message": message}
            return jsonify(payload), 202

        def _enqueue_background_task(_task_type, _target, created_by_username=None, queued_message=None):
            _ = created_by_username
            _ = queued_message
            return FakeTask(id="task-new", task_type="update_system", status="queued")

        self._collect_map: dict[str, list[str]] = {
            "openvpn": ["/tmp/same.conf"],
            "wg": ["/tmp/same.conf"],
            "amneziawg": ["/tmp/same.conf"],
        }

        register_admin_routes(
            self.app,
            auth_manager=FakeAuthManager(),
            db=self.db,
            app_root="/opt/AdminAntizapret",
            background_task_model=FakeTask,
            user_model=FakeUserModel,
            viewer_config_access_model=FakeViewerAccessModel,
            collect_all_configs_for_access=lambda config_type: self._collect_map.get(config_type, []),
            normalize_openvpn_group_key=lambda value: "groupA" if value == "same.conf" else "other",
            normalize_conf_group_key=lambda value, _config_type: "groupA" if value == "same.conf" else "other",
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

    def test_viewer_access_non_json_request_returns_consistent_json_error(self) -> None:
        with self.app.test_client() as client:
            response = client.post(
                "/api/viewer-access",
                data="x=1",
                content_type="application/x-www-form-urlencoded",
            )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertFalse(payload.get("success", True))

    def test_viewer_access_grant_allows_same_name_for_different_protocol(self) -> None:
        FakeViewerAccessModel.query.rows = [
            FakeViewerAccessRow(user_id=1, config_type="openvpn", config_name="same.conf")
        ]

        with self.app.test_client() as client:
            response = client.post(
                "/api/viewer-access",
                json={
                    "user_id": 1,
                    "config_name": "groupA",
                    "config_type": "wg",
                    "action": "grant",
                },
            )

        self.assertEqual(response.status_code, 200)
        rows = FakeViewerAccessModel.query.rows
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(r.config_type == "openvpn" and r.config_name == "same.conf" for r in rows))
        self.assertTrue(any(r.config_type == "wg" and r.config_name == "same.conf" for r in rows))

    def test_viewer_access_revoke_removes_only_requested_protocol(self) -> None:
        FakeViewerAccessModel.query.rows = [
            FakeViewerAccessRow(user_id=1, config_type="openvpn", config_name="same.conf"),
            FakeViewerAccessRow(user_id=1, config_type="wg", config_name="same.conf"),
        ]

        with self.app.test_client() as client:
            response = client.post(
                "/api/viewer-access",
                json={
                    "user_id": 1,
                    "config_name": "groupA",
                    "config_type": "wg",
                    "action": "revoke",
                },
            )

        self.assertEqual(response.status_code, 200)
        rows = FakeViewerAccessModel.query.rows
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].config_type, "openvpn")
        self.assertEqual(rows[0].config_name, "same.conf")


if __name__ == "__main__":
    unittest.main()
