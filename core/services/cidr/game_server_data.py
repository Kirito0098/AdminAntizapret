"""Curated game server IPs and source URLs from public documentation."""

# ── Riot Direct (LoL wiki, Valorant, Wild Rift) ─────────────────────────────
RIOT_DIRECT_ASNS = [6507]
RIOT_IP_SOURCE_URL = "https://wiki.leagueoflegends.com/en-us/Servers"

RIOT_LOL_SERVER_IPS = [
    "104.160.141.3",  # EUW
    "104.160.142.3",  # EUNE
    "104.160.152.3",  # BR
    "104.160.136.3",  # LAN
    "104.160.131.3",  # NA
    "104.160.131.1",  # NA alt
    "104.160.156.1",  # OCE
]

# Valorant / Wild Rift share Riot Direct login infrastructure (104.160.0.0/16).
RIOT_VALORANT_SERVER_IPS = list(RIOT_LOL_SERVER_IPS)
RIOT_WILD_RIFT_SERVER_IPS = list(RIOT_LOL_SERVER_IPS)
VALORANT_IP_SOURCE_URL = "https://wiki.leagueoflegends.com/en-us/Servers"
WILD_RIFT_IP_SOURCE_URL = "https://wiki.leagueoflegends.com/en-us/Servers"

# ── Square Enix — FFXIV physical datacenter traceroute IPs (official) ───────
FFXIV_IP_SOURCE_URL = (
    "https://na.finalfantasyxiv.com/lodestone/topics/detail/"
    "82254b55f875f3c3fb85b2c578a14f5c38a5cba1"
)
FFXIV_SERVER_IPS = [
    "119.252.37.58",   # Japan
    "204.2.29.122",    # North America
    "80.239.145.101",  # Europe
    "153.254.80.65",   # Oceania
]

# ── Path of Exile — dynamic instance servers on IBM Cloud / AWS ─────────────
POE_IP_SOURCE_URL = "https://www.pathofexile.com/forum/view-thread/1377789"
POE_GAME_ASNS = [36351, 16509]

# ── Roblox game network (BGP, not marketing CDN) ────────────────────────────
ROBLOX_IP_SOURCE_URL = "https://devforum.roblox.com/t/all-of-robloxs-ip-ranges-ipv4-ipv6-2023/2527578"
ROBLOX_GAME_ASNS = [22697, 11281]
ROBLOX_GAME_SERVER_CIDRS = [
    "128.116.0.0/17",
]

# ── Minecraft Java — session / multiplayer services (Microsoft) ───────────
MINECRAFT_IP_SOURCE_URL = "https://minecraft.wiki/w/Minecraft_server"
MINECRAFT_GAME_ASNS = [8075]

# ── Activision Call of Duty ─────────────────────────────────────────────────
ACTIVISION_IP_SOURCE_URL = "https://support.activision.com/articles/call-of-duty-connectivity-issues"
ACTIVISION_GAME_ASNS = [394536, 57976]

# ── Supercell mobile game backends (Google Cloud game servers) ─────────────
SUPERCELL_IP_SOURCE_URL = "https://supercell.com/en/support/"
SUPERCELL_GAME_ASNS = [396982]

# ── FACEIT matchmaking / anti-cheat infrastructure ─────────────────────────
FACEIT_IP_SOURCE_URL = "https://www.peeringdb.com/asn/200613"
FACEIT_GAME_ASNS = [200613]

# ── Digital Extremes — Warframe (AWS game servers) ───────────────────────────
WARFRAME_IP_SOURCE_URL = "https://www.digitalextremes.com/"
WARFRAME_GAME_ASNS = [16509, 14618]

# ── Moonton — Mobile Legends ────────────────────────────────────────────────
MOBILE_LEGENDS_IP_SOURCE_URL = "https://mobilelegends.com/"
MOBILE_LEGENDS_GAME_ASNS = [138699, 55990]

# ── Kuro Games — Wuthering Waves (similar cloud game backend) ───────────────
WUTHERING_WAVES_IP_SOURCE_URL = "https://wutheringwaves.kurogames.com/"
WUTHERING_WAVES_GAME_ASNS = [45062, 16509]

# ── Bethesda / ZeniMax online titles ────────────────────────────────────────
ZENIMAX_IP_SOURCE_URL = "https://help.bethesda.net/"
ZENIMAX_GAME_ASNS = [30109, 8075]

# ── Gameforge — Metin2 ──────────────────────────────────────────────────────
GAMEFORGE_IP_SOURCE_URL = "https://gameforge.com/"
GAMEFORGE_GAME_ASNS = [48173, 16265]

# ── Sandbox Interactive — Albion Online game servers ───────────────────────
ALBION_IP_SOURCE_URL = "https://forum.albiononline.com/index.php/Thread/92005-Public-IP-addresses-of-Albion-Online-servers/"
ALBION_GAME_ASNS = [58212]
ALBION_SERVER_IPS = [
    "185.218.131.50",
    "37.9.32.15",
    "5.188.189.218",
]

# ── Take-Two / 2K — NBA 2K online ───────────────────────────────────────────
NBA_2K_IP_SOURCE_URL = "https://2k.com/"
NBA_2K_GAME_ASNS = [46652, 36351]

# ── InnerSloth — Among Us (Multiplay / Unity hosting) ───────────────────────
AMONG_US_IP_SOURCE_URL = "https://www.innersloth.com/"
AMONG_US_GAME_ASNS = [60068, 16509]

# ── TiMi / Garena — Arena of Valor ──────────────────────────────────────────
ARENA_OF_VALOR_IP_SOURCE_URL = "https://www.arenaofvalor.com/"
ARENA_OF_VALOR_GAME_ASNS = [38561, 45090]
