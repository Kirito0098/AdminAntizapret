"""Provider URLs, game catalog, region scopes, and DPI maps."""
import os
import re

from core.services.cidr.constants import (
    GAME_FILTER_BLOCK_END,
    GAME_FILTER_BLOCK_START,
    GAME_FILTER_IP_BLOCK_END,
    GAME_FILTER_IP_BLOCK_START,
    GAME_INCLUDE_HOSTS_FILE,
    GAME_INCLUDE_IPS_FILE,
)
from core.services.cidr.game_server_data import (
    ACTIVISION_GAME_ASNS,
    ACTIVISION_IP_SOURCE_URL,
    ALBION_GAME_ASNS,
    ALBION_IP_SOURCE_URL,
    ALBION_SERVER_IPS,
    AMONG_US_GAME_ASNS,
    AMONG_US_IP_SOURCE_URL,
    ARENA_OF_VALOR_GAME_ASNS,
    ARENA_OF_VALOR_IP_SOURCE_URL,
    FACEIT_GAME_ASNS,
    FACEIT_IP_SOURCE_URL,
    FFXIV_IP_SOURCE_URL,
    FFXIV_SERVER_IPS,
    GAMEFORGE_GAME_ASNS,
    GAMEFORGE_IP_SOURCE_URL,
    MINECRAFT_GAME_ASNS,
    MINECRAFT_IP_SOURCE_URL,
    MOBILE_LEGENDS_GAME_ASNS,
    MOBILE_LEGENDS_IP_SOURCE_URL,
    NBA_2K_GAME_ASNS,
    NBA_2K_IP_SOURCE_URL,
    POE_GAME_ASNS,
    POE_IP_SOURCE_URL,
    RIOT_DIRECT_ASNS,
    RIOT_IP_SOURCE_URL,
    RIOT_LOL_SERVER_IPS,
    RIOT_VALORANT_SERVER_IPS,
    RIOT_WILD_RIFT_SERVER_IPS,
    ROBLOX_GAME_ASNS,
    ROBLOX_GAME_SERVER_CIDRS,
    ROBLOX_IP_SOURCE_URL,
    SUPERCELL_GAME_ASNS,
    SUPERCELL_IP_SOURCE_URL,
    VALORANT_IP_SOURCE_URL,
    WARFRAME_GAME_ASNS,
    WARFRAME_IP_SOURCE_URL,
    WILD_RIFT_IP_SOURCE_URL,
    WUTHERING_WAVES_GAME_ASNS,
    WUTHERING_WAVES_IP_SOURCE_URL,
    ZENIMAX_GAME_ASNS,
    ZENIMAX_IP_SOURCE_URL,
)

PROVIDER_SOURCES = {
    "akamai-ips.txt": [
        {
            "name": "ripe-as20940-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS20940",
            "format": "ripe_json",
            "timeout": 120,
        },
        {
            "name": "ripe-as20940-bgpstate",
            "url": "https://stat.ripe.net/data/bgp-state/data.json?resource=AS20940",
            "format": "ripe_bgp_state_json",
            "timeout": 90,
        },
        {
            "name": "ripe-as20940-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS20940",
            "format": "ripe_geo_json",
            "timeout": 120,
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
GAME_FILTER_CATALOG = [
    # ── Riot Games ── League of Legends ──────────────────────────────
    {
        "key": "lol",
        "title": "League of Legends",
        "subtitle": "Riot Games — Riot Direct",
        "asns": list(RIOT_DIRECT_ASNS),
        "server_ips": list(RIOT_LOL_SERVER_IPS),
        "ip_source_url": RIOT_IP_SOURCE_URL,
        "domains": ["riotgames.com", "leagueoflegends.com", "pvp.net"],
    },
    # ── Riot Games ── VALORANT ────────────────────────────────────────
    {
        "key": "valorant",
        "title": "VALORANT",
        "subtitle": "Riot Games — Riot Direct",
        "asns": list(RIOT_DIRECT_ASNS),
        "server_ips": list(RIOT_VALORANT_SERVER_IPS),
        "ip_source_url": VALORANT_IP_SOURCE_URL,
        "domains": ["playvalorant.com", "riotgames.com"],
    },
    # ── Riot Games ── Wild Rift ───────────────────────────────────────
    {
        "key": "wild_rift",
        "title": "Wild Rift",
        "subtitle": "Riot Games — Riot Direct",
        "asns": list(RIOT_DIRECT_ASNS),
        "server_ips": list(RIOT_WILD_RIFT_SERVER_IPS),
        "ip_source_url": WILD_RIFT_IP_SOURCE_URL,
        "domains": ["wildrift.leagueoflegends.com", "riotgames.com"],
    },
    # ── Valve ── Dota 2 ───────────────────────────────────────────────
    {
        "key": "dota2",
        "title": "Dota 2",
        "subtitle": "Valve — AS32590",
        "asns": [32590],
        "domains": ["dota2.com", "steampowered.com"],
    },
    # ── Valve ── Counter-Strike 2 ─────────────────────────────────────
    {
        "key": "cs2",
        "title": "Counter-Strike 2",
        "subtitle": "Valve — AS32590",
        "asns": [32590],
        "domains": ["counter-strike.net", "steampowered.com"],
    },
    # ── Valve ── Steam Platform ───────────────────────────────────────
    {
        "key": "steam_platform",
        "title": "Steam Platform",
        "subtitle": "Valve — AS32590",
        "asns": [32590],
        "domains": ["steampowered.com", "steamcommunity.com", "steamcontent.com", "steamserver.net"],
    },
    # ── Blizzard ── World of Warcraft ─────────────────────────────────
    {
        "key": "world_of_warcraft",
        "title": "World of Warcraft",
        "subtitle": "Blizzard — AS57976",
        "asns": [57976],
        "domains": ["worldofwarcraft.com", "battle.net"],
    },
    # ── Blizzard ── Overwatch 2 ───────────────────────────────────────
    {
        "key": "overwatch2",
        "title": "Overwatch 2",
        "subtitle": "Blizzard — AS57976",
        "asns": [57976],
        "domains": ["playoverwatch.com", "battle.net"],
    },
    # ── Blizzard ── Hearthstone ───────────────────────────────────────
    {
        "key": "hearthstone",
        "title": "Hearthstone",
        "subtitle": "Blizzard — AS57976",
        "asns": [57976],
        "domains": ["playhearthstone.com", "battle.net"],
    },
    # ── Blizzard ── Diablo IV ─────────────────────────────────────────
    {
        "key": "diablo4",
        "title": "Diablo IV",
        "subtitle": "Blizzard — AS57976",
        "asns": [57976],
        "domains": ["diablo.com", "battle.net"],
    },
    # ── Blizzard ── StarCraft II ──────────────────────────────────────
    {
        "key": "starcraft2",
        "title": "StarCraft II",
        "subtitle": "Blizzard — AS57976",
        "asns": [57976],
        "domains": ["starcraft2.com", "battle.net"],
    },
    # ── Electronic Arts ── Apex Legends ──────────────────────────────
    {
        "key": "apex_legends",
        "title": "Apex Legends",
        "subtitle": "EA / Respawn — AS12222",
        "asns": [12222],
        "domains": ["ea.com", "respawn.com"],
    },
    # ── Electronic Arts ── Battlefield ───────────────────────────────
    {
        "key": "battlefield",
        "title": "Battlefield",
        "subtitle": "EA — AS12222",
        "asns": [12222],
        "domains": ["battlefield.com", "ea.com"],
    },
    # ── Electronic Arts ── EA Sports FC ──────────────────────────────
    {
        "key": "ea_fc",
        "title": "EA Sports FC",
        "subtitle": "EA — AS12222",
        "asns": [12222],
        "domains": ["easports.com", "ea.com"],
    },
    # ── Wargaming ── World of Tanks ───────────────────────────────────
    {
        "key": "world_of_tanks",
        "title": "World of Tanks",
        "subtitle": "Wargaming — AS42396",
        "asns": [42396, 35540],
        "domains": ["worldoftanks.com", "wargaming.net"],
    },
    # ── Wargaming ── World of Warships ────────────────────────────────
    {
        "key": "world_of_warships",
        "title": "World of Warships",
        "subtitle": "Wargaming — AS42396",
        "asns": [42396, 62317],
        "domains": ["worldofwarships.com", "wargaming.net"],
    },
    # ── Wargaming ── WoT Blitz ────────────────────────────────────────
    {
        "key": "wot_blitz",
        "title": "WoT Blitz",
        "subtitle": "Wargaming — AS42396",
        "asns": [42396, 62317],
        "domains": ["wotblitz.com", "wargaming.net"],
    },
    # ── Lesta Games ── Мир Танков ────────────────────────────────────
    {
        "key": "mir_tankov",
        "title": "Мир Танков",
        "subtitle": "Lesta Games — AS215859",
        "asns": [215859],
        "domains": ["tanki.su", "lesta.ru"],
    },
    # ── Lesta Games ── Мир Кораблей ──────────────────────────────────
    {
        "key": "mir_korabley",
        "title": "Мир Кораблей",
        "subtitle": "Lesta Games — AS215859",
        "asns": [215859],
        "domains": ["korabli.eu", "lesta.ru"],
    },
    # ── Gaijin ── War Thunder ─────────────────────────────────────────
    {
        "key": "war_thunder",
        "title": "War Thunder",
        "subtitle": "Gaijin — AS44530",
        "asns": [44530],
        "domains": ["warthunder.com", "gaijin.net"],
    },
    # ── Gaijin ── Enlisted ────────────────────────────────────────────
    {
        "key": "enlisted",
        "title": "Enlisted",
        "subtitle": "Gaijin — AS44530",
        "asns": [44530],
        "domains": ["enlisted.net", "gaijin.net"],
    },
    # ── Gaijin ── Crossout ────────────────────────────────────────────
    {
        "key": "crossout",
        "title": "Crossout",
        "subtitle": "Gaijin — AS44530",
        "asns": [44530],
        "domains": ["crossout.net", "gaijin.net"],
    },
    # ── Krafton ── PUBG ───────────────────────────────────────────────
    {
        "key": "pubg",
        "title": "PUBG: Battlegrounds",
        "subtitle": "Krafton — AS263444",
        "asns": [263444, 209242],
        "domains": ["pubg.com", "krafton.com"],
    },
    # ── Krafton ── PUBG Mobile ────────────────────────────────────────
    {
        "key": "pubg_mobile",
        "title": "PUBG Mobile",
        "subtitle": "Krafton — AS263444",
        "asns": [263444, 209242],
        "domains": ["pubgmobile.com", "krafton.com"],
    },
    # ── HoYoverse ── Genshin Impact ───────────────────────────────────
    {
        "key": "genshin_impact",
        "title": "Genshin Impact",
        "subtitle": "HoYoverse — AS45062",
        "asns": [45062],
        "domains": ["genshin.hoyoverse.com", "hoyoverse.com", "mihoyo.com"],
    },
    # ── HoYoverse ── Honkai: Star Rail ───────────────────────────────
    {
        "key": "honkai_star_rail",
        "title": "Honkai: Star Rail",
        "subtitle": "HoYoverse — AS45062",
        "asns": [45062],
        "domains": ["hsr.hoyoverse.com", "hoyoverse.com"],
    },
    # ── HoYoverse ── Zenless Zone Zero ───────────────────────────────
    {
        "key": "zzz",
        "title": "Zenless Zone Zero",
        "subtitle": "HoYoverse — AS45062",
        "asns": [45062],
        "domains": ["zzz.hoyoverse.com", "hoyoverse.com"],
    },
    # ── Bungie ── Destiny 2 ───────────────────────────────────────────
    {
        "key": "destiny2",
        "title": "Destiny 2",
        "subtitle": "Bungie — AS36958",
        "asns": [36958],
        "domains": ["bungie.net"],
    },
    # ── Sony ── PlayStation Network ───────────────────────────────────
    {
        "key": "playstation_network",
        "title": "PlayStation Network",
        "subtitle": "Sony — AS13213",
        "asns": [13213],
        "domains": ["playstation.com", "sonyentertainmentnetwork.com", "playstation.net"],
    },
    # ── Microsoft ── Xbox Live ────────────────────────────────────────
    {
        "key": "xbox_live",
        "title": "Xbox Live",
        "subtitle": "Microsoft — AS8075",
        "asns": [8075],
        "domains": ["xbox.com", "xboxlive.com"],
    },
    # ── Microsoft ── Minecraft ────────────────────────────────────────
    {
        "key": "minecraft",
        "title": "Minecraft",
        "subtitle": "Mojang / Microsoft — AS8075",
        "asns": list(MINECRAFT_GAME_ASNS),
        "ip_source_url": MINECRAFT_IP_SOURCE_URL,
        "domains": ["minecraft.net", "mojang.com"],
    },
    # ── Microsoft ── Halo Infinite ────────────────────────────────────
    {
        "key": "halo_infinite",
        "title": "Halo Infinite",
        "subtitle": "343 Industries / Microsoft — AS8075",
        "asns": [8075],
        "domains": ["halowaypoint.com", "xbox.com"],
    },
    # ── Ubisoft ── Rainbow Six Siege ──────────────────────────────────
    {
        "key": "rainbow6",
        "title": "Rainbow Six Siege",
        "subtitle": "Ubisoft — AS25376",
        "asns": [25376],
        "domains": ["rainbow6.com", "ubisoft.com"],
    },
    # ── Ubisoft ── XDefiant ───────────────────────────────────────────
    {
        "key": "xdefiant",
        "title": "XDefiant",
        "subtitle": "Ubisoft — AS25376",
        "asns": [25376],
        "domains": ["xdefiant.com", "ubisoft.com"],
    },
    # ── Take-Two ── GTA Online ────────────────────────────────────────
    {
        "key": "gta_online",
        "title": "GTA Online",
        "subtitle": "Rockstar / Take-Two — AS46652",
        "asns": [46652],
        "domains": ["rockstargames.com", "socialclub.rockstargames.com"],
    },
    # ── Take-Two ── NBA 2K ────────────────────────────────────────────
    {
        "key": "nba_2k",
        "title": "NBA 2K",
        "subtitle": "2K / Take-Two — AS46652",
        "asns": list(NBA_2K_GAME_ASNS),
        "ip_source_url": NBA_2K_IP_SOURCE_URL,
        "domains": ["2k.com", "nba.2k.com"],
    },
    # ── Bohemia ── DayZ ───────────────────────────────────────────────
    {
        "key": "dayz",
        "title": "DayZ",
        "subtitle": "Bohemia Interactive — AS56704",
        "asns": [56704],
        "domains": ["dayz.com", "bohemia.net"],
    },
    # ── Bohemia ── ARMA Reforger ──────────────────────────────────────
    {
        "key": "arma",
        "title": "ARMA Reforger",
        "subtitle": "Bohemia Interactive — AS56704",
        "asns": [56704],
        "domains": ["bohemia.net", "arma.com"],
    },
    # ── Pearl Abyss ── Black Desert Online ───────────────────────────
    {
        "key": "black_desert",
        "title": "Black Desert Online",
        "subtitle": "Pearl Abyss — AS55967",
        "asns": [55967],
        "domains": ["pearlabyss.com", "blackdesertonline.com"],
    },
    # ── Smilegate ── Lost Ark ─────────────────────────────────────────
    {
        "key": "lost_ark",
        "title": "Lost Ark",
        "subtitle": "Smilegate — AS38631",
        "asns": [38631],
        "domains": ["lostark.com", "smilegate.com"],
    },
    # ── Smilegate ── CrossFire ────────────────────────────────────────
    {
        "key": "crossfire",
        "title": "CrossFire",
        "subtitle": "Smilegate — AS38631",
        "asns": [38631],
        "domains": ["crossfire.z8games.com", "smilegate.com"],
    },
    # ── Plarium ── RAID: Shadow Legends ──────────────────────────────
    {
        "key": "raid_shadow_legends",
        "title": "RAID: Shadow Legends",
        "subtitle": "Plarium — AS213230",
        "asns": [213230],
        "domains": ["plarium.com", "raidshadowlegends.com"],
    },
    # ── MY.GAMES ── Warface ───────────────────────────────────────────
    {
        "key": "warface",
        "title": "Warface",
        "subtitle": "MY.GAMES — AS47764",
        "asns": [47764],
        "domains": ["warface.com", "my.games"],
    },
    # ── MY.GAMES ── Skyforge ──────────────────────────────────────────
    {
        "key": "skyforge",
        "title": "Skyforge",
        "subtitle": "MY.GAMES — AS47764",
        "asns": [47764],
        "domains": ["skyforge.com", "my.games"],
    },
    # ── Axlebolt ── Standoff 2 ────────────────────────────────────────
    {
        "key": "standoff2",
        "title": "Standoff 2",
        "subtitle": "Axlebolt — AS212317",
        "asns": [212317],
        "domains": ["standoff2.com", "axlebolt.com"],
    },
    # ── Embark Studios ── THE FINALS ─────────────────────────────────
    {
        "key": "the_finals",
        "title": "THE FINALS",
        "subtitle": "Embark Studios — AS201281",
        "asns": [201281],
        "domains": ["reachthefinals.com", "embark-studios.com"],
    },
    # ── Pixonic ── War Robots ─────────────────────────────────────────
    {
        "key": "war_robots",
        "title": "War Robots",
        "subtitle": "Pixonic — AS60890",
        "asns": [60890],
        "domains": ["warrobots.com", "pixonic.com"],
    },
    # ── Battlestate Games ── Escape from Tarkov ───────────────────────
    {
        "key": "escape_from_tarkov",
        "title": "Escape from Tarkov",
        "subtitle": "Battlestate Games — AS48172",
        "asns": [48172],
        "domains": ["escapefromtarkov.com", "battlestategames.com"],
    },
    # ── Battlestate Games ── Tarkov Arena ────────────────────────────
    {
        "key": "tarkov_arena",
        "title": "Tarkov Arena",
        "subtitle": "Battlestate Games — AS48172",
        "asns": [48172],
        "domains": ["tarkovarena.com", "battlestategames.com"],
    },
    # ── NCSoft ── Lineage 2 ───────────────────────────────────────────
    {
        "key": "lineage2",
        "title": "Lineage 2",
        "subtitle": "NCSoft — AS9318",
        "asns": [9318],
        "domains": ["lineage2.com", "ncsoft.com"],
    },
    # ── NCSoft ── Guild Wars 2 ────────────────────────────────────────
    {
        "key": "guild_wars2",
        "title": "Guild Wars 2",
        "subtitle": "NCSoft — AS9318",
        "asns": [9318],
        "domains": ["guildwars2.com", "ncsoft.com"],
    },
    # ── NCSoft ── Blade & Soul ────────────────────────────────────────
    {
        "key": "blade_and_soul",
        "title": "Blade & Soul",
        "subtitle": "NCSoft — AS9318",
        "asns": [9318],
        "domains": ["bladeandsoul.com", "ncsoft.com"],
    },
    # ── Garena ── Free Fire ───────────────────────────────────────────
    {
        "key": "free_fire",
        "title": "Free Fire",
        "subtitle": "Garena / Sea Group — AS38561",
        "asns": [38561],
        "domains": ["ff.garena.com", "garena.com"],
    },
    # ── Garena ── Arena of Valor ──────────────────────────────────────
    {
        "key": "arena_of_valor",
        "title": "Arena of Valor",
        "subtitle": "TiMi / Garena — AS38561",
        "asns": list(ARENA_OF_VALOR_GAME_ASNS),
        "ip_source_url": ARENA_OF_VALOR_IP_SOURCE_URL,
        "domains": ["arenaofvalor.com", "garena.com"],
    },
    # ── Epic Games ── Fortnite ────────────────────────────────────────
    {
        "key": "fortnite",
        "title": "Fortnite",
        "subtitle": "Epic Games — AS14593",
        "asns": [14593],
        "domains": ["fortnite.com", "epicgames.com"],
    },
    # ── Epic Games ── Rocket League ───────────────────────────────────
    {
        "key": "rocket_league",
        "title": "Rocket League",
        "subtitle": "Psyonix / Epic Games — AS14593",
        "asns": [14593],
        "domains": ["rocketleague.com", "epicgames.com"],
    },
    # ── FACEIT ── matchmaking platform ───────────────────────────────
    {
        "key": "faceit",
        "title": "FACEIT",
        "subtitle": "FACEIT — AS200613",
        "asns": list(FACEIT_GAME_ASNS),
        "ip_source_url": FACEIT_IP_SOURCE_URL,
        "domains": ["faceit.com", "faceit-cdn.net", "faceitusercontent.com"],
    },
    # ── Supercell ── Clash of Clans ───────────────────────────────────
    {
        "key": "clash_of_clans",
        "title": "Clash of Clans",
        "subtitle": "Supercell — AS396982",
        "asns": list(SUPERCELL_GAME_ASNS),
        "ip_source_url": SUPERCELL_IP_SOURCE_URL,
        "domains": ["clashofclans.com", "supercell.com"],
    },
    # ── Supercell ── Clash Royale ─────────────────────────────────────
    {
        "key": "clash_royale",
        "title": "Clash Royale",
        "subtitle": "Supercell — AS396982",
        "asns": list(SUPERCELL_GAME_ASNS),
        "ip_source_url": SUPERCELL_IP_SOURCE_URL,
        "domains": ["clashroyale.com", "supercell.com"],
    },
    # ── Supercell ── Brawl Stars ──────────────────────────────────────
    {
        "key": "brawl_stars",
        "title": "Brawl Stars",
        "subtitle": "Supercell — AS396982",
        "asns": list(SUPERCELL_GAME_ASNS),
        "ip_source_url": SUPERCELL_IP_SOURCE_URL,
        "domains": ["brawlstars.com", "supercell.com"],
    },
    # ── Activision ── Call of Duty: Warzone ───────────────────────────
    {
        "key": "warzone",
        "title": "Call of Duty: Warzone",
        "subtitle": "Activision — AS394536",
        "asns": list(ACTIVISION_GAME_ASNS),
        "ip_source_url": ACTIVISION_IP_SOURCE_URL,
        "domains": ["callofduty.com", "activision.com"],
    },
    # ── Activision ── CoD Mobile ──────────────────────────────────────
    {
        "key": "cod_mobile",
        "title": "Call of Duty Mobile",
        "subtitle": "Activision / TiMi — AS394536",
        "asns": list(ACTIVISION_GAME_ASNS),
        "ip_source_url": ACTIVISION_IP_SOURCE_URL,
        "domains": ["codmobile.activision.com", "callofduty.com"],
    },
    # ── Roblox ────────────────────────────────────────────────────────
    {
        "key": "roblox",
        "title": "Roblox",
        "subtitle": "Roblox Corporation — AS22697",
        "asns": list(ROBLOX_GAME_ASNS),
        "server_ips": list(ROBLOX_GAME_SERVER_CIDRS),
        "ip_source_url": ROBLOX_IP_SOURCE_URL,
        "domains": ["roblox.com", "rbxcdn.com"],
    },
    # ── Kuro Games ── Wuthering Waves ────────────────────────────────
    {
        "key": "wuthering_waves",
        "title": "Wuthering Waves",
        "subtitle": "Kuro Games — AS45062",
        "asns": list(WUTHERING_WAVES_GAME_ASNS),
        "ip_source_url": WUTHERING_WAVES_IP_SOURCE_URL,
        "domains": ["wutheringwaves.com", "kurogames.com"],
    },
    # ── Moonton ── Mobile Legends ────────────────────────────────────
    {
        "key": "mobile_legends",
        "title": "Mobile Legends: Bang Bang",
        "subtitle": "Moonton / ByteDance — AS138699",
        "asns": list(MOBILE_LEGENDS_GAME_ASNS),
        "ip_source_url": MOBILE_LEGENDS_IP_SOURCE_URL,
        "domains": ["mobilelegends.com", "moonton.com"],
    },
    # ── Digital Extremes ── Warframe ──────────────────────────────────
    {
        "key": "warframe",
        "title": "Warframe",
        "subtitle": "Digital Extremes — AS16509",
        "asns": list(WARFRAME_GAME_ASNS),
        "ip_source_url": WARFRAME_IP_SOURCE_URL,
        "domains": ["warframe.com", "digitalextremes.com"],
    },
    # ── Gameforge ── Metin2 ───────────────────────────────────────────
    {
        "key": "metin2",
        "title": "Metin2",
        "subtitle": "Gameforge — AS48173",
        "asns": list(GAMEFORGE_GAME_ASNS),
        "ip_source_url": GAMEFORGE_IP_SOURCE_URL,
        "domains": ["gameforge.com", "metin2.gameforge.com"],
    },
    # ── Sandbox Interactive ── Albion Online ─────────────────────────
    {
        "key": "albion_online",
        "title": "Albion Online",
        "subtitle": "Sandbox Interactive — AS58212",
        "asns": list(ALBION_GAME_ASNS),
        "server_ips": list(ALBION_SERVER_IPS),
        "ip_source_url": ALBION_IP_SOURCE_URL,
        "domains": ["albiononline.com", "sandbox-interactive.com"],
    },
    # ── Square Enix ── Final Fantasy XIV ─────────────────────────────
    {
        "key": "final_fantasy_xiv",
        "title": "Final Fantasy XIV",
        "subtitle": "Square Enix — Game DCs",
        "asns": [],
        "server_ips": list(FFXIV_SERVER_IPS),
        "ip_source_url": FFXIV_IP_SOURCE_URL,
        "domains": ["finalfantasyxiv.com", "square-enix.com"],
    },
    # ── Bethesda ── Elder Scrolls Online ─────────────────────────────
    {
        "key": "elder_scrolls_online",
        "title": "Elder Scrolls Online",
        "subtitle": "ZeniMax / Bethesda — AS30109",
        "asns": list(ZENIMAX_GAME_ASNS),
        "ip_source_url": ZENIMAX_IP_SOURCE_URL,
        "domains": ["elderscrollsonline.com", "bethesda.net"],
    },
    # ── Bethesda ── Fallout 76 ────────────────────────────────────────
    {
        "key": "fallout_76",
        "title": "Fallout 76",
        "subtitle": "Bethesda — AS30109",
        "asns": list(ZENIMAX_GAME_ASNS),
        "ip_source_url": ZENIMAX_IP_SOURCE_URL,
        "domains": ["fallout.bethesda.net", "bethesda.net"],
    },
    # ── Grinding Gear Games ── Path of Exile ─────────────────────────
    {
        "key": "path_of_exile",
        "title": "Path of Exile",
        "subtitle": "Grinding Gear Games — AS36351",
        "asns": list(POE_GAME_ASNS),
        "ip_source_url": POE_IP_SOURCE_URL,
        "domains": ["pathofexile.com", "grindinggear.com"],
    },
    # ── Grinding Gear Games ── Path of Exile 2 ───────────────────────
    {
        "key": "path_of_exile2",
        "title": "Path of Exile 2",
        "subtitle": "Grinding Gear Games — AS36351",
        "asns": list(POE_GAME_ASNS),
        "ip_source_url": POE_IP_SOURCE_URL,
        "domains": ["pathofexile.com", "grindinggear.com"],
    },
    # ── Facepunch Studios ── Rust ─────────────────────────────────────
    {
        "key": "rust",
        "title": "Rust",
        "subtitle": "Facepunch Studios — AS32590",
        "asns": [32590],
        "domains": ["facepunch.com", "rust.facepunch.com"],
    },
    # ── InnerSloth ── Among Us ────────────────────────────────────────
    {
        "key": "among_us",
        "title": "Among Us",
        "subtitle": "InnerSloth — AS60068",
        "asns": list(AMONG_US_GAME_ASNS),
        "ip_source_url": AMONG_US_IP_SOURCE_URL,
        "domains": ["innersloth.com", "among.us"],
    },
]
GAME_FILTER_ALIASES = {
    # Старые названия игр → прямые ключи каталога
    "csgo": "cs2",
    "counter-strike": "cs2",
    "counter_strike": "cs2",
    "dota": "dota2",
    "steam": "steam_platform",
    "wow": "world_of_warcraft",
    "world_of_warcraft": "world_of_warcraft",
    "overwatch": "overwatch2",
    "ow2": "overwatch2",
    "diablo": "diablo4",
    "sc2": "starcraft2",
    "wot": "world_of_tanks",
    "world_of_tanks_blitz": "wot_blitz",
    "wotb": "wot_blitz",
    "wows": "world_of_warships",
    "tarkov": "escape_from_tarkov",
    "genshin": "genshin_impact",
    "hsr": "honkai_star_rail",
    "epic_games_store": "fortnite",
    "league-of-legends": "lol",
    "league_of_legends": "lol",
    "point_blank": "crossfire",
    # Старые ключи издательств → основная игра для обратной совместимости
    "riot_games": "lol",
    "valve": "cs2",
    "blizzard": "world_of_warcraft",
    "electronic_arts": "apex_legends",
    "wargaming": "world_of_tanks",
    "lesta_games": "mir_tankov",
    "gaijin": "war_thunder",
    "krafton": "pubg",
    "hoyoverse": "genshin_impact",
    "bungie": "destiny2",
    "sony_playstation": "playstation_network",
    "microsoft_xbox": "xbox_live",
    "ubisoft": "rainbow6",
    "take_two": "gta_online",
    "bohemia": "dayz",
    "pearl_abyss": "black_desert",
    "smilegate": "lost_ark",
    "plarium": "raid_shadow_legends",
    "my_games": "warface",
    "axlebolt": "standoff2",
    "embark_studios": "the_finals",
    "pixonic": "war_robots",
    "battlestate": "escape_from_tarkov",
    "ncsoft": "lineage2",
    "garena": "free_fire",
    "epic_games": "fortnite",
    "supercell": "clash_of_clans",
    "activision": "warzone",
    "kuro_games": "wuthering_waves",
    "moonton": "mobile_legends",
    "digital_extremes": "warframe",
    "gameforge": "metin2",
    "sandbox_interactive": "albion_online",
    "square_enix": "final_fantasy_xiv",
    "bethesda": "elder_scrolls_online",
    "grinding_gear": "path_of_exile",
    "facepunch": "rust",
    "innersloth": "among_us",
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
