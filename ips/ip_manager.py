import os
from config.antizapret_params import IP_FILES
from ips.include_ips_header import write_include_ips_file

BASE_DIR = "/opt/AdminAntizapret"
INCLUDE_FILE = "/root/antizapret/config/include-ips.txt"
LIST_DIR = os.path.join(BASE_DIR, "ips", "list")


def load_include_ips():
    try:
        with open(INCLUDE_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip() and not line.startswith("#"))
    except FileNotFoundError:
        return set()


def save_include_ips(ips, comments=None):
    os.makedirs(os.path.dirname(INCLUDE_FILE), exist_ok=True)
    write_include_ips_file(INCLUDE_FILE, ips, comments=comments)


def list_ip_files():
    return IP_FILES.copy()


def get_file_states():
    states = {}
    for fname in list_ip_files().keys():
        states[fname] = os.path.exists(os.path.join(LIST_DIR, fname + ".added"))
    return states


def _read_ips_from_listfile(fname):
    path = os.path.join(LIST_DIR, fname)
    ips = set()
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ips.add(line)
    return ips


def add_from_file(fname):
    ips = _read_ips_from_listfile(fname)
    existing = load_include_ips()
    added = 0
    for ip in ips:
        if ip not in existing:
            existing.add(ip)
            added += 1
    comment = f"Add ips list {fname}"
    save_include_ips(existing, comments=comment)
    return added


def enable_file(fname):
    full = os.path.join(LIST_DIR, fname)
    if not os.path.exists(full):
        raise FileNotFoundError(fname)
    file_ips = _read_ips_from_listfile(fname)
    existing = load_include_ips()
    added_file = full + ".added"
    if not os.path.exists(added_file):
        # first time activation
        with open(added_file, "w") as f:
            for ip in file_ips:
                f.write(ip + "\n")
        existing.update(file_ips)
        count = len(file_ips)
    else:
        with open(added_file, "r") as f:
            added_ips = set(line.strip() for line in f if line.strip())
        new_ips = file_ips - added_ips
        count = 0
        if new_ips:
            existing.update(new_ips)
            with open(added_file, "a") as f:
                for ip in sorted(new_ips):
                    f.write(ip + "\n")
            count = len(new_ips)
    comment = f"Enable ips list {fname}"
    save_include_ips(existing, comments=comment)
    return count


def disable_file(fname):
    full = os.path.join(LIST_DIR, fname)
    added_file = full + ".added"
    existing = load_include_ips()
    if not os.path.exists(added_file):
        return 0
    with open(added_file, "r") as f:
        added_ips = set(line.strip() for line in f if line.strip())
    existing.difference_update(added_ips)
    try:
        os.remove(added_file)
    except OSError:
        pass
    comment = f"Disable ips list {fname}"
    save_include_ips(existing, comments=comment)
    return len(added_ips)


def sync_enabled():
    existing = load_include_ips()
    comments = []
    for fname, enabled in get_file_states().items():
        if not enabled:
            continue
        full = os.path.join(LIST_DIR, fname)
        added_file = full + ".added"
        if os.path.exists(added_file):
            file_ips = _read_ips_from_listfile(fname)
            with open(added_file, "r") as f:
                added_ips = set(line.strip() for line in f if line.strip())
            missing = file_ips - added_ips
            if missing:
                existing.update(missing)
                comments.append(f"Sync ips list {fname}")
                with open(added_file, "a") as f:
                    for ip in sorted(missing):
                        f.write(ip + "\n")
    if comments:
        save_include_ips(existing, comments=comments)
    return existing
