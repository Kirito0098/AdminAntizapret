"""HTTP download helpers for CIDR sources."""
from urllib import request

def _download_text(url, timeout=30, user_agent="AdminAntizapret-CIDR-Updater/1.0"):
    req = request.Request(url, headers={"User-Agent": user_agent})
    with request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")

