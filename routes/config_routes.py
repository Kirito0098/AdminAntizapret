import hashlib
import os
import re
from datetime import datetime

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import case
from werkzeug.exceptions import HTTPException


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
    file_editor,
    enqueue_background_task,
    task_run_doall,
    task_accepted_response,
    set_env_value,
    get_public_download_enabled,
    set_public_download_enabled,
):
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

    @app.route("/qr_download/<token>")
    def one_time_qr_download(token):
        if not token or len(token) < 16:
            abort(404)

        now = datetime.utcnow()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        pin_page_tpl = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Введите PIN</title>
  <style>
    body { font-family: sans-serif; background: #101722; color: #e6edf3; margin: 0; }
    .wrap { max-width: 420px; margin: 60px auto; padding: 24px; border-radius: 12px; background: #162133; }
    h2 { margin-top: 0; }
    input { width: 100%; box-sizing: border-box; padding: 12px; border-radius: 8px; border: 1px solid #2d3d56; background: #0f1725; color: #fff; }
    button { margin-top: 12px; width: 100%; padding: 12px; border: none; border-radius: 8px; background: #2c84ff; color: #fff; cursor: pointer; }
    .hint { color: #9fb3c8; font-size: 0.92rem; margin-top: 8px; }
    .error { color: #ff8b8b; margin-top: 10px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h2>PIN для скачивания</h2>
    <form method="GET">
      <input type="password" name="pin" inputmode="numeric" pattern="[0-9]*" placeholder="Введите PIN" autofocus required />
      <button type="submit">Скачать файл</button>
    </form>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <div class="hint">Осталось скачиваний: {{ remaining }}</div>
  </div>
</body>
</html>
        """

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
                pin = (request.args.get("pin") or "").strip()
                remaining = max(token_row.max_downloads - token_row.download_count, 0)
                if not pin:
                    return render_template_string(pin_page_tpl, error=None, remaining=remaining)

                pin_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
                if pin_hash != token_row.pin_hash:
                    log_qr_event("download_pin_invalid", token_row=token_row, details="invalid_pin")
                    return render_template_string(pin_page_tpl, error="Неверный PIN", remaining=remaining), 403

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
            return send_from_directory(
                os.path.dirname(file_path),
                base,
                as_attachment=True,
                download_name=base,
            )
        except HTTPException:
            raise
        except Exception as e:
            print(f"Аларм! ошибка: {str(e)}")
            abort(500)

    @app.route("/download/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def download(file_path, clean_name):
        _ = clean_name
        user = user_model.query.filter_by(username=session["username"]).first()
        if user and user.role == "viewer":
            cfg_type = get_config_type(file_path)
            if cfg_type not in ("openvpn", "wg", "amneziawg"):
                abort(403)
            cfg_name = os.path.basename(file_path)
            access = viewer_config_access_model.query.filter_by(
                user_id=user.id, config_name=cfg_name
            ).first()
            if not access:
                abort(403)

        try:
            base = os.path.basename(file_path)
            pattern = re.compile(
                r"^(?P<prefix>antizapret|vpn)-(?P<client>[\w\-]+?)(?:_(?P<id>[\w\-]+))?(?:-\([^)]+\))?(?:-(?P<proto>udp|tcp))?(?:-(?P<suffix>wg|am))?\.(?P<ext>ovpn|conf)$",
                re.IGNORECASE,
            )
            m = pattern.match(base)

            if m:
                prefix = m.group("prefix").lower()
                client = m.group("client")
                id_ = m.group("id")
                proto = m.group("proto")
                ext = m.group("ext").lower()
                prefix_out = "az" if prefix == "antizapret" else "vpn"
                if id_:
                    base_name = f"{prefix_out}-{client}_{id_}"
                else:
                    base_name = f"{prefix_out}-{client}"
                if proto:
                    download_name = f"{base_name}-{proto}.{ext}"
                else:
                    download_name = f"{base_name}.{ext}"
            else:
                download_name = base
            return send_from_directory(
                os.path.dirname(file_path),
                base,
                as_attachment=True,
                download_name=download_name,
            )
        except Exception as e:
            print(f"Аларм! ошибка: {e}")
            abort(500)

    @app.route("/public_download/<router>")
    def public_download(router):
        if not get_public_download_enabled():
            abort(404)
        filename = result_dir_files.get(router)
        if not filename:
            abort(404)

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
        user = user_model.query.filter_by(username=session["username"]).first()
        if user and user.role == "viewer":
            cfg_type = get_config_type(file_path)
            if cfg_type not in ("openvpn", "wg", "amneziawg"):
                abort(403)
            cfg_name = os.path.basename(file_path)
            access = viewer_config_access_model.query.filter_by(
                user_id=user.id, config_name=cfg_name
            ).first()
            if not access:
                abort(403)
        try:
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
        except Exception as e:
            print(f"Аларм! ошибка: {str(e)}")
            abort(500)

    @app.route("/generate_one_time_download/<file_type>/<path:filename>")
    @auth_manager.login_required
    @file_validator.validate_file
    def generate_one_time_download(file_path, clean_name):
        _ = clean_name
        user = user_model.query.filter_by(username=session["username"]).first()
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
        except Exception as e:
            print(f"Аларм! ошибка: {str(e)}")
            abort(500)

    @app.route("/edit-files", methods=["GET", "POST"])
    @auth_manager.admin_required
    def edit_files():
        if request.method == "POST":
            file_type = request.form.get("file_type")
            content = request.form.get("content", "")

            if file_editor.update_file_content(file_type, content):
                try:
                    task = enqueue_background_task(
                        "run_doall",
                        task_run_doall,
                        created_by_username=session.get("username"),
                        queued_message="Применение изменений запущено в фоне",
                    )
                    return task_accepted_response(
                        task,
                        "Файл сохранен. Применение изменений выполняется в фоне.",
                    )
                except Exception as e:
                    return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500

            return jsonify({"success": False, "message": "Неверный тип файла."}), 400

        file_contents = file_editor.get_file_contents()
        return render_template(
            "edit_files.html",
            file_contents=file_contents,
            public_download_enabled=get_public_download_enabled(),
        )

    @app.route("/run-doall", methods=["POST"])
    @auth_manager.admin_required
    def run_doall():
        try:
            task = enqueue_background_task(
                "run_doall",
                task_run_doall,
                created_by_username=session.get("username"),
                queued_message="Запуск doall поставлен в очередь",
            )
            return task_accepted_response(
                task,
                "Скрипт doall запущен в фоне.",
            )
        except Exception as e:
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
