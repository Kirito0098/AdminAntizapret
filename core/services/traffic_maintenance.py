from collections import defaultdict
from datetime import datetime


class TrafficMaintenanceService:
    def __init__(
        self,
        *,
        db,
        user_traffic_sample_model,
        traffic_session_state_model,
        user_traffic_stat_model,
        user_traffic_stat_protocol_model,
        collect_config_protocols_by_client,
        build_session_key,
        collect_status_rows_for_snapshot,
    ):
        self.db = db
        self.user_traffic_sample_model = user_traffic_sample_model
        self.traffic_session_state_model = traffic_session_state_model
        self.user_traffic_stat_model = user_traffic_stat_model
        self.user_traffic_stat_protocol_model = user_traffic_stat_protocol_model
        self.collect_config_protocols_by_client = collect_config_protocols_by_client
        self.build_session_key = build_session_key
        self.collect_status_rows_for_snapshot = collect_status_rows_for_snapshot

    def normalize_traffic_protocol_scope(self, protocol_scope):
        scope = (protocol_scope or "all").strip().lower()
        if scope not in ("all", "openvpn", "wireguard"):
            return "all"
        return scope

    def normalize_traffic_protocol_type(self, protocol_type, fallback="openvpn"):
        protocol = (protocol_type or fallback).strip().lower()
        if protocol not in ("openvpn", "wireguard"):
            protocol = fallback if fallback in ("openvpn", "wireguard") else "openvpn"
        return protocol

    def profile_matches_protocol_scope(self, profile, protocol_scope):
        scope = self.normalize_traffic_protocol_scope(protocol_scope)
        is_wireguard_profile = str(profile or "").strip().lower().endswith("-wg")
        if scope == "wireguard":
            return is_wireguard_profile
        if scope == "openvpn":
            return not is_wireguard_profile
        return True

    def collect_wireguard_only_client_names_lower(self):
        protocols_by_client = self.collect_config_protocols_by_client()
        result = set()
        for client_name, protocols in protocols_by_client.items():
            normalized = {
                str(protocol or "").strip()
                for protocol in (protocols or set())
                if str(protocol or "").strip()
            }
            if normalized == {"WireGuard"}:
                name = (client_name or "").strip().lower()
                if name:
                    result.add(name)
        return result

    def delete_persisted_traffic_rows_by_scope(self, protocol_scope):
        scope = self.normalize_traffic_protocol_scope(protocol_scope)

        if scope == "all":
            deleted_samples = self.user_traffic_sample_model.query.delete(synchronize_session=False)
            deleted_sessions = self.traffic_session_state_model.query.delete(synchronize_session=False)
            return {
                "scope": scope,
                "deleted_samples": int(deleted_samples or 0),
                "deleted_sessions": int(deleted_sessions or 0),
            }

        if scope == "openvpn":
            deleted_samples = self.user_traffic_sample_model.query.filter(
                self.user_traffic_sample_model.protocol_type != "wireguard"
            ).delete(synchronize_session=False)
            deleted_sessions = self.traffic_session_state_model.query.filter(
                self.traffic_session_state_model.profile.notlike("%-wg")
            ).delete(synchronize_session=False)
            return {
                "scope": scope,
                "deleted_samples": int(deleted_samples or 0),
                "deleted_sessions": int(deleted_sessions or 0),
            }

        wireguard_only_clients = self.collect_wireguard_only_client_names_lower()
        sample_query = self.user_traffic_sample_model.query.filter(
            self.user_traffic_sample_model.protocol_type == "wireguard"
        )
        if wireguard_only_clients:
            sample_query = self.user_traffic_sample_model.query.filter(
                (self.user_traffic_sample_model.protocol_type == "wireguard")
                | (
                    (self.user_traffic_sample_model.protocol_type != "wireguard")
                    & self.db.func.lower(self.user_traffic_sample_model.common_name).in_(
                        sorted(wireguard_only_clients)
                    )
                )
            )

        deleted_samples = sample_query.delete(synchronize_session=False)
        deleted_sessions = self.traffic_session_state_model.query.filter(
            self.traffic_session_state_model.profile.like("%-wg")
        ).delete(synchronize_session=False)

        return {
            "scope": scope,
            "deleted_samples": int(deleted_samples or 0),
            "deleted_sessions": int(deleted_sessions or 0),
        }

    def seed_traffic_session_baseline_for_scope(self, status_rows, protocol_scope, now=None):
        scope = self.normalize_traffic_protocol_scope(protocol_scope)
        now = now or datetime.utcnow()

        sessions_by_key = {
            row.session_key: row
            for row in self.traffic_session_state_model.query.all()
        }

        seen_scope_keys = set()
        seeded_users = set()
        inserted_sessions = 0
        updated_sessions = 0
        deactivated_sessions = 0

        for status_row in (status_rows or []):
            profile = status_row.get("profile", "unknown")
            if not self.profile_matches_protocol_scope(profile, scope):
                continue

            for client in status_row.get("traffic_clients", status_row.get("clients", [])):
                common_name = (client.get("common_name") or "-").strip()
                if not common_name or common_name == "-":
                    continue

                session_key = self.build_session_key(profile, client)
                if session_key in seen_scope_keys:
                    continue
                seen_scope_keys.add(session_key)

                current_rx = int(client.get("bytes_received") or 0)
                current_tx = int(client.get("bytes_sent") or 0)

                session_state = sessions_by_key.get(session_key)
                if session_state is None:
                    session_state = self.traffic_session_state_model(
                        session_key=session_key,
                        profile=profile,
                        common_name=common_name,
                        real_address=(client.get("real_address") or "").strip() or None,
                        virtual_address=(client.get("virtual_address") or "").strip() or None,
                        connected_since_ts=int(client.get("connected_since_ts") or 0),
                        last_bytes_received=current_rx,
                        last_bytes_sent=current_tx,
                        is_active=True,
                        last_seen_at=now,
                        ended_at=None,
                    )
                    self.db.session.add(session_state)
                    sessions_by_key[session_key] = session_state
                    inserted_sessions += 1
                else:
                    session_state.profile = profile
                    session_state.common_name = common_name
                    session_state.real_address = (client.get("real_address") or "").strip() or None
                    session_state.virtual_address = (client.get("virtual_address") or "").strip() or None
                    session_state.connected_since_ts = int(client.get("connected_since_ts") or 0)
                    session_state.last_bytes_received = current_rx
                    session_state.last_bytes_sent = current_tx
                    session_state.is_active = True
                    session_state.last_seen_at = now
                    session_state.ended_at = None
                    updated_sessions += 1

                seeded_users.add(common_name)

        for session_key, session_state in sessions_by_key.items():
            if not self.profile_matches_protocol_scope(session_state.profile, scope):
                continue
            if session_key in seen_scope_keys:
                continue
            if session_state.is_active:
                session_state.is_active = False
                session_state.ended_at = now
                deactivated_sessions += 1

        return {
            "scope": scope,
            "seeded_users": seeded_users,
            "active_sessions": len(seen_scope_keys),
            "inserted_sessions": inserted_sessions,
            "updated_sessions": updated_sessions,
            "deactivated_sessions": deactivated_sessions,
        }

    def rebuild_user_traffic_stats_from_samples(self, seed_users=None, now=None):
        now = now or datetime.utcnow()
        self.user_traffic_stat_model.query.delete(synchronize_session=False)
        self.user_traffic_stat_protocol_model.query.delete(synchronize_session=False)

        stats_map = {}
        stats_map_by_protocol = {}
        wireguard_only_clients = self.collect_wireguard_only_client_names_lower()

        for sample in self.user_traffic_sample_model.query.order_by(
            self.user_traffic_sample_model.created_at.asc()
        ).all():
            common_name = (sample.common_name or "").strip()
            if not common_name:
                continue

            normalized_protocol = self.normalize_traffic_protocol_type(sample.protocol_type, fallback="openvpn")
            if normalized_protocol == "openvpn" and common_name.strip().lower() in wireguard_only_clients:
                normalized_protocol = "wireguard"

            stat = stats_map.get(common_name)
            sample_dt = sample.created_at or now
            if stat is None:
                stat = {
                    "total_received": 0,
                    "total_sent": 0,
                    "total_received_vpn": 0,
                    "total_sent_vpn": 0,
                    "total_received_antizapret": 0,
                    "total_sent_antizapret": 0,
                    "first_seen_at": sample_dt,
                    "last_seen_at": sample_dt,
                }
                stats_map[common_name] = stat

            protocol_key = (common_name, normalized_protocol)
            protocol_stat = stats_map_by_protocol.get(protocol_key)
            if protocol_stat is None:
                protocol_stat = {
                    "total_received": 0,
                    "total_sent": 0,
                    "total_received_vpn": 0,
                    "total_sent_vpn": 0,
                    "total_received_antizapret": 0,
                    "total_sent_antizapret": 0,
                    "first_seen_at": sample_dt,
                    "last_seen_at": sample_dt,
                }
                stats_map_by_protocol[protocol_key] = protocol_stat

            delta_rx = max(int(sample.delta_received or 0), 0)
            delta_tx = max(int(sample.delta_sent or 0), 0)
            network_type = (sample.network_type or "vpn").strip().lower()

            stat["total_received"] += delta_rx
            stat["total_sent"] += delta_tx
            if network_type == "antizapret":
                stat["total_received_antizapret"] += delta_rx
                stat["total_sent_antizapret"] += delta_tx
            else:
                stat["total_received_vpn"] += delta_rx
                stat["total_sent_vpn"] += delta_tx

            protocol_stat["total_received"] += delta_rx
            protocol_stat["total_sent"] += delta_tx
            if network_type == "antizapret":
                protocol_stat["total_received_antizapret"] += delta_rx
                protocol_stat["total_sent_antizapret"] += delta_tx
            else:
                protocol_stat["total_received_vpn"] += delta_rx
                protocol_stat["total_sent_vpn"] += delta_tx

            if sample_dt < stat["first_seen_at"]:
                stat["first_seen_at"] = sample_dt
            if sample_dt > stat["last_seen_at"]:
                stat["last_seen_at"] = sample_dt

            if sample_dt < protocol_stat["first_seen_at"]:
                protocol_stat["first_seen_at"] = sample_dt
            if sample_dt > protocol_stat["last_seen_at"]:
                protocol_stat["last_seen_at"] = sample_dt

        for common_name, stat in stats_map.items():
            self.db.session.add(
                self.user_traffic_stat_model(
                    common_name=common_name,
                    total_received=stat["total_received"],
                    total_sent=stat["total_sent"],
                    total_received_vpn=stat["total_received_vpn"],
                    total_sent_vpn=stat["total_sent_vpn"],
                    total_received_antizapret=stat["total_received_antizapret"],
                    total_sent_antizapret=stat["total_sent_antizapret"],
                    total_sessions=0,
                    first_seen_at=stat["first_seen_at"] or now,
                    last_seen_at=stat["last_seen_at"] or now,
                )
            )

        for (common_name, protocol_type), stat in stats_map_by_protocol.items():
            self.db.session.add(
                self.user_traffic_stat_protocol_model(
                    common_name=common_name,
                    protocol_type=protocol_type,
                    total_received=stat["total_received"],
                    total_sent=stat["total_sent"],
                    total_received_vpn=stat["total_received_vpn"],
                    total_sent_vpn=stat["total_sent_vpn"],
                    total_received_antizapret=stat["total_received_antizapret"],
                    total_sent_antizapret=stat["total_sent_antizapret"],
                    total_sessions=0,
                    first_seen_at=stat["first_seen_at"] or now,
                    last_seen_at=stat["last_seen_at"] or now,
                )
            )

        seeded_only = 0
        seeded_only_protocol_rows = 0
        seed_names = sorted({(name or "").strip() for name in (seed_users or set()) if (name or "").strip()})
        seed_protocols_by_name = defaultdict(set)
        if seed_names:
            seed_sessions = self.traffic_session_state_model.query.filter(
                self.traffic_session_state_model.common_name.in_(seed_names)
            ).all()
            for state_row in seed_sessions:
                protocol_type = "wireguard" if str(state_row.profile or "").strip().lower().endswith("-wg") else "openvpn"
                seed_protocols_by_name[(state_row.common_name or "").strip()].add(protocol_type)

        for common_name in seed_names:
            if common_name in stats_map:
                continue
            self.db.session.add(
                self.user_traffic_stat_model(
                    common_name=common_name,
                    total_received=0,
                    total_sent=0,
                    total_received_vpn=0,
                    total_sent_vpn=0,
                    total_received_antizapret=0,
                    total_sent_antizapret=0,
                    total_sessions=0,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            seeded_only += 1

            protocol_candidates = seed_protocols_by_name.get(common_name, set()) or {"openvpn"}
            for protocol_type in sorted(protocol_candidates):
                if (common_name, protocol_type) in stats_map_by_protocol:
                    continue
                self.db.session.add(
                    self.user_traffic_stat_protocol_model(
                        common_name=common_name,
                        protocol_type=protocol_type,
                        total_received=0,
                        total_sent=0,
                        total_received_vpn=0,
                        total_sent_vpn=0,
                        total_received_antizapret=0,
                        total_sent_antizapret=0,
                        total_sessions=0,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                seeded_only_protocol_rows += 1

        return {
            "rebuilt_users": len(stats_map),
            "rebuilt_users_protocol_rows": len(stats_map_by_protocol),
            "seeded_only_users": seeded_only,
            "seeded_only_protocol_rows": seeded_only_protocol_rows,
        }

    def reset_persisted_traffic_data(self, protocol_scope="all"):
        scope = self.normalize_traffic_protocol_scope(protocol_scope)
        scope_human = {
            "all": "вся статистика",
            "openvpn": "OpenVPN",
            "wireguard": "WireGuard/AWG",
        }

        try:
            now = datetime.utcnow()
            status_rows = self.collect_status_rows_for_snapshot()

            deleted_info = self.delete_persisted_traffic_rows_by_scope(scope)
            baseline_info = self.seed_traffic_session_baseline_for_scope(status_rows, scope, now=now)
            rebuilt_info = self.rebuild_user_traffic_stats_from_samples(
                seed_users=baseline_info.get("seeded_users", set()),
                now=now,
            )

            self.db.session.commit()

            if scope == "all":
                return True, (
                    "Накопленная статистика трафика очищена. "
                    f"Точка отсчета установлена: пользователей {len(baseline_info.get('seeded_users', set()))}, "
                    f"активных сессий {baseline_info.get('active_sessions', 0)}."
                )

            return True, (
                f"Статистика {scope_human.get(scope, scope)} очищена. "
                f"Удалено записей: samples={deleted_info.get('deleted_samples', 0)}, "
                f"sessions={deleted_info.get('deleted_sessions', 0)}. "
                f"Обновлен baseline активных сессий: {baseline_info.get('active_sessions', 0)}. "
                f"Пользователей в БД: {int(rebuilt_info.get('rebuilt_users', 0)) + int(rebuilt_info.get('seeded_only_users', 0))}."
            )
        except Exception as e:
            self.db.session.rollback()
            return False, f"Ошибка сброса статистики трафика: {e}"
