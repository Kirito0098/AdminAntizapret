"""Region/country geo filtering and RU exclusion."""
import time

from core.services.cidr.constants import (
    RU_COUNTRY_CIDR_CACHE_TTL_SECONDS,
    RU_COUNTRY_CIDR_SOURCE_URL,
    _RU_COUNTRY_CIDR_CACHE,
)
from core.services.cidr.facade_compat import call as _facade_call
from core.services.cidr.parsers import _normalize_cidrs
from core.services.cidr.provider_sources import (
    REGION_SCOPES,
    STRICT_ASIA_PACIFIC_BUCKETS,
    STRICT_GEO_BUCKET_SCOPES,
)

COUNTRY_CODES_BY_SCOPE = {
    "europe": {
        "AD", "AL", "AM", "AT", "AZ", "BA", "BE", "BG", "BY", "CH", "CY", "CZ", "DE", "DK", "EE",
        "ES", "FI", "FO", "FR", "GB", "GE", "GG", "GI", "GR", "HR", "HU", "IE", "IM", "IS", "IT",
        "JE", "KZ", "LI", "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL", "PT",
        "RO", "RS", "RU", "SE", "SI", "SK", "SM", "TR", "UA", "VA", "XK",
    },
    "north-america": {"BM", "CA", "GL", "PM", "US"},
    "central-america": {"BZ", "CR", "GT", "HN", "MX", "NI", "PA", "SV"},
    "south-america": {"AR", "BO", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PE", "PY", "SR", "UY", "VE"},
    "asia-east": {"CN", "HK", "JP", "KP", "KR", "MN", "MO", "TW"},
    "asia-south": {"AF", "BD", "BT", "IN", "IR", "LK", "MV", "NP", "PK"},
    "asia-southeast": {"BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL", "VN"},
    "oceania": {
        "AS", "AU", "CK", "FJ", "FM", "GU", "KI", "MH", "MP", "NC", "NF", "NR", "NU", "NZ", "PF",
        "PG", "PN", "PW", "SB", "TK", "TO", "TV", "VU", "WF", "WS",
    },
    "middle-east": {"AE", "BH", "CY", "EG", "IL", "IQ", "IR", "JO", "KW", "LB", "OM", "PS", "QA", "SA", "SY", "TR", "YE"},
    "africa": {
        "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ", "DZ", "EG", "EH", "ER", "ET", "GA",
        "GH", "GM", "GN", "GQ", "GW", "KE", "KM", "LR", "LS", "LY", "MA", "MG", "ML", "MR", "MU", "MW", "MZ", "NA",
        "NE", "NG", "RE", "RW", "SC", "SD", "SH", "SL", "SN", "SO", "SS", "ST", "SZ", "TD", "TG", "TN", "TZ", "UG",
        "YT", "ZA", "ZM", "ZW",
    },
    "china": {"CN", "HK", "MO"},
}
COUNTRY_CODES_BY_SCOPE["asia-pacific"] = (
    COUNTRY_CODES_BY_SCOPE["asia-east"]
    | COUNTRY_CODES_BY_SCOPE["asia-south"]
    | COUNTRY_CODES_BY_SCOPE["asia-southeast"]
    | COUNTRY_CODES_BY_SCOPE["oceania"]
)


def _normalize_region_scopes(raw_scopes):
    if raw_scopes is None:
        return ["all"]

    values = raw_scopes
    if isinstance(values, str):
        values = [values]

    normalized = []
    for value in values:
        token = str(value or "").strip().lower()
        if not token:
            continue
        if token not in REGION_SCOPES:
            continue
        normalized.append(token)

    if not normalized:
        return ["all"]

    if "all" in normalized:
        return ["all"]

    return sorted(set(normalized))

def _matches_region_scope(region_or_scope, region_scopes):
    scopes = _normalize_region_scopes(region_scopes)
    if "all" in scopes:
        return True

    value = str(region_or_scope or "").strip().lower()
    if not value:
        return False

    for scope in scopes:
        if scope == "global":
            if value == "global":
                return True
            continue
        if scope == "government":
            if value.startswith("us-gov"):
                return True
            continue
        if scope == "china":
            if value.startswith("cn-") or value.startswith("china"):
                return True
            continue
        if scope == "europe":
            if (
                value.startswith("eu-")
                or value.startswith("europe")
                or value.startswith("eusc-")
                or value in {"eu", "eur"}
            ):
                return True
            continue
        if scope == "north-america":
            if value.startswith("us-") or value.startswith("ca-") or value.startswith("na-") or value.startswith("northamerica-"):
                return True
            continue
        if scope == "central-america":
            if value.startswith("mx-") or value.startswith("centralamerica") or value.startswith("central-america") or value.startswith("northamerica-south"):
                return True
            continue
        if scope == "south-america":
            if value.startswith("sa-") or value.startswith("southamerica") or value.startswith("south-america"):
                return True
            continue
        if scope == "asia-east":
            if value.startswith("asia-east") or value.startswith("ap-east") or value.startswith("asia-northeast") or value.startswith("ap-northeast"):
                return True
            continue
        if scope == "asia-south":
            if value.startswith("asia-south") or value.startswith("ap-south"):
                return True
            continue
        if scope == "asia-southeast":
            if value.startswith("asia-southeast") or value.startswith("ap-southeast"):
                return True
            continue
        if scope == "oceania":
            if value.startswith("australia") or value.startswith("oceania"):
                return True
            continue
        if scope == "asia-pacific":
            if (
                value.startswith("ap-")
                or value.startswith("asia")
                or value.startswith("australia")
                or value.startswith("oceania")
            ):
                return True
            continue
        if scope == "middle-east":
            if value.startswith("me-") or value.startswith("middleeast") or value.startswith("middle-east"):
                return True
            continue
        if scope == "africa":
            if value.startswith("af-") or value.startswith("africa"):
                return True
            continue

    return False

def _matches_country_scope(country_code, region_scopes):
    scopes = _normalize_region_scopes(region_scopes)
    if "all" in scopes:
        return True

    # ASN geodata is country-based; treat "global" as non-restrictive for this source.
    if "global" in scopes:
        return True

    code = str(country_code or "").strip().upper()
    if not code:
        return False

    for scope in scopes:
        allowed = COUNTRY_CODES_BY_SCOPE.get(scope)
        if allowed and code in allowed:
            return True

    return False

def _normalize_country_code(country_code):
    return str(country_code or "").strip().upper()

def _country_strict_geo_buckets(country_code):
    code = _normalize_country_code(country_code)
    if not code:
        return set()

    buckets = set()
    for scope in STRICT_GEO_BUCKET_SCOPES:
        allowed = COUNTRY_CODES_BY_SCOPE.get(scope) or set()
        if code in allowed:
            buckets.add(scope)
    return buckets

def _is_strict_geo_country_set(country_codes):
    clean_codes = {_normalize_country_code(code) for code in (country_codes or []) if _normalize_country_code(code)}
    if not clean_codes:
        return False

    combined_buckets = set()
    for code in clean_codes:
        buckets = _country_strict_geo_buckets(code)
        # Countries that belong to multiple macro-buckets are treated as border/disputed in strict mode.
        if len(buckets) != 1:
            return False
        combined_buckets.update(buckets)

    # Prefixes geolocated across multiple macro-buckets are treated as ambiguous in strict mode.
    return len(combined_buckets) == 1

def _scope_strict_geo_buckets(region_or_scope):
    value = str(region_or_scope or "").strip().lower()
    if not value:
        return set()

    if value.startswith("northamerica-south") or value.startswith("centralamerica") or value.startswith("central-america") or value.startswith("mx-"):
        return {"central-america"}

    if value.startswith("us-gov"):
        return {"north-america"}

    if value.startswith("cn-") or value.startswith("china"):
        return {"asia-east"}

    if value.startswith("eu-") or value.startswith("europe") or value.startswith("eusc-") or value in {"eu", "eur"}:
        return {"europe"}

    if value.startswith("us-") or value.startswith("ca-") or value.startswith("na-") or value.startswith("northamerica-"):
        return {"north-america"}

    if value.startswith("sa-") or value.startswith("southamerica") or value.startswith("south-america"):
        return {"south-america"}

    if value.startswith("ap-east") or value.startswith("asia-east") or value.startswith("asia-northeast") or value.startswith("ap-northeast"):
        return {"asia-east"}

    if value.startswith("ap-south") or value.startswith("asia-south"):
        return {"asia-south"}

    if value.startswith("ap-southeast") or value.startswith("asia-southeast"):
        return {"asia-southeast"}

    if value.startswith("australia") or value.startswith("oceania"):
        return {"oceania"}

    if value.startswith("me-") or value.startswith("middleeast") or value.startswith("middle-east"):
        return {"middle-east"}

    if value.startswith("af-") or value.startswith("africa"):
        return {"africa"}

    # Generic "asia"/"ap" values are too broad for strict mode and are treated as ambiguous.
    if value.startswith("asia") or value.startswith("ap-") or value.startswith("asia-pacific"):
        return set(STRICT_ASIA_PACIFIC_BUCKETS)

    return set()

def _matches_strict_scope_value(region_or_scope, region_scopes):
    scopes = _normalize_region_scopes(region_scopes)
    if "all" in scopes:
        return True

    value = str(region_or_scope or "").strip().lower()
    if not value:
        return False

    if "global" in scopes and value == "global":
        return True

    buckets = _scope_strict_geo_buckets(value)
    if len(buckets) != 1:
        return False

    allowed_buckets = set()
    for scope in scopes:
        if scope in STRICT_GEO_BUCKET_SCOPES:
            allowed_buckets.add(scope)
            continue
        if scope == "asia-pacific":
            allowed_buckets.update(STRICT_ASIA_PACIFIC_BUCKETS)
            continue
        if scope == "china":
            allowed_buckets.add("asia-east")
            continue
        if scope == "government":
            allowed_buckets.add("north-america")

    return bool(buckets & allowed_buckets)

def _download_ru_country_cidrs(timeout=30):
    text_data = _facade_call("_download_text", RU_COUNTRY_CIDR_SOURCE_URL, timeout=timeout)
    cidr_candidates = []
    for line in (text_data or "").splitlines():
        value = str(line or "").strip()
        if not value or value.startswith("#"):
            continue
        cidr_candidates.append(value)
    return _normalize_cidrs(cidr_candidates)

def _get_ru_cidr_index():
    """Return O(log n)-queryable interval index for RU networks, with 12-hour cache."""
    from core.services.cidr.antifilter import _build_antifilter_overlap_index

    now_ts = time.time()
    if _RU_COUNTRY_CIDR_CACHE["index"] is not None and now_ts < float(_RU_COUNTRY_CIDR_CACHE["expires_at"]):
        return _RU_COUNTRY_CIDR_CACHE["index"], None

    try:
        cidrs = _download_ru_country_cidrs()
        index = _build_antifilter_overlap_index(cidrs)
    except Exception as exc:  # noqa: BLE001
        _RU_COUNTRY_CIDR_CACHE["expires_at"] = now_ts + 300
        _RU_COUNTRY_CIDR_CACHE["index"] = None
        _RU_COUNTRY_CIDR_CACHE["error"] = str(exc)
        return None, str(exc)

    _RU_COUNTRY_CIDR_CACHE["expires_at"] = now_ts + RU_COUNTRY_CIDR_CACHE_TTL_SECONDS
    _RU_COUNTRY_CIDR_CACHE["index"] = index
    _RU_COUNTRY_CIDR_CACHE["error"] = None
    return index, None

def _exclude_ru_country_cidrs(cidrs):
    from core.services.cidr.antifilter import _cidr_contained_in_index

    if not cidrs:
        return cidrs, None

    ru_index, error_text = _facade_call("_get_ru_cidr_index")
    if ru_index is None:
        if error_text:
            return cidrs, {
                "strategy": "exclude_ru_country",
                "status": "source_unavailable",
                "error": error_text,
            }
        return cidrs, None

    ranges, starts, max_ends = ru_index
    filtered = []
    removed_count = 0
    for value in cidrs:
        if _cidr_contained_in_index(value, ranges, starts, max_ends):
            removed_count += 1
        else:
            filtered.append(str(value))

    normalized_filtered = sorted(set(filtered))
    if removed_count <= 0:
        return normalized_filtered, None

    return normalized_filtered, {
        "strategy": "exclude_ru_country",
        "status": "applied",
        "removed_cidr_count": removed_count,
        "result_cidr_count": len(normalized_filtered),
        "source": RU_COUNTRY_CIDR_SOURCE_URL,
    }

