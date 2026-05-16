import hashlib
import os
import re
from datetime import datetime

from flask import (
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import case
from werkzeug.exceptions import HTTPException

from core.services.request_user import get_current_user
from tg_mini.services.config_delivery import build_short_download_name
from tg_mini.session import has_telegram_mini_session


def register_config_routes(
    app,
    *,
    auth_manager,
    file_validator,
    db,
    user_model,
    viewer_config_access_model,
    qr_download_token_model,
    client_name_pattern,
    group_folders,
    result_dir_files,
    ensure_client_connect_ban_check_block,
    read_banned_clients,
    write_banned_clients,
    get_config_type,
    resolve_config_file,
    create_one_time_download_url,
    log_qr_event,
    qr_generator,
    enqueue_background_task,
    task_run_doall,
    task_accepted_response,
    io_executor,
    set_env_value,
    get_public_download_enabled,
    set_public_download_enabled,
    log_telegram_audit_event,
    log_user_action_event,
) -> None:
    def _has_telegram_mini_session() -> bool:
        return has_telegram_mini_session(session)

    @app.route("/api/openvpn/client-block", methods=["POST"])
    @auth_manager.admin_required
    def api_openvpn_client_block():
        client_name = request.form.get("client_name", "").strip()
        blocked_raw = (request.form.get("blocked", "").strip().lower())

        if not client_name_pattern.fullmatch(client_name):
            return jsonify({"success": False, "message": "Некорректный CN клиента."}), 400

        should_block = blocked_raw in {"1", "true", "yes", "on"}

        try:
            ensure_client_connect_ban_check_block()
            banned_clients = read_banned_clients()

            if should_block:
                banned_clients.add(client_name)
            else:
                banned_clients.discard(client_name)

            write_banned_clients(banned_clients)
            is_tg_mini_action = _has_telegram_mini_session()
            details_text = f"blocked={1 if should_block else 0}"
            if is_tg_mini_action:
                log_telegram_audit_event(
                    "mini_openvpn_block_toggle",
                    config_name=client_name,
                    details=details_text,
                )
                details_text += " via=tg-mini"

            log_user_action_event(
                "openvpn_client_block_toggle",
                target_type="openvpn",
                target_name=client_name,
                details=details_text,
            )
            return jsonify(
                {
                    "success": True,
                    "client_name": client_name,
                    "blocked": should_block,
                    "message": "Клиент заблокирован." if should_block else "Блокировка снята.",
                }
            )
        except PermissionError:
            return jsonify({"success": False, "message": "Нет прав на запись banned_clients."}), 500
        except OSError as e:
            return jsonify({"success": False, "message": f"Ошибка работы с banned_clients: {e}"}), 500

    @app.route("/set_openvpn_group", methods=["POST"])
    @auth_manager.login_required
    def set_openvpn_group():
        grp = request.form.get("group", "GROUP_UDP\\TCP")
        if grp not in group_folders:
            grp = "GROUP_UDP\\TCP"
        session["openvpn_group"] = grp
        return redirect(url_for("index"))

    @app.route("/qr_download/<token>", methods=["GET", "POST"])
    def one_time_qr_download(token):
        if not token or len(token) < 16:
            abort(404)

        now = datetime.utcnow()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        def _render_pin_page(error=None, remaining=0, status_code=200):
            response = make_response(
                render_template("qr_download_pin.html", error=error, remaining=remaining),
                status_code,
            )
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        try:
            token_row = qr_download_token_model.query.filter_by(token_hash=token_hash).first()
            if not token_row:
                log_qr_event("download_not_found", details="token_not_found")
                abort(410, description="Ссылка истекла или уже использована")

            if token_row.expires_at < now:
                log_qr_event("download_expired", token_row=token_row, details="token_expired")
                abort(410, description="Ссылка истекла или уже использована")

            if token_row.download_count >= token_row.max_downloads:
                log_qr_event("download_limit_reached", token_row=token_row, details="limit_reached")
                abort(410, description="Ссылка истекла или уже использована")

            if token_row.pin_hash:
                remaining = max(token_row.max_downloads - token_row.download_count, 0)
                if request.method != "POST":
                    return _render_pin_page(error=None, remaining=remaining)

                pin = (request.form.get("pin") or "").strip()
                if not pin:
                    return _render_pin_page(error="Введите PIN", remaining=remaining, status_code=400)

                pin_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
                if pin_hash != token_row.pin_hash:
                    log_qr_event("download_pin_invalid", token_row=token_row, details="invalid_pin")
                    return _render_pin_page(error="Неверный PIN", remaining=remaining, status_code=403)

            updated = db.session.query(qr_download_token_model).filter(
                qr_download_token_model.id == token_row.id,
                qr_download_token_model.expires_at >= now,
                qr_download_token_model.download_count < qr_download_token_model.max_downloads,
            ).update(
                {
                    "used_at": case((qr_download_token_model.used_at.is_(None), now), else_=qr_download_token_model.used_at),
                    "download_count": qr_download_token_model.download_count + 1,
                },
                synchronize_session=False,
            )

            if updated != 1:
                db.session.rollback()
                log_qr_event("download_limit_reached", token_row=token_row, details="race_limit_reached")
                abort(410, description="Ссылка уже использована")

            db.session.commit()
            log_qr_event("download_success", token_row=token_row, details=f"count+1/{token_row.max_downloads}")

            file_path, _ = resolve_config_file(token_row.config_type, token_row.config_name)
            if not file_path:
                log_qr_event("download_file_missing", token_row=token_row, details="file_not_found")
                abort(404, description="Файл не найден")

            base = os.path.basename(file_path)
            log_user_action_event(
                "config_download",
                target_type=str(token_row.config_type or "config"),
                target_name=base,
                details="channel=qr_one_time",
            )
            return send_from_directory(
                os.path.dirname(file_path),
                base,
                as_attachment=True,
                download_name=base,
            )
        except HTTPException:
            raise

    @app.route("/download/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def download(file_path, clean_name):
        _ = clean_name
        user = get_current_user(user_model)
        if user and user.role == "viewer":
            cfg_type = get_config_type(file_path)
            if cfg_type not in ("openvpn", "wg", "amneziawg"):
                abort(403)
            cfg_name = os.path.basename(file_path)
            access = viewer_config_access_model.query.filter_by(
                user_id=user.id,
                config_type=cfg_type,
                config_name=cfg_name,
            ).first()
            if not access:
                abort(403)

        base = os.path.basename(file_path)
        download_name = build_short_download_name(file_path)
        log_user_action_event(
            "config_download",
            target_type=str(get_config_type(file_path) or "config"),
            target_name=base,
            details=f"channel=web filename={download_name}",
        )
        return send_from_directory(
            os.path.dirname(file_path),
            base,
            as_attachment=True,
            download_name=download_name,
        )
    @app.route("/public_download/<router>")
    def public_download(router):
        if not get_public_download_enabled():
            abort(404)
        filename = result_dir_files.get(router)
        if not filename:
            abort(404)

        log_user_action_event(
            "config_download",
            target_type="public",
            target_name=filename,
            details=f"channel=public router={router}",
        )

        return send_from_directory("/root/antizapret/result", filename, as_attachment=True)

    @app.route("/toggle_public_download", methods=["POST"])
    @auth_manager.admin_required
    def toggle_public_download():
        enabled_value = request.form.get("enabled", "").lower()
        current_state = get_public_download_enabled()
        if enabled_value in ("true", "false"):
            next_state = enabled_value == "true"
        else:
            next_state = not current_state

        set_public_download_enabled(next_state)
        env_value = "true" if next_state else "false"
        set_env_value("PUBLIC_DOWNLOAD_ENABLED", env_value)
        os.environ["PUBLIC_DOWNLOAD_ENABLED"] = env_value
        log_user_action_event(
            "settings_public_download_toggle",
            target_type="public_download",
            target_name="PUBLIC_DOWNLOAD_ENABLED",
            details=f"{'вкл' if current_state else 'выкл'} → {'вкл' if next_state else 'выкл'}",
        )

        flash(
            "Публичный доступ к файлам включен." if next_state else "Публичный доступ к файлам выключен.",
            "success",
        )
        return_to = request.form.get("return_to", "edit_files")
        if return_to not in ("edit_files", "settings"):
            return_to = "edit_files"
        return redirect(url_for(return_to))

    @app.route("/generate_qr/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def generate_qr(file_path, clean_name):
        _ = clean_name
        user = get_current_user(user_model)
        if user and user.role == "viewer":
            cfg_type = get_config_type(file_path)
            if cfg_type not in ("openvpn", "wg", "amneziawg"):
                abort(403)
            cfg_name = os.path.basename(file_path)
            access = viewer_config_access_model.query.filter_by(
                user_id=user.id,
                config_type=cfg_type,
                config_name=cfg_name,
            ).first()
            if not access:
                abort(403)
        with open(file_path, "r") as file:
            config_text = file.read()

        config_type = get_config_type(file_path)
        force_download_url_qr = (
            config_type == "amneziawg" and len(config_text.encode("utf-8")) > 2200
        )

        if force_download_url_qr:
            download_url = create_one_time_download_url(file_path)
            img_byte_arr = qr_generator.generate_qr_for_download_url(download_url)
            response = send_file(img_byte_arr, mimetype="image/png")
            response.headers["X-QR-Mode"] = "download-url"
            response.headers["X-QR-Message-Code"] = "CONFIG_TOO_LARGE_USE_DOWNLOAD"
            response.headers["X-QR-Download-Url"] = download_url
            return response

        try:
            img_byte_arr = qr_generator.generate_qr_code(config_text)
            response = send_file(img_byte_arr, mimetype="image/png")
            response.headers["X-QR-Mode"] = "config"
            return response
        except ValueError as qr_error:
            if "слишком длинная" in str(qr_error):
                download_url = create_one_time_download_url(file_path)
                img_byte_arr = qr_generator.generate_qr_for_download_url(download_url)
                response = send_file(img_byte_arr, mimetype="image/png")
                response.headers["X-QR-Mode"] = "download-url"
                response.headers["X-QR-Message-Code"] = "CONFIG_OVERFLOW_USE_DOWNLOAD"
                response.headers["X-QR-Download-Url"] = download_url
                return response
            raise

    @app.route("/generate_one_time_download/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def generate_one_time_download(file_path, clean_name):
        _ = clean_name
        user = get_current_user(user_model)
        if not user or user.role != "admin":
            return jsonify({"success": False, "message": "Доступ запрещён."}), 403

        try:
            download_url = create_one_time_download_url(file_path)
            return jsonify(
                {
                    "success": True,
                    "download_url": download_url,
                }
            )
        except HTTPException:
            raise
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400

    @app.route("/run-doall", methods=["POST"])
    @auth_manager.admin_required
    def run_doall():
        try:
            _body = request.get_json(silent=True) or {}
            _context = (_body.get("context") or "").strip()[:300] or None

            task = enqueue_background_task(
                "run_doall",
                task_run_doall,
                created_by_username=session.get("username"),
                queued_message="Запуск doall поставлен в очередь",
            )
            is_tg_mini_action = _has_telegram_mini_session()
            if is_tg_mini_action:
                log_telegram_audit_event(
                    "mini_run_doall",
                    details=_context or "via=tg-mini",
                )
                _context = (_context + "; via=tg-mini") if _context else "via=tg-mini"

            log_user_action_event(
                "settings_run_doall",
                target_type="maintenance",
                target_name="doall",
                details=_context,
            )
            return task_accepted_response(
                task,
                "Скрипт doall запущен в фоне.",
            )
        except (RuntimeError, ValueError, OSError) as e:
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
