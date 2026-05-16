import json as _json

from core.services.settings.telegram_normalize import normalize_telegram_id


def handle_users_settings(
    form,
    *,
    flash,
    session,
    db,
    user_model,
    log_user_action_event,
    redirect_url,
):
    username = form.get("username")
    password = form.get("password")
    if username and password:
        if len(password) < 8:
            flash("Пароль должен содержать минимум 8 символов!", "error")
        else:
            role = form.get("role", "admin")
            if role not in ("admin", "viewer"):
                role = "admin"
            telegram_id_raw = form.get("telegram_id", "")
            normalized_telegram_id, tg_error = normalize_telegram_id(telegram_id_raw)

            if tg_error:
                flash(tg_error, "error")
            elif user_model.query.filter_by(username=username).first():
                flash(f"Пользователь '{username}' уже существует!", "error")
            elif normalized_telegram_id and user_model.query.filter_by(telegram_id=normalized_telegram_id).first():
                flash(f"Telegram ID {normalized_telegram_id} уже привязан к другому пользователю!", "error")
            else:
                user = user_model(
                    username=username,
                    role=role,
                    telegram_id=normalized_telegram_id or None,
                )
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                flash(f"Пользователь '{username}' ({role}) успешно добавлен!", "success")
                log_user_action_event(
                    "settings_user_create",
                    target_type="user",
                    target_name=username,
                    details=f"роль={role}" + (f" TG={normalized_telegram_id}" if normalized_telegram_id else ""),
                )

    change_tg_notify_username = form.get("change_tg_notify_username")
    if change_tg_notify_username:
        notify_user = user_model.query.filter_by(username=change_tg_notify_username).first()
        if notify_user:
            _ev_keys = [
                "login_success", "login_failed", "tg_unlinked",
                "config_create", "config_delete",
                "user_create", "user_delete",
                "client_ban", "settings_change",
                "high_cpu", "high_ram",
            ]
            events = {k: (form.get(f"tg_e_{k}") == "1") for k in _ev_keys}
            notify_user.tg_notify_events = _json.dumps(events)
            db.session.commit()
            flash(f"Настройки уведомлений для '{change_tg_notify_username}' сохранены", "success")
            log_user_action_event(
                "settings_user_tg_notify_update",
                target_type="user",
                target_name=change_tg_notify_username,
                details=_json.dumps({k: v for k, v in events.items() if v}),
            )
        else:
            flash(f"Пользователь '{change_tg_notify_username}' не найден!", "error")

    change_telegram_username = form.get("change_telegram_username")
    if change_telegram_username:
        tg_user = user_model.query.filter_by(username=change_telegram_username).first()
        if not tg_user:
            flash(f"Пользователь '{change_telegram_username}' не найден!", "error")
        else:
            new_telegram_id_raw = form.get("new_telegram_id", "")
            normalized_telegram_id, tg_error = normalize_telegram_id(new_telegram_id_raw)
            if tg_error:
                flash(tg_error, "error")
            else:
                if normalized_telegram_id:
                    owner = user_model.query.filter(
                        user_model.telegram_id == normalized_telegram_id,
                        user_model.username != change_telegram_username,
                    ).first()
                    if owner:
                        flash(
                            f"Telegram ID {normalized_telegram_id} уже привязан к пользователю '{owner.username}'",
                            "error",
                        )
                        return redirect_url

                old_telegram_id = tg_user.telegram_id or "—"
                tg_user.telegram_id = normalized_telegram_id or None
                db.session.commit()
                if normalized_telegram_id:
                    flash(
                        f"Telegram ID пользователя '{change_telegram_username}' обновлён",
                        "success",
                    )
                else:
                    flash(
                        f"Telegram ID пользователя '{change_telegram_username}' очищен",
                        "success",
                    )
                log_user_action_event(
                    "settings_user_telegram_update",
                    target_type="user",
                    target_name=change_telegram_username,
                    details=f"{old_telegram_id} → {normalized_telegram_id or '—'}",
                )

    delete_username = form.get("delete_username")
    if delete_username:
        if delete_username == session.get("username"):
            flash("Нельзя удалить собственный аккаунт!", "error")
        else:
            user = user_model.query.filter_by(username=delete_username).first()
            if user:
                db.session.delete(user)
                db.session.commit()
                flash(f"Пользователь '{delete_username}' успешно удалён!", "success")
                log_user_action_event(
                    "settings_user_delete",
                    target_type="user",
                    target_name=delete_username,
                )
            else:
                flash(f"Пользователь '{delete_username}' не найден!", "error")

    change_role_username = form.get("change_role_username")
    new_role = form.get("new_role")
    if change_role_username and new_role:
        if new_role not in ("admin", "viewer"):
            flash("Неверная роль!", "error")
        elif change_role_username == session.get("username"):
            flash("Нельзя изменить собственную роль!", "error")
        else:
            role_user = user_model.query.filter_by(username=change_role_username).first()
            if role_user:
                old_role = role_user.role
                role_user.role = new_role
                db.session.commit()
                flash(f"Роль пользователя '{change_role_username}' изменена на '{new_role}'!", "success")
                log_user_action_event(
                    "settings_user_role_update",
                    target_type="user",
                    target_name=change_role_username,
                    details=f"{old_role} → {new_role}",
                )
            else:
                flash(f"Пользователь '{change_role_username}' не найден!", "error")

    change_password_username = form.get("change_password_username")
    new_password = form.get("new_password")
    if change_password_username and new_password:
        if len(new_password) < 8:
            flash("Пароль должен содержать минимум 8 символов!", "error")
        else:
            pw_user = user_model.query.filter_by(username=change_password_username).first()
            if pw_user:
                pw_user.set_password(new_password)
                db.session.commit()
                flash(f"Пароль пользователя '{change_password_username}' изменён!", "success")
                log_user_action_event(
                    "settings_user_password_update",
                    target_type="user",
                    target_name=change_password_username,
                    details="пароль изменён",
                )
            else:
                flash(f"Пользователь '{change_password_username}' не найден!", "error")

    return None
