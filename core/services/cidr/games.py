"""Game filter catalog sync for dedicated AZ-Game include files."""
import ipaddress
import json
import logging
import os
import re
import socket
import time
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.antizapret_params import IP_FILES
from core.services.cidr.constants import (
    GAME_FILTER_EXCLUDE_BLOCK_END,
    GAME_FILTER_EXCLUDE_BLOCK_START,
    GAME_FILTER_EXCLUDE_IP_BLOCK_END,
    GAME_FILTER_EXCLUDE_IP_BLOCK_START,
    GAME_FILTER_BLOCK_END,
    GAME_FILTER_BLOCK_START,
    GAME_FILTER_IP_BLOCK_END,
    GAME_FILTER_IP_BLOCK_START,
    SOURCE_FORMATS_WITH_GEO,
)
from core.services.cidr.facade_compat import call as _facade_call, get_attr as _cfg
from core.services.cidr.parsers import _normalize_cidrs
from core.services.cidr.provider_sources import (
    GAME_FILTER_ALIASES,
    GAME_FILTER_BY_KEY,
    GAME_FILTER_CATALOG,
)

logger = logging.getLogger(__name__)

GAME_ASN_CACHE_TTL_SECONDS = 3600
GAME_ASN_FETCH_TIMEOUT_SECONDS = 10
EXCLUDE_PUNCH_MIN_INCLUDE_PREFIX = 16
EXCLUDE_PUNCH_MAX_RESULT_CIDRS = 64
AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT_ENV = "AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT"
AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK_ENV = "AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK"
EXCLUDE_PUNCH_MAX_OVERLAP_ENTRIES = 32
EXCLUDE_PUNCH_PREVIEW_PATCHES_LIMIT = 30
EXCLUDE_PUNCH_MAX_SKIP_REASONS = 5
EXCLUDE_PUNCH_SKIP_SUMMARY_LIMIT = 200
_GAME_ASN_CIDRS_CACHE = {}
_OVERLAP_INDEX_CACHE = {"signature": None, "entries": None, "starts": None}


def _derive_game_provider(item):
    if isinstance(item, dict):
        provider = str(item.get("provider") or "").strip()
        if provider:
            return provider
        subtitle = str(item.get("subtitle") or "").strip()
    else:
        subtitle = ""
    if not subtitle:
        return "Unknown"
    return subtitle.split("—")[0].strip() or subtitle


def _derive_game_network(item):
    if isinstance(item, dict):
        explicit = str(item.get("network") or "").strip()
        if explicit:
            return explicit
        subtitle = str(item.get("subtitle") or "").strip()
    else:
        subtitle = ""
    if "—" not in subtitle:
        return ""
    network = subtitle.split("—", 1)[1].strip()
    if network.upper() == "DNS":
        return ""
    return network


def _derive_game_source_type(item):
    server_ip_count = len((item or {}).get("server_ips") or [])
    asn_count = len((item or {}).get("asns") or [])
    if server_ip_count > 0:
        return "servers"
    if asn_count > 0:
        return "asn"
    return "dns"


def _derive_game_tags(item):
    tags = []
    tags.append(_derive_game_source_type(item))
    provider = _derive_game_provider(item).strip().lower().replace(" ", "_")
    if provider:
        tags.append(f"provider:{provider}")
    return tags


def _normalize_server_ips_to_cidrs(server_ips):
    raw_values = []
    for value in server_ips or []:
        token = str(value or "").strip()
        if not token:
            continue
        if "/" not in token:
            token = f"{token}/32"
        raw_values.append(token)
    return set(_normalize_cidrs(raw_values))


def get_available_regions():
    regions = []
    for file_name, meta in IP_FILES.items():
        sources = _cfg("PROVIDER_SOURCES").get(file_name) or []
        supports_geo_filter = any((src.get("format") in SOURCE_FORMATS_WITH_GEO) for src in sources)
        regions.append(
            {
                "file": file_name,
                "region": meta.get("name") or file_name,
                "description": meta.get("description") or "",
                "can_update": file_name in _cfg("PROVIDER_SOURCES"),
                "supports_geo_filter": supports_geo_filter,
            }
        )
    return regions


def get_available_game_filters():
    return [
        {
            "key": item["key"],
            "title": item["title"],
            "subtitle": item.get("subtitle", ""),
            "domain_count": len(item.get("domains") or []),
            "asn_count": len(item.get("asns") or []),
            "server_ip_count": len(item.get("server_ips") or []),
            "source_type": _derive_game_source_type(item),
            "provider": _derive_game_provider(item),
            "network": _derive_game_network(item),
            "tags": _derive_game_tags(item),
        }
        for item in GAME_FILTER_CATALOG
    ]


def _normalize_game_filter_keys(raw_keys, with_invalid=False):
    if raw_keys is None:
        return ([], []) if with_invalid else []

    values = raw_keys
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]

    selected = set()
    invalid = []
    for value in values:
        token = str(value or "").strip().lower()
        if not token:
            continue
        token = GAME_FILTER_ALIASES.get(token, token)
        if token in GAME_FILTER_BY_KEY:
            selected.add(token)
        else:
            invalid.append(token)

    normalized = [item["key"] for item in GAME_FILTER_CATALOG if item["key"] in selected]
    return (normalized, sorted(set(invalid))) if with_invalid else normalized


def validate_game_filter_keys(raw_keys):
    normalized_keys, invalid_keys = _normalize_game_filter_keys(raw_keys, with_invalid=True)
    return {
        "normalized_keys": normalized_keys,
        "invalid_keys": invalid_keys,
        "valid_count": len(normalized_keys),
    }


def _provider_key(name):
    slug = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
    return slug or "unknown"


def _build_provider_filter_catalog():
    grouped = {}
    for item in GAME_FILTER_CATALOG:
        provider_title = _derive_game_provider(item)
        provider_key = _provider_key(provider_title)
        entry = grouped.setdefault(
            provider_key,
            {
                "key": provider_key,
                "title": provider_title,
                "game_keys": [],
                "game_titles": [],
                "domain_count": 0,
                "asn_count": 0,
                "server_ip_count": 0,
                "networks": set(),
                "source_types": set(),
            },
        )
        game_key = item["key"]
        if game_key not in entry["game_keys"]:
            entry["game_keys"].append(game_key)
            entry["game_titles"].append(item["title"])
        entry["domain_count"] += len(item.get("domains") or [])
        entry["asn_count"] += len(item.get("asns") or [])
        entry["server_ip_count"] += len(item.get("server_ips") or [])
        network = _derive_game_network(item)
        if network:
            entry["networks"].add(network)
        entry["source_types"].add(_derive_game_source_type(item))

    catalog = []
    for provider_key in sorted(grouped.keys(), key=lambda value: grouped[value]["title"].lower()):
        entry = grouped[provider_key]
        networks = sorted(entry["networks"])
        if len(networks) == 1:
            network_label = networks[0]
        elif networks:
            network_label = f"{len(networks)} сетей"
        else:
            network_label = ""
        source_types = sorted(entry["source_types"])
        if len(source_types) == 1:
            source_type = source_types[0]
        else:
            source_type = "mixed"
        catalog.append(
            {
                "key": provider_key,
                "title": entry["title"],
                "game_keys": list(entry["game_keys"]),
                "game_titles": list(entry["game_titles"]),
                "game_count": len(entry["game_keys"]),
                "domain_count": entry["domain_count"],
                "asn_count": entry["asn_count"],
                "server_ip_count": entry["server_ip_count"],
                "source_type": source_type,
                "network": network_label,
                "tags": [source_type, f"provider:{provider_key}"],
            }
        )
    return catalog


PROVIDER_FILTER_CATALOG = _build_provider_filter_catalog()
PROVIDER_FILTER_BY_KEY = {item["key"]: item for item in PROVIDER_FILTER_CATALOG}
GAME_KEY_TO_PROVIDER_KEY = {
    game_key: provider["key"]
    for provider in PROVIDER_FILTER_CATALOG
    for game_key in provider["game_keys"]
}


def get_available_provider_filters():
    return [dict(item) for item in PROVIDER_FILTER_CATALOG]


def _token_to_provider_key(token):
    token = str(token or "").strip().lower()
    if not token:
        return None
    token = GAME_FILTER_ALIASES.get(token, token)
    if token in PROVIDER_FILTER_BY_KEY:
        return token
    if token in GAME_FILTER_BY_KEY:
        return GAME_KEY_TO_PROVIDER_KEY.get(token)
    return None


def _normalize_provider_filter_keys(raw_keys, with_invalid=False):
    if raw_keys is None:
        return ([], []) if with_invalid else []

    values = raw_keys
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]

    selected = set()
    invalid = []
    for value in values:
        provider_key = _token_to_provider_key(value)
        if provider_key:
            selected.add(provider_key)
        else:
            invalid.append(str(value or "").strip().lower())

    normalized = [item["key"] for item in PROVIDER_FILTER_CATALOG if item["key"] in selected]
    return (normalized, sorted(set(invalid))) if with_invalid else normalized


def validate_provider_filter_keys(raw_keys):
    normalized_keys, invalid_keys = _normalize_provider_filter_keys(raw_keys, with_invalid=True)
    return {
        "normalized_keys": normalized_keys,
        "invalid_keys": invalid_keys,
        "valid_count": len(normalized_keys),
    }


def _expand_provider_keys_to_game_keys(provider_keys):
    game_keys = []
    seen = set()
    for provider_key in _normalize_provider_filter_keys(provider_keys):
        provider = PROVIDER_FILTER_BY_KEY.get(provider_key) or {}
        for game_key in provider.get("game_keys") or []:
            if game_key in seen:
                continue
            seen.add(game_key)
            game_keys.append(game_key)
    return game_keys


def _providers_from_game_keys(game_keys):
    provider_keys = []
    seen = set()
    for game_key in _normalize_game_filter_keys(game_keys):
        provider_key = GAME_KEY_TO_PROVIDER_KEY.get(game_key)
        if not provider_key or provider_key in seen:
            continue
        seen.add(provider_key)
        provider_keys.append(provider_key)
    return [item["key"] for item in PROVIDER_FILTER_CATALOG if item["key"] in seen]


def _resolve_provider_keys_from_payload(include_provider_keys=None, include_game_keys=None):
    normalized = _normalize_provider_filter_keys(include_provider_keys)
    if normalized:
        return normalized
    if include_game_keys:
        return _normalize_provider_filter_keys(include_game_keys)
    return []


def _resolve_provider_filter_selection(
    include_provider_keys=None,
    include_game_keys=None,
    include_game_hosts=False,
):
    normalized_keys = _resolve_provider_keys_from_payload(
        include_provider_keys=include_provider_keys,
        include_game_keys=include_game_keys,
    )
    if normalized_keys:
        return normalized_keys
    if include_game_hosts:
        return [item["key"] for item in PROVIDER_FILTER_CATALOG]
    return []


def _resolve_game_filter_selection(include_game_keys=None, include_game_hosts=False):
    return _expand_provider_keys_to_game_keys(
        _resolve_provider_filter_selection(
            include_game_keys=include_game_keys,
            include_game_hosts=bool(include_game_hosts),
        )
    )


def _collect_provider_domains(selected_provider_keys):
    domains = []
    seen = set()
    titles = []
    for provider_key in _normalize_provider_filter_keys(selected_provider_keys):
        provider = PROVIDER_FILTER_BY_KEY.get(provider_key)
        if not provider:
            continue
        titles.append(provider["title"])
        for game_key in provider.get("game_keys") or []:
            item = GAME_FILTER_BY_KEY.get(game_key) or {}
            for domain in item.get("domains") or []:
                value = str(domain or "").strip().lower()
                if not value or value in seen:
                    continue
                seen.add(value)
                domains.append(value)
    return titles, domains


def _collect_provider_union_cidrs(provider_key, asn_prefixes_map=None, shared_asn_cache=None):
    provider = PROVIDER_FILTER_BY_KEY.get(provider_key) or {}
    all_cidrs = set()
    unresolved_domains = []
    game_server_ip_total = 0
    dns_fallback_domains = []
    dns_fallback_used = False
    for game_key in provider.get("game_keys") or []:
        item = GAME_FILTER_BY_KEY.get(game_key)
        if not item:
            continue
        key_cidrs, key_had_game_data, key_unresolved = _collect_item_cidrs(
            item,
            asn_prefixes_map=asn_prefixes_map,
            shared_asn_cache=shared_asn_cache,
        )
        server_ips = item.get("server_ips") or []
        if server_ips:
            game_server_ip_total += len(_normalize_server_ips_to_cidrs(server_ips))
        domains = item.get("domains") or []
        if not key_had_game_data and domains:
            dns_fallback_used = True
            dns_fallback_domains.extend(domains)
        unresolved_domains.extend(key_unresolved)
        all_cidrs.update(key_cidrs)
    return (
        _normalize_cidrs(sorted(all_cidrs)),
        sorted(set(unresolved_domains)),
        {
            "game_server_ip_total": game_server_ip_total,
            "dns_fallback_used": dns_fallback_used,
            "dns_fallback_domains": dns_fallback_domains,
        },
    )


def _collect_game_domains(selected_game_keys):
    domains = []
    seen = set()
    titles = []
    for key in _normalize_game_filter_keys(selected_game_keys):
        item = GAME_FILTER_BY_KEY.get(key)
        if not item:
            continue
        titles.append(item["title"])
        for domain in item.get("domains") or []:
            value = str(domain or "").strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            domains.append(value)
    return titles, domains


def _resolve_game_domains_ipv4_cidrs(domains):
    cidr_values = []
    unresolved = []
    for domain in domains:
        raw_domain = str(domain or "").strip().lower()
        if not raw_domain:
            continue
        ipv4_addresses = set()
        try:
            for info in socket.getaddrinfo(raw_domain, None, socket.AF_INET):
                sockaddr = info[4] if len(info) > 4 else None
                address = sockaddr[0] if isinstance(sockaddr, tuple) and sockaddr else ""
                if address:
                    ipv4_addresses.add(address)
        except (socket.gaierror, OSError):
            unresolved.append(raw_domain)
            continue
        if not ipv4_addresses:
            unresolved.append(raw_domain)
            continue
        for address in sorted(ipv4_addresses):
            cidr_values.append(f"{address}/32")
    return _normalize_cidrs(cidr_values), sorted(set(unresolved))


def _fetch_single_asn_cidrs(asn_int, shared_cache=None):
    now = time.time()
    cached = _GAME_ASN_CIDRS_CACHE.get(asn_int)
    if cached and (now - cached.get("ts", 0)) < GAME_ASN_CACHE_TTL_SECONDS:
        if shared_cache is not None:
            shared_cache[asn_int] = cached
        return list(cached.get("cidrs") or []), str(cached.get("label") or ""), None

    url = f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn_int}"
    try:
        text = _facade_call("_download_text", url, timeout=GAME_ASN_FETCH_TIMEOUT_SECONDS)
        data = json.loads(text)
        prefixes = data.get("data", {}).get("prefixes") or []
        ipv4 = [
            str(p.get("prefix") or "").strip()
            for p in prefixes
            if ":" not in str(p.get("prefix") or "")
        ]
        ipv4 = [p for p in ipv4 if p]
        normalized = _normalize_cidrs(sorted(set(ipv4)))
        label = f"ripe-AS{asn_int}({len(normalized)})" if normalized else ""
        entry = {"ts": now, "cidrs": normalized, "label": label}
        _GAME_ASN_CIDRS_CACHE[asn_int] = entry
        if shared_cache is not None:
            shared_cache[asn_int] = entry
        return normalized, label, None
    except Exception as exc:  # noqa: BLE001
        return [], "", f"AS{asn_int}: {exc}"


def _resolve_asn_prefixes_map(asns, shared_cache=None, max_workers=6):
    unique_asns = sorted({int(asn) for asn in (asns or []) if asn is not None})
    if not unique_asns:
        return {}, [], []

    cache = _GAME_ASN_CIDRS_CACHE
    prefixes_map = {}
    labels = []
    errors = []
    pending = []
    now = time.time()

    for asn_int in unique_asns:
        cached = cache.get(asn_int)
        if cached and (now - cached.get("ts", 0)) < GAME_ASN_CACHE_TTL_SECONDS:
            cidrs = list(cached.get("cidrs") or [])
            label = str(cached.get("label") or "")
            if cidrs:
                prefixes_map[asn_int] = cidrs
            if label:
                labels.append(label)
            continue
        pending.append(asn_int)

    if pending:
        worker_count = max(1, min(max_workers, len(pending)))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {
                pool.submit(_fetch_single_asn_cidrs, asn_int, shared_cache): asn_int
                for asn_int in pending
            }
            for future in as_completed(futures):
                asn_int = futures[future]
                try:
                    cidrs, label, error = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"AS{asn_int}: {exc}")
                    continue
                if cidrs:
                    prefixes_map[asn_int] = cidrs
                if label:
                    labels.append(label)
                if error:
                    errors.append(error)

    return prefixes_map, sorted(set(labels)), errors


def _fetch_game_asn_cidrs(asns, shared_cache=None):
    prefixes_map, labels, errors = _resolve_asn_prefixes_map(asns, shared_cache=shared_cache)
    all_cidrs = set()
    for cidrs in prefixes_map.values():
        all_cidrs.update(cidrs)
    return _normalize_cidrs(sorted(all_cidrs)), labels, errors


def _collect_item_cidrs(item, asn_prefixes_map=None, shared_asn_cache=None):
    if not item:
        return set(), False, []
    asns = item.get("asns") or []
    domains = item.get("domains") or []
    server_ips = item.get("server_ips") or []
    key_cidrs = set()
    key_had_game_data = False
    unresolved_domains = []

    if server_ips:
        server_cidrs = _normalize_server_ips_to_cidrs(server_ips)
        if server_cidrs:
            key_cidrs.update(server_cidrs)
            key_had_game_data = True

    if asns:
        if asn_prefixes_map is None:
            asn_prefixes_map, _, _ = _resolve_asn_prefixes_map(asns, shared_cache=shared_asn_cache)
        asn_cidrs = set()
        for asn in asns:
            asn_cidrs.update(asn_prefixes_map.get(int(asn)) or [])
        if asn_cidrs:
            key_cidrs.update(asn_cidrs)
            key_had_game_data = True

    if not key_had_game_data and domains:
        dns_cidrs, unresolved = _facade_call(
            "_resolve_game_domains_ipv4_cidrs",
            list(dict.fromkeys(domains)),
        )
        key_cidrs.update(dns_cidrs)
        unresolved_domains.extend(unresolved)

    return key_cidrs, key_had_game_data, unresolved_domains


def _strip_managed_block(content, block_start, block_end):
    text = str(content or "")
    pattern = re.compile(
        rf"\n?{re.escape(str(block_start))}\n.*?\n{re.escape(str(block_end))}\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text)


def _extract_managed_block(content, block_start, block_end):
    text = str(content or "")
    pattern = re.compile(
        rf"{re.escape(str(block_start))}\n(.*?)\n{re.escape(str(block_end))}",
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1) if match else ""


def _read_managed_block_cidrs(file_path, block_start, block_end):
    path = str(file_path or "").strip()
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return []
    block_text = _extract_managed_block(content, block_start, block_end)
    if not block_text:
        return []
    cidr_pattern = _cfg("CIDR_V4_SCAN_PATTERN")
    if not cidr_pattern:
        return []
    return _normalize_cidrs(cidr_pattern.findall(block_text))


def _preview_file_label(path):
    return os.path.basename(str(path or "").strip()) or str(path or "").strip() or "—"


def _diff_normalized_cidr_lists(current_cidrs, planned_cidrs):
    current = _normalize_cidrs(current_cidrs or [])
    planned = _normalize_cidrs(planned_cidrs or [])
    current_set = set(current)
    planned_set = set(planned)
    return {
        "added": [cidr for cidr in planned if cidr not in current_set],
        "removed": [cidr for cidr in current if cidr not in planned_set],
        "unchanged": [cidr for cidr in planned if cidr in current_set],
    }


def _append_change_log_lines(lines, title, body_lines, empty_text="(пусто)"):
    lines.append(f"=== {title} ===")
    if body_lines:
        lines.extend(body_lines)
    else:
        lines.append(empty_text)
    lines.append("")


def _punch_limitation_context():
    min_prefix = EXCLUDE_PUNCH_MIN_INCLUDE_PREFIX
    max_fragments = EXCLUDE_PUNCH_MAX_RESULT_CIDRS
    return {
        "min_include_prefix": min_prefix,
        "max_result_cidrs": max_fragments,
        "notes": [
            (
                f"Автоматический punch (вырезание exclude из include) разрешён только для "
                f"маршрутов /{min_prefix} и уже (не шире /16)."
            ),
            (
                "Маршруты шире /16 — типичные блоки CDN вроде Akamai "
                "(/10, /13, /15) — не разбиваются: вычитание маленького exclude из "
                "огромной суперсети порождает сотни тысяч фрагментов."
            ),
            (
                "Такое поведение ранее приводило к зависанию «Проверить перед применением» "
                "(HTTP 504, 100% CPU, несколько GB RAM) — ограничения добавлены как защита."
            ),
            (
                f"Дополнительный предохранитель: не более {max_fragments} CIDR на одну "
                "операцию split; иначе punch тоже пропускается (patch_too_many_fragments)."
            ),
            (
                "Exclude-маршруты игры всё равно будут записаны в AZ-Game-exclude-ips.txt; "
                "include-файл AP-*-include-ips.txt при пропуске не меняется."
            ),
            (
                "Если нужен DIRECT поверх широкого include, сузьте или уберите "
                "пересекающиеся строки в config/AP-*-include-ips.txt вручную."
            ),
        ],
    }


def _describe_include_punch_skip_reason(reason):
    reason = str(reason or "").strip()
    if reason == "include_route_too_broad":
        return (
            f"шире /{EXCLUDE_PUNCH_MIN_INCLUDE_PREFIX} "
            "(автоматический punch отключён)"
        )
    if reason == "patch_too_many_fragments":
        return (
            f"слишком много фрагментов при split include "
            f"(лимит {EXCLUDE_PUNCH_MAX_RESULT_CIDRS})"
        )
    if reason == "exclude_trim_too_many_fragments":
        return (
            f"слишком много фрагментов при обрезке exclude "
            f"(лимит {EXCLUDE_PUNCH_MAX_RESULT_CIDRS})"
        )
    return reason or "пропущено"


def _record_include_patch_skip_summary(summary_map, old_cidr, file_path, reason, exclude_cidr=""):
    file_path = str(file_path or "").strip()
    old_cidr = str(old_cidr or "").strip()
    reason = str(reason or "").strip() or "skipped"
    if not file_path or not old_cidr:
        return
    key = (file_path, old_cidr, reason)
    entry = summary_map.setdefault(
        key,
        {
            "file": file_path,
            "old_cidr": old_cidr,
            "reason": reason,
            "overlap_count": 0,
            "exclude_cidr_samples": [],
        },
    )
    entry["overlap_count"] = int(entry.get("overlap_count") or 0) + 1
    exclude_cidr = str(exclude_cidr or "").strip()
    samples = entry["exclude_cidr_samples"]
    if exclude_cidr and exclude_cidr not in samples and len(samples) < 3:
        samples.append(exclude_cidr)


def _finalize_include_patch_skip_summary(summary_map):
    items = sorted(
        summary_map.values(),
        key=lambda item: (_preview_file_label(item.get("file")), str(item.get("old_cidr") or "")),
    )
    for item in items[:EXCLUDE_PUNCH_SKIP_SUMMARY_LIMIT]:
        item["reason_label"] = _describe_include_punch_skip_reason(item.get("reason"))
        item["file_label"] = _preview_file_label(item.get("file"))
    return items[:EXCLUDE_PUNCH_SKIP_SUMMARY_LIMIT]


def _build_include_punch_warnings(skip_summary):
    skip_summary = list(skip_summary or [])
    if not skip_summary:
        return []

    ctx = _punch_limitation_context()
    broad_items = [item for item in skip_summary if item.get("reason") == "include_route_too_broad"]
    warnings = []
    if broad_items:
        warnings.append(
            "Внимание: include punch пропущен для "
            f"{len(broad_items)} широких маршрутов (шире /{ctx['min_include_prefix']}). "
            "Exclude игры будут добавлены, но AP-*-include-ips.txt не изменится — "
            "возможен конфликт VPN (include) и DIRECT (exclude)."
        )
        warnings.extend(ctx["notes"])
        return warnings

    warnings.append(
        f"Include punch частично пропущен ({len(skip_summary)} случаев). "
        "Подробности — в журнале изменений."
    )
    return warnings


def _enrich_overlap_summary_punch_warnings(overlap_summary, skip_summary_map):
    overlap_summary = dict(overlap_summary or _empty_overlap_summary())
    skip_summary = _finalize_include_patch_skip_summary(skip_summary_map)
    ctx = _punch_limitation_context()
    overlap_summary["include_patches_skip_summary"] = skip_summary
    overlap_summary["include_patches_skip_reasons"] = skip_summary
    overlap_summary["punch_limit_min_prefix"] = ctx["min_include_prefix"]
    overlap_summary["punch_limit_max_fragments"] = ctx["max_result_cidrs"]
    overlap_summary["punch_limitations"] = ctx["notes"]
    overlap_summary["punch_warnings"] = _build_include_punch_warnings(skip_summary)
    return overlap_summary


def _format_include_patch_skip_log_line(item):
    file_label = str(item.get("file_label") or _preview_file_label(item.get("file")) or "—")
    old_cidr = str(item.get("old_cidr") or "—")
    reason_label = str(
        item.get("reason_label") or _describe_include_punch_skip_reason(item.get("reason"))
    )
    overlap_count = int(item.get("overlap_count") or 0)
    count_suffix = f", пересечений с exclude: {overlap_count}" if overlap_count > 1 else ""
    samples = item.get("exclude_cidr_samples") or []
    sample_suffix = f" (пример exclude: {', '.join(samples)})" if samples else ""
    return f"{file_label}: {old_cidr} — punch пропущен ({reason_label}){count_suffix}{sample_suffix}"


def _build_preview_change_log(
    filter_kind,
    ips_file_path,
    block_start,
    block_end,
    planned_cidrs,
    overlap_summary,
    selected_game_keys=None,
):
    overlap_summary = overlap_summary or _empty_overlap_summary()
    planned = _normalize_cidrs(planned_cidrs or [])
    current = _read_managed_block_cidrs(ips_file_path, block_start, block_end)
    diff = _diff_normalized_cidr_lists(current, planned)
    trim_details = list(overlap_summary.get("trim_details") or [])
    include_patches = list(overlap_summary.get("include_patches") or [])
    include_skipped = list(
        overlap_summary.get("include_patches_skip_summary")
        or overlap_summary.get("include_patches_skip_reasons")
        or []
    )
    punch_limitations = list(overlap_summary.get("punch_limitations") or [])
    target_label = _preview_file_label(ips_file_path)
    is_exclude = filter_kind == "exclude"
    route_mode = "DIRECT (exclude)" if is_exclude else "VPN (include)"
    lines = []
    preview_limit = 200

    broad_skips = [item for item in include_skipped if item.get("reason") == "include_route_too_broad"]
    if is_exclude and broad_skips:
        warning_body = list(punch_limitations or _punch_limitation_context()["notes"])
        warning_body.append("")
        warning_body.append(f"Затронуто уникальных include-маршрутов: {len(broad_skips)}")
        for item in broad_skips[:preview_limit]:
            warning_body.append(_format_include_patch_skip_log_line(item))
        if len(broad_skips) > preview_limit:
            warning_body.append(f"... ещё {len(broad_skips) - preview_limit} маршрутов")
        _append_change_log_lines(
            lines,
            "ВНИМАНИЕ: punch не выполнен для широких include-маршрутов",
            warning_body,
        )
    elif is_exclude and include_skipped and punch_limitations:
        other_body = [_format_include_patch_skip_log_line(item) for item in include_skipped[:preview_limit]]
        if len(include_skipped) > preview_limit:
            other_body.append(f"... ещё {len(include_skipped) - preview_limit} случаев")
        other_body.extend(["", *punch_limitations])
        _append_change_log_lines(lines, "ВНИМАНИЕ: punch частично пропущен", other_body)

    current_body = [f"Файл: {target_label}", f"Маршрутов в управляемом блоке: {len(current)}"]
    if current:
        current_body.extend(current[:preview_limit])
        if len(current) > preview_limit:
            current_body.append(f"... ещё {len(current) - preview_limit}")
    _append_change_log_lines(lines, f"Сейчас — {target_label}", current_body, empty_text="Блок отсутствует или пуст")

    planned_body = [
        f"Будет записано маршрутов: {len(planned)}",
        f"Исходных из каталога игр: {int(overlap_summary.get('original_cidr_count') or len(planned))}",
    ]
    if diff["unchanged"]:
        planned_body.append(f"Без изменений (уже в блоке): {len(diff['unchanged'])}")
    if diff["added"]:
        planned_body.append(f"Новых к добавлению: {len(diff['added'])}")
    if diff["removed"]:
        planned_body.append(f"Будет убрано из блока: {len(diff['removed'])}")
    _append_change_log_lines(
        lines,
        f"Итог — {target_label} ({route_mode})",
        planned_body,
    )

    if diff["removed"]:
        removed_body = diff["removed"][:preview_limit]
        if len(diff["removed"]) > preview_limit:
            removed_body.append(f"... ещё {len(diff['removed']) - preview_limit}")
        _append_change_log_lines(lines, "Убирается из блока", removed_body)

    additions_body = []
    if trim_details:
        for item in trim_details:
            comment = str(item.get("comment") or "").strip().lstrip("#").strip()
            original_cidr = str(item.get("original_cidr") or item.get("game_cidr") or "").strip()
            game_key = str(item.get("game_key") or "").strip()
            status = str(item.get("status") or "").strip()
            write_cidrs = _normalize_cidrs(item.get("write_cidrs") or [])
            prefix = f"[{game_key}] " if game_key else ""
            if comment:
                additions_body.append(f"{prefix}{comment}")
            elif status == "full" and is_exclude:
                additions_body.append(
                    f"{prefix}{original_cidr} — полностью в include; добавлено: {original_cidr}"
                )
            elif status == "full":
                additions_body.append(f"{prefix}{original_cidr} — уже через VPN, не добавляется")
            elif status == "partial":
                added_desc = ", ".join(write_cidrs) or original_cidr
                label = "частично в include" if is_exclude else "частично обрезано"
                additions_body.append(f"{prefix}{original_cidr} — {label}; добавлено: {added_desc}")
            elif write_cidrs:
                additions_body.append(f"{prefix}{original_cidr} → {', '.join(write_cidrs)}")
            elif original_cidr and original_cidr not in (planned if is_exclude else diff["added"]):
                if not is_exclude and status == "none":
                    additions_body.append(f"{prefix}{original_cidr}")
    elif diff["added"]:
        additions_body = diff["added"][:preview_limit]
        if len(diff["added"]) > preview_limit:
            additions_body.append(f"... ещё {len(diff['added']) - preview_limit}")
    section_title = (
        "Детали exclude-маршрутов (пересечения с include)"
        if is_exclude
        else "Детали include-маршрутов (пересечения с VPN)"
    )
    _append_change_log_lines(lines, section_title, additions_body)

    if diff["added"] and trim_details:
        added_only_body = diff["added"][:preview_limit]
        if len(diff["added"]) > preview_limit:
            added_only_body.append(f"... ещё {len(diff['added']) - preview_limit}")
        _append_change_log_lines(lines, "Новые маршруты (нет в текущем блоке)", added_only_body)

    if planned:
        planned_list_body = planned[:preview_limit]
        if len(planned) > preview_limit:
            planned_list_body.append(f"... ещё {len(planned) - preview_limit}")
        _append_change_log_lines(
            lines,
            f"Полный список после применения ({len(planned)})",
            planned_list_body,
        )

    if is_exclude and (include_patches or include_skipped):
        patch_body = []
        for patch in include_patches:
            file_label = _preview_file_label(patch.get("file"))
            old_cidr = str(patch.get("old_cidr") or "").strip()
            new_cidrs = _normalize_cidrs(patch.get("new_cidrs") or [])
            target = ", ".join(new_cidrs) if new_cidrs else "(удалено)"
            patch_body.append(f"{file_label}: {old_cidr} → {target}")
        for item in include_skipped:
            patch_body.append(_format_include_patch_skip_log_line(item))
        _append_change_log_lines(lines, "Изменения include-файлов (punch)", patch_body)

    if selected_game_keys:
        lines.append(f"# Игры: {', '.join(selected_game_keys)}")

    return {
        "filter_kind": filter_kind,
        "target_file": str(ips_file_path or ""),
        "target_label": target_label,
        "current_cidrs": current,
        "planned_cidrs": planned,
        "added_cidrs": diff["added"],
        "removed_cidrs": diff["removed"],
        "unchanged_cidrs": diff["unchanged"],
        "trim_details": trim_details,
        "include_changes": include_patches,
        "include_changes_skipped": include_skipped,
        "punch_warnings": list(overlap_summary.get("punch_warnings") or []),
        "punch_limitations": punch_limitations,
        "lines": lines,
    }


def _merge_preview_change_logs(*logs):
    merged_lines = []
    sections = []
    for index, log in enumerate(logs):
        if not log:
            continue
        sections.append(log)
        if index > 0:
            merged_lines.append("")
        merged_lines.extend(log.get("lines") or [])
    if len(sections) <= 1:
        return sections[0] if sections else None
    return {
        "filter_kind": "mixed",
        "sections": sections,
        "lines": merged_lines,
    }


def _strip_games_filter_block(content):
    return _strip_managed_block(content, GAME_FILTER_BLOCK_START, GAME_FILTER_BLOCK_END)


def _strip_games_filter_ips_block(content):
    return _strip_managed_block(content, GAME_FILTER_IP_BLOCK_START, GAME_FILTER_IP_BLOCK_END)


def _strip_games_exclude_filter_block(content):
    return _strip_managed_block(content, GAME_FILTER_EXCLUDE_BLOCK_START, GAME_FILTER_EXCLUDE_BLOCK_END)


def _strip_games_exclude_filter_ips_block(content):
    return _strip_managed_block(content, GAME_FILTER_EXCLUDE_IP_BLOCK_START, GAME_FILTER_EXCLUDE_IP_BLOCK_END)


def _format_game_section_header(key, title):
    safe_title = str(title or key or "Game").strip()
    safe_key = str(key or "").strip().lower()
    return f"# --- {safe_title} ({safe_key}) ---"


def _format_provider_section_header(provider_key, title):
    safe_title = str(title or provider_key or "Provider").strip()
    safe_key = str(provider_key or "").strip().lower()
    return f"# --- {safe_title} ({safe_key}) ---"


def _render_games_filter_block(
    selected_provider_keys,
    include_game_domains=False,
    block_start=GAME_FILTER_BLOCK_START,
    block_end=GAME_FILTER_BLOCK_END,
):
    normalized_keys = _normalize_provider_filter_keys(selected_provider_keys)
    if not include_game_domains:
        selected_titles, _ = _collect_provider_domains(normalized_keys)
        return "", selected_titles, []
    lines = [block_start]
    lines.append(f"# Keys: {','.join(normalized_keys)}")
    lines.append(f"# Providers: {len(normalized_keys)}")
    selected_titles = []
    selected_domains = []
    for provider_key in normalized_keys:
        provider = PROVIDER_FILTER_BY_KEY.get(provider_key)
        if not provider:
            continue
        selected_titles.append(provider["title"])
        domains = list(dict.fromkeys(
            domain
            for game_key in provider.get("game_keys") or []
            for domain in (GAME_FILTER_BY_KEY.get(game_key) or {}).get("domains") or []
        ))
        if not domains:
            continue
        lines.append("")
        lines.append(_format_provider_section_header(provider_key, provider["title"]))
        lines.append(f"# Games: {','.join(provider.get('game_keys') or [])}")
        lines.extend(domains)
        for domain in domains:
            if domain not in selected_domains:
                selected_domains.append(domain)
    if len(lines) <= 3:
        return "", selected_titles, []
    lines.append(block_end)
    return "\n".join(lines), selected_titles, selected_domains


def _render_games_ips_block(
    selected_provider_keys,
    block_start=GAME_FILTER_IP_BLOCK_START,
    block_end=GAME_FILTER_IP_BLOCK_END,
    apply_vpn_overlap_trim=None,
    apply_exclude_include_punch=None,
    preview_only=False,
):
    if apply_vpn_overlap_trim is None:
        apply_vpn_overlap_trim = block_start == GAME_FILTER_IP_BLOCK_START
    if apply_exclude_include_punch is None:
        apply_exclude_include_punch = block_start == GAME_FILTER_EXCLUDE_IP_BLOCK_START
    normalized_keys = _normalize_provider_filter_keys(selected_provider_keys)
    if not normalized_keys:
        return "", [], [], [], [], {}, _empty_overlap_summary(), {}
    titles = []
    all_cidrs = set()
    source_labels = []
    game_server_ip_total = 0
    dns_fallback_domains = []
    dns_fallback_used = False
    unresolved_domains = []
    per_game_cidrs = {}
    shared_asn_cache = {}
    unique_asns = set()
    for provider_key in normalized_keys:
        for game_key in (PROVIDER_FILTER_BY_KEY.get(provider_key) or {}).get("game_keys") or []:
            unique_asns.update((GAME_FILTER_BY_KEY.get(game_key) or {}).get("asns") or [])
    asn_prefixes_map, asn_labels, asn_errors = _resolve_asn_prefixes_map(
        sorted(unique_asns),
        shared_cache=shared_asn_cache,
    )
    if asn_labels:
        source_labels.extend(asn_labels)
    if asn_errors:
        logger.warning("Game ASN fetch errors: %s", "; ".join(asn_errors))
    for provider_key in normalized_keys:
        provider = PROVIDER_FILTER_BY_KEY.get(provider_key)
        if not provider:
            continue
        titles.append(provider["title"])
        key_cidrs, key_unresolved, meta = _collect_provider_union_cidrs(
            provider_key,
            asn_prefixes_map=asn_prefixes_map,
            shared_asn_cache=shared_asn_cache,
        )
        game_server_ip_total += int(meta.get("game_server_ip_total") or 0)
        if meta.get("dns_fallback_used"):
            dns_fallback_used = True
            dns_fallback_domains.extend(meta.get("dns_fallback_domains") or [])
        unresolved_domains.extend(key_unresolved)
        per_game_cidrs[provider_key] = key_cidrs
        all_cidrs.update(key_cidrs)
    selected_cidrs = _normalize_cidrs(sorted(all_cidrs))
    unresolved_domains = sorted(set(unresolved_domains))
    selected_domains = list(dict.fromkeys(
        domain
        for provider_key in normalized_keys
        for game_key in (PROVIDER_FILTER_BY_KEY.get(provider_key) or {}).get("game_keys") or []
        for domain in (GAME_FILTER_BY_KEY.get(game_key) or {}).get("domains") or []
    ))
    if not selected_cidrs:
        return "", titles, selected_domains, [], unresolved_domains, per_game_cidrs, _empty_overlap_summary(), {}

    overlap_summary = _empty_overlap_summary()
    render_lines_by_key = {}
    per_game_trim_stats = {}
    if apply_vpn_overlap_trim:
        filtered_per_game, render_lines_by_key, overlap_summary, per_game_trim_stats = _apply_vpn_overlap_trim(
            per_game_cidrs,
            collect_trim_details=bool(preview_only),
        )
        per_game_cidrs = filtered_per_game
        selected_cidrs = _normalize_cidrs(sorted({cidr for cidrs in per_game_cidrs.values() for cidr in cidrs}))
        per_game_cidrs, route_budget_meta = _apply_config_route_budget_to_providers(
            per_game_cidrs,
            normalized_keys,
        )
        overlap_summary = dict(overlap_summary or _empty_overlap_summary())
        overlap_summary["route_budget"] = route_budget_meta
        selected_cidrs = _normalize_cidrs(sorted({cidr for cidrs in per_game_cidrs.values() for cidr in cidrs}))
        for provider_key, cidrs in per_game_cidrs.items():
            if provider_key not in render_lines_by_key or route_budget_meta.get("compression_applied"):
                render_lines_by_key[provider_key] = list(cidrs)
            key_stats = per_game_trim_stats.get(provider_key) or {}
            key_stats["routes_count"] = len(render_lines_by_key.get(provider_key) or cidrs)
            key_stats["cidr_count"] = len(cidrs)
            per_game_trim_stats[provider_key] = key_stats
        overlap_summary["routes_written_count"] = len(selected_cidrs)
    elif apply_exclude_include_punch:
        filtered_per_game, render_lines_by_key, overlap_summary, per_game_trim_stats = _apply_exclude_include_punch(
            per_game_cidrs,
            preview_only=bool(preview_only),
        )
        per_game_cidrs = filtered_per_game
        selected_cidrs = _normalize_cidrs(sorted({cidr for cidrs in per_game_cidrs.values() for cidr in cidrs}))

    lines = [block_start]
    lines.append(f"# Keys: {','.join(normalized_keys)}")
    lines.append(f"# Providers: {len(normalized_keys)}")
    if apply_vpn_overlap_trim and int(overlap_summary.get("original_cidr_count") or 0) > 0:
        fully_covered = int(overlap_summary.get("fully_covered_count") or 0)
        routes_written = int(overlap_summary.get("routes_written_count") or 0)
        original_count = int(overlap_summary.get("original_cidr_count") or 0)
        if fully_covered > 0:
            lines.append(f"# VPN-covered (skip): {fully_covered}")
        lines.append(f"# Routes added after trim: {routes_written} (from {original_count} original)")
    if apply_exclude_include_punch and int(overlap_summary.get("original_cidr_count") or 0) > 0:
        include_patches_count = int(overlap_summary.get("include_patches_count") or 0)
        routes_written = int(overlap_summary.get("routes_written_count") or 0)
        original_count = int(overlap_summary.get("original_cidr_count") or 0)
        if include_patches_count > 0:
            lines.append(f"# Include split: {include_patches_count}")
        skipped_patches = int(overlap_summary.get("include_patches_skipped_count") or 0)
        if skipped_patches > 0:
            lines.append(f"# Include split skipped: {skipped_patches}")
        lines.append(f"# Routes added: {routes_written} (from {original_count} original)")
    if game_server_ip_total:
        lines.append(f"# Game servers: {game_server_ip_total} static IP/CIDR entries")
    route_budget = overlap_summary.get("route_budget") or {}
    if route_budget:
        lines.append(
            f"# Config include-ips budget: {int(route_budget.get('total_routes_planned') or 0)}"
            f"/{int(route_budget.get('limit') or _get_config_include_ips_route_limit())}"
            f" (non-game: {int(route_budget.get('non_game_routes') or 0)},"
            f" game: {int(route_budget.get('game_routes_planned') or 0)})"
        )
        if route_budget.get("compression_applied"):
            lines.append(
                f"# Game routes compacted: {int(route_budget.get('game_routes_before') or 0)}"
                f" → {int(route_budget.get('game_routes_planned') or 0)}"
            )
    if source_labels:
        lines.append(f"# Sources (ASN via RIPE): {', '.join(source_labels)}")
    if dns_fallback_used:
        lines.append("# WARNING: DNS fallback (website domains)")
    if dns_fallback_domains:
        unique_domains = len(list(dict.fromkeys(dns_fallback_domains)))
        resolved_count = unique_domains - len(unresolved_domains)
        lines.append(f"# DNS-resolved domains: {resolved_count}/{unique_domains}")
    if unresolved_domains:
        preview = ", ".join(unresolved_domains[:10])
        if len(unresolved_domains) > 10:
            preview = f"{preview}, ..."
        lines.append(f"# Unresolved ({len(unresolved_domains)}): {preview}")
    preview_line_limit = 20 if preview_only and apply_exclude_include_punch else None
    preview_lines_added = 0
    for provider_key in normalized_keys:
        provider = PROVIDER_FILTER_BY_KEY.get(provider_key)
        if not provider:
            continue
        key_cidrs = per_game_cidrs.get(provider_key) or []
        game_lines = render_lines_by_key.get(provider_key) if (apply_vpn_overlap_trim or apply_exclude_include_punch) else key_cidrs
        if not game_lines and not (preview_only and apply_exclude_include_punch and key_cidrs):
            continue
        lines.append("")
        lines.append(_format_provider_section_header(provider_key, provider["title"]))
        lines.append(f"# Games: {','.join(provider.get('game_keys') or [])}")
        if preview_only and apply_exclude_include_punch:
            sample_lines = game_lines[:preview_line_limit] if game_lines else key_cidrs[:preview_line_limit]
            for line in sample_lines:
                if preview_line_limit is not None and preview_lines_added >= preview_line_limit:
                    break
                lines.append(line)
                preview_lines_added += 1
            remaining_routes = max(0, len(key_cidrs) - len(sample_lines))
            if remaining_routes > 0:
                lines.append(f"# ... preview truncated, ещё {remaining_routes} маршрутов")
            break
        lines.extend(game_lines)
    lines.append(block_end)
    return (
        "\n".join(lines),
        titles,
        selected_domains,
        selected_cidrs,
        unresolved_domains,
        per_game_cidrs,
        overlap_summary,
        per_game_trim_stats,
    )


def _iter_overlap_source_files():
    """VPN include routes used for overlap/punch (deployed antizapret config only).

    ``ips/list/*.txt`` is the AdminAntizapret source catalog and is intentionally
    excluded — live OpenVPN routes come from ``config/AP-*-include-ips.txt`` copies.
    """
    files = set()

    az_ips_path = str(_cfg("AZ_GAME_INCLUDE_IPS_FILE") or "").strip()
    az_hosts_path = str(_cfg("AZ_GAME_INCLUDE_HOSTS_FILE") or "").strip()
    config_dir = os.path.dirname(az_ips_path) if az_ips_path else "/root/antizapret/config"
    if os.path.isdir(config_dir):
        az_ips_name = os.path.basename(az_ips_path)
        az_hosts_name = os.path.basename(az_hosts_path)
        for name in os.listdir(config_dir):
            path = os.path.join(config_dir, name)
            if not os.path.isfile(path) or not name.endswith(".txt"):
                continue
            if name in {az_ips_name, az_hosts_name}:
                continue
            files.add(path)

    legacy = str(_cfg("LEGACY_GAME_INCLUDE_IPS_FILE") or "").strip()
    if legacy:
        files.add(legacy)

    return sorted(files)


def _extract_cidr_entries_from_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return []
    cidr_pattern = _cfg("CIDR_V4_SCAN_PATTERN")
    if not cidr_pattern:
        return []
    matches = cidr_pattern.findall(content)
    entries = []
    for cidr in _normalize_cidrs(matches):
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        entries.append(
            {
                "cidr": cidr,
                "file": path,
                "start": int(network.network_address),
                "end": int(network.broadcast_address),
            }
        )
    return entries


def _overlap_source_files_signature():
    parts = []
    for path in _iter_overlap_source_files():
        try:
            stat = os.stat(path)
            parts.append((path, stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((path, 0, 0))
    return tuple(parts)


def _build_overlap_index():
    signature = _overlap_source_files_signature()
    cached = _OVERLAP_INDEX_CACHE
    if cached.get("signature") == signature and cached.get("entries") is not None:
        return cached["entries"], cached["starts"]

    entries = []
    for path in _iter_overlap_source_files():
        entries.extend(_extract_cidr_entries_from_file(path))
    entries.sort(key=lambda item: item["start"])
    starts = [entry["start"] for entry in entries]
    _OVERLAP_INDEX_CACHE.update({"signature": signature, "entries": entries, "starts": starts})
    return entries, starts


def _overlap_source_label(path):
    return os.path.basename(str(path or "")) or str(path or "")


def _is_include_patch_target_file(path):
    list_dir = os.path.abspath(str(_cfg("LIST_DIR") or "").strip())
    normalized = os.path.abspath(str(path or "").strip())
    if not normalized:
        return False
    if list_dir and (normalized == list_dir or normalized.startswith(list_dir + os.sep)):
        return False
    return True


def _format_covering_desc(covering, limit=3):
    parts = []
    for item in covering[:limit]:
        parts.append(f"{_overlap_source_label(item['file'])}: {item['cidr']}")
    if len(covering) > limit:
        parts.append(f"... ещё {len(covering) - limit}")
    return "; ".join(parts)


def _find_overlapping_entries(start, end, entries, starts):
    overlaps = []
    idx = bisect_right(starts, end) - 1
    while idx >= 0:
        item = entries[idx]
        if item["end"] >= start and item["start"] <= end:
            overlaps.append(item)
        idx -= 1
    return overlaps


def _collapse_trimmed_cidrs(cidrs):
    if not cidrs:
        return []
    try:
        parsed = [ipaddress.ip_network(value, strict=False) for value in cidrs]
        collapsed = ipaddress.collapse_addresses(parsed)
        return _normalize_cidrs([str(network) for network in collapsed])
    except ValueError:
        return _normalize_cidrs(cidrs)


def _read_env_bool(key, *, default="n", get_env_value=None):
    if callable(get_env_value):
        raw = str(get_env_value(key, default) or default).strip().lower()
    else:
        raw = str(os.getenv(key, default) or default).strip().lower()
    return raw in {"y", "yes", "1", "true", "on"}


def get_game_filter_route_limit_settings(*, get_env_value=None):
    """Settings for optional disable of the 900-route budget during game filter apply."""
    disable_requested = _read_env_bool(
        AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT_ENV,
        get_env_value=get_env_value,
    )
    risk_ack = _read_env_bool(
        AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK_ENV,
        get_env_value=get_env_value,
    )
    limit_enforced = not (disable_requested and risk_ack)
    return {
        "disable_route_limit": disable_requested,
        "route_limit_risk_ack": risk_ack,
        "route_limit_enforced": limit_enforced,
    }


def is_game_filter_config_route_limit_enforced(*, get_env_value=None):
    return bool(get_game_filter_route_limit_settings(get_env_value=get_env_value)["route_limit_enforced"])


def _get_config_include_ips_route_limit():
    try:
        limit = int(_facade_call("_get_openvpn_route_total_cidr_limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        limit = int(_cfg("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS") or 900)
    return limit


def _iter_config_include_ips_files():
    az_ips_path = str(_cfg("AZ_GAME_INCLUDE_IPS_FILE") or "").strip()
    config_dir = os.path.dirname(az_ips_path) if az_ips_path else "/root/antizapret/config"
    if not os.path.isdir(config_dir):
        return []
    files = []
    for name in sorted(os.listdir(config_dir)):
        if not name.endswith("include-ips.txt"):
            continue
        path = os.path.join(config_dir, name)
        if os.path.isfile(path):
            files.append(path)
    return files


def _count_cidrs_in_text(content):
    cidr_pattern = _cfg("CIDR_V4_SCAN_PATTERN")
    if not cidr_pattern:
        return 0
    return len(_normalize_cidrs(cidr_pattern.findall(content)))


def _count_file_include_ips_routes(path, *, strip_managed_block=False, block_start=None, block_end=None):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return 0
    if strip_managed_block and block_start and block_end:
        content = _strip_managed_block(content, block_start, block_end)
    return _count_cidrs_in_text(content)


def get_config_include_ips_route_stats(*, planned_game_cidrs=None, route_limit_enforced=None):
    """Count OpenVPN routes across config/*include-ips.txt (hard limit 900 on iOS)."""
    if route_limit_enforced is None:
        route_limit_enforced = is_game_filter_config_route_limit_enforced()
    limit = _get_config_include_ips_route_limit()
    az_ips_path = str(_cfg("AZ_GAME_INCLUDE_IPS_FILE") or "").strip()
    by_file = {}
    non_game_routes = 0
    game_routes = 0
    az_outside_routes = 0

    for path in _iter_config_include_ips_files():
        label = os.path.basename(path)
        if path == az_ips_path:
            az_outside_routes = _count_file_include_ips_routes(
                path,
                strip_managed_block=True,
                block_start=GAME_FILTER_IP_BLOCK_START,
                block_end=GAME_FILTER_IP_BLOCK_END,
            )
            if planned_game_cidrs is not None:
                game_routes = len(_normalize_cidrs(planned_game_cidrs))
            else:
                game_routes = len(
                    _read_managed_block_cidrs(path, GAME_FILTER_IP_BLOCK_START, GAME_FILTER_IP_BLOCK_END)
                )
            file_total = az_outside_routes + game_routes
            by_file[label] = file_total
        else:
            file_total = _count_file_include_ips_routes(path)
            by_file[label] = file_total
            non_game_routes += file_total

    non_game_routes += az_outside_routes
    total_routes = non_game_routes + game_routes
    game_budget = max(0, limit - non_game_routes)
    over_limit = max(0, total_routes - limit)
    if not route_limit_enforced:
        over_limit = 0
    return {
        "limit": limit,
        "limit_enforced": route_limit_enforced,
        "total_routes": total_routes,
        "non_game_routes": non_game_routes,
        "game_routes": game_routes,
        "game_budget": game_budget,
        "remaining_budget": max(0, limit - total_routes),
        "over_limit": over_limit,
        "by_file": by_file,
    }


def _summarize_provider_cidrs_no_overlap(cidrs, budget):
    normalized = _normalize_cidrs(cidrs or [])
    if budget <= 0:
        return [], {
            "strategy": "budget_empty",
            "original_cidr_count": len(normalized),
            "compressed_cidr_count": 0,
            "target_limit": 0,
        }
    if not normalized:
        return [], None

    collapsed = _collapse_trimmed_cidrs(normalized)
    if len(collapsed) <= budget:
        if len(collapsed) < len(normalized):
            return collapsed, {
                "strategy": "collapse_addresses",
                "original_cidr_count": len(normalized),
                "compressed_cidr_count": len(collapsed),
                "target_limit": budget,
            }
        return collapsed, None

    merged = collapsed
    try:
        import netaddr

        merged = [str(item) for item in netaddr.cidr_merge([netaddr.IPNetwork(value) for value in collapsed])]
        merged = _normalize_cidrs(merged)
    except Exception:  # noqa: BLE001
        merged = collapsed

    if len(merged) <= budget:
        return merged, {
            "strategy": "netaddr_cidr_merge",
            "original_cidr_count": len(normalized),
            "compressed_cidr_count": len(merged),
            "target_limit": budget,
        }

    compressed, compression_meta = _facade_call("_compress_cidrs_to_limit", merged, budget)
    if compression_meta:
        compression_meta = dict(compression_meta)
        compression_meta["original_cidr_count"] = len(normalized)
    else:
        compression_meta = {
            "strategy": "trim_to_budget",
            "original_cidr_count": len(normalized),
            "compressed_cidr_count": len(compressed),
            "target_limit": budget,
        }
    return _normalize_cidrs(compressed), compression_meta


def _apply_config_route_budget_to_providers(per_provider_cidrs, provider_order):
    stats = get_config_include_ips_route_stats()
    budget = int(stats.get("game_budget") or 0)
    limit = int(stats.get("limit") or _get_config_include_ips_route_limit())
    non_game_routes = int(stats.get("non_game_routes") or 0)
    limit_enforced = bool(stats.get("limit_enforced", True))

    ordered_keys = [key for key in provider_order if key in (per_provider_cidrs or {})]
    original_by_key = {
        key: _normalize_cidrs(per_provider_cidrs.get(key) or [])
        for key in ordered_keys
    }
    original_total = sum(len(original_by_key.get(key) or []) for key in ordered_keys)

    def _build_route_budget(result_by_key, *, compression_applied, provider_compression=None, strategy=None):
        compressed_total = sum(len(result_by_key.get(key) or []) for key in ordered_keys)
        planned_total = non_game_routes + compressed_total
        over_limit = max(0, planned_total - limit)
        if not limit_enforced:
            over_limit = 0
        payload = {
            "limit": limit,
            "limit_enforced": limit_enforced,
            "non_game_routes": non_game_routes,
            "game_budget": budget,
            "game_routes_before": original_total,
            "game_routes_after_collapse": compressed_total,
            "game_routes_planned": compressed_total,
            "total_routes_planned": planned_total,
            "remaining_budget": max(0, limit - planned_total),
            "over_limit": over_limit,
            "compressed_providers": provider_compression or {},
            "compression_applied": compression_applied,
        }
        if strategy:
            payload["strategy"] = strategy
        return payload

    if not limit_enforced:
        return original_by_key, _build_route_budget(original_by_key, compression_applied=False)

    if original_total <= budget:
        return original_by_key, _build_route_budget(original_by_key, compression_applied=False)

    collapsed_by_key = {
        key: _collapse_trimmed_cidrs(original_by_key.get(key) or [])
        for key in ordered_keys
    }
    collapsed_total = sum(len(collapsed_by_key.get(key) or []) for key in ordered_keys)
    if collapsed_total <= budget:
        return collapsed_by_key, _build_route_budget(
            collapsed_by_key,
            compression_applied=collapsed_total < original_total,
            strategy="collapse_addresses",
        )

    result = {}
    provider_compression = {}
    remaining = budget
    for provider_key in ordered_keys:
        provider_cidrs = collapsed_by_key.get(provider_key) or []
        if not provider_cidrs:
            result[provider_key] = []
            continue
        provider_budget = min(len(provider_cidrs), remaining)
        compressed, meta = _summarize_provider_cidrs_no_overlap(provider_cidrs, provider_budget)
        result[provider_key] = compressed
        remaining = max(0, remaining - len(compressed))
        if meta:
            provider_compression[provider_key] = meta

    return result, _build_route_budget(
        result,
        compression_applied=True,
        provider_compression=provider_compression,
    )


def _trim_cidr_against_vpn_routes(cidr, entries, starts):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return {"status": "none", "write_cidrs": [], "covering": [], "comment": ""}

    start = int(network.network_address)
    end = int(network.broadcast_address)
    overlapping = _find_overlapping_entries(start, end, entries, starts)
    if not overlapping:
        return {"status": "none", "write_cidrs": [cidr], "covering": [], "comment": ""}

    covering = [{"cidr": item["cidr"], "file": item["file"]} for item in overlapping]
    covering_desc = _format_covering_desc(covering)

    try:
        import netaddr

        candidate = netaddr.IPNetwork(cidr)
        covering_set = netaddr.IPSet([netaddr.IPNetwork(item["cidr"]) for item in overlapping])
        remaining = list(netaddr.IPSet([candidate]) - covering_set)
    except Exception:  # noqa: BLE001
        for item in overlapping:
            try:
                existing = ipaddress.ip_network(item["cidr"], strict=False)
            except ValueError:
                continue
            if existing.supernet_of(network) or existing == network:
                comment = (
                    f"# {cidr} — уже идёт через VPN ({covering_desc}), "
                    "добавление не требуется"
                )
                return {"status": "full", "write_cidrs": [], "covering": covering, "comment": comment}
        return {"status": "none", "write_cidrs": [cidr], "covering": covering, "comment": ""}

    if not remaining:
        comment = (
            f"# {cidr} — уже идёт через VPN ({covering_desc}), "
            "добавление не требуется"
        )
        return {"status": "full", "write_cidrs": [], "covering": covering, "comment": comment}

    write_cidrs = _collapse_trimmed_cidrs([str(value) for value in remaining])
    added_desc = ", ".join(write_cidrs)
    comment = f"# {cidr} — частично покрыто ({covering_desc}); добавлено: {added_desc}"
    return {"status": "partial", "write_cidrs": write_cidrs, "covering": covering, "comment": comment}


def _empty_overlap_summary():
    return {
        "overlap_count": 0,
        "overlap_game_keys_count": 0,
        "fully_covered_count": 0,
        "partial_trimmed_count": 0,
        "routes_written_count": 0,
        "original_cidr_count": 0,
        "overlap_examples": [],
        "trim_details": [],
        "include_patches_count": 0,
        "include_patches": [],
        "include_patches_preview_only": False,
        "include_patches_skipped_count": 0,
        "include_patches_skip_reasons": [],
        "include_patches_skip_summary": [],
        "punch_limit_min_prefix": EXCLUDE_PUNCH_MIN_INCLUDE_PREFIX,
        "punch_limit_max_fragments": EXCLUDE_PUNCH_MAX_RESULT_CIDRS,
        "punch_limitations": _punch_limitation_context()["notes"],
        "punch_warnings": [],
    }


def _parse_ipv4_network(cidr):
    try:
        network = ipaddress.ip_network(str(cidr or "").strip(), strict=False)
    except ValueError:
        return None
    if network.version != 4:
        return None
    return network


def _is_punchable_include_cidr(cidr):
    network = _parse_ipv4_network(cidr)
    if network is None:
        return False
    return int(network.prefixlen) >= EXCLUDE_PUNCH_MIN_INCLUDE_PREFIX


def _network_fully_covers(outer_cidr, inner_cidr):
    outer = _parse_ipv4_network(outer_cidr)
    inner = _parse_ipv4_network(inner_cidr)
    if outer is None or inner is None:
        return False
    return outer.supernet_of(inner) or outer == inner


def _cidr_fully_covered_by_any(candidate_cidr, cover_cidrs):
    for cover_cidr in cover_cidrs or []:
        if _network_fully_covers(cover_cidr, candidate_cidr):
            return True
    return False


def _exclude_hole_from_network(base_net, hole_net):
    if not base_net.overlaps(hole_net):
        return [base_net]
    if hole_net.supernet_of(base_net) or hole_net == base_net:
        return []

    networks = [base_net]
    index = 0
    while index < len(networks):
        current = networks[index]
        if not current.overlaps(hole_net):
            index += 1
            continue
        if hole_net.supernet_of(current) or hole_net == current:
            networks.pop(index)
            continue
        if int(current.prefixlen) >= 32:
            networks.pop(index)
            continue
        left, right = current.subnets(prefixlen_diff=1)
        networks[index:index + 1] = [left, right]
    return networks


def _subtract_cidrs(base_cidr, subtract_cidrs, max_result_cidrs=None):
    max_result = int(max_result_cidrs or EXCLUDE_PUNCH_MAX_RESULT_CIDRS)
    base_net = _parse_ipv4_network(base_cidr)
    if base_net is None:
        return []
    if not subtract_cidrs:
        return _normalize_cidrs([str(base_net)])

    networks = [base_net]
    for subtract_cidr in subtract_cidrs:
        hole_net = _parse_ipv4_network(subtract_cidr)
        if hole_net is None:
            continue
        next_networks = []
        for network in networks:
            next_networks.extend(_exclude_hole_from_network(network, hole_net))
            if len(next_networks) > max_result:
                return None
        networks = next_networks
        if not networks:
            break

    if not networks:
        return []
    collapsed = _collapse_trimmed_cidrs([str(network) for network in networks])
    if len(collapsed) > max_result:
        return None
    return collapsed


def _append_include_patch_skip_reason(skip_reasons, old_cidr, file_path, reason, exclude_cidr=""):
    if len(skip_reasons) >= EXCLUDE_PUNCH_MAX_SKIP_REASONS:
        return
    skip_reasons.append(
        {
            "old_cidr": str(old_cidr or ""),
            "file": str(file_path or ""),
            "reason": str(reason or ""),
            "exclude_cidr": str(exclude_cidr or ""),
        }
    )


def _trim_exclude_cidr_against_include_routes(cidr, entries, starts):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return {
            "status": "none",
            "write_cidrs": [],
            "include_patches": [],
            "include_patches_skipped": 0,
            "skip_reasons": [],
            "comment": "",
        }

    start = int(network.network_address)
    end = int(network.broadcast_address)
    overlapping = _find_overlapping_entries(start, end, entries, starts)
    if not overlapping:
        return {
            "status": "none",
            "write_cidrs": [cidr],
            "include_patches": [],
            "include_patches_skipped": 0,
            "skip_reasons": [],
            "comment": "",
        }

    if len(overlapping) > EXCLUDE_PUNCH_MAX_OVERLAP_ENTRIES:
        overlapping = overlapping[:EXCLUDE_PUNCH_MAX_OVERLAP_ENTRIES]

    covering = [{"cidr": item["cidr"], "file": item["file"]} for item in overlapping]
    covering_desc = _format_covering_desc(covering)
    overlapping_cidrs = [item["cidr"] for item in overlapping]
    skip_reasons = []

    if _cidr_fully_covered_by_any(cidr, overlapping_cidrs):
        status = "full"
        write_cidrs = [cidr]
        comment = (
            f"# {cidr} — полностью в include ({covering_desc}); "
            f"добавлено: {cidr}"
        )
    else:
        write_cidrs = _subtract_cidrs(cidr, overlapping_cidrs)
        if write_cidrs is None:
            write_cidrs = [cidr]
            _append_include_patch_skip_reason(
                skip_reasons,
                overlapping_cidrs[0] if overlapping_cidrs else cidr,
                covering[0]["file"] if covering else "",
                "exclude_trim_too_many_fragments",
                exclude_cidr=cidr,
            )
        if not write_cidrs:
            status = "full"
            write_cidrs = [cidr]
            comment = (
                f"# {cidr} — полностью в include ({covering_desc}); "
                f"добавлено: {cidr}"
            )
        else:
            status = "partial"
            added_desc = ", ".join(write_cidrs)
            comment = (
                f"# {cidr} — частично в include ({covering_desc}); "
                f"добавлено: {added_desc}"
            )

    include_patches = []
    patches_skipped = 0
    for item in overlapping:
        old_cidr = item["cidr"]
        if not _is_include_patch_target_file(item["file"]):
            continue
        if not _is_punchable_include_cidr(old_cidr):
            patches_skipped += 1
            _append_include_patch_skip_reason(
                skip_reasons,
                old_cidr,
                item["file"],
                "include_route_too_broad",
                exclude_cidr=cidr,
            )
            continue
        new_cidrs = _subtract_cidrs(old_cidr, [cidr])
        if new_cidrs is None:
            patches_skipped += 1
            _append_include_patch_skip_reason(
                skip_reasons,
                old_cidr,
                item["file"],
                "patch_too_many_fragments",
                exclude_cidr=cidr,
            )
            continue
        normalized_old = _normalize_cidrs([old_cidr])
        normalized_new = _normalize_cidrs(new_cidrs)
        if normalized_new == normalized_old:
            continue
        if normalized_new:
            patch_comment = f"# разбита include-сеть {old_cidr} (exclude {cidr})"
        else:
            patch_comment = f"# удалена include-сеть {old_cidr} (полностью в exclude {cidr})"
        include_patches.append(
            {
                "file": item["file"],
                "old_cidr": old_cidr,
                "new_cidrs": normalized_new,
                "comment": patch_comment,
            }
        )

    return {
        "status": status,
        "write_cidrs": write_cidrs,
        "include_patches": include_patches,
        "include_patches_skipped": patches_skipped,
        "skip_reasons": skip_reasons,
        "comment": comment,
        "covering": covering,
    }


def _merge_include_patch_maps(patch_map, include_patches, exclude_cidr):
    for patch in include_patches or []:
        file_path = str(patch.get("file") or "").strip()
        old_cidr = str(patch.get("old_cidr") or "").strip()
        if not file_path or not old_cidr:
            continue
        key = (file_path, old_cidr)
        entry = patch_map.setdefault(
            key,
            {
                "file": file_path,
                "old_cidr": old_cidr,
                "subtract_cidrs": [],
            },
        )
        if exclude_cidr not in entry["subtract_cidrs"]:
            entry["subtract_cidrs"].append(exclude_cidr)


def _finalize_include_patches(patch_map):
    include_patches = []
    skip_reasons = []
    patches_skipped = 0
    for item in patch_map.values():
        old_cidr = item["old_cidr"]
        if not _is_include_patch_target_file(item["file"]):
            continue
        if not _is_punchable_include_cidr(old_cidr):
            patches_skipped += 1
            _append_include_patch_skip_reason(
                skip_reasons,
                old_cidr,
                item["file"],
                "include_route_too_broad",
            )
            continue
        new_cidrs = _subtract_cidrs(old_cidr, item.get("subtract_cidrs") or [])
        if new_cidrs is None:
            patches_skipped += 1
            subtract_desc = ", ".join(item.get("subtract_cidrs") or [])
            _append_include_patch_skip_reason(
                skip_reasons,
                old_cidr,
                item["file"],
                "patch_too_many_fragments",
                exclude_cidr=subtract_desc,
            )
            continue
        normalized_old = _normalize_cidrs([old_cidr])
        normalized_new = _normalize_cidrs(new_cidrs)
        if normalized_new == normalized_old:
            continue
        subtract_desc = ", ".join(item.get("subtract_cidrs") or [])
        if normalized_new:
            patch_comment = f"# разбита include-сеть {old_cidr} (exclude {subtract_desc})"
        else:
            patch_comment = f"# удалена include-сеть {old_cidr} (полностью в exclude {subtract_desc})"
        include_patches.append(
            {
                "file": item["file"],
                "old_cidr": old_cidr,
                "new_cidrs": normalized_new,
                "comment": patch_comment,
            }
        )
    return include_patches, patches_skipped, skip_reasons


def _apply_exclude_include_punch(per_game_cidrs, overlap_index=None, preview_only=False):
    if overlap_index is not None:
        entries, starts = overlap_index
    else:
        entries, starts = _build_overlap_index()

    if not per_game_cidrs:
        summary = _empty_overlap_summary()
        if preview_only:
            summary["include_patches_preview_only"] = True
        return {}, {}, summary, {}

    filtered_per_game = {}
    render_lines_by_key = {}
    per_game_trim_stats = {}
    fully_covered_count = 0
    partial_trimmed_count = 0
    original_cidr_count = 0
    overlap_examples = []
    overlapped_original = set()
    patch_map = {}
    patches_skipped_total = 0
    skip_summary_map = {}
    trim_details = [] if preview_only else None

    for key, cidrs in per_game_cidrs.items():
        filtered = []
        lines = [] if not preview_only else None
        key_full = 0
        key_partial = 0
        key_overlap = 0
        key_punched = 0
        for cidr in cidrs:
            original_cidr_count += 1
            punch_result = _trim_exclude_cidr_against_include_routes(cidr, entries, starts)
            status = punch_result.get("status") or "none"
            comment = str(punch_result.get("comment") or "").strip()
            write_cidrs = punch_result.get("write_cidrs") or []
            covering = punch_result.get("covering") or []
            include_patches = punch_result.get("include_patches") or []
            patches_skipped_total += int(punch_result.get("include_patches_skipped") or 0)
            for skip_reason in punch_result.get("skip_reasons") or []:
                _record_include_patch_skip_summary(
                    skip_summary_map,
                    skip_reason.get("old_cidr"),
                    skip_reason.get("file"),
                    skip_reason.get("reason"),
                    exclude_cidr=skip_reason.get("exclude_cidr"),
                )

            if status in {"full", "partial"}:
                overlapped_original.add(cidr)
                key_overlap += 1
            if status == "full":
                fully_covered_count += 1
                key_full += 1
            elif status == "partial":
                partial_trimmed_count += 1
                key_partial += 1
            if include_patches:
                key_punched += len(include_patches)
                _merge_include_patch_maps(patch_map, include_patches, cidr)

            if not preview_only:
                if comment:
                    lines.append(comment)
                for write_cidr in write_cidrs:
                    if write_cidr not in filtered:
                        filtered.append(write_cidr)
                    lines.append(write_cidr)
            else:
                for write_cidr in write_cidrs:
                    if write_cidr not in filtered:
                        filtered.append(write_cidr)

            if trim_details is not None:
                trim_details.append(
                    {
                        "game_key": key,
                        "original_cidr": cidr,
                        "status": status,
                        "write_cidrs": list(write_cidrs),
                        "comment": comment,
                        "covering": covering,
                    }
                )

            if status in {"full", "partial"} and len(overlap_examples) < 20:
                overlap_examples.append(
                    {
                        "type": status,
                        "game_cidr": cidr,
                        "existing_cidr": covering[0]["cidr"] if covering else "",
                        "file": covering[0]["file"] if covering else "",
                        "written_cidrs": write_cidrs,
                        "comment": comment,
                    }
                )

        filtered_per_game[key] = _normalize_cidrs(filtered)
        render_lines_by_key[key] = lines or []
        per_game_trim_stats[key] = {
            "cidr_count": len(cidrs),
            "routes_count": len(filtered_per_game[key]),
            "covered_count": key_full,
            "partial_count": key_partial,
            "overlap_count": key_overlap,
            "punched_include_count": key_punched,
        }

    include_patches, finalize_skipped, finalize_skip_reasons = _finalize_include_patches(patch_map)
    patches_skipped_total += int(finalize_skipped or 0)
    for skip_reason in finalize_skip_reasons or []:
        _record_include_patch_skip_summary(
            skip_summary_map,
            skip_reason.get("old_cidr"),
            skip_reason.get("file"),
            skip_reason.get("reason"),
            exclude_cidr=skip_reason.get("exclude_cidr"),
        )
    overlap_game_keys_count = sum(
        1 for stats in per_game_trim_stats.values() if int(stats.get("overlap_count") or 0) > 0
    )
    routes_written_count = len(
        _normalize_cidrs(sorted({cidr for key_cidrs in filtered_per_game.values() for cidr in key_cidrs}))
    )
    overlap_summary = {
        "overlap_count": len(overlapped_original),
        "overlap_game_keys_count": overlap_game_keys_count,
        "fully_covered_count": fully_covered_count,
        "partial_trimmed_count": partial_trimmed_count,
        "routes_written_count": routes_written_count,
        "original_cidr_count": original_cidr_count,
        "overlap_examples": overlap_examples,
        "trim_details": trim_details or [],
        "include_patches_count": len(include_patches),
        "include_patches": include_patches,
        "include_patches_preview_only": bool(preview_only),
        "include_patches_skipped_count": patches_skipped_total,
    }
    overlap_summary = _enrich_overlap_summary_punch_warnings(overlap_summary, skip_summary_map)
    return filtered_per_game, render_lines_by_key, overlap_summary, per_game_trim_stats


def _line_is_exact_cidr_line(line, cidr):
    stripped = str(line or "").strip()
    if not stripped or stripped.startswith("#"):
        return False
    normalized = _normalize_cidrs([stripped])
    target = _normalize_cidrs([cidr])
    return bool(normalized and target and normalized[0] == target[0])


def _replace_exact_cidr_line(content, old_cidr, new_cidrs):
    lines = content.splitlines(keepends=True)
    if not lines and not content:
        return content, False

    replaced = False
    output = []
    for line in lines:
        if not replaced and _line_is_exact_cidr_line(line, old_cidr):
            replaced = True
            if new_cidrs:
                line_ending = "\n"
                if line.endswith("\r\n"):
                    line_ending = "\r\n"
                elif line.endswith("\n"):
                    line_ending = "\n"
                for new_cidr in new_cidrs:
                    output.append(f"{new_cidr}{line_ending}")
            continue
        output.append(line)

    if not replaced:
        return None, False
    return "".join(output), True


def _apply_include_patches_to_files(patches):
    if not patches:
        return {"success": True, "changed": False, "files_patched": 0}

    by_file = {}
    for patch in patches:
        path = str(patch.get("file") or "").strip()
        if not path or not _is_include_patch_target_file(path):
            continue
        by_file.setdefault(path, []).append(patch)

    changed = False
    files_patched = 0
    for path, file_patches in by_file.items():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except OSError as exc:
            return {
                "success": False,
                "error": f"Include patch read failed ({path}): {exc}",
                "changed": False,
                "files_patched": files_patched,
            }

        new_content = content
        file_changed = False
        for patch in file_patches:
            old_cidr = patch.get("old_cidr")
            new_cidrs = patch.get("new_cidrs") or []
            patched_content, did_change = _replace_exact_cidr_line(new_content, old_cidr, new_cidrs)
            if patched_content is None:
                return {
                    "success": False,
                    "error": f"Include patch failed: CIDR {old_cidr} not found in {path}",
                    "changed": False,
                    "files_patched": files_patched,
                }
            new_content = patched_content
            file_changed = file_changed or did_change

        if file_changed and new_content != content:
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(new_content)
            except OSError as exc:
                return {
                    "success": False,
                    "error": f"Include patch write failed ({path}): {exc}",
                    "changed": False,
                    "files_patched": files_patched,
                }
            changed = True
            files_patched += 1

    if changed:
        _OVERLAP_INDEX_CACHE.update({"signature": None, "entries": None, "starts": None})

    return {"success": True, "changed": changed, "files_patched": files_patched}


def _apply_vpn_overlap_trim(per_game_cidrs, overlap_index=None, collect_trim_details=False):
    if overlap_index is not None:
        entries, starts = overlap_index
    else:
        entries, starts = _build_overlap_index()

    if not per_game_cidrs:
        return {}, {}, _empty_overlap_summary(), {}

    filtered_per_game = {}
    render_lines_by_key = {}
    per_game_trim_stats = {}
    fully_covered_count = 0
    partial_trimmed_count = 0
    original_cidr_count = 0
    overlap_examples = []
    overlapped_original = set()
    trim_details = [] if collect_trim_details else None

    for key, cidrs in per_game_cidrs.items():
        filtered = []
        lines = []
        key_fully = 0
        key_partial = 0
        key_overlap = 0
        for cidr in cidrs:
            original_cidr_count += 1
            trim_result = _trim_cidr_against_vpn_routes(cidr, entries, starts)
            status = trim_result.get("status") or "none"
            comment = str(trim_result.get("comment") or "").strip()
            write_cidrs = trim_result.get("write_cidrs") or []
            covering = trim_result.get("covering") or []

            if status in {"full", "partial"}:
                overlapped_original.add(cidr)
                key_overlap += 1
            if status == "full":
                fully_covered_count += 1
                key_fully += 1
                if comment:
                    lines.append(comment)
            elif status == "partial":
                partial_trimmed_count += 1
                key_partial += 1
                if comment:
                    lines.append(comment)
                for write_cidr in write_cidrs:
                    if write_cidr not in filtered:
                        filtered.append(write_cidr)
                    lines.append(write_cidr)
            else:
                filtered.append(cidr)
                lines.append(cidr)

            if trim_details is not None:
                if status == "partial":
                    detail_write = list(write_cidrs)
                elif status == "none":
                    detail_write = [cidr]
                else:
                    detail_write = []
                trim_details.append(
                    {
                        "game_key": key,
                        "original_cidr": cidr,
                        "status": status,
                        "write_cidrs": detail_write,
                        "comment": comment,
                        "covering": covering,
                    }
                )

            if status in {"full", "partial"} and len(overlap_examples) < 20:
                overlap_examples.append(
                    {
                        "type": status,
                        "game_cidr": cidr,
                        "existing_cidr": covering[0]["cidr"] if covering else "",
                        "file": covering[0]["file"] if covering else "",
                        "written_cidrs": write_cidrs,
                        "comment": comment,
                    }
                )

        filtered_per_game[key] = _normalize_cidrs(filtered)
        render_lines_by_key[key] = lines
        per_game_trim_stats[key] = {
            "cidr_count": len(cidrs),
            "routes_count": len(filtered_per_game[key]),
            "covered_count": key_fully,
            "partial_count": key_partial,
            "overlap_count": key_overlap,
        }

    overlap_game_keys_count = sum(
        1 for stats in per_game_trim_stats.values() if int(stats.get("overlap_count") or 0) > 0
    )
    routes_written_count = len(
        _normalize_cidrs(sorted({cidr for key_cidrs in filtered_per_game.values() for cidr in key_cidrs}))
    )
    overlap_summary = {
        "overlap_count": len(overlapped_original),
        "overlap_game_keys_count": overlap_game_keys_count,
        "fully_covered_count": fully_covered_count,
        "partial_trimmed_count": partial_trimmed_count,
        "routes_written_count": routes_written_count,
        "original_cidr_count": original_cidr_count,
        "overlap_examples": overlap_examples,
        "trim_details": trim_details or [],
    }
    return filtered_per_game, render_lines_by_key, overlap_summary, per_game_trim_stats


def _collect_overlap_summary(candidate_cidrs, selected_game_keys=None, _overlap_index=None):
    if _overlap_index is not None:
        entries, starts = _overlap_index
    else:
        entries, starts = _build_overlap_index()
    if not entries or not candidate_cidrs:
        return _empty_overlap_summary()
    _, _, overlap_summary, _ = _apply_vpn_overlap_trim({"_batch": list(candidate_cidrs)}, (entries, starts))
    if selected_game_keys and overlap_summary.get("overlap_count"):
        overlap_summary = dict(overlap_summary)
        overlap_summary["overlap_game_keys_count"] = len(selected_game_keys)
    return overlap_summary


def _read_saved_game_keys(filepaths, block_keyword="games"):
    keys_pattern = re.compile(
        rf"# BEGIN AdminAntizapret CIDR {re.escape(str(block_keyword))}.*?\n# Keys: ([^\n]+)",
        re.DOTALL,
    )
    for filepath in filepaths:
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue
        m = keys_pattern.search(content)
        if not m:
            continue
        raw = m.group(1).strip()
        found = _normalize_provider_filter_keys([k.strip() for k in raw.split(",") if k.strip()])
        if found:
            return found
    return []


def get_saved_provider_keys():
    return _read_saved_game_keys(
        (_cfg("AZ_GAME_INCLUDE_IPS_FILE"), _cfg("AZ_GAME_INCLUDE_HOSTS_FILE")),
        block_keyword="games",
    )


def get_saved_exclude_provider_keys():
    return _read_saved_game_keys(
        (_cfg("AZ_GAME_EXCLUDE_IPS_FILE"), _cfg("AZ_GAME_EXCLUDE_HOSTS_FILE")),
        block_keyword="games",
    )


def get_saved_game_keys():
    return get_saved_provider_keys()


def get_saved_exclude_game_keys():
    return get_saved_exclude_provider_keys()


def preview_games_batch_stats(include_provider_keys=None, include_game_keys=None):
    normalized_keys = _resolve_provider_keys_from_payload(
        include_provider_keys=include_provider_keys,
        include_game_keys=include_game_keys,
    )
    if not normalized_keys:
        normalized_keys = [item["key"] for item in PROVIDER_FILTER_CATALOG]

    shared_asn_cache = {}
    unique_asns = set()
    for provider_key in normalized_keys:
        for game_key in (PROVIDER_FILTER_BY_KEY.get(provider_key) or {}).get("game_keys") or []:
            unique_asns.update((GAME_FILTER_BY_KEY.get(game_key) or {}).get("asns") or [])
    asn_prefixes_map, _, asn_errors = _resolve_asn_prefixes_map(
        sorted(unique_asns),
        shared_cache=shared_asn_cache,
    )
    if asn_errors:
        logger.warning("Game ASN batch fetch errors: %s", "; ".join(asn_errors))

    overlap_index = _build_overlap_index()
    per_provider_stats = {}
    per_game_stats = {}
    for provider_key in normalized_keys:
        key_cidrs, _, _ = _collect_provider_union_cidrs(
            provider_key,
            asn_prefixes_map=asn_prefixes_map,
            shared_asn_cache=shared_asn_cache,
        )
        normalized_key_cidrs = _normalize_cidrs(sorted(key_cidrs))
        _, _, _, trim_stats = _apply_vpn_overlap_trim({provider_key: normalized_key_cidrs}, overlap_index)
        key_stats = trim_stats.get(provider_key) or {}
        stats = {
            "cidr_count": int(key_stats.get("cidr_count") or len(normalized_key_cidrs)),
            "routes_count": int(key_stats.get("routes_count") or len(normalized_key_cidrs)),
            "covered_count": int(key_stats.get("covered_count") or 0),
            "overlap_count": int(key_stats.get("overlap_count") or 0),
        }
        per_provider_stats[provider_key] = stats
        per_game_stats[provider_key] = stats

    return {
        "success": True,
        "message": f"Статистика готова для {len(per_provider_stats)} провайдеров",
        "preview": {
            "per_provider_stats": per_provider_stats,
            "per_game_stats": per_game_stats,
        },
    }


def preview_game_hosts_filter(
    include_game_hosts=False,
    include_game_keys=None,
    include_provider_keys=None,
    include_game_domains=False,
):
    selected_provider_keys = _resolve_provider_filter_selection(
        include_provider_keys=include_provider_keys,
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    hosts_block, selected_titles, selected_domains = _render_games_filter_block(
        selected_provider_keys,
        include_game_domains=bool(include_game_domains),
    )
    ips_block, _, all_domains, selected_cidrs, unresolved_domains, per_provider_cidrs, overlap_summary, per_provider_trim_stats = _render_games_ips_block(
        selected_provider_keys
    )
    per_provider_stats = per_provider_trim_stats or {}
    per_game_stats = {}
    for provider_key, cidrs in per_provider_cidrs.items():
        if provider_key in per_provider_stats:
            stats = per_provider_stats[provider_key]
        else:
            stats = {
                "cidr_count": len(cidrs),
                "routes_count": len(cidrs),
                "covered_count": 0,
                "overlap_count": 0,
            }
        per_provider_stats[provider_key] = stats
        per_game_stats[provider_key] = stats
    selected_count = len(selected_titles)
    routes_written = int(overlap_summary.get("routes_written_count") or len(selected_cidrs))
    original_count = int(overlap_summary.get("original_cidr_count") or len(selected_cidrs))
    if selected_count > 0:
        message = (
            f"Preview готов: {selected_count} провайдеров, "
            f"{len(selected_domains)} доменов, {routes_written} CIDR"
        )
        if original_count > routes_written:
            message += f" (из {original_count} исходных)"
    else:
        message = "Preview готов: выбранные провайдеры отсутствуют"
    fully_covered = int(overlap_summary.get("fully_covered_count") or 0)
    partial_trimmed = int(overlap_summary.get("partial_trimmed_count") or 0)
    if fully_covered > 0:
        message += f". Уже через VPN: {fully_covered}"
    if partial_trimmed > 0:
        message += f". Частично обрезано: {partial_trimmed}"
    route_budget = overlap_summary.get("route_budget") or {}
    if route_budget.get("compression_applied"):
        message += (
            f". Сжато под лимит config: {int(route_budget.get('game_routes_before') or 0)}"
            f" → {int(route_budget.get('game_routes_planned') or 0)} игровых маршрутов"
        )
    if int(route_budget.get("over_limit") or 0) > 0:
        message += f". Превышение лимита config include-ips: {int(route_budget.get('over_limit') or 0)}"
    change_log = _build_preview_change_log(
        "include",
        _cfg("AZ_GAME_INCLUDE_IPS_FILE"),
        GAME_FILTER_IP_BLOCK_START,
        GAME_FILTER_IP_BLOCK_END,
        selected_cidrs,
        overlap_summary,
        selected_game_keys=selected_provider_keys,
    )
    return {
        "success": True,
        "message": message,
        "preview": {
            "enabled": bool(selected_provider_keys),
            "selected_provider_keys": selected_provider_keys,
            "selected_game_keys": selected_provider_keys,
            "selected_provider_count": selected_count,
            "selected_game_count": selected_count,
            "domain_count": len(selected_domains),
            "all_domain_count": len(all_domains),
            "cidr_count": routes_written,
            "original_cidr_count": original_count,
            "unresolved_domain_count": len(unresolved_domains),
            "unresolved_domains": unresolved_domains[:50],
            "include_game_domains": bool(include_game_domains),
            "domains_to_add": selected_domains if include_game_domains else [],
            "overlap_summary": overlap_summary,
            "route_budget": route_budget,
            "per_provider_stats": per_provider_stats,
            "per_game_stats": per_game_stats,
            "change_log": change_log,
            "host_block_preview": hosts_block.splitlines()[:20] if hosts_block else [],
            "ips_block_preview": ips_block.splitlines() if ips_block else [],
        },
    }


def preview_game_exclude_filter(
    include_game_hosts=False,
    include_game_keys=None,
    include_provider_keys=None,
    include_game_domains=False,
):
    selected_provider_keys = _resolve_provider_filter_selection(
        include_provider_keys=include_provider_keys,
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    hosts_block, selected_titles, selected_domains = _render_games_filter_block(
        selected_provider_keys,
        include_game_domains=bool(include_game_domains),
        block_start=GAME_FILTER_EXCLUDE_BLOCK_START,
        block_end=GAME_FILTER_EXCLUDE_BLOCK_END,
    )
    ips_block, _, all_domains, selected_cidrs, unresolved_domains, per_provider_cidrs, overlap_summary, per_provider_trim_stats = _render_games_ips_block(
        selected_provider_keys,
        block_start=GAME_FILTER_EXCLUDE_IP_BLOCK_START,
        block_end=GAME_FILTER_EXCLUDE_IP_BLOCK_END,
        preview_only=True,
    )
    overlap_summary = dict(overlap_summary or _empty_overlap_summary())
    overlap_summary["include_patches_preview_only"] = True
    per_provider_stats = {}
    per_game_stats = {}
    for provider_key, cidrs in per_provider_cidrs.items():
        key_stats = per_provider_trim_stats.get(provider_key) or {}
        stats = {
            "cidr_count": int(key_stats.get("cidr_count") or len(cidrs)),
            "routes_count": int(key_stats.get("routes_count") or len(cidrs)),
            "overlap_count": int(key_stats.get("overlap_count") or 0),
            "punched_include_count": int(key_stats.get("punched_include_count") or 0),
        }
        per_provider_stats[provider_key] = stats
        per_game_stats[provider_key] = stats
    routes_written = int(overlap_summary.get("routes_written_count") or len(selected_cidrs))
    original_count = int(overlap_summary.get("original_cidr_count") or routes_written)
    include_patches_count = int(overlap_summary.get("include_patches_count") or 0)
    include_patches_skipped = int(overlap_summary.get("include_patches_skipped_count") or 0)
    selected_count = len(selected_titles)
    if selected_count > 0:
        message = (
            f"Preview EXCLUDE готов: {selected_count} провайдеров, "
            f"{len(selected_domains)} доменов, {routes_written} CIDR"
        )
        if original_count > routes_written:
            message += f" (из {original_count} исходных)"
    else:
        message = "Preview EXCLUDE готов: выбранные провайдеры отсутствуют"
    if include_patches_count > 0:
        message += f". Будет разбито include-сетей: {include_patches_count}"
    if include_patches_skipped > 0:
        broad_count = sum(
            1
            for item in (overlap_summary.get("include_patches_skip_summary") or [])
            if item.get("reason") == "include_route_too_broad"
        )
        if broad_count:
            message += (
                f". Punch не выполнен для {broad_count} широких include-маршрутов "
                f"(шире /{EXCLUDE_PUNCH_MIN_INCLUDE_PREFIX}) — см. предупреждения"
            )
        else:
            message += f". Punch пропущен: {include_patches_skipped} случаев"
    elif overlap_summary.get("overlap_count"):
        message += f". Найдено пересечений: {overlap_summary.get('overlap_count')}"
    change_log = _build_preview_change_log(
        "exclude",
        _cfg("AZ_GAME_EXCLUDE_IPS_FILE"),
        GAME_FILTER_EXCLUDE_IP_BLOCK_START,
        GAME_FILTER_EXCLUDE_IP_BLOCK_END,
        selected_cidrs,
        overlap_summary,
        selected_game_keys=selected_provider_keys,
    )
    return {
        "success": True,
        "message": message,
        "preview": {
            "enabled": bool(selected_provider_keys),
            "selected_provider_keys": selected_provider_keys,
            "selected_game_keys": selected_provider_keys,
            "selected_provider_count": selected_count,
            "selected_game_count": selected_count,
            "domain_count": len(selected_domains),
            "all_domain_count": len(all_domains),
            "cidr_count": routes_written,
            "original_cidr_count": original_count,
            "unresolved_domain_count": len(unresolved_domains),
            "unresolved_domains": unresolved_domains[:50],
            "include_game_domains": bool(include_game_domains),
            "domains_to_add": selected_domains if include_game_domains else [],
            "overlap_summary": overlap_summary,
            "per_provider_stats": per_provider_stats,
            "per_game_stats": per_game_stats,
            "change_log": change_log,
            "punch_warnings": overlap_summary.get("punch_warnings") or [],
            "host_block_preview": hosts_block.splitlines()[:20] if hosts_block else [],
            "ips_block_preview": ips_block.splitlines() if ips_block else [],
        },
    }


def _sync_games_include_hosts(selected_provider_keys, include_game_domains=False):
    normalized_keys = _normalize_provider_filter_keys(selected_provider_keys)
    path = _cfg("AZ_GAME_INCLUDE_HOSTS_FILE")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            current_content = handle.read()
    except FileNotFoundError:
        current_content = ""
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"AZ game hosts read failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys) and bool(include_game_domains),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    cleaned = _strip_games_filter_block(current_content).strip()
    if normalized_keys and include_game_domains:
        block, selected_titles, selected_domains = _render_games_filter_block(
            normalized_keys,
            include_game_domains=True,
        )
        next_content = f"{cleaned}\n\n{block}\n" if cleaned and block else (f"{block}\n" if block else f"{cleaned}\n")
    else:
        selected_titles, selected_domains = [], []
        next_content = f"{cleaned}\n" if cleaned else ""

    if next_content == current_content:
        return {
            "success": True,
            "changed": False,
            "enabled": bool(normalized_keys) and bool(include_game_domains),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "selected_game_count": len(selected_titles),
            "domain_count": len(selected_domains),
            "include_game_domains": bool(include_game_domains),
            "file": path,
        }

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(next_content)
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"AZ game hosts write failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys) and bool(include_game_domains),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    return {
        "success": True,
        "changed": True,
        "enabled": bool(normalized_keys) and bool(include_game_domains),
        "selected_game_keys": normalized_keys,
        "selected_game_count": len(selected_titles),
        "domain_count": len(selected_domains),
        "include_game_domains": bool(include_game_domains),
        "file": path,
    }


def _sync_games_exclude_hosts(selected_provider_keys, include_game_domains=False):
    normalized_keys = _normalize_provider_filter_keys(selected_provider_keys)
    path = _cfg("AZ_GAME_EXCLUDE_HOSTS_FILE")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            current_content = handle.read()
    except FileNotFoundError:
        current_content = ""
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"AZ game exclude hosts read failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys) and bool(include_game_domains),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    cleaned = _strip_games_exclude_filter_block(current_content).strip()
    if normalized_keys and include_game_domains:
        block, selected_titles, selected_domains = _render_games_filter_block(
            normalized_keys,
            include_game_domains=True,
            block_start=GAME_FILTER_EXCLUDE_BLOCK_START,
            block_end=GAME_FILTER_EXCLUDE_BLOCK_END,
        )
        next_content = f"{cleaned}\n\n{block}\n" if cleaned and block else (f"{block}\n" if block else f"{cleaned}\n")
    else:
        selected_titles, selected_domains = [], []
        next_content = f"{cleaned}\n" if cleaned else ""

    if next_content == current_content:
        return {
            "success": True,
            "changed": False,
            "enabled": bool(normalized_keys) and bool(include_game_domains),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "selected_game_count": len(selected_titles),
            "domain_count": len(selected_domains),
            "include_game_domains": bool(include_game_domains),
            "file": path,
        }

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(next_content)
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"AZ game exclude hosts write failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys) and bool(include_game_domains),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    return {
        "success": True,
        "changed": True,
        "enabled": bool(normalized_keys) and bool(include_game_domains),
        "selected_game_keys": normalized_keys,
        "selected_game_count": len(selected_titles),
        "domain_count": len(selected_domains),
        "include_game_domains": bool(include_game_domains),
        "file": path,
    }


def _sync_games_include_ips(selected_provider_keys):
    normalized_keys = _normalize_provider_filter_keys(selected_provider_keys)
    path = _cfg("AZ_GAME_INCLUDE_IPS_FILE")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            current_content = handle.read()
    except FileNotFoundError:
        current_content = ""
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"AZ game ips read failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    cleaned = _strip_games_filter_ips_block(current_content).strip()
    if normalized_keys:
        block, selected_titles, selected_domains, selected_cidrs, unresolved_domains, _, overlap_summary, _ = _render_games_ips_block(
            normalized_keys
        )
        next_content = f"{cleaned}\n\n{block}\n" if block and cleaned else (f"{block}\n" if block else (f"{cleaned}\n" if cleaned else ""))
    else:
        selected_titles, selected_domains, selected_cidrs, unresolved_domains = [], [], [], []
        overlap_summary = _empty_overlap_summary()
        next_content = f"{cleaned}\n" if cleaned else ""

    cidr_count = int(overlap_summary.get("routes_written_count") or len(selected_cidrs))

    if next_content == current_content:
        return {
            "success": True,
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "selected_game_count": len(selected_titles),
            "domain_count": len(selected_domains),
            "cidr_count": cidr_count,
            "original_cidr_count": int(overlap_summary.get("original_cidr_count") or cidr_count),
            "unresolved_domain_count": len(unresolved_domains),
            "overlap_summary": overlap_summary,
            "file": path,
        }

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(next_content)
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"AZ game ips write failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    return {
        "success": True,
        "changed": True,
        "enabled": bool(normalized_keys),
        "selected_game_keys": normalized_keys,
        "selected_game_count": len(selected_titles),
        "domain_count": len(selected_domains),
        "cidr_count": cidr_count,
        "original_cidr_count": int(overlap_summary.get("original_cidr_count") or cidr_count),
        "unresolved_domain_count": len(unresolved_domains),
        "overlap_summary": overlap_summary,
        "file": path,
    }


def _sync_games_exclude_ips(selected_provider_keys):
    normalized_keys = _normalize_provider_filter_keys(selected_provider_keys)
    path = _cfg("AZ_GAME_EXCLUDE_IPS_FILE")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            current_content = handle.read()
    except FileNotFoundError:
        current_content = ""
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"AZ game exclude ips read failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    cleaned = _strip_games_exclude_filter_ips_block(current_content).strip()
    if normalized_keys:
        block, selected_titles, selected_domains, selected_cidrs, unresolved_domains, _, overlap_summary, _ = _render_games_ips_block(
            normalized_keys,
            block_start=GAME_FILTER_EXCLUDE_IP_BLOCK_START,
            block_end=GAME_FILTER_EXCLUDE_IP_BLOCK_END,
        )
        next_content = f"{cleaned}\n\n{block}\n" if block and cleaned else (f"{block}\n" if block else (f"{cleaned}\n" if cleaned else ""))
    else:
        selected_titles, selected_domains, selected_cidrs, unresolved_domains = [], [], [], []
        overlap_summary = _empty_overlap_summary()
        next_content = f"{cleaned}\n" if cleaned else ""

    include_patches = overlap_summary.get("include_patches") or []
    patch_result = {"success": True, "changed": False, "files_patched": 0}
    if include_patches:
        patch_result = _apply_include_patches_to_files(include_patches)
        if not patch_result.get("success"):
            return {
                "success": False,
                "error": patch_result.get("error") or "Include patch failed",
                "changed": False,
                "enabled": bool(normalized_keys),
                "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
                "file": path,
                "overlap_summary": overlap_summary,
            }

    cidr_count = int(overlap_summary.get("routes_written_count") or len(selected_cidrs))
    include_files_changed = bool(patch_result.get("changed"))
    exclude_content_changed = next_content != current_content

    if not exclude_content_changed and not include_files_changed:
        return {
            "success": True,
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
            "selected_game_count": len(selected_titles),
            "domain_count": len(selected_domains),
            "cidr_count": cidr_count,
            "original_cidr_count": int(overlap_summary.get("original_cidr_count") or cidr_count),
            "unresolved_domain_count": len(unresolved_domains),
            "overlap_summary": overlap_summary,
            "include_patches_applied": int(patch_result.get("files_patched") or 0),
            "file": path,
        }

    if exclude_content_changed:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(next_content)
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "error": f"AZ game exclude ips write failed: {exc}",
                "changed": False,
                "enabled": bool(normalized_keys),
                "selected_provider_keys": normalized_keys,
            "selected_game_keys": normalized_keys,
                "file": path,
            }

    return {
        "success": True,
        "changed": True,
        "enabled": bool(normalized_keys),
        "selected_game_keys": normalized_keys,
        "selected_game_count": len(selected_titles),
        "domain_count": len(selected_domains),
        "cidr_count": cidr_count,
        "original_cidr_count": int(overlap_summary.get("original_cidr_count") or cidr_count),
        "unresolved_domain_count": len(unresolved_domains),
        "overlap_summary": overlap_summary,
        "include_patches_applied": int(patch_result.get("files_patched") or 0),
        "file": path,
    }


def sync_game_hosts_filter(
    include_game_hosts=False,
    include_game_keys=None,
    include_provider_keys=None,
    include_game_domains=False,
):
    selected_provider_keys = _resolve_provider_filter_selection(
        include_provider_keys=include_provider_keys,
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    hosts_sync_result = _sync_games_include_hosts(
        selected_provider_keys,
        include_game_domains=bool(include_game_domains),
    )
    if not hosts_sync_result.get("success"):
        return {
            "success": False,
            "message": "Не удалось синхронизировать AZ-Game-include-hosts",
            "game_hosts_filter": hosts_sync_result,
        }

    ips_sync_result = _sync_games_include_ips(selected_provider_keys)
    if not ips_sync_result.get("success"):
        return {
            "success": False,
            "message": "Не удалось синхронизировать AZ-Game-include-ips",
            "game_hosts_filter": hosts_sync_result,
            "game_ips_filter": ips_sync_result,
        }

    selected_count = int(ips_sync_result.get("selected_game_count") or 0)
    domain_count = int(hosts_sync_result.get("domain_count") or 0)
    cidr_count = int(ips_sync_result.get("cidr_count") or 0)
    original_cidr_count = int(ips_sync_result.get("original_cidr_count") or cidr_count)
    overlap_summary = ips_sync_result.get("overlap_summary") or {}
    fully_covered = int(overlap_summary.get("fully_covered_count") or 0)
    partial_trimmed = int(overlap_summary.get("partial_trimmed_count") or 0)
    if selected_count > 0:
        message = (
            f"Игровой фильтр синхронизирован в AZ-файлы: {selected_count} провайдеров, "
            f"{domain_count} доменов, {cidr_count} CIDR"
        )
        if original_cidr_count > cidr_count:
            message += f" (из {original_cidr_count} исходных)"
        if fully_covered > 0:
            message += f", уже через VPN: {fully_covered}"
        if partial_trimmed > 0:
            message += f", частично обрезано: {partial_trimmed}"
    else:
        message = "Игровой фильтр очищен из AZ-Game-include-hosts/AZ-Game-include-ips"

    return {
        "success": True,
        "message": message,
        "changed": bool(hosts_sync_result.get("changed") or ips_sync_result.get("changed")),
        "game_hosts_filter": hosts_sync_result,
        "game_ips_filter": ips_sync_result,
    }


def sync_game_exclude_filter(
    include_game_hosts=False,
    include_game_keys=None,
    include_provider_keys=None,
    include_game_domains=False,
):
    selected_provider_keys = _resolve_provider_filter_selection(
        include_provider_keys=include_provider_keys,
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    hosts_sync_result = _sync_games_exclude_hosts(
        selected_provider_keys,
        include_game_domains=bool(include_game_domains),
    )
    if not hosts_sync_result.get("success"):
        return {
            "success": False,
            "message": "Не удалось синхронизировать AZ-Game-exclude-hosts",
            "game_hosts_filter": hosts_sync_result,
        }

    ips_sync_result = _sync_games_exclude_ips(selected_provider_keys)
    if not ips_sync_result.get("success"):
        return {
            "success": False,
            "message": "Не удалось синхронизировать AZ-Game-exclude-ips",
            "game_hosts_filter": hosts_sync_result,
            "game_ips_filter": ips_sync_result,
        }

    selected_count = int(ips_sync_result.get("selected_game_count") or 0)
    domain_count = int(hosts_sync_result.get("domain_count") or 0)
    cidr_count = int(ips_sync_result.get("cidr_count") or 0)
    original_cidr_count = int(ips_sync_result.get("original_cidr_count") or cidr_count)
    overlap_summary = ips_sync_result.get("overlap_summary") or {}
    include_patches_count = int(overlap_summary.get("include_patches_count") or 0)
    include_patches_applied = int(ips_sync_result.get("include_patches_applied") or 0)
    if selected_count > 0:
        message = (
            f"Игровой EXCLUDE синхронизирован в AZ-файлы: {selected_count} провайдеров, "
            f"{domain_count} доменов, {cidr_count} CIDR"
        )
        if original_cidr_count > cidr_count:
            message += f" (из {original_cidr_count} исходных)"
        if include_patches_applied > 0 or include_patches_count > 0:
            message += (
                f", разбито include-сетей: {include_patches_applied or include_patches_count}"
            )
        message += f", добавлено exclude-маршрутов: {cidr_count}"
    else:
        message = "Игровой EXCLUDE очищен из AZ-Game-exclude-hosts/AZ-Game-exclude-ips"

    return {
        "success": True,
        "message": message,
        "changed": bool(hosts_sync_result.get("changed") or ips_sync_result.get("changed")),
        "game_hosts_filter": hosts_sync_result,
        "game_ips_filter": ips_sync_result,
    }


def sync_game_routes_filter(
    include_game_keys=None,
    exclude_game_keys=None,
    include_provider_keys=None,
    exclude_provider_keys=None,
    include_game_domains=False,
):
    include_result = sync_game_hosts_filter(
        include_provider_keys=include_provider_keys,
        include_game_keys=include_game_keys,
        include_game_domains=bool(include_game_domains),
    )
    exclude_result = sync_game_exclude_filter(
        include_provider_keys=exclude_provider_keys,
        include_game_keys=exclude_game_keys,
        include_game_domains=bool(include_game_domains),
    )
    success = bool(include_result.get("success")) and bool(exclude_result.get("success"))
    include_ips = include_result.get("game_ips_filter") or {}
    exclude_ips = exclude_result.get("game_ips_filter") or {}
    include_hosts = include_result.get("game_hosts_filter") or {}
    exclude_hosts = exclude_result.get("game_hosts_filter") or {}
    include_changed = bool(include_hosts.get("changed") or include_ips.get("changed"))
    exclude_changed = bool(exclude_hosts.get("changed") or exclude_ips.get("changed"))
    if not success:
        message = include_result.get("message") or exclude_result.get("message") or "Не удалось синхронизировать игровые маршруты"
    elif include_changed or exclude_changed:
        message = "Игровые маршруты синхронизированы"
    else:
        message = "Игровые маршруты без изменений"
    return {
        "success": success,
        "message": message,
        "changed": include_changed or exclude_changed,
        "include_changed": include_changed,
        "exclude_changed": exclude_changed,
        "include_result": include_result,
        "exclude_result": exclude_result,
        "game_hosts_filter": include_hosts,
        "game_ips_filter": include_ips,
        "game_exclude_hosts_filter": exclude_hosts,
        "game_exclude_ips_filter": exclude_ips,
    }

