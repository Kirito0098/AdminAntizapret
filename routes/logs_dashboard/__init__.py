from .api import register_logs_dashboard_api_routes
from .routes import register_logs_dashboard_page_routes


def register_logs_dashboard_routes(
    app,
    sock,
    *,
    auth_manager,
    get_logs_dashboard_data_cached,
    cleanup_status_logs_now,
    set_status_cleanup_schedule,
    normalize_traffic_protocol_scope,
    reset_persisted_traffic_data,
    collect_existing_config_client_names,
    normalize_traffic_client_identity,
    delete_client_traffic_stats,
    queue_logs_dashboard_refresh_after_traffic_mutation,
    openvpn_log_tail_lines,
    db,
    background_task_model,
    collect_config_protocols_by_client,
    user_traffic_sample_model,
    human_bytes,
):
    register_logs_dashboard_page_routes(
        app,
        sock,
        auth_manager=auth_manager,
        get_logs_dashboard_data_cached=get_logs_dashboard_data_cached,
        cleanup_status_logs_now=cleanup_status_logs_now,
        set_status_cleanup_schedule=set_status_cleanup_schedule,
        normalize_traffic_protocol_scope=normalize_traffic_protocol_scope,
        reset_persisted_traffic_data=reset_persisted_traffic_data,
        collect_existing_config_client_names=collect_existing_config_client_names,
        normalize_traffic_client_identity=normalize_traffic_client_identity,
        delete_client_traffic_stats=delete_client_traffic_stats,
        queue_logs_dashboard_refresh_after_traffic_mutation=queue_logs_dashboard_refresh_after_traffic_mutation,
        openvpn_log_tail_lines=openvpn_log_tail_lines,
    )
    register_logs_dashboard_api_routes(
        app,
        auth_manager=auth_manager,
        db=db,
        background_task_model=background_task_model,
        collect_config_protocols_by_client=collect_config_protocols_by_client,
        user_traffic_sample_model=user_traffic_sample_model,
        human_bytes=human_bytes,
    )


__all__ = ["register_logs_dashboard_routes"]
