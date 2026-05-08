import bisect
import ipaddress
import json
import os
import re
import socket
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib import request

from config.antizapret_params import IP_FILES

BASE_DIR = "/opt/AdminAntizapret"
LIST_DIR = os.path.join(BASE_DIR, "ips", "list")
BASELINE_DIR = os.path.join(LIST_DIR, "_baseline")
RUNTIME_BACKUP_ROOT = os.path.join(BASE_DIR, "ips", "runtime_backups")
RUNTIME_BACKUP_RETENTION_SECONDS = 12 * 60 * 60
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")

# Each list file can have one or more sources. Successful source payloads are merged.
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
        },
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
        },
        {
            "name": "ripe-as46652-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS46652",
            "format": "ripe_json",
        },
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
        },
        {
            "name": "ripe-as213230-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS213230",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as212317-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS212317",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as215859-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS215859",
            "format": "ripe_json",
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
        },
        {
            "name": "ripe-as35540-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS35540",
            "format": "ripe_json",
        }
    ],
    "cloudflare-ips.txt": [
        {
            "name": "cloudflare-ips-v4",
            "url": "https://www.cloudflare.com/ips-v4",
            "format": "cidr_text",
        },
        {
            "name": "ripe-as13335-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS13335",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as209242-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS209242",
            "format": "ripe_json",
        },
    ],
    "fastly-ips.txt": [
        {
            "name": "ripe-as54113-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS54113",
            "format": "ripe_json",
        }
    ],
    "azure-ips.txt": [
        {
            "name": "ripe-as8075-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS8075",
            "format": "ripe_json",
        }
    ],
    "oracle-ips.txt": [
        {
            "name": "ripe-as31898-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS31898",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as54253-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS54253",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as1219-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS1219",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as6142-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS6142",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as14544-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS14544",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as20054-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS20054",
            "format": "ripe_json",
        }
    ],
    "cdn77-ips.txt": [
        {
            "name": "ripe-as60068-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS60068",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as212238-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS212238",
            "format": "ripe_json",
        }
    ],
    "m247-ips.txt": [
        {
            "name": "ripe-as9009-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS9009",
            "format": "ripe_json",
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
    # ── Riot Games (AS6507) ── LoL, VALORANT, Wild Rift ──────────────
    {
        "key": "riot_games",
        "title": "Riot Games",
        "subtitle": "League of Legends, VALORANT, Wild Rift",
        "asns": [6507],
        "domains": ["riotgames.com", "leagueoflegends.com", "playvalorant.com", "pvp.net"],
    },
    # ── Valve (AS32590) ── Dota 2, CS2, Steam ────────────────────────
    {
        "key": "valve",
        "title": "Valve / Steam",
        "subtitle": "Dota 2, Counter-Strike 2, Steam",
        "asns": [32590],
        "domains": ["steampowered.com", "steamcommunity.com", "steamcontent.com", "steamserver.net", "dota2.com", "counter-strike.net"],
    },
    # ── Blizzard (AS57976) ── WoW, OW2, Hearthstone, Diablo IV ───────
    {
        "key": "blizzard",
        "title": "Blizzard Entertainment",
        "subtitle": "WoW, Overwatch 2, Hearthstone, Diablo IV, StarCraft II",
        "asns": [57976],
        "domains": ["battle.net", "worldofwarcraft.com", "playoverwatch.com", "playhearthstone.com", "diablo.com", "starcraft2.com"],
    },
    # ── Electronic Arts (AS12222) ── Apex, Battlefield, EA FC ─────────
    {
        "key": "electronic_arts",
        "title": "Electronic Arts",
        "subtitle": "Apex Legends, Battlefield, EA Sports FC",
        "asns": [12222],
        "domains": ["ea.com", "respawn.com", "battlefield.com", "easports.com"],
    },
    # ── Wargaming (AS42396, AS35540, AS62317) ─────────────────────────
    {
        "key": "wargaming",
        "title": "Wargaming",
        "subtitle": "World of Tanks, World of Warships, WoT Blitz",
        "asns": [42396, 35540, 62317],
        "domains": ["wargaming.net", "worldoftanks.com", "worldofwarships.com", "wotblitz.com"],
    },
    # ── Lesta Games (AS215859) ── Мир Танков / Мир Кораблей RU ───────
    {
        "key": "lesta_games",
        "title": "Lesta Games",
        "subtitle": "Мир Танков, Мир Кораблей (RU-серверы)",
        "asns": [215859],
        "domains": ["tanki.su", "lesta.ru"],
    },
    # ── Gaijin Entertainment (AS44530) ── War Thunder, Enlisted ──────
    {
        "key": "gaijin",
        "title": "Gaijin Entertainment",
        "subtitle": "War Thunder, Enlisted, Crossout",
        "asns": [44530],
        "domains": ["gaijin.net", "warthunder.com", "enlisted.net", "crossout.net"],
    },
    # ── Krafton (AS263444, AS209242) ── PUBG ──────────────────────────
    {
        "key": "krafton",
        "title": "Krafton",
        "subtitle": "PUBG, PUBG Mobile",
        "asns": [263444, 209242],
        "domains": ["krafton.com", "pubg.com", "pubgmobile.com"],
    },
    # ── miHoYo / HoYoverse (AS45062) ─────────────────────────────────
    {
        "key": "hoyoverse",
        "title": "HoYoverse / miHoYo",
        "subtitle": "Genshin Impact, Honkai: Star Rail, ZZZ",
        "asns": [45062],
        "domains": ["hoyoverse.com", "mihoyo.com", "genshin.hoyoverse.com", "hsr.hoyoverse.com"],
    },
    # ── Bungie (AS36958) ─────────────────────────────────────────────
    {
        "key": "bungie",
        "title": "Bungie",
        "subtitle": "Destiny 2",
        "asns": [36958],
        "domains": ["bungie.net"],
    },
    # ── Sony Interactive Entertainment (AS13213) ─────────────────────
    {
        "key": "sony_playstation",
        "title": "Sony / PlayStation Network",
        "subtitle": "PS4, PS5, PSN, PlayStation Store",
        "asns": [13213],
        "domains": ["playstation.com", "sonyentertainmentnetwork.com", "playstation.net"],
    },
    # ── Microsoft / Xbox / Mojang (AS8075) ───────────────────────────
    {
        "key": "microsoft_xbox",
        "title": "Microsoft / Xbox",
        "subtitle": "Xbox Live, Halo Infinite, Minecraft",
        "asns": [8075],
        "domains": ["xbox.com", "xboxlive.com", "minecraft.net", "mojang.com", "halowaypoint.com"],
    },
    # ── Ubisoft (AS25376) ────────────────────────────────────────────
    {
        "key": "ubisoft",
        "title": "Ubisoft",
        "subtitle": "Rainbow Six Siege, XDefiant, Far Cry, Assassin's Creed",
        "asns": [25376],
        "domains": ["ubisoft.com", "rainbow6.com", "xdefiant.com"],
    },
    # ── Take-Two Interactive (AS46652) ───────────────────────────────
    {
        "key": "take_two",
        "title": "Take-Two Interactive / 2K",
        "subtitle": "NBA 2K, GTA Online, Borderlands",
        "asns": [46652],
        "domains": ["2k.com", "rockstargames.com"],
    },
    # ── Bohemia Interactive (AS56704) ────────────────────────────────
    {
        "key": "bohemia",
        "title": "Bohemia Interactive",
        "subtitle": "DayZ, ARMA",
        "asns": [56704],
        "domains": ["bohemia.net", "dayz.com"],
    },
    # ── Pearl Abyss (AS55967) ────────────────────────────────────────
    {
        "key": "pearl_abyss",
        "title": "Pearl Abyss",
        "subtitle": "Black Desert Online",
        "asns": [55967],
        "domains": ["pearlabyss.com", "blackdesertonline.com"],
    },
    # ── Smilegate (AS38631) ──────────────────────────────────────────
    {
        "key": "smilegate",
        "title": "Smilegate",
        "subtitle": "Lost Ark, CrossFire",
        "asns": [38631],
        "domains": ["smilegate.com", "lostark.com"],
    },
    # ── Plarium (AS213230) ───────────────────────────────────────────
    {
        "key": "plarium",
        "title": "Plarium",
        "subtitle": "RAID: Shadow Legends, Forge of Empires",
        "asns": [213230],
        "domains": ["plarium.com", "raidshadowlegends.com"],
    },
    # ── MY.GAMES / Mail.ru (AS47764) ─────────────────────────────────
    {
        "key": "my_games",
        "title": "MY.GAMES",
        "subtitle": "Warface, Skyforge, Armored Warfare",
        "asns": [47764],
        "domains": ["my.games", "warface.com"],
    },
    # ── Axlebolt (AS212317) ──────────────────────────────────────────
    {
        "key": "axlebolt",
        "title": "Axlebolt",
        "subtitle": "Standoff 2",
        "asns": [212317],
        "domains": ["standoff2.com", "axlebolt.com"],
    },
    # ── Embark Studios (AS201281) ────────────────────────────────────
    {
        "key": "embark_studios",
        "title": "Embark Studios",
        "subtitle": "THE FINALS",
        "asns": [201281],
        "domains": ["reachthefinals.com", "embark-studios.com"],
    },
    # ── Pixonic (AS60890) ────────────────────────────────────────────
    {
        "key": "pixonic",
        "title": "Pixonic",
        "subtitle": "War Robots",
        "asns": [60890],
        "domains": ["warrobots.com", "pixonic.com"],
    },
    # ── Battlestate Games (AS48172) ──────────────────────────────────
    {
        "key": "battlestate",
        "title": "Battlestate Games",
        "subtitle": "Escape from Tarkov, Tarkov Arena",
        "asns": [48172],
        "domains": ["escapefromtarkov.com", "battlestategames.com"],
    },
    # ── NCSoft (AS9318) ──────────────────────────────────────────────
    {
        "key": "ncsoft",
        "title": "NCSoft",
        "subtitle": "Lineage 2, Guild Wars 2, Blade and Soul",
        "asns": [9318],
        "domains": ["ncsoft.com", "lineage2.com", "guildwars2.com"],
    },
    # ── Garena / Sea Group (AS38561) ─────────────────────────────────
    {
        "key": "garena",
        "title": "Garena / Sea Group",
        "subtitle": "Free Fire, Arena of Valor",
        "asns": [38561],
        "domains": ["garena.com", "ff.garena.com"],
    },
    # ── Epic Games (AS14593) ─────────────────────────────────────────
    {
        "key": "epic_games",
        "title": "Epic Games",
        "subtitle": "Fortnite, Rocket League, Epic Games Store",
        "asns": [14593],
        "domains": ["epicgames.com", "fortnite.com", "rocketleague.com"],
    },
    # ── FACEIT (AS212238) ────────────────────────────────────────────
    {
        "key": "faceit",
        "title": "FACEIT",
        "subtitle": "Платформа для CS2, Dota 2 и других",
        "asns": [212238],
        "domains": ["faceit.com", "faceit-cdn.net", "faceitusercontent.com"],
    },
    # ── Supercell (DNS) ──────────────────────────────────────────────
    {
        "key": "supercell",
        "title": "Supercell",
        "subtitle": "Clash of Clans, Clash Royale, Brawl Stars",
        "asns": [],
        "domains": ["supercell.com", "clashofclans.com", "clashroyale.com", "brawlstars.com"],
    },
    # ── Activision / King (DNS) ──────────────────────────────────────
    {
        "key": "activision",
        "title": "Activision",
        "subtitle": "Call of Duty: Warzone, CoD Mobile",
        "asns": [],
        "domains": ["activision.com", "callofduty.com"],
    },
    # ── Roblox Corporation (DNS) ─────────────────────────────────────
    {
        "key": "roblox",
        "title": "Roblox Corporation",
        "subtitle": "Roblox",
        "asns": [],
        "domains": ["roblox.com", "rbxcdn.com"],
    },
    # ── Kuro Games (DNS) ─────────────────────────────────────────────
    {
        "key": "kuro_games",
        "title": "Kuro Games",
        "subtitle": "Wuthering Waves",
        "asns": [],
        "domains": ["kurogames.com", "wutheringwaves.com"],
    },
    # ── Moonton / ByteDance (DNS) ────────────────────────────────────
    {
        "key": "moonton",
        "title": "Moonton / ByteDance",
        "subtitle": "Mobile Legends: Bang Bang",
        "asns": [],
        "domains": ["moonton.com", "mobilelegends.com"],
    },
    # ── Digital Extremes (DNS) ───────────────────────────────────────
    {
        "key": "digital_extremes",
        "title": "Digital Extremes",
        "subtitle": "Warframe",
        "asns": [],
        "domains": ["warframe.com", "digitalextremes.com"],
    },
    # ── Gameforge (DNS) ──────────────────────────────────────────────
    {
        "key": "gameforge",
        "title": "Gameforge",
        "subtitle": "Metin2, NosTale, Soulworker",
        "asns": [],
        "domains": ["gameforge.com", "metin2.gameforge.com"],
    },
    # ── Sandbox Interactive (DNS) ────────────────────────────────────
    {
        "key": "sandbox_interactive",
        "title": "Sandbox Interactive",
        "subtitle": "Albion Online",
        "asns": [],
        "domains": ["albiononline.com", "sandbox-interactive.com"],
    },
    # ── Square Enix (DNS) ────────────────────────────────────────────
    {
        "key": "square_enix",
        "title": "Square Enix",
        "subtitle": "Final Fantasy XIV, Dragon Quest",
        "asns": [],
        "domains": ["square-enix.com", "finalfantasyxiv.com"],
    },
    # ── ZeniMax / Bethesda (DNS) ─────────────────────────────────────
    {
        "key": "bethesda",
        "title": "ZeniMax / Bethesda",
        "subtitle": "Elder Scrolls Online, Fallout 76",
        "asns": [],
        "domains": ["bethesda.net", "elderscrollsonline.com"],
    },
    # ── Grinding Gear Games (DNS) ────────────────────────────────────
    {
        "key": "grinding_gear",
        "title": "Grinding Gear Games",
        "subtitle": "Path of Exile, Path of Exile 2",
        "asns": [],
        "domains": ["pathofexile.com", "grindinggear.com"],
    },
    # ── Facepunch Studios (DNS) ──────────────────────────────────────
    {
        "key": "facepunch",
        "title": "Facepunch Studios",
        "subtitle": "Rust",
        "asns": [],
        "domains": ["facepunch.com", "rust.facepunch.com"],
    },
    # ── InnerSloth (DNS) ─────────────────────────────────────────────
    {
        "key": "innersloth",
        "title": "InnerSloth",
        "subtitle": "Among Us",
        "asns": [],
        "domains": ["innersloth.com", "among.us"],
    },
]
GAME_FILTER_ALIASES = {
    # старые ключи игр → новые ключи издательств
    "lol": "riot_games",
    "valorant": "riot_games",
    "dota2": "valve",
    "dota": "valve",
    "cs2": "valve",
    "csgo": "valve",
    "counter-strike": "valve",
    "counter_strike": "valve",
    "steam_platform": "valve",
    "world_of_warcraft": "blizzard",
    "overwatch2": "blizzard",
    "hearthstone": "blizzard",
    "diablo4": "blizzard",
    "starcraft2": "blizzard",
    "heroes_of_the_storm": "blizzard",
    "apex_legends": "electronic_arts",
    "battlefield": "electronic_arts",
    "ea_fc": "electronic_arts",
    "world_of_tanks": "wargaming",
    "wot": "wargaming",
    "world_of_tanks_blitz": "wargaming",
    "wotb": "wargaming",
    "world_of_warships": "wargaming",
    "wows": "wargaming",
    "mir_tankov": "lesta_games",
    "war_thunder": "gaijin",
    "enlisted": "gaijin",
    "crossout": "gaijin",
    "pubg": "krafton",
    "pubg_mobile": "krafton",
    "genshin_impact": "hoyoverse",
    "honkai_star_rail": "hoyoverse",
    "destiny2": "bungie",
    "playstation_network": "sony_playstation",
    "xbox_live": "microsoft_xbox",
    "halo_infinite": "microsoft_xbox",
    "minecraft": "microsoft_xbox",
    "rainbow6": "ubisoft",
    "xdefiant": "ubisoft",
    "nba_2k": "take_two",
    "dayz": "bohemia",
    "black_desert": "pearl_abyss",
    "lost_ark": "smilegate",
    "raid_shadow_legends": "plarium",
    "warface": "my_games",
    "standoff2": "axlebolt",
    "the_finals": "embark_studios",
    "war_robots": "pixonic",
    "escape_from_tarkov": "battlestate",
    "tarkov_arena": "battlestate",
    "tarkov": "battlestate",
    "lineage2": "ncsoft",
    "free_fire": "garena",
    "fortnite": "epic_games",
    "epic_games_store": "epic_games",
    "rocket_league": "epic_games",
    "warframe": "digital_extremes",
    "wuthering_waves": "kuro_games",
    "mobile_legends": "moonton",
    "clash_of_clans": "supercell",
    "clash_royale": "supercell",
    "brawl_stars": "supercell",
    "cod_mobile": "activision",
    "warzone": "activision",
    "among_us": "innersloth",
    "albion_online": "sandbox_interactive",
    "final_fantasy_xiv": "square_enix",
    "elder_scrolls_online": "bethesda",
    "path_of_exile": "grinding_gear",
    "rust": "facepunch",
    "metin2": "gameforge",
    "point_blank": "ncsoft",
    "league-of-legends": "riot_games",
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


DPI_NODE_CODE_TO_FILE = {
    "AKM": "akamai-ips.txt",
    "AWS": "amazon-ips.txt",
    "CDN77": "cdn77-ips.txt",
    "CF": "cloudflare-ips.txt",
    "DO": "digitalocean-ips.txt",
    "FST": "fastly-ips.txt",
    "GC": "google-ips.txt",
    "HE": "hetzner-ips.txt",
    "ME": "m247-ips.txt",
    "MS": "azure-ips.txt",
    "OR": "oracle-ips.txt",
    "OVH": "ovh-ips.txt",
}

DPI_PROVIDER_TO_FILE = {
    "Akamai": "akamai-ips.txt",
    "AWS": "amazon-ips.txt",
    "CDN77": "cdn77-ips.txt",
    "Cloudflare": "cloudflare-ips.txt",
    "DigitalOcean": "digitalocean-ips.txt",
    "Fastly": "fastly-ips.txt",
    "Google Cloud": "google-ips.txt",
    "Hetzner": "hetzner-ips.txt",
    "M247 Europe SRL": "m247-ips.txt",
    "Microsoft/Azure": "azure-ips.txt",
    "Oracle": "oracle-ips.txt",
    "OVH": "ovh-ips.txt",
}


def _normalize_provider_name_token(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


DPI_PROVIDER_ALIASES = {
    "aws": "amazon-ips.txt",
    "amazon": "amazon-ips.txt",
    "amazonaws": "amazon-ips.txt",
    "azure": "azure-ips.txt",
    "microsoft": "azure-ips.txt",
    "microsoftazure": "azure-ips.txt",
    "google": "google-ips.txt",
    "googlecloud": "google-ips.txt",
    "gcp": "google-ips.txt",
    "m247": "m247-ips.txt",
}
for _provider_name, _file_name in DPI_PROVIDER_TO_FILE.items():
    _alias = _normalize_provider_name_token(_provider_name)
    if _alias and _alias not in DPI_PROVIDER_ALIASES:
        DPI_PROVIDER_ALIASES[_alias] = _file_name


def _provider_name_to_file(provider_name):
    token = _normalize_provider_name_token(provider_name)
    if not token:
        return None

    if token in DPI_PROVIDER_ALIASES:
        return DPI_PROVIDER_ALIASES[token]

    for alias, file_name in DPI_PROVIDER_ALIASES.items():
        if token.startswith(alias) or alias.startswith(token):
            return file_name
    return None


def _normalize_dpi_severity(value):
    text = str(value or "").strip().lower()
    if not text:
        return "unknown", -1

    if text == "ok" or text.startswith("ok "):
        return "not_detected", 0
    if "not detected" in text:
        return "not_detected", 0
    if "unlikely" in text:
        return "unlikely", 1
    if ("possible" in text or "probably" in text) and "detected" in text:
        return "possible_detected", 2
    if "detected" in text:
        return "detected", 3

    return "unknown", -1


def _dpi_node_id_to_file(node_id):
    cyrillic_homoglyphs = str.maketrans(
        {
            "А": "A",
            "В": "B",
            "С": "C",
            "Е": "E",
            "К": "K",
            "М": "M",
            "Н": "H",
            "О": "O",
            "Р": "P",
            "Т": "T",
            "У": "Y",
            "Х": "X",
        }
    )

    value = str(node_id or "").strip().upper().translate(cyrillic_homoglyphs).lstrip("#")
    if not value:
        return None

    tokens = [item for item in re.split(r"[\.\-_/:\s]+", value) if item]
    for token in tokens:
        file_name = DPI_NODE_CODE_TO_FILE.get(token)
        if file_name:
            return file_name

    if "." in value:
        value = value.split(".", 1)[1]

    code = value.split("-", 1)[0]
    return DPI_NODE_CODE_TO_FILE.get(code)


def analyze_dpi_log(dpi_log_text):
    text = str(dpi_log_text or "")
    if not text.strip():
        return {
            "success": False,
            "message": "Лог DPI пуст",
            "summary": {},
            "nodes": [],
            "providers": [],
            "priority_files": [],
            "critical_files": [],
            "unknown_nodes": [],
        }

    node_pattern = re.compile(r"DPI\s*checking\s*\(\s*#?([^\)]+)\s*\)", re.IGNORECASE)
    status_pattern = re.compile(r"tcp\s*16\s*[-–—]\s*20\s*:\s*([^\n\r]+)", re.IGNORECASE)
    provider_pattern = re.compile(r"provider\s*[:=]\s*([^,\n\r\]]+)", re.IGNORECASE)
    table_row_pattern = re.compile(
        r"^\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*$"
    )

    node_events = {}
    unknown_nodes = set()

    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue

        node_match = node_pattern.search(line)
        table_match = table_row_pattern.match(line)

        node_id = ""
        file_name = None
        status_text = ""

        if node_match:
            node_id = str(node_match.group(1) or "").strip()
            if not node_id:
                continue

            file_name = _dpi_node_id_to_file(node_id)
            if not file_name:
                provider_match = provider_pattern.search(line)
                provider_name = str(provider_match.group(1) or "").strip() if provider_match else ""
                if provider_name:
                    file_name = _provider_name_to_file(provider_name)

            if not file_name:
                normalized_line = _normalize_provider_name_token(line)
                for alias, mapped_file in DPI_PROVIDER_ALIASES.items():
                    if alias and alias in normalized_line:
                        file_name = mapped_file
                        break

            status_match = status_pattern.search(line)
            if not status_match:
                continue

            status_text = str(status_match.group(1) or "").strip()
        elif table_match:
            node_id = str(table_match.group(1) or "").strip()
            provider_name = str(table_match.group(3) or "").strip()
            status_text = str(table_match.group(5) or "").strip()

            node_id_lower = node_id.lower()
            status_lower = status_text.lower()
            if node_id_lower in {"id", "ид"} or status_lower in {"status", "статус"}:
                continue

            if not node_id or not status_text:
                continue

            file_name = _dpi_node_id_to_file(node_id)
            if not file_name and provider_name:
                file_name = _provider_name_to_file(provider_name)

            if not file_name:
                normalized_provider = _normalize_provider_name_token(provider_name)
                for alias, mapped_file in DPI_PROVIDER_ALIASES.items():
                    if alias and alias in normalized_provider:
                        file_name = mapped_file
                        break
        else:
            continue

        severity_key, severity_score = _normalize_dpi_severity(status_text)
        event = node_events.get(node_id)
        if event is None or severity_score > event.get("severity_score", -1):
            node_events[node_id] = {
                "node_id": node_id,
                "file": file_name,
                "severity": severity_key,
                "severity_score": severity_score,
                "status_text": status_text,
            }

        if not file_name:
            unknown_nodes.add(node_id)

    if not node_events:
        return {
            "success": False,
            "message": "В логе не найдены результаты tcp 16-20",
            "summary": {},
            "nodes": [],
            "providers": [],
            "priority_files": [],
            "critical_files": [],
            "unknown_nodes": [],
        }

    provider_stats = {}
    nodes = sorted(node_events.values(), key=lambda item: item["node_id"])
    for item in nodes:
        file_name = item.get("file")
        if not file_name:
            continue

        stats = provider_stats.setdefault(
            file_name,
            {
                "file": file_name,
                "max_severity_score": -1,
                "detected": 0,
                "possible_detected": 0,
                "unlikely": 0,
                "not_detected": 0,
                "nodes": 0,
            },
        )
        stats["nodes"] += 1
        stats[item["severity"]] = stats.get(item["severity"], 0) + 1
        stats["max_severity_score"] = max(stats["max_severity_score"], item["severity_score"])

    providers = sorted(
        provider_stats.values(),
        key=lambda item: (-item["max_severity_score"], -item["nodes"], item["file"]),
    )
    all_seen_files = [item["file"] for item in providers]
    detected_files = [item["file"] for item in providers if item["max_severity_score"] >= 3]
    priority_files = [item["file"] for item in providers if item["max_severity_score"] >= 1]
    critical_files = [item["file"] for item in providers if item["max_severity_score"] >= 2]

    return {
        "success": True,
        "message": "DPI лог обработан",
        "summary": {
            "total_nodes": len(nodes),
            "matched_nodes": sum(1 for item in nodes if item.get("file")),
            "unknown_nodes": len(unknown_nodes),
            "all_seen_files": len(all_seen_files),
            "detected_files": len(detected_files),
            "priority_files": len(priority_files),
            "critical_files": len(critical_files),
        },
        "nodes": nodes,
        "providers": providers,
        "all_seen_files": all_seen_files,
        "detected_files": detected_files,
        "priority_files": priority_files,
        "critical_files": critical_files,
        "unknown_nodes": sorted(unknown_nodes),
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
    for filepath in (GAME_INCLUDE_HOSTS_FILE, GAME_INCLUDE_IPS_FILE):
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
            text = _download_text(url)
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


def _download_ru_country_cidrs(timeout=30):
    text_data = _download_text(RU_COUNTRY_CIDR_SOURCE_URL, timeout=timeout)
    cidr_candidates = []
    for line in (text_data or "").splitlines():
        value = str(line or "").strip()
        if not value or value.startswith("#"):
            continue
        cidr_candidates.append(value)
    return _normalize_cidrs(cidr_candidates)


def _get_ru_cidr_index():
    """Return O(log n)-queryable interval index for RU networks, with 12-hour cache."""
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
    if not cidrs:
        return cidrs, None

    ru_index, error_text = _get_ru_cidr_index()
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
        dns_cidrs, unresolved = _resolve_game_domains_ipv4_cidrs(list(dict.fromkeys(dns_fallback_domains)))
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
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
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

    # Phase 1: resolve which files to download and their effective scopes
    download_jobs = []  # [(file_name, sources, effective_scopes)]
    for file_name in normalized:
        sources = PROVIDER_SOURCES.get(file_name) or []
        if not sources:
            skipped.append({"file": file_name, "reason": "source_not_configured"})
            continue

        effective_scopes = list(normalized_scopes)
        if not is_all_scope:
            if not _supports_geo_scope(sources):
                if include_non_geo_fallback:
                    effective_scopes = ["all"]
                else:
                    skipped.append({"file": file_name, "reason": "geo_scope_not_supported"})
                    continue

        download_jobs.append((file_name, sources, effective_scopes))

    # Phase 2: parallel HTTP downloads
    download_results = {}  # file_name -> (cidrs, source_name, last_error)
    _emit_progress(progress_callback, 10, f"Скачивание {len(download_jobs)} провайдеров параллельно…")
    if download_jobs:
        max_workers = min(len(download_jobs), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_file = {
                pool.submit(
                    _collect_cidrs_from_sources, sources, effective_scopes,
                    strict_geo_filter=bool(strict_geo_filter)
                ): file_name
                for file_name, sources, effective_scopes in download_jobs
            }
            completed = 0
            for future in as_completed(future_to_file):
                file_name = future_to_file[future]
                completed += 1
                pct = 10 + int((completed / len(download_jobs)) * 50)
                _emit_progress(progress_callback, pct, f"Загружен {file_name} ({completed}/{len(download_jobs)})")
                try:
                    download_results[file_name] = future.result()
                except Exception as exc:  # noqa: BLE001
                    download_results[file_name] = ([], "", str(exc))

    # Phase 3: post-process in original order
    for index, (file_name, sources, effective_scopes) in enumerate(download_jobs, start=1):
        progress_start = 60 + int(((index - 1) / max(len(download_jobs), 1)) * 32)
        _emit_progress(progress_callback, progress_start, f"Обработка {file_name}")

        cidrs, source_name, last_error = download_results.get(file_name, ([], "", "download missing"))
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

        planned_updates.append(
            {
                "file": file_name,
                "cidrs": cidrs,
                "source": source_name,
                "country_exclusion": country_exclusion_meta,
                "route_optimization": optimization_meta,
            }
        )
        _emit_progress(progress_callback, progress_start, f"Файл {file_name} готов: {len(cidrs)} CIDR")

    planned_updates, global_route_optimization_meta = _apply_total_route_limit(
        planned_updates,
        _get_openvpn_route_total_cidr_limit(),
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
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
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
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

    pre_limit_counts_by_file = {
        item["file"]: len(item.get("cidrs") or [])
        for item in planned_estimated
    }

    planned_estimated, global_route_optimization_meta = _apply_total_route_limit(
        planned_estimated,
        _get_openvpn_route_total_cidr_limit(),
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )

    for item in planned_estimated:
        post_limit_count = len(item.get("cidrs") or [])
        pre_limit_count = int(pre_limit_counts_by_file.get(item["file"], post_limit_count))
        estimated_item = {
            "file": item["file"],
            "cidr_count": post_limit_count,
            "raw_cidr_count": pre_limit_count,
            "cidr_count_after_limit": post_limit_count,
            "source": item.get("source") or "unknown",
        }
        if pre_limit_count != post_limit_count:
            estimated_item["limit_applied"] = True
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


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed CIDR file generation
# ─────────────────────────────────────────────────────────────────────────────

def _build_antifilter_overlap_index(cidr_strs):
    """Build sorted ranges + prefix-max-end array for O(log n) overlap queries.

    Returns (ranges, starts, max_ends) where:
      ranges    = sorted list of (start_int, end_int)
      starts    = [r[0] for r in ranges]  (for bisect)
      max_ends  = prefix-max of end values so max_ends[i] = max(e for ranges[0..i])
    """
    ranges = []
    for c in cidr_strs:
        try:
            net = ipaddress.ip_network(c, strict=False)
            if net.prefixlen > 0:
                ranges.append((int(net.network_address), int(net.broadcast_address)))
        except ValueError:
            pass
    ranges.sort()
    starts = [r[0] for r in ranges]
    max_ends = []
    cur = -1
    for _, e in ranges:
        cur = max(cur, e)
        max_ends.append(cur)
    return ranges, starts, max_ends


def _cidr_overlaps_index(cidr_str, ranges, starts, max_ends):
    """O(log n) overlap check: does cidr_str overlap with any range in the index?"""
    if not ranges:
        return False
    try:
        net = ipaddress.ip_network(cidr_str, strict=False)
        ps = int(net.network_address)
        pe = int(net.broadcast_address)
        idx = bisect.bisect_right(starts, pe) - 1
        if idx < 0:
            return False
        # max_ends[idx] = max end among all ranges whose start <= pe
        # if that max end >= ps, at least one range overlaps [ps, pe]
        return max_ends[idx] >= ps
    except ValueError:
        return False


def _cidr_contained_in_index(cidr_str, ranges, starts, max_ends):
    """O(log n) containment check: is cidr_str a subnet of ANY range in the index?

    A CIDR [ps, pe] is contained in range [rs, re] when rs <= ps AND re >= pe.
    Using the prefix-max-end array: find rightmost range with start <= ps,
    then check if its max_end >= pe.
    """
    if not ranges:
        return False
    try:
        net = ipaddress.ip_network(cidr_str, strict=False)
        ps = int(net.network_address)
        pe = int(net.broadcast_address)
        idx = bisect.bisect_right(starts, ps) - 1
        if idx < 0:
            return False
        return max_ends[idx] >= pe
    except ValueError:
        return False


def _load_antifilter_index():
    """Load antifilter index from DB (5-minute in-process cache)."""
    now_ts = time.time()
    if _ANTIFILTER_INDEX_CACHE["index"] is not None and now_ts < float(_ANTIFILTER_INDEX_CACHE["expires_at"]):
        return _ANTIFILTER_INDEX_CACHE["index"]

    from core.models import AntifilterCidr, AntifilterMeta
    meta = AntifilterMeta.query.first()
    if not meta or meta.refresh_status not in ("ok", "partial") or (meta.cidr_count or 0) == 0:
        return None
    rows = AntifilterCidr.query.with_entities(AntifilterCidr.cidr).all()
    index = _build_antifilter_overlap_index([r.cidr for r in rows])
    _ANTIFILTER_INDEX_CACHE["index"] = index
    _ANTIFILTER_INDEX_CACHE["expires_at"] = now_ts + 300.0
    return index


def update_cidr_files_from_db(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
    filter_by_antifilter=False,
    total_cidr_limit=None,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
    progress_callback=None,
):
    """Generate CIDR route files by reading provider data from the local DB.

    Unlike update_cidr_files(), this function does NOT download anything —
    it relies on data previously loaded by CidrDbUpdaterService.refresh_all_providers().
    """
    from core.models import ProviderCidr, ProviderMeta

    _emit_progress(progress_callback, 2, "Подготовка: чтение данных из БД")
    _snapshot_baseline_if_missing()

    # Load antifilter index once (if requested) before processing files
    af_index = None
    if filter_by_antifilter:
        _emit_progress(progress_callback, 4, "Загрузка антифильтра из БД…")
        af_index = _load_antifilter_index()
        if af_index is None:
            _emit_progress(progress_callback, 100, "Ошибка: антифильтр не загружен в БД")
            return {
                "success": False,
                "message": "Фильтр по антифильтру запрошен, но БД антифильтра пуста. Сначала обновите антифильтр.",
                "updated": [],
                "failed": [],
                "skipped": [],
            }

    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    if not normalized:
        _emit_progress(progress_callback, 100, "Нет файлов для обновления")
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
    failed = []
    skipped = []
    quality_by_file = {}
    total_files = len(normalized)

    # Single bulk query for all provider metadata and CIDR rows
    all_meta = {
        pm.provider_key: pm
        for pm in ProviderMeta.query.filter(ProviderMeta.provider_key.in_(normalized)).all()
    }
    _emit_progress(progress_callback, 9, "Загрузка CIDR из БД…")
    all_rows_by_provider: dict = {}
    for row in (
        ProviderCidr.query
        .filter(ProviderCidr.provider_key.in_(normalized))
        .with_entities(ProviderCidr.provider_key, ProviderCidr.cidr,
                       ProviderCidr.region_scope, ProviderCidr.country_codes)
        .all()
    ):
        all_rows_by_provider.setdefault(row.provider_key, []).append(row)

    for index, file_name in enumerate(normalized, start=1):
        progress_start = 10 + int(((index - 1) / max(total_files, 1)) * 82)
        _emit_progress(progress_callback, progress_start, f"Обработка {file_name} из БД")

        file_quality = {
            "raw_db_count": 0,
            "after_scope_count": 0,
            "after_ru_exclusion_count": 0,
            "after_antifilter_count": 0,
            "final_after_limit_count": 0,
            "status": "pending",
            "skip_reason": None,
        }

        meta = all_meta.get(file_name)
        if not meta or meta.refresh_status not in ("ok", "partial") or meta.cidr_count == 0:
            reason = "no_db_data" if (not meta or meta.cidr_count == 0) else f"db_status:{meta.refresh_status}"
            skipped.append({"file": file_name, "reason": reason})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = reason
            quality_by_file[file_name] = file_quality
            _emit_progress(progress_callback, progress_start, f"Файл {file_name} пропущен: {reason}")
            continue

        rows = all_rows_by_provider.get(file_name) or []
        file_quality["raw_db_count"] = len(rows)

        if is_all_scope:
            cidrs = [row.cidr for row in rows]
        else:
            cidrs = []
            for row in rows:
                has_region = row.region_scope is not None
                has_countries = row.country_codes is not None

                if has_region:
                    if not _matches_region_scope(row.region_scope, normalized_scopes):
                        continue
                    if strict_geo_filter and not _matches_strict_scope_value(row.region_scope, normalized_scopes):
                        continue
                    cidrs.append(row.cidr)
                elif has_countries:
                    countries = row.country_codes.split(",")
                    if not any(_matches_country_scope(c, normalized_scopes) for c in countries):
                        continue
                    if strict_geo_filter and not _is_strict_geo_country_set(set(countries)):
                        continue
                    cidrs.append(row.cidr)
                else:
                    if include_non_geo_fallback:
                        cidrs.append(row.cidr)

        # Extra safety: enforce IPv4-only output even if legacy DB rows contain IPv6.
        cidrs = _normalize_cidrs(cidrs)
        file_quality["after_scope_count"] = len(cidrs)

        if not cidrs:
            skipped.append({"file": file_name, "reason": "empty_after_geo_filter"})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = "empty_after_geo_filter"
            quality_by_file[file_name] = file_quality
            _emit_progress(progress_callback, progress_start, f"Файл {file_name} пропущен: empty_after_geo_filter")
            continue

        country_exclusion_meta = None
        if exclude_ru_cidrs:
            cidrs, country_exclusion_meta = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                file_quality["after_ru_exclusion_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_ru_exclusion"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_ru_exclusion_count"] = len(cidrs)
        else:
            file_quality["after_ru_exclusion_count"] = len(cidrs)

        antifilter_meta = None
        if af_index is not None:
            before = len(cidrs)
            cidrs = [c for c in cidrs if _cidr_overlaps_index(c, *af_index)]
            antifilter_meta = {"before": before, "after": len(cidrs)}
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_antifilter"})
                file_quality["after_antifilter_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_antifilter"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_antifilter_count"] = len(cidrs)
        else:
            file_quality["after_antifilter_count"] = len(cidrs)

        planned_updates.append({
            "file": file_name,
            "cidrs": cidrs,
            "source": f"db:{meta.source_used or 'unknown'}",
            "country_exclusion": country_exclusion_meta,
            "antifilter": antifilter_meta,
        })
        file_quality["status"] = "planned"
        quality_by_file[file_name] = file_quality

        progress_done = 10 + int((index / max(total_files, 1)) * 82)
        _emit_progress(progress_callback, progress_done, f"Файл {file_name}: {len(cidrs)} CIDR из БД")

    effective_limit = int(total_cidr_limit) if total_cidr_limit and int(total_cidr_limit) > 0 else _get_openvpn_route_total_cidr_limit()
    planned_updates, global_route_optimization_meta = _apply_total_route_limit(
        planned_updates,
        effective_limit,
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )

    os.makedirs(LIST_DIR, exist_ok=True)
    updated = []
    final_counts_by_file = {}

    for item in planned_updates:
        file_name = item["file"]
        cidrs = item.get("cidrs") or []
        source_name = item.get("source") or "db"
        final_counts_by_file[file_name] = len(cidrs)

        out_path = os.path.join(LIST_DIR, file_name)
        content = _render_file_content(file_name, cidrs, source_name)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(content)

        updated_item = {"file": file_name, "cidr_count": len(cidrs), "source": source_name}
        if item.get("country_exclusion"):
            updated_item["country_exclusion"] = item["country_exclusion"]
        if item.get("global_route_optimization"):
            updated_item["global_route_optimization"] = item["global_route_optimization"]
        updated.append(updated_item)

    for file_name in normalized:
        file_quality = quality_by_file.setdefault(
            file_name,
            {
                "raw_db_count": 0,
                "after_scope_count": 0,
                "after_ru_exclusion_count": 0,
                "after_antifilter_count": 0,
                "final_after_limit_count": 0,
                "status": "skipped",
                "skip_reason": "not_processed",
            },
        )
        file_quality["final_after_limit_count"] = int(final_counts_by_file.get(file_name, 0))
        if file_quality["status"] == "planned":
            if file_quality["final_after_limit_count"] > 0:
                file_quality["status"] = "updated"
                file_quality["skip_reason"] = None
            else:
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_total_limit"

    _emit_progress(progress_callback, 100, "Генерация CIDR-файлов из БД завершена")

    success = bool(updated)
    if updated and (failed or skipped):
        message = "CIDR-файлы обновлены из БД (часть пропущена или с ошибкой)"
    elif updated:
        message = "CIDR-файлы успешно обновлены из БД"
    elif failed:
        message = "Не удалось обновить CIDR-файлы из БД"
    else:
        message = "Нет данных в БД для обновления"

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
        "quality_report": {
            "providers": quality_by_file,
            "totals": {
                "requested_files": len(normalized),
                "raw_db_cidrs": sum(int(item.get("raw_db_count") or 0) for item in quality_by_file.values()),
                "after_scope_cidrs": sum(int(item.get("after_scope_count") or 0) for item in quality_by_file.values()),
                "after_ru_exclusion_cidrs": sum(int(item.get("after_ru_exclusion_count") or 0) for item in quality_by_file.values()),
                "after_antifilter_cidrs": sum(int(item.get("after_antifilter_count") or 0) for item in quality_by_file.values()),
                "final_after_limit_cidrs": sum(int(item.get("final_after_limit_count") or 0) for item in quality_by_file.values()),
            },
            "dropped_mandatory_files": ((global_route_optimization_meta or {}).get("dpi_mandatory") or {}).get("dropped_mandatory_files", []),
            "warnings": [
                warning
                for warning in [
                    (global_route_optimization_meta or {}).get("warning"),
                ]
                if warning
            ],
        },
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    return result


def estimate_cidr_matches_from_db(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
    filter_by_antifilter=False,
    total_cidr_limit=None,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
    progress_callback=None,
):
    """Preview how many CIDRs would be written from DB, without modifying any files."""
    from core.models import ProviderCidr, ProviderMeta

    def _report_progress(percent, stage):
        if not callable(progress_callback):
            return
        try:
            progress_callback(percent, stage)
        except Exception:
            return

    _report_progress(3, "Подготовка оценки CIDR из БД...")

    def _apply_total_route_limit_counts(counts_by_file):
        route_limit = int(total_cidr_limit) if total_cidr_limit and int(total_cidr_limit) > 0 else _get_openvpn_route_total_cidr_limit()
        if route_limit is None or int(route_limit) <= 0:
            return dict(counts_by_file), None

        ordered_files = list(counts_by_file.keys())
        original_total = sum(int(counts_by_file.get(name) or 0) for name in ordered_files)
        if original_total <= int(route_limit):
            return dict(counts_by_file), None

        route_limit = int(route_limit)
        counts = [int(counts_by_file.get(name) or 0) for name in ordered_files]
        non_empty_indices = [idx for idx, value in enumerate(counts) if value > 0]
        if not non_empty_indices:
            return dict(counts_by_file), None

        priority_files = set(_normalize_dpi_priority_files(dpi_priority_files))
        mandatory_files = set(_normalize_dpi_priority_files(dpi_mandatory_files))
        priority_files.update(mandatory_files)
        priority_min_budget = _normalize_priority_min_budget(dpi_priority_min_budget)

        budgets = {idx: 0 for idx in non_empty_indices}

        if route_limit < len(non_empty_indices):
            prioritized_indices = sorted(non_empty_indices, key=lambda idx: counts[idx], reverse=True)

            if mandatory_files:
                mandatory_first = sorted(
                    [
                        idx for idx in non_empty_indices
                        if ordered_files[idx] in mandatory_files
                    ],
                    key=lambda idx: counts[idx],
                    reverse=True,
                )
                fallback_rest = [idx for idx in prioritized_indices if idx not in mandatory_first]
                prioritized_indices = mandatory_first + fallback_rest
            elif priority_files and priority_min_budget > 0:
                priority_first = [idx for idx in non_empty_indices if ordered_files[idx] in priority_files]
                fallback_rest = [idx for idx in prioritized_indices if idx not in priority_first]
                prioritized_indices = priority_first + fallback_rest

            allowed_indices = set(prioritized_indices[:route_limit])
            for idx in non_empty_indices:
                budgets[idx] = 1 if idx in allowed_indices else 0
        else:
            reserved_total = 0

            if mandatory_files:
                for idx in non_empty_indices:
                    if ordered_files[idx] not in mandatory_files:
                        continue
                    budgets[idx] = max(budgets[idx], 1)
                    reserved_total += 1

            if reserved_total > route_limit:
                mandatory_indices = sorted(
                    [idx for idx in non_empty_indices if ordered_files[idx] in mandatory_files],
                    key=lambda idx: counts[idx],
                    reverse=True,
                )
                budgets = {idx: 0 for idx in non_empty_indices}
                allocated = 0
                for idx in mandatory_indices:
                    if allocated >= route_limit:
                        break
                    budgets[idx] = 1
                    allocated += 1
                reserved_total = allocated

            if priority_files and priority_min_budget > 0:
                for idx in non_empty_indices:
                    if ordered_files[idx] not in priority_files:
                        continue
                    reserved = min(counts[idx], priority_min_budget)
                    new_budget = max(budgets[idx], reserved)
                    reserved_total += max(0, new_budget - budgets[idx])
                    budgets[idx] = new_budget

            if reserved_total > route_limit:
                priority_indices = sorted(
                    [idx for idx in non_empty_indices if ordered_files[idx] in priority_files],
                    key=lambda idx: counts[idx],
                    reverse=True,
                )
                budgets = {idx: 0 for idx in non_empty_indices}
                allocated = 0
                for idx in priority_indices:
                    if allocated >= route_limit:
                        break
                    budgets[idx] = 1
                    allocated += 1
                reserved_total = allocated

            remaining_limit = max(route_limit - reserved_total, 0)
            remaining_capacity = {idx: max(0, counts[idx] - budgets[idx]) for idx in non_empty_indices}
            total_capacity = sum(remaining_capacity.values())
            raw_shares = {}

            if remaining_limit > 0 and total_capacity > 0:
                for idx in non_empty_indices:
                    capacity = remaining_capacity[idx]
                    if capacity <= 0:
                        raw_shares[idx] = 0.0
                        continue
                    share = (capacity * remaining_limit) / total_capacity
                    raw_shares[idx] = share
                    budgets[idx] += min(capacity, int(share))

                allocated = sum(budgets.values())
                if allocated > route_limit:
                    for idx, _ in sorted(budgets.items(), key=lambda pair: pair[1], reverse=True):
                        while budgets[idx] > 0 and allocated > route_limit:
                            budgets[idx] -= 1
                            allocated -= 1
                        if allocated <= route_limit:
                            break

                if allocated < route_limit:
                    for idx, _ in sorted(raw_shares.items(), key=lambda pair: pair[1] - int(pair[1]), reverse=True):
                        upper_bound = counts[idx]
                        while budgets[idx] < upper_bound and allocated < route_limit:
                            budgets[idx] += 1
                            allocated += 1
                        if allocated >= route_limit:
                            break

        compressed_counts_by_file = {}
        per_file = []
        for idx, file_name in enumerate(ordered_files):
            original_count = counts[idx]
            target_budget = budgets.get(idx, original_count)
            compressed_count = min(original_count, max(0, int(target_budget)))
            compressed_counts_by_file[file_name] = compressed_count
            per_file.append(
                {
                    "file": file_name,
                    "original_cidr_count": original_count,
                    "compressed_cidr_count": compressed_count,
                    "target_budget": int(target_budget),
                    "dpi_priority": bool(file_name in priority_files),
                    "dpi_mandatory": bool(file_name in mandatory_files),
                }
            )

        compressed_total = sum(compressed_counts_by_file.values())
        present_mandatory_files = {
            file_name for file_name, count in compressed_counts_by_file.items()
            if file_name in mandatory_files and count > 0
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
        return compressed_counts_by_file, meta

    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    af_index = None
    if filter_by_antifilter:
        af_index = _load_antifilter_index()

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

    planned_estimated = []
    failed = []
    skipped = []
    quality_by_file = {}
    total_files = max(len(normalized), 1)

    all_meta = {
        pm.provider_key: pm
        for pm in ProviderMeta.query.filter(ProviderMeta.provider_key.in_(normalized)).all()
    }

    is_fast_aggregate_mode = is_all_scope and not exclude_ru_cidrs and af_index is None
    if is_fast_aggregate_mode:
        _report_progress(8, "Быстрая оценка по агрегатам БД...")
        pre_limit_counts_by_file = {}
        source_by_file = {}

        for idx, file_name in enumerate(normalized, start=1):
            _report_progress(
                10 + int((idx - 1) * 65 / total_files),
                f"Оценка провайдера {idx}/{total_files}: {file_name}",
            )
            file_quality = {
                "raw_db_count": 0,
                "after_scope_count": 0,
                "after_ru_exclusion_count": 0,
                "after_antifilter_count": 0,
                "final_after_limit_count": 0,
                "status": "pending",
                "skip_reason": None,
            }

            meta = all_meta.get(file_name)
            if not meta or meta.refresh_status not in ("ok", "partial") or meta.cidr_count == 0:
                reason = "no_db_data" if (not meta or meta.cidr_count == 0) else f"db_status:{meta.refresh_status}"
                skipped.append({"file": file_name, "reason": reason})
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = reason
                quality_by_file[file_name] = file_quality
                continue

            count_value = max(0, int(meta.cidr_count or 0))
            file_quality["raw_db_count"] = count_value
            file_quality["after_scope_count"] = count_value
            file_quality["after_ru_exclusion_count"] = count_value
            file_quality["after_antifilter_count"] = count_value
            file_quality["status"] = "planned"
            quality_by_file[file_name] = file_quality
            pre_limit_counts_by_file[file_name] = count_value
            source_by_file[file_name] = f"db:{meta.source_used or 'unknown'}"

        _report_progress(80, "Оптимизация и применение лимита маршрутов...")
        final_counts_by_file, global_route_optimization_meta = _apply_total_route_limit_counts(pre_limit_counts_by_file)

        estimated = []
        for file_name in normalized:
            raw_count = int(pre_limit_counts_by_file.get(file_name, 0))
            final_count = int(final_counts_by_file.get(file_name, 0))
            if raw_count <= 0:
                continue
            estimated.append(
                {
                    "file": file_name,
                    "cidr_count": final_count,
                    "raw_cidr_count": raw_count,
                    "cidr_count_after_limit": final_count,
                    "source": source_by_file.get(file_name) or "db",
                    **({"limit_applied": True} if raw_count != final_count else {}),
                }
            )

        for file_name in normalized:
            file_quality = quality_by_file.setdefault(
                file_name,
                {
                    "raw_db_count": 0,
                    "after_scope_count": 0,
                    "after_ru_exclusion_count": 0,
                    "after_antifilter_count": 0,
                    "final_after_limit_count": 0,
                    "status": "skipped",
                    "skip_reason": "not_processed",
                },
            )
            file_quality["final_after_limit_count"] = int(final_counts_by_file.get(file_name, 0))
            if file_quality["status"] == "planned":
                if file_quality["final_after_limit_count"] > 0:
                    file_quality["status"] = "estimated"
                    file_quality["skip_reason"] = None
                else:
                    file_quality["status"] = "skipped"
                    file_quality["skip_reason"] = "empty_after_total_limit"

        selected_game_keys = _resolve_game_filter_selection(
            include_game_keys=include_game_keys,
            include_game_hosts=bool(include_game_hosts),
        )
        _, selected_game_domains = _collect_game_domains(selected_game_keys)

        result = {
            "success": True,
            "message": "Оценка CIDR из БД готова",
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
            "quality_report": {
                "providers": quality_by_file,
                "totals": {
                    "requested_files": len(normalized),
                    "raw_db_cidrs": sum(int(item.get("raw_db_count") or 0) for item in quality_by_file.values()),
                    "after_scope_cidrs": sum(int(item.get("after_scope_count") or 0) for item in quality_by_file.values()),
                    "after_ru_exclusion_cidrs": sum(int(item.get("after_ru_exclusion_count") or 0) for item in quality_by_file.values()),
                    "after_antifilter_cidrs": sum(int(item.get("after_antifilter_count") or 0) for item in quality_by_file.values()),
                    "final_after_limit_cidrs": sum(int(item.get("final_after_limit_count") or 0) for item in quality_by_file.values()),
                },
                "dropped_mandatory_files": ((global_route_optimization_meta or {}).get("dpi_mandatory") or {}).get("dropped_mandatory_files", []),
                "warnings": [
                    warning
                    for warning in [
                        (global_route_optimization_meta or {}).get("warning"),
                    ]
                    if warning
                ],
            },
        }

        if global_route_optimization_meta:
            result["global_route_optimization"] = global_route_optimization_meta

        _report_progress(98, "Формирование результата оценки...")
        return result

    _report_progress(8, "Загрузка CIDR из БД...")
    all_rows_by_provider = {}
    for row in (
        ProviderCidr.query
        .filter(ProviderCidr.provider_key.in_(normalized))
        .with_entities(ProviderCidr.provider_key, ProviderCidr.cidr, ProviderCidr.region_scope, ProviderCidr.country_codes)
        .all()
    ):
        all_rows_by_provider.setdefault(row.provider_key, []).append(row)

    for idx, file_name in enumerate(normalized, start=1):
        _report_progress(
            5 + int((idx - 1) * 75 / total_files),
            f"Оценка провайдера {idx}/{total_files}: {file_name}",
        )
        file_quality = {
            "raw_db_count": 0,
            "after_scope_count": 0,
            "after_ru_exclusion_count": 0,
            "after_antifilter_count": 0,
            "final_after_limit_count": 0,
            "status": "pending",
            "skip_reason": None,
        }
        meta = all_meta.get(file_name)
        if not meta or meta.refresh_status not in ("ok", "partial") or meta.cidr_count == 0:
            reason = "no_db_data" if (not meta or meta.cidr_count == 0) else f"db_status:{meta.refresh_status}"
            skipped.append({"file": file_name, "reason": reason})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = reason
            quality_by_file[file_name] = file_quality
            continue

        rows = all_rows_by_provider.get(file_name) or []
        file_quality["raw_db_count"] = len(rows)

        if is_all_scope:
            cidrs = [row.cidr for row in rows]
        else:
            cidrs = []
            for row in rows:
                has_region = row.region_scope is not None
                has_countries = row.country_codes is not None
                if has_region:
                    if not _matches_region_scope(row.region_scope, normalized_scopes):
                        continue
                    if strict_geo_filter and not _matches_strict_scope_value(row.region_scope, normalized_scopes):
                        continue
                    cidrs.append(row.cidr)
                elif has_countries:
                    countries = row.country_codes.split(",")
                    if not any(_matches_country_scope(c, normalized_scopes) for c in countries):
                        continue
                    if strict_geo_filter and not _is_strict_geo_country_set(set(countries)):
                        continue
                    cidrs.append(row.cidr)
                else:
                    if include_non_geo_fallback:
                        cidrs.append(row.cidr)

        cidrs = _normalize_cidrs(cidrs)
        file_quality["after_scope_count"] = len(cidrs)
        if not cidrs:
            skipped.append({"file": file_name, "reason": "empty_after_geo_filter"})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = "empty_after_geo_filter"
            quality_by_file[file_name] = file_quality
            continue

        if exclude_ru_cidrs:
            cidrs, _ = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                file_quality["after_ru_exclusion_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_ru_exclusion"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_ru_exclusion_count"] = len(cidrs)
        else:
            file_quality["after_ru_exclusion_count"] = len(cidrs)

        if af_index is not None:
            cidrs = [c for c in cidrs if _cidr_overlaps_index(c, *af_index)]
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_antifilter"})
                file_quality["after_antifilter_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_antifilter"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_antifilter_count"] = len(cidrs)
        else:
            file_quality["after_antifilter_count"] = len(cidrs)

        planned_estimated.append({
            "file": file_name,
            "cidrs": cidrs,
            "source": f"db:{meta.source_used or 'unknown'}",
        })
        file_quality["status"] = "planned"
        quality_by_file[file_name] = file_quality

    effective_limit = int(total_cidr_limit) if total_cidr_limit and int(total_cidr_limit) > 0 else _get_openvpn_route_total_cidr_limit()
    pre_limit_counts_by_file = {
        item["file"]: len(item.get("cidrs") or [])
        for item in planned_estimated
    }

    planned_estimated, global_route_optimization_meta = _apply_total_route_limit(
        planned_estimated,
        effective_limit,
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )
    _report_progress(88, "Оптимизация и применение лимита маршрутов...")

    estimated = [
        {
            "file": item["file"],
            "cidr_count": len(item.get("cidrs") or []),
            "raw_cidr_count": int(pre_limit_counts_by_file.get(item["file"], len(item.get("cidrs") or []))),
            "cidr_count_after_limit": len(item.get("cidrs") or []),
            "source": item.get("source") or "db",
            **({"limit_applied": True} if int(pre_limit_counts_by_file.get(item["file"], len(item.get("cidrs") or []))) != len(item.get("cidrs") or []) else {}),
        }
        for item in planned_estimated
    ]

    final_counts_by_file = {item["file"]: len(item.get("cidrs") or []) for item in planned_estimated}
    for file_name in normalized:
        file_quality = quality_by_file.setdefault(
            file_name,
            {
                "raw_db_count": 0,
                "after_scope_count": 0,
                "after_ru_exclusion_count": 0,
                "after_antifilter_count": 0,
                "final_after_limit_count": 0,
                "status": "skipped",
                "skip_reason": "not_processed",
            },
        )
        file_quality["final_after_limit_count"] = int(final_counts_by_file.get(file_name, 0))
        if file_quality["status"] == "planned":
            if file_quality["final_after_limit_count"] > 0:
                file_quality["status"] = "estimated"
                file_quality["skip_reason"] = None
            else:
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_total_limit"

    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    _, selected_game_domains = _collect_game_domains(selected_game_keys)

    result = {
        "success": True,
        "message": "Оценка CIDR из БД готова",
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
        "quality_report": {
            "providers": quality_by_file,
            "totals": {
                "requested_files": len(normalized),
                "raw_db_cidrs": sum(int(item.get("raw_db_count") or 0) for item in quality_by_file.values()),
                "after_scope_cidrs": sum(int(item.get("after_scope_count") or 0) for item in quality_by_file.values()),
                "after_ru_exclusion_cidrs": sum(int(item.get("after_ru_exclusion_count") or 0) for item in quality_by_file.values()),
                "after_antifilter_cidrs": sum(int(item.get("after_antifilter_count") or 0) for item in quality_by_file.values()),
                "final_after_limit_cidrs": sum(int(item.get("final_after_limit_count") or 0) for item in quality_by_file.values()),
            },
            "dropped_mandatory_files": ((global_route_optimization_meta or {}).get("dpi_mandatory") or {}).get("dropped_mandatory_files", []),
            "warnings": [
                warning
                for warning in [
                    (global_route_optimization_meta or {}).get("warning"),
                ]
                if warning
            ],
        },
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    _report_progress(98, "Формирование результата оценки...")

    return result
