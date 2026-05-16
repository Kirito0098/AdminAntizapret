"""CIDR parsing and normalization."""
import ipaddress
import json
import re
from datetime import datetime, timezone

from core.services.cidr.constants import (
    CIDR_V4_SCAN_PATTERN,
    _BGP_TOOLS_RAW_ALLOC_IPV4_PATTERN,
)
def _normalize_cidrs(values):
    cidrs = set()
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if network.version != 4:
            continue
        if network.prefixlen == 0:
            continue
        cidrs.add(str(network))
    return sorted(cidrs)

def _normalize_single_cidr(raw):
    normalized = _normalize_cidrs([raw])
    return normalized[0] if normalized else None


def _extract_bgp_tools_ipv4(text_data):
    """BGP.tools scan with full-page fallback (DB pipeline — no geo filter)."""
    raw = text_data or ""
    lowered = raw.lower()
    raw_marker = lowered.find("raw allocations")
    if raw_marker < 0:
        return CIDR_V4_SCAN_PATTERN.findall(raw)

    additional_links_marker = lowered.find("additional links", raw_marker)
    scoped = raw[raw_marker:additional_links_marker] if additional_links_marker > raw_marker else raw[raw_marker:]

    candidates = []
    for match in _BGP_TOOLS_RAW_ALLOC_IPV4_PATTERN.finditer(scoped):
        block = match.group(1)
        if block:
            candidates.extend(CIDR_V4_SCAN_PATTERN.findall(block))
    return candidates


def _extract_bgp_tools_raw_alloc_ipv4(text_data):
    raw = text_data or ""
    if not raw:
        return []

    lowered = raw.lower()
    raw_marker = lowered.find("raw allocations")
    if raw_marker < 0:
        return []

    additional_links_marker = lowered.find("additional links", raw_marker)
    if additional_links_marker > raw_marker:
        scoped = raw[raw_marker:additional_links_marker]
    else:
        scoped = raw[raw_marker:]

    cidr_candidates = []
    for match in _BGP_TOOLS_RAW_ALLOC_IPV4_PATTERN.finditer(scoped):
        block = match.group(1)
        if not block:
            continue
        cidr_candidates.extend(CIDR_V4_SCAN_PATTERN.findall(block))
    return cidr_candidates

def _extract_cidrs(text_data, source_format, region_scopes=None, strict_geo_filter=False):
    from core.services.cidr.geo import (
        _is_strict_geo_country_set,
        _matches_country_scope,
        _matches_region_scope,
        _matches_strict_scope_value,
        _normalize_country_code,
        _normalize_region_scopes,
    )

    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    if source_format == "cidr_text":
        if not is_all_scope:
            return []

        cidr_candidates = []
        for line in text_data.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cidr_candidates.append(line)
        return _normalize_cidrs(cidr_candidates)

    if source_format == "cidr_text_scan":
        if not is_all_scope:
            return []

        cidr_candidates = _extract_bgp_tools_raw_alloc_ipv4(text_data)
        if not cidr_candidates:
            cidr_candidates = CIDR_V4_SCAN_PATTERN.findall(text_data or "")
        return _normalize_cidrs(cidr_candidates)

    parsed = json.loads(text_data)

    if source_format == "aws_json":
        prefixes = parsed.get("prefixes") or []
        cidr_candidates = []
        for item in prefixes:
            if not isinstance(item, dict):
                continue
            if not _matches_region_scope(item.get("region"), normalized_scopes):
                continue
            if strict_geo_filter and not _matches_strict_scope_value(item.get("region"), normalized_scopes):
                continue
            cidr_candidates.append(item.get("ip_prefix"))
        return _normalize_cidrs(cidr_candidates)

    if source_format == "google_json":
        prefixes = parsed.get("prefixes") or []
        cidr_candidates = []
        for item in prefixes:
            if not isinstance(item, dict):
                continue
            if not _matches_region_scope(item.get("scope"), normalized_scopes):
                continue
            if strict_geo_filter and not _matches_strict_scope_value(item.get("scope"), normalized_scopes):
                continue
            v4_prefix = item.get("ipv4Prefix")
            if v4_prefix:
                cidr_candidates.append(v4_prefix)
        return _normalize_cidrs(cidr_candidates)

    if source_format == "ripe_geo_json":
        data = parsed.get("data") or {}
        located_resources = data.get("located_resources") or []
        resource_country_map = {}

        for item in located_resources:
            if not isinstance(item, dict):
                continue
            locations = item.get("locations") or []
            for location in locations:
                if not isinstance(location, dict):
                    continue
                country_code = _normalize_country_code(location.get("country"))
                resources = location.get("resources") or []
                if not resources:
                    continue

                for resource in resources:
                    prefix = str(resource or "").strip()
                    if not prefix:
                        continue
                    country_set = resource_country_map.setdefault(prefix, set())
                    if country_code:
                        country_set.add(country_code)

        cidr_candidates = []
        for resource, countries in resource_country_map.items():
            if strict_geo_filter and not is_all_scope and not _is_strict_geo_country_set(countries):
                continue

            if not countries:
                continue

            if any(_matches_country_scope(code, normalized_scopes) for code in countries):
                cidr_candidates.append(resource)

        return _normalize_cidrs(cidr_candidates)

    if source_format == "ripe_json":
        if not is_all_scope:
            return []

        data = parsed.get("data") or {}
        prefixes = data.get("prefixes") or []
        cidr_candidates = [item.get("prefix") for item in prefixes if isinstance(item, dict)]
        return _normalize_cidrs(cidr_candidates)

    raise ValueError(f"Unsupported source format: {source_format}")

def _render_file_content(file_name, cidrs, source_name):
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    # Агрегируем смежные/поглощённые блоки перед записью
    try:
        parsed = [ipaddress.ip_network(c, strict=False) for c in cidrs if c]
        aggregated = [str(n) for n in ipaddress.collapse_addresses(parsed)]
    except Exception:
        aggregated = list(cidrs)
    lines = [
        f"# Auto-generated CIDR list for {file_name}",
        f"# Source: {source_name}",
        f"# Generated at: {generated_at}",
        "",
    ]
    lines.extend(aggregated)
    return "\n".join(lines) + "\n"

