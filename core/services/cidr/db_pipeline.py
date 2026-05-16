"""DB-backed CIDR file generation pipeline."""
import os

from config.antizapret_params import IP_FILES
from core.services.cidr.antifilter import (
    _build_antifilter_overlap_index,
    _cidr_contained_in_index,
    _cidr_overlaps_index,
    _load_antifilter_index,
)
from core.services.cidr.facade_compat import call as _facade_call, get_attr as _cfg
from core.services.cidr.geo import (
    _exclude_ru_country_cidrs,
    _is_strict_geo_country_set,
    _matches_country_scope,
    _matches_region_scope,
    _matches_strict_scope_value,
    _normalize_region_scopes,
)
from core.services.cidr.parsers import _normalize_cidrs, _render_file_content
from core.services.cidr.route_limits import (
    _apply_total_route_limit,
    _normalize_dpi_priority_files,
    _normalize_priority_min_budget,
)

def update_cidr_files_from_db(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
    filter_by_antifilter=False,
    total_cidr_limit=None,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
    progress_callback=None,
):
    """Generate CIDR route files by reading provider data from the local DB.

    Unlike update_cidr_files(), this function does NOT download anything —
    it relies on data previously loaded by CidrDbUpdaterService.refresh_all_providers().
    """
    from core.models import ProviderCidr, ProviderMeta

    _emit_progress(progress_callback, 2, "Подготовка: чтение данных из БД")
    _snapshot_baseline_if_missing()

    # Load antifilter index once (if requested) before processing files
    af_index = None
    if filter_by_antifilter:
        _emit_progress(progress_callback, 4, "Загрузка антифильтра из БД…")
        af_index = _load_antifilter_index()
        if af_index is None:
            _emit_progress(progress_callback, 100, "Ошибка: антифильтр не загружен в БД")
            return {
                "success": False,
                "message": "Фильтр по антифильтру запрошен, но БД антифильтра пуста. Сначала обновите антифильтр.",
                "updated": [],
                "failed": [],
                "skipped": [],
            }

    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    requested = selected_files or list(IP_FILES.keys())
    normalized = [name for name in requested if name in IP_FILES]

    if not normalized:
        _emit_progress(progress_callback, 100, "Нет файлов для обновления")
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
    failed = []
    skipped = []
    quality_by_file = {}
    total_files = len(normalized)

    # Single bulk query for all provider metadata and CIDR rows
    all_meta = {
        pm.provider_key: pm
        for pm in ProviderMeta.query.filter(ProviderMeta.provider_key.in_(normalized)).all()
    }
    _emit_progress(progress_callback, 9, "Загрузка CIDR из БД…")
    all_rows_by_provider: dict = {}
    for row in (
        ProviderCidr.query
        .filter(ProviderCidr.provider_key.in_(normalized))
        .with_entities(ProviderCidr.provider_key, ProviderCidr.cidr,
                       ProviderCidr.region_scope, ProviderCidr.country_codes)
        .all()
    ):
        all_rows_by_provider.setdefault(row.provider_key, []).append(row)

    for index, file_name in enumerate(normalized, start=1):
        progress_start = 10 + int(((index - 1) / max(total_files, 1)) * 82)
        _emit_progress(progress_callback, progress_start, f"Обработка {file_name} из БД")

        file_quality = {
            "raw_db_count": 0,
            "after_scope_count": 0,
            "after_ru_exclusion_count": 0,
            "after_antifilter_count": 0,
            "final_after_limit_count": 0,
            "status": "pending",
            "skip_reason": None,
        }

        meta = all_meta.get(file_name)
        if not meta or meta.refresh_status not in ("ok", "partial") or meta.cidr_count == 0:
            reason = "no_db_data" if (not meta or meta.cidr_count == 0) else f"db_status:{meta.refresh_status}"
            skipped.append({"file": file_name, "reason": reason})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = reason
            quality_by_file[file_name] = file_quality
            _emit_progress(progress_callback, progress_start, f"Файл {file_name} пропущен: {reason}")
            continue

        rows = all_rows_by_provider.get(file_name) or []
        file_quality["raw_db_count"] = len(rows)

        if is_all_scope:
            cidrs = [row.cidr for row in rows]
        else:
            cidrs = []
            for row in rows:
                has_region = row.region_scope is not None
                has_countries = row.country_codes is not None

                if has_region:
                    if not _matches_region_scope(row.region_scope, normalized_scopes):
                        continue
                    if strict_geo_filter and not _matches_strict_scope_value(row.region_scope, normalized_scopes):
                        continue
                    cidrs.append(row.cidr)
                elif has_countries:
                    countries = row.country_codes.split(",")
                    if not any(_matches_country_scope(c, normalized_scopes) for c in countries):
                        continue
                    if strict_geo_filter and not _is_strict_geo_country_set(set(countries)):
                        continue
                    cidrs.append(row.cidr)
                else:
                    if include_non_geo_fallback:
                        cidrs.append(row.cidr)

        # Extra safety: enforce IPv4-only output even if legacy DB rows contain IPv6.
        cidrs = _normalize_cidrs(cidrs)
        file_quality["after_scope_count"] = len(cidrs)

        if not cidrs:
            skipped.append({"file": file_name, "reason": "empty_after_geo_filter"})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = "empty_after_geo_filter"
            quality_by_file[file_name] = file_quality
            _emit_progress(progress_callback, progress_start, f"Файл {file_name} пропущен: empty_after_geo_filter")
            continue

        country_exclusion_meta = None
        if exclude_ru_cidrs:
            cidrs, country_exclusion_meta = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                file_quality["after_ru_exclusion_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_ru_exclusion"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_ru_exclusion_count"] = len(cidrs)
        else:
            file_quality["after_ru_exclusion_count"] = len(cidrs)

        antifilter_meta = None
        if af_index is not None:
            before = len(cidrs)
            cidrs = [c for c in cidrs if _cidr_overlaps_index(c, *af_index)]
            antifilter_meta = {"before": before, "after": len(cidrs)}
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_antifilter"})
                file_quality["after_antifilter_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_antifilter"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_antifilter_count"] = len(cidrs)
        else:
            file_quality["after_antifilter_count"] = len(cidrs)

        planned_updates.append({
            "file": file_name,
            "cidrs": cidrs,
            "source": f"db:{meta.source_used or 'unknown'}",
            "country_exclusion": country_exclusion_meta,
            "antifilter": antifilter_meta,
        })
        file_quality["status"] = "planned"
        quality_by_file[file_name] = file_quality

        progress_done = 10 + int((index / max(total_files, 1)) * 82)
        _emit_progress(progress_callback, progress_done, f"Файл {file_name}: {len(cidrs)} CIDR из БД")

    effective_limit = int(total_cidr_limit) if total_cidr_limit and int(total_cidr_limit) > 0 else _facade_call("_get_openvpn_route_total_cidr_limit")
    planned_updates, global_route_optimization_meta = _apply_total_route_limit(
        planned_updates,
        effective_limit,
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )

    os.makedirs(_cfg("LIST_DIR"), exist_ok=True)
    updated = []
    final_counts_by_file = {}

    for item in planned_updates:
        file_name = item["file"]
        cidrs = item.get("cidrs") or []
        source_name = item.get("source") or "db"
        final_counts_by_file[file_name] = len(cidrs)

        out_path = os.path.join(_cfg("LIST_DIR"), file_name)
        content = _render_file_content(file_name, cidrs, source_name)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(content)

        updated_item = {"file": file_name, "cidr_count": len(cidrs), "source": source_name}
        if item.get("country_exclusion"):
            updated_item["country_exclusion"] = item["country_exclusion"]
        if item.get("global_route_optimization"):
            updated_item["global_route_optimization"] = item["global_route_optimization"]
        updated.append(updated_item)

    for file_name in normalized:
        file_quality = quality_by_file.setdefault(
            file_name,
            {
                "raw_db_count": 0,
                "after_scope_count": 0,
                "after_ru_exclusion_count": 0,
                "after_antifilter_count": 0,
                "final_after_limit_count": 0,
                "status": "skipped",
                "skip_reason": "not_processed",
            },
        )
        file_quality["final_after_limit_count"] = int(final_counts_by_file.get(file_name, 0))
        if file_quality["status"] == "planned":
            if file_quality["final_after_limit_count"] > 0:
                file_quality["status"] = "updated"
                file_quality["skip_reason"] = None
            else:
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_total_limit"

    _emit_progress(progress_callback, 100, "Генерация CIDR-файлов из БД завершена")

    success = bool(updated)
    if updated and (failed or skipped):
        message = "CIDR-файлы обновлены из БД (часть пропущена или с ошибкой)"
    elif updated:
        message = "CIDR-файлы успешно обновлены из БД"
    elif failed:
        message = "Не удалось обновить CIDR-файлы из БД"
    else:
        message = "Нет данных в БД для обновления"

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
        "quality_report": {
            "providers": quality_by_file,
            "totals": {
                "requested_files": len(normalized),
                "raw_db_cidrs": sum(int(item.get("raw_db_count") or 0) for item in quality_by_file.values()),
                "after_scope_cidrs": sum(int(item.get("after_scope_count") or 0) for item in quality_by_file.values()),
                "after_ru_exclusion_cidrs": sum(int(item.get("after_ru_exclusion_count") or 0) for item in quality_by_file.values()),
                "after_antifilter_cidrs": sum(int(item.get("after_antifilter_count") or 0) for item in quality_by_file.values()),
                "final_after_limit_cidrs": sum(int(item.get("final_after_limit_count") or 0) for item in quality_by_file.values()),
            },
            "dropped_mandatory_files": ((global_route_optimization_meta or {}).get("dpi_mandatory") or {}).get("dropped_mandatory_files", []),
            "warnings": [
                warning
                for warning in [
                    (global_route_optimization_meta or {}).get("warning"),
                ]
                if warning
            ],
        },
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    return result

def estimate_cidr_matches_from_db(
    selected_files=None,
    region_scopes=None,
    include_non_geo_fallback=False,
    exclude_ru_cidrs=False,
    include_game_hosts=False,
    include_game_keys=None,
    strict_geo_filter=False,
    filter_by_antifilter=False,
    total_cidr_limit=None,
    dpi_priority_files=None,
    dpi_mandatory_files=None,
    dpi_priority_min_budget=0,
    progress_callback=None,
):
    """Preview how many CIDRs would be written from DB, without modifying any files."""
    from core.models import ProviderCidr, ProviderMeta

    def _report_progress(percent, stage):
        if not callable(progress_callback):
            return
        try:
            progress_callback(percent, stage)
        except Exception:
            return

    _report_progress(3, "Подготовка оценки CIDR из БД...")

    def _apply_total_route_limit_counts(counts_by_file):
        route_limit = int(total_cidr_limit) if total_cidr_limit and int(total_cidr_limit) > 0 else _facade_call("_get_openvpn_route_total_cidr_limit")
        if route_limit is None or int(route_limit) <= 0:
            return dict(counts_by_file), None

        ordered_files = list(counts_by_file.keys())
        original_total = sum(int(counts_by_file.get(name) or 0) for name in ordered_files)
        if original_total <= int(route_limit):
            return dict(counts_by_file), None

        route_limit = int(route_limit)
        counts = [int(counts_by_file.get(name) or 0) for name in ordered_files]
        non_empty_indices = [idx for idx, value in enumerate(counts) if value > 0]
        if not non_empty_indices:
            return dict(counts_by_file), None

        priority_files = set(_normalize_dpi_priority_files(dpi_priority_files))
        mandatory_files = set(_normalize_dpi_priority_files(dpi_mandatory_files))
        priority_files.update(mandatory_files)
        priority_min_budget = _normalize_priority_min_budget(dpi_priority_min_budget)

        budgets = {idx: 0 for idx in non_empty_indices}

        if route_limit < len(non_empty_indices):
            prioritized_indices = sorted(non_empty_indices, key=lambda idx: counts[idx], reverse=True)

            if mandatory_files:
                mandatory_first = sorted(
                    [
                        idx for idx in non_empty_indices
                        if ordered_files[idx] in mandatory_files
                    ],
                    key=lambda idx: counts[idx],
                    reverse=True,
                )
                fallback_rest = [idx for idx in prioritized_indices if idx not in mandatory_first]
                prioritized_indices = mandatory_first + fallback_rest
            elif priority_files and priority_min_budget > 0:
                priority_first = [idx for idx in non_empty_indices if ordered_files[idx] in priority_files]
                fallback_rest = [idx for idx in prioritized_indices if idx not in priority_first]
                prioritized_indices = priority_first + fallback_rest

            allowed_indices = set(prioritized_indices[:route_limit])
            for idx in non_empty_indices:
                budgets[idx] = 1 if idx in allowed_indices else 0
        else:
            reserved_total = 0

            if mandatory_files:
                for idx in non_empty_indices:
                    if ordered_files[idx] not in mandatory_files:
                        continue
                    budgets[idx] = max(budgets[idx], 1)
                    reserved_total += 1

            if reserved_total > route_limit:
                mandatory_indices = sorted(
                    [idx for idx in non_empty_indices if ordered_files[idx] in mandatory_files],
                    key=lambda idx: counts[idx],
                    reverse=True,
                )
                budgets = {idx: 0 for idx in non_empty_indices}
                allocated = 0
                for idx in mandatory_indices:
                    if allocated >= route_limit:
                        break
                    budgets[idx] = 1
                    allocated += 1
                reserved_total = allocated

            if priority_files and priority_min_budget > 0:
                for idx in non_empty_indices:
                    if ordered_files[idx] not in priority_files:
                        continue
                    reserved = min(counts[idx], priority_min_budget)
                    new_budget = max(budgets[idx], reserved)
                    reserved_total += max(0, new_budget - budgets[idx])
                    budgets[idx] = new_budget

            if reserved_total > route_limit:
                priority_indices = sorted(
                    [idx for idx in non_empty_indices if ordered_files[idx] in priority_files],
                    key=lambda idx: counts[idx],
                    reverse=True,
                )
                budgets = {idx: 0 for idx in non_empty_indices}
                allocated = 0
                for idx in priority_indices:
                    if allocated >= route_limit:
                        break
                    budgets[idx] = 1
                    allocated += 1
                reserved_total = allocated

            remaining_limit = max(route_limit - reserved_total, 0)
            remaining_capacity = {idx: max(0, counts[idx] - budgets[idx]) for idx in non_empty_indices}
            total_capacity = sum(remaining_capacity.values())
            raw_shares = {}

            if remaining_limit > 0 and total_capacity > 0:
                for idx in non_empty_indices:
                    capacity = remaining_capacity[idx]
                    if capacity <= 0:
                        raw_shares[idx] = 0.0
                        continue
                    share = (capacity * remaining_limit) / total_capacity
                    raw_shares[idx] = share
                    budgets[idx] += min(capacity, int(share))

                allocated = sum(budgets.values())
                if allocated > route_limit:
                    for idx, _ in sorted(budgets.items(), key=lambda pair: pair[1], reverse=True):
                        while budgets[idx] > 0 and allocated > route_limit:
                            budgets[idx] -= 1
                            allocated -= 1
                        if allocated <= route_limit:
                            break

                if allocated < route_limit:
                    for idx, _ in sorted(raw_shares.items(), key=lambda pair: pair[1] - int(pair[1]), reverse=True):
                        upper_bound = counts[idx]
                        while budgets[idx] < upper_bound and allocated < route_limit:
                            budgets[idx] += 1
                            allocated += 1
                        if allocated >= route_limit:
                            break

        compressed_counts_by_file = {}
        per_file = []
        for idx, file_name in enumerate(ordered_files):
            original_count = counts[idx]
            target_budget = budgets.get(idx, original_count)
            compressed_count = min(original_count, max(0, int(target_budget)))
            compressed_counts_by_file[file_name] = compressed_count
            per_file.append(
                {
                    "file": file_name,
                    "original_cidr_count": original_count,
                    "compressed_cidr_count": compressed_count,
                    "target_budget": int(target_budget),
                    "dpi_priority": bool(file_name in priority_files),
                    "dpi_mandatory": bool(file_name in mandatory_files),
                }
            )

        compressed_total = sum(compressed_counts_by_file.values())
        present_mandatory_files = {
            file_name for file_name, count in compressed_counts_by_file.items()
            if file_name in mandatory_files and count > 0
        }
        dropped_mandatory_files = sorted(mandatory_files - present_mandatory_files)

        meta = {
            "strategy": "global_total_route_limit",
            "limit": route_limit,
            "original_total_cidr_count": original_total,
            "compressed_total_cidr_count": compressed_total,
            "files": per_file,
        }
        if mandatory_files:
            meta["dpi_mandatory"] = {
                "enabled": True,
                "mandatory_files": sorted(mandatory_files),
                "dropped_mandatory_files": dropped_mandatory_files,
            }
            if dropped_mandatory_files:
                meta["warning"] = "Не все обязательные detected-провайдеры поместились в лимит"
        if priority_files and priority_min_budget > 0:
            meta["dpi_priority"] = {
                "enabled": True,
                "priority_files": sorted(priority_files),
                "priority_min_budget": priority_min_budget,
            }
        return compressed_counts_by_file, meta

    normalized_scopes = _normalize_region_scopes(region_scopes)
    is_all_scope = "all" in normalized_scopes

    af_index = None
    if filter_by_antifilter:
        af_index = _load_antifilter_index()

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

    planned_estimated = []
    failed = []
    skipped = []
    quality_by_file = {}
    total_files = max(len(normalized), 1)

    all_meta = {
        pm.provider_key: pm
        for pm in ProviderMeta.query.filter(ProviderMeta.provider_key.in_(normalized)).all()
    }

    is_fast_aggregate_mode = is_all_scope and not exclude_ru_cidrs and af_index is None
    if is_fast_aggregate_mode:
        _report_progress(8, "Быстрая оценка по агрегатам БД...")
        pre_limit_counts_by_file = {}
        source_by_file = {}

        for idx, file_name in enumerate(normalized, start=1):
            _report_progress(
                10 + int((idx - 1) * 65 / total_files),
                f"Оценка провайдера {idx}/{total_files}: {file_name}",
            )
            file_quality = {
                "raw_db_count": 0,
                "after_scope_count": 0,
                "after_ru_exclusion_count": 0,
                "after_antifilter_count": 0,
                "final_after_limit_count": 0,
                "status": "pending",
                "skip_reason": None,
            }

            meta = all_meta.get(file_name)
            if not meta or meta.refresh_status not in ("ok", "partial") or meta.cidr_count == 0:
                reason = "no_db_data" if (not meta or meta.cidr_count == 0) else f"db_status:{meta.refresh_status}"
                skipped.append({"file": file_name, "reason": reason})
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = reason
                quality_by_file[file_name] = file_quality
                continue

            count_value = max(0, int(meta.cidr_count or 0))
            file_quality["raw_db_count"] = count_value
            file_quality["after_scope_count"] = count_value
            file_quality["after_ru_exclusion_count"] = count_value
            file_quality["after_antifilter_count"] = count_value
            file_quality["status"] = "planned"
            quality_by_file[file_name] = file_quality
            pre_limit_counts_by_file[file_name] = count_value
            source_by_file[file_name] = f"db:{meta.source_used or 'unknown'}"

        _report_progress(80, "Оптимизация и применение лимита маршрутов...")
        final_counts_by_file, global_route_optimization_meta = _apply_total_route_limit_counts(pre_limit_counts_by_file)

        estimated = []
        for file_name in normalized:
            raw_count = int(pre_limit_counts_by_file.get(file_name, 0))
            final_count = int(final_counts_by_file.get(file_name, 0))
            if raw_count <= 0:
                continue
            estimated.append(
                {
                    "file": file_name,
                    "cidr_count": final_count,
                    "raw_cidr_count": raw_count,
                    "cidr_count_after_limit": final_count,
                    "source": source_by_file.get(file_name) or "db",
                    **({"limit_applied": True} if raw_count != final_count else {}),
                }
            )

        for file_name in normalized:
            file_quality = quality_by_file.setdefault(
                file_name,
                {
                    "raw_db_count": 0,
                    "after_scope_count": 0,
                    "after_ru_exclusion_count": 0,
                    "after_antifilter_count": 0,
                    "final_after_limit_count": 0,
                    "status": "skipped",
                    "skip_reason": "not_processed",
                },
            )
            file_quality["final_after_limit_count"] = int(final_counts_by_file.get(file_name, 0))
            if file_quality["status"] == "planned":
                if file_quality["final_after_limit_count"] > 0:
                    file_quality["status"] = "estimated"
                    file_quality["skip_reason"] = None
                else:
                    file_quality["status"] = "skipped"
                    file_quality["skip_reason"] = "empty_after_total_limit"

        selected_game_keys = _resolve_game_filter_selection(
            include_game_keys=include_game_keys,
            include_game_hosts=bool(include_game_hosts),
        )
        _, selected_game_domains = _collect_game_domains(selected_game_keys)

        result = {
            "success": True,
            "message": "Оценка CIDR из БД готова",
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
            "quality_report": {
                "providers": quality_by_file,
                "totals": {
                    "requested_files": len(normalized),
                    "raw_db_cidrs": sum(int(item.get("raw_db_count") or 0) for item in quality_by_file.values()),
                    "after_scope_cidrs": sum(int(item.get("after_scope_count") or 0) for item in quality_by_file.values()),
                    "after_ru_exclusion_cidrs": sum(int(item.get("after_ru_exclusion_count") or 0) for item in quality_by_file.values()),
                    "after_antifilter_cidrs": sum(int(item.get("after_antifilter_count") or 0) for item in quality_by_file.values()),
                    "final_after_limit_cidrs": sum(int(item.get("final_after_limit_count") or 0) for item in quality_by_file.values()),
                },
                "dropped_mandatory_files": ((global_route_optimization_meta or {}).get("dpi_mandatory") or {}).get("dropped_mandatory_files", []),
                "warnings": [
                    warning
                    for warning in [
                        (global_route_optimization_meta or {}).get("warning"),
                    ]
                    if warning
                ],
            },
        }

        if global_route_optimization_meta:
            result["global_route_optimization"] = global_route_optimization_meta

        _report_progress(98, "Формирование результата оценки...")
        return result

    _report_progress(8, "Загрузка CIDR из БД...")
    all_rows_by_provider = {}
    for row in (
        ProviderCidr.query
        .filter(ProviderCidr.provider_key.in_(normalized))
        .with_entities(ProviderCidr.provider_key, ProviderCidr.cidr, ProviderCidr.region_scope, ProviderCidr.country_codes)
        .all()
    ):
        all_rows_by_provider.setdefault(row.provider_key, []).append(row)

    for idx, file_name in enumerate(normalized, start=1):
        _report_progress(
            5 + int((idx - 1) * 75 / total_files),
            f"Оценка провайдера {idx}/{total_files}: {file_name}",
        )
        file_quality = {
            "raw_db_count": 0,
            "after_scope_count": 0,
            "after_ru_exclusion_count": 0,
            "after_antifilter_count": 0,
            "final_after_limit_count": 0,
            "status": "pending",
            "skip_reason": None,
        }
        meta = all_meta.get(file_name)
        if not meta or meta.refresh_status not in ("ok", "partial") or meta.cidr_count == 0:
            reason = "no_db_data" if (not meta or meta.cidr_count == 0) else f"db_status:{meta.refresh_status}"
            skipped.append({"file": file_name, "reason": reason})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = reason
            quality_by_file[file_name] = file_quality
            continue

        rows = all_rows_by_provider.get(file_name) or []
        file_quality["raw_db_count"] = len(rows)

        if is_all_scope:
            cidrs = [row.cidr for row in rows]
        else:
            cidrs = []
            for row in rows:
                has_region = row.region_scope is not None
                has_countries = row.country_codes is not None
                if has_region:
                    if not _matches_region_scope(row.region_scope, normalized_scopes):
                        continue
                    if strict_geo_filter and not _matches_strict_scope_value(row.region_scope, normalized_scopes):
                        continue
                    cidrs.append(row.cidr)
                elif has_countries:
                    countries = row.country_codes.split(",")
                    if not any(_matches_country_scope(c, normalized_scopes) for c in countries):
                        continue
                    if strict_geo_filter and not _is_strict_geo_country_set(set(countries)):
                        continue
                    cidrs.append(row.cidr)
                else:
                    if include_non_geo_fallback:
                        cidrs.append(row.cidr)

        cidrs = _normalize_cidrs(cidrs)
        file_quality["after_scope_count"] = len(cidrs)
        if not cidrs:
            skipped.append({"file": file_name, "reason": "empty_after_geo_filter"})
            file_quality["status"] = "skipped"
            file_quality["skip_reason"] = "empty_after_geo_filter"
            quality_by_file[file_name] = file_quality
            continue

        if exclude_ru_cidrs:
            cidrs, _ = _exclude_ru_country_cidrs(cidrs)
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_ru_exclusion"})
                file_quality["after_ru_exclusion_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_ru_exclusion"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_ru_exclusion_count"] = len(cidrs)
        else:
            file_quality["after_ru_exclusion_count"] = len(cidrs)

        if af_index is not None:
            cidrs = [c for c in cidrs if _cidr_overlaps_index(c, *af_index)]
            if not cidrs:
                skipped.append({"file": file_name, "reason": "empty_after_antifilter"})
                file_quality["after_antifilter_count"] = 0
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_antifilter"
                quality_by_file[file_name] = file_quality
                continue
            file_quality["after_antifilter_count"] = len(cidrs)
        else:
            file_quality["after_antifilter_count"] = len(cidrs)

        planned_estimated.append({
            "file": file_name,
            "cidrs": cidrs,
            "source": f"db:{meta.source_used or 'unknown'}",
        })
        file_quality["status"] = "planned"
        quality_by_file[file_name] = file_quality

    effective_limit = int(total_cidr_limit) if total_cidr_limit and int(total_cidr_limit) > 0 else _facade_call("_get_openvpn_route_total_cidr_limit")
    pre_limit_counts_by_file = {
        item["file"]: len(item.get("cidrs") or [])
        for item in planned_estimated
    }

    planned_estimated, global_route_optimization_meta = _apply_total_route_limit(
        planned_estimated,
        effective_limit,
        dpi_priority_files=dpi_priority_files,
        dpi_mandatory_files=dpi_mandatory_files,
        dpi_priority_min_budget=dpi_priority_min_budget,
    )
    _report_progress(88, "Оптимизация и применение лимита маршрутов...")

    estimated = [
        {
            "file": item["file"],
            "cidr_count": len(item.get("cidrs") or []),
            "raw_cidr_count": int(pre_limit_counts_by_file.get(item["file"], len(item.get("cidrs") or []))),
            "cidr_count_after_limit": len(item.get("cidrs") or []),
            "source": item.get("source") or "db",
            **({"limit_applied": True} if int(pre_limit_counts_by_file.get(item["file"], len(item.get("cidrs") or []))) != len(item.get("cidrs") or []) else {}),
        }
        for item in planned_estimated
    ]

    final_counts_by_file = {item["file"]: len(item.get("cidrs") or []) for item in planned_estimated}
    for file_name in normalized:
        file_quality = quality_by_file.setdefault(
            file_name,
            {
                "raw_db_count": 0,
                "after_scope_count": 0,
                "after_ru_exclusion_count": 0,
                "after_antifilter_count": 0,
                "final_after_limit_count": 0,
                "status": "skipped",
                "skip_reason": "not_processed",
            },
        )
        file_quality["final_after_limit_count"] = int(final_counts_by_file.get(file_name, 0))
        if file_quality["status"] == "planned":
            if file_quality["final_after_limit_count"] > 0:
                file_quality["status"] = "estimated"
                file_quality["skip_reason"] = None
            else:
                file_quality["status"] = "skipped"
                file_quality["skip_reason"] = "empty_after_total_limit"

    selected_game_keys = _resolve_game_filter_selection(
        include_game_keys=include_game_keys,
        include_game_hosts=bool(include_game_hosts),
    )
    _, selected_game_domains = _collect_game_domains(selected_game_keys)

    result = {
        "success": True,
        "message": "Оценка CIDR из БД готова",
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
        "quality_report": {
            "providers": quality_by_file,
            "totals": {
                "requested_files": len(normalized),
                "raw_db_cidrs": sum(int(item.get("raw_db_count") or 0) for item in quality_by_file.values()),
                "after_scope_cidrs": sum(int(item.get("after_scope_count") or 0) for item in quality_by_file.values()),
                "after_ru_exclusion_cidrs": sum(int(item.get("after_ru_exclusion_count") or 0) for item in quality_by_file.values()),
                "after_antifilter_cidrs": sum(int(item.get("after_antifilter_count") or 0) for item in quality_by_file.values()),
                "final_after_limit_cidrs": sum(int(item.get("final_after_limit_count") or 0) for item in quality_by_file.values()),
            },
            "dropped_mandatory_files": ((global_route_optimization_meta or {}).get("dpi_mandatory") or {}).get("dropped_mandatory_files", []),
            "warnings": [
                warning
                for warning in [
                    (global_route_optimization_meta or {}).get("warning"),
                ]
                if warning
            ],
        },
    }

    if global_route_optimization_meta:
        result["global_route_optimization"] = global_route_optimization_meta

    _report_progress(98, "Формирование результата оценки...")

    return result

