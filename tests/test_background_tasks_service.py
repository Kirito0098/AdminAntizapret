import subprocess
import unittest
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import patch

from flask import Flask

from core.services.background_tasks import BackgroundTaskService


@dataclass
class FakeTask:
    id: str
    task_type: str
    status: str
    created_by_username: str | None = None
    message: str = ""
    output: str = ""
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FakeSession:
    def __init__(self):
        self.storage: dict[str, FakeTask] = {}
        self.added: list[FakeTask] = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def get(self, _model, task_id: str) -> FakeTask | None:
        return self.storage.get(task_id)

    def add(self, task: FakeTask) -> None:
        self.storage[task.id] = task
        self.added.append(task)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


class FakeDb:
    def __init__(self):
        self.session = FakeSession()


class FakeExecutor:
    def __init__(self):
        self.submissions: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, fn, *args):
        self.submissions.append((fn, args))
        return None


class BackgroundTaskServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.db = FakeDb()
        self.executor = FakeExecutor()
        self.service = BackgroundTaskService(
            app=self.app,
            db=self.db,
            background_task_model=FakeTask,
            executor=self.executor,
            max_output_chars=10,
            app_root="/opt/AdminAntizapret",
        )

    def test_enqueue_background_task_creates_record_and_submits_executor(self) -> None:
        task = self.service.enqueue_background_task(
            task_type="demo",
            task_callable=lambda: {"message": "ok", "output": "done"},
            created_by_username="admin",
            queued_message="queued",
        )

        self.assertEqual(task.status, "queued")
        self.assertEqual(task.created_by_username, "admin")
        self.assertEqual(self.db.session.commit_calls, 1)
        self.assertEqual(len(self.executor.submissions), 1)
        submitted_fn, submitted_args = self.executor.submissions[0]
        self.assertEqual(submitted_fn, self.service.run_background_task)
        self.assertEqual(submitted_args[0], task.id)

    def test_run_background_task_marks_completed_and_trims_output(self) -> None:
        task = FakeTask(id="task-1", task_type="demo", status="queued")
        self.db.session.storage[task.id] = task

        self.service.run_background_task(
            task.id,
            lambda: {"message": "completed", "output": "x" * 30},
        )

        self.assertEqual(task.status, "completed")
        self.assertEqual(task.message, "completed")
        self.assertIsNone(task.error)
        self.assertIn("...[truncated]", task.output)

    def test_run_checked_command_raises_runtime_error_on_nonzero_exit(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["test"],
            returncode=7,
            stdout="",
            stderr="boom",
        )
        with patch("core.services.background_tasks.subprocess.run", return_value=completed):
            with self.assertRaises(RuntimeError) as ctx:
                self.service.run_checked_command(["test"])

        self.assertIn("кодом 7", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
