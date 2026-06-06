"""Каталог игровых/провайдерских фильтров и нормализация ключей выбора.

Вынесено из core/services/cidr/games.py: чистая часть «каталог + выбор»
(производные поля, список регионов/игр/провайдеров, валидация и нормализация
ключей). Не зависит от ASN-загрузки, overlap-индекса и записи файлов — это
остаётся в games.py. games.py реэкспортирует все имена отсюда, поэтому
существующие импорты (cidr/__init__, cidr_list_updater и тесты) не меняются.
"""

import re

from config.antizapret_params import IP_FILES
from core.services.cidr.constants import SOURCE_FORMATS_WITH_GEO
from core.services.cidr.facade_compat import get_attr as _cfg
from core.services.cidr.parsers import _normalize_cidrs
from core.services.cidr.provider_sources import (
    GAME_FILTER_ALIASES,
    GAME_FILTER_BY_KEY,
    GAME_FILTER_CATALOG,
)


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
