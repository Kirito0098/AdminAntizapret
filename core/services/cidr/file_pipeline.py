"""File-based CIDR update pipeline (download providers)."""
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from config.antizapret_params import IP_FILES
from core.services.cidr.constants import RUNTIME_BACKUP_RETENTION_SECONDS
from core.services.cidr.facade_compat import call as _facade_call, get_attr as _cfg
from core.services.cidr.geo import _exclude_ru_country_cidrs, _normalize_region_scopes
from core.services.cidr.parsers import _render_file_content
from core.services.cidr.games import (
    _collect_game_domains,
    _resolve_game_filter_selection,
    sync_game_hosts_filter,
)
from core.services.cidr.route_limits import (
    _apply_total_route_limit,
    _optimize_cidrs_for_openvpn_routes,
    _supports_geo_scope,
)


def _pool_collect_cidrs(sources, effective_scopes, strict_geo_filter=False):
    return _facade_call(
        "_collect_cidrs_from_sources",
        sources,
        effective_scopes,
        strict_geo_filter=strict_geo_filter,
    )

def _snapshot_baseline_if_missing():
    os.makedirs(_cfg("BASELINE_DIR"), exist_ok=True)
    for file_name in IP_FILES.keys():
        source_path = os.path.join(_cfg("LIST_DIR"), file_name)
        target_path = os.path.join(_cfg("BASELINE_DIR"), file_name)
        if os.path.exists(target_path):
            continue
        if os.path.exists(source_path):
            shutil.copyfile(source_path, target_path)

def _make_runtime_backup(files):
    _prune_runtime_backups()

    backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = os.path.join(_cfg("RUNTIME_BACKUP_ROOT"), backup_stamp)
    os.makedirs(backup_dir, exist_ok=True)

    copied = []
    for file_name in files:
        source_path = os.path.join(_cfg("LIST_DIR"), file_name)
        if not os.path.exists(source_path):
            continue
        shutil.copyfile(source_path, os.path.join(backup_dir, file_name))
        copied.append(file_name)

    return backup_dir, copied

def _prune_runtime_backups(now_ts=None, retention_seconds=RUNTIME_BACKUP_RETENTION_SECONDS):
    if retention_seconds <= 0:
        return []

    os.makedirs(_cfg("RUNTIME_BACKUP_ROOT"), exist_ok=True)

    current_ts = float(now_ts) if now_ts is not None else datetime.now(timezone.utc).timestamp()
    cutoff_ts = current_ts - float(retention_seconds)
    removed_dirs = []

    for entry_name in os.listdir(_cfg("RUNTIME_BACKUP_ROOT")):
        entry_path = os.path.join(_cfg("RUNTIME_BACKUP_ROOT"), entry_name)
        if not os.path.isdir(entry_path):
            continue

        try:
            if os.path.getmtime(entry_path) > cutoff_ts:
                continue
            shutil.rmtree(entry_path)
            removed_dirs.append(entry_name)
        except OSError:
            continue

    return removed_dirs

def _emit_progress(progress_callback, percent, stage):
    if progress_callback is None:
        return
    try:
        safe_percent = max(0, min(100, int(percent)))
    except (TypeError, ValueError):
        safe_percent = 0

    text = str(stage or "").strip() or "Выполняется операция"
    progress_callback(safe_percent, text)

def update_cidr_files(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
    progress_callback=None,
):
    _emit_progress(progress_callback, 2, "Подготовка к обновлению CIDR-файлов")
    _snapshot_baseline_if_missing()
    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    if not normalized:
        _emit_progress(progress_callback, 100, "Обновление завершено")
        return {
            "success": False,
            "message": "Не выбраны корректные CIDR-файлы",
            "updated": [],
            "failed": [],
            "skipped": [],
        }

    _emit_progress(progress_callback, 8, "Создание резервной копии текущих CIDR-файлов")
    backup_dir, backup_files = _make_runtime_backup(normalized)

    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    game_filter_sync_result = sync_game_hosts_filter(include_game_keys=selected_game_keys)
    game_hosts_filter = game_filter_sync_result.get("game_hosts_filter") or {}
    game_ips_filter = game_filter_sync_result.get("game_ips_filter") or {}
    if not game_filter_sync_result.get("success"):
        _emit_progress(progress_callback, 100, "Ошибка синхронизации игрового фильтра")
        return {
            "success": False,
            "message": "Не удалось синхронизировать игровой фильтр",
            "updated": [],
            "failed": [],
            "skipped": [],
            "backup_dir": backup_dir,
            "backup_files": backup_files,
            "game_hosts_filter": game_hosts_filter,
            "game_ips_filter": game_ips_filter,
        }

    planned_updates = []
    updated = []
    failed = []
    skipped = []

    total_files = len(normalized)

    # Phase 1: resolve which files to download and their effective scopes
    download_jobs = []  # [(file_name, sources, effective_scopes)]
    for file_name in normalized:
        sources = _cfg("PROVIDER_SOURCES").get(file_name) or []
        if not sources:
            skipped.append({"file": file_name, "reason": "source_not_configured"})
            continue

        effective_scopes = list(normalized_scopes)
        if not is_all_scope:
            if not _supports_geo_scope(sources):
                if include_non_geo_fallback:
                    effective_scopes = ["all"]
                else:
                    skipped.append({"file": file_name, "reason": "geo_scope_not_supported"})
                    continue

        download_jobs.append((file_name, sources, effective_scopes))

    # Phase 2: parallel HTTP downloads
    download_results = {}  # file_name -> (cidrs, source_name, last_error)
    _emit_progress(progress_callback, 10, f"Скачивание {len(download_jobs)} провайдеров параллельно…")
    if download_jobs:
        max_workers = min(len(download_jobs), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_file = {
                pool.submit(
                    _pool_collect_cidrs,
                    sources,
                    effective_scopes,
                    strict_geo_filter=bool(strict_geo_filter),
                ): file_name
                for file_name, sources, effective_scopes in download_jobs
            }
            completed = 0
            for future in as_completed(future_to_file):
                file_name = future_to_file[future]
                completed += 1
                pct = 10 + int((completed / len(download_jobs)) * 50)
                _emit_progress(progress_callback, pct, f"Загружен {file_name} ({completed}/{len(download_jobs)})")
                try:
                    download_results[file_name] = future.result()
                except Exception as exc:  # noqa: BLE001
                    download_results[file_name] = ([], "", str(exc))

    # Phase 3: post-process in original order
    for index, (file_name, sources, effective_scopes) in enumerate(download_jobs, start=1):
        progress_start = 60 + int(((index - 1) / max(len(download_jobs), 1)) * 32)
        _emit_progress(progress_callback, progress_start, f"Обработка {file_name}")

        cidrs, source_name, last_error = download_results.get(file_name, ([], "", "download missing"))
        if not cidrs:
            failed.append({"file": file_name, "error": last_error})
            continue

        country_exclusion_meta = None
        if exclude_ru_cidrs and "all" in effective_scopes:
            cidrs, country_exclusion_meta = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                continue

        cidrs, source_name, optimization_meta = _optimize_cidrs_for_openvpn_routes(
            sources=sources,
            effective_scopes=effective_scopes,
            cidrs=cidrs,
            source_name=source_name,
            strict_geo_filter=bool(strict_geo_filter),
        )

        planned_updates.append(
            {
                "file": file_name,
                "cidrs": cidrs,
                "source": source_name,
                "country_exclusion": country_exclusion_meta,
                "route_optimization": optimization_meta,
            }
        )
        _emit_progress(progress_callback, progress_start, f"Файл {file_name} готов: {len(cidrs)} CIDR")

    planned_updates, global_route_optimization_meta = _apply_total_route_limit(
        planned_updates,
        _facade_call("_get_openvpn_route_total_cidr_limit"),
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )

    for item in planned_updates:
        file_name = item["file"]
        cidrs = item.get("cidrs") or []
        source_name = item.get("source") or "unknown"

        out_path = os.path.join(_cfg("LIST_DIR"), file_name)
        content = _render_file_content(file_name, cidrs, source_name)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(content)

        updated_item = {"file": file_name, "cidr_count": len(cidrs), "source": source_name}
        if item.get("country_exclusion"):
            updated_item["country_exclusion"] = item["country_exclusion"]
        if item.get("route_optimization"):
            updated_item["route_optimization"] = item["route_optimization"]
        if item.get("global_route_optimization"):
            updated_item["global_route_optimization"] = item["global_route_optimization"]
        updated.append(updated_item)

    success = bool(updated)
    if updated and failed:
        message = "Часть CIDR-файлов обновлена, часть завершилась с ошибкой"
    elif updated:
        message = "CIDR-файлы успешно обновлены"
    elif failed:
        message = "Не удалось обновить CIDR-файлы"
    else:
        message = "Нет файлов для обновления"

    _emit_progress(progress_callback, 100, "Обновление CIDR-файлов завершено")

    result = {
        "success": success,
        "message": message,
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
        "backup_dir": backup_dir,
        "backup_files": backup_files,
        "game_hosts_filter": game_hosts_filter,
        "game_ips_filter": game_ips_filter,
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    return result

def estimate_cidr_matches(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
):
    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    if not normalized:
        return {
            "success": False,
            "message": "Не выбраны корректные CIDR-файлы",
            "estimated": [],
            "failed": [],
            "skipped": [],
        }

    estimated = []
    planned_estimated = []
    failed = []
    skipped = []

    for file_name in normalized:
        sources = _cfg("PROVIDER_SOURCES").get(file_name) or []
        if not sources:
            skipped.append({"file": file_name, "reason": "source_not_configured"})
            continue

        effective_scopes = list(normalized_scopes)

        if not is_all_scope:
            supports_geo_scope = _supports_geo_scope(sources)
            if not supports_geo_scope:
                if include_non_geo_fallback:
                    effective_scopes = ["all"]
                else:
                    skipped.append({"file": file_name, "reason": "geo_scope_not_supported"})
                    continue

        cidrs, source_name, last_error = _facade_call(
            "_collect_cidrs_from_sources",
            sources,
            effective_scopes,
            strict_geo_filter=bool(strict_geo_filter),
        )

        if not cidrs:
            failed.append({"file": file_name, "error": last_error})
            continue

        country_exclusion_meta = None
        if exclude_ru_cidrs and "all" in effective_scopes:
            cidrs, country_exclusion_meta = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                continue

        cidrs, source_name, optimization_meta = _optimize_cidrs_for_openvpn_routes(
            sources=sources,
            effective_scopes=effective_scopes,
            cidrs=cidrs,
            source_name=source_name,
            strict_geo_filter=bool(strict_geo_filter),
        )

        planned_estimated.append(
            {
                "file": file_name,
                "cidrs": cidrs,
                "source": source_name,
                "country_exclusion": country_exclusion_meta,
                "route_optimization": optimization_meta,
            }
        )

    pre_limit_counts_by_file = {
        item["file"]: len(item.get("cidrs") or [])
        for item in planned_estimated
    }

    planned_estimated, global_route_optimization_meta = _apply_total_route_limit(
        planned_estimated,
        _facade_call("_get_openvpn_route_total_cidr_limit"),
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )

    for item in planned_estimated:
        post_limit_count = len(item.get("cidrs") or [])
        pre_limit_count = int(pre_limit_counts_by_file.get(item["file"], post_limit_count))
        estimated_item = {
            "file": item["file"],
            "cidr_count": post_limit_count,
            "raw_cidr_count": pre_limit_count,
            "cidr_count_after_limit": post_limit_count,
            "source": item.get("source") or "unknown",
        }
        if pre_limit_count != post_limit_count:
            estimated_item["limit_applied"] = True
        if item.get("country_exclusion"):
            estimated_item["country_exclusion"] = item["country_exclusion"]
        if item.get("route_optimization"):
            estimated_item["route_optimization"] = item["route_optimization"]
        if item.get("global_route_optimization"):
            estimated_item["global_route_optimization"] = item["global_route_optimization"]
        estimated.append(estimated_item)

    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    _, selected_game_domains = _collect_game_domains(selected_game_keys)

    result = {
        "success": True,
        "message": "Оценка CIDR перед обновлением готова",
        "estimated": estimated,
        "failed": failed,
        "skipped": skipped,
        "game_hosts_filter": {
            "enabled": bool(selected_game_keys),
            "selected_game_keys": selected_game_keys,
            "selected_game_count": len(selected_game_keys),
            "domain_count": len(selected_game_domains),
            "file": _cfg("GAME_INCLUDE_HOSTS_FILE"),
        },
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    return result

def rollback_to_baseline(selected_files=None, progress_callback=None):
    _emit_progress(progress_callback, 3, "Подготовка к откату CIDR-файлов")
    _snapshot_baseline_if_missing()

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    restored = []
    missing = []

    total_files = len(normalized)
    if total_files == 0:
        _emit_progress(progress_callback, 100, "Откат завершен")

    for index, file_name in enumerate(normalized, start=1):
        progress_start = 8 + int(((index - 1) / max(total_files, 1)) * 90)
        _emit_progress(progress_callback, progress_start, f"Откат файла {file_name}")

        baseline_path = os.path.join(_cfg("BASELINE_DIR"), file_name)
        target_path = os.path.join(_cfg("LIST_DIR"), file_name)

        if not os.path.exists(baseline_path):
            missing.append(file_name)
            progress_done = 8 + int((index / max(total_files, 1)) * 90)
            _emit_progress(progress_callback, progress_done, f"Файл {file_name} пропущен: baseline не найден")
            continue

        shutil.copyfile(baseline_path, target_path)
        restored.append(file_name)
        progress_done = 8 + int((index / max(total_files, 1)) * 90)
        _emit_progress(progress_callback, progress_done, f"Файл {file_name} восстановлен")

    success = bool(restored)
    if restored and missing:
        message = "Откат выполнен частично"
    elif restored:
        message = "Откат к эталонным CIDR-спискам выполнен"
    else:
        message = "Эталонные файлы не найдены"

    _emit_progress(progress_callback, 100, "Откат CIDR-файлов завершен")

    return {
        "success": success,
        "message": message,
        "restored": restored,
        "missing": missing,
    }

