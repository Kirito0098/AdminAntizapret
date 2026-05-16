import os
from collections import OrderedDict

_PROTOCOL_TABLE_CONFIG = {
    "openvpn": {
        "file_type": "openvpn",
        "delete_option": "2",
        "protocol_label": "OpenVPN",
        "supports_qr": False,
        "supports_cert_meta": True,
        "supports_block": True,
    },
    "amneziawg": {
        "file_type": "amneziawg",
        "delete_option": "5",
        "protocol_label": "AmneziaWG",
        "supports_qr": True,
        "supports_cert_meta": False,
        "supports_block": False,
    },
    "wireguard": {
        "file_type": "wg",
        "delete_option": "5",
        "protocol_label": "WireGuard",
        "supports_qr": True,
        "supports_cert_meta": False,
        "supports_block": False,
    },
}


def resolve_openvpn_group_and_files(session, group_folders, config_file_handler, idx_user):
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


def group_config_files_by_client(file_paths):
    grouped = OrderedDict()

    for file_path in file_paths:
        filename = os.path.basename(file_path)
        stem = filename.rsplit(".", 1)[0]
        stem_lc = stem.lower()

        if stem_lc.startswith("antizapret-"):
            kind = "antizapret"
            after_prefix = stem[11:]
        elif stem_lc.startswith("vpn-"):
            kind = "vpn"
            after_prefix = stem[4:]
        else:
            kind = "vpn"
            after_prefix = stem

        client_name = after_prefix.split("-(")[0]
        if client_name not in grouped:
            grouped[client_name] = {"antizapret": None, "vpn": None}
        grouped[client_name][kind] = file_path

    return grouped


def _resolve_cert_state(cert_info):
    if not cert_info:
        return "active", None, None

    cert_days = cert_info.get("days_left")
    cert_expires_at = cert_info.get("expires_at")

    if cert_days is None:
        return "active", None, cert_expires_at
    if cert_days <= 0:
        return "expired", cert_days, cert_expires_at
    if cert_days <= 30:
        return "expiring", cert_days, cert_expires_at
    return "active", cert_days, cert_expires_at


def _build_file_url(url_for, endpoint, file_type, file_path):
    if not file_path:
        return None
    return url_for(endpoint, file_type=file_type, filename=os.path.basename(file_path))


def build_client_table_rows(
    protocol,
    grouped_files,
    *,
    current_user,
    cert_expiry,
    banned_clients,
    url_for,
):
    config = _PROTOCOL_TABLE_CONFIG[protocol]
    is_admin = bool(current_user and current_user.is_admin())
    rows = []

    for client_name in sorted(grouped_files.keys()):
        files = grouped_files[client_name]
        cert_info = cert_expiry.get(client_name) if cert_expiry else None
        cert_state, cert_days, cert_expires_at = _resolve_cert_state(cert_info)
        is_blocked = bool(banned_clients and client_name in banned_clients)

        show_cert_meta = is_admin and config["supports_cert_meta"]
        if show_cert_meta:
            data_cert_state = cert_state
            data_cert_days = cert_days if cert_days is not None else 99999
        else:
            data_cert_state = "active"
            data_cert_days = 99999

        file_type = config["file_type"]
        row = {
            "client_name": client_name,
            "protocol": protocol,
            "protocol_label": config["protocol_label"],
            "show_cert_meta": show_cert_meta,
            "cert_state": data_cert_state,
            "cert_days": data_cert_days,
            "cert_expires_at": cert_expires_at,
            "cert_days_display": cert_days,
            "is_blocked": is_blocked,
            "can_block": is_admin and config["supports_block"],
            "can_manage": is_admin,
            "delete_option": config["delete_option"],
            "has_vpn": bool(files.get("vpn")),
            "has_antizapret": bool(files.get("antizapret")),
            "download_vpn_url": _build_file_url(url_for, "download", file_type, files.get("vpn")),
            "download_az_url": _build_file_url(url_for, "download", file_type, files.get("antizapret")),
            "qr_vpn_url": (
                _build_file_url(url_for, "generate_qr", file_type, files.get("vpn"))
                if config["supports_qr"]
                else None
            ),
            "qr_az_url": (
                _build_file_url(url_for, "generate_qr", file_type, files.get("antizapret"))
                if config["supports_qr"]
                else None
            ),
            "one_time_vpn_endpoint": (
                _build_file_url(url_for, "generate_one_time_download", file_type, files.get("vpn"))
                if is_admin
                else None
            ),
            "one_time_az_endpoint": (
                _build_file_url(url_for, "generate_one_time_download", file_type, files.get("antizapret"))
                if is_admin
                else None
            ),
        }
        rows.append(row)

    return rows


def build_index_kpi(cert_expiry, banned_clients, openvpn_count, wg_awg_count):
    expiring_count = 0
    expired_count = 0

    if cert_expiry:
        for cert_info in cert_expiry.values():
            cert_days = cert_info.get("days_left")
            if cert_days is not None and cert_days <= 0:
                expired_count += 1
            elif cert_days is not None and cert_days <= 30:
                expiring_count += 1

    return {
        "expiring_count": expiring_count,
        "expired_count": expired_count,
        "openvpn_clients_count": openvpn_count,
        "wg_awg_clients_count": wg_awg_count,
        "banned_clients_count": len(banned_clients) if banned_clients else 0,
    }


def collect_unique_client_names(file_paths, extract_client_name_from_config_file):
    unique_names = set()
    for path in file_paths:
        extracted_name = extract_client_name_from_config_file(path)
        normalized_name = str(extracted_name or "").strip()

        if not normalized_name:
            normalized_name = os.path.splitext(os.path.basename(path))[0].strip()

        if normalized_name:
            unique_names.add(normalized_name)

    return unique_names


def build_index_get_context(
    *,
    session,
    group_folders,
    config_file_handler,
    idx_user,
    read_banned_clients,
    extract_client_name_from_config_file,
    url_for,
):
    (
        group,
        folders,
        request_config_file_handler,
        openvpn_files,
        wg_files,
        amneziawg_files,
    ) = resolve_openvpn_group_and_files(session, group_folders, config_file_handler, idx_user)

    is_admin = bool(idx_user and idx_user.role == "admin")
    cert_expiry = {}
    banned_clients = set()

    openvpn_client_names = collect_unique_client_names(openvpn_files, extract_client_name_from_config_file)
    wg_awg_client_names = collect_unique_client_names(wg_files, extract_client_name_from_config_file)
    wg_awg_client_names.update(collect_unique_client_names(amneziawg_files, extract_client_name_from_config_file))

    if is_admin:
        cert_expiry = request_config_file_handler.get_openvpn_cert_expiry()
        raw_banned_clients = read_banned_clients()

        for file_path in openvpn_files:
            filename = os.path.basename(file_path)
            client_name = request_config_file_handler._extract_client_name_from_ovpn(filename)
            if client_name and client_name in raw_banned_clients:
                banned_clients.add(client_name)

    kpi = build_index_kpi(
        cert_expiry,
        banned_clients,
        len(openvpn_client_names),
        len(wg_awg_client_names),
    )

    openvpn_grouped = group_config_files_by_client(openvpn_files)
    amneziawg_grouped = group_config_files_by_client(amneziawg_files)
    wireguard_grouped = group_config_files_by_client(wg_files)

    row_kwargs = {
        "current_user": idx_user,
        "cert_expiry": cert_expiry,
        "banned_clients": banned_clients,
        "url_for": url_for,
    }

    return {
        "openvpn_files": openvpn_files,
        "wg_files": wg_files,
        "amneziawg_files": amneziawg_files,
        "cert_expiry": cert_expiry,
        "banned_clients": banned_clients,
        "openvpn_clients_count": kpi["openvpn_clients_count"],
        "wg_awg_clients_count": kpi["wg_awg_clients_count"],
        "expiring_cert_count": kpi["expiring_count"],
        "expired_cert_count": kpi["expired_count"],
        "banned_clients_count": kpi["banned_clients_count"],
        "current_openvpn_group": group,
        "current_openvpn_folders": folders,
        "openvpn_client_rows": build_client_table_rows("openvpn", openvpn_grouped, **row_kwargs),
        "amneziawg_client_rows": build_client_table_rows("amneziawg", amneziawg_grouped, **row_kwargs),
        "wireguard_client_rows": build_client_table_rows("wireguard", wireguard_grouped, **row_kwargs),
        "client_details_payload": {"connected": {}, "traffic": {}},
    }
