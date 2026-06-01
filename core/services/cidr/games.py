"""Game filter catalog sync for dedicated AZ-Game include files."""
import ipaddress
import json
import logging
import os
import re
import socket
from bisect import bisect_right

from config.antizapret_params import IP_FILES
from core.services.cidr.constants import (
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


def _derive_game_tags(item):
    tags = []
    asn_count = len((item or {}).get("asns") or [])
    tags.append("asn" if asn_count > 0 else "dns")
    provider = _derive_game_provider(item).strip().lower().replace(" ", "_")
    if provider:
        tags.append(f"provider:{provider}")
    return tags


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
            "source_type": "asn" if len(item.get("asns") or []) > 0 else "dns",
            "provider": _derive_game_provider(item),
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


def _resolve_game_filter_selection(include_game_keys=None, include_game_hosts=False):
    normalized_keys = _normalize_game_filter_keys(include_game_keys)
    if normalized_keys:
        return normalized_keys
    if include_game_hosts:
        return [item["key"] for item in GAME_FILTER_CATALOG]
    return []


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


def _fetch_game_asn_cidrs(asns):
    all_cidrs = set()
    labels = []
    errors = []
    for asn in (asns or []):
        asn_int = int(asn)
        url = f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn_int}"
        try:
            text = _facade_call("_download_text", url)
            data = json.loads(text)
            prefixes = data.get("data", {}).get("prefixes") or []
            ipv4 = [
                str(p.get("prefix") or "").strip()
                for p in prefixes
                if ":" not in str(p.get("prefix") or "")
            ]
            ipv4 = [p for p in ipv4 if p]
            if ipv4:
                all_cidrs.update(ipv4)
                labels.append(f"ripe-AS{asn_int}({len(ipv4)})")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"AS{asn_int}: {exc}")
    return _normalize_cidrs(sorted(all_cidrs)), labels, errors


def _strip_games_filter_block(content):
    text = str(content or "")
    pattern = re.compile(
        rf"\n?{re.escape(GAME_FILTER_BLOCK_START)}\n.*?\n{re.escape(GAME_FILTER_BLOCK_END)}\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text)


def _strip_games_filter_ips_block(content):
    text = str(content or "")
    pattern = re.compile(
        rf"\n?{re.escape(GAME_FILTER_IP_BLOCK_START)}\n.*?\n{re.escape(GAME_FILTER_IP_BLOCK_END)}\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text)


def _render_games_filter_block(selected_game_keys, include_game_domains=False):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    selected_titles, selected_domains = _collect_game_domains(normalized_keys)
    if not include_game_domains or not selected_domains:
        return "", selected_titles, (selected_domains if include_game_domains else [])
    lines = [GAME_FILTER_BLOCK_START]
    lines.append(f"# Keys: {','.join(normalized_keys)}")
    lines.append(f"# Selected games ({len(selected_titles)}): {', '.join(selected_titles)}")
    lines.extend(selected_domains)
    lines.append(GAME_FILTER_BLOCK_END)
    return "\n".join(lines), selected_titles, selected_domains


def _render_games_ips_block(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    if not normalized_keys:
        return "", [], [], [], [], {}
    titles = []
    all_cidrs = set()
    source_labels = []
    dns_fallback_domains = []
    unresolved_domains = []
    per_game_cidrs = {}
    for key in normalized_keys:
        item = GAME_FILTER_BY_KEY.get(key)
        if not item:
            continue
        titles.append(item["title"])
        asns = item.get("asns") or []
        domains = item.get("domains") or []
        key_cidrs = set()
        key_had_asn_data = False
        if asns:
            cidrs, labels, errors = _fetch_game_asn_cidrs(asns)
            if cidrs:
                key_cidrs.update(cidrs)
                source_labels.extend(labels)
                key_had_asn_data = True
            if errors:
                logger.warning("Game ASN fetch errors for %s: %s", key, errors)
        if not key_had_asn_data and domains:
            dns_fallback_domains.extend(domains)
            dns_cidrs, unresolved = _facade_call(
                "_resolve_game_domains_ipv4_cidrs",
                list(dict.fromkeys(domains)),
            )
            key_cidrs.update(dns_cidrs)
            unresolved_domains.extend(unresolved)
        normalized_key_cidrs = _normalize_cidrs(sorted(key_cidrs))
        per_game_cidrs[key] = normalized_key_cidrs
        all_cidrs.update(normalized_key_cidrs)
    selected_cidrs = _normalize_cidrs(sorted(all_cidrs))
    unresolved_domains = sorted(set(unresolved_domains))
    selected_domains = list(dict.fromkeys(
        d for key in normalized_keys
        for d in (GAME_FILTER_BY_KEY.get(key) or {}).get("domains", [])
    ))
    if not selected_cidrs:
        return "", titles, selected_domains, [], unresolved_domains, per_game_cidrs
    lines = [GAME_FILTER_IP_BLOCK_START]
    lines.append(f"# Keys: {','.join(normalized_keys)}")
    lines.append(f"# Selected games ({len(titles)}): {', '.join(titles)}")
    if source_labels:
        lines.append(f"# Sources (ASN via RIPE): {', '.join(source_labels)}")
    if dns_fallback_domains:
        unique_domains = len(list(dict.fromkeys(dns_fallback_domains)))
        resolved_count = unique_domains - len(unresolved_domains)
        lines.append(f"# DNS-resolved domains: {resolved_count}/{unique_domains}")
    if unresolved_domains:
        preview = ", ".join(unresolved_domains[:10])
        if len(unresolved_domains) > 10:
            preview = f"{preview}, ..."
        lines.append(f"# Unresolved ({len(unresolved_domains)}): {preview}")
    lines.extend(selected_cidrs)
    lines.append(GAME_FILTER_IP_BLOCK_END)
    return "\n".join(lines), titles, selected_domains, selected_cidrs, unresolved_domains, per_game_cidrs


def _iter_overlap_source_files():
    files = set()
    list_dir = str(_cfg("LIST_DIR") or "").strip()
    if list_dir and os.path.isdir(list_dir):
        for name in os.listdir(list_dir):
            path = os.path.join(list_dir, name)
            if not os.path.isfile(path) or not name.endswith(".txt"):
                continue
            files.add(path)

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


def _build_overlap_index():
    entries = []
    for path in _iter_overlap_source_files():
        entries.extend(_extract_cidr_entries_from_file(path))
    entries.sort(key=lambda item: item["start"])
    starts = [entry["start"] for entry in entries]
    return entries, starts


def _collect_overlap_summary(candidate_cidrs, selected_game_keys=None, _overlap_index=None):
    if _overlap_index is not None:
        entries, starts = _overlap_index
    else:
        entries, starts = _build_overlap_index()
    if not entries or not candidate_cidrs:
        return {
            "overlap_count": 0,
            "overlap_game_keys_count": 0,
            "overlap_examples": [],
        }
    overlapped_candidates = set()
    overlap_examples = []
    for cidr in candidate_cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        start = int(network.network_address)
        end = int(network.broadcast_address)
        idx = bisect_right(starts, end) - 1
        while idx >= 0:
            item = entries[idx]
            if item["end"] < start:
                break
            if item["start"] <= end and item["end"] >= start:
                overlapped_candidates.add(cidr)
                if len(overlap_examples) < 20:
                    overlap_examples.append(
                        {
                            "game_cidr": cidr,
                            "existing_cidr": item["cidr"],
                            "file": item["file"],
                        }
                    )
                break
            idx -= 1
    return {
        "overlap_count": len(overlapped_candidates),
        "overlap_game_keys_count": len(selected_game_keys or []) if overlapped_candidates else 0,
        "overlap_examples": overlap_examples,
    }


def get_saved_game_keys():
    keys_pattern = re.compile(
        r"# BEGIN AdminAntizapret CIDR games.*?\n# Keys: ([^\n]+)",
        re.DOTALL,
    )
    for filepath in (_cfg("AZ_GAME_INCLUDE_IPS_FILE"), _cfg("AZ_GAME_INCLUDE_HOSTS_FILE")):
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue
        m = keys_pattern.search(content)
        if not m:
            continue
        raw = m.group(1).strip()
        found = _normalize_game_filter_keys([k.strip() for k in raw.split(",") if k.strip()])
        if found:
            return found
    return []


def preview_game_hosts_filter(include_game_hosts=False, include_game_keys=None, include_game_domains=False):
    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    hosts_block, selected_titles, selected_domains = _render_games_filter_block(
        selected_game_keys,
        include_game_domains=bool(include_game_domains),
    )
    ips_block, _, all_domains, selected_cidrs, unresolved_domains, per_game_cidrs = _render_games_ips_block(selected_game_keys)
    overlap_index = _build_overlap_index()
    overlap_summary = _collect_overlap_summary(selected_cidrs, selected_game_keys, _overlap_index=overlap_index)
    per_game_stats = {}
    for key, cidrs in per_game_cidrs.items():
        key_overlap = _collect_overlap_summary(cidrs, [key], _overlap_index=overlap_index)
        per_game_stats[key] = {
            "cidr_count": len(cidrs),
            "overlap_count": int(key_overlap.get("overlap_count") or 0),
        }
    selected_count = len(selected_titles)
    if selected_count > 0:
        message = (
            f"Preview готов: {selected_count} игр, "
            f"{len(selected_domains)} доменов, {len(selected_cidrs)} CIDR"
        )
    else:
        message = "Preview готов: выбранные игровые фильтры отсутствуют"
    if overlap_summary.get("overlap_count"):
        message += f". Найдено пересечений: {overlap_summary.get('overlap_count')}"
    return {
        "success": True,
        "message": message,
        "preview": {
            "enabled": bool(selected_game_keys),
            "selected_game_keys": selected_game_keys,
            "selected_game_count": selected_count,
            "domain_count": len(selected_domains),
            "all_domain_count": len(all_domains),
            "cidr_count": len(selected_cidrs),
            "unresolved_domain_count": len(unresolved_domains),
            "unresolved_domains": unresolved_domains[:50],
            "include_game_domains": bool(include_game_domains),
            "domains_to_add": selected_domains if include_game_domains else [],
            "overlap_summary": overlap_summary,
            "per_game_stats": per_game_stats,
            "host_block_preview": hosts_block.splitlines()[:20] if hosts_block else [],
            "ips_block_preview": ips_block.splitlines()[:20] if ips_block else [],
        },
    }


def _sync_games_include_hosts(selected_game_keys, include_game_domains=False):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
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


def _sync_games_include_ips(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
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
            "selected_game_keys": normalized_keys,
            "file": path,
        }

    cleaned = _strip_games_filter_ips_block(current_content).strip()
    if normalized_keys:
        block, selected_titles, selected_domains, selected_cidrs, unresolved_domains, _ = _render_games_ips_block(normalized_keys)
        next_content = f"{cleaned}\n\n{block}\n" if block and cleaned else (f"{block}\n" if block else (f"{cleaned}\n" if cleaned else ""))
    else:
        selected_titles, selected_domains, selected_cidrs, unresolved_domains = [], [], [], []
        next_content = f"{cleaned}\n" if cleaned else ""

    overlap_summary = _collect_overlap_summary(selected_cidrs, normalized_keys)

    if next_content == current_content:
        return {
            "success": True,
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_game_keys": normalized_keys,
            "selected_game_count": len(selected_titles),
            "domain_count": len(selected_domains),
            "cidr_count": len(selected_cidrs),
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
        "cidr_count": len(selected_cidrs),
        "unresolved_domain_count": len(unresolved_domains),
        "overlap_summary": overlap_summary,
        "file": path,
    }


def sync_game_hosts_filter(include_game_hosts=False, include_game_keys=None, include_game_domains=False):
    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    hosts_sync_result = _sync_games_include_hosts(
        selected_game_keys,
        include_game_domains=bool(include_game_domains),
    )
    if not hosts_sync_result.get("success"):
        return {
            "success": False,
            "message": "Не удалось синхронизировать AZ-Game-include-hosts",
            "game_hosts_filter": hosts_sync_result,
        }

    ips_sync_result = _sync_games_include_ips(selected_game_keys)
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
    overlap_count = int((ips_sync_result.get("overlap_summary") or {}).get("overlap_count") or 0)
    if selected_count > 0:
        message = (
            f"Игровой фильтр синхронизирован в AZ-файлы: {selected_count} игр, "
            f"{domain_count} доменов, {cidr_count} CIDR"
        )
        if overlap_count > 0:
            message += f", пересечений с существующими списками: {overlap_count}"
    else:
        message = "Игровой фильтр очищен из AZ-Game-include-hosts/AZ-Game-include-ips"

    return {
        "success": True,
        "message": message,
        "game_hosts_filter": hosts_sync_result,
        "game_ips_filter": ips_sync_result,
    }

