import os
import subprocess

from flask import jsonify, render_template, request, session


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
):
    @app.route("/", methods=["GET", "POST"])
    @auth_manager.login_required
    def index():
        if request.method == "GET":
            idx_user = user_model.query.filter_by(username=session["username"]).first()
            group = session.get("openvpn_group", "GROUP_UDP\\TCP")
            if group not in group_folders:
                group = "GROUP_UDP\\TCP"
            folders = group_folders[group]
            config_file_handler.config_paths["openvpn"] = folders
            file_validator.config_paths["openvpn"] = folders
            openvpn_files, wg_files, amneziawg_files = config_file_handler.get_config_files()
            cert_expiry = config_file_handler.get_openvpn_cert_expiry()
            raw_banned_clients = read_banned_clients()
            banned_clients = set()

            for file_path in openvpn_files:
                filename = os.path.basename(file_path)
                client_name = config_file_handler._extract_client_name_from_ovpn(filename)
                if client_name and client_name in raw_banned_clients:
                    banned_clients.add(client_name)

            if idx_user and idx_user.role == "viewer":
                allowed = {acc.config_name for acc in idx_user.allowed_configs}
                openvpn_files = [f for f in openvpn_files if os.path.basename(f) in allowed]
                wg_files = [f for f in wg_files if os.path.basename(f) in allowed]
                amneziawg_files = [f for f in amneziawg_files if os.path.basename(f) in allowed]

            visible_client_names = set()
            for file_list in (openvpn_files, wg_files, amneziawg_files):
                for path in file_list:
                    name = extract_client_name_from_config_file(path)
                    if name:
                        visible_client_names.add(name)

            client_details_payload = {"connected": {}, "traffic": {}}
            try:
                dashboard_data = get_logs_dashboard_data_cached(created_by_username=session.get("username"))
                connected_clients = dashboard_data.get("connected_clients", []) or []
                persisted_traffic_rows = dashboard_data.get("persisted_traffic_rows", []) or []

                if visible_client_names:
                    connected_clients = [
                        item
                        for item in connected_clients
                        if (item.get("common_name") or "") in visible_client_names
                    ]
                    persisted_traffic_rows = [
                        row
                        for row in persisted_traffic_rows
                        if (row.get("common_name") or "") in visible_client_names
                    ]

                for item in connected_clients:
                    name = (item.get("common_name") or "").strip()
                    if not name:
                        continue
                    client_details_payload["connected"][name] = {
                        "common_name": name,
                        "sessions": int(item.get("sessions") or 0),
                        "profiles": item.get("profiles") or "-",
                        "bytes_received_human": item.get("bytes_received_human") or "0 B",
                        "bytes_sent_human": item.get("bytes_sent_human") or "0 B",
                        "total_bytes_human": item.get("total_bytes_human") or "0 B",
                        "ip_device_map": item.get("ip_device_map") or [],
                    }

                for row in persisted_traffic_rows:
                    name = (row.get("common_name") or "").strip()
                    if not name:
                        continue

                    entry = client_details_payload["traffic"].setdefault(
                        name,
                        {
                            "traffic_1d": 0,
                            "traffic_7d": 0,
                            "traffic_30d": 0,
                            "total_bytes_vpn": 0,
                            "total_bytes_antizapret": 0,
                            "total_bytes": 0,
                            "last_seen_at": "-",
                            "is_active": False,
                        },
                    )

                    entry["traffic_1d"] += int(row.get("traffic_1d") or 0)
                    entry["traffic_7d"] += int(row.get("traffic_7d") or 0)
                    entry["traffic_30d"] += int(row.get("traffic_30d") or 0)
                    entry["total_bytes_vpn"] += int(row.get("total_bytes_vpn") or 0)
                    entry["total_bytes_antizapret"] += int(row.get("total_bytes_antizapret") or 0)
                    entry["total_bytes"] += int(row.get("total_bytes") or 0)

                    row_last_seen = (row.get("last_seen_at") or "-").strip() or "-"
                    if row_last_seen != "-" and (
                        entry.get("last_seen_at") in (None, "-")
                        or row_last_seen > str(entry.get("last_seen_at") or "-")
                    ):
                        entry["last_seen_at"] = row_last_seen

                    if bool(row.get("is_active")):
                        entry["is_active"] = True

                for entry in client_details_payload["traffic"].values():
                    entry["traffic_1d_human"] = human_bytes(int(entry.get("traffic_1d") or 0))
                    entry["traffic_7d_human"] = human_bytes(int(entry.get("traffic_7d") or 0))
                    entry["traffic_30d_human"] = human_bytes(int(entry.get("traffic_30d") or 0))
                    entry["total_bytes_vpn_human"] = human_bytes(int(entry.get("total_bytes_vpn") or 0))
                    entry["total_bytes_antizapret_human"] = human_bytes(int(entry.get("total_bytes_antizapret") or 0))
                    entry["total_bytes_human"] = human_bytes(int(entry.get("total_bytes") or 0))
            except Exception as e:
                app.logger.warning("Не удалось подготовить client_details_payload для index: %s", e)

            return render_template(
                "index.html",
                openvpn_files=openvpn_files,
                wg_files=wg_files,
                amneziawg_files=amneziawg_files,
                cert_expiry=cert_expiry,
                banned_clients=banned_clients,
                current_openvpn_group=group,
                current_openvpn_folders=folders,
                client_details_payload=client_details_payload,
            )

        post_user = user_model.query.filter_by(username=session["username"]).first()
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
