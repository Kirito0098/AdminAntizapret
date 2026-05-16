GROUP_ORDER = {
    "Домены": 10,
    "IP и маршрутизация": 20,
    "Рекламные фильтры": 30,
    "Безопасность": 40,
    "Прочее": 90,
}

_DEFAULT_SUBTITLE = (
    "Формат: по одному домену или IP в строке. Комментарии допускаются через #."
)

_DROP_IPS_SUBTITLE = (
    "Формат: по одной IPv4-подсети или адресу в CIDR на строку "
    "(например, 149.154.160.0/20). Эти сети всегда запрещены для форвардинга "
    "через VPN. Комментарии допускаются через #."
)


def get_editor_subtitle(file_type: str) -> str:
    if file_type == "drop-ips":
        return _DROP_IPS_SUBTITLE
    return _DEFAULT_SUBTITLE
