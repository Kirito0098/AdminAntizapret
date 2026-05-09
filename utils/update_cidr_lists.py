#!/usr/bin/env python3
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.services.cidr_list_updater import (
    estimate_cidr_matches,
    get_available_regions,
    rollback_to_baseline,
    update_cidr_files,
)


def _parse_regions(raw_value):
    if not raw_value:
        return None

    wanted = []
    for item in raw_value.split(","):
        token = item.strip()
        if token:
            wanted.append(token)
    return wanted or None


def _parse_region_scopes(raw_value):
    if not raw_value:
        return ["all"]

    wanted = []
    for item in str(raw_value).split(","):
        token = item.strip().lower()
        if token:
            wanted.append(token)

    if not wanted:
        return ["all"]

    if "all" in wanted:
        return ["all"]

    return wanted


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Обновление и откат CIDR-файлов в ips/list",
    )
    parser.add_argument(
        "--action",
        choices=["update", "rollback", "list", "estimate"],
        default="update",
        help="Действие: update (обновить), rollback (откат к эталону), list (показать регионы), estimate (оценить CIDR до обновления)",
    )
    parser.add_argument(
        "--regions",
        default="",
        help="Список файлов через запятую (например: amazon-ips.txt,google-ips.txt). По умолчанию: все",
    )
    parser.add_argument(
        "--region-scopes",
        default="all",
        help=(
            "Геофильтр для update (можно несколько через запятую): "
            "all,europe,north-america,central-america,south-america,asia-east,"
            "asia-south,asia-southeast,asia-pacific,oceania,middle-east,africa,"
            "china,government,global"
        ),
    )
    parser.add_argument(
        "--region-scope",
        default="all",
        help=(
            "Геофильтр для update: all|europe|north-america|central-america|south-america|"
            "asia-east|asia-south|asia-southeast|asia-pacific|oceania|middle-east|"
            "africa|china|government|global (legacy, используйте --region-scopes)"
        ),
    )
    parser.add_argument(
        "--include-non-geo-fallback",
        action="store_true",
        help="Включать провайдеров без geo-меток целиком при использовании геофильтра",
    )
    parser.add_argument(
        "--strict-geo-filter",
        action="store_true",
        help="Строгий geo-фильтр: исключать спорные/пограничные префиксы",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Печать JSON с форматированием",
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    regions = _parse_regions(args.regions)
    region_scopes = _parse_region_scopes(args.region_scopes or args.region_scope)

    if args.action == "list":
        result = {"success": True, "regions": get_available_regions()}
    elif args.action == "rollback":
        result = rollback_to_baseline(regions)
    elif args.action == "estimate":
        result = estimate_cidr_matches(
            regions,
            region_scopes=region_scopes,
            include_non_geo_fallback=bool(args.include_non_geo_fallback),
            strict_geo_filter=bool(args.strict_geo_filter),
        )
    else:
        result = update_cidr_files(
            regions,
            region_scopes=region_scopes,
            include_non_geo_fallback=bool(args.include_non_geo_fallback),
            strict_geo_filter=bool(args.strict_geo_filter),
        )

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
