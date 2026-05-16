"""Event log collection and peer-info cache merge for logs dashboard."""

from collections import defaultdict


def collect_event_rows(*, _parse_event_log, EVENT_LOG_FILES):
    return [
        _parse_event_log(profile_key, filename)
        for profile_key, filename in EVENT_LOG_FILES.items()
    ]


def build_peer_info_context(
    *,
    app,
    db,
    event_rows,
    _persist_peer_info_cache,
    _load_peer_info_history_map,
    _load_peer_info_cache_map,
):
    try:
        _persist_peer_info_cache(event_rows)
    except Exception as e:
        db.session.rollback()
        app.logger.warning("Не удалось сохранить peer info cache/history: %s", e)

    peer_info_cache = _load_peer_info_history_map()
    peer_info_cache_stale = _load_peer_info_history_map(include_stale=True)
    legacy_peer_info_cache = _load_peer_info_cache_map()
    legacy_peer_info_cache_stale = _load_peer_info_cache_map(include_stale=True)

    for key, cached in legacy_peer_info_cache.items():
        existing = peer_info_cache.get(key)
        if existing is None or int(cached.get("rank", -1)) > int(existing.get("rank", -1)):
            peer_info_cache[key] = cached

    for key, cached in legacy_peer_info_cache_stale.items():
        existing = peer_info_cache_stale.get(key)
        if existing is None or int(cached.get("rank", -1)) > int(existing.get("rank", -1)):
            peer_info_cache_stale[key] = cached

    peer_info_cache_by_client_ip = {}
    peer_info_cache_by_client = defaultdict(list)
    for (_profile_key, client_name, ip), cached in peer_info_cache.items():
        if not client_name or not ip:
            continue
        key = (client_name, ip)
        prev = peer_info_cache_by_client_ip.get(key)
        if prev is None or int(cached.get("rank", -1)) > int(prev.get("rank", -1)):
            peer_info_cache_by_client_ip[key] = cached
        peer_info_cache_by_client[client_name].append(cached)

    peer_info_cache_stale_by_client_ip = {}
    peer_info_cache_stale_by_client = defaultdict(list)
    for (_profile_key, client_name, ip), cached in peer_info_cache_stale.items():
        if not client_name or not ip:
            continue
        key = (client_name, ip)
        prev = peer_info_cache_stale_by_client_ip.get(key)
        if prev is None or int(cached.get("rank", -1)) > int(prev.get("rank", -1)):
            peer_info_cache_stale_by_client_ip[key] = cached
        peer_info_cache_stale_by_client[client_name].append(cached)

    return {
        "peer_info_cache": peer_info_cache,
        "peer_info_cache_stale": peer_info_cache_stale,
        "peer_info_cache_by_client_ip": peer_info_cache_by_client_ip,
        "peer_info_cache_by_client": peer_info_cache_by_client,
        "peer_info_cache_stale_by_client_ip": peer_info_cache_stale_by_client_ip,
        "peer_info_cache_stale_by_client": peer_info_cache_stale_by_client,
    }

def enrich_client_aggregate_from_events(client_aggregate, event_rows, peer_ctx):
    peer_info_cache = peer_ctx["peer_info_cache"]
    peer_info_cache_stale = peer_ctx["peer_info_cache_stale"]
    peer_info_cache_by_client_ip = peer_ctx["peer_info_cache_by_client_ip"]
    peer_info_cache_by_client = peer_ctx["peer_info_cache_by_client"]
    peer_info_cache_stale_by_client_ip = peer_ctx["peer_info_cache_stale_by_client_ip"]
    peer_info_cache_stale_by_client = peer_ctx["peer_info_cache_stale_by_client"]

    # Дополняем версии/платформы и IP из event-логов
    for event in event_rows:
        for sess in event.get("client_sessions", []):
                client_name = sess.get("client")
                if not client_name or client_name == "-":
                    continue

                # Подключенные клиенты формируются только из *-status.log.
                # Event-логи лишь дополняют метаданные уже активных клиентов.
                if client_name not in client_aggregate:
                    continue

                sess_ip = sess.get("ip")
                if not sess_ip:
                    continue

                # Привязываем версию/платформу только к активным IP из status-логов.
                if sess_ip not in client_aggregate[client_name]["ips"]:
                    continue

                if sess_ip not in client_aggregate[client_name]["ip_details"]:
                    client_aggregate[client_name]["ip_details"][sess_ip] = {
                            "version": None,
                            "platform": None,
                            "rank": -1,
                        }

                # Для активного IP берём только наиболее актуальные данные из event-логов.
                event_rank = int(event.get("updated_at_ts", 0)) * 1000000 + int(sess.get("last_order", -1))
                current_rank = int(client_aggregate[client_name]["ip_details"][sess_ip].get("rank", -1))
                if event_rank >= current_rank:
                    client_aggregate[client_name]["ip_details"][sess_ip]["version"] = sess.get("version")
                    client_aggregate[client_name]["ip_details"][sess_ip]["platform"] = sess.get("platform")
                    client_aggregate[client_name]["ip_details"][sess_ip]["rank"] = event_rank

    # Для клиентов без свежего события подставляем последнее известное значение из БД.
    for client_name, stats in client_aggregate.items():
        for ip in sorted(stats.get("ips", set())):
                profile_candidates = sorted(stats.get("ip_profiles", {}).get(ip, set()))
                best_cached = None
                for profile_key in profile_candidates:
                    cached = peer_info_cache.get((profile_key, client_name, ip))
                    if not cached:
                        continue
                    if best_cached is None or int(cached.get("rank", -1)) > int(best_cached.get("rank", -1)):
                        best_cached = cached

                # Если по текущему профилю не нашли, берём наиболее свежий кэш по client+ip.
                if not best_cached:
                    best_cached = peer_info_cache_by_client_ip.get((client_name, ip))

                # Если IP сменился, но у клиента метаданные консистентны, берём их по имени.
                if not best_cached:
                    cached_candidates = peer_info_cache_by_client.get(client_name, [])
                    if cached_candidates:
                        unique_meta = {
                            ((item.get("version") or "").strip() or None, (item.get("platform") or "").strip() or None)
                            for item in cached_candidates
                            if (item.get("version") or item.get("platform"))
                        }
                        if len(unique_meta) == 1:
                            best_cached = max(
                                cached_candidates,
                                key=lambda item: int(item.get("rank", -1)),
                            )

                # Последний fallback: используем устаревший кэш, если свежих данных нет.
                if not best_cached:
                    for profile_key in profile_candidates:
                        cached = peer_info_cache_stale.get((profile_key, client_name, ip))
                        if not cached:
                            continue
                        if best_cached is None or int(cached.get("rank", -1)) > int(best_cached.get("rank", -1)):
                            best_cached = cached

                if not best_cached:
                    best_cached = peer_info_cache_stale_by_client_ip.get((client_name, ip))

                if not best_cached:
                    cached_candidates = peer_info_cache_stale_by_client.get(client_name, [])
                    if cached_candidates:
                        unique_meta = {
                            ((item.get("version") or "").strip() or None, (item.get("platform") or "").strip() or None)
                            for item in cached_candidates
                            if (item.get("version") or item.get("platform"))
                        }
                        if len(unique_meta) == 1:
                            best_cached = max(
                                cached_candidates,
                                key=lambda item: int(item.get("rank", -1)),
                            )

                if not best_cached:
                    continue
                details = stats["ip_details"].setdefault(
                    ip,
                    {"version": None, "platform": None, "rank": -1},
                )
                if not details.get("version") and best_cached.get("version"):
                    details["version"] = best_cached.get("version")
                if not details.get("platform") and best_cached.get("platform"):
                    details["platform"] = best_cached.get("platform")
