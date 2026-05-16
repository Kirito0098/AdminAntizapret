import secrets
import threading
from datetime import datetime, timedelta


CIDR_TASKS = {}
CIDR_TASKS_LOCK = threading.Lock()
CIDR_TASK_RETENTION = timedelta(hours=2)


def _cidr_now_utc():
    return datetime.utcnow()


def _cleanup_cidr_tasks():
    cutoff = _cidr_now_utc() - CIDR_TASK_RETENTION
    with CIDR_TASKS_LOCK:
        stale_task_ids = []
        for task_id, task in CIDR_TASKS.items():
            finished_at = task.get("finished_at")
            if not finished_at:
                continue
            if finished_at < cutoff:
                stale_task_ids.append(task_id)
        for task_id in stale_task_ids:
            CIDR_TASKS.pop(task_id, None)


def create_cidr_task(task_type, message):
    _cleanup_cidr_tasks()
    task_id = secrets.token_hex(16)
    task = {
        "task_id": task_id,
        "task_type": task_type,
        "status": "queued",
        "message": str(message or "Задача поставлена в очередь"),
        "progress_percent": 0,
        "progress_stage": "Ожидание запуска...",
        "error": None,
        "result": None,
        "created_at": _cidr_now_utc(),
        "started_at": None,
        "finished_at": None,
        "updated_at": _cidr_now_utc(),
    }
    with CIDR_TASKS_LOCK:
        CIDR_TASKS[task_id] = task
    return task_id


def update_cidr_task(task_id, **fields):
    with CIDR_TASKS_LOCK:
        task = CIDR_TASKS.get(task_id)
        if not task:
            return
        task.update(fields)
        task["updated_at"] = _cidr_now_utc()


def get_cidr_task(task_id):
    with CIDR_TASKS_LOCK:
        task = CIDR_TASKS.get(task_id)
        if not task:
            return None
        return dict(task)


def find_active_cidr_task(task_type):
    with CIDR_TASKS_LOCK:
        for task in CIDR_TASKS.values():
            if str(task.get("task_type") or "") != str(task_type or ""):
                continue
            if str(task.get("status") or "") in {"queued", "running"}:
                return dict(task)
    return None


def serialize_cidr_task(task):
    payload = dict(task)
    for key in ("created_at", "started_at", "finished_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if isinstance(value, datetime) else None
    return payload


def make_start_cidr_task(app):
    def start_cidr_task(task_id, runner):
        def _progress_callback(percent, stage):
            update_cidr_task(
                task_id,
                status="running",
                progress_percent=max(0, min(99, int(percent))),
                progress_stage=str(stage or "Выполняется операция"),
                message=str(stage or "Выполняется операция"),
            )

        def _worker():
            update_cidr_task(
                task_id,
                status="running",
                progress_percent=1,
                progress_stage="Подготовка...",
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
                        message=str(result.get("message") or "Операция завершилась с ошибкой"),
                        error=str(result.get("message") or "Операция завершилась с ошибкой"),
                        result=result,
                        finished_at=_cidr_now_utc(),
                    )
                    return

                update_cidr_task(
                    task_id,
                    status="completed",
                    progress_percent=100,
                    progress_stage="Операция завершена",
                    message=str(result.get("message") or "Операция завершена"),
                    result=result,
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
