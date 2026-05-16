import os
import shutil
from config.antizapret_params import IP_FILES
from ips.include_ips_header import write_include_ips_file

BASE_DIR = "/opt/AdminAntizapret"
CONFIG_DIR = "/root/antizapret/config"
INCLUDE_FILE = os.path.join(CONFIG_DIR, "include-ips.txt")
LIST_DIR = os.path.join(BASE_DIR, "ips", "list")


def _provider_prefix(fname):
    base_name = os.path.basename(fname)
    if base_name.endswith("-ips.txt"):
        return base_name[: -len("-ips.txt")]
    if base_name.endswith(".txt"):
        return base_name[: -len(".txt")]
    return base_name


def _masked_include_file_path(fname):
    return os.path.join(CONFIG_DIR, f"AP-{_provider_prefix(fname)}-include-ips.txt")


def _legacy_masked_include_file_path(fname):
    return os.path.join(CONFIG_DIR, f"{_provider_prefix(fname)}-include-ips.txt")


def _legacy_added_file_path(fname):
    return os.path.join(LIST_DIR, fname + ".added")


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
        states[fname] = (
            os.path.exists(_masked_include_file_path(fname))
            or os.path.exists(_legacy_masked_include_file_path(fname))
            or os.path.exists(_legacy_added_file_path(fname))
        )
    return states


def get_source_states():
    """Returns dict of filename -> bool indicating if source data is available.

    A source is considered available if either the list file exists in LIST_DIR
    or the corresponding AP-* include file exists in CONFIG_DIR. The AP-* file
    is a verbatim copy of the list file written by enable_file(), so its presence
    means the data is intact even if the LIST_DIR copy was lost.
    When the AP-* file exists but the list file is absent, restore_source_from_config()
    can recreate the list file before the next enable/disable cycle.
    """
    states = {}
    for fname in list_ip_files().keys():
        states[fname] = (
            os.path.exists(os.path.join(LIST_DIR, fname))
            or os.path.exists(_masked_include_file_path(fname))
        )
    return states


def restore_source_from_config():
    """Restores missing LIST_DIR files from existing AP-* config files.

    Call this when ips/list/ files are absent but AP-* counterparts exist in
    CONFIG_DIR (e.g., after a database rebuild that deleted the list files).
    Returns dict of filename -> bool indicating which files were restored.
    """
    restored = {}
    for fname in list_ip_files().keys():
        list_path = os.path.join(LIST_DIR, fname)
        ap_path = _masked_include_file_path(fname)
        if not os.path.exists(list_path) and os.path.exists(ap_path):
            try:
                os.makedirs(LIST_DIR, exist_ok=True)
                shutil.copyfile(ap_path, list_path)
                restored[fname] = True
            except OSError:
                restored[fname] = False
    return restored


def _read_ips_from_listfile(fname):
    path = os.path.join(LIST_DIR, fname)
    ips = set()
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ips.add(line)
    return ips


def _read_ips_from_path(path):
    ips = set()
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ips.add(line)
    return ips


def _read_file_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def add_from_file(fname):
    return enable_file(fname)


def enable_file(fname):
    full = os.path.join(LIST_DIR, fname)
    if not os.path.exists(full):
        raise FileNotFoundError(fname)

    file_ips = _read_ips_from_path(full)
    os.makedirs(CONFIG_DIR, exist_ok=True)

    ap_masked_include_file = _masked_include_file_path(fname)
    shutil.copyfile(full, ap_masked_include_file)

    # Remove old mask file format without AP- prefix to avoid duplicate processing.
    legacy_masked_include_file = _legacy_masked_include_file_path(fname)
    if os.path.exists(legacy_masked_include_file):
        try:
            os.remove(legacy_masked_include_file)
        except OSError:
            pass

    # Remove legacy marker if present: active state is now determined by masked config files.
    added_file = _legacy_added_file_path(fname)
    if os.path.exists(added_file):
        try:
            os.remove(added_file)
        except OSError:
            pass

    return len(file_ips)


def disable_file(fname):
    removed_count = 0
    file_ips = set()

    try:
        file_ips = _read_ips_from_listfile(fname)
    except FileNotFoundError:
        file_ips = set()

    masked_include_file = _masked_include_file_path(fname)
    if os.path.exists(masked_include_file):
        removed_count = len(_read_ips_from_path(masked_include_file))
        try:
            os.remove(masked_include_file)
        except OSError:
            pass

    legacy_masked_include_file = _legacy_masked_include_file_path(fname)
    if os.path.exists(legacy_masked_include_file):
        if not removed_count:
            removed_count = len(_read_ips_from_path(legacy_masked_include_file))
        try:
            os.remove(legacy_masked_include_file)
        except OSError:
            pass

    added_file = _legacy_added_file_path(fname)
    added_ips = set()
    if os.path.exists(added_file):
        with open(added_file, "r") as f:
            added_ips = set(line.strip() for line in f if line.strip())

    cleanup_ips = added_ips or file_ips

    if cleanup_ips:
        existing = load_include_ips()
        before_count = len(existing)
        existing.difference_update(cleanup_ips)
        if len(existing) != before_count:
            comment = f"Disable ips list {fname}"
            save_include_ips(existing, comments=comment)

    try:
        os.remove(added_file)
    except OSError:
        pass

    if removed_count:
        return removed_count
    return len(cleanup_ips)


def sync_enabled():
    existing = load_include_ips()
    for fname, enabled in get_file_states().items():
        if not enabled:
            continue

        masked_file_exists = os.path.exists(_masked_include_file_path(fname))
        legacy_masked_file = _legacy_masked_include_file_path(fname)
        legacy_masked_file_exists = os.path.exists(legacy_masked_file)

        # Migrate old mask naming (<name>-include-ips.txt) to AP-<name>-include-ips.txt.
        if legacy_masked_file_exists and not masked_file_exists:
            try:
                shutil.move(legacy_masked_file, _masked_include_file_path(fname))
                masked_file_exists = True
                legacy_masked_file_exists = False
            except OSError:
                pass
        elif legacy_masked_file_exists and masked_file_exists:
            try:
                os.remove(legacy_masked_file)
                legacy_masked_file_exists = False
            except OSError:
                pass

        legacy_file = _legacy_added_file_path(fname)
        legacy_file_exists = os.path.exists(legacy_file)

        # Migrate legacy enabled state to the new mask-based include files.
        if legacy_file_exists and not masked_file_exists:
            try:
                enable_file(fname)
            except FileNotFoundError:
                continue
        elif legacy_file_exists:
            try:
                os.remove(legacy_file)
            except OSError:
                pass

    return existing


def sync_enabled_from_list():
    # Ensure legacy states are migrated before explicit synchronization.
    sync_enabled()

    synced_files = 0
    updated_files = 0
    missing_sources = []

    for fname, enabled in get_file_states().items():
        if not enabled:
            continue

        source_file = os.path.join(LIST_DIR, fname)
        if not os.path.exists(source_file):
            missing_sources.append(fname)
            continue

        target_file = _masked_include_file_path(fname)
        legacy_target_file = _legacy_masked_include_file_path(fname)
        os.makedirs(CONFIG_DIR, exist_ok=True)

        source_data = _read_file_bytes(source_file)
        target_data = _read_file_bytes(target_file) if os.path.exists(target_file) else None

        if source_data != target_data:
            shutil.copyfile(source_file, target_file)
            updated_files += 1

        if os.path.exists(legacy_target_file):
            try:
                os.remove(legacy_target_file)
            except OSError:
                pass

        synced_files += 1

    return {
        "synced_files": synced_files,
        "updated_files": updated_files,
        "missing_sources": missing_sources,
    }
