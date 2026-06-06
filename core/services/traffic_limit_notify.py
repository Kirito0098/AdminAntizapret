"""Telegram notifications for automatic traffic-limit blocks and unblocks."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from core.services.traffic_limit import (
    TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED,
    get_traffic_limit_period_start,
)


class TrafficLimitNotifyService:
    def __init__(
        self,
        *,
        admin_notify_service,
        wg_access_policy_service,
        openvpn_access_policy_service,
        config_paths,
        extract_client_name_from_config_file,
        logger,
    ):
        self.admin_notify_service = admin_notify_service
        self.wg_access_policy_service = wg_access_policy_service
        self.openvpn_access_policy_service = openvpn_access_policy_service
        self.config_paths = config_paths or {}
        self.extract_client_name_from_config_file = extract_client_name_from_config_file
        self.logger = logger
        self._lock = threading.Lock()
        self._client_state: dict[tuple[str, str], dict] = {}
        self._protocol_index: dict[str, str] | None = None

    def process_clients(self, *, protocol_scope: str, client_names):
        for client_name in client_names or []:
            try:
                self.process_client(protocol_scope=protocol_scope, client_name=client_name)
            except Exception as exc:
                self.logger.warning(
                    "Traffic limit notify error for %s/%s: %s",
                    protocol_scope,
                    client_name,
                    exc,
                )

    def process_client(self, *, protocol_scope: str, client_name: str):
        normalized = (client_name or "").strip().lower()
        if not normalized:
            return

        state = self._load_policy_state(protocol_scope, normalized)
        if not state or not state.get("traffic_limit_bytes"):
            self._forget_client(protocol_scope, normalized)
            return

        period_days = state.get("traffic_limit_period_days")
        period_start = self._period_start_key(period_days)
        traffic_blocked = bool(
            state.get("traffic_limit_exceeded")
            and state.get("block_mode") == "traffic_limit"
        )
        cache_key = (protocol_scope, normalized)
        target_type = self._resolve_target_type(protocol_scope, normalized)

        with self._lock:
            cached = self._client_state.get(cache_key)
            prev_blocked = bool(cached.get("traffic_blocked")) if cached else False
            prev_period_start = cached.get("last_period_start") if cached else None

            if not prev_blocked and traffic_blocked:
                if not cached or cached.get("notified_block_period") != period_start:
                    self._send_block_notification(
                        target_type=target_type,
                        client_name=normalized,
                        state=state,
                    )
                    if cached is None:
                        cached = {}
                        self._client_state[cache_key] = cached
                    cached["notified_block_period"] = period_start
            elif prev_blocked and not traffic_blocked:
                if (
                    period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED
                    and prev_period_start
                    and period_start != prev_period_start
                    and cached.get("notified_unblock_period") != period_start
                ):
                    self._send_unblock_notification(
                        target_type=target_type,
                        client_name=normalized,
                        state=state,
                    )
                    cached["notified_unblock_period"] = period_start

            if cached is None:
                cached = {}
                self._client_state[cache_key] = cached
            cached["traffic_blocked"] = traffic_blocked
            cached["last_period_start"] = period_start

    def _forget_client(self, protocol_scope: str, normalized: str):
        with self._lock:
            self._client_state.pop((protocol_scope, normalized), None)

    def _load_policy_state(self, protocol_scope: str, normalized: str):
        if protocol_scope == "wg":
            status_map = self.wg_access_policy_service.build_status_map([normalized])
        elif protocol_scope == "openvpn":
            status_map = self.openvpn_access_policy_service.build_status_map([normalized])
        else:
            return None
        return status_map.get(normalized)

    def _period_start_key(self, period_days):
        if period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
            period_start = get_traffic_limit_period_start(period_days)
            if period_start is not None:
                return period_start.isoformat()
        return "all-time"

    def _resolve_target_type(self, protocol_scope: str, normalized: str) -> str:
        if protocol_scope == "openvpn":
            return "openvpn"
        protocol = self._build_protocol_index().get(normalized)
        return protocol or "wireguard"

    def _build_protocol_index(self) -> dict[str, str]:
        if self._protocol_index is not None:
            return self._protocol_index

        index: dict[str, str] = {}
        for config_type, target_type in (("amneziawg", "amneziawg"), ("wg", "wireguard")):
            for base_dir in self.config_paths.get(config_type, []):
                if not os.path.exists(base_dir):
                    continue
                for root, _, files in os.walk(base_dir):
                    for filename in files:
                        if not filename.lower().endswith(".conf"):
                            continue
                        client_name = self.extract_client_name_from_config_file(filename)
                        if not client_name:
                            continue
                        normalized = client_name.strip().lower()
                        if normalized not in index:
                            index[normalized] = target_type

        self._protocol_index = index
        return index

    def _build_details(self, state: dict) -> str:
        parts = [
            f"limit_bytes={int(state.get('traffic_limit_bytes') or 0)}",
            f"consumed_bytes={int(state.get('traffic_consumed_bytes') or 0)}",
        ]
        period_days = state.get("traffic_limit_period_days")
        if period_days is not None:
            parts.append(f"period_days={period_days}")
        unblock_at = (state.get("traffic_limit_unblock_at") or "").strip()
        if unblock_at:
            parts.append(f"unblock_at={unblock_at}")
        return " ".join(parts)

    def _send_block_notification(self, *, target_type: str, client_name: str, state: dict):
        self.admin_notify_service.send(
            "traffic_limit_block",
            target_name=client_name,
            target_type=target_type,
            details=self._build_details(state),
        )

    def _send_unblock_notification(self, *, target_type: str, client_name: str, state: dict):
        self.admin_notify_service.send(
            "traffic_limit_unblock",
            target_name=client_name,
            target_type=target_type,
            details=self._build_details(state),
        )
