from datetime import datetime, timedelta


class PeerInfoCacheService:
    def __init__(
        self,
        *,
        db,
        openvpn_peer_info_cache_model,
        openvpn_peer_info_history_model,
        openvpn_peer_info_cache_ttl_seconds,
        openvpn_peer_info_history_retention_seconds,
    ):
        self.db = db
        self.openvpn_peer_info_cache_model = openvpn_peer_info_cache_model
        self.openvpn_peer_info_history_model = openvpn_peer_info_history_model
        self.openvpn_peer_info_cache_ttl_seconds = int(openvpn_peer_info_cache_ttl_seconds or 0)
        self.openvpn_peer_info_history_retention_seconds = int(openvpn_peer_info_history_retention_seconds or 0)

    def persist_peer_info_cache(self, event_rows):
        """Сохраняет версию/платформу клиентов в БД, чтобы UI мог брать данные из кэша."""
        best_rows = {}
        now = datetime.utcnow()

        for event in event_rows:
            profile = event.get("profile") or ""

            for sess in event.get("client_sessions", []):
                client_name = (sess.get("client") or "").strip()
                ip = (sess.get("ip") or "").strip()
                if not client_name or client_name == "-" or not ip:
                    continue

                version = (sess.get("version") or "").strip() or None
                platform = (sess.get("platform") or "").strip() or None
                if not version and not platform:
                    continue

                event_ts = int(sess.get("event_ts") or 0)
                if event_ts <= 0:
                    event_ts = int(event.get("updated_at_ts", 0))

                endpoint = (sess.get("endpoint") or "").strip() or None
                rank = int(event_ts) * 1000000 + int(sess.get("last_order", -1))
                key = (profile, client_name, ip)
                prev = best_rows.get(key)
                if prev is None or rank >= int(prev.get("rank", -1)):
                    best_rows[key] = {
                        "rank": rank,
                        "version": version,
                        "platform": platform,
                        "endpoint": endpoint,
                    }

        if not best_rows:
            deleted_history = self.prune_peer_info_history()
            if deleted_history > 0:
                self.db.session.commit()
            return

        cache_changed = False
        history_changed = False
        for (profile, client_name, ip), data in best_rows.items():
            row = self.openvpn_peer_info_cache_model.query.filter_by(
                profile=profile,
                client_name=client_name,
                ip=ip,
            ).first()

            if row is None:
                self.db.session.add(
                    self.openvpn_peer_info_cache_model(
                        profile=profile,
                        client_name=client_name,
                        ip=ip,
                        endpoint=data.get("endpoint"),
                        version=data.get("version"),
                        platform=data.get("platform"),
                        last_event_rank=int(data.get("rank", 0)),
                        last_seen_at=now,
                    )
                )
                cache_changed = True
            else:
                incoming_rank = int(data.get("rank", 0))
                current_rank = int(row.last_event_rank or 0)
                if incoming_rank >= current_rank:
                    row.last_event_rank = incoming_rank
                    row.last_seen_at = now
                    if data.get("endpoint"):
                        row.endpoint = data.get("endpoint")
                    if data.get("version"):
                        row.version = data.get("version")
                    if data.get("platform"):
                        row.platform = data.get("platform")
                    cache_changed = True

            incoming_rank = int(data.get("rank", 0))
            existing_history = self.openvpn_peer_info_history_model.query.filter_by(
                profile=profile,
                client_name=client_name,
                ip=ip,
                event_rank=incoming_rank,
            ).first()
            if existing_history is None:
                self.db.session.add(
                    self.openvpn_peer_info_history_model(
                        profile=profile,
                        client_name=client_name,
                        ip=ip,
                        endpoint=data.get("endpoint"),
                        version=data.get("version"),
                        platform=data.get("platform"),
                        event_rank=incoming_rank,
                        observed_at=now,
                    )
                )
                history_changed = True

        deleted_history = self.prune_peer_info_history()
        if cache_changed or history_changed or deleted_history > 0:
            self.db.session.commit()

    def prune_peer_info_history(self):
        if self.openvpn_peer_info_history_retention_seconds <= 0:
            return 0

        cutoff = datetime.utcnow() - timedelta(seconds=self.openvpn_peer_info_history_retention_seconds)
        deleted = self.openvpn_peer_info_history_model.query.filter(
            self.openvpn_peer_info_history_model.observed_at < cutoff
        ).delete(synchronize_session=False)
        return int(deleted or 0)

    def load_peer_info_cache_map(self, include_stale=False):
        """Возвращает map (profile, client_name, ip) -> последняя версия/платформа из БД."""
        query = self.openvpn_peer_info_cache_model.query
        if self.openvpn_peer_info_cache_ttl_seconds > 0 and not include_stale:
            cutoff = datetime.utcnow() - timedelta(seconds=self.openvpn_peer_info_cache_ttl_seconds)
            query = query.filter(self.openvpn_peer_info_cache_model.last_seen_at >= cutoff)

        rows = query.order_by(self.openvpn_peer_info_cache_model.last_event_rank.desc()).all()
        out = {}
        for row in rows:
            key = ((row.profile or "").strip(), (row.client_name or "").strip(), (row.ip or "").strip())
            if not key[0] or not key[1] or not key[2] or key in out:
                continue
            out[key] = {
                "version": (row.version or "").strip() or None,
                "platform": (row.platform or "").strip() or None,
                "rank": int(row.last_event_rank or 0),
            }
        return out

    def load_peer_info_history_map(self, include_stale=False):
        """Возвращает map (profile, client_name, ip) -> последнее значение из истории peer info."""
        query = self.openvpn_peer_info_history_model.query
        if self.openvpn_peer_info_history_retention_seconds > 0 and not include_stale:
            cutoff = datetime.utcnow() - timedelta(seconds=self.openvpn_peer_info_history_retention_seconds)
            query = query.filter(self.openvpn_peer_info_history_model.observed_at >= cutoff)

        rows = query.order_by(
            self.openvpn_peer_info_history_model.event_rank.desc(),
            self.openvpn_peer_info_history_model.observed_at.desc(),
        ).all()
        out = {}
        for row in rows:
            key = ((row.profile or "").strip(), (row.client_name or "").strip(), (row.ip or "").strip())
            if not key[0] or not key[1] or not key[2] or key in out:
                continue
            out[key] = {
                "version": (row.version or "").strip() or None,
                "platform": (row.platform or "").strip() or None,
                "rank": int(row.event_rank or 0),
            }
        return out

    def human_device_type(self, platform_value):
        if not platform_value:
            return "Не определено"

        key = str(platform_value).strip().lower()
        mapping = {
            "win": "Windows",
            "windows": "Windows",
            "ios": "iOS (iPhone/iPad)",
            "android": "Android",
            "mac": "macOS",
            "macos": "macOS",
            "darwin": "macOS",
            "linux": "Linux",
        }
        return mapping.get(key, platform_value)
