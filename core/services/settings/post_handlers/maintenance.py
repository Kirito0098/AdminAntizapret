import os
import re


def _form_getlist(form, key):
    getter = getattr(form, "getlist", None)
    if callable(getter):
        return getter(key)
    value = form.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


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


def handle_backup_settings(
    form,
    *,
    flash,
    to_bool,
    set_backup_settings,
    set_env_value,
    ensure_app_backup_cron,
    log_user_action_event,
):
    if form.get("backup_settings_action") != "save":
        return None

    enabled = to_bool((form.get("app_backup_enabled") or "false").strip().lower(), default=False)
    tg_enabled = to_bool((form.get("app_backup_tg_enabled") or "false").strip().lower(), default=False)

    interval_raw = (form.get("app_backup_interval_days") or "1").strip()
    time_raw = (form.get("app_backup_time_hhmm") or "03:00").strip()
    selected_components = [str(v).strip().lower() for v in _form_getlist(form, "app_backup_components")]
    selected_components = [v for v in selected_components if v in {"db", "env", "data"}]
    if not selected_components:
        selected_components = ["db", "env", "data"]

    selected_admin_ids = [str(v).strip() for v in _form_getlist(form, "app_backup_tg_admin_ids")]
    selected_admin_ids = [v for v in selected_admin_ids if v.isdigit()]

    if interval_raw not in {"1", "7", "30"}:
        flash("Интервал авто-бэкапа должен быть 1, 7 или 30 дней", "error")
        return None

    time_match = re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", time_raw)
    if not time_match:
        flash("Укажите время авто-бэкапа в формате ЧЧ:ММ", "error")
        return None

    components_csv = ",".join(selected_components)
    admin_ids_csv = ",".join(selected_admin_ids)
    interval_days = int(interval_raw)
    set_backup_settings(
        enabled=enabled,
        interval_days=interval_days,
        time_hhmm=time_raw,
        components=components_csv,
        tg_enabled=tg_enabled,
        tg_admin_ids=admin_ids_csv,
    )
    set_env_value("APP_BACKUP_ENABLED", "true" if enabled else "false")
    set_env_value("APP_BACKUP_INTERVAL_DAYS", str(interval_days))
    set_env_value("APP_BACKUP_TIME", time_raw)
    set_env_value("APP_BACKUP_COMPONENTS", components_csv)
    set_env_value("APP_BACKUP_TG_ENABLED", "true" if tg_enabled else "false")
    set_env_value("APP_BACKUP_TG_ADMIN_IDS", admin_ids_csv)

    os.environ["APP_BACKUP_ENABLED"] = "true" if enabled else "false"
    os.environ["APP_BACKUP_INTERVAL_DAYS"] = str(interval_days)
    os.environ["APP_BACKUP_TIME"] = time_raw
    os.environ["APP_BACKUP_COMPONENTS"] = components_csv
    os.environ["APP_BACKUP_TG_ENABLED"] = "true" if tg_enabled else "false"
    os.environ["APP_BACKUP_TG_ADMIN_IDS"] = admin_ids_csv

    cron_ok, cron_msg = ensure_app_backup_cron()
    if cron_ok:
        flash("Настройки авто-бэкапов сохранены", "success")
    else:
        flash(cron_msg, "error")
    log_user_action_event(
        "settings_backup_update",
        target_type="backup",
        target_name="app_backup",
        details=(
            f"enabled={'вкл' if enabled else 'выкл'} interval={interval_days}d "
            f"time={time_raw} components={components_csv} "
            f"tg={'вкл' if tg_enabled else 'выкл'} admins={admin_ids_csv or '-'}"
        ),
        status="success" if cron_ok else "warning",
    )
    return None


def handle_backup_create(
    form,
    *,
    flash,
    session,
    enqueue_background_task,
    backup_manager_service,
    get_backup_settings,
    log_user_action_event,
):
    if form.get("backup_create_action") != "create":
        return None

    backup_settings = get_backup_settings() or {}
    selected_components = str(backup_settings.get("components", "db,env,data")).split(",")
    selected_components = [item.strip().lower() for item in selected_components if item.strip()]

    try:
        def _task_create_backup():
            result = backup_manager_service.create_backup(
                selected_components=selected_components,
                trigger="manual",
            )
            return {
                "message": f"Бэкап создан: {result.get('archive_name', '')}",
                "output": str(result.get("archive_path", "")),
            }

        task = enqueue_background_task(
            "app_backup_create",
            _task_create_backup,
            created_by_username=session.get("username"),
            queued_message="Создание бэкапа поставлено в очередь",
        )
        flash(
            f"Создание бэкапа запущено в фоне (task: {task.id[:8]}).",
            "info",
        )
        log_user_action_event(
            "settings_backup_create",
            target_type="backup",
            target_name="manual_create",
        )
    except Exception as exc:
        flash(f"Ошибка запуска создания бэкапа: {exc}", "error")
    return None


def handle_backup_restore(
    form,
    *,
    flash,
    session,
    enqueue_background_task,
    backup_manager_service,
    log_user_action_event,
):
    if form.get("backup_restore_action") != "restore":
        return None

    backup_file_name = (form.get("backup_file_name") or "").strip()
    if not backup_file_name:
        flash("Не выбран файл бэкапа для восстановления", "error")
        return None

    try:
        def _task_restore_backup():
            result = backup_manager_service.restore_backup(backup_file_name)
            return {
                "message": "Восстановление из бэкапа завершено",
                "output": str(result.get("archive_path", "")),
            }

        task = enqueue_background_task(
            "app_backup_restore",
            _task_restore_backup,
            created_by_username=session.get("username"),
            queued_message="Восстановление из бэкапа поставлено в очередь",
        )
        flash(
            (
                f"Восстановление из бэкапа запущено в фоне (task: {task.id[:8]}). "
                "Сервис будет перезапущен автоматически."
            ),
            "warning",
        )
        log_user_action_event(
            "settings_backup_restore",
            target_type="backup",
            target_name=backup_file_name,
        )
    except Exception as exc:
        flash(f"Ошибка запуска восстановления бэкапа: {exc}", "error")
    return None


def handle_backup_delete(
    form,
    *,
    flash,
    backup_manager_service,
    log_user_action_event,
):
    if form.get("backup_delete_action") != "delete":
        return None

    backup_file_name = (form.get("backup_file_name") or "").strip()
    if not backup_file_name:
        flash("Не выбран файл бэкапа для удаления", "error")
        return None

    try:
        backup_manager_service.delete_backup(backup_file_name)
        flash(f"Бэкап удалён: {backup_file_name}", "success")
        log_user_action_event(
            "settings_backup_delete",
            target_type="backup",
            target_name=backup_file_name,
        )
    except Exception as exc:
        flash(f"Ошибка удаления бэкапа: {exc}", "error")
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
