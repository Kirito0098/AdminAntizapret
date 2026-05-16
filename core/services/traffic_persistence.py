from datetime import datetime, timedelta

from sqlalchemy import case


class TrafficPersistenceService:
    def __init__(
        self,
        *,
        app,
        db,
        traffic_session_state_model,
        user_traffic_stat_model,
        user_traffic_stat_protocol_model,
        user_traffic_sample_model,
        openvpn_peer_info_cache_model,
        openvpn_peer_info_history_model,
        wireguard_peer_cache_model=None,
        integrity_error_cls,
        normalize_traffic_protocol_type,
        normalize_traffic_client_identity=None,
        rebuild_user_traffic_stats_from_samples,
        human_bytes,
        human_seconds,
        format_dt,
        traffic_db_stale_seconds,
    ):
        self.app = app
        self.db = db
        self.traffic_session_state_model = traffic_session_state_model
        self.user_traffic_stat_model = user_traffic_stat_model
        self.user_traffic_stat_protocol_model = user_traffic_stat_protocol_model
        self.user_traffic_sample_model = user_traffic_sample_model
        self.openvpn_peer_info_cache_model = openvpn_peer_info_cache_model
        self.openvpn_peer_info_history_model = openvpn_peer_info_history_model
        self.wireguard_peer_cache_model = wireguard_peer_cache_model
        self.integrity_error_cls = integrity_error_cls
        self.normalize_traffic_protocol_type = normalize_traffic_protocol_type
        self.normalize_traffic_client_identity = normalize_traffic_client_identity or (
            lambda name: (name or "").strip().lower()
        )
        self.rebuild_user_traffic_stats_from_samples = rebuild_user_traffic_stats_from_samples
        self.human_bytes = human_bytes
        self.human_seconds = human_seconds
        self.format_dt = format_dt
        self.traffic_db_stale_seconds = traffic_db_stale_seconds

    def build_session_key(self, profile, client):
        session_kind = (client.get("session_kind") or "").strip().lower()
        if session_kind == "wireguard" or str(profile or "").endswith("-wg"):
            common_name = (client.get("common_name") or "-").strip()
            peer_public_key = (client.get("peer_public_key") or "-").strip()
            virtual_address = (client.get("virtual_address") or "-").strip()
            # Для WG ключ сессии должен быть стабильным между handshake, иначе дельта удваивается.
            return f"{profile}|wg|{common_name}|{peer_public_key}|{virtual_address}"

        common_name = (client.get("common_name") or "-").strip()
        real_address = (client.get("real_address") or "-").strip()
        virtual_address = (client.get("virtual_address") or "-").strip()
        connected_since_ts = int(client.get("connected_since_ts") or 0)
        return f"{profile}|{common_name}|{real_address}|{virtual_address}|{connected_since_ts}"

    def is_retryable_snapshot_integrity_error(self, exc):
        error_text = str(getattr(exc, "orig", exc) or exc).lower()
        retryable_markers = (
            "unique constraint failed: traffic_session_state.session_key",
            "unique constraint failed: user_traffic_stat.common_name",
            "unique constraint failed: user_traffic_stat_protocol.common_name, user_traffic_stat_protocol.protocol_type",
        )
        return any(marker in error_text for marker in retryable_markers)

    def persist_traffic_snapshot(self, status_rows, retry_on_integrity=True):
        """Сохраняет дельту трафика из текущего снимка *-status.log в БД."""
        now = datetime.utcnow()

        sessions_by_key = {
            row.session_key: row
            for row in self.traffic_session_state_model.query.all()
        }
        previously_active_keys = {
            key for key, row in sessions_by_key.items() if bool(row.is_active)
        }
        stats_by_user = {
            (
                (row.common_name or "").strip(),
                self.normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn"),
            ): row
            for row in self.user_traffic_stat_protocol_model.query.all()
        }

        seen_keys = set()

        for status_row in status_rows:
            profile = status_row.get("profile", "unknown")
            for client in status_row.get("traffic_clients", status_row.get("clients", [])):
                session_key = self.build_session_key(profile, client)
                if session_key in seen_keys:
                    continue
                seen_keys.add(session_key)

                current_rx = int(client.get("bytes_received") or 0)
                current_tx = int(client.get("bytes_sent") or 0)
                common_name = (client.get("common_name") or "-").strip()
                is_antizapret_profile = str(profile).startswith("antizapret")
                is_wireguard_profile = str(profile).endswith("-wg")
                protocol_type = "wireguard" if is_wireguard_profile else "openvpn"

                session_state = sessions_by_key.get(session_key)
                is_new_session = session_state is None

                if is_new_session:
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
                    if is_wireguard_profile:
                        # Для нового WG-ключа считаем текущие байты baseline, чтобы не учитывать
                        # накопленные счетчики интерфейса как новый трафик клиента.
                        delta_rx = 0
                        delta_tx = 0
                    else:
                        delta_rx = max(current_rx, 0)
                        delta_tx = max(current_tx, 0)
                else:
                    delta_rx = current_rx - int(session_state.last_bytes_received or 0)
                    delta_tx = current_tx - int(session_state.last_bytes_sent or 0)

                    # Если счётчик сбросился, учитываем текущее значение как новую дельту.
                    if delta_rx < 0:
                        delta_rx = max(current_rx, 0)
                    if delta_tx < 0:
                        delta_tx = max(current_tx, 0)

                    session_state.last_bytes_received = current_rx
                    session_state.last_bytes_sent = current_tx
                    session_state.last_seen_at = now
                    session_state.is_active = True
                    session_state.ended_at = None

                user_stat = stats_by_user.get((common_name, protocol_type))
                if user_stat is None:
                    user_stat = self.user_traffic_stat_protocol_model(
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
                    self.db.session.add(user_stat)
                    stats_by_user[(common_name, protocol_type)] = user_stat

                user_stat.total_received = int(user_stat.total_received or 0) + max(delta_rx, 0)
                user_stat.total_sent = int(user_stat.total_sent or 0) + max(delta_tx, 0)

                if max(delta_rx, 0) > 0 or max(delta_tx, 0) > 0:
                    self.db.session.add(
                        self.user_traffic_sample_model(
                            common_name=common_name,
                            network_type="antizapret" if is_antizapret_profile else "vpn",
                            protocol_type="wireguard" if is_wireguard_profile else "openvpn",
                            delta_received=max(delta_rx, 0),
                            delta_sent=max(delta_tx, 0),
                            created_at=now,
                        )
                    )

                if is_antizapret_profile:
                    user_stat.total_received_antizapret = int(user_stat.total_received_antizapret or 0) + max(delta_rx, 0)
                    user_stat.total_sent_antizapret = int(user_stat.total_sent_antizapret or 0) + max(delta_tx, 0)
                else:
                    user_stat.total_received_vpn = int(user_stat.total_received_vpn or 0) + max(delta_rx, 0)
                    user_stat.total_sent_vpn = int(user_stat.total_sent_vpn or 0) + max(delta_tx, 0)
                user_stat.last_seen_at = now
                if is_new_session:
                    user_stat.total_sessions = int(user_stat.total_sessions or 0) + 1

        for session_key, session_state in sessions_by_key.items():
            if session_key in seen_keys or session_key not in previously_active_keys:
                continue
            if session_state.is_active:
                session_state.is_active = False
                session_state.ended_at = now

        try:
            self.db.session.commit()
        except self.integrity_error_cls as exc:
            self.db.session.rollback()
            if retry_on_integrity and self.is_retryable_snapshot_integrity_error(exc):
                self.app.logger.warning("Повтор сохранения traffic snapshot после конкурентного UNIQUE-конфликта: %s", exc)
                self.persist_traffic_snapshot(status_rows, retry_on_integrity=False)
                return
            raise

    def protocol_label_from_type(self, protocol_type):
        normalized = self.normalize_traffic_protocol_type(protocol_type, fallback="openvpn")
        return "WireGuard" if normalized == "wireguard" else "OpenVPN"

    def ensure_protocol_traffic_stats_backfilled(self, now=None):
        now = now or datetime.utcnow()
        sample_total_expr = self.user_traffic_sample_model.delta_received + self.user_traffic_sample_model.delta_sent
        protocol_total_expr = self.user_traffic_stat_protocol_model.total_received + self.user_traffic_stat_protocol_model.total_sent

        sample_total_bytes = int(
            self.db.session.query(self.db.func.coalesce(self.db.func.sum(sample_total_expr), 0)).scalar() or 0
        )
        if sample_total_bytes <= 0:
            return False

        has_protocol_stats = self.db.session.query(self.user_traffic_stat_protocol_model.id).limit(1).first() is not None
        protocol_total_bytes = int(
            self.db.session.query(self.db.func.coalesce(self.db.func.sum(protocol_total_expr), 0)).scalar() or 0
        )

        if has_protocol_stats and protocol_total_bytes >= int(sample_total_bytes * 0.999):
            return False

        seed_users = {
            (row.common_name or "").strip()
            for row in self.traffic_session_state_model.query.with_entities(self.traffic_session_state_model.common_name).all()
            if (row.common_name or "").strip()
        }

        rebuilt_info = self.rebuild_user_traffic_stats_from_samples(seed_users=seed_users, now=now)
        self.db.session.commit()
        self.app.logger.info(
            "Выполнен авто-бэкфилл user_traffic_stat_protocol из sample: rows=%s, sample_total=%s, protocol_total_before=%s",
            int(rebuilt_info.get("rebuilt_users_protocol_rows", 0)),
            sample_total_bytes,
            protocol_total_bytes,
        )
        return True

    def collect_persisted_traffic_data(self, active_names=None, active_protocol_identities=None):
        try:
            self.ensure_protocol_traffic_stats_backfilled()
        except Exception as exc:
            self.db.session.rollback()
            self.app.logger.warning("Не удалось выполнить авто-бэкфилл user_traffic_stat_protocol: %s", exc)

        users = self.user_traffic_stat_protocol_model.query.all()
        now = datetime.utcnow()
        active_names = set(active_names or set())
        active_protocol_identities = {
            ((name or "").strip(), self.normalize_traffic_protocol_type(protocol, fallback="openvpn"))
            for name, protocol in (active_protocol_identities or set())
            if (name or "").strip()
        }
        day_1_since = now - timedelta(days=1)
        day_7_since = now - timedelta(days=7)
        day_30_since = now - timedelta(days=30)

        users_by_key = {
            (
                (row.common_name or "").strip(),
                self.normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn"),
            ): row
            for row in users
        }
        for state_row in self.traffic_session_state_model.query.with_entities(
            self.traffic_session_state_model.common_name,
            self.traffic_session_state_model.profile,
        ).all():
            common_name = (state_row.common_name or "").strip()
            if not common_name:
                continue
            protocol_type = "wireguard" if str(state_row.profile or "").strip().lower().endswith("-wg") else "openvpn"
            pair_key = (common_name, protocol_type)
            if pair_key in users_by_key:
                continue
            synthetic_row = self.user_traffic_stat_protocol_model(
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
            users.append(synthetic_row)
            users_by_key[pair_key] = synthetic_row

        delta_total_expr = self.user_traffic_sample_model.delta_received + self.user_traffic_sample_model.delta_sent
        recent_usage_rows = self.db.session.query(
            self.user_traffic_sample_model.common_name.label("common_name"),
            self.user_traffic_sample_model.protocol_type.label("protocol_type"),
            self.db.func.sum(
                case(
                    (self.user_traffic_sample_model.created_at >= day_1_since, delta_total_expr),
                    else_=0,
                )
            ).label("days_1"),
            self.db.func.sum(
                case(
                    (self.user_traffic_sample_model.created_at >= day_7_since, delta_total_expr),
                    else_=0,
                )
            ).label("days_7"),
            self.db.func.sum(delta_total_expr).label("days_30"),
        ).filter(
            self.user_traffic_sample_model.created_at >= day_30_since
        ).group_by(
            self.user_traffic_sample_model.common_name,
            self.user_traffic_sample_model.protocol_type,
        ).all()

        recent_usage = {
            (
                (row.common_name or "").strip(),
                self.normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn"),
            ): {
                "days_1": int(row.days_1 or 0),
                "days_7": int(row.days_7 or 0),
                "days_30": int(row.days_30 or 0),
            }
            for row in recent_usage_rows
        }

        users_sorted = sorted(
            users,
            key=lambda row: (int(row.total_received or 0) + int(row.total_sent or 0)),
            reverse=True,
        )

        rows = []
        total_received = 0
        total_sent = 0
        total_received_vpn = 0
        total_sent_vpn = 0
        total_received_antizapret = 0
        total_sent_antizapret = 0

        for row in users_sorted:
            protocol_type = self.normalize_traffic_protocol_type(row.protocol_type, fallback="openvpn")
            protocol_label = self.protocol_label_from_type(protocol_type)
            rx = int(row.total_received or 0)
            tx = int(row.total_sent or 0)
            rx_vpn = int(row.total_received_vpn or 0)
            tx_vpn = int(row.total_sent_vpn or 0)
            rx_antizapret = int(row.total_received_antizapret or 0)
            tx_antizapret = int(row.total_sent_antizapret or 0)
            total = rx + tx
            total_received += rx
            total_sent += tx
            total_received_vpn += rx_vpn
            total_sent_vpn += tx_vpn
            total_received_antizapret += rx_antizapret
            total_sent_antizapret += tx_antizapret

            recent = recent_usage.get((row.common_name, protocol_type), {"days_1": 0, "days_7": 0, "days_30": 0})
            traffic_1d = int(recent.get("days_1", 0))
            traffic_7d = int(recent.get("days_7", 0))
            traffic_30d = int(recent.get("days_30", 0))

            is_active = (row.common_name, protocol_type) in active_protocol_identities
            if not active_protocol_identities:
                is_active = row.common_name in active_names
            rows.append(
                {
                    "common_name": row.common_name,
                    "protocol_type": protocol_type,
                    "protocol_label": protocol_label,
                    "display_name": f"{row.common_name} ({protocol_label})",
                    "total_received": rx,
                    "total_sent": tx,
                    "total_bytes": total,
                    "total_received_vpn": rx_vpn,
                    "total_sent_vpn": tx_vpn,
                    "total_bytes_vpn": rx_vpn + tx_vpn,
                    "total_received_antizapret": rx_antizapret,
                    "total_sent_antizapret": tx_antizapret,
                    "total_bytes_antizapret": rx_antizapret + tx_antizapret,
                    "total_received_human": self.human_bytes(rx),
                    "total_sent_human": self.human_bytes(tx),
                    "total_bytes_human": self.human_bytes(total),
                    "total_received_vpn_human": self.human_bytes(rx_vpn),
                    "total_sent_vpn_human": self.human_bytes(tx_vpn),
                    "total_bytes_vpn_human": self.human_bytes(rx_vpn + tx_vpn),
                    "total_received_antizapret_human": self.human_bytes(rx_antizapret),
                    "total_sent_antizapret_human": self.human_bytes(tx_antizapret),
                    "total_bytes_antizapret_human": self.human_bytes(rx_antizapret + tx_antizapret),
                    "traffic_1d": traffic_1d,
                    "traffic_7d": traffic_7d,
                    "traffic_30d": traffic_30d,
                    "traffic_1d_human": self.human_bytes(traffic_1d),
                    "traffic_7d_human": self.human_bytes(traffic_7d),
                    "traffic_30d_human": self.human_bytes(traffic_30d),
                    "total_sessions": int(row.total_sessions or 0),
                    "first_seen_at": self.format_dt(row.first_seen_at),
                    "last_seen_at": self.format_dt(row.last_seen_at),
                    "is_active": is_active,
                }
            )

        latest_sample_dt = self.db.session.query(self.db.func.max(self.user_traffic_sample_model.created_at)).scalar()
        latest_stat_dt = self.db.session.query(self.db.func.max(self.user_traffic_stat_protocol_model.last_seen_at)).scalar()
        latest_dt_candidates = [dt for dt in (latest_sample_dt, latest_stat_dt) if dt is not None]
        latest_db_dt = max(latest_dt_candidates) if latest_dt_candidates else None
        db_age_seconds = None
        if latest_db_dt:
            try:
                db_age_seconds = max(int((now - latest_db_dt).total_seconds()), 0)
            except Exception:
                db_age_seconds = None

        summary = {
            "users_count": len(rows),
            "active_users_count": sum(1 for item in rows if item.get("is_active")),
            "offline_users_count": sum(1 for item in rows if not item.get("is_active")),
            "total_received": total_received,
            "total_sent": total_sent,
            "total_received_human": self.human_bytes(total_received),
            "total_sent_human": self.human_bytes(total_sent),
            "total_traffic_human": self.human_bytes(total_received + total_sent),
            "total_received_vpn": total_received_vpn,
            "total_sent_vpn": total_sent_vpn,
            "total_received_antizapret": total_received_antizapret,
            "total_sent_antizapret": total_sent_antizapret,
            "total_received_vpn_human": self.human_bytes(total_received_vpn),
            "total_sent_vpn_human": self.human_bytes(total_sent_vpn),
            "total_traffic_vpn_human": self.human_bytes(total_received_vpn + total_sent_vpn),
            "total_received_antizapret_human": self.human_bytes(total_received_antizapret),
            "total_sent_antizapret_human": self.human_bytes(total_sent_antizapret),
            "total_traffic_antizapret_human": self.human_bytes(total_received_antizapret + total_sent_antizapret),
            "latest_sample_at": self.format_dt(latest_sample_dt),
            "latest_stat_seen_at": self.format_dt(latest_stat_dt),
            "db_age_seconds": db_age_seconds,
            "db_age_human": "-" if db_age_seconds is None else self.human_seconds(db_age_seconds),
            "db_is_stale": False if db_age_seconds is None else (db_age_seconds > self.traffic_db_stale_seconds),
        }
        return rows, summary

    def _resolve_traffic_common_names_for_identity(self, common_name):
        target_name = (common_name or "").strip()
        target_identity = self.normalize_traffic_client_identity(target_name)
        if not target_identity:
            return set()

        names_to_delete = set()
        if target_name:
            names_to_delete.add(target_name)

        name_sources = [
            self.user_traffic_sample_model.common_name,
            self.traffic_session_state_model.common_name,
            self.user_traffic_stat_model.common_name,
            self.user_traffic_stat_protocol_model.common_name,
            self.openvpn_peer_info_cache_model.client_name,
            self.openvpn_peer_info_history_model.client_name,
        ]
        if self.wireguard_peer_cache_model is not None:
            name_sources.append(self.wireguard_peer_cache_model.client_name)

        for column in name_sources:
            for (stored_name,) in self.db.session.query(column).distinct().all():
                candidate = (stored_name or "").strip()
                if not candidate:
                    continue
                if self.normalize_traffic_client_identity(candidate) == target_identity:
                    names_to_delete.add(candidate)

        return names_to_delete

    def delete_client_traffic_stats(self, common_name):
        """Удаляет накопленную статистику трафика для одного клиента (VPN + Antizapret, все протоколы)."""
        target_name = (common_name or "").strip()
        if not target_name:
            return False, "Не указано имя клиента."

        names_to_delete = self._resolve_traffic_common_names_for_identity(target_name)
        if not names_to_delete:
            return False, f"Для клиента '{target_name}' статистика не найдена."

        normalized_names = sorted({name.lower() for name in names_to_delete if name})

        def _name_in_target_set(column):
            return self.db.func.lower(self.db.func.trim(column)).in_(normalized_names)

        try:
            deleted_samples = self.user_traffic_sample_model.query.filter(
                _name_in_target_set(self.user_traffic_sample_model.common_name)
            ).delete(synchronize_session=False)
            deleted_sessions = self.traffic_session_state_model.query.filter(
                _name_in_target_set(self.traffic_session_state_model.common_name)
            ).delete(synchronize_session=False)
            deleted_stats = self.user_traffic_stat_model.query.filter(
                _name_in_target_set(self.user_traffic_stat_model.common_name)
            ).delete(synchronize_session=False)
            deleted_protocol_stats = self.user_traffic_stat_protocol_model.query.filter(
                _name_in_target_set(self.user_traffic_stat_protocol_model.common_name)
            ).delete(synchronize_session=False)
            deleted_peer_cache = self.openvpn_peer_info_cache_model.query.filter(
                _name_in_target_set(self.openvpn_peer_info_cache_model.client_name)
            ).delete(synchronize_session=False)
            deleted_peer_history = self.openvpn_peer_info_history_model.query.filter(
                _name_in_target_set(self.openvpn_peer_info_history_model.client_name)
            ).delete(synchronize_session=False)
            deleted_wg_peer_cache = 0
            if self.wireguard_peer_cache_model is not None:
                deleted_wg_peer_cache = self.wireguard_peer_cache_model.query.filter(
                    _name_in_target_set(self.wireguard_peer_cache_model.client_name)
                ).delete(synchronize_session=False)

            self.db.session.commit()

            deleted_total = (
                int(deleted_samples or 0)
                + int(deleted_sessions or 0)
                + int(deleted_stats or 0)
                + int(deleted_protocol_stats or 0)
            )
            if (
                deleted_total == 0
                and int(deleted_peer_cache or 0) == 0
                and int(deleted_peer_history or 0) == 0
                and int(deleted_wg_peer_cache or 0) == 0
            ):
                return False, f"Для клиента '{target_name}' статистика не найдена."

            aliases_note = ""
            alias_names = sorted(names_to_delete - {target_name}, key=str.lower)
            if alias_names:
                aliases_note = f" Также удалены связанные записи: {', '.join(alias_names)}."

            return True, (
                f"Статистика клиента '{target_name}' удалена (VPN и Antizapret, все протоколы)"
                f"{aliases_note} "
                f"(stat={int(deleted_stats or 0)}, stat_protocol={int(deleted_protocol_stats or 0)}, "
                f"sessions={int(deleted_sessions or 0)}, samples={int(deleted_samples or 0)})."
            )
        except Exception as exc:
            self.db.session.rollback()
            return False, f"Ошибка удаления статистики клиента '{target_name}': {exc}"
