"""Game filter catalog sync for include-hosts/include-ips."""
import json
import logging
import os
import re
import socket

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
        }
        for item in GAME_FILTER_CATALOG
    ]

def get_saved_game_keys():
    """Read the Keys comment from include-hosts or include-ips block and return saved publisher keys."""
    keys_pattern = re.compile(
        r"# BEGIN AdminAntizapret CIDR games.*?\n# Keys: ([^\n]+)",
        re.DOTALL,
    )
    for filepath in (_cfg("GAME_INCLUDE_HOSTS_FILE"), _cfg("GAME_INCLUDE_IPS_FILE")):
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue
        m = keys_pattern.search(content)
        if m:
            raw = m.group(1).strip()
            found = _normalize_game_filter_keys([k.strip() for k in raw.split(",") if k.strip()])
            if found:
                return found
    return []

def _normalize_game_filter_keys(raw_keys):
    if raw_keys is None:
        return []

    values = raw_keys
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]

    selected = set()
    for value in values:
        token = str(value or "").strip().lower()
        if not token:
            continue
        token = GAME_FILTER_ALIASES.get(token, token)
        if token in GAME_FILTER_BY_KEY:
            selected.add(token)

    if not selected:
        return []

    return [item["key"] for item in GAME_FILTER_CATALOG if item["key"] in selected]

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
        except socket.gaierror:
            unresolved.append(raw_domain)
            continue
        except OSError:
            unresolved.append(raw_domain)
            continue

        if not ipv4_addresses:
            unresolved.append(raw_domain)
            continue

        for address in sorted(ipv4_addresses):
            cidr_values.append(f"{address}/32")

    return _normalize_cidrs(cidr_values), sorted(set(unresolved))

def _fetch_game_asn_cidrs(asns):
    """Query RIPE stat.ripe.net API live for announced IPv4 prefixes of each ASN.

    Each call makes one HTTP request per ASN to:
      https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS<N>

    Results are NOT cached — every invocation hits RIPE directly.
    For games without a dedicated AS, use DNS fallback via _resolve_game_domains_ipv4_cidrs().

    Returns (cidrs, source_labels, errors).
    """
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
                if ":" not in str(p.get("prefix") or "")  # skip IPv6
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

def _render_games_filter_block(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    selected_titles, selected_domains = _collect_game_domains(normalized_keys)
    if not selected_domains:
        return "", selected_titles, selected_domains

    lines = [GAME_FILTER_BLOCK_START]
    lines.append(f"# Keys: {','.join(normalized_keys)}")
    lines.append(f"# Selected games ({len(selected_titles)}): {', '.join(selected_titles)}")
    lines.extend(selected_domains)
    lines.append(GAME_FILTER_BLOCK_END)
    return "\n".join(lines), selected_titles, selected_domains

def _render_games_ips_block(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    if not normalized_keys:
        return "", [], [], [], []

    titles = []
    all_cidrs = set()
    source_labels = []
    dns_fallback_domains = []
    unresolved_domains = []

    for key in normalized_keys:
        item = GAME_FILTER_BY_KEY.get(key)
        if not item:
            continue
        titles.append(item["title"])
        asns = item.get("asns") or []
        domains = item.get("domains") or []

        if asns:
            cidrs, labels, errors = _fetch_game_asn_cidrs(asns)
            if cidrs:
                all_cidrs.update(cidrs)
                source_labels.extend(labels)
                continue
            if errors:
                logger.warning("Game ASN fetch errors for %s: %s", key, errors)

        # DNS fallback for games without own AS or when ASN fetch failed
        dns_fallback_domains.extend(domains)

    if dns_fallback_domains:
        dns_cidrs, unresolved = _facade_call(
            "_resolve_game_domains_ipv4_cidrs",
            list(dict.fromkeys(dns_fallback_domains)),
        )
        all_cidrs.update(dns_cidrs)
        unresolved_domains = unresolved

    selected_cidrs = _normalize_cidrs(sorted(all_cidrs))
    selected_domains = list(dict.fromkeys(
        d for key in normalized_keys
        for d in (GAME_FILTER_BY_KEY.get(key) or {}).get("domains", [])
    ))

    if not selected_cidrs:
        return "", titles, selected_domains, [], unresolved_domains

    lines = [GAME_FILTER_IP_BLOCK_START]
    lines.append(f"# Keys: {','.join(normalized_keys)}")
    lines.append(f"# Selected games ({len(titles)}): {', '.join(titles)}")
    if source_labels:
        lines.append(f"# Sources (ASN via RIPE): {', '.join(source_labels)}")
    if dns_fallback_domains:
        resolved_count = len(list(dict.fromkeys(dns_fallback_domains))) - len(unresolved_domains)
        lines.append(f"# DNS-resolved domains: {resolved_count}/{len(list(dict.fromkeys(dns_fallback_domains)))}")
    if unresolved_domains:
        preview = ", ".join(unresolved_domains[:10])
        if len(unresolved_domains) > 10:
            preview = f"{preview}, ..."
        lines.append(f"# Unresolved ({len(unresolved_domains)}): {preview}")
    lines.extend(selected_cidrs)
    lines.append(GAME_FILTER_IP_BLOCK_END)
    return "\n".join(lines), titles, selected_domains, selected_cidrs, unresolved_domains

def _sync_games_include_hosts(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    try:
        with open(_cfg("GAME_INCLUDE_HOSTS_FILE"), "r", encoding="utf-8") as handle:
            current_content = handle.read()
    except FileNotFoundError:
        current_content = ""
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"include-hosts read failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_game_keys": normalized_keys,
        }

    cleaned = _strip_games_filter_block(current_content).strip()
    if normalized_keys:
        block, selected_titles, selected_domains = _render_games_filter_block(normalized_keys)
        next_content = f"{cleaned}\n\n{block}\n" if cleaned else f"{block}\n"
    else:
        selected_titles, selected_domains = [], []
        next_content = f"{cleaned}\n" if cleaned else ""

    if next_content == current_content:
        return {
            "success": True,
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_game_keys": normalized_keys,
            "selected_game_count": len(selected_titles),
            "domain_count": len(selected_domains),
            "file": _cfg("GAME_INCLUDE_HOSTS_FILE"),
        }

    try:
        os.makedirs(os.path.dirname(_cfg("GAME_INCLUDE_HOSTS_FILE")), exist_ok=True)
        with open(_cfg("GAME_INCLUDE_HOSTS_FILE"), "w", encoding="utf-8") as handle:
            handle.write(next_content)
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"include-hosts write failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_game_keys": normalized_keys,
        }

    return {
        "success": True,
        "changed": True,
        "enabled": bool(normalized_keys),
        "selected_game_keys": normalized_keys,
        "selected_game_count": len(selected_titles),
        "file": _cfg("GAME_INCLUDE_HOSTS_FILE"),
        "domain_count": len(selected_domains),
    }

def _sync_games_include_ips(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    try:
        with open(_cfg("GAME_INCLUDE_IPS_FILE"), "r", encoding="utf-8") as handle:
            current_content = handle.read()
    except FileNotFoundError:
        current_content = ""
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"include-ips read failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_game_keys": normalized_keys,
        }

    cleaned = _strip_games_filter_ips_block(current_content).strip()
    if normalized_keys:
        block, selected_titles, selected_domains, selected_cidrs, unresolved_domains = _render_games_ips_block(normalized_keys)
        next_content = f"{cleaned}\n\n{block}\n" if block and cleaned else (f"{block}\n" if block else (f"{cleaned}\n" if cleaned else ""))
    else:
        selected_titles, selected_domains, selected_cidrs, unresolved_domains = [], [], [], []
        next_content = f"{cleaned}\n" if cleaned else ""

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
            "file": _cfg("GAME_INCLUDE_IPS_FILE"),
        }

    try:
        os.makedirs(os.path.dirname(_cfg("GAME_INCLUDE_IPS_FILE")), exist_ok=True)
        with open(_cfg("GAME_INCLUDE_IPS_FILE"), "w", encoding="utf-8") as handle:
            handle.write(next_content)
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"include-ips write failed: {exc}",
            "changed": False,
            "enabled": bool(normalized_keys),
            "selected_game_keys": normalized_keys,
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
        "file": _cfg("GAME_INCLUDE_IPS_FILE"),
    }

def sync_game_hosts_filter(include_game_hosts=False, include_game_keys=None):
    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    hosts_sync_result = _sync_games_include_hosts(selected_game_keys)
    if not hosts_sync_result.get("success"):
        return {
            "success": False,
            "message": "Не удалось синхронизировать include-hosts",
            "game_hosts_filter": hosts_sync_result,
        }

    ips_sync_result = _sync_games_include_ips(selected_game_keys)
    if not ips_sync_result.get("success"):
        return {
            "success": False,
            "message": "Не удалось синхронизировать include-ips",
            "game_hosts_filter": hosts_sync_result,
            "game_ips_filter": ips_sync_result,
        }

    selected_count = int(hosts_sync_result.get("selected_game_count") or 0)
    domain_count = int(hosts_sync_result.get("domain_count") or 0)
    cidr_count = int(ips_sync_result.get("cidr_count") or 0)
    if selected_count > 0:
        message = (
            f"Игровой фильтр синхронизирован: {selected_count} игр, "
            f"{domain_count} доменов, {cidr_count} CIDR"
        )
    else:
        message = "Игровой фильтр очищен из include-hosts/include-ips"

    return {
        "success": True,
        "message": message,
        "game_hosts_filter": hosts_sync_result,
        "game_ips_filter": ips_sync_result,
    }

