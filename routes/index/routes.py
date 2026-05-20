import subprocess

from flask import jsonify, render_template, request, session, url_for

from core.services.index import (
    build_client_details_payload,
    build_index_get_context,
    collect_grouped_service_statuses,
    resolve_openvpn_group_and_files,
)
from core.services.wg_access_policy import EXPIRED_REQUIRES_EXTEND_CODE, ExpiredRequiresExtendError
from core.services.request_user import get_current_user
from utils.wg_runtime_subprocess import trigger_wg_policy_sync_background
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
    openvpn_build_status_map,
    openvpn_reconcile_all_policies,
    extract_client_name_from_config_file,
    get_logs_dashboard_data_cached,
    human_bytes,
    script_executor,
    sync_wireguard_peer_cache_from_configs,
    wg_build_status_map,
    wg_set_expiry_days,
    wg_set_temp_block_days,
    wg_set_permanent_block,
    wg_clear_temp_block,
    wg_reconcile_client_policy,
    wg_reconcile_all_policies,
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
            try:
                openvpn_reconcile_all_policies()
            except Exception as e:
                db.session.rollback()
                app.logger.warning("Не удалось синхронизировать OpenVPN политики при загрузке index: %s", e)
            try:
                wg_reconcile_all_policies(apply_runtime=False)
                trigger_wg_policy_sync_background()
            except Exception as e:
                db.session.rollback()
                app.logger.warning("Не удалось синхронизировать WG/AWG политики при загрузке index: %s", e)
            context = build_index_get_context(
                session=session,
                group_folders=group_folders,
                config_file_handler=config_file_handler,
                idx_user=idx_user,
                read_banned_clients=read_banned_clients,
                openvpn_build_status_map=openvpn_build_status_map,
                extract_client_name_from_config_file=extract_client_name_from_config_file,
                wg_build_status_map=wg_build_status_map,
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
            if option == "4" and cert_expire:
                try:
                    wg_set_expiry_days(
                        client_name,
                        int(cert_expire),
                        actor_username=session.get("username"),
                        extend=False,
                    )
                except Exception as e:
                    db.session.rollback()
                    app.logger.warning(
                        "Не удалось установить срок WG/AWG политики после создания client.sh option=4: %s",
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

    @app.route("/api/wg/client-access", methods=["POST"])
    @auth_manager.admin_required
    def api_wg_client_access():
        client_name = (request.form.get("client_name") or "").strip()
        action = (request.form.get("action") or "").strip().lower()
        days_raw = (request.form.get("days") or "").strip()
        actor_username = session.get("username")

        if not client_name:
            return jsonify({"success": False, "message": "Не указано имя клиента."}), 400

        try:
            if action == "temp_block":
                days_value = int(days_raw or "0")
                if days_value < 1 or days_value > 3650:
                    return jsonify({"success": False, "message": "Срок блокировки должен быть в диапазоне 1..3650 дней."}), 400
                row = wg_set_temp_block_days(client_name, days_value, actor_username=actor_username)
                log_user_action_event(
                    "wg_client_temp_block_set",
                    target_type="wireguard",
                    target_name=client_name,
                    details=f"days={days_value}",
                )
                message = "Клиент временно заблокирован."
            elif action == "permanent_block":
                row = wg_set_permanent_block(client_name, actor_username=actor_username)
                log_user_action_event(
                    "wg_client_permanent_block_set",
                    target_type="wireguard",
                    target_name=client_name,
                    details="manual_permanent=1",
                )
                message = "Клиент заблокирован до ручной разблокировки."
            elif action == "unblock":
                row = wg_clear_temp_block(client_name, actor_username=actor_username)
                log_user_action_event(
                    "wg_client_block_clear",
                    target_type="wireguard",
                    target_name=client_name,
                    details="manual_unblock=1",
                )
                message = "Блокировка клиента снята."
            elif action == "extend":
                days_value = int(days_raw or "0")
                if days_value < 1 or days_value > 3650:
                    return jsonify({"success": False, "message": "Срок продления должен быть в диапазоне 1..3650 дней."}), 400
                row = wg_set_expiry_days(
                    client_name,
                    days_value,
                    actor_username=actor_username,
                    extend=True,
                )
                log_user_action_event(
                    "wg_client_expiry_extend",
                    target_type="wireguard",
                    target_name=client_name,
                    details=f"days={days_value}",
                )
                message = "Срок действия WG/AWG продлён."
            else:
                return jsonify({"success": False, "message": "Неизвестное действие."}), 400

            reconcile_result = wg_reconcile_client_policy(client_name, apply_runtime=True) or {}
            state = (reconcile_result.get("state") or {})
            runtime_result = reconcile_result.get("runtime_result") or {}
            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "client_name": client_name,
                    "is_blocked": bool(state.get("is_blocked")),
                    "reason": state.get("reason"),
                    "expires_at": row.expires_at.strftime("%Y-%m-%d %H:%M:%S") if row.expires_at else None,
                    "block_until": row.block_until.strftime("%Y-%m-%d %H:%M:%S") if row.block_until else None,
                    "access_days_left": state.get("access_days_left"),
                    "blocked_days_left": state.get("blocked_days_left"),
                    "block_mode": state.get("block_mode"),
                    "block_duration_days": state.get("block_duration_days"),
                    "block_started_at": (
                        state.get("block_started_at").strftime("%Y-%m-%d %H:%M:%S")
                        if state.get("block_started_at")
                        else None
                    ),
                    "runtime_synced_count": int(runtime_result.get("synced_count") or 0),
                    "runtime_error_count": int(runtime_result.get("error_count") or 0),
                    "runtime_errors": runtime_result.get("errors") or [],
                }
            )
        except ValueError as e:
            if isinstance(e, ExpiredRequiresExtendError):
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": str(e),
                            "error_code": EXPIRED_REQUIRES_EXTEND_CODE,
                        }
                    ),
                    409,
                )
            return jsonify({"success": False, "message": str(e)}), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": f"Ошибка: {e}"}), 500
