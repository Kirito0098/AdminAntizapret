import os
import platform
import re
import subprocess
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, request, session, url_for


def register_settings_routes(
    app,
    *,
    auth_manager,
    db,
    user_model,
    active_web_session_model,
    qr_download_audit_log_model,
    ip_restriction,
    ip_manager,
    collect_all_openvpn_files_for_access,
    build_openvpn_access_groups,
    config_file_handler,
    group_folders,
    build_conf_access_groups,
    enqueue_background_task,
    task_restart_service,
    set_env_value,
    get_env_value,
    to_bool,
    is_valid_cron_expression,
    ensure_nightly_idle_restart_cron,
    get_nightly_idle_restart_settings,
    set_nightly_idle_restart_settings,
    get_active_web_session_settings,
    set_active_web_session_settings,
    get_public_download_enabled,
):
    @app.route("/settings", methods=["GET", "POST"])
    @auth_manager.admin_required
    def settings():
        if request.method == "POST":
            new_port = request.form.get("port")
            if new_port and new_port.isdigit():
                env_path = os.path.join(app.root_path, ".env")
                with open(env_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
                with open(env_path, "w", encoding="utf-8") as file:
                    for line in lines:
                        if line.startswith("APP_PORT="):
                            file.write(f"APP_PORT={new_port}\n")
                        else:
                            file.write(line)
                flash("Порт успешно изменён. Перезапуск службы...", "success")

                try:
                    if platform.system() == "Linux":
                        subprocess.run(
                            ["systemctl", "restart", "admin-antizapret.service"], check=True
                        )
                except subprocess.CalledProcessError as e:
                    flash(f"Ошибка при перезапуске службы: {e}", "error")

            ttl_raw = request.form.get("qr_download_token_ttl_seconds", "").strip()
            if ttl_raw:
                if ttl_raw.isdigit():
                    ttl_value = int(ttl_raw)
                    if 60 <= ttl_value <= 3600:
                        set_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", str(ttl_value))
                        os.environ["QR_DOWNLOAD_TOKEN_TTL_SECONDS"] = str(ttl_value)
                        flash("TTL одноразовой QR-ссылки обновлен", "success")
                    else:
                        flash("TTL QR-ссылки должен быть в диапазоне 60..3600 секунд", "error")
                else:
                    flash("TTL QR-ссылки должен быть целым числом", "error")

            max_downloads_raw = request.form.get("qr_download_token_max_downloads", "").strip()
            if max_downloads_raw:
                if max_downloads_raw.isdigit() and int(max_downloads_raw) in (1, 3, 5):
                    set_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", max_downloads_raw)
                    os.environ["QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS"] = max_downloads_raw
                    flash("Лимит скачиваний одноразовой ссылки обновлен", "success")
                else:
                    flash("Лимит скачиваний должен быть одним из значений: 1, 3 или 5", "error")

            clear_pin = request.form.get("clear_qr_download_pin") == "on"
            pin_raw = (request.form.get("qr_download_pin") or "").strip()
            if clear_pin:
                set_env_value("QR_DOWNLOAD_PIN", "")
                os.environ["QR_DOWNLOAD_PIN"] = ""
                flash("PIN для QR-ссылок очищен", "success")
            elif pin_raw:
                if pin_raw.isdigit() and 4 <= len(pin_raw) <= 12:
                    set_env_value("QR_DOWNLOAD_PIN", pin_raw)
                    os.environ["QR_DOWNLOAD_PIN"] = pin_raw
                    flash("PIN для QR-ссылок обновлен", "success")
                else:
                    flash("PIN должен содержать только цифры и иметь длину от 4 до 12", "error")

            if request.form.get("nightly_settings_action") == "save":
                nightly_enabled_raw = (request.form.get("nightly_idle_restart_enabled") or "true").strip().lower()
                nightly_enabled = to_bool(nightly_enabled_raw, default=True)

                ttl_raw = (request.form.get("active_web_session_ttl_seconds") or "").strip()
                touch_raw = (request.form.get("active_web_session_touch_interval_seconds") or "").strip()
                nightly_time_raw = (request.form.get("nightly_idle_restart_time") or "").strip()
                cron_expr_raw = (request.form.get("nightly_idle_restart_cron") or "").strip()

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

            username = request.form.get("username")
            password = request.form.get("password")
            if username and password:
                if len(password) < 8:
                    flash("Пароль должен содержать минимум 8 символов!", "error")
                else:
                    role = request.form.get("role", "admin")
                    if role not in ("admin", "viewer"):
                        role = "admin"
                    if user_model.query.filter_by(username=username).first():
                        flash(f"Пользователь '{username}' уже существует!", "error")
                    else:
                        user = user_model(username=username, role=role)
                        user.set_password(password)
                        db.session.add(user)
                        db.session.commit()
                        flash(f"Пользователь '{username}' ({role}) успешно добавлен!", "success")

            delete_username = request.form.get("delete_username")
            if delete_username:
                if delete_username == session.get("username"):
                    flash("Нельзя удалить собственный аккаунт!", "error")
                else:
                    user = user_model.query.filter_by(username=delete_username).first()
                    if user:
                        db.session.delete(user)
                        db.session.commit()
                        flash(f"Пользователь '{delete_username}' успешно удалён!", "success")
                    else:
                        flash(f"Пользователь '{delete_username}' не найден!", "error")

            change_role_username = request.form.get("change_role_username")
            new_role = request.form.get("new_role")
            if change_role_username and new_role:
                if new_role not in ("admin", "viewer"):
                    flash("Неверная роль!", "error")
                elif change_role_username == session.get("username"):
                    flash("Нельзя изменить собственную роль!", "error")
                else:
                    role_user = user_model.query.filter_by(username=change_role_username).first()
                    if role_user:
                        role_user.role = new_role
                        db.session.commit()
                        flash(f"Роль пользователя '{change_role_username}' изменена на '{new_role}'!", "success")
                    else:
                        flash(f"Пользователь '{change_role_username}' не найден!", "error")

            change_password_username = request.form.get("change_password_username")
            new_password = request.form.get("new_password")
            if change_password_username and new_password:
                if len(new_password) < 8:
                    flash("Пароль должен содержать минимум 8 символов!", "error")
                else:
                    pw_user = user_model.query.filter_by(username=change_password_username).first()
                    if pw_user:
                        pw_user.set_password(new_password)
                        db.session.commit()
                        flash(f"Пароль пользователя '{change_password_username}' изменён!", "success")
                    else:
                        flash(f"Пользователь '{change_password_username}' не найден!", "error")

            ip_action = request.form.get("ip_action")

            if ip_action == "add_ip":
                new_ip = request.form.get("new_ip", "").strip()
                if new_ip:
                    if ip_restriction.add_ip(new_ip):
                        flash(f"IP {new_ip} добавлен", "success")
                    else:
                        flash("Неверный формат IP", "error")

            elif ip_action == "remove_ip":
                ip_to_remove = request.form.get("ip_to_remove", "").strip()
                if ip_to_remove:
                    if ip_restriction.remove_ip(ip_to_remove):
                        flash(f"IP {ip_to_remove} удален", "success")
                    else:
                        flash("IP не найден", "error")

            elif ip_action == "clear_all_ips":
                ip_restriction.clear_all()
                flash("Все IP ограничения сброшены (доступ разрешен всем)", "success")

            elif ip_action == "enable_ips":
                ips_text = request.form.get("ips_text", "").strip()
                if ips_text:
                    ip_restriction.clear_all()
                    for ip in ips_text.split(","):
                        ip_restriction.add_ip(ip.strip())
                    flash("IP ограничения включены", "success")
                else:
                    flash("Укажите хотя бы один IP-адрес", "error")

            file_action = request.form.get("file_action")

            if file_action == "add_from_file":
                ip_file = request.form.get("ip_file", "").strip()
                if ip_file:
                    try:
                        added_count = ip_manager.add_from_file(ip_file)
                        flash(f"Добавлено {added_count} IP из файла {ip_file}", "success")
                    except FileNotFoundError:
                        flash("Файл не найден", "error")
                    except Exception as e:
                        flash(f"Ошибка при добавлении IP: {e}", "error")
                else:
                    flash("Выберите файл", "error")

            elif file_action in ("enable_file", "disable_file"):
                ip_file = request.form.get("ip_file", "").strip()
                if ip_file:
                    try:
                        if file_action == "enable_file":
                            cnt = ip_manager.enable_file(ip_file)
                            flash(f"Добавлено {cnt} IP из файла {ip_file}", "success")
                        else:
                            cnt = ip_manager.disable_file(ip_file)
                            flash(f"Удалено {cnt} IP из файла {ip_file}", "success")
                    except FileNotFoundError:
                        flash("Файл не найден", "error")
                    except Exception as e:
                        flash(f"Ошибка при обработке файла: {e}", "error")
                else:
                    flash("Не указан файл", "error")

            restart_action = request.form.get("restart_action")

            if restart_action == "restart_service":
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
                except Exception as e:
                    flash(f"Ошибка запуска фонового перезапуска: {str(e)}", "error")

            return redirect(url_for("settings"))

        current_port = os.getenv("APP_PORT", "5050")
        qr_download_token_ttl_seconds = get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600")
        qr_download_token_max_downloads = get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1")
        qr_download_pin_set = bool((get_env_value("QR_DOWNLOAD_PIN", "") or "").strip())

        nightly_idle_restart_enabled, nightly_idle_restart_cron = get_nightly_idle_restart_settings()
        nightly_idle_restart_time = "04:00"
        cron_parts = (nightly_idle_restart_cron or "").split()
        if len(cron_parts) == 5 and cron_parts[0].isdigit() and cron_parts[1].isdigit():
            minute_value = int(cron_parts[0])
            hour_value = int(cron_parts[1])
            if 0 <= minute_value <= 59 and 0 <= hour_value <= 23:
                nightly_idle_restart_time = f"{hour_value:02d}:{minute_value:02d}"

        active_web_session_ttl_seconds, active_web_session_touch_interval_seconds = get_active_web_session_settings()
        active_web_sessions_count = active_web_session_model.query.filter(
            active_web_session_model.last_seen_at >= datetime.utcnow() - timedelta(seconds=active_web_session_ttl_seconds)
        ).count()

        qr_download_audit_logs = qr_download_audit_log_model.query.order_by(
            qr_download_audit_log_model.created_at.desc()
        ).limit(100).all()
        users = user_model.query.all()
        viewer_users = user_model.query.filter_by(role="viewer").all()

        all_openvpn = collect_all_openvpn_files_for_access()
        openvpn_access_groups = build_openvpn_access_groups(all_openvpn)

        orig_paths = config_file_handler.config_paths["openvpn"]
        try:
            config_file_handler.config_paths["openvpn"] = [d for g in group_folders.values() for d in g]
            _, all_wg, all_amneziawg = config_file_handler.get_config_files()
        finally:
            config_file_handler.config_paths["openvpn"] = orig_paths

        wg_access_groups = build_conf_access_groups(all_wg, "wg")
        amneziawg_access_groups = build_conf_access_groups(all_amneziawg, "amneziawg")

        viewer_access = {vu.id: {acc.config_name for acc in vu.allowed_configs} for vu in viewer_users}

        allowed_ips = ip_restriction.get_allowed_ips()
        ip_enabled = ip_restriction.is_enabled()
        current_ip = ip_restriction.get_client_ip()

        ip_manager.sync_enabled()
        ip_files = ip_manager.list_ip_files()
        ip_file_states = ip_manager.get_file_states()

        return render_template(
            "settings.html",
            port=current_port,
            users=users,
            viewer_users=viewer_users,
            allowed_ips=allowed_ips,
            ip_enabled=ip_enabled,
            current_ip=current_ip,
            ip_files=ip_files,
            ip_file_states=ip_file_states,
            all_openvpn=all_openvpn,
            openvpn_access_groups=openvpn_access_groups,
            all_wg=all_wg,
            all_amneziawg=all_amneziawg,
            wg_access_groups=wg_access_groups,
            amneziawg_access_groups=amneziawg_access_groups,
            viewer_access=viewer_access,
            public_download_enabled=get_public_download_enabled(),
            qr_download_token_ttl_seconds=qr_download_token_ttl_seconds,
            qr_download_token_max_downloads=qr_download_token_max_downloads,
            qr_download_pin_set=qr_download_pin_set,
            nightly_idle_restart_enabled=nightly_idle_restart_enabled,
            nightly_idle_restart_cron=nightly_idle_restart_cron,
            nightly_idle_restart_time=nightly_idle_restart_time,
            active_web_session_ttl_seconds=active_web_session_ttl_seconds,
            active_web_session_touch_interval_seconds=active_web_session_touch_interval_seconds,
            active_web_sessions_count=active_web_sessions_count,
            qr_download_audit_logs=qr_download_audit_logs,
        )
