# app/config/antizapret_params.py

ANTIZAPRET_PARAMS = [
    {
        "key": "route_all",
        "env": "ROUTE_ALL",
        "type": "flag",
        "default": "n",
        "html_id": "route-all-toggle",
        "title": "Всех доменов, кроме .ru",
        "description": "Перенаправляет весь трафик через antizapret, кроме российских доменов (.ru, .рф) и исключений из exclude-hosts.txt",
    },
    {
        "key": "discord_include",
        "env": "DISCORD_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "discord-toggle",
        "title": "Discord",
        "description": "Перенаправляет трафик Discord через antizapret, включая голосовые каналы и обмен сообщениями",
    },
    {
        "key": "cloudflare_include",
        "env": "CLOUDFLARE_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "cloudflare-toggle",
        "title": "Cloudflare",
        "description": "Перенаправляет трафик Cloudflare через antizapret, включая сайты и сервисы, использующие Cloudflare для защиты от DDoS-атак",
    },
    {
        "key": "telegram_include",
        "env": "TELEGRAM_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "telegram-toggle",
        "title": "Telegram",
        "description": "Перенаправляет трафик Telegram через Antizapret, включая обмен сообщениями, каналы и группы",
    },
    {
        "key": "block_ads",
        "env": "BLOCK_ADS",
        "type": "flag",
        "default": "n",
        "html_id": "AdBlock-toggle",
        "title": "AdBlock",
        "description": "Блокировка рекламы, трекеров, вредоносных программ и фишинговых веб-сайтов в AntiZapret VPN (Antizapret-*) на основе правил AdGuard и OISD",
    },
    {
        "key": "whatsapp_include",
        "env": "WHATSAPP_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "whatsapp-toggle",
        "title": "WhatsApp",
        "description": "Перенаправляет трафик WhatsApp через Antizapret, включая обмен сообщениями, звонки и медиафайлы.",
    },
    {
        "key": "roblox_include",
        "env": "ROBLOX_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "roblox-toggle",
        "title": "Roblox",
        "description": "Перенаправляет трафик Roblox через Antizapret, включая игровой контент, платежи и социальные функции.",
    },
    {
        "key": "OPENVPN_BACKUP_TCP",
        "env": "OPENVPN_BACKUP_TCP",
        "type": "flag",
        "default": "n",
        "html_id": "OPENVPN_BACKUP_TCP-toggle",
        "title": "TCP",
        "description": "Включает резервные порты OpenVPN TCP (80,443,504,508) для обхода блокировок провайдеров, если стандартный порт заблокирован.",
    },
    {
        "key": "OPENVPN_BACKUP_UDP",
        "env": "OPENVPN_BACKUP_UDP",
        "type": "flag",
        "default": "n",
        "html_id": "OPENVPN_BACKUP_UDP-toggle",
        "title": "UDP",
        "description": "Включает резервные порты OpenVPN UDP (80,443,504,508) для обхода блокировок провайдеров, если стандартный порт заблокирован.",
    },
    {
        "key": "WIREGUARD_BACKUP",
        "env": "WIREGUARD_BACKUP",
        "param_label": "WIREGUARD_BACKUP_TCP",
        "type": "flag",
        "default": "n",
        "html_id": "WIREGUARD_540_580-toggle",
        "title": "WireGuard/AmneziaWG",
        "description": "Включает резервные порты WireGuard/AmneziaWG (540,580) для обхода блокировок провайдеров, если стандартный порт заблокирован.",
    },
    {
        "key": "ANTIZAPRET_WARP",
        "env": "ANTIZAPRET_WARP",
        "type": "flag",
        "default": "n",
        "html_id": "ANTIZAPRET_WARP-toggle",
        "title": "Cloudflare WARP for Antizapret",
        "description": "Включает отправку трафика Antizapret через Cloudflare WARP для улучшения устойчивости к блокировкам",
    },
    {
        "key": "VPN_WARP",
        "env": "VPN_WARP",
        "type": "flag",
        "default": "n",
        "html_id": "VPN_WARP-toggle",
        "title": "Cloudflare WARP for VPN outbound",
        "description": "Включает отправку исходящего VPN трафика через Cloudflare WARP",
    },
    {
        "key": "ssh_protection",
        "env": "SSH_PROTECTION",
        "type": "flag",
        "default": "n",
        "html_id": "ssh_protection-toggle",
        "title": "Защита от брутфорса SSH",
        "description": "Включить защиту от перебора паролей SSH (не более 3 новых подключений в час с одного IP)",
    },
    {
        "key": "attack_protection",
        "env": "ATTACK_PROTECTION",
        "type": "flag",
        "default": "n",
        "html_id": "attack_protection-toggle",
        "title": "Защита от атак",
        "description": "Блокирует подозрительную сетевую активность: превышение лимита подключений и попытки подключения по нетипичным портам.",
    },
    {
        "key": "scan_protection",
        "env": "SCAN_PROTECTION",
        "type": "flag",
        "default": "n",
        "html_id": "scan_protection-toggle",
        "title": "Scan protection",
        "description": "Скрывает сервер от простого сканирования: отключает ответ на ping и на запросы к закрытым портам.",
    },
    {
        "key": "torrent_guard",
        "env": "TORRENT_GUARD",
        "type": "flag",
        "default": "n",
        "html_id": "torrent_guard-toggle",
        "title": "Torrent Guard",
        "description": "Torrent Guard — если хостер запрещает торренты или присылает жалобы, эта опция поможет: при обнаружении торрент-трафика VPN будет блокироваться на 1 минуту",
    },
    {
        "key": "restrict_forward",
        "env": "RESTRICT_FORWARD",
        "param_label": "restrict_forward",
        "type": "flag",
        "default": "n",
        "html_id": "restrict_forward-toggle",
        "title": "Ограничение форвардинга",
        "description": "Включить ограничение форвардинга — через AntiZapret VPN будет маршрутизироваться только трафик к IP-адресам, которые явно указаны в файлах config/forward-ips.txt и result/route-ips.txt",
    },
    {
        "key": "clear_hosts",
        "env": "CLEAR_HOSTS",
        "type": "flag",
        "default": "n",
        "html_id": "clear-hosts-toggle",
        "title": "Очистка хостов: казино-домены",
        "description": "Удаляет домены с азартными играми при авто-обновлении списков (≈ 170 000 записей), уменьшая объём мусора и нагрузку.",
    },
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
