"""OpenVPN route limit compaction and DPI-aware budgeting."""
import ipaddress
import logging

from config.antizapret_params import IP_FILES
from core.services.cidr.constants import (
    OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS,
    SOURCE_FORMATS_WITH_GEO,
)
from core.services.cidr.facade_compat import call as _facade_call, get_attr as _cfg
from core.services.cidr.geo import _normalize_region_scopes
from core.services.cidr.parsers import _normalize_cidrs

logger = logging.getLogger(__name__)

def _supports_geo_scope(sources):
    return any((src.get("format") in SOURCE_FORMATS_WITH_GEO) for src in (sources or []))

def _collect_cidrs_from_sources(sources, effective_scopes, strict_geo_filter=False):
    merged_cidrs = set()
    source_names = []
    errors = []
    has_non_geo_results = False

    for source in sources:
        source_format = source.get("format")
        if "all" in effective_scopes and has_non_geo_results and source_format in SOURCE_FORMATS_WITH_GEO:
            continue

        try:
            text_data = _facade_call("_download_text", source["url"])
            cidrs = _facade_call(
                "_extract_cidrs",
                text_data,
                source_format,
                effective_scopes,
                strict_geo_filter=strict_geo_filter,
            )
            if not cidrs:
                if "all" not in effective_scopes:
                    joined_scopes = ",".join(effective_scopes)
                    raise ValueError(f"empty cidr payload for region scopes {joined_scopes}")
                raise ValueError("empty cidr payload")

            merged_cidrs.update(cidrs)
            source_names.append(source["name"])
            if source_format not in SOURCE_FORMATS_WITH_GEO:
                has_non_geo_results = True
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    if merged_cidrs:
        return sorted(merged_cidrs), ", ".join(source_names), None

    return [], "", (errors[-1] if errors else "unknown error")

def _has_non_geo_sources(sources):
    return any((src.get("format") not in SOURCE_FORMATS_WITH_GEO) for src in (sources or []))

def _optimize_cidrs_for_openvpn_routes(
    *,
    sources,
    effective_scopes,
    cidrs,
    source_name,
    strict_geo_filter=False,
):
    if not cidrs:
        return cidrs, source_name, None

    scopes = _normalize_region_scopes(effective_scopes)
    if "all" in scopes:
        return cidrs, source_name, None

    if len(cidrs) <= _cfg("OPENVPN_ROUTE_CIDR_LIMIT"):
        return cidrs, source_name, None

    if not _has_non_geo_sources(sources):
        return cidrs, source_name, None

    optimized_cidrs, optimized_source_name, _ = _facade_call(
        "_collect_cidrs_from_sources",
        sources,
        ["all"],
        strict_geo_filter=bool(strict_geo_filter),
    )
    if not optimized_cidrs:
        return cidrs, source_name, None

    if len(optimized_cidrs) >= len(cidrs):
        return cidrs, source_name, None

    optimization_meta = {
        "strategy": "route_limit_non_geo_fallback",
        "original_cidr_count": len(cidrs),
        "optimized_cidr_count": len(optimized_cidrs),
        "scope": ",".join(scopes),
    }
    return optimized_cidrs, f"{optimized_source_name} [route-optimized]", optimization_meta

def _compress_cidrs_to_limit(cidrs, limit):
    normalized = _normalize_cidrs(cidrs)
    if not normalized:
        return [], None

    if limit is None or int(limit) <= 0:
        return [], {
            "strategy": "supernet_compaction",
            "original_cidr_count": len(normalized),
            "compressed_cidr_count": 0,
            "target_limit": 0,
            "aggregation_method": "netaddr",
        }

    target_limit = int(limit)

    try:
        import netaddr
    except ImportError:
        raise RuntimeError("netaddr package is required for CIDR aggregation. Install it with: pip install netaddr")

    # Parse all networks using netaddr for proper handling
    try:
        networks = [netaddr.IPNetwork(value) for value in normalized]
    except (netaddr.AddrFormatError, ValueError) as e:
        logger.warning(f"Failed to parse CIDR blocks with netaddr: {e}. Falling back to ipaddress module.")
        networks = [ipaddress.ip_network(value, strict=False) for value in normalized]

    # Remove redundant CIDRs where one is completely contained within another
    # This is a conservative approach that doesn't merge adjacent blocks
    non_redundant = []
    sorted_networks = sorted(networks, key=lambda n: (int(n.ip), -n.prefixlen))

    for net in sorted_networks:
        is_redundant = False
        for other in non_redundant:
            if net in other:
                # This network is contained in another, skip it
                is_redundant = True
                break
        if not is_redundant:
            # Remove any previously added networks that are now contained in this one
            non_redundant = [n for n in non_redundant if n not in net]
            non_redundant.append(net)

    # If deduplication resulted in redundant entries being removed
    if len(non_redundant) < len(normalized):
        # We had overlaps, return deduplicated
        if len(non_redundant) <= target_limit:
            compressed = [str(net) for net in sorted(non_redundant, key=lambda n: (int(n.ip), n.prefixlen))]
            return compressed, {
                "strategy": "netaddr_deduplicate_overlaps",
                "original_cidr_count": len(normalized),
                "compressed_cidr_count": len(compressed),
                "target_limit": target_limit,
                "aggregation_method": "netaddr",
            }
    else:
        # No overlaps found, return original if within limit
        if len(normalized) <= target_limit:
            return normalized, None

    # At this point we're over limit, need to trim
    # Sort by prefix length (ascending = keep larger blocks first), then by address
    trimmed = sorted(
        non_redundant,
        key=lambda n: (n.prefixlen, int(n.ip)),
    )[:target_limit]

    compressed = [str(net) for net in trimmed]
    return compressed, {
        "strategy": "netaddr_trim_to_limit",
        "original_cidr_count": len(normalized),
        "compressed_cidr_count": len(compressed),
        "target_limit": target_limit,
        "aggregation_method": "netaddr",
        "trimmed_to_limit": True,
    }

def _normalize_dpi_priority_files(values):
    if values is None:
        return []

    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]

    normalized = []
    seen = set()
    for item in values:
        file_name = str(item or "").strip()
        if not file_name or file_name in seen:
            continue
        if file_name not in IP_FILES:
            continue
        normalized.append(file_name)
        seen.add(file_name)
    return normalized

def _normalize_priority_min_budget(value):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return 0

    if parsed <= 0:
        return 0
    return parsed

def _apply_total_route_limit(
    entries,
    total_limit,
    *,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
):
    if not entries:
        return entries, None

    if total_limit is None or int(total_limit) <= 0:
        return entries, None

    route_limit = int(total_limit)
    original_total = sum(len(item.get("cidrs") or []) for item in entries)
    if original_total <= route_limit:
        return entries, None

    non_empty_indices = [index for index, item in enumerate(entries) if item.get("cidrs")]
    if not non_empty_indices:
        return entries, None

    priority_files = set(_normalize_dpi_priority_files(dpi_priority_files))
    mandatory_files = set(_normalize_dpi_priority_files(dpi_mandatory_files))
    priority_files.update(mandatory_files)
    priority_min_budget = _normalize_priority_min_budget(dpi_priority_min_budget)

    if route_limit < len(non_empty_indices):
        prioritized_indices = sorted(
            non_empty_indices,
            key=lambda idx: len(entries[idx].get("cidrs") or []),
            reverse=True,
        )

        if mandatory_files:
            mandatory_first = sorted(
                [
                    idx for idx in non_empty_indices
                    if str(entries[idx].get("file") or "") in mandatory_files
                ],
                key=lambda idx: len(entries[idx].get("cidrs") or []),
                reverse=True,
            )
            fallback_rest = [idx for idx in prioritized_indices if idx not in mandatory_first]
            prioritized_indices = mandatory_first + fallback_rest
        elif priority_files and priority_min_budget > 0:
            priority_first = [
                idx for idx in non_empty_indices
                if str(entries[idx].get("file") or "") in priority_files
            ]
            fallback_rest = [idx for idx in prioritized_indices if idx not in priority_first]
            prioritized_indices = priority_first + fallback_rest

        allowed_indices = set(prioritized_indices[:route_limit])
        adjusted_entries = []
        per_file = []
        for index, entry in enumerate(entries):
            item = dict(entry)
            cidrs = list(item.get("cidrs") or [])
            budget = 1 if index in allowed_indices else 0
            compressed_cidrs, compression_meta = _compress_cidrs_to_limit(cidrs, budget)
            item["cidrs"] = compressed_cidrs
            if compression_meta and compression_meta.get("compressed_cidr_count", len(compressed_cidrs)) < compression_meta.get("original_cidr_count", len(cidrs)):
                item["global_route_optimization"] = compression_meta
            adjusted_entries.append(item)
            per_file.append(
                {
                    "file": item.get("file"),
                    "original_cidr_count": len(cidrs),
                    "compressed_cidr_count": len(compressed_cidrs),
                    "target_budget": budget,
                    "dpi_priority": bool(str(item.get("file") or "") in priority_files),
                    "dpi_mandatory": bool(str(item.get("file") or "") in mandatory_files),
                }
            )

        compressed_total = sum(len(item.get("cidrs") or []) for item in adjusted_entries)
        present_mandatory_files = {
            str(item.get("file") or "")
            for item in adjusted_entries
            if str(item.get("file") or "") in mandatory_files and (item.get("cidrs") or [])
        }
        dropped_mandatory_files = sorted(mandatory_files - present_mandatory_files)
        meta = {
            "strategy": "global_total_route_limit",
            "limit": route_limit,
            "original_total_cidr_count": original_total,
            "compressed_total_cidr_count": compressed_total,
            "files": per_file,
        }
        if mandatory_files:
            meta["dpi_mandatory"] = {
                "enabled": True,
                "mandatory_files": sorted(mandatory_files),
                "dropped_mandatory_files": dropped_mandatory_files,
            }
            if dropped_mandatory_files:
                meta["warning"] = "Не все обязательные detected-провайдеры поместились в лимит"
        return adjusted_entries, meta

    budgets = {index: 0 for index in non_empty_indices}
    reserved_total = 0

    if mandatory_files:
        for index in non_empty_indices:
            file_name = str(entries[index].get("file") or "")
            if file_name not in mandatory_files:
                continue
            current_count = len(entries[index].get("cidrs") or [])
            if current_count <= 0:
                continue
            budgets[index] = max(budgets[index], 1)
            reserved_total += 1

    if reserved_total > route_limit:
        mandatory_indices = [
            idx for idx in non_empty_indices
            if str(entries[idx].get("file") or "") in mandatory_files
        ]
        mandatory_indices = sorted(
            mandatory_indices,
            key=lambda idx: len(entries[idx].get("cidrs") or []),
            reverse=True,
        )
        budgets = {index: 0 for index in non_empty_indices}
        allocated = 0
        for idx in mandatory_indices:
            if allocated >= route_limit:
                break
            budgets[idx] = 1
            allocated += 1
        reserved_total = allocated

    if priority_files and priority_min_budget > 0:
        for index in non_empty_indices:
            file_name = str(entries[index].get("file") or "")
            if file_name not in priority_files:
                continue
            current_count = len(entries[index].get("cidrs") or [])
            reserved = min(current_count, priority_min_budget)
            new_budget = max(budgets[index], reserved)
            reserved_total += max(0, new_budget - budgets[index])
            budgets[index] = new_budget

    if reserved_total > route_limit:
        priority_indices = [
            idx for idx in non_empty_indices
            if str(entries[idx].get("file") or "") in priority_files
        ]
        priority_indices = sorted(
            priority_indices,
            key=lambda idx: len(entries[idx].get("cidrs") or []),
            reverse=True,
        )
        budgets = {index: 0 for index in non_empty_indices}
        allocated = 0
        for idx in priority_indices:
            if allocated >= route_limit:
                break
            budgets[idx] = 1
            allocated += 1
        reserved_total = allocated

    remaining_limit = max(route_limit - reserved_total, 0)
    remaining_capacity = {
        index: max(0, len(entries[index].get("cidrs") or []) - budgets[index])
        for index in non_empty_indices
    }
    total_capacity = sum(remaining_capacity.values())

    raw_shares = {}
    if remaining_limit > 0 and total_capacity > 0:
        for index in non_empty_indices:
            capacity = remaining_capacity[index]
            if capacity <= 0:
                raw_shares[index] = 0.0
                continue
            share = (capacity * remaining_limit) / total_capacity
            raw_shares[index] = share
            budgets[index] += min(capacity, int(share))

        allocated = sum(budgets.values())
        if allocated > route_limit:
            for index, _ in sorted(budgets.items(), key=lambda pair: pair[1], reverse=True):
                while budgets[index] > 0 and allocated > route_limit:
                    budgets[index] -= 1
                    allocated -= 1
                if allocated <= route_limit:
                    break

        if allocated < route_limit:
            for index, _ in sorted(raw_shares.items(), key=lambda pair: pair[1] - int(pair[1]), reverse=True):
                capacity = remaining_capacity.get(index, 0)
                upper_bound = len(entries[index].get("cidrs") or [])
                while budgets[index] < upper_bound and budgets[index] - (upper_bound - capacity) < capacity and allocated < route_limit:
                    budgets[index] += 1
                    allocated += 1
                if allocated >= route_limit:
                    break

    adjusted_entries = []
    per_file = []
    for index, entry in enumerate(entries):
        item = dict(entry)
        cidrs = list(item.get("cidrs") or [])
        budget = budgets.get(index, len(cidrs))
        compressed_cidrs, compression_meta = _compress_cidrs_to_limit(cidrs, budget)
        item["cidrs"] = compressed_cidrs
        if compression_meta and compression_meta.get("compressed_cidr_count", len(compressed_cidrs)) < compression_meta.get("original_cidr_count", len(cidrs)):
            item["global_route_optimization"] = compression_meta
        adjusted_entries.append(item)
        per_file.append(
            {
                "file": item.get("file"),
                "original_cidr_count": len(cidrs),
                "compressed_cidr_count": len(compressed_cidrs),
                "target_budget": budget,
                "dpi_priority": bool(str(item.get("file") or "") in priority_files),
                "dpi_mandatory": bool(str(item.get("file") or "") in mandatory_files),
            }
        )

    compressed_total = sum(len(item.get("cidrs") or []) for item in adjusted_entries)
    present_mandatory_files = {
        str(item.get("file") or "")
        for item in adjusted_entries
        if str(item.get("file") or "") in mandatory_files and (item.get("cidrs") or [])
    }
    dropped_mandatory_files = sorted(mandatory_files - present_mandatory_files)
    meta = {
        "strategy": "global_total_route_limit",
        "limit": route_limit,
        "original_total_cidr_count": original_total,
        "compressed_total_cidr_count": compressed_total,
        "files": per_file,
    }
    if mandatory_files:
        meta["dpi_mandatory"] = {
            "enabled": True,
            "mandatory_files": sorted(mandatory_files),
            "dropped_mandatory_files": dropped_mandatory_files,
        }
        if dropped_mandatory_files:
            meta["warning"] = "Не все обязательные detected-провайдеры поместились в лимит"
    if priority_files and priority_min_budget > 0:
        meta["dpi_priority"] = {
            "enabled": True,
            "priority_files": sorted(priority_files),
            "priority_min_budget": priority_min_budget,
        }
    return adjusted_entries, meta


def clamp_openvpn_route_total_cidr_limit(value, *, default=OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return int(default)
    if parsed <= 0:
        return int(default)
    return min(parsed, OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)


def resolve_openvpn_route_total_cidr_limit(get_env_value):
    raw = str(
        get_env_value(
            "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
            str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS),
        )
        or str(OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)
    ).strip()
    return str(clamp_openvpn_route_total_cidr_limit(raw))

