"""Paths, env limits, caches, and regex patterns for CIDR pipelines."""
import os
import re
import time

# Корень репозитория (для CI и dev-клонов вне /opt/AdminAntizapret).
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BASE_DIR = os.path.abspath(os.environ.get("ADMIN_ANTIZAPRET_ROOT", _PROJECT_ROOT))
LIST_DIR = os.path.join(BASE_DIR, "ips", "list")
BASELINE_DIR = os.path.join(LIST_DIR, "_baseline")
RUNTIME_BACKUP_ROOT = os.path.join(BASE_DIR, "ips", "runtime_backups")
RUNTIME_BACKUP_RETENTION_SECONDS = 12 * 60 * 60
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")

CIDR_V4_SCAN_PATTERN = re.compile(
    r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}/(?:[0-9]|[12][0-9]|3[0-2])\b"
)
_BGP_TOOLS_RAW_ALLOC_IPV4_PATTERN = re.compile(
    r"\[ipv4\]\s*--\s*(.+?)(?=(?:\[ipv[46]\]\s*--|\[asn\]\s*--|##\s+Additional\s+Links|$))",
    re.IGNORECASE | re.DOTALL,
)

SOURCE_FORMATS_WITH_GEO = {"aws_json", "google_json", "ripe_geo_json"}


def _read_positive_int_env(name, default):
    raw = os.getenv(name)
    if raw is None:
        return int(default)

    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)

    if parsed <= 0:
        return int(default)

    return parsed


def _read_env_file_value(key):
    from core.services.cidr.facade_compat import get_attr

    env_path = get_attr("ENV_FILE_PATH")
    if not os.path.exists(env_path):
        return None

    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = str(raw_line or "").strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith(f"{key}="):
                    continue
                return line.split("=", 1)[1].strip()
    except OSError:
        return None

    return None


def _read_positive_int_runtime(name, default):
    raw = _read_env_file_value(name)
    if raw is None:
        raw = os.getenv(name)

    if raw is None:
        return int(default)

    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)

    if parsed <= 0:
        return int(default)

    return parsed


def _get_openvpn_route_total_cidr_limit():
    raw_limit = _read_positive_int_runtime(
        "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
        OPENVPN_ROUTE_TOTAL_CIDR_LIMIT,
    )
    return min(raw_limit, OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS)


OPENVPN_ROUTE_CIDR_LIMIT = _read_positive_int_env("OPENVPN_ROUTE_CIDR_LIMIT", 1500)
OPENVPN_ROUTE_TOTAL_CIDR_LIMIT = _read_positive_int_env("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", 1500)
OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS = _read_positive_int_env("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT_MAX_IOS", 900)
OPENVPN_ROUTE_MIN_PREFIXLEN = min(
    32,
    _read_positive_int_env("OPENVPN_ROUTE_MIN_PREFIXLEN", 8),
)
RU_COUNTRY_CIDR_SOURCE_URL = os.getenv(
    "CIDR_EXCLUDE_RU_SOURCE_URL",
    "https://www.ipdeny.com/ipblocks/data/countries/ru.zone",
)
RU_COUNTRY_CIDR_CACHE_TTL_SECONDS = 12 * 60 * 60
_RU_COUNTRY_CIDR_CACHE = {
    "expires_at": 0.0,
    "index": None,   # (ranges, starts, max_ends) tuple built by _build_antifilter_overlap_index
    "error": None,
}
_ANTIFILTER_INDEX_CACHE = {
    "expires_at": 0.0,
    "index": None,
}
LEGACY_GAME_INCLUDE_HOSTS_FILE = os.getenv(
    "CIDR_GAME_LEGACY_INCLUDE_HOSTS_FILE",
    "/root/antizapret/config/include-hosts.txt",
)
LEGACY_GAME_INCLUDE_IPS_FILE = os.getenv(
    "CIDR_GAME_LEGACY_INCLUDE_IPS_FILE",
    "/root/antizapret/config/include-ips.txt",
)
AZ_GAME_INCLUDE_HOSTS_FILE = os.getenv(
    "CIDR_AZ_GAME_INCLUDE_HOSTS_FILE",
    "/root/antizapret/config/AZ-Game-include-hosts.txt",
)
AZ_GAME_INCLUDE_IPS_FILE = os.getenv(
    "CIDR_AZ_GAME_INCLUDE_IPS_FILE",
    "/root/antizapret/config/AZ-Game-include-ips.txt",
)
# Backward-compatible aliases for modules/tests that still patch GAME_INCLUDE_*.
GAME_INCLUDE_HOSTS_FILE = AZ_GAME_INCLUDE_HOSTS_FILE
GAME_INCLUDE_IPS_FILE = AZ_GAME_INCLUDE_IPS_FILE
AZ_GAME_EXCLUDE_HOSTS_FILE = os.getenv(
    "CIDR_AZ_GAME_EXCLUDE_HOSTS_FILE",
    "/root/antizapret/config/AZ-Game-exclude-hosts.txt",
)
AZ_GAME_EXCLUDE_IPS_FILE = os.getenv(
    "CIDR_AZ_GAME_EXCLUDE_IPS_FILE",
    "/root/antizapret/config/AZ-Game-exclude-ips.txt",
)
GAME_FILTER_BLOCK_START = "# BEGIN AdminAntizapret CIDR games include"
GAME_FILTER_BLOCK_END = "# END AdminAntizapret CIDR games include"
GAME_FILTER_IP_BLOCK_START = "# BEGIN AdminAntizapret CIDR games include-ips"
GAME_FILTER_IP_BLOCK_END = "# END AdminAntizapret CIDR games include-ips"
GAME_FILTER_EXCLUDE_BLOCK_START = "# BEGIN AdminAntizapret CIDR games exclude"
GAME_FILTER_EXCLUDE_BLOCK_END = "# END AdminAntizapret CIDR games exclude"
GAME_FILTER_EXCLUDE_IP_BLOCK_START = "# BEGIN AdminAntizapret CIDR games exclude-ips"
GAME_FILTER_EXCLUDE_IP_BLOCK_END = "# END AdminAntizapret CIDR games exclude-ips"
