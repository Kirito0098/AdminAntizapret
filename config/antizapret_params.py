# app/config/antizapret_params.py

ANTIZAPRET_PARAMS = [
    {"key": "route_all",              "env": "ROUTE_ALL",              "type": "flag",   "default": "n", "html_id": "route-all-toggle"},
    {"key": "discord_include",        "env": "DISCORD_INCLUDE",        "type": "flag",   "default": "n", "html_id": "discord-toggle"},
    {"key": "cloudflare_include",     "env": "CLOUDFLARE_INCLUDE",     "type": "flag",   "default": "n", "html_id": "cloudflare-toggle"},
    {"key": "telegram_include",       "env": "TELEGRAM_INCLUDE",       "type": "flag",   "default": "n", "html_id": "telegram-toggle"},
    {"key": "block_ads",              "env": "BLOCK_ADS",              "type": "flag",   "default": "n", "html_id": "AdBlock-toggle"},
    {"key": "whatsapp_include",       "env": "WHATSAPP_INCLUDE",       "type": "flag",   "default": "n", "html_id": "whatsapp-toggle"},
    {"key": "roblox_include",         "env": "ROBLOX_INCLUDE",         "type": "flag",   "default": "n", "html_id": "roblox-toggle"},
    {"key": "OPENVPN_BACKUP_TCP",     "env": "OPENVPN_BACKUP_TCP",     "type": "flag",   "default": "n", "html_id": "OPENVPN_BACKUP_TCP-toggle"},
    {"key": "OPENVPN_BACKUP_UDP",     "env": "OPENVPN_BACKUP_UDP",     "type": "flag",   "default": "n", "html_id": "OPENVPN_BACKUP_UDP-toggle"},
    {"key": "WIREGUARD_BACKUP",       "env": "WIREGUARD_BACKUP",       "type": "flag",   "default": "n", "html_id": "WIREGUARD_540_580-toggle"},
    {"key": "WARP_OUTBOUND",          "env": "WARP_OUTBOUND",          "type": "flag",   "default": "n", "html_id": "WARP_OUTBOUND-toggle"},
    {"key": "ssh_protection",         "env": "SSH_PROTECTION",         "type": "flag",   "default": "n", "html_id": "ssh_protection-toggle"},
    {"key": "attack_protection",      "env": "ATTACK_PROTECTION",      "type": "flag",   "default": "n", "html_id": "attack_protection-toggle"},
    {"key": "torrent_guard",          "env": "TORRENT_GUARD",          "type": "flag",   "default": "n", "html_id": "torrent_guard-toggle"},
    {"key": "restrict_forward",       "env": "RESTRICT_FORWARD",       "type": "flag",   "default": "n", "html_id": "restrict_forward-toggle"},
    {"key": "clear_hosts",            "env": "CLEAR_HOSTS",            "type": "flag",   "default": "n", "html_id": "clear-hosts-toggle"},
    {"key": "openvpn_host",           "env": "OPENVPN_HOST",           "type": "string", "default": "", "html_id": "openvpn-host-input"},
    {"key": "wireguard_host",         "env": "WIREGUARD_HOST",         "type": "string", "default": "", "html_id": "wireguard-host-input"},
]

# Список разрешенных IP-файлов с отображаемыми именами и описаниями
IP_FILES = {
    "akamai-ips.txt": {
        "name": "Akamai",
        "description": "Перенаправляет трафик Akamai через Antizapret, включая сайты и сервисы, использующие Akamai для доставки контента."
    },
    "amazon-ips.txt": {
        "name": "Amazon",
        "description": "Перенаправляет трафик Amazon через Antizapret, включая облачные сервисы и веб-сайты Amazon."
    },
    "digitalocean-ips.txt": {
        "name": "DigitalOcean",
        "description": "Перенаправляет трафик DigitalOcean через Antizapret, включая облачные серверы и сервисы, предоставляемые DigitalOcean"
    },
    "google-ips.txt": {
        "name": "Google",
        "description": "Перенаправляет трафик Google через Antizapret, включая поисковую систему и другие сервисы Google"
    },
    "hetzner-ips.txt": {
        "name": "Hetzner",
        "description": "Перенаправляет трафик Hetzner через Antizapret, включая серверы и сервисы, размещенные в дата-центрах Hetzner"
    },
    "ovh-ips.txt": {
        "name": "OVH",
        "description": "Перенаправляет трафик OVH через Antizapret, включая серверы и сервисы, размещенные в дата-центрах OVH"
    }
}
