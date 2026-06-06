import os


def handle_feature_toggles_settings(
    form,
    *,
    flash,
    to_bool,
    set_env_value,
    runtime_set,
    maintenance_scheduler_service,
    ensure_traffic_sync_cron,
    ensure_wg_policy_sync_cron,
    ensure_runtime_backup_cleanup_cron,
    ensure_app_backup_cron=None,
    log_user_action_event,
):
    if form.get("feature_toggles_action") != "save":
        return None

    from core.services.feature_toggles import FEATURE_TOGGLES, apply_feature_toggle_settings

    form_values = {}
    for item in FEATURE_TOGGLES:
        raw = (form.get(f"feature_toggle_{item.key}") or ("true" if item.default else "false")).strip()
        form_values[item.key] = to_bool(raw, default=item.default)

    ok, details = apply_feature_toggle_settings(
        form_values=form_values,
        set_env_value=set_env_value,
        runtime_set=runtime_set,
        maintenance_scheduler_service=maintenance_scheduler_service,
        ensure_traffic_sync_cron=ensure_traffic_sync_cron,
        ensure_wg_policy_sync_cron=ensure_wg_policy_sync_cron,
        ensure_runtime_backup_cleanup_cron=ensure_runtime_backup_cleanup_cron,
        ensure_app_backup_cron=ensure_app_backup_cron,
    )
    if not ok:
        flash(details, "error")
        return None

    for item in FEATURE_TOGGLES:
        env_value = "true" if form_values[item.key] else "false"
        os.environ[item.env_key] = env_value

    log_user_action_event(
        "settings_feature_toggles_update",
        target_type="feature_toggles",
        target_name="feature_modules",
        details=details,
    )
    flash("Настройки модулей сохранены", "success")
    return None
