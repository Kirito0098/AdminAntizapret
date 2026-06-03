"""Общие хелперы для модулей routes/settings/api*.

Вынесены из routes/settings/api.py, чтобы разные группы обработчиков
(cidr-lists, cidr-db, tests, misc) могли переиспользовать парсинг payload без
дублирования. Публичные имена и поведение сохранены 1:1.
"""

import os

from core.services.cidr_list_updater import validate_provider_filter_keys


def normalize_key_list(raw_values):
    if not isinstance(raw_values, list):
        return []
    return [str(item).strip().lower() for item in raw_values if str(item).strip()]


def parse_provider_filter_payload(payload):
    include_raw = normalize_key_list(payload.get("include_provider_keys"))
    if not include_raw:
        include_raw = normalize_key_list(payload.get("include_game_keys"))
    exclude_raw = normalize_key_list(payload.get("exclude_provider_keys"))
    if not exclude_raw:
        exclude_raw = normalize_key_list(payload.get("exclude_game_keys"))

    include_validation = validate_provider_filter_keys(include_raw)
    exclude_validation = validate_provider_filter_keys(exclude_raw)
    include_provider_keys = include_validation.get("normalized_keys") or []
    exclude_provider_keys = exclude_validation.get("normalized_keys") or []
    invalid_keys = list(
        dict.fromkeys(
            (include_validation.get("invalid_keys") or [])
            + (exclude_validation.get("invalid_keys") or [])
        )
    )
    conflicted_provider_keys = sorted(set(include_provider_keys).intersection(set(exclude_provider_keys)))
    return {
        "include_provider_keys": include_provider_keys,
        "exclude_provider_keys": exclude_provider_keys,
        "invalid_keys": invalid_keys,
        "conflicted_provider_keys": conflicted_provider_keys,
    }


def tests_subprocess_env(app_root_dir):
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = app_root_dir + (":" + existing if existing else "")
    return env
