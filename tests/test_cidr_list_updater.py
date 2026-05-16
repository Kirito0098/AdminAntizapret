import ipaddress
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core.services import cidr_list_updater


class CidrListUpdaterTests(unittest.TestCase):
    def test_extract_cidrs_from_bgp_tools_raw_allocations_section(self):
        payload = """
        # de.hetzner Announced Allocations
        | Has a valid RPKI cert | 203.0.113.0/24 | Example |

        # de.hetzner Raw Allocations
        [ipv4] -- 5.9.0.0/16
        [ipv4] -- [54.36.0.0/15 54.38.0.0/16]
        ## Additional Links
        """

        extracted = cidr_list_updater._extract_cidrs(
            payload,
            "cidr_text_scan",
            region_scopes=["all"],
        )

        self.assertEqual(extracted, ["5.9.0.0/16", "54.36.0.0/15", "54.38.0.0/16"])

    def test_extract_cidrs_from_ripe_json(self):
        payload = {
            "status": "ok",
            "data": {
                "prefixes": [
                    {"prefix": "1.1.1.0/24"},
                    {"prefix": "2001:db8::/32"},
                    {"prefix": "2.2.2.0/24"},
                ]
            },
        }

        extracted = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "ripe_json",
        )

        self.assertEqual(extracted, ["1.1.1.0/24", "2.2.2.0/24"])

    def test_extract_cidrs_from_ripe_geo_json(self):
        payload = {
            "status": "ok",
            "data": {
                "located_resources": [
                    {
                        "resource": "5.9.0.0/16",
                        "locations": [
                            {
                                "country": "DE",
                                "resources": ["5.9.0.0/24", "5.9.1.0/24"],
                            },
                            {
                                "country": "US",
                                "resources": ["5.9.2.0/24"],
                            },
                        ],
                    }
                ]
            },
        }

        europe_only = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "ripe_geo_json",
            region_scopes=["europe"],
        )
        self.assertEqual(europe_only, ["5.9.0.0/24", "5.9.1.0/24"])

        north_america_only = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "ripe_geo_json",
            region_scopes=["north-america"],
        )
        self.assertEqual(north_america_only, ["5.9.2.0/24"])

    def test_extract_cidrs_from_ripe_geo_json_strict_mode_excludes_ambiguous(self):
        payload = {
            "status": "ok",
            "data": {
                "located_resources": [
                    {
                        "locations": [
                            {
                                "country": "DE",
                                "resources": ["7.7.7.0/24", "8.8.8.0/24"],
                            },
                            {
                                "country": "US",
                                "resources": ["8.8.8.0/24"],
                            },
                        ],
                    }
                ]
            },
        }

        non_strict = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "ripe_geo_json",
            region_scopes=["europe"],
            strict_geo_filter=False,
        )
        self.assertEqual(non_strict, ["7.7.7.0/24", "8.8.8.0/24"])

        strict = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "ripe_geo_json",
            region_scopes=["europe"],
            strict_geo_filter=True,
        )
        self.assertEqual(strict, ["7.7.7.0/24"])

    def test_extract_cidrs_from_google_json_strict_mode_excludes_ambiguous_scope(self):
        payload = {
            "syncToken": "t",
            "creationTime": "now",
            "prefixes": [
                {"scope": "asia", "ipv4Prefix": "10.0.0.0/24"},
                {"scope": "asia-east1", "ipv4Prefix": "10.0.1.0/24"},
                {"scope": "global", "ipv4Prefix": "10.0.2.0/24"},
            ],
        }

        non_strict = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "google_json",
            region_scopes=["asia-pacific"],
            strict_geo_filter=False,
        )
        self.assertEqual(non_strict, ["10.0.0.0/24", "10.0.1.0/24"])

        strict = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "google_json",
            region_scopes=["asia-pacific"],
            strict_geo_filter=True,
        )
        self.assertEqual(strict, ["10.0.1.0/24"])

        strict_all = cidr_list_updater._extract_cidrs(
            json.dumps(payload),
            "google_json",
            region_scopes=["all"],
            strict_geo_filter=True,
        )
        self.assertEqual(strict_all, ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24"])

    def test_estimate_cidr_matches(self):
        payload = {
            "status": "ok",
            "data": {
                "located_resources": [
                    {
                        "locations": [
                            {
                                "country": "DE",
                                "resources": ["10.10.0.0/24", "10.10.1.0/24"],
                            }
                        ],
                    }
                ]
            },
        }

        with patch.object(
            cidr_list_updater,
            "PROVIDER_SOURCES",
            {
                "amazon-ips.txt": [
                    {
                        "name": "ripe-test",
                        "url": "https://example.test/ripe",
                        "format": "ripe_geo_json",
                    }
                ]
            },
        ), patch.object(cidr_list_updater, "_download_text", return_value=json.dumps(payload)):
            result = cidr_list_updater.estimate_cidr_matches(
                ["amazon-ips.txt"],
                region_scopes=["europe"],
                strict_geo_filter=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["estimated"]), 1)
        self.assertEqual(result["estimated"][0]["file"], "amazon-ips.txt")
        self.assertEqual(result["estimated"][0]["cidr_count"], 2)
        self.assertEqual(result["estimated"][0]["raw_cidr_count"], 2)
        self.assertEqual(result["estimated"][0]["cidr_count_after_limit"], 2)

    def test_prune_runtime_backups_removes_directories_older_than_12_hours(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_dir = os.path.join(tmp_dir, "old-backup")
            new_dir = os.path.join(tmp_dir, "new-backup")
            os.makedirs(old_dir, exist_ok=True)
            os.makedirs(new_dir, exist_ok=True)

            now_ts = 1_700_000_000
            old_ts = now_ts - (13 * 60 * 60)
            new_ts = now_ts - (2 * 60 * 60)
            os.utime(old_dir, (old_ts, old_ts))
            os.utime(new_dir, (new_ts, new_ts))

            with patch.object(cidr_list_updater, "RUNTIME_BACKUP_ROOT", tmp_dir):
                removed = cidr_list_updater._prune_runtime_backups(now_ts=now_ts)

            self.assertIn("old-backup", removed)
            self.assertFalse(os.path.exists(old_dir))
            self.assertTrue(os.path.exists(new_dir))

    def test_update_selected_and_rollback_to_baseline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            list_dir = os.path.join(tmp_dir, "list")
            baseline_dir = os.path.join(list_dir, "_baseline")
            backup_dir = os.path.join(tmp_dir, "runtime_backups")
            include_hosts_path = os.path.join(tmp_dir, "include-hosts.txt")
            include_ips_path = os.path.join(tmp_dir, "include-ips.txt")
            os.makedirs(list_dir, exist_ok=True)

            target_file = "amazon-ips.txt"
            target_path = os.path.join(list_dir, target_file)
            with open(target_path, "w", encoding="utf-8") as handle:
                handle.write("# baseline\n10.0.0.0/24\n")

            with patch.object(cidr_list_updater, "LIST_DIR", list_dir), patch.object(
                cidr_list_updater, "BASELINE_DIR", baseline_dir
            ), patch.object(cidr_list_updater, "RUNTIME_BACKUP_ROOT", backup_dir), patch.object(
                cidr_list_updater, "GAME_INCLUDE_HOSTS_FILE", include_hosts_path
            ), patch.object(
                cidr_list_updater, "GAME_INCLUDE_IPS_FILE", include_ips_path
            ), patch.object(
                cidr_list_updater,
                "PROVIDER_SOURCES",
                {
                    target_file: [
                        {
                            "name": "mock-source",
                            "url": "https://example.test/amazon.txt",
                            "format": "cidr_text",
                        }
                    ]
                },
            ), patch.object(
                cidr_list_updater,
                "_download_text",
                return_value="1.1.1.1/32\n2.2.2.0/24\n",
            ):
                update_result = cidr_list_updater.update_cidr_files([target_file])
                self.assertTrue(update_result["success"])
                self.assertEqual(len(update_result["updated"]), 1)

                with open(target_path, "r", encoding="utf-8") as handle:
                    updated_text = handle.read()

                self.assertIn("1.1.1.1/32", updated_text)
                self.assertIn("2.2.2.0/24", updated_text)

                rollback_result = cidr_list_updater.rollback_to_baseline([target_file])
                self.assertTrue(rollback_result["success"])
                self.assertEqual(rollback_result["restored"], [target_file])

                with open(target_path, "r", encoding="utf-8") as handle:
                    rolled_back_text = handle.read()

                self.assertIn("10.0.0.0/24", rolled_back_text)
                self.assertNotIn("2.2.2.0/24", rolled_back_text)

    def test_non_geo_provider_can_be_included_with_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            list_dir = os.path.join(tmp_dir, "list")
            baseline_dir = os.path.join(list_dir, "_baseline")
            backup_dir = os.path.join(tmp_dir, "runtime_backups")
            include_hosts_path = os.path.join(tmp_dir, "include-hosts.txt")
            include_ips_path = os.path.join(tmp_dir, "include-ips.txt")
            os.makedirs(list_dir, exist_ok=True)

            target_file = "akamai-ips.txt"
            target_path = os.path.join(list_dir, target_file)
            with open(target_path, "w", encoding="utf-8") as handle:
                handle.write("# baseline\n10.0.0.0/24\n")

            with patch.object(cidr_list_updater, "LIST_DIR", list_dir), patch.object(
                cidr_list_updater, "BASELINE_DIR", baseline_dir
            ), patch.object(cidr_list_updater, "RUNTIME_BACKUP_ROOT", backup_dir), patch.object(
                cidr_list_updater, "GAME_INCLUDE_HOSTS_FILE", include_hosts_path
            ), patch.object(
                cidr_list_updater, "GAME_INCLUDE_IPS_FILE", include_ips_path
            ), patch.object(
                cidr_list_updater,
                "PROVIDER_SOURCES",
                {
                    target_file: [
                        {
                            "name": "plain-list",
                            "url": "https://example.test/plain.txt",
                            "format": "cidr_text",
                        }
                    ]
                },
            ), patch.object(
                cidr_list_updater,
                "_download_text",
                return_value="1.1.1.0/24\n2.2.2.0/24\n",
            ):
                result_skip = cidr_list_updater.update_cidr_files(
                    [target_file],
                    region_scopes=["europe", "asia-pacific"],
                    include_non_geo_fallback=False,
                )
                self.assertFalse(result_skip["updated"])
                self.assertEqual(result_skip["skipped"][0]["reason"], "geo_scope_not_supported")

                result_fallback = cidr_list_updater.update_cidr_files(
                    [target_file],
                    region_scopes=["europe", "asia-pacific"],
                    include_non_geo_fallback=True,
                )
                self.assertTrue(result_fallback["updated"])

                with open(target_path, "r", encoding="utf-8") as handle:
                    updated_text = handle.read()

                self.assertIn("1.1.1.0/24", updated_text)
                self.assertIn("2.2.2.0/24", updated_text)

    def test_collect_cidrs_skips_geo_source_when_all_scope_has_non_geo_results(self):
        sources = [
            {
                "name": "bgp-tools-source",
                "url": "https://example.test/non-geo",
                "format": "cidr_text_scan",
            },
            {
                "name": "ripe-geo-source",
                "url": "https://example.test/geo",
                "format": "ripe_geo_json",
            },
        ]

        non_geo_payload = """
        # Raw Allocations
        [ipv4] -- 5.9.0.0/16
        ## Additional Links
        """

        with patch.object(cidr_list_updater, "_download_text", side_effect=[non_geo_payload]) as mocked_download:
            cidrs, source_name, error = cidr_list_updater._collect_cidrs_from_sources(
                sources,
                ["all"],
            )

        self.assertEqual(cidrs, ["5.9.0.0/16"])
        self.assertEqual(source_name, "bgp-tools-source")
        self.assertIsNone(error)
        self.assertEqual(mocked_download.call_count, 1)

    def test_analyze_dpi_log_builds_priority_files(self):
        dpi_log = "\n".join(
            [
                "[03:38:47.119] DPI checking(#US.CDN77-01)/INFO: tcp 16-20: detected❗️, method: 1",
                "[03:38:47.165] DPI checking(#DE.HE-01)/INFO: tcp 16-20: possible detected ⚠️, reqtime: 180.8 ms",
                "[03:38:47.257] DPI checking(#SE.AKM-01)/INFO: tcp 16-20: unlikely ⚠️, reqtime: 220.0 ms",
                "[03:38:47.631] DPI checking(#US.GH-HPRN)/INFO: tcp 16-20: not detected ✅, reqtime: 100.0 ms",
            ]
        )

        result = cidr_list_updater.analyze_dpi_log(dpi_log)

        self.assertTrue(result["success"])
        self.assertIn("cdn77-ips.txt", result["priority_files"])
        self.assertIn("hetzner-ips.txt", result["priority_files"])
        self.assertIn("akamai-ips.txt", result["priority_files"])
        self.assertIn("cdn77-ips.txt", result["critical_files"])
        self.assertIn("hetzner-ips.txt", result["critical_files"])
        self.assertNotIn("akamai-ips.txt", result["critical_files"])
        self.assertIn("cdn77-ips.txt", result["detected_files"])
        self.assertNotIn("hetzner-ips.txt", result["detected_files"])

    def test_analyze_dpi_log_supports_dpi_detector_table_format(self):
        dpi_log = "\n".join(
            [
                "│ ID     │ ASN      │ Провайдер       │ Alive │  Статус  │ Детали                   │",
                "│ OR-01  │ AS31898  │ Oracle Cloud    │  Да   │ DETECTED │ Read Timeout at 20KB     │",
                "│ HE-01  │ AS24940  │ Hetzner         │  Нет  │ REFUSED  │ TCP соединение отклонено │",
                "│ HE-02  │ AS24940  │ Hetzner         │  Да   │ DETECTED │ Read Timeout at 20KB     │",
                "│ GC-01  │ AS396982 │ Google Cloud    │  Да   │    OK    │                          │",
            ]
        )

        result = cidr_list_updater.analyze_dpi_log(dpi_log)

        self.assertTrue(result["success"])
        self.assertIn("oracle-ips.txt", result["detected_files"])
        self.assertIn("hetzner-ips.txt", result["detected_files"])
        self.assertIn("google-ips.txt", result["all_seen_files"])
        self.assertNotIn("google-ips.txt", result["priority_files"])

    def test_apply_total_route_limit_with_dpi_priority_reserve(self):
        entries = [
            {
                "file": "google-ips.txt",
                "cidrs": [f"10.10.{index}.0/24" for index in range(30)],
            },
            {
                "file": "ovh-ips.txt",
                "cidrs": [f"10.20.{index}.0/24" for index in range(30)],
            },
        ]

        adjusted, meta = cidr_list_updater._apply_total_route_limit(
            entries,
            10,
            dpi_priority_files=["google-ips.txt"],
            dpi_priority_min_budget=6,
        )

        self.assertIsNotNone(meta)
        self.assertIn("dpi_priority", meta)
        self.assertLessEqual(sum(len(item["cidrs"]) for item in adjusted), 10)
        google_entry = next(item for item in adjusted if item["file"] == "google-ips.txt")
        self.assertGreaterEqual(len(google_entry["cidrs"]), 6)

    def test_apply_total_route_limit_keeps_mandatory_detected_file(self):
        entries = [
            {
                "file": "google-ips.txt",
                "cidrs": [f"10.10.{index}.0/24" for index in range(40)],
            },
            {
                "file": "ovh-ips.txt",
                "cidrs": [f"10.20.{index}.0/24" for index in range(40)],
            },
            {
                "file": "cdn77-ips.txt",
                "cidrs": ["10.30.0.0/24", "10.30.1.0/24"],
            },
        ]

        adjusted, meta = cidr_list_updater._apply_total_route_limit(
            entries,
            2,
            dpi_mandatory_files=["cdn77-ips.txt"],
        )

        self.assertIsNotNone(meta)
        self.assertIn("dpi_mandatory", meta)
        self.assertFalse(meta["dpi_mandatory"]["dropped_mandatory_files"])
        kept_cdn77 = next(item for item in adjusted if item["file"] == "cdn77-ips.txt")
        self.assertGreaterEqual(len(kept_cdn77["cidrs"]), 1)

    def test_estimate_applies_route_optimization_for_large_geo_result(self):
        target_file = "ovh-ips.txt"
        sources = [
            {
                "name": "bgp-tools-fr-ovh",
                "url": "https://example.test/non-geo",
                "format": "cidr_text_scan",
            },
            {
                "name": "ripe-as16276-geo",
                "url": "https://example.test/geo",
                "format": "ripe_geo_json",
            },
        ]

        large_geo = [f"10.0.{idx // 256}.{idx % 256}/32" for idx in range(5000)]
        compact_non_geo = ["57.128.0.0/14", "54.36.0.0/15", "54.38.0.0/16"]

        with patch.object(
            cidr_list_updater,
            "PROVIDER_SOURCES",
            {target_file: sources},
        ), patch.object(
            cidr_list_updater,
            "_collect_cidrs_from_sources",
            side_effect=[
                (large_geo, "ripe-as16276-geo", None),
                (compact_non_geo, "bgp-tools-fr-ovh", None),
            ],
        ) as mocked_collect:
            result = cidr_list_updater.estimate_cidr_matches(
                [target_file],
                region_scopes=["europe"],
                include_non_geo_fallback=False,
                strict_geo_filter=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["estimated"]), 1)
        estimated_item = result["estimated"][0]
        self.assertEqual(estimated_item["file"], target_file)
        self.assertEqual(estimated_item["cidr_count"], len(compact_non_geo))
        self.assertIn("route_optimization", estimated_item)
        self.assertEqual(
            estimated_item["route_optimization"]["strategy"],
            "route_limit_non_geo_fallback",
        )
        self.assertEqual(mocked_collect.call_count, 2)

    def test_estimate_excludes_ru_cidrs_for_all_scope(self):
        target_file = "akamai-ips.txt"
        with patch.object(
            cidr_list_updater,
            "PROVIDER_SOURCES",
            {
                target_file: [
                    {
                        "name": "plain-list",
                        "url": "https://example.test/plain.txt",
                        "format": "cidr_text",
                    }
                ]
            },
        ), patch.object(
            cidr_list_updater,
            "_download_text",
            return_value="5.255.0.0/16\n8.8.8.0/24\n",
        ), patch.object(
            cidr_list_updater,
            "_get_ru_cidr_index",
            return_value=(cidr_list_updater._build_antifilter_overlap_index(["5.0.0.0/8"]), None),
        ):
            result = cidr_list_updater.estimate_cidr_matches(
                [target_file],
                region_scopes=["all"],
                exclude_ru_cidrs=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["estimated"]), 1)

        estimated_item = result["estimated"][0]
        self.assertEqual(estimated_item["file"], target_file)
        self.assertEqual(estimated_item["cidr_count"], 1)
        self.assertIn("country_exclusion", estimated_item)
        self.assertEqual(
            estimated_item["country_exclusion"]["strategy"],
            "exclude_ru_country",
        )
        self.assertEqual(
            estimated_item["country_exclusion"]["removed_cidr_count"],
            1,
        )

    def test_update_applies_global_total_route_limit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            list_dir = os.path.join(tmp_dir, "list")
            baseline_dir = os.path.join(list_dir, "_baseline")
            backup_dir = os.path.join(tmp_dir, "runtime_backups")
            include_hosts_path = os.path.join(tmp_dir, "include-hosts.txt")
            include_ips_path = os.path.join(tmp_dir, "include-ips.txt")
            os.makedirs(list_dir, exist_ok=True)

            selected_files = ["amazon-ips.txt", "google-ips.txt"]
            for file_name in selected_files:
                with open(os.path.join(list_dir, file_name), "w", encoding="utf-8") as handle:
                    handle.write("# baseline\n10.0.0.0/24\n")

            payload_a = "\n".join([f"10.10.{idx}.0/24" for idx in range(40)]) + "\n"
            payload_b = "\n".join([f"10.20.{idx}.0/24" for idx in range(40)]) + "\n"

            with patch.object(cidr_list_updater, "LIST_DIR", list_dir), patch.object(
                cidr_list_updater, "BASELINE_DIR", baseline_dir
            ), patch.object(cidr_list_updater, "RUNTIME_BACKUP_ROOT", backup_dir), patch.object(
                cidr_list_updater, "GAME_INCLUDE_HOSTS_FILE", include_hosts_path
            ), patch.object(
                cidr_list_updater, "GAME_INCLUDE_IPS_FILE", include_ips_path
            ), patch.object(
                cidr_list_updater,
                "PROVIDER_SOURCES",
                {
                    "amazon-ips.txt": [
                        {
                            "name": "amazon-source",
                            "url": "https://example.test/amazon",
                            "format": "cidr_text",
                        }
                    ],
                    "google-ips.txt": [
                        {
                            "name": "google-source",
                            "url": "https://example.test/google",
                            "format": "cidr_text",
                        }
                    ],
                },
            ), patch.object(
                cidr_list_updater,
                "_get_openvpn_route_total_cidr_limit",
                return_value=12,
            ), patch.object(
                cidr_list_updater,
                "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT",
                12,
            ), patch.object(
                cidr_list_updater,
                "OPENVPN_ROUTE_CIDR_LIMIT",
                10_000,
            ), patch.object(
                cidr_list_updater,
                "_download_text",
                side_effect=[payload_a, payload_b],
            ):
                result = cidr_list_updater.update_cidr_files(
                    selected_files=selected_files,
                    region_scopes=["all"],
                    include_non_geo_fallback=False,
                    strict_geo_filter=False,
                )

            self.assertTrue(result["success"])
            self.assertEqual(len(result["updated"]), 2)
            self.assertIn("global_route_optimization", result)
            self.assertEqual(result["global_route_optimization"]["limit"], 12)

            total_cidrs = sum(item["cidr_count"] for item in result["updated"])
            self.assertLessEqual(total_cidrs, 12)

    def test_apply_total_route_limit_with_budget_smaller_than_file_count(self):
        entries = [
            {"file": "amazon-ips.txt", "cidrs": ["10.10.0.0/24"]},
            {"file": "google-ips.txt", "cidrs": ["10.20.0.0/24"]},
        ]

        adjusted, meta = cidr_list_updater._apply_total_route_limit(entries, 1)

        self.assertIsNotNone(meta)
        self.assertEqual(meta["limit"], 1)
        self.assertLessEqual(sum(len(item["cidrs"]) for item in adjusted), 1)

    def test_compress_cidrs_to_limit_never_returns_default_route(self):
        cidrs = [
            "10.0.0.0/24",
            "11.0.0.0/24",
            "12.0.0.0/24",
            "13.0.0.0/24",
        ]

        with patch.object(cidr_list_updater, "OPENVPN_ROUTE_MIN_PREFIXLEN", 8):
            compressed, meta = cidr_list_updater._compress_cidrs_to_limit(cidrs, 1)

        self.assertIsNotNone(meta)
        self.assertEqual(len(compressed), 1)
        self.assertNotIn("0.0.0.0/0", compressed)

    def test_compress_cidrs_to_limit_does_not_overcompress_far_below_budget(self):
        cidrs = [
            f"10.{index // 256}.{index % 256}.0/24"
            for index in range(1024)
        ]

        compressed, meta = cidr_list_updater._compress_cidrs_to_limit(cidrs, 900)

        self.assertIsNotNone(meta)
        self.assertEqual(len(compressed), 900)
        self.assertEqual(meta["target_limit"], 900)

    def test_total_limit_reads_from_env_file_runtime(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = os.path.join(tmp_dir, ".env")
            with open(env_file, "w", encoding="utf-8") as handle:
                handle.write("OPENVPN_ROUTE_TOTAL_CIDR_LIMIT=777\n")

            with patch.object(cidr_list_updater, "ENV_FILE_PATH", env_file):
                self.assertEqual(cidr_list_updater._get_openvpn_route_total_cidr_limit(), 777)

    def test_sync_games_include_hosts_enable_and_disable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            include_hosts_path = os.path.join(tmp_dir, "include-hosts.txt")
            with open(include_hosts_path, "w", encoding="utf-8") as handle:
                handle.write("custom.example\n")

            with patch.object(cidr_list_updater, "GAME_INCLUDE_HOSTS_FILE", include_hosts_path):
                enabled = cidr_list_updater._sync_games_include_hosts(["lol", "dota2", "csgo", "faceit"])

                self.assertTrue(enabled["success"])
                self.assertTrue(enabled["changed"])

                with open(include_hosts_path, "r", encoding="utf-8") as handle:
                    enabled_content = handle.read()

                self.assertIn(cidr_list_updater.GAME_FILTER_BLOCK_START, enabled_content)
                self.assertIn("riotgames.com", enabled_content)
                self.assertIn("dota2.com", enabled_content)
                self.assertIn("counter-strike.net", enabled_content)
                self.assertIn("faceit.com", enabled_content)

                disabled = cidr_list_updater._sync_games_include_hosts([])
                self.assertTrue(disabled["success"])

                with open(include_hosts_path, "r", encoding="utf-8") as handle:
                    disabled_content = handle.read()

                self.assertIn("custom.example", disabled_content)
                self.assertNotIn(cidr_list_updater.GAME_FILTER_BLOCK_START, disabled_content)
                self.assertNotIn("faceit.com", disabled_content)

    def test_sync_game_hosts_filter_runs_without_cidr_update(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            include_hosts_path = os.path.join(tmp_dir, "include-hosts.txt")
            include_ips_path = os.path.join(tmp_dir, "include-ips.txt")

            with patch.object(cidr_list_updater, "GAME_INCLUDE_HOSTS_FILE", include_hosts_path), patch.object(
                cidr_list_updater, "GAME_INCLUDE_IPS_FILE", include_ips_path
            ), patch.object(
                cidr_list_updater,
                "_resolve_game_domains_ipv4_cidrs",
                return_value=(["203.0.113.10/32", "203.0.113.11/32"], []),
            ):
                result = cidr_list_updater.sync_game_hosts_filter(include_game_keys=["lol", "faceit"])

            self.assertTrue(result["success"])
            self.assertIn("game_hosts_filter", result)
            self.assertIn("game_ips_filter", result)
            self.assertTrue(result["game_hosts_filter"]["enabled"])
            self.assertEqual(result["game_hosts_filter"]["selected_game_count"], 2)
            self.assertEqual(result["game_ips_filter"]["cidr_count"], 2)

            with open(include_hosts_path, "r", encoding="utf-8") as handle:
                content = handle.read()

            self.assertIn(cidr_list_updater.GAME_FILTER_BLOCK_START, content)
            self.assertIn("riotgames.com", content)
            self.assertIn("faceit.com", content)

            with open(include_ips_path, "r", encoding="utf-8") as handle:
                ips_content = handle.read()

            self.assertIn(cidr_list_updater.GAME_FILTER_IP_BLOCK_START, ips_content)
            self.assertIn("203.0.113.10/32", ips_content)
            self.assertIn("203.0.113.11/32", ips_content)

if __name__ == "__main__":
    unittest.main()
