import ipaddress
import json
import os
import re
import socket
import shutil
import time
from datetime import datetime, timezone
from urllib import request

from config.antizapret_params import IP_FILES

BASE_DIR = "/opt/AdminAntizapret"
LIST_DIR = os.path.join(BASE_DIR, "ips", "list")
BASELINE_DIR = os.path.join(LIST_DIR, "_baseline")
RUNTIME_BACKUP_ROOT = os.path.join(BASE_DIR, "ips", "runtime_backups")
RUNTIME_BACKUP_RETENTION_SECONDS = 12 * 60 * 60
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")

# Each list file can have one or more sources. The first source that yields valid CIDRs is used.
PROVIDER_SOURCES = {
    "akamai-ips.txt": [
        {
            "name": "bgp-tools-nl-akamai",
            "url": "https://bgp.tools/rir-owner/nl.akamai",
            "format": "cidr_text_scan",
        },
        {
            "name": "bgp-tools-arin-akamai",
            "url": "https://bgp.tools/rir-owner/ARIN-AKAMAI",
            "format": "cidr_text_scan",
        },
        {
            "name": "ripe-as20940-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS20940",
            "format": "ripe_geo_json",
        }
    ],
    "amazon-ips.txt": [
        {
            "name": "aws-ip-ranges",
            "url": "https://ip-ranges.amazonaws.com/ip-ranges.json",
            "format": "aws_json",
        }
    ],
    "digitalocean-ips.txt": [
        {
            "name": "bgp-tools-arin-do-13",
            "url": "https://bgp.tools/rir-owner/ARIN-DO-13",
            "format": "cidr_text_scan",
        },
        {
            "name": "ripe-as14061-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS14061",
            "format": "ripe_geo_json",
        }
    ],
    "google-ips.txt": [
        {
            "name": "google-goog-json",
            "url": "https://www.gstatic.com/ipranges/goog.json",
            "format": "google_json",
        },
        {
            "name": "google-cloud-json",
            "url": "https://www.gstatic.com/ipranges/cloud.json",
            "format": "google_json",
        },
    ],
    "hetzner-ips.txt": [
        {
            "name": "bgp-tools-de-hetzner",
            "url": "https://bgp.tools/rir-owner/de.hetzner",
            "format": "cidr_text_scan",
        },
        {
            "name": "ripe-as24940-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS24940",
            "format": "ripe_geo_json",
        }
    ],
    "ovh-ips.txt": [
        {
            "name": "bgp-tools-fr-ovh",
            "url": "https://bgp.tools/rir-owner/fr.ovh",
            "format": "cidr_text_scan",
        },
        {
            "name": "ripe-as16276-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS16276",
            "format": "ripe_geo_json",
        }
    ],
}

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
    env_path = ENV_FILE_PATH
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
    return _read_positive_int_runtime(
        "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
        OPENVPN_ROUTE_TOTAL_CIDR_LIMIT,
    )


OPENVPN_ROUTE_CIDR_LIMIT = _read_positive_int_env("OPENVPN_ROUTE_CIDR_LIMIT", 1500)
OPENVPN_ROUTE_TOTAL_CIDR_LIMIT = _read_positive_int_env("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT", 1500)
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
    "networks": [],
    "error": None,
}
GAME_INCLUDE_HOSTS_FILE = os.getenv(
    "CIDR_GAME_INCLUDE_HOSTS_FILE",
    "/root/antizapret/config/include-hosts.txt",
)
GAME_INCLUDE_IPS_FILE = os.getenv(
    "CIDR_GAME_INCLUDE_IPS_FILE",
    "/root/antizapret/config/include-ips.txt",
)
GAME_FILTER_BLOCK_START = "# BEGIN AdminAntizapret CIDR games include"
GAME_FILTER_BLOCK_END = "# END AdminAntizapret CIDR games include"
GAME_FILTER_IP_BLOCK_START = "# BEGIN AdminAntizapret CIDR games include-ips"
GAME_FILTER_IP_BLOCK_END = "# END AdminAntizapret CIDR games include-ips"
GAME_FILTER_CATALOG = [
    {"key": "lol", "title": "League of Legends", "domains": ["riotgames.com", "pvp.net", "leagueoflegends.com", "lolesports.com"]},
    {"key": "valorant", "title": "VALORANT", "domains": ["playvalorant.com", "valorantesports.com"]},
    {"key": "dota2", "title": "Dota 2", "domains": ["dota2.com"]},
    {"key": "cs2", "title": "Counter-Strike 2 / CS:GO", "domains": ["counter-strike.net"]},
    {"key": "faceit", "title": "FACEIT", "domains": ["faceit.com", "faceit-cdn.net", "faceitusercontent.com"]},
    {"key": "fortnite", "title": "Fortnite", "domains": ["fortnite.com", "epicgames.com"]},
    {"key": "apex_legends", "title": "Apex Legends", "domains": ["ea.com", "respawn.com"]},
    {"key": "pubg", "title": "PUBG", "domains": ["pubg.com", "krafton.com"]},
    {"key": "warzone", "title": "Call of Duty: Warzone", "domains": ["callofduty.com", "activision.com"]},
    {"key": "overwatch2", "title": "Overwatch 2", "domains": ["playoverwatch.com", "blizzard.com"]},
    {"key": "rocket_league", "title": "Rocket League", "domains": ["rocketleague.com", "psyonix.com"]},
    {"key": "rainbow6", "title": "Rainbow Six Siege", "domains": ["rainbow6.com", "ubisoft.com"]},
    {"key": "destiny2", "title": "Destiny 2", "domains": ["bungie.net"]},
    {"key": "warframe", "title": "Warframe", "domains": ["warframe.com"]},
    {"key": "world_of_warcraft", "title": "World of Warcraft", "domains": ["worldofwarcraft.com", "battle.net"]},
    {"key": "hearthstone", "title": "Hearthstone", "domains": ["playhearthstone.com", "battle.net"]},
    {"key": "diablo4", "title": "Diablo IV", "domains": ["diablo.com", "battle.net"]},
    {"key": "starcraft2", "title": "StarCraft II", "domains": ["starcraft2.com", "battle.net"]},
    {"key": "heroes_of_the_storm", "title": "Heroes of the Storm", "domains": ["heroesofthestorm.com", "battle.net"]},
    {"key": "minecraft", "title": "Minecraft", "domains": ["minecraft.net", "mojang.com"]},
    {"key": "roblox", "title": "Roblox", "domains": ["roblox.com", "rbxcdn.com"]},
    {"key": "genshin_impact", "title": "Genshin Impact", "domains": ["genshin.hoyoverse.com", "hoyoverse.com", "mihoyo.com"]},
    {"key": "honkai_star_rail", "title": "Honkai: Star Rail", "domains": ["hsr.hoyoverse.com", "hoyoverse.com"]},
    {"key": "wuthering_waves", "title": "Wuthering Waves", "domains": ["wutheringwaves.com", "kurogames.com"]},
    {"key": "mobile_legends", "title": "Mobile Legends", "domains": ["mobilelegends.com", "moonton.com"]},
    {"key": "clash_of_clans", "title": "Clash of Clans", "domains": ["clashofclans.com", "supercell.com"]},
    {"key": "clash_royale", "title": "Clash Royale", "domains": ["clashroyale.com", "supercell.com"]},
    {"key": "brawl_stars", "title": "Brawl Stars", "domains": ["brawlstars.com", "supercell.com"]},
    {"key": "free_fire", "title": "Free Fire", "domains": ["ff.garena.com", "garena.com"]},
    {"key": "cod_mobile", "title": "Call of Duty: Mobile", "domains": ["callofduty.com", "activision.com"]},
    {"key": "pubg_mobile", "title": "PUBG Mobile", "domains": ["pubgmobile.com", "krafton.com"]},
    {"key": "among_us", "title": "Among Us", "domains": ["among.us", "innersloth.com"]},
    {"key": "world_of_tanks", "title": "World of Tanks", "domains": ["worldoftanks.com", "wargaming.net"]},
    {"key": "mir_tankov", "title": "Mir Tankov", "domains": ["tanki.su", "lesta.ru"]},
    {"key": "world_of_tanks_blitz", "title": "World of Tanks Blitz", "domains": ["wotblitz.com", "wargaming.net"]},
    {"key": "world_of_warships", "title": "World of Warships", "domains": ["worldofwarships.com", "wargaming.net"]},
    {"key": "war_thunder", "title": "War Thunder", "domains": ["warthunder.com", "gaijin.net"]},
    {"key": "enlisted", "title": "Enlisted", "domains": ["enlisted.net", "gaijin.net"]},
    {"key": "crossout", "title": "Crossout", "domains": ["crossout.net", "gaijin.net"]},
    {"key": "warface", "title": "Warface", "domains": ["warface.com", "my.games"]},
    {"key": "caliber", "title": "Caliber", "domains": ["playcaliber.com"]},
    {"key": "path_of_exile", "title": "Path of Exile", "domains": ["pathofexile.com", "grindinggear.com"]},
    {"key": "lineage2", "title": "Lineage 2", "domains": ["lineage2.com", "4game.com"]},
    {"key": "point_blank", "title": "Point Blank", "domains": ["pointblank.com", "4game.com"]},
    {"key": "metin2", "title": "Metin2", "domains": ["metin2.gameforge.com", "gameforge.com"]},
    {"key": "lost_ark", "title": "Lost Ark", "domains": ["lostark.com", "smilegate.com"]},
    {"key": "albion_online", "title": "Albion Online", "domains": ["albiononline.com"]},
    {"key": "black_desert", "title": "Black Desert Online", "domains": ["blackdesertonline.com", "pearlabyss.com"]},
    {"key": "raid_shadow_legends", "title": "RAID: Shadow Legends", "domains": ["raidshadowlegends.com", "plarium.com"]},
    {"key": "final_fantasy_xiv", "title": "Final Fantasy XIV", "domains": ["finalfantasyxiv.com", "square-enix.com"]},
    {"key": "elder_scrolls_online", "title": "Elder Scrolls Online", "domains": ["elderscrollsonline.com", "bethesda.net"]},
    {"key": "escape_from_tarkov", "title": "Escape from Tarkov", "domains": ["escapefromtarkov.com", "battlestategames.com"]},
    {"key": "tarkov_arena", "title": "Escape from Tarkov: Arena", "domains": ["arena.tarkov.com", "escapefromtarkov.com"]},
    {"key": "standoff2", "title": "Standoff 2", "domains": ["standoff2.com", "axlebolt.com"]},
    {"key": "war_robots", "title": "War Robots", "domains": ["warrobots.com", "pixonic.com"]},
    {"key": "battlefield", "title": "Battlefield", "domains": ["battlefield.com", "ea.com"]},
    {"key": "rust", "title": "Rust", "domains": ["rust.facepunch.com", "facepunch.com"]},
    {"key": "dayz", "title": "DayZ", "domains": ["dayz.com", "bohemia.net"]},
    {"key": "halo_infinite", "title": "Halo Infinite", "domains": ["halowaypoint.com", "xbox.com"]},
    {"key": "xdefiant", "title": "XDefiant", "domains": ["xdefiant.com", "ubisoft.com"]},
    {"key": "the_finals", "title": "THE FINALS", "domains": ["reachthefinals.com", "embark-studios.com"]},
    {"key": "ea_fc", "title": "EA Sports FC", "domains": ["ea.com", "easports.com"]},
    {"key": "nba_2k", "title": "NBA 2K", "domains": ["nba.2k.com", "2k.com"]},
    {"key": "steam_platform", "title": "Steam Platform", "domains": ["steampowered.com", "steamcommunity.com", "steamstatic.com", "steamcontent.com", "steamserver.net", "valvesoftware.com"]},
    {"key": "epic_games_store", "title": "Epic Games Store", "domains": ["epicgames.com", "unrealengine.com"]},
    {"key": "xbox_live", "title": "Xbox Live", "domains": ["xbox.com", "xboxlive.com"]},
    {"key": "playstation_network", "title": "PlayStation Network", "domains": ["playstation.com", "sonyentertainmentnetwork.com"]},
]
GAME_FILTER_ALIASES = {
    "csgo": "cs2",
    "counter-strike": "cs2",
    "counter_strike": "cs2",
    "dota": "dota2",
    "wot": "world_of_tanks",
    "wotb": "world_of_tanks_blitz",
    "wows": "world_of_warships",
    "tarkov": "escape_from_tarkov",
    "league-of-legends": "lol",
}
GAME_FILTER_BY_KEY = {item["key"]: item for item in GAME_FILTER_CATALOG}
STRICT_GEO_BUCKET_SCOPES = (
    "europe",
    "north-america",
    "central-america",
    "south-america",
    "asia-east",
    "asia-south",
    "asia-southeast",
    "oceania",
    "middle-east",
    "africa",
)
STRICT_ASIA_PACIFIC_BUCKETS = {
    "asia-east",
    "asia-south",
    "asia-southeast",
    "oceania",
}

REGION_SCOPES = {
    "all",
    "europe",
    "north-america",
    "central-america",
    "south-america",
    "asia-pacific",
    "asia-east",
    "asia-south",
    "asia-southeast",
    "oceania",
    "middle-east",
    "africa",
    "china",
    "government",
    "global",
}


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


def _download_text(url, timeout=30):
    req = request.Request(url, headers={"User-Agent": "AdminAntizapret-CIDR-Updater/1.0"})
    with request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


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
    lines = [
        f"# Auto-generated CIDR list for {file_name}",
        f"# Source: {source_name}",
        f"# Generated at: {generated_at}",
        "",
    ]
    lines.extend(cidrs)
    return "\n".join(lines) + "\n"


def _snapshot_baseline_if_missing():
    os.makedirs(BASELINE_DIR, exist_ok=True)
    for file_name in IP_FILES.keys():
        source_path = os.path.join(LIST_DIR, file_name)
        target_path = os.path.join(BASELINE_DIR, file_name)
        if os.path.exists(target_path):
            continue
        if os.path.exists(source_path):
            shutil.copyfile(source_path, target_path)


def get_available_regions():
    regions = []
    for file_name, meta in IP_FILES.items():
        sources = PROVIDER_SOURCES.get(file_name) or []
        supports_geo_filter = any((src.get("format") in SOURCE_FORMATS_WITH_GEO) for src in sources)
        regions.append(
            {
                "file": file_name,
                "region": meta.get("name") or file_name,
                "description": meta.get("description") or "",
                "can_update": file_name in PROVIDER_SOURCES,
                "supports_geo_filter": supports_geo_filter,
            }
        )
    return regions


def get_available_game_filters():
    return [
        {
            "key": item["key"],
            "title": item["title"],
            "domain_count": len(item["domains"]),
        }
        for item in GAME_FILTER_CATALOG
    ]


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
            text_data = _download_text(source["url"])
            cidrs = _extract_cidrs(
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

    if len(cidrs) <= OPENVPN_ROUTE_CIDR_LIMIT:
        return cidrs, source_name, None

    if not _has_non_geo_sources(sources):
        return cidrs, source_name, None

    optimized_cidrs, optimized_source_name, _ = _collect_cidrs_from_sources(
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
            "widening_passes": 0,
        }

    target_limit = int(limit)
    if len(normalized) <= target_limit:
        return normalized, None

    networks = [ipaddress.ip_network(value, strict=False) for value in normalized]
    min_prefixlen = max(1, OPENVPN_ROUTE_MIN_PREFIXLEN)
    current = set(networks)
    passes = 0
    exact_merge_count = 0

    while len(current) > target_limit:
        need_reduction = len(current) - target_limit
        consumed = set()
        merged_parents = []
        ordered = sorted(current, key=lambda n: (-n.prefixlen, int(n.network_address)))
        lookup = set(current)

        for net in ordered:
            if need_reduction <= 0:
                break
            if net in consumed or net.prefixlen <= min_prefixlen:
                continue

            parent = net.supernet(prefixlen_diff=1)
            children = list(parent.subnets(new_prefix=net.prefixlen))
            sibling = children[0] if children[1] == net else children[1]
            if sibling not in lookup or sibling in consumed:
                continue

            consumed.add(net)
            consumed.add(sibling)
            merged_parents.append(parent)
            need_reduction -= 1
            exact_merge_count += 1

        if not merged_parents:
            break

        current.difference_update(consumed)
        current.update(merged_parents)
        current = {net for net in current if net.prefixlen > 0}
        passes += 1

        if passes >= 64:
            break

    was_trimmed = False
    if len(current) > target_limit:
        was_trimmed = True
        current = set(
            sorted(
                current,
                key=lambda n: (-n.prefixlen, int(n.network_address)),
            )[:target_limit]
        )

    compressed = [
        str(net)
        for net in sorted(current, key=lambda n: (int(n.network_address), n.prefixlen))
    ]
    return compressed, {
        "strategy": "bounded_exact_compaction_trim" if was_trimmed else "bounded_exact_compaction",
        "original_cidr_count": len(normalized),
        "compressed_cidr_count": len(compressed),
        "target_limit": target_limit,
        "widening_passes": 0,
        "exact_merge_passes": passes,
        "exact_merge_count": exact_merge_count,
        "min_prefixlen": min_prefixlen,
        "trimmed_to_limit": was_trimmed,
        "forbidden_default_route_filtered": False,
    }


def _apply_total_route_limit(entries, total_limit):
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

    if route_limit < len(non_empty_indices):
        prioritized_indices = sorted(
            non_empty_indices,
            key=lambda idx: len(entries[idx].get("cidrs") or []),
            reverse=True,
        )
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
                }
            )

        compressed_total = sum(len(item.get("cidrs") or []) for item in adjusted_entries)
        meta = {
            "strategy": "global_total_route_limit",
            "limit": route_limit,
            "original_total_cidr_count": original_total,
            "compressed_total_cidr_count": compressed_total,
            "files": per_file,
        }
        return adjusted_entries, meta

    raw_shares = {}
    budgets = {}
    for index in non_empty_indices:
        current_count = len(entries[index]["cidrs"])
        share = (current_count * route_limit) / max(original_total, 1)
        raw_shares[index] = share
        budgets[index] = min(current_count, max(1, int(share)))

    allocated = sum(budgets.values())
    if allocated > route_limit:
        for index, _ in sorted(budgets.items(), key=lambda pair: pair[1], reverse=True):
            while budgets[index] > 1 and allocated > route_limit:
                budgets[index] -= 1
                allocated -= 1
            if allocated <= route_limit:
                break

    if allocated < route_limit:
        for index, _ in sorted(raw_shares.items(), key=lambda pair: pair[1] - int(pair[1]), reverse=True):
            current_count = len(entries[index]["cidrs"])
            while budgets[index] < current_count and allocated < route_limit:
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
            }
        )

    compressed_total = sum(len(item.get("cidrs") or []) for item in adjusted_entries)
    meta = {
        "strategy": "global_total_route_limit",
        "limit": route_limit,
        "original_total_cidr_count": original_total,
        "compressed_total_cidr_count": compressed_total,
        "files": per_file,
    }
    return adjusted_entries, meta


def _download_ru_country_cidrs(timeout=30):
    text_data = _download_text(RU_COUNTRY_CIDR_SOURCE_URL, timeout=timeout)
    cidr_candidates = []
    for line in (text_data or "").splitlines():
        value = str(line or "").strip()
        if not value or value.startswith("#"):
            continue
        cidr_candidates.append(value)
    return _normalize_cidrs(cidr_candidates)


def _get_ru_cidr_networks():
    now_ts = time.time()
    cache_expires_at = float(_RU_COUNTRY_CIDR_CACHE.get("expires_at") or 0.0)
    cache_networks = _RU_COUNTRY_CIDR_CACHE.get("networks") or []
    if cache_networks and now_ts < cache_expires_at:
        return cache_networks, None

    try:
        cidrs = _download_ru_country_cidrs()
        networks = [ipaddress.ip_network(cidr, strict=False) for cidr in cidrs]
    except Exception as exc:  # noqa: BLE001
        _RU_COUNTRY_CIDR_CACHE["expires_at"] = now_ts + 300
        _RU_COUNTRY_CIDR_CACHE["networks"] = []
        _RU_COUNTRY_CIDR_CACHE["error"] = str(exc)
        return [], str(exc)

    _RU_COUNTRY_CIDR_CACHE["expires_at"] = now_ts + RU_COUNTRY_CIDR_CACHE_TTL_SECONDS
    _RU_COUNTRY_CIDR_CACHE["networks"] = networks
    _RU_COUNTRY_CIDR_CACHE["error"] = None
    return networks, None


def _exclude_ru_country_cidrs(cidrs):
    if not cidrs:
        return cidrs, None

    ru_networks, error_text = _get_ru_cidr_networks()
    if not ru_networks:
        if error_text:
            return cidrs, {
                "strategy": "exclude_ru_country",
                "status": "source_unavailable",
                "error": error_text,
            }
        return cidrs, None

    filtered = []
    removed_count = 0
    for value in cidrs:
        raw = str(value or "").strip()
        if not raw:
            continue
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue

        if any(network.subnet_of(ru_network) for ru_network in ru_networks):
            removed_count += 1
            continue

        filtered.append(str(network))

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
    selected_titles, selected_domains = _collect_game_domains(selected_game_keys)
    if not selected_domains:
        return "", selected_titles, selected_domains

    lines = [GAME_FILTER_BLOCK_START]
    lines.append(f"# Selected games ({len(selected_titles)}): {', '.join(selected_titles)}")
    lines.extend(selected_domains)
    lines.append(GAME_FILTER_BLOCK_END)
    return "\n".join(lines), selected_titles, selected_domains


def _render_games_ips_block(selected_game_keys):
    selected_titles, selected_domains = _collect_game_domains(selected_game_keys)
    if not selected_domains:
        return "", selected_titles, selected_domains, [], []

    selected_cidrs, unresolved_domains = _resolve_game_domains_ipv4_cidrs(selected_domains)
    if not selected_cidrs:
        return "", selected_titles, selected_domains, [], unresolved_domains

    lines = [GAME_FILTER_IP_BLOCK_START]
    lines.append(f"# Selected games ({len(selected_titles)}): {', '.join(selected_titles)}")
    lines.append(f"# Domains resolved: {len(selected_domains) - len(unresolved_domains)}/{len(selected_domains)}")
    if unresolved_domains:
        preview = ", ".join(unresolved_domains[:10])
        if len(unresolved_domains) > 10:
            preview = f"{preview}, ..."
        lines.append(f"# Unresolved domains ({len(unresolved_domains)}): {preview}")
    lines.extend(selected_cidrs)
    lines.append(GAME_FILTER_IP_BLOCK_END)
    return "\n".join(lines), selected_titles, selected_domains, selected_cidrs, unresolved_domains


def _sync_games_include_hosts(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    try:
        with open(GAME_INCLUDE_HOSTS_FILE, "r", encoding="utf-8") as handle:
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
            "file": GAME_INCLUDE_HOSTS_FILE,
        }

    try:
        os.makedirs(os.path.dirname(GAME_INCLUDE_HOSTS_FILE), exist_ok=True)
        with open(GAME_INCLUDE_HOSTS_FILE, "w", encoding="utf-8") as handle:
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
        "file": GAME_INCLUDE_HOSTS_FILE,
        "domain_count": len(selected_domains),
    }


def _sync_games_include_ips(selected_game_keys):
    normalized_keys = _normalize_game_filter_keys(selected_game_keys)
    try:
        with open(GAME_INCLUDE_IPS_FILE, "r", encoding="utf-8") as handle:
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
            "file": GAME_INCLUDE_IPS_FILE,
        }

    try:
        os.makedirs(os.path.dirname(GAME_INCLUDE_IPS_FILE), exist_ok=True)
        with open(GAME_INCLUDE_IPS_FILE, "w", encoding="utf-8") as handle:
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
        "file": GAME_INCLUDE_IPS_FILE,
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


def _make_runtime_backup(files):
    _prune_runtime_backups()

    backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = os.path.join(RUNTIME_BACKUP_ROOT, backup_stamp)
    os.makedirs(backup_dir, exist_ok=True)

    copied = []
    for file_name in files:
        source_path = os.path.join(LIST_DIR, file_name)
        if not os.path.exists(source_path):
            continue
        shutil.copyfile(source_path, os.path.join(backup_dir, file_name))
        copied.append(file_name)

    return backup_dir, copied


def _prune_runtime_backups(now_ts=None, retention_seconds=RUNTIME_BACKUP_RETENTION_SECONDS):
    if retention_seconds <= 0:
        return []

    os.makedirs(RUNTIME_BACKUP_ROOT, exist_ok=True)

    current_ts = float(now_ts) if now_ts is not None else datetime.now(timezone.utc).timestamp()
    cutoff_ts = current_ts - float(retention_seconds)
    removed_dirs = []

    for entry_name in os.listdir(RUNTIME_BACKUP_ROOT):
        entry_path = os.path.join(RUNTIME_BACKUP_ROOT, entry_name)
        if not os.path.isdir(entry_path):
            continue

        try:
            if os.path.getmtime(entry_path) > cutoff_ts:
                continue
            shutil.rmtree(entry_path)
            removed_dirs.append(entry_name)
        except OSError:
            continue

    return removed_dirs


def _emit_progress(progress_callback, percent, stage):
    if progress_callback is None:
        return
    try:
        safe_percent = max(0, min(100, int(percent)))
    except (TypeError, ValueError):
        safe_percent = 0

    text = str(stage or "").strip() or "Выполняется операция"
    progress_callback(safe_percent, text)


def update_cidr_files(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
    progress_callback=None,
):
    _emit_progress(progress_callback, 2, "Подготовка к обновлению CIDR-файлов")
    _snapshot_baseline_if_missing()
    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    if not normalized:
        _emit_progress(progress_callback, 100, "Обновление завершено")
        return {
            "success": False,
            "message": "Не выбраны корректные CIDR-файлы",
            "updated": [],
            "failed": [],
            "skipped": [],
        }

    _emit_progress(progress_callback, 8, "Создание резервной копии текущих CIDR-файлов")
    backup_dir, backup_files = _make_runtime_backup(normalized)

    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    game_filter_sync_result = sync_game_hosts_filter(include_game_keys=selected_game_keys)
    game_hosts_filter = game_filter_sync_result.get("game_hosts_filter") or {}
    game_ips_filter = game_filter_sync_result.get("game_ips_filter") or {}
    if not game_filter_sync_result.get("success"):
        _emit_progress(progress_callback, 100, "Ошибка синхронизации игрового фильтра")
        return {
            "success": False,
            "message": "Не удалось синхронизировать игровой фильтр",
            "updated": [],
            "failed": [],
            "skipped": [],
            "backup_dir": backup_dir,
            "backup_files": backup_files,
            "game_hosts_filter": game_hosts_filter,
            "game_ips_filter": game_ips_filter,
        }

    planned_updates = []
    updated = []
    failed = []
    skipped = []

    total_files = len(normalized)
    for index, file_name in enumerate(normalized, start=1):
        progress_start = 10 + int(((index - 1) / max(total_files, 1)) * 82)
        _emit_progress(progress_callback, progress_start, f"Обработка файла {file_name}")

        sources = PROVIDER_SOURCES.get(file_name) or []
        if not sources:
            skipped.append({"file": file_name, "reason": "source_not_configured"})
            progress_done = 10 + int((index / max(total_files, 1)) * 82)
            _emit_progress(progress_callback, progress_done, f"Файл {file_name} пропущен: source_not_configured")
            continue

        effective_scopes = list(normalized_scopes)

        if not is_all_scope:
            supports_geo_scope = _supports_geo_scope(sources)
            if not supports_geo_scope:
                if include_non_geo_fallback:
                    effective_scopes = ["all"]
                else:
                    skipped.append({"file": file_name, "reason": "geo_scope_not_supported"})
                    progress_done = 10 + int((index / max(total_files, 1)) * 82)
                    _emit_progress(progress_callback, progress_done, f"Файл {file_name} пропущен: geo_scope_not_supported")
                    continue

        cidrs, source_name, last_error = _collect_cidrs_from_sources(
            sources,
            effective_scopes,
            strict_geo_filter=bool(strict_geo_filter),
        )

        if not cidrs:
            failed.append({"file": file_name, "error": last_error})
            progress_done = 10 + int((index / max(total_files, 1)) * 82)
            _emit_progress(progress_callback, progress_done, f"Ошибка файла {file_name}")
            continue

        country_exclusion_meta = None
        if exclude_ru_cidrs and "all" in effective_scopes:
            cidrs, country_exclusion_meta = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                progress_done = 10 + int((index / max(total_files, 1)) * 82)
                _emit_progress(progress_callback, progress_done, f"Файл {file_name} пропущен: empty_after_ru_exclusion")
                continue

        cidrs, source_name, optimization_meta = _optimize_cidrs_for_openvpn_routes(
            sources=sources,
            effective_scopes=effective_scopes,
            cidrs=cidrs,
            source_name=source_name,
            strict_geo_filter=bool(strict_geo_filter),
        )

        planned_updates.append(
            {
                "file": file_name,
                "cidrs": cidrs,
                "source": source_name,
                "country_exclusion": country_exclusion_meta,
                "route_optimization": optimization_meta,
            }
        )
        progress_done = 10 + int((index / max(total_files, 1)) * 82)
        _emit_progress(progress_callback, progress_done, f"Файл {file_name} обновлен")

    planned_updates, global_route_optimization_meta = _apply_total_route_limit(
        planned_updates,
        _get_openvpn_route_total_cidr_limit(),
    )

    for item in planned_updates:
        file_name = item["file"]
        cidrs = item.get("cidrs") or []
        source_name = item.get("source") or "unknown"

        out_path = os.path.join(LIST_DIR, file_name)
        content = _render_file_content(file_name, cidrs, source_name)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(content)

        updated_item = {"file": file_name, "cidr_count": len(cidrs), "source": source_name}
        if item.get("country_exclusion"):
            updated_item["country_exclusion"] = item["country_exclusion"]
        if item.get("route_optimization"):
            updated_item["route_optimization"] = item["route_optimization"]
        if item.get("global_route_optimization"):
            updated_item["global_route_optimization"] = item["global_route_optimization"]
        updated.append(updated_item)

    success = bool(updated)
    if updated and failed:
        message = "Часть CIDR-файлов обновлена, часть завершилась с ошибкой"
    elif updated:
        message = "CIDR-файлы успешно обновлены"
    elif failed:
        message = "Не удалось обновить CIDR-файлы"
    else:
        message = "Нет файлов для обновления"

    _emit_progress(progress_callback, 100, "Обновление CIDR-файлов завершено")

    result = {
        "success": success,
        "message": message,
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
        "backup_dir": backup_dir,
        "backup_files": backup_files,
        "game_hosts_filter": game_hosts_filter,
        "game_ips_filter": game_ips_filter,
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    return result


def estimate_cidr_matches(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
):
    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    if not normalized:
        return {
            "success": False,
            "message": "Не выбраны корректные CIDR-файлы",
            "estimated": [],
            "failed": [],
            "skipped": [],
        }

    estimated = []
    planned_estimated = []
    failed = []
    skipped = []

    for file_name in normalized:
        sources = PROVIDER_SOURCES.get(file_name) or []
        if not sources:
            skipped.append({"file": file_name, "reason": "source_not_configured"})
            continue

        effective_scopes = list(normalized_scopes)

        if not is_all_scope:
            supports_geo_scope = _supports_geo_scope(sources)
            if not supports_geo_scope:
                if include_non_geo_fallback:
                    effective_scopes = ["all"]
                else:
                    skipped.append({"file": file_name, "reason": "geo_scope_not_supported"})
                    continue

        cidrs, source_name, last_error = _collect_cidrs_from_sources(
            sources,
            effective_scopes,
            strict_geo_filter=bool(strict_geo_filter),
        )

        if not cidrs:
            failed.append({"file": file_name, "error": last_error})
            continue

        country_exclusion_meta = None
        if exclude_ru_cidrs and "all" in effective_scopes:
            cidrs, country_exclusion_meta = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                continue

        cidrs, source_name, optimization_meta = _optimize_cidrs_for_openvpn_routes(
            sources=sources,
            effective_scopes=effective_scopes,
            cidrs=cidrs,
            source_name=source_name,
            strict_geo_filter=bool(strict_geo_filter),
        )

        planned_estimated.append(
            {
                "file": file_name,
                "cidrs": cidrs,
                "source": source_name,
                "country_exclusion": country_exclusion_meta,
                "route_optimization": optimization_meta,
            }
        )

    planned_estimated, global_route_optimization_meta = _apply_total_route_limit(
        planned_estimated,
        _get_openvpn_route_total_cidr_limit(),
    )

    for item in planned_estimated:
        estimated_item = {
            "file": item["file"],
            "cidr_count": len(item.get("cidrs") or []),
            "source": item.get("source") or "unknown",
        }
        if item.get("country_exclusion"):
            estimated_item["country_exclusion"] = item["country_exclusion"]
        if item.get("route_optimization"):
            estimated_item["route_optimization"] = item["route_optimization"]
        if item.get("global_route_optimization"):
            estimated_item["global_route_optimization"] = item["global_route_optimization"]
        estimated.append(estimated_item)

    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    _, selected_game_domains = _collect_game_domains(selected_game_keys)

    result = {
        "success": True,
        "message": "Оценка CIDR перед обновлением готова",
        "estimated": estimated,
        "failed": failed,
        "skipped": skipped,
        "game_hosts_filter": {
            "enabled": bool(selected_game_keys),
            "selected_game_keys": selected_game_keys,
            "selected_game_count": len(selected_game_keys),
            "domain_count": len(selected_game_domains),
            "file": GAME_INCLUDE_HOSTS_FILE,
        },
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    return result


def rollback_to_baseline(selected_files=None, progress_callback=None):
    _emit_progress(progress_callback, 3, "Подготовка к откату CIDR-файлов")
    _snapshot_baseline_if_missing()

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    restored = []
    missing = []

    total_files = len(normalized)
    if total_files == 0:
        _emit_progress(progress_callback, 100, "Откат завершен")

    for index, file_name in enumerate(normalized, start=1):
        progress_start = 8 + int(((index - 1) / max(total_files, 1)) * 90)
        _emit_progress(progress_callback, progress_start, f"Откат файла {file_name}")

        baseline_path = os.path.join(BASELINE_DIR, file_name)
        target_path = os.path.join(LIST_DIR, file_name)

        if not os.path.exists(baseline_path):
            missing.append(file_name)
            progress_done = 8 + int((index / max(total_files, 1)) * 90)
            _emit_progress(progress_callback, progress_done, f"Файл {file_name} пропущен: baseline не найден")
            continue

        shutil.copyfile(baseline_path, target_path)
        restored.append(file_name)
        progress_done = 8 + int((index / max(total_files, 1)) * 90)
        _emit_progress(progress_callback, progress_done, f"Файл {file_name} восстановлен")

    success = bool(restored)
    if restored and missing:
        message = "Откат выполнен частично"
    elif restored:
        message = "Откат к эталонным CIDR-спискам выполнен"
    else:
        message = "Эталонные файлы не найдены"

    _emit_progress(progress_callback, 100, "Откат CIDR-файлов завершен")

    return {
        "success": success,
        "message": message,
        "restored": restored,
        "missing": missing,
    }
