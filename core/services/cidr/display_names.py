"""Human-readable labels for CIDR provider files."""
from config.antizapret_params import IP_FILES


def cidr_provider_display_name(file_name: str) -> str:
    meta = IP_FILES.get(file_name) or {}
    name = str(meta.get("name") or "").strip()
    if name:
        return name
    base = str(file_name or "").replace("-ips.txt", "").replace(".txt", "")
    return base.replace("-", " ").title() or str(file_name)
