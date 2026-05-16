import subprocess

from flask import jsonify, render_template, request, session, url_for

from core.services.index import (
    build_client_details_payload,
    build_index_get_context,
    collect_grouped_service_statuses,
    resolve_openvpn_group_and_files,
)
from core.services.request_user import get_current_user
from tg_mini.session import has_telegram_mini_session


def register_index_routes(
    app,
    *,
    auth_manager,
    db,
    user_model,
    config_file_handler,
    file_validator,
    group_folders,
    read_banned_clients,
    extract_client_name_from_config_file,
    get_logs_dashboard_data_cached,
    human_bytes,
    script_executor,
    sync_wireguard_peer_cache_from_configs,
    log_telegram_audit_event,
    log_user_action_event,
    send_tg_admin_notification=None,
):
    def _has_telegram_mini_session() -> bool:
        return has_telegram_mini_session(session)

    @app.route("/api/index-client-details", methods=["GET"])
    @auth_manager.login_required
    def api_index_client_details():
        idx_user = get_current_user(user_model)
        (
            _,
            _,
            _,
            openvpn_files,
            wg_files,
            amneziawg_files,
        ) = resolve_openvpn_group_and_files(session, group_folders, config_file_handler, idx_user)

        visible_client_names = set()
        for file_list in (openvpn_files, wg_files, amneziawg_files):
            for path in file_list:
                name = extract_client_name_from_config_file(path)
                if name:
                    visible_client_names.add(name)

        return jsonify(
            {
                "success": True,
                "payload": build_client_details_payload(
                    visible_client_names,
                    get_logs_dashboard_data_cached=get_logs_dashboard_data_cached,
                    session_username=session.get("username"),
                    human_bytes=human_bytes,
                    logger=app.logger,
                ),
            }
        )

    @app.route("/", methods=["GET", "POST"])
    @auth_manager.login_required
    def index():
        if request.method == "GET":
            idx_user = get_current_user(user_model)
            context = build_index_get_context(
                session=session,
                group_folders=group_folders,
                config_file_handler=config_file_handler,
                idx_user=idx_user,
                read_banned_clients=read_banned_clients,
                extract_client_name_from_config_file=extract_client_name_from_config_file,
                url_for=url_for,
            )
            context["service_statuses"] = collect_grouped_service_statuses()
            return render_template("index.html", **context)

        post_user = get_current_user(user_model)
        if not post_user or post_user.role != "admin":
            return jsonify({"success": False, "message": "Доступ запрещён."}), 403
        try:
            option = request.form.get("option")
            client_name = request.form.get("client-name", "").strip()
            cert_expire = request.form.get("work-term", "").strip()

            if not option or not client_name:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Не указаны обязательные параметры.",
                        }
                    ),
                    400,
                )

            stdout, stderr = script_executor.run_bash_script(
                option, client_name, cert_expire
            )

            if option in {"1", "2"}:
                try:
                    config_file_handler.__class__.clear_openvpn_cert_expiry_cache()
                except Exception as e:
                    app.logger.warning(
                        "Не удалось сбросить кэш сроков OpenVPN сертификатов после client.sh option=%s: %s",
                        option,
                        e,
                    )

            if option in {"4", "5", "7"}:
                try:
                    sync_wireguard_peer_cache_from_configs(force=True)
                except Exception as e:
                    db.session.rollback()
                    app.logger.warning(
                        "Не удалось синхронизировать wireguard_peer_cache после client.sh option=%s: %s",
                        option,
                        e,
                    )

            is_tg_mini_action = _has_telegram_mini_session()
            if is_tg_mini_action:
                option_events = {
                    "1": "mini_create_openvpn_config",
                    "2": "mini_delete_openvpn_config",
                    "4": "mini_create_wireguard_config",
                    "5": "mini_delete_wireguard_config",
                    "7": "mini_recreate_wireguard_config",
                }
                log_telegram_audit_event(
                    option_events.get(str(option), "mini_index_action"),
                    config_name=client_name,
                    details=f"option={option} cert_days={cert_expire or '-'}",
                )

            user_action_events = {
                "1": ("config_create", "openvpn"),
                "2": ("config_delete", "openvpn"),
                "4": ("config_create", "wireguard"),
                "5": ("config_delete", "wireguard"),
                "7": ("config_recreate", "wireguard"),
            }
            event_type, target_type = user_action_events.get(str(option), ("config_action", "config"))
            details_text = f"option={option} cert_days={cert_expire or '-'}"
            if is_tg_mini_action:
                details_text += " via=tg-mini"
            log_user_action_event(
                event_type,
                target_type=target_type,
                target_name=client_name,
                details=details_text,
            )
            if event_type in ("config_create", "config_recreate") and callable(send_tg_admin_notification):
                send_tg_admin_notification(
                    event_type,
                    actor_username=session.get("username"),
                    target_name=client_name,
                )

            return jsonify(
                {
                    "success": True,
                    "message": "Операция выполнена успешно.",
                    "output": stdout,
                }
            )
        except subprocess.CalledProcessError as e:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Ошибка выполнения скрипта: {e.stderr}",
                        "output": e.stdout,
                    }
                ),
                500,
            )
        except Exception as e:
            return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
