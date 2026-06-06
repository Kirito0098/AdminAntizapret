"""Статические пути и константы файловой структуры AntiZapret.

Вынесено из app.py, чтобы app.py не был «god module»: здесь только данные
(пути к каталогам конфигов, имена файлов, паттерны), без побочных эффектов.
Имена сохранены 1:1 — app.py реэкспортирует их, поэтому route_wiring и тесты,
обращающиеся к этим константам через locals()/импорт app, продолжают работать.
"""

import re

#   hostname/public_download/
RESULT_DIR_FILES = {
    "keenetic": "keenetic-wireguard-routes.txt",
    "mikrotik": "mikrotik-wireguard-routes.txt",
    "ips": "route-ips.txt",
    "tplink": "tp-link-openvpn-routes.txt",
}

OPENVPN_FOLDERS = [
    "/root/antizapret/client/openvpn/antizapret",
    "/root/antizapret/client/openvpn/antizapret-tcp",
    "/root/antizapret/client/openvpn/antizapret-udp",
    "/root/antizapret/client/openvpn/vpn",
    "/root/antizapret/client/openvpn/vpn-tcp",
    "/root/antizapret/client/openvpn/vpn-udp",
]

GROUP_FOLDERS = {
    'GROUP_UDP\\TCP': [OPENVPN_FOLDERS[0], OPENVPN_FOLDERS[3]],  # UDP AND tcp
    'GROUP_UDP':  [OPENVPN_FOLDERS[2], OPENVPN_FOLDERS[5]],  # UDP only
    'GROUP_TCP':  [OPENVPN_FOLDERS[1], OPENVPN_FOLDERS[4]],  # TCP only
}

CONFIG_PATHS = {
    "openvpn": GROUP_FOLDERS["GROUP_UDP\\TCP"],
    "wg": [
        "/root/antizapret/client/wireguard/antizapret",
        "/root/antizapret/client/wireguard/vpn",
    ],
    "amneziawg": [
        "/root/antizapret/client/amneziawg/antizapret",
        "/root/antizapret/client/amneziawg/vpn",
    ],
    "antizapret_result": [
        "/root/antizapret/result"
    ],
}

OPENVPN_BANNED_CLIENTS_FILE = "/etc/openvpn/server/banned_clients"
OPENVPN_CLIENT_CONNECT_SCRIPT = "/etc/openvpn/server/scripts/client-connect.sh"
CLIENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

CLIENT_CONNECT_BAN_CHECK_BLOCK = (
    "BANNED=\"/etc/openvpn/server/banned_clients\"\n\n"
    "if [ -f \"$BANNED\" ]; then\n"
    "    if grep -q \"^$common_name$\" \"$BANNED\"; then\n"
    "        echo \"Client $common_name banned\" >&2\n"
    "        exit 1\n"
    "    fi\n"
    "fi\n"
)

MIN_CERT_EXPIRE = 1
MAX_CERT_EXPIRE = 3650
