import os
import secrets
import subprocess
from datetime import datetime
from typing import Any, Callable, Protocol

from flask import jsonify, url_for


class BackgroundTaskCallable(Protocol):
    def __call__(self) -> dict[str, str] | None:
        ...


class BackgroundTaskService:
    def __init__(
        self,
        *,
        app,
        db,
        background_task_model,
        executor,
        max_output_chars,
        app_root,
    ):
        self.app = app
        self.db = db
        self.background_task_model = background_task_model
        self.executor = executor
        self.max_output_chars = max_output_chars
        self.app_root = app_root

    def trim_background_task_text(self, value: str | None) -> str:
        text = (value or "").strip()
        if len(text) <= self.max_output_chars:
            return text
        return text[: self.max_output_chars] + "\n...[truncated]"

    def serialize_background_task(self, task: Any) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "message": task.message,
            "output": task.output,
            "error": task.error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }

    def update_background_task(self, task_id: str, **fields: Any) -> None:
        with self.app.app_context():
            task = self.db.session.get(self.background_task_model, task_id)
            if not task:
                return

            for key, value in fields.items():
                setattr(task, key, value)

            self.db.session.commit()

    def run_background_task(self, task_id: str, task_callable: BackgroundTaskCallable) -> None:
        self.update_background_task(
            task_id,
            status="running",
            started_at=datetime.utcnow(),
            message="Задача выполняется",
        )

        try:
            with self.app.app_context():
                result = task_callable() or {}
            self.update_background_task(
                task_id,
                status="completed",
                finished_at=datetime.utcnow(),
                message=(result.get("message") or "Задача выполнена")[:255],
                output=self.trim_background_task_text(result.get("output", "")),
                error=None,
            )
        except Exception as e:
            self.app.logger.exception("Ошибка фоновой задачи %s: %s", task_id, e)
            try:
                with self.app.app_context():
                    self.db.session.rollback()
            except Exception:
                pass
            self.update_background_task(
                task_id,
                status="failed",
                finished_at=datetime.utcnow(),
                message="Задача завершилась с ошибкой",
                error=self.trim_background_task_text(str(e)),
            )

    def enqueue_background_task(
        self,
        task_type: str,
        task_callable: BackgroundTaskCallable,
        created_by_username: str | None = None,
        queued_message: str | None = None,
    ) -> Any:
        task = self.background_task_model(
            id=secrets.token_hex(16),
            task_type=task_type,
            status="queued",
            created_by_username=created_by_username,
            message=(queued_message or "Задача поставлена в очередь")[:255],
        )
        self.db.session.add(task)
        self.db.session.commit()

        self.executor.submit(self.run_background_task, task.id, task_callable)
        return task

    def task_accepted_response(
        self,
        task: Any,
        message: str,
        status_endpoint: str = "api_task_status",
    ) -> tuple[Any, int]:
        payload = self.serialize_background_task(task)
        payload.update(
            {
                "success": True,
                "queued": True,
                "message": message,
                "status_url": url_for(status_endpoint, task_id=task.id),
            }
        )
        return jsonify(payload), 202

    def run_checked_command(
        self,
        args: list[str],
        cwd: str | None = None,
        timeout: int = 120,
    ) -> tuple[str, str]:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            raise RuntimeError(
                f"Команда {' '.join(args)} завершилась с кодом {result.returncode}. {stderr or stdout}"
            )
        return stdout, stderr

    def task_run_doall(
        self,
        sync_wireguard_peer_cache_callback: Callable[..., Any] | None = None,
    ) -> dict[str, str]:
        stdout, stderr = self.run_checked_command(["/root/antizapret/doall.sh"], timeout=900)
        if sync_wireguard_peer_cache_callback is not None:
            try:
                sync_wireguard_peer_cache_callback(force=True)
            except Exception as e:
                self.db.session.rollback()
                self.app.logger.warning(
                    "Не удалось синхронизировать wireguard_peer_cache после doall: %s",
                    e,
                )
        combined = "\n".join(part for part in [stdout, stderr] if part).strip()
        return {
            "message": "Скрипт doall выполнен успешно",
            "output": combined,
        }

    def task_restart_service(self) -> dict[str, str]:
        stdout, stderr = self.run_checked_command(
            ["/opt/AdminAntizapret/script_sh/adminpanel.sh", "--restart"],
            timeout=120,
        )
        combined = "\n".join(part for part in [stdout, stderr] if part).strip()
        return {
            "message": "Служба успешно перезапущена",
            "output": combined,
        }

    def task_update_system(self) -> dict[str, str]:
        output_parts: list[str] = []
        repo_dir = self.app_root
        pip_path = os.path.join(self.app_root, "venv", "bin", "pip")
        if not os.path.exists(pip_path):
            pip_path = "pip3"

        commands = [
            (["git", "fetch", "origin", "main", "--quiet"], 90),
            (["git", "reset", "--hard", "origin/main", "--quiet"], 90),
            (["git", "clean", "-fd", "--quiet"], 90),
            ([pip_path, "install", "-q", "-r", "requirements.txt"], 300),
        ]

        for cmd, timeout in commands:
            stdout, stderr = self.run_checked_command(cmd, cwd=repo_dir, timeout=timeout)
            output_parts.extend([part for part in [stdout, stderr] if part])

        return {
            "message": "Обновление завершено. Выполните перезапуск службы отдельно.",
            "output": "\n".join(output_parts).strip(),
        }
