import json
from datetime import datetime


class LogsDashboardCacheService:
    def __init__(
        self,
        *,
        db,
        logs_dashboard_cache_model,
        background_task_model,
        logs_dashboard_cache_ttl_seconds,
        collect_logs_dashboard_data,
        enqueue_background_task,
        human_bytes,
    ):
        self.db = db
        self.logs_dashboard_cache_model = logs_dashboard_cache_model
        self.background_task_model = background_task_model
        self.logs_dashboard_cache_ttl_seconds = int(logs_dashboard_cache_ttl_seconds or 0)
        self.collect_logs_dashboard_data = collect_logs_dashboard_data
        self.enqueue_background_task = enqueue_background_task
        self.human_bytes = human_bytes

    def logs_dashboard_cache_row(self):
        return self.logs_dashboard_cache_model.query.filter_by(cache_key="main").first()

    def save_logs_dashboard_cache_payload(self, payload, last_error=None):
        row = self.logs_dashboard_cache_row()
        if row is None:
            row = self.logs_dashboard_cache_model(cache_key="main")

        row.payload_json = json.dumps(payload, ensure_ascii=False)
        row.generated_at = datetime.utcnow()
        row.last_error = (last_error or "").strip()[:255] or None
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def load_logs_dashboard_cache_payload(self):
        row = self.logs_dashboard_cache_row()
        if row is None or not row.payload_json:
            return None, row

        try:
            payload = json.loads(row.payload_json)
        except Exception:
            return None, row

        if not isinstance(payload, dict):
            return None, row

        return payload, row

    def build_empty_logs_dashboard_payload(self, reason_message=None):
        reason = (reason_message or "Данные временно недоступны").strip()
        return {
            "status_rows": [],
            "event_rows": [],
            "grouped_status_rows": [
                {
                    "network": "Antizapret",
                    "files": "-",
                    "snapshot_times": "-",
                    "updated_at": "-",
                    "client_count": 0,
                    "unique_real_ips": 0,
                    "transport_split": "TCP: 0, UDP: 0",
                    "total_received": 0,
                    "total_sent": 0,
                    "total_traffic": 0,
                    "total_received_human": self.human_bytes(0),
                    "total_sent_human": self.human_bytes(0),
                    "total_traffic_human": self.human_bytes(0),
                },
                {
                    "network": "VPN",
                    "files": "-",
                    "snapshot_times": "-",
                    "updated_at": "-",
                    "client_count": 0,
                    "unique_real_ips": 0,
                    "transport_split": "TCP: 0, UDP: 0",
                    "total_received": 0,
                    "total_sent": 0,
                    "total_traffic": 0,
                    "total_received_human": self.human_bytes(0),
                    "total_sent_human": self.human_bytes(0),
                    "total_traffic_human": self.human_bytes(0),
                },
            ],
            "grouped_event_rows": [],
            "openvpn_logging_enabled": False,
            "missing_event_log_files": [reason],
            "summary": {
                "total_active_clients": 0,
                "unique_client_names": 0,
                "unique_ips": 0,
                "total_received": 0,
                "total_sent": 0,
                "total_received_human": self.human_bytes(0),
                "total_sent_human": self.human_bytes(0),
                "total_traffic_human": self.human_bytes(0),
                "total_event_lines": 0,
                "total_event_counts": {},
            },
            "connected_clients": [],
            "persisted_traffic_rows": [],
            "deleted_persisted_traffic_rows": [],
            "persisted_traffic_summary": {
                "users_count": 0,
                "active_users_count": 0,
                "offline_users_count": 0,
                "total_received_human": self.human_bytes(0),
                "total_sent_human": self.human_bytes(0),
                "total_traffic_human": self.human_bytes(0),
                "latest_sample_at": "-",
                "latest_stat_seen_at": "-",
                "db_age_seconds": None,
                "db_age_human": "-",
                "db_is_stale": False,
            },
            "deleted_persisted_traffic_summary": {
                "users_count": 0,
                "total_bytes": 0,
                "total_bytes_human": self.human_bytes(0),
            },
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def get_logs_dashboard_refresh_task(self):
        return (
            self.background_task_model.query.filter(
                self.background_task_model.task_type == "logs_dashboard_refresh",
                self.background_task_model.status.in_(["queued", "running"]),
            )
            .order_by(self.background_task_model.created_at.desc())
            .first()
        )

    def is_logs_dashboard_refresh_in_progress(self):
        return self.get_logs_dashboard_refresh_task() is not None

    def task_refresh_logs_dashboard_cache(self):
        try:
            payload = self.collect_logs_dashboard_data()
            self.save_logs_dashboard_cache_payload(payload, last_error=None)
            return {
                "message": "Кэш dashboard обновлен",
                "output": f"generated_at={payload.get('generated_at', '-')}"
            }
        except Exception as exc:
            self.db.session.rollback()
            row = self.logs_dashboard_cache_row()
            if row is not None:
                row.last_error = str(exc)[:255]
                self.db.session.commit()
            raise

    def queue_logs_dashboard_refresh_if_needed(self, created_by_username=None):
        existing_task = self.get_logs_dashboard_refresh_task()
        if existing_task is not None:
            return False

        self.enqueue_background_task(
            "logs_dashboard_refresh",
            self.task_refresh_logs_dashboard_cache,
            created_by_username=created_by_username,
            queued_message="Обновление кэша dashboard поставлено в очередь",
        )
        return True

    def get_logs_dashboard_data_cached(self, created_by_username=None):
        payload, row = self.load_logs_dashboard_cache_payload()
        now = datetime.utcnow()

        if payload is not None and row is not None and row.generated_at is not None:
            age_seconds = max(int((now - row.generated_at).total_seconds()), 0)
            is_stale = age_seconds > self.logs_dashboard_cache_ttl_seconds
            refresh_task = self.get_logs_dashboard_refresh_task()

            if is_stale:
                if refresh_task is None:
                    self.queue_logs_dashboard_refresh_if_needed(created_by_username=created_by_username)
                    refresh_task = self.get_logs_dashboard_refresh_task()

            payload["cache_meta"] = {
                "from_cache": True,
                "is_stale": is_stale,
                "age_seconds": age_seconds,
                "refresh_in_progress": refresh_task is not None,
                "refresh_task_id": refresh_task.id if refresh_task is not None else None,
                "ttl_seconds": self.logs_dashboard_cache_ttl_seconds,
                "last_error": (row.last_error or "").strip() or None,
            }
            return payload

        try:
            fresh_payload = self.collect_logs_dashboard_data()
            self.save_logs_dashboard_cache_payload(fresh_payload, last_error=None)
            fresh_payload["cache_meta"] = {
                "from_cache": False,
                "is_stale": False,
                "age_seconds": 0,
                "refresh_in_progress": False,
                "refresh_task_id": None,
                "ttl_seconds": self.logs_dashboard_cache_ttl_seconds,
                "last_error": None,
            }
            return fresh_payload
        except Exception as exc:
            self.db.session.rollback()
            self.queue_logs_dashboard_refresh_if_needed(created_by_username=created_by_username)
            refresh_task = self.get_logs_dashboard_refresh_task()
            fallback_payload = self.build_empty_logs_dashboard_payload(str(exc))
            fallback_payload["cache_meta"] = {
                "from_cache": False,
                "is_stale": True,
                "age_seconds": None,
                "refresh_in_progress": refresh_task is not None,
                "refresh_task_id": refresh_task.id if refresh_task is not None else None,
                "ttl_seconds": self.logs_dashboard_cache_ttl_seconds,
                "last_error": str(exc),
            }
            return fallback_payload
