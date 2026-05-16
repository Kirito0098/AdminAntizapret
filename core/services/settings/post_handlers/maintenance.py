import os
import re


def handle_maintenance_settings(
    form,
    *,
    flash,
    to_bool,
    is_valid_cron_expression,
    ensure_nightly_idle_restart_cron,
    get_active_web_session_settings,
    set_nightly_idle_restart_settings,
    set_active_web_session_settings,
    set_env_value,
    log_user_action_event,
):
    if form.get("nightly_settings_action") != "save":
        return None

    nightly_enabled_raw = (form.get("nightly_idle_restart_enabled") or "true").strip().lower()
    nightly_enabled = to_bool(nightly_enabled_raw, default=True)

    ttl_raw = (form.get("active_web_session_ttl_seconds") or "").strip()
    touch_raw = (form.get("active_web_session_touch_interval_seconds") or "").strip()
    nightly_time_raw = (form.get("nightly_idle_restart_time") or "").strip()
    cron_expr_raw = (form.get("nightly_idle_restart_cron") or "").strip()

    has_error = False

    cron_expr = ""
    if nightly_time_raw:
        time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", nightly_time_raw)
        if time_match:
            hour_value = int(time_match.group(1))
            minute_value = int(time_match.group(2))
            cron_expr = f"{minute_value} {hour_value} * * *"
        else:
            flash("Укажите время в формате ЧЧ:ММ (например, 04:00)", "error")
            has_error = True

    if not cron_expr:
        cron_expr = cron_expr_raw or "0 4 * * *"

    if not is_valid_cron_expression(cron_expr):
        flash("Cron-выражение должно состоять из 5 полей и содержать только цифры и символы */,-", "error")
        has_error = True

    active_ttl_seconds, active_touch_interval_seconds = get_active_web_session_settings()
    ttl_value = active_ttl_seconds
    if ttl_raw:
        if ttl_raw.isdigit() and 30 <= int(ttl_raw) <= 86400:
            ttl_value = int(ttl_raw)
        else:
            flash("TTL активной сессии должен быть целым числом в диапазоне 30..86400 секунд", "error")
            has_error = True

    touch_value = active_touch_interval_seconds
    if touch_raw:
        if touch_raw.isdigit() and 1 <= int(touch_raw) <= 3600:
            touch_value = int(touch_raw)
        else:
            flash("Интервал heartbeat должен быть целым числом в диапазоне 1..3600 секунд", "error")
            has_error = True

    if not has_error:
        set_nightly_idle_restart_settings(nightly_enabled, cron_expr)
        set_active_web_session_settings(ttl_value, touch_value)

        env_enabled = "true" if nightly_enabled else "false"
        set_env_value("NIGHTLY_IDLE_RESTART_ENABLED", env_enabled)
        set_env_value("NIGHTLY_IDLE_RESTART_CRON", cron_expr)
        set_env_value("ACTIVE_WEB_SESSION_TTL_SECONDS", str(ttl_value))
        set_env_value("ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS", str(touch_value))

        os.environ["NIGHTLY_IDLE_RESTART_ENABLED"] = env_enabled
        os.environ["NIGHTLY_IDLE_RESTART_CRON"] = cron_expr
        os.environ["ACTIVE_WEB_SESSION_TTL_SECONDS"] = str(ttl_value)
        os.environ["ACTIVE_WEB_SESSION_TOUCH_INTERVAL_SECONDS"] = str(touch_value)

        cron_ok, cron_msg = ensure_nightly_idle_restart_cron()
        if cron_ok:
            flash("Настройки ночного рестарта сохранены", "success")
        else:
            flash(cron_msg, "error")
        log_user_action_event(
            "settings_nightly_update",
            target_type="maintenance",
            target_name="nightly_idle_restart",
            details=(
                f"enabled={'вкл' if nightly_enabled else 'выкл'} "
                f"cron={cron_expr} ttl={ttl_value}с touch={touch_value}с"
            ),
            status="success" if cron_ok else "warning",
        )
    return None


def handle_restart_service(
    form,
    *,
    flash,
    session,
    enqueue_background_task,
    task_restart_service,
    log_user_action_event,
):
    if form.get("restart_action") != "restart_service":
        return None

    try:
        task = enqueue_background_task(
            "restart_service",
            task_restart_service,
            created_by_username=session.get("username"),
            queued_message="Перезапуск службы поставлен в очередь",
        )
        flash(
            f"Перезапуск службы запущен в фоне (task: {task.id[:8]}). Обновите страницу через 10-20 секунд.",
            "info",
        )
        log_user_action_event(
            "settings_restart_service",
            target_type="service",
            target_name="admin-antizapret.service",
        )
    except Exception as e:
        flash(f"Ошибка запуска фонового перезапуска: {str(e)}", "error")
    return None
