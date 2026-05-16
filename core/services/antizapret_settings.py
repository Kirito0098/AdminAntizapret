import re

from config.antizapret_params import ANTIZAPRET_PARAMS

ANTIZAPRET_SETUP_FILE = "/root/antizapret/setup"


def read_antizapret_settings(path=ANTIZAPRET_SETUP_FILE):
    """Читает antizapret setup и возвращает dict {key: value}."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        content = ""

    settings = {}
    for p in ANTIZAPRET_PARAMS:
        key, env, typ, default = p["key"], p["env"], p["type"], p["default"]
        if typ == "string":
            m = re.search(rf"^{re.escape(env)}=(.+)$", content, re.M | re.I)
            settings[key] = m.group(1).strip() if m else default
        else:
            m = re.search(rf"^{re.escape(env)}=([yn])$", content, re.M | re.I)
            settings[key] = m.group(1).lower() if m else default
    return settings
