import sys

from .active_web_session import ActiveWebSessionService
from .logs_dashboard_cache import LogsDashboardCacheService
from .maintenance_scheduler import MaintenanceSchedulerService
from .network_status_collector import NetworkStatusCollectorService
from .openvpn_socket_reader import OpenVPNSocketReaderService
from .peer_info_cache import PeerInfoCacheService
from .traffic_maintenance import TrafficMaintenanceService
from .traffic_persistence import TrafficPersistenceService


def build_services(
    *,
    app,
    db,
    app_root,
    logs_dir,
    status_log_cleanup_marker,
    status_log_cleanup_periods,
    traffic_sync_cron_marker,
    traffic_sync_cron_expr,
    traffic_sync_enabled,
    nightly_idle_restart_marker,
    runtime_backup_cleanup_marker,
    runtime_backup_cleanup_cron_expr,
    runtime_backup_root,
    runtime_backup_retention_hours,
    openvpn_socket_dir,
    openvpn_socket_timeout,
    openvpn_socket_idle_timeout,
    openvpn_log_tail_lines,
    openvpn_event_max_response_bytes,
    wireguard_config_files,
    wireguard_active_handshake_seconds,
    wireguard_peer_cache_sync_min_interval_seconds,
    status_log_files,
    traffic_db_stale_seconds,
    openvpn_peer_info_cache_ttl_seconds,
    openvpn_peer_info_history_retention_seconds,
    logs_dashboard_cache_ttl_seconds,
    active_web_session_model,
    user_traffic_sample_model,
    traffic_session_state_model,
    user_traffic_stat_model,
    user_traffic_stat_protocol_model,
    openvpn_peer_info_cache_model,
    openvpn_peer_info_history_model,
    wireguard_peer_cache_model,
    logs_dashboard_cache_model,
    background_task_model,
    integrity_error_cls,
    is_valid_cron_expression,
    get_nightly_idle_restart_settings,
    get_active_web_session_settings,
    collect_config_protocols_by_client,
    build_session_key,
    collect_status_rows_for_snapshot,
    human_bytes,
    extract_ip_from_openvpn_address,
    profile_meta,
    read_status_source,
    read_event_source,
    normalize_openvpn_endpoint,
    normalize_traffic_protocol_type,
    rebuild_user_traffic_stats_from_samples,
    human_seconds,
    format_dt,
    collect_logs_dashboard_data,
    enqueue_background_task,
):
    maintenance_scheduler_service = MaintenanceSchedulerService(
        app_root=app_root,
        logs_dir=logs_dir,
        python_executable=(sys.executable or "python3"),
        status_log_cleanup_marker=status_log_cleanup_marker,
        status_log_cleanup_periods=status_log_cleanup_periods,
        traffic_sync_cron_marker=traffic_sync_cron_marker,
        traffic_sync_cron_expr=traffic_sync_cron_expr,
        traffic_sync_enabled=traffic_sync_enabled,
        nightly_idle_restart_marker=nightly_idle_restart_marker,
        runtime_backup_cleanup_marker=runtime_backup_cleanup_marker,
        runtime_backup_cleanup_cron_expr=runtime_backup_cleanup_cron_expr,
        runtime_backup_root=runtime_backup_root,
        runtime_backup_retention_hours=runtime_backup_retention_hours,
        is_valid_cron_expression=is_valid_cron_expression,
        get_nightly_idle_restart_settings=get_nightly_idle_restart_settings,
    )

    active_web_session_service = ActiveWebSessionService(
        active_web_session_model=active_web_session_model,
        get_active_web_session_settings=get_active_web_session_settings,
    )

    traffic_maintenance_service = TrafficMaintenanceService(
        db=db,
        user_traffic_sample_model=user_traffic_sample_model,
        traffic_session_state_model=traffic_session_state_model,
        user_traffic_stat_model=user_traffic_stat_model,
        user_traffic_stat_protocol_model=user_traffic_stat_protocol_model,
        collect_config_protocols_by_client=collect_config_protocols_by_client,
        build_session_key=build_session_key,
        collect_status_rows_for_snapshot=collect_status_rows_for_snapshot,
    )

    openvpn_socket_reader_service = OpenVPNSocketReaderService(
        openvpn_socket_dir=openvpn_socket_dir,
        openvpn_socket_timeout=openvpn_socket_timeout,
        openvpn_socket_idle_timeout=openvpn_socket_idle_timeout,
        openvpn_log_tail_lines=openvpn_log_tail_lines,
        openvpn_event_max_response_bytes=openvpn_event_max_response_bytes,
    )

    network_status_collector_service = NetworkStatusCollectorService(
        app=app,
        db=db,
        wireguard_peer_cache_model=wireguard_peer_cache_model,
        wireguard_config_files=wireguard_config_files,
        wireguard_active_handshake_seconds=wireguard_active_handshake_seconds,
        wireguard_peer_cache_sync_min_interval_seconds=wireguard_peer_cache_sync_min_interval_seconds,
        status_log_files=status_log_files,
        human_bytes=human_bytes,
        extract_ip_from_openvpn_address=extract_ip_from_openvpn_address,
        profile_meta=profile_meta,
        read_status_source=read_status_source,
        read_event_source=read_event_source,
        normalize_openvpn_endpoint=normalize_openvpn_endpoint,
    )

    traffic_persistence_service = TrafficPersistenceService(
        app=app,
        db=db,
        traffic_session_state_model=traffic_session_state_model,
        user_traffic_stat_model=user_traffic_stat_model,
        user_traffic_stat_protocol_model=user_traffic_stat_protocol_model,
        user_traffic_sample_model=user_traffic_sample_model,
        openvpn_peer_info_cache_model=openvpn_peer_info_cache_model,
        openvpn_peer_info_history_model=openvpn_peer_info_history_model,
        integrity_error_cls=integrity_error_cls,
        normalize_traffic_protocol_type=normalize_traffic_protocol_type,
        rebuild_user_traffic_stats_from_samples=rebuild_user_traffic_stats_from_samples,
        human_bytes=human_bytes,
        human_seconds=human_seconds,
        format_dt=format_dt,
        traffic_db_stale_seconds=traffic_db_stale_seconds,
    )

    peer_info_cache_service = PeerInfoCacheService(
        db=db,
        openvpn_peer_info_cache_model=openvpn_peer_info_cache_model,
        openvpn_peer_info_history_model=openvpn_peer_info_history_model,
        openvpn_peer_info_cache_ttl_seconds=openvpn_peer_info_cache_ttl_seconds,
        openvpn_peer_info_history_retention_seconds=openvpn_peer_info_history_retention_seconds,
    )

    logs_dashboard_cache_service = LogsDashboardCacheService(
        db=db,
        logs_dashboard_cache_model=logs_dashboard_cache_model,
        background_task_model=background_task_model,
        logs_dashboard_cache_ttl_seconds=logs_dashboard_cache_ttl_seconds,
        collect_logs_dashboard_data=collect_logs_dashboard_data,
        enqueue_background_task=enqueue_background_task,
        human_bytes=human_bytes,
    )

    return {
        "maintenance_scheduler_service": maintenance_scheduler_service,
        "active_web_session_service": active_web_session_service,
        "traffic_maintenance_service": traffic_maintenance_service,
        "openvpn_socket_reader_service": openvpn_socket_reader_service,
        "network_status_collector_service": network_status_collector_service,
        "traffic_persistence_service": traffic_persistence_service,
        "peer_info_cache_service": peer_info_cache_service,
        "logs_dashboard_cache_service": logs_dashboard_cache_service,
    }
