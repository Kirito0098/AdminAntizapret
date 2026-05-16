def resolve_file_nav_group(file_type: str) -> str:
    if file_type in ("include_hosts", "exclude_hosts", "remove-hosts"):
        return "Домены"
    if file_type in ("include_ips", "exclude-ips", "forward-ips", "drop-ips"):
        return "IP и маршрутизация"
    if file_type in ("include-adblock-hosts", "exclude-adblock-hosts"):
        return "Рекламные фильтры"
    if file_type == "allow-ips":
        return "Безопасность"
    return "Прочее"
