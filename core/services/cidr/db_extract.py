"""Чистые функции парсинга CIDR/ASN из ответов провайдеров.

Вынесено из core/services/cidr/db_service.py, чтобы отделить разбор форматов
(AWS/Google/RIPE/bgp.tools/cidr-text) и извлечение ASN от сервисного класса
CidrDbUpdaterService, работающего с БД. Функции не зависят от моделей БД и
не имеют побочных эффектов. Имена сохранены 1:1 — db_service реэкспортирует их.
"""

import json
import re
from urllib.parse import parse_qs, urlparse

from core.services.cidr.parsers import _extract_bgp_tools_ipv4, _normalize_single_cidr

ASN_TOKEN_PATTERN = re.compile(r"\bAS(\d{1,10})\b", re.IGNORECASE)
SOURCE_NAME_ASN_PATTERN = re.compile(r"(?:^|[^0-9])as(\d{1,10})(?:[^0-9]|$)", re.IGNORECASE)


def _normalize_country_code(raw):
    if not raw:
        return None
    code = str(raw).strip().upper()
    return code if len(code) == 2 else None


def _normalize_asn(value):
    if value is None:
        return None
    raw = str(value).strip().upper()
    if raw.startswith("AS"):
        raw = raw[2:]
    if not raw.isdigit():
        return None
    asn = int(raw)
    if asn <= 0:
        return None
    return asn


def _extract_asns_from_url(url):
    asns = set()
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return asns

    query = parse_qs(parsed.query)
    for raw in query.get("resource", []):
        asn = _normalize_asn(raw)
        if asn is not None:
            asns.add(asn)

    for token in ASN_TOKEN_PATTERN.findall(parsed.path or ""):
        asn = _normalize_asn(token)
        if asn is not None:
            asns.add(asn)

    return asns


def _extract_asns_from_source_name(name):
    asns = set()
    for token in SOURCE_NAME_ASN_PATTERN.findall(str(name or "")):
        asn = _normalize_asn(token)
        if asn is not None:
            asns.add(asn)
    return asns


def _extract_asns_from_text(text_data):
    asns = set()
    for token in ASN_TOKEN_PATTERN.findall(str(text_data or "")):
        asn = _normalize_asn(token)
        if asn is not None:
            asns.add(asn)
    return asns


def _extract_asns_from_sources(sources):
    """Collect ASNs explicitly referenced in provider source names and URLs."""
    asns = set()
    for source in sources or []:
        asns.update(_extract_asns_from_source_name(source.get("name")))
        asns.update(_extract_asns_from_url(source.get("url")))
    return asns


# ──────────────────────────────────────────────────────────────────────
# Core extraction: returns list of dicts with cidr + geo metadata
# ──────────────────────────────────────────────────────────────────────

def _extract_cidrs_with_meta(text_data, source_format):
    """Parse provider data and return list of {cidr, region, countries}."""
    items = []

    if source_format == "cidr_text":
        for line in text_data.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cidr = _normalize_single_cidr(line)
            if cidr:
                items.append({"cidr": cidr, "region": None, "countries": None})
        return items

    if source_format == "cidr_text_scan":
        candidates = _extract_bgp_tools_ipv4(text_data)
        seen = set()
        for raw in candidates:
            cidr = _normalize_single_cidr(raw)
            if cidr and cidr not in seen:
                seen.add(cidr)
                items.append({"cidr": cidr, "region": None, "countries": None})
        return items

    parsed = json.loads(text_data)

    if source_format == "aws_json":
        for prefix in parsed.get("prefixes") or []:
            if not isinstance(prefix, dict):
                continue
            cidr = _normalize_single_cidr(prefix.get("ip_prefix"))
            if cidr:
                items.append({
                    "cidr": cidr,
                    "region": prefix.get("region") or None,
                    "countries": None,
                })
        return items

    if source_format == "google_json":
        for prefix in parsed.get("prefixes") or []:
            if not isinstance(prefix, dict):
                continue
            cidr = _normalize_single_cidr(prefix.get("ipv4Prefix"))
            if cidr:
                items.append({
                    "cidr": cidr,
                    "region": prefix.get("scope") or None,
                    "countries": None,
                })
        return items

    if source_format == "ripe_geo_json":
        data = parsed.get("data") or {}
        resource_country_map = {}
        for item in data.get("located_resources") or []:
            if not isinstance(item, dict):
                continue
            for location in item.get("locations") or []:
                if not isinstance(location, dict):
                    continue
                cc = _normalize_country_code(location.get("country"))
                for resource in location.get("resources") or []:
                    prefix = str(resource or "").strip()
                    if prefix:
                        country_set = resource_country_map.setdefault(prefix, set())
                        if cc:
                            country_set.add(cc)
        for raw_cidr, countries in resource_country_map.items():
            cidr = _normalize_single_cidr(raw_cidr)
            if cidr:
                items.append({
                    "cidr": cidr,
                    "region": None,
                    "countries": sorted(countries) if countries else None,
                })
        return items

    if source_format == "ripe_json":
        data = parsed.get("data") or {}
        for prefix_item in data.get("prefixes") or []:
            if not isinstance(prefix_item, dict):
                continue
            cidr = _normalize_single_cidr(prefix_item.get("prefix"))
            if cidr:
                items.append({"cidr": cidr, "region": None, "countries": None})
        return items

    if source_format == "ripe_bgp_state_json":
        data = parsed.get("data") or {}
        seen = set()
        for state_item in data.get("bgp_state") or []:
            if not isinstance(state_item, dict):
                continue
            cidr = _normalize_single_cidr(state_item.get("target_prefix"))
            if not cidr or cidr in seen:
                continue
            seen.add(cidr)
            items.append({"cidr": cidr, "region": None, "countries": None})
        return items

    raise ValueError(f"Unsupported source format: {source_format}")
