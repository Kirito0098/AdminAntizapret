import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

try:
    from flask import has_app_context
except ImportError:  # pragma: no cover
    def has_app_context():  # type: ignore[misc]
        return False


# ---------------------------------------------------------------------------
# Module-level DB state — initialised by init_cidr_task_db()
# ---------------------------------------------------------------------------
_app = None
_db = None
_BackgroundTask = None


def init_cidr_task_db(app, db, background_task_model) -> None:
    """Wire CIDR tasks to use the BackgroundTask DB table.

    Call once at startup, after run_db_migrations(), before route registration.
    """
    global _app, _db, _BackgroundTask
    _app = app
    _db = db
    _BackgroundTask = background_task_model


# ---------------------------------------------------------------------------
# In-memory fallback (used when DB not initialised, e.g. unit tests)
# ---------------------------------------------------------------------------
_CIDR_TASKS: dict = {}
_CIDR_TASKS_LOCK = threading.Lock()
_CIDR_TASK_RETENTION = timedelta(hours=2)


def _cidr_now_utc():
    return datetime.now(timezone.utc)


def _cleanup_cidr_tasks_memory():
    cutoff = _cidr_now_utc() - _CIDR_TASK_RETENTION
    with _CIDR_TASKS_LOCK:
        stale = [
            tid for tid, t in _CIDR_TASKS.items()
            if t.get("finished_at") and t["finished_at"] < cutoff
        ]
        for tid in stale:
            _CIDR_TASKS.pop(tid, None)


# ---------------------------------------------------------------------------
# Public API (DB-backed when initialised, in-memory otherwise)
# ---------------------------------------------------------------------------

def create_cidr_task(task_type: str, message: str) -> str:
    task_id = secrets.token_hex(16)
    if _db is not None and _BackgroundTask is not None:
        return _create_cidr_task_db(task_id, task_type, message)
    return _create_cidr_task_memory(task_id, task_type, message)


def update_cidr_task(task_id: str, **fields) -> None:
    if _db is not None and _BackgroundTask is not None:
        _update_cidr_task_db(task_id, **fields)
    else:
        _update_cidr_task_memory(task_id, **fields)


def get_cidr_task(task_id: str) -> dict | None:
    if _db is not None and _BackgroundTask is not None:
        return _get_cidr_task_db(task_id)
    return _get_cidr_task_memory(task_id)


def find_active_cidr_task(task_type: str) -> dict | None:
    if _db is not None and _BackgroundTask is not None:
        return _find_active_cidr_task_db(task_type)
    return _find_active_cidr_task_memory(task_type)


def serialize_cidr_task(task: dict) -> dict:
    """Serialize a task dict (from get_cidr_task) to JSON-safe payload."""
    payload = dict(task)
    for key in ("created_at", "started_at", "finished_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if isinstance(value, datetime) else value
    return payload


# ---------------------------------------------------------------------------
# DB-backed implementations
# ---------------------------------------------------------------------------

def _create_cidr_task_db(task_id: str, task_type: str, message: str) -> str:
    def _do():
        task = _BackgroundTask(
            id=task_id,
            task_type=task_type,
            status="queued",
            message=str(message or "Задача поставлена в очередь")[:255],
            progress_percent=0,
            progress_stage="Ожидание запуска задачи…",
        )
        _db.session.add(task)
        _db.session.commit()

    _run_with_context(_do)
    return task_id


def _update_cidr_task_db(task_id: str, **fields) -> None:
    _allowed = {
        "status", "message", "output", "error",
        "progress_percent", "progress_stage",
        "started_at", "finished_at",
    }

    def _do():
        task = _db.session.get(_BackgroundTask, task_id)
        if not task:
            return
        for key, value in fields.items():
            if key not in _allowed:
                continue
            if key == "message" and isinstance(value, str):
                value = value[:255]
            if key == "progress_stage" and isinstance(value, str):
                value = value[:255]
            setattr(task, key, value)
        _db.session.commit()

    try:
        _run_with_context(_do)
    except Exception:  # noqa: BLE001
        pass


def _get_cidr_task_db(task_id: str) -> dict | None:
    result: list = []

    def _do():
        task = _db.session.get(_BackgroundTask, task_id)
        if task:
            result.append(_serialize_bg_task(task))

    _run_with_context(_do)
    return result[0] if result else None


def _find_active_cidr_task_db(task_type: str) -> dict | None:
    result: list = []

    def _do():
        task = (
            _BackgroundTask.query
            .filter(
                _BackgroundTask.task_type == task_type,
                _BackgroundTask.status.in_(["queued", "running"]),
            )
            .order_by(_BackgroundTask.created_at.desc())
            .first()
        )
        if task:
            result.append(_serialize_bg_task(task))

    _run_with_context(_do)
    return result[0] if result else None


def _serialize_bg_task(task) -> dict:
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "message": task.message,
        "progress_percent": getattr(task, "progress_percent", 0) or 0,
        "progress_stage": getattr(task, "progress_stage", None),
        "error": task.error,
        "result": None,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "updated_at": task.finished_at,  # approximate
    }


def _run_with_context(fn) -> None:
    """Run fn() inside an app context, pushing one only if not already active."""
    if has_app_context():
        fn()
    else:
        with _app.app_context():
            fn()


# ---------------------------------------------------------------------------
# In-memory implementations (fallback / test usage)
# ---------------------------------------------------------------------------

def _create_cidr_task_memory(task_id: str, task_type: str, message: str) -> str:
    _cleanup_cidr_tasks_memory()
    now = _cidr_now_utc()
    task = {
        "task_id": task_id,
        "task_type": task_type,
        "status": "queued",
        "message": str(message or "Задача поставлена в очередь"),
        "progress_percent": 0,
        "progress_stage": "Ожидание запуска задачи…",
        "error": None,
        "result": None,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "updated_at": now,
    }
    with _CIDR_TASKS_LOCK:
        _CIDR_TASKS[task_id] = task
    return task_id


def _update_cidr_task_memory(task_id: str, **fields) -> None:
    with _CIDR_TASKS_LOCK:
        task = _CIDR_TASKS.get(task_id)
        if not task:
            return
        task.update(fields)
        task["updated_at"] = _cidr_now_utc()


def _get_cidr_task_memory(task_id: str) -> dict | None:
    with _CIDR_TASKS_LOCK:
        task = _CIDR_TASKS.get(task_id)
        if not task:
            return None
        return dict(task)


def _find_active_cidr_task_memory(task_type: str) -> dict | None:
    with _CIDR_TASKS_LOCK:
        for task in _CIDR_TASKS.values():
            if str(task.get("task_type") or "") != str(task_type or ""):
                continue
            if str(task.get("status") or "") in {"queued", "running"}:
                return dict(task)
    return None


# ---------------------------------------------------------------------------
# Thread worker factory
# ---------------------------------------------------------------------------

def make_start_cidr_task(app):
    def start_cidr_task(task_id, runner):
        progress_lock = threading.Lock()
        progress_state = {"last_at": 0.0, "last_pct": -1}

        def _progress_callback(percent, stage):
            pct = max(0, min(99, int(percent)))
            stage_str = str(stage or "Выполняется операция…")
            now = time.monotonic()
            with progress_lock:
                if (
                    pct < 99
                    and (now - progress_state["last_at"]) < 0.5
                    and pct <= progress_state["last_pct"] + 1
                ):
                    return
                progress_state["last_at"] = now
                progress_state["last_pct"] = pct
            update_cidr_task(
                task_id,
                status="running",
                progress_percent=pct,
                progress_stage=stage_str,
                message=stage_str,
            )

        def _worker():
            update_cidr_task(
                task_id,
                status="running",
                progress_percent=1,
                progress_stage="Подготовка к выполнению…",
                started_at=_cidr_now_utc(),
            )
            try:
                with app.app_context():
                    result = runner(_progress_callback) or {}
                if not bool(result.get("success")):
                    update_cidr_task(
                        task_id,
                        status="failed",
                        progress_percent=100,
                        progress_stage="Операция завершилась с ошибкой",
                        message=str(result.get("message") or "Операция завершилась с ошибкой")[:255],
                        error=str(result.get("message") or "Операция завершилась с ошибкой"),
                        finished_at=_cidr_now_utc(),
                    )
                    return

                update_cidr_task(
                    task_id,
                    status="completed",
                    progress_percent=100,
                    progress_stage="Операция успешно завершена",
                    message=str(result.get("message") or "Операция завершена")[:255],
                    error=None,
                    finished_at=_cidr_now_utc(),
                )
            except Exception as exc:  # noqa: BLE001
                update_cidr_task(
                    task_id,
                    status="failed",
                    progress_percent=100,
                    progress_stage="Операция завершилась с ошибкой",
                    message="Операция завершилась с ошибкой",
                    error=str(exc),
                    finished_at=_cidr_now_utc(),
                )
                app.logger.exception("CIDR background task failed (%s): %s", task_id, exc)

        threading.Thread(target=_worker, daemon=True).start()

    return start_cidr_task
