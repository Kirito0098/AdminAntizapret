import os
import shutil
import subprocess

from flask import jsonify, render_template, request, session

from core.services.request_user import get_current_user
from core.services.telegram_mini_session import has_telegram_mini_session


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
):
    def _has_telegram_mini_session() -> bool:
        return has_telegram_mini_session(session)

    def _resolve_group_and_files(idx_user):
        group = session.get("openvpn_group", "GROUP_UDP\\TCP")
        if group not in group_folders:
            group = "GROUP_UDP\\TCP"

        folders = group_folders[group]
        request_config_paths = dict(config_file_handler.config_paths)
        request_config_paths["openvpn"] = list(folders)
        request_config_file_handler = config_file_handler.__class__(request_config_paths)

        openvpn_files, wg_files, amneziawg_files = request_config_file_handler.get_config_files()

        if idx_user and idx_user.role == "viewer":
            allowed_by_type = {
                "openvpn": set(),
                "wg": set(),
                "amneziawg": set(),
            }
            for access_entry in idx_user.allowed_configs:
                cfg_type = str(getattr(access_entry, "config_type", "") or "").strip().lower()
                cfg_name = str(getattr(access_entry, "config_name", "") or "").strip()
                if cfg_type in allowed_by_type and cfg_name:
                    allowed_by_type[cfg_type].add(cfg_name)

            openvpn_files = [
                file_path
                for file_path in openvpn_files
                if os.path.basename(file_path) in allowed_by_type["openvpn"]
            ]
            wg_files = [
                file_path
                for file_path in wg_files
                if os.path.basename(file_path) in allowed_by_type["wg"]
            ]
            amneziawg_files = [
                file_path
                for file_path in amneziawg_files
                if os.path.basename(file_path) in allowed_by_type["amneziawg"]
            ]

        return (
            group,
            folders,
            request_config_file_handler,
            openvpn_files,
            wg_files,
            amneziawg_files,
        )

    def _build_client_details_payload(visible_client_names):
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

        return client_details_payload

    def _collect_unique_client_names(file_paths):
        unique_names = set()
        for path in file_paths:
            extracted_name = extract_client_name_from_config_file(path)
            normalized_name = str(extracted_name or "").strip()

            if not normalized_name:
                # Fallback keeps KPI stable even when parser cannot detect CN in a file.
                normalized_name = os.path.splitext(os.path.basename(path))[0].strip()

            if normalized_name:
                unique_names.add(normalized_name)

        return unique_names

    def _collect_service_statuses():
        service_groups = [
            {
                "project_label": "AdminAntizapret",
                "services": [
                    {
                        "label": "Веб-панель",
                        "description": "Интерфейс управления (admin-antizapret)",
                        "units": ["admin-antizapret.service", "admin-antizapret"],
                    },
                    {
                        "label": "Nginx",
                        "description": "Прокси и HTTPS-шлюз",
                        "units": ["nginx.service", "nginx"],
                    },
                    {
                        "label": "vnStat",
                        "description": "Учёт сетевого трафика",
                        "units": ["vnstat.service", "vnstat"],
                    },
                ],
            },
            {
                "project_label": "AntiZapret-VPN",
                "services": [
                    {
                        "label": "VPN ядро",
                        "description": "Основной сервис AntiZapret (antizapret)",
                        "units": ["antizapret.service", "antizapret"],
                    },
                    {
                        "label": "OpenVPN AntiZapret (UDP/TCP)",
                        "description": "Туннели antizapret-udp и antizapret-tcp",
                        "unit_groups": [
                            ["openvpn-server@antizapret-udp.service", "openvpn-server@antizapret-udp"],
                            ["openvpn-server@antizapret-tcp.service", "openvpn-server@antizapret-tcp"],
                        ],
                    },
                    {
                        "label": "OpenVPN VPN (UDP/TCP)",
                        "description": "Туннели vpn-udp и vpn-tcp",
                        "unit_groups": [
                            ["openvpn-server@vpn-udp.service", "openvpn-server@vpn-udp"],
                            ["openvpn-server@vpn-tcp.service", "openvpn-server@vpn-tcp"],
                        ],
                    },
                    {
                        "label": "WireGuard AntiZapret",
                        "description": "Интерфейс wg-quick@antizapret",
                        "units": ["wg-quick@antizapret.service", "wg-quick@antizapret"],
                    },
                    {
                        "label": "WireGuard VPN",
                        "description": "Интерфейс wg-quick@vpn",
                        "units": ["wg-quick@vpn.service", "wg-quick@vpn"],
                    },
                    {
                        "label": "DNS резолвер #1",
                        "description": "Knot Resolver instance kresd@1",
                        "units": ["kresd@1.service", "kresd@1"],
                    },
                    {
                        "label": "DNS резолвер #2",
                        "description": "Knot Resolver instance kresd@2",
                        "units": ["kresd@2.service", "kresd@2"],
                    },
                    {
                        "label": "Автообновление AntiZapret",
                        "description": "Таймер antizapret-update.timer",
                        "units": ["antizapret-update.timer", "antizapret-update.service", "antizapret-update"],
                    },
                ],
            },
        ]

        state_map = {
            "active": ("ok", "Работает"),
            "activating": ("warn", "Запуск"),
            "deactivating": ("warn", "Остановка"),
            "inactive": ("warn", "Остановлен"),
            "failed": ("error", "Ошибка"),
            "unknown": ("unknown", "Не найден"),
        }
        systemd_states = {"active", "activating", "deactivating", "inactive", "failed"}

        def _detect_state(unit_candidates):
            detected_state = "unknown"

            for unit in unit_candidates:
                try:
                    proc = subprocess.run(
                        ["systemctl", "is-active", unit],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=1.5,
                    )
                    state = (proc.stdout or "").strip().lower()
                    if not state:
                        state = (proc.stderr or "").strip().lower()

                    if state:
                        detected_state = state

                    if state in systemd_states:
                        break
                except Exception:
                    detected_state = "unknown"

            return detected_state

        def _aggregate_group_states(states):
            if not states:
                return "unknown", "Не найден"

            if "failed" in states:
                return "error", "Ошибка"
            if "activating" in states:
                return "warn", "Запуск"
            if "deactivating" in states:
                return "warn", "Остановка"

            total = len(states)
            active_count = sum(1 for state in states if state == "active")
            inactive_count = sum(1 for state in states if state == "inactive")
            unknown_count = sum(1 for state in states if state == "unknown")

            if active_count == total:
                return "ok", "Работает"
            if inactive_count == total:
                return "warn", "Остановлен"
            if unknown_count == total:
                return "unknown", "Не найден"
            if active_count > 0:
                return "warn", f"Частично {active_count}/{total}"

            return "unknown", "Неизвестно"

        if not shutil.which("systemctl"):
            return [
                {
                    "project_label": group["project_label"],
                    "services": [
                        {
                            "label": item["label"],
                            "description": item["description"],
                            "state_class": "unknown",
                            "state_label": "n/a",
                        }
                        for item in group["services"]
                    ],
                }
                for group in service_groups
            ]

        grouped_statuses = []
        for group in service_groups:
            statuses = []
            for item in group["services"]:
                if item.get("unit_groups"):
                    grouped_states = [_detect_state(unit_group) for unit_group in item["unit_groups"]]
                    state_class, state_label = _aggregate_group_states(grouped_states)
                else:
                    detected_state = _detect_state(item["units"])
                    state_class, state_label = state_map.get(detected_state, ("unknown", "Неизвестно"))

                statuses.append(
                    {
                        "label": item["label"],
                        "description": item["description"],
                        "state_class": state_class,
                        "state_label": state_label,
                    }
                )

            grouped_statuses.append(
                {
                    "project_label": group["project_label"],
                    "services": statuses,
                }
            )

        return grouped_statuses

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
        ) = _resolve_group_and_files(idx_user)

        visible_client_names = set()
        for file_list in (openvpn_files, wg_files, amneziawg_files):
            for path in file_list:
                name = extract_client_name_from_config_file(path)
                if name:
                    visible_client_names.add(name)

        return jsonify(
            {
                "success": True,
                "payload": _build_client_details_payload(visible_client_names),
            }
        )

    @app.route("/", methods=["GET", "POST"])
    @auth_manager.login_required
    def index():
        if request.method == "GET":
            idx_user = get_current_user(user_model)
            (
                group,
                folders,
                request_config_file_handler,
                openvpn_files,
                wg_files,
                amneziawg_files,
            ) = _resolve_group_and_files(idx_user)

            is_admin = bool(idx_user and idx_user.role == "admin")
            cert_expiry = {}
            banned_clients = set()
            service_statuses = _collect_service_statuses()

            openvpn_client_names = _collect_unique_client_names(openvpn_files)
            wg_awg_client_names = _collect_unique_client_names(wg_files)
            wg_awg_client_names.update(_collect_unique_client_names(amneziawg_files))

            if is_admin:
                cert_expiry = request_config_file_handler.get_openvpn_cert_expiry()
                raw_banned_clients = read_banned_clients()

                for file_path in openvpn_files:
                    filename = os.path.basename(file_path)
                    client_name = request_config_file_handler._extract_client_name_from_ovpn(filename)
                    if client_name and client_name in raw_banned_clients:
                        banned_clients.add(client_name)

            return render_template(
                "index.html",
                openvpn_files=openvpn_files,
                wg_files=wg_files,
                amneziawg_files=amneziawg_files,
                cert_expiry=cert_expiry,
                banned_clients=banned_clients,
                service_statuses=service_statuses,
                openvpn_clients_count=len(openvpn_client_names),
                wg_awg_clients_count=len(wg_awg_client_names),
                current_openvpn_group=group,
                current_openvpn_folders=folders,
                client_details_payload={"connected": {}, "traffic": {}},
            )

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
