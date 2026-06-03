"""Прочие settings-API эндпоинты: экспорт журналов, IP-файлы, мониторинг, тест TG.

Вынесено из routes/settings/api.py. URL-пути и поведение сохранены 1:1.
"""

import csv
import io
import os
from datetime import datetime, timezone

from flask import Response, jsonify, request, session

from core.services.audit_view_presenter import build_user_action_audit_view
from core.services.tg_notify import send_tg_message


def register_settings_misc_api_routes(
    app,
    *,
    auth_manager,
    user_model,
    user_action_log_model,
    ip_manager,
    set_env_value,
    get_env_value,
    log_user_action_event,
):
    @app.route("/api/settings/action-logs/export", methods=["GET"])
    @auth_manager.admin_required
    def api_settings_action_logs_export():
        q = (request.args.get("q") or "").strip().lower()
        src = (request.args.get("src") or "").strip().lower()
        user = (request.args.get("user") or "").strip()
        status = (request.args.get("status") or "").strip().lower()
        sort = (request.args.get("sort") or "time_desc").strip().lower()
        alert_only = (request.args.get("alert_only") or "").strip() in {"1", "true", "yes", "on"}

        rows = user_action_log_model.query.order_by(
            user_action_log_model.created_at.desc()
        ).limit(300).all()
        view_rows = build_user_action_audit_view(rows)

        filtered_rows = []
        for row in view_rows:
            row_src = str(row.get("source_kind") or "").lower()
            row_user = str(row.get("actor_display") or "")
            row_status = str(row.get("status") or "").lower()
            row_alert = bool(row.get("is_security_alert"))
            row_search = str(row.get("search_blob") or "").lower()
            if src and row_src != src:
                continue
            if user and row_user != user:
                continue
            if status and row_status != status:
                continue
            if alert_only and not row_alert:
                continue
            if q and q not in row_search:
                continue
            filtered_rows.append(row)

        if sort == "time_asc":
            filtered_rows.sort(key=lambda r: int(r.get("created_at_ts") or 0))
        elif sort == "user_asc":
            filtered_rows.sort(key=lambda r: str(r.get("actor_display") or "").lower())
        elif sort == "result_asc":
            filtered_rows.sort(key=lambda r: str(r.get("status_display") or "").lower())
        else:
            filtered_rows.sort(key=lambda r: int(r.get("created_at_ts") or 0), reverse=True)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Дата/время", "Пользователь", "Действие", "IP", "Результат", "Детали"])
        for row in filtered_rows:
            csv_row = row.get("csv_row") or {}
            writer.writerow(
                [
                    csv_row.get("timestamp", ""),
                    csv_row.get("username", ""),
                    csv_row.get("action", ""),
                    csv_row.get("ip", "—"),
                    csv_row.get("result", ""),
                    csv_row.get("details", "—"),
                ]
            )

        csv_payload = "\ufeff" + output.getvalue()
        filename = f"action_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            csv_payload,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @app.route("/api/antizapret/ip-files", methods=["GET", "POST"])
    @auth_manager.admin_required
    def api_antizapret_ip_files():
        if request.method == "GET":
            ip_manager.sync_enabled()
            return jsonify(
                {
                    "success": True,
                    "states": {k: bool(v) for k, v in ip_manager.get_file_states().items()},
                    "source_states": {k: bool(v) for k, v in ip_manager.get_source_states().items()},
                }
            )

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

        action = str(payload.get("action") or "").strip().lower()
        if action == "sync_with_list":
            ip_manager.sync_enabled()
            sync_result = ip_manager.sync_enabled_from_list()
            refreshed_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

            synced_files = int(sync_result.get("synced_files", 0))
            updated_files = int(sync_result.get("updated_files", 0))
            missing_sources = [str(item) for item in (sync_result.get("missing_sources") or [])]

            details_parts = [f"synced={synced_files}", f"updated={updated_files}"]
            if missing_sources:
                details_parts.append(f"missing={','.join(missing_sources[:5])}")

            log_user_action_event(
                "settings_ip_files_sync",
                target_type="ip_file",
                target_name="all_enabled",
                details=" ".join(details_parts),
            )

            if missing_sources:
                message = (
                    f"Сверка завершена: синхронизировано {synced_files}, обновлено {updated_files}. "
                    f"Не найдены исходные файлы: {', '.join(missing_sources)}"
                )
            else:
                message = (
                    f"Сверка завершена: синхронизировано {synced_files}, обновлено {updated_files}."
                )

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "synced_files": synced_files,
                    "updated_files": updated_files,
                    "missing_sources": missing_sources,
                    "states": refreshed_states,
                }
            )

        states = payload.get("states")
        if not isinstance(states, dict):
            return jsonify({"success": False, "message": "Ожидается поле states в формате объекта"}), 400

        ip_manager.sync_enabled()
        all_ip_files_meta = ip_manager.list_ip_files()
        available_files = set(all_ip_files_meta.keys())
        current_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

        changes_count = 0
        details = []

        for ip_file, raw_state in states.items():
            if ip_file not in available_files:
                continue

            desired_enabled = bool(raw_state)
            current_enabled = bool(current_states.get(ip_file, False))
            if desired_enabled == current_enabled:
                continue

            if desired_enabled:
                affected_count = ip_manager.enable_file(ip_file)
            else:
                affected_count = ip_manager.disable_file(ip_file)

            _meta = all_ip_files_meta.get(ip_file, {})
            _display = (_meta.get("name") if isinstance(_meta, dict) else None) \
                       or ip_file.replace(".txt", "").replace("-ips", "").replace("-", " ").title()

            changes_count += 1
            details.append(ip_file)

            log_user_action_event(
                "settings_ip_file_toggle",
                target_type="ip_file",
                target_name=ip_file,
                details=f"{'вкл' if desired_enabled else 'выкл'}|{_display}|{affected_count} IP",
            )

        refreshed_states = {k: bool(v) for k, v in ip_manager.get_file_states().items()}

        return jsonify(
            {
                "success": True,
                "message": "Состояние IP-файлов сохранено" if changes_count else "Изменений в IP-файлах нет",
                "changes": changes_count,
                "states": refreshed_states,
                "details": details,
            }
        )

    @app.route("/api/monitor-settings", methods=["POST"])
    @auth_manager.admin_required
    def api_monitor_settings():
        data = request.get_json(silent=True) or {}

        def _int_clamp(val, lo, hi, default):
            try:
                v = int(str(val).strip())
                return max(lo, min(hi, v))
            except (TypeError, ValueError):
                return default

        cpu_threshold = _int_clamp(data.get("cpu_threshold"), 1, 100, 90)
        ram_threshold = _int_clamp(data.get("ram_threshold"), 1, 100, 90)
        interval_sec  = _int_clamp(data.get("interval_seconds"), 10, 3600, 60)
        cooldown_min  = _int_clamp(data.get("cooldown_minutes"), 1, 1440, 30)

        set_env_value("MONITOR_CPU_THRESHOLD", str(cpu_threshold))
        set_env_value("MONITOR_RAM_THRESHOLD", str(ram_threshold))
        set_env_value("MONITOR_CHECK_INTERVAL_SECONDS", str(interval_sec))
        set_env_value("MONITOR_COOLDOWN_MINUTES", str(cooldown_min))
        os.environ["MONITOR_CPU_THRESHOLD"] = str(cpu_threshold)
        os.environ["MONITOR_RAM_THRESHOLD"] = str(ram_threshold)
        os.environ["MONITOR_CHECK_INTERVAL_SECONDS"] = str(interval_sec)
        os.environ["MONITOR_COOLDOWN_MINUTES"] = str(cooldown_min)

        log_user_action_event(
            "settings_monitor_update",
            target_type="monitor",
            target_name="resource_monitor",
            details=f"cpu={cpu_threshold}% ram={ram_threshold}% interval={interval_sec}с cooldown={cooldown_min}мин",
        )
        return jsonify({"success": True, "message": "Настройки мониторинга сохранены"})

    @app.route("/api/tg-notify-test", methods=["POST"])
    @auth_manager.admin_required
    def api_tg_notify_test():
        data = request.get_json(silent=True) or {}
        target_username = (data.get("username") or "").strip()
        current_username = session.get("username", "")
        if not target_username or target_username != current_username:
            return jsonify({"success": False, "message": "Тест разрешён только для собственного аккаунта"}), 403

        user = user_model.query.filter_by(username=target_username).first()
        if not user or not user.telegram_id:
            return jsonify({"success": False, "message": "Telegram ID не привязан"}), 400

        bot_token = (get_env_value("TELEGRAM_AUTH_BOT_TOKEN", "") or "").strip()
        if not bot_token:
            return jsonify({"success": False, "message": "Бот не настроен"}), 400

        _ev_labels = [
            ("login_success",   "Успешный вход"),
            ("login_failed",    "Неверный пароль"),
            ("tg_unlinked",     "Вход с непривязанным TG ID"),
            ("config_create",   "Создание / пересоздание конфига"),
            ("config_delete",   "Удаление конфига"),
            ("user_create",     "Добавление пользователя"),
            ("user_delete",     "Удаление пользователя"),
            ("client_ban",      "Блокировка / разблокировка клиента"),
            ("settings_change", "Изменение настроек"),
            ("high_cpu",        "Высокая нагрузка CPU"),
            ("high_ram",        "Высокая нагрузка RAM"),
        ]
        enabled = [label for key, label in _ev_labels if user.has_tg_notify_event(key)]
        events_text = "\n".join(f"  ✓ {l}" for l in enabled) if enabled else "  (нет включённых событий)"

        text = (
            "🔔 <b>Тест уведомлений AdminAntiZapret</b>\n\n"
            f"Аккаунт: <code>{target_username}</code>\n\n"
            f"Включённые события:\n{events_text}"
        )
        send_tg_message(bot_token, user.telegram_id, text)
        return jsonify({"success": True, "message": "Тестовое сообщение отправлено"})
