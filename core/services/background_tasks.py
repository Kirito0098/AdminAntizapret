import inspect
import os
import secrets
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from flask import jsonify, url_for

from core.services.time_utils import as_utc


class BackgroundTaskCallable(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, str] | None:
        ...


_TASK_START_PROGRESS: dict[str, tuple[str, str, int]] = {
    "run_doall": ("AntiZapret: применение изменений…", "AntiZapret: запуск doall.sh…", 5),
    "restart_service": (
        "Перезапуск службы AdminAntizapret…",
        "Перезапуск службы AdminAntizapret…",
        10,
    ),
    "update_system": (
        "Обновление кода и зависимостей…",
        "Обновление: загрузка изменений из репозитория…",
        5,
    ),
    "app_backup_create": (
        "Резервная копия: создание архива…",
        "Резервная копия: подготовка файлов…",
        5,
    ),
    "app_backup_restore": (
        "Восстановление из резервной копии…",
        "Восстановление: остановка службы…",
        5,
    ),
    "app_backup_test_tg": (
        "Резервная копия: отправка в Telegram…",
        "Резервная копия: создание архива для Telegram…",
        5,
    ),
    "logs_dashboard_refresh": (
        "Обновление панели логов…",
        "Обновление панели логов…",
        5,
    ),
}

_TASK_DONE_PROGRESS: dict[str, str] = {
    "run_doall": "AntiZapret: изменения применены",
    "restart_service": "Служба AdminAntizapret перезапущена",
    "update_system": "Обновление завершено",
    "app_backup_create": "Резервная копия создана",
    "app_backup_restore": "Восстановление завершено",
    "app_backup_test_tg": "Бэкап отправлен в Telegram",
    "logs_dashboard_refresh": "Панель логов обновлена",
}

_TASK_STALE_SECONDS: dict[str, int] = {
    "logs_dashboard_refresh": 600,
    "restart_service": 300,
    "run_doall": 300,
    "update_system": 3600,
    "app_backup_create": 3600,
    "app_backup_restore": 3600,
    "app_backup_test_tg": 3600,
}

_DEFAULT_TASK_STALE_SECONDS = 3600


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
            "progress_percent": getattr(task, "progress_percent", 0) or 0,
            "progress_stage": getattr(task, "progress_stage", None),
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

    def _task_stale_seconds(self, task_type: str) -> int:
        return _TASK_STALE_SECONDS.get(task_type, _DEFAULT_TASK_STALE_SECONDS)

    def recover_stale_background_tasks(
        self,
        *,
        task_types: list[str] | None = None,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        query = self.background_task_model.query.filter(
            self.background_task_model.status.in_(["queued", "running"])
        )
        if task_types:
            query = query.filter(self.background_task_model.task_type.in_(task_types))

        recovered = 0
        for task in query.all():
            stale_seconds = self._task_stale_seconds(task.task_type)
            if task.status == "running":
                reference_at = as_utc(task.started_at) or as_utc(task.created_at)
            else:
                reference_at = as_utc(task.created_at)
            if reference_at is None:
                continue

            age_seconds = int((now - reference_at).total_seconds())
            if age_seconds <= stale_seconds:
                continue

            self.update_background_task(
                task.id,
                status="failed",
                finished_at=now,
                message="Задача прервана (истёк таймаут выполнения)",
                error=self.trim_background_task_text(
                    f"Задача {task.task_type} зависла в статусе {task.status} более {age_seconds} с"
                ),
                progress_percent=100,
                progress_stage="Прервано",
            )
            recovered += 1

        return recovered

    def _read_task_type(self, task_id: str) -> str:
        with self.app.app_context():
            task = self.db.session.get(self.background_task_model, task_id)
            return str(getattr(task, "task_type", "") or "")

    def _task_start_progress(self, task_type: str) -> tuple[str, str, int]:
        return _TASK_START_PROGRESS.get(
            task_type,
            ("Задача выполняется…", "Запуск…", 5),
        )

    def _task_done_stage(self, task_type: str) -> str:
        return _TASK_DONE_PROGRESS.get(task_type, "Готово")

    def _make_progress_updater(self, task_id: str) -> Callable[[int, str, str | None], None]:
        def updater(percent: int, stage: str, message: str | None = None) -> None:
            fields: dict[str, Any] = {
                "progress_percent": max(0, min(99, int(percent))),
                "progress_stage": str(stage or "").strip()[:255] or None,
            }
            if message:
                fields["message"] = str(message).strip()[:255]
            self.update_background_task(task_id, **fields)

        return updater

    def _invoke_task_callable(
        self,
        task_callable: BackgroundTaskCallable,
        progress_updater: Callable[[int, str, str | None], None],
    ) -> dict[str, str] | None:
        try:
            signature = inspect.signature(task_callable)
        except (TypeError, ValueError):
            signature = None

        if signature is not None and "progress_updater" in signature.parameters:
            with self.app.app_context():
                return task_callable(progress_updater=progress_updater) or {}

        with self.app.app_context():
            return task_callable() or {}

    def run_background_task(self, task_id: str, task_callable: BackgroundTaskCallable) -> None:
        task_type = self._read_task_type(task_id)
        running_message, starting_stage, starting_percent = self._task_start_progress(task_type)
        progress_updater = self._make_progress_updater(task_id)

        self.update_background_task(
            task_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            message=running_message,
            progress_percent=starting_percent,
            progress_stage=starting_stage,
        )

        try:
            result = self._invoke_task_callable(task_callable, progress_updater)
            done_stage = self._task_done_stage(task_type)
            self.update_background_task(
                task_id,
                status="completed",
                finished_at=datetime.now(timezone.utc),
                message=(result.get("message") or running_message)[:255],
                output=self.trim_background_task_text(result.get("output", "")),
                error=None,
                progress_percent=100,
                progress_stage=done_stage,
            )
        except Exception as e:
            self.app.logger.exception("Ошибка фоновой задачи %s: %s", task_id, e)
            try:
                with self.app.app_context():
                    self.db.session.rollback()
            except Exception as rollback_exc:
                self.app.logger.warning(
                    "Откат сессии после ошибки фоновой задачи %s не удался: %s",
                    task_id,
                    rollback_exc,
                )
            self.update_background_task(
                task_id,
                status="failed",
                finished_at=datetime.now(timezone.utc),
                message="Задача завершилась с ошибкой",
                error=self.trim_background_task_text(str(e)),
                progress_percent=100,
                progress_stage="Ошибка выполнения",
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

    def _antizapret_install_dir(self) -> str:
        for key in ("APP_BACKUP_AZ_INSTALL_DIR", "ANTIZAPRET_INSTALL_DIR"):
            value = (os.environ.get(key) or "").strip()
            if value:
                return os.path.abspath(value)
        return "/root/antizapret"

    def _run_client_sh_recreate_profiles(self, install_dir: str) -> tuple[str, str]:
        """Пересоздание файлов профилей клиентов (client.sh option 7) после doall."""
        client_sh = os.path.join(install_dir, "client.sh")
        if not os.path.isfile(client_sh):
            raise FileNotFoundError(f"client.sh не найден: {client_sh}")
        if not os.access(client_sh, os.X_OK):
            raise PermissionError(f"client.sh не исполняемый: {client_sh}")
        return self.run_checked_command([client_sh, "7"], cwd=install_dir, timeout=900)

    def task_run_doall(
        self,
        sync_wireguard_peer_cache_callback: Callable[..., Any] | None = None,
        progress_updater: Callable[[int, str, str | None], None] | None = None,
    ) -> dict[str, str]:
        install_dir = self._antizapret_install_dir()
        doall_sh = os.path.join(install_dir, "doall.sh")
        if progress_updater:
            progress_updater(10, "AntiZapret: запуск doall.sh…")
        stdout, stderr = self.run_checked_command([doall_sh], timeout=900)
        if progress_updater:
            progress_updater(65, "AntiZapret: пересоздание профилей клиентов…")
        recreate_stdout, recreate_stderr = self._run_client_sh_recreate_profiles(install_dir)
        if sync_wireguard_peer_cache_callback is not None:
            if progress_updater:
                progress_updater(85, "AntiZapret: синхронизация кэша WireGuard…")
            try:
                sync_wireguard_peer_cache_callback(force=True)
            except Exception as e:
                self.db.session.rollback()
                self.app.logger.warning(
                    "Не удалось синхронизировать wireguard_peer_cache после doall: %s",
                    e,
                )
        combined = "\n".join(
            part
            for part in [stdout, stderr, recreate_stdout, recreate_stderr]
            if part
        ).strip()
        return {
            "message": "doall и пересоздание профилей клиентов выполнены успешно",
            "output": combined,
        }

    def task_restart_service(
        self,
        progress_updater: Callable[[int, str, str | None], None] | None = None,
    ) -> dict[str, str]:
        if progress_updater:
            progress_updater(20, "Перезапуск службы AdminAntizapret…")
        adminpanel_sh = os.path.join(self.app_root, "script_sh", "adminpanel.sh")
        stdout, stderr = self.run_checked_command(
            [adminpanel_sh, "--restart"],
            timeout=120,
        )
        combined = "\n".join(part for part in [stdout, stderr] if part).strip()
        return {
            "message": "Служба успешно перезапущена",
            "output": combined,
        }

    def task_update_system(
        self,
        progress_updater: Callable[[int, str, str | None], None] | None = None,
    ) -> dict[str, str]:
        output_parts: list[str] = []
        repo_dir = self.app_root
        pip_path = os.path.join(self.app_root, "venv", "bin", "pip")
        if not os.path.exists(pip_path):
            pip_path = "pip3"

        commands = [
            (["git", "fetch", "origin", "main", "--quiet"], 90, "Обновление: загрузка изменений из репозитория…", 15),
            (["git", "reset", "--hard", "origin/main", "--quiet"], 90, "Обновление: применение версии из main…", 35),
            (["git", "clean", "-fd", "--quiet"], 90, "Обновление: очистка лишних файлов…", 55),
            ([pip_path, "install", "-q", "-r", "requirements.txt"], 300, "Обновление: установка зависимостей Python…", 75),
        ]

        for cmd, timeout, stage, pct in commands:
            if progress_updater:
                progress_updater(pct, stage)
            stdout, stderr = self.run_checked_command(cmd, cwd=repo_dir, timeout=timeout)
            output_parts.extend([part for part in [stdout, stderr] if part])

        return {
            "message": "Обновление завершено. Выполните перезапуск службы отдельно.",
            "output": "\n".join(output_parts).strip(),
        }
