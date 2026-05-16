import shutil
import subprocess

SERVICE_GROUPS = [
    {
        "project_label": "AdminAntizapret",
        "services": [
            {
                "label": "Веб-панель",
                "description": "Интерфейс управления (admin-antizapret)",
                "units": ["admin-antizapret.service", "admin-antizapret"],
            },
            {
                "label": "Nginx",
                "description": "Прокси и HTTPS-шлюз",
                "units": ["nginx.service", "nginx"],
            },
            {
                "label": "vnStat",
                "description": "Учёт сетевого трафика",
                "units": ["vnstat.service", "vnstat"],
            },
        ],
    },
    {
        "project_label": "AntiZapret-VPN",
        "services": [
            {
                "label": "VPN ядро",
                "description": "Основной сервис AntiZapret (antizapret)",
                "units": ["antizapret.service", "antizapret"],
            },
            {
                "label": "OpenVPN AntiZapret (UDP/TCP)",
                "description": "Туннели antizapret-udp и antizapret-tcp",
                "unit_groups": [
                    ["openvpn-server@antizapret-udp.service", "openvpn-server@antizapret-udp"],
                    ["openvpn-server@antizapret-tcp.service", "openvpn-server@antizapret-tcp"],
                ],
            },
            {
                "label": "OpenVPN VPN (UDP/TCP)",
                "description": "Туннели vpn-udp и vpn-tcp",
                "unit_groups": [
                    ["openvpn-server@vpn-udp.service", "openvpn-server@vpn-udp"],
                    ["openvpn-server@vpn-tcp.service", "openvpn-server@vpn-tcp"],
                ],
            },
            {
                "label": "WireGuard AntiZapret",
                "description": "Интерфейс wg-quick@antizapret",
                "units": ["wg-quick@antizapret.service", "wg-quick@antizapret"],
            },
            {
                "label": "WireGuard VPN",
                "description": "Интерфейс wg-quick@vpn",
                "units": ["wg-quick@vpn.service", "wg-quick@vpn"],
            },
            {
                "label": "DNS резолвер #1",
                "description": "Knot Resolver instance kresd@1",
                "units": ["kresd@1.service", "kresd@1"],
            },
            {
                "label": "DNS резолвер #2",
                "description": "Knot Resolver instance kresd@2",
                "units": ["kresd@2.service", "kresd@2"],
            },
            {
                "label": "Автообновление AntiZapret",
                "description": "Таймер antizapret-update.timer",
                "units": ["antizapret-update.timer", "antizapret-update.service", "antizapret-update"],
            },
        ],
    },
]

_STATE_MAP = {
    "active": ("ok", "Работает"),
    "activating": ("warn", "Запуск"),
    "deactivating": ("warn", "Остановка"),
    "inactive": ("warn", "Остановлен"),
    "failed": ("error", "Ошибка"),
    "unknown": ("unknown", "Не найден"),
}
_SYSTEMD_STATES = {"active", "activating", "deactivating", "inactive", "failed"}


def _detect_state(unit_candidates):
    detected_state = "unknown"

    for unit in unit_candidates:
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            state = (proc.stdout or "").strip().lower()
            if not state:
                state = (proc.stderr or "").strip().lower()

            if state:
                detected_state = state

            if state in _SYSTEMD_STATES:
                break
        except Exception:
            detected_state = "unknown"

    return detected_state


def _aggregate_group_states(states):
    if not states:
        return "unknown", "Не найден"

    if "failed" in states:
        return "error", "Ошибка"
    if "activating" in states:
        return "warn", "Запуск"
    if "deactivating" in states:
        return "warn", "Остановка"

    total = len(states)
    active_count = sum(1 for state in states if state == "active")
    inactive_count = sum(1 for state in states if state == "inactive")
    unknown_count = sum(1 for state in states if state == "unknown")

    if active_count == total:
        return "ok", "Работает"
    if inactive_count == total:
        return "warn", "Остановлен"
    if unknown_count == total:
        return "unknown", "Не найден"
    if active_count > 0:
        return "warn", f"Частично {active_count}/{total}"

    return "unknown", "Неизвестно"


def collect_grouped_service_statuses():
    if not shutil.which("systemctl"):
        return [
            {
                "project_label": group["project_label"],
                "services": [
                    {
                        "label": item["label"],
                        "description": item["description"],
                        "state_class": "unknown",
                        "state_label": "n/a",
                    }
                    for item in group["services"]
                ],
            }
            for group in SERVICE_GROUPS
        ]

    grouped_statuses = []
    for group in SERVICE_GROUPS:
        statuses = []
        for item in group["services"]:
            if item.get("unit_groups"):
                grouped_states = [_detect_state(unit_group) for unit_group in item["unit_groups"]]
                state_class, state_label = _aggregate_group_states(grouped_states)
            else:
                detected_state = _detect_state(item["units"])
                state_class, state_label = _STATE_MAP.get(detected_state, ("unknown", "Неизвестно"))

            statuses.append(
                {
                    "label": item["label"],
                    "description": item["description"],
                    "state_class": state_class,
                    "state_label": state_label,
                }
            )

        grouped_statuses.append(
            {
                "project_label": group["project_label"],
                "services": statuses,
            }
        )

    return grouped_statuses
