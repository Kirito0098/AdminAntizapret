import os
import re
from collections import OrderedDict
from datetime import datetime, timezone

from core.services.access_remaining import format_access_remaining, is_access_expired
from core.services.time_utils import as_utc

_CLIENT_NAME_SUFFIX_RE = re.compile(r"-(?:udp|tcp|wg|am)$", re.IGNORECASE)
_CLIENT_NAME_EXTRA_RE = re.compile(r"-\([^)]+\)$")


def _client_name_from_config_stem(stem):
    stem_lc = stem.lower()
    if stem_lc.startswith("antizapret-"):
        after_prefix = stem[11:]
    elif stem_lc.startswith("vpn-"):
        after_prefix = stem[4:]
    else:
        after_prefix = stem
    name = _CLIENT_NAME_SUFFIX_RE.sub("", after_prefix)
    name = _CLIENT_NAME_EXTRA_RE.sub("", name)
    return name.strip()

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
        "protocol_label": "AWG",
        "supports_qr": True,
        "supports_cert_meta": False,
        "supports_block": True,
    },
    "wireguard": {
        "file_type": "wg",
        "delete_option": "5",
        "protocol_label": "WG",
        "supports_qr": True,
        "supports_cert_meta": False,
        "supports_block": True,
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
        elif stem_lc.startswith("vpn-"):
            kind = "vpn"
        else:
            kind = "vpn"

        client_name = _client_name_from_config_stem(stem)
        if client_name not in grouped:
            grouped[client_name] = {"antizapret": None, "vpn": None}
        grouped[client_name][kind] = file_path

    return grouped


def _cert_is_expired(cert_days, cert_expires_at, *, now=None):
    if cert_days is not None and cert_days < 0:
        return True

    expired_by_date = is_access_expired(cert_expires_at, now=now)
    if expired_by_date is not None:
        return expired_by_date

    return cert_days is not None and cert_days <= 0


def _resolve_cert_state(cert_info, *, now=None):
    if not cert_info:
        return "active", None, None

    cert_days = cert_info.get("days_left")
    cert_expires_at = cert_info.get("expires_at")

    if cert_days is None:
        return "active", None, cert_expires_at
    if _cert_is_expired(cert_days, cert_expires_at, now=now):
        return "expired", cert_days, cert_expires_at
    if cert_days <= 30:
        return "expiring", cert_days, cert_expires_at
    return "active", cert_days, cert_expires_at


def _build_file_url(url_for, endpoint, file_type, file_path):
    if not file_path:
        return None
    return url_for(endpoint, file_type=file_type, filename=os.path.basename(file_path))


def _format_dt(value):
    if not value:
        return None
    try:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _resolve_wg_days_left(expires_at):
    if not expires_at:
        return None
    try:
        now = datetime.now(timezone.utc)
        return (as_utc(expires_at) - now).days
    except Exception:
        return None


def _resolve_access_days_left(expires_at_dt):
    if not expires_at_dt:
        return None
    try:
        return (as_utc(expires_at_dt) - datetime.now(timezone.utc)).days
    except Exception:
        return None


def _build_blocked_entries(
    *,
    openvpn_blocked_clients,
    openvpn_policy_status_by_client,
    wg_policy_status_by_client,
    wg_awg_client_names,
):
    entries = []
    for client_name in sorted(openvpn_blocked_clients or set(), key=lambda value: value.lower()):
        ovpn_state = (openvpn_policy_status_by_client or {}).get(str(client_name), {})
        entries.append(
            {
                "client_name": client_name,
                "protocol_group": "OpenVPN",
                "reason": ovpn_state.get("reason") or "manual_permanent",
            }
        )

    for raw_name in sorted(wg_awg_client_names or set(), key=lambda value: value.lower()):
        state = (wg_policy_status_by_client or {}).get(str(raw_name).lower(), {})
        if not bool(state.get("is_blocked")):
            continue
        entries.append(
            {
                "client_name": raw_name,
                "protocol_group": "WG/AWG",
                "reason": state.get("reason"),
            }
        )
    return entries


def _traffic_row_fields(state, human_bytes=None):
    state = state or {}
    limit_bytes = state.get("traffic_limit_bytes")
    consumed_bytes = int(state.get("traffic_consumed_bytes") or 0)
    left_bytes = state.get("traffic_bytes_left")
    format_bytes = human_bytes or (lambda value: str(value))
    return {
        "traffic_limit_bytes": limit_bytes,
        "traffic_limit_period_days": state.get("traffic_limit_period_days"),
        "traffic_limit_period_label": state.get("traffic_limit_period_label"),
        "traffic_limit_unblock_at": state.get("traffic_limit_unblock_at"),
        "traffic_limit_unblock_label": state.get("traffic_limit_unblock_label"),
        "traffic_consumed_bytes": consumed_bytes,
        "traffic_bytes_left": left_bytes,
        "traffic_limit_exceeded": bool(state.get("traffic_limit_exceeded")),
        "traffic_limit_human": format_bytes(limit_bytes) if limit_bytes else None,
        "traffic_consumed_human": format_bytes(consumed_bytes),
        "traffic_bytes_left_human": format_bytes(left_bytes) if left_bytes is not None else None,
    }


def build_client_table_rows(
    protocol,
    grouped_files,
    *,
    current_user,
    cert_expiry,
    banned_clients,
    openvpn_policy_status_by_client,
    wg_policy_status_by_client,
    url_for,
    human_bytes=None,
):
    config = _PROTOCOL_TABLE_CONFIG[protocol]
    is_admin = bool(current_user and current_user.is_admin())
    rows = []

    for client_name in sorted(grouped_files.keys()):
        files = grouped_files[client_name]
        cert_info = cert_expiry.get(client_name) if cert_expiry else None
        cert_state, cert_days, cert_expires_at = _resolve_cert_state(cert_info)
        is_blocked = bool(banned_clients and client_name in banned_clients)
        ovpn_state = (openvpn_policy_status_by_client or {}).get(client_name, {})
        ovpn_is_blocked = bool(ovpn_state.get("is_blocked"))
        ovpn_block_reason = ovpn_state.get("reason")
        ovpn_block_until_dt = ovpn_state.get("block_until")
        ovpn_block_until = _format_dt(ovpn_block_until_dt)
        ovpn_blocked_days_left = ovpn_state.get("blocked_days_left")
        if ovpn_blocked_days_left is None:
            ovpn_blocked_days_left = _resolve_access_days_left(ovpn_block_until_dt)
        ovpn_block_mode = ovpn_state.get("block_mode") or ("permanent" if is_blocked else "none")
        ovpn_block_duration_days = ovpn_state.get("block_duration_days")
        wg_state = (wg_policy_status_by_client or {}).get(client_name.lower(), {})
        wg_is_blocked = bool(wg_state.get("is_blocked"))
        wg_block_reason = wg_state.get("reason")
        wg_expires_at_dt = wg_state.get("expires_at")
        wg_block_until_dt = wg_state.get("block_until")
        wg_expires_at = _format_dt(wg_expires_at_dt)
        wg_block_until = _format_dt(wg_block_until_dt)
        wg_days_left = wg_state.get("access_days_left")
        if wg_days_left is None:
            wg_days_left = _resolve_wg_days_left(wg_expires_at_dt)
        wg_blocked_days_left = wg_state.get("blocked_days_left")
        if wg_blocked_days_left is None:
            wg_blocked_days_left = _resolve_access_days_left(wg_block_until_dt)
        wg_block_mode = wg_state.get("block_mode") or ("temp" if wg_block_reason == "manual_temp" else ("expired" if wg_block_reason == "expired" else ("traffic_limit" if wg_block_reason == "traffic_limit" else ("permanent" if wg_block_reason == "manual_permanent" else "none"))))
        wg_block_duration_days = wg_state.get("block_duration_days")

        if protocol == "openvpn":
            access_expires_at = cert_expires_at
            access_expires_at_raw = cert_info.get("expires_at") if cert_info else None
            access_days_left = cert_days
            block_mode = ovpn_block_mode
            block_reason = ovpn_block_reason
            blocked_until = ovpn_block_until
            blocked_days_left = ovpn_blocked_days_left
            block_duration_days = ovpn_block_duration_days
        else:
            access_expires_at = wg_expires_at
            access_expires_at_raw = wg_expires_at_dt
            access_days_left = wg_days_left
            block_mode = wg_block_mode
            block_reason = wg_block_reason
            blocked_until = wg_block_until
            blocked_days_left = wg_blocked_days_left
            block_duration_days = wg_block_duration_days

        access_remaining_text = format_access_remaining(access_expires_at_raw)

        policy_state = ovpn_state if protocol == "openvpn" else wg_state
        traffic_fields = _traffic_row_fields(policy_state, human_bytes)

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
            "is_blocked": ovpn_is_blocked if protocol == "openvpn" else wg_is_blocked,
            "access_expires_at": access_expires_at,
            "access_days_left": access_days_left,
            "access_remaining_text": access_remaining_text,
            "blocked_until": blocked_until,
            "blocked_days_left": blocked_days_left,
            "block_mode": block_mode,
            "block_reason": block_reason,
            "block_duration_days": block_duration_days,
            "wg_block_reason": wg_block_reason,
            "wg_expires_at": wg_expires_at,
            "wg_block_until": wg_block_until,
            "wg_days_left": wg_days_left,
            "wg_blocked_days_left": wg_blocked_days_left,
            "wg_block_mode": wg_block_mode,
            "wg_block_duration_days": wg_block_duration_days,
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
            **traffic_fields,
        }
        rows.append(row)

    return rows


def build_index_kpi(
    cert_expiry,
    *,
    blocked_openvpn_count,
    blocked_wg_awg_count,
    openvpn_count,
    wg_awg_count,
):
    expiring_count = 0
    expired_count = 0

    if cert_expiry:
        for cert_info in cert_expiry.values():
            cert_state, _, _ = _resolve_cert_state(cert_info)
            if cert_state == "expired":
                expired_count += 1
            elif cert_state == "expiring":
                expiring_count += 1

    return {
        "expiring_count": expiring_count,
        "expired_count": expired_count,
        "openvpn_clients_count": openvpn_count,
        "wg_awg_clients_count": wg_awg_count,
        "blocked_openvpn_count": int(blocked_openvpn_count or 0),
        "blocked_wg_awg_count": int(blocked_wg_awg_count or 0),
        "blocked_total_count": int(blocked_openvpn_count or 0) + int(blocked_wg_awg_count or 0),
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
    openvpn_build_status_map,
    extract_client_name_from_config_file,
    wg_build_status_map,
    url_for,
    human_bytes=None,
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
    openvpn_policy_status_by_client = openvpn_build_status_map(openvpn_client_names)
    wg_awg_client_names = collect_unique_client_names(wg_files, extract_client_name_from_config_file)
    wg_awg_client_names.update(collect_unique_client_names(amneziawg_files, extract_client_name_from_config_file))
    wg_policy_status_by_client = wg_build_status_map(wg_awg_client_names)

    if is_admin:
        cert_expiry = request_config_file_handler.get_openvpn_cert_expiry()
        raw_banned_clients = read_banned_clients()

        for file_path in openvpn_files:
            filename = os.path.basename(file_path)
            client_name = request_config_file_handler._extract_client_name_from_ovpn(filename)
            if client_name and client_name in raw_banned_clients:
                banned_clients.add(client_name)

    if openvpn_policy_status_by_client:
        for client_name in openvpn_client_names:
            ovpn_state = (openvpn_policy_status_by_client.get(client_name) or {})
            if bool(ovpn_state.get("is_blocked")):
                banned_clients.add(client_name)

    blocked_wg_awg_names = {
        client_name
        for client_name in wg_awg_client_names
        if bool((wg_policy_status_by_client.get(client_name.lower(), {}) or {}).get("is_blocked"))
    }
    blocked_entries = _build_blocked_entries(
        openvpn_blocked_clients=banned_clients,
        openvpn_policy_status_by_client=openvpn_policy_status_by_client,
        wg_policy_status_by_client=wg_policy_status_by_client,
        wg_awg_client_names=blocked_wg_awg_names,
    )

    kpi = build_index_kpi(
        cert_expiry,
        blocked_openvpn_count=len(banned_clients),
        blocked_wg_awg_count=len(blocked_wg_awg_names),
        openvpn_count=len(openvpn_client_names),
        wg_awg_count=len(wg_awg_client_names),
    )

    openvpn_grouped = group_config_files_by_client(openvpn_files)
    amneziawg_grouped = group_config_files_by_client(amneziawg_files)
    wireguard_grouped = group_config_files_by_client(wg_files)

    row_kwargs = {
        "current_user": idx_user,
        "cert_expiry": cert_expiry,
        "banned_clients": banned_clients,
        "openvpn_policy_status_by_client": openvpn_policy_status_by_client,
        "wg_policy_status_by_client": wg_policy_status_by_client,
        "url_for": url_for,
        "human_bytes": human_bytes,
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
        "banned_clients_count": kpi["blocked_total_count"],
        "blocked_total_count": kpi["blocked_total_count"],
        "blocked_openvpn_count": kpi["blocked_openvpn_count"],
        "blocked_wg_awg_count": kpi["blocked_wg_awg_count"],
        "blocked_entries": blocked_entries,
        "current_openvpn_group": group,
        "current_openvpn_folders": folders,
        "openvpn_client_rows": build_client_table_rows("openvpn", openvpn_grouped, **row_kwargs),
        "amneziawg_client_rows": build_client_table_rows("amneziawg", amneziawg_grouped, **row_kwargs),
        "wireguard_client_rows": build_client_table_rows("wireguard", wireguard_grouped, **row_kwargs),
        "client_details_payload": {"connected": {}, "traffic": {}},
    }
