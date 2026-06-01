import unittest
from unittest.mock import MagicMock, patch

from core.services.cidr_db_updater import (
    CidrDbUpdaterService,
    _read_positive_int_env,
    _extract_asns_from_text,
    _extract_asns_from_url,
    _extract_asns_from_sources,
)
from core.services.cidr.provider_sources import PROVIDER_SOURCES


class CidrDbUpdaterServiceHelperTests(unittest.TestCase):
    def test_helper_parsing_and_workers(self):
        self.assertEqual(CidrDbUpdaterService._resolve_asn_fetch_workers(0, 8), 0)
        self.assertEqual(CidrDbUpdaterService._resolve_asn_fetch_workers(100, 128), 32)
        with patch.dict("os.environ", {"CIDR_DB_ASN_FETCH_WORKERS": "6"}, clear=True):
            self.assertEqual(CidrDbUpdaterService._resolve_asn_fetch_workers(20), 6)

        with patch.dict("os.environ", {"CIDR_DB_TEST_INT": "abc"}, clear=True):
            self.assertEqual(_read_positive_int_env("CIDR_DB_TEST_INT", 55), 55)
        with patch.dict("os.environ", {"CIDR_DB_TEST_INT": "128"}, clear=True):
            self.assertEqual(_read_positive_int_env("CIDR_DB_TEST_INT", 55), 128)

        self.assertIn(13335, _extract_asns_from_url(
            "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS13335"
        ))
        self.assertEqual(
            _extract_asns_from_text("AS13335, as15169"),
            {13335, 15169},
        )

    def test_merge_cidr_items_prefers_richer_geo_metadata(self):
        merged = CidrDbUpdaterService._merge_cidr_items(
            [
                {"cidr": "1.1.1.0/24", "region": None, "countries": None},
                {"cidr": "1.1.1.0/24", "region": "europe", "countries": ["DE"]},
            ]
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["region"], "europe")
        self.assertEqual(merged[0]["countries"], ["DE"])

    def test_compute_provider_anomaly_marks_critical_on_large_drop(self):
        level, reason = CidrDbUpdaterService._compute_provider_anomaly(
            expected_asn_min=2,
            active_asn_count=2,
            current_cidr_count=120,
            previous_cidr_count=300,
            asn_discovery_errors=[],
            asn_fetch_errors=[],
        )
        self.assertEqual(level, "critical")
        self.assertIn("CIDR упали", reason)

    def test_compute_provider_anomaly_softens_asn_errors_for_healthy_pool_after_clear(self):
        level, reason = CidrDbUpdaterService._compute_provider_anomaly(
            expected_asn_min=2,
            active_asn_count=2,
            current_cidr_count=5000,
            previous_cidr_count=0,
            asn_discovery_errors=["bgp-tools: timeout"],
            asn_fetch_errors=["AS20940: timeout"],
        )
        self.assertEqual(level, "info")
        self.assertIn("Ошибки ASN-источников", reason)

    def test_build_degradation_alerts_skips_global_drop_after_cleared_baseline(self):
        svc = CidrDbUpdaterService(db=MagicMock())
        last_log = MagicMock(id=2, total_cidrs=150865)
        prev_log = MagicMock(id=1, total_cidrs=404540, status="cleared")
        meta = MagicMock(anomaly_level="none", anomaly_reason=None, provider_key="amazon-ips.txt")

        models = MagicMock()
        query = MagicMock()
        query.filter.return_value.order_by.return_value.first.return_value = prev_log
        models.CidrDbRefreshLog.query = query

        with patch("core.services.cidr.db_service._get_models", return_value=models):
            alerts = svc._build_degradation_alerts(last_log, [meta])

        self.assertEqual(alerts, [])

    def test_build_degradation_alerts_keeps_global_drop_without_cleared_baseline(self):
        svc = CidrDbUpdaterService(db=MagicMock())
        last_log = MagicMock(id=2, total_cidrs=150865)
        prev_log = MagicMock(id=1, total_cidrs=404540, status="ok")
        meta = MagicMock(anomaly_level="none", anomaly_reason=None, provider_key="amazon-ips.txt")

        models = MagicMock()
        query = MagicMock()
        query.filter.return_value.order_by.return_value.first.return_value = prev_log
        models.CidrDbRefreshLog.query = query

        with patch("core.services.cidr.db_service._get_models", return_value=models):
            alerts = svc._build_degradation_alerts(last_log, [meta])

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["scope"], "global")
        self.assertIn("150865", alerts[0]["message"])

    def test_download_asn_cidrs_with_meta_retries_after_transient_failure(self):
        svc = CidrDbUpdaterService(db=None)
        success = ([{"cidr": "203.0.113.0/24"}], "ripe-as9059-bgpstate")

        with patch.object(
            svc,
            "_download_cidrs_with_meta",
            side_effect=[RuntimeError("timeout"), RuntimeError("timeout"), success],
        ) as mocked_fetch, patch("core.services.cidr.db_service.time.sleep") as mocked_sleep:
            items, source_used, error = svc._download_asn_cidrs_with_meta(9059)

        self.assertIsNone(error)
        self.assertEqual(source_used, "ripe-as9059-bgpstate")
        self.assertEqual([item["cidr"] for item in items], ["203.0.113.0/24"])
        self.assertEqual(mocked_fetch.call_count, 3)
        self.assertEqual(mocked_sleep.call_count, 2)

    def test_should_preserve_previous_pool_on_hard_drop_without_errors(self):
        self.assertFalse(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=38313,
                candidate_cidr_count=7631,
                asn_errors=[],
            )
        )

    def test_should_preserve_previous_pool_when_candidate_empty(self):
        self.assertTrue(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=1000,
                candidate_cidr_count=0,
                asn_errors=[],
            )
        )

    def test_should_preserve_previous_pool_accepts_large_healthy_candidate(self):
        self.assertFalse(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=286127,
                candidate_cidr_count=32452,
                asn_errors=[],
            )
        )

    def test_should_preserve_previous_pool_when_errors_and_large_drop(self):
        self.assertTrue(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=286127,
                candidate_cidr_count=32452,
                asn_errors=["AS20940: timeout"],
            )
        )

    def test_should_preserve_previous_pool_when_candidate_too_small(self):
        self.assertTrue(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=1000,
                candidate_cidr_count=70,
                asn_errors=[],
            )
        )

    def test_should_not_preserve_previous_pool_for_stable_small_provider_without_errors(self):
        self.assertFalse(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=15,
                candidate_cidr_count=15,
                asn_errors=[],
            )
        )

    def test_discover_provider_asns_combines_seed_source_and_scan(self):
        svc = CidrDbUpdaterService(db=None)
        sources = [
            {
                "name": "bgp-tools-as396982",
                "url": "https://example.test/provider?resource=AS15169",
                "format": "cidr_text_scan",
            }
        ]

        with patch("core.services.cidr_db_updater._download_text", return_value="owner includes AS3356 and AS15169"):
            discovered, source_tags, errors = svc._discover_provider_asns(
                "google-ips.txt",
                sources,
                seed_asns={13335},
            )

        self.assertIn(13335, discovered)
        self.assertIn(15169, discovered)
        self.assertIn(3356, discovered)
        self.assertIn("source-meta", source_tags)
        self.assertFalse(errors)

    def test_discover_provider_asns_skips_scan_when_limit_zero(self):
        svc = CidrDbUpdaterService(db=None)
        sources = [
            {
                "name": "bgp-tools-scan-source",
                "url": "https://example.test/provider",
                "format": "cidr_text_scan",
            }
        ]

        with patch("core.services.cidr_db_updater._download_text") as mocked_download:
            discovered, source_tags, errors = svc._discover_provider_asns(
                "digitalocean-ips.txt",
                sources,
                seed_asns={14061, 46652},
                scan_extra_limit=0,
            )

        self.assertEqual(discovered, [14061, 46652])
        self.assertEqual(source_tags, set())
        self.assertFalse(errors)
        mocked_download.assert_not_called()

    def test_download_asn_cidrs_with_meta_uses_bgp_state_fallback(self):
        svc = CidrDbUpdaterService(db=None)

        empty_announced = '{"data":{"prefixes":[]}}'
        empty_geo = '{"data":{"located_resources":[]}}'
        bgp_state_payload = '{"data":{"bgp_state":[{"target_prefix":"203.0.113.0/24"}]}}'

        with patch(
            "core.services.cidr_db_updater._download_text",
            side_effect=[empty_announced, empty_geo, bgp_state_payload],
        ):
            items, source_used, error = svc._download_asn_cidrs_with_meta(9059)

        self.assertIsNone(error)
        self.assertTrue(source_used)
        self.assertIn("ripe-as9059-bgpstate", source_used)
        self.assertEqual([item["cidr"] for item in items], ["203.0.113.0/24"])

    def test_download_cidrs_with_meta_parallel_keeps_source_order(self):
        svc = CidrDbUpdaterService(db=None)
        sources = [
            {
                "name": "source-a",
                "url": "https://example.test/a",
                "format": "cidr_text",
            },
            {
                "name": "source-b",
                "url": "https://example.test/b",
                "format": "cidr_text",
            },
        ]

        def fake_download(url, timeout=45):
            if url.endswith("/a"):
                return "1.1.1.0/24\n"
            if url.endswith("/b"):
                return "2.2.2.0/24\n"
            raise RuntimeError("unexpected url")

        with (
            patch.object(svc, "_current_source_fetch_workers", return_value=4),
            patch("core.services.cidr_db_updater._download_text", side_effect=fake_download),
        ):
            items, source_used = svc._download_cidrs_with_meta(sources)

        self.assertEqual(source_used, "source-a, source-b")
        self.assertEqual(
            {item["cidr"] for item in items},
            {"1.1.1.0/24", "2.2.2.0/24"},
        )

    @patch("core.services.cidr.db_service._get_models")
    def test_refresh_cloudflare_official_only_keeps_status_ok_without_asn(self, mocked_get_models):
        models = MagicMock()
        models.CidrDbRefreshLog.side_effect = lambda **kwargs: MagicMock(**kwargs)
        models.ProviderCidr.query.filter_by.return_value.count.return_value = 0
        models.ProviderAsn.query.filter_by.return_value.count.return_value = 0
        mocked_get_models.return_value = models

        db = MagicMock()
        svc = CidrDbUpdaterService(db=db)

        cloudflare_sources = PROVIDER_SOURCES["cloudflare-ips.txt"]
        self.assertEqual(len(cloudflare_sources), 1)

        with (
            patch.object(svc, "_discover_provider_asns", return_value=([], set(), [])),
            patch.object(
                svc,
                "_download_cidrs_with_meta",
                return_value=(
                    [{"cidr": "173.245.48.0/20", "region": None, "countries": None}],
                    "cloudflare-ips-v4",
                    [{"name": "cloudflare-ips-v4", "status": "ok", "count": 1, "error": None, "cache_hit": False}],
                ),
            ),
            patch.object(svc, "_upsert_provider_asns", return_value=[]),
            patch.object(svc, "_apply_provider_asn_runtime_meta"),
            patch.object(svc, "_upsert_provider_cidrs", return_value=1),
            patch.object(svc, "_update_provider_meta") as mocked_update_meta,
        ):
            result = svc.refresh_all_providers(
                selected_files=["cloudflare-ips.txt"],
                triggered_by="manual:test",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        provider_result = result["per_provider"]["cloudflare-ips.txt"]
        self.assertEqual(provider_result["status"], "ok")
        self.assertEqual(provider_result["expected_asn_min"], 0)
        self.assertEqual(provider_result["asn_count"], 0)
        self.assertEqual(provider_result["active_asn_count"], 0)
        self.assertEqual(provider_result["asn_errors"], [])
        self.assertEqual(provider_result["source"], "cloudflare-ips-v4")

        update_kwargs = mocked_update_meta.call_args.kwargs
        self.assertEqual(update_kwargs["status"], "ok")
        self.assertEqual(update_kwargs["expected_asn_min"], 0)
        self.assertEqual(update_kwargs["asn_count"], 0)
        self.assertEqual(update_kwargs["active_asn_count"], 0)

    @patch("core.services.cidr.db_service._get_models")
    def test_refresh_akamai_ripe_only_keeps_status_ok_without_discovery_errors(self, mocked_get_models):
        models = MagicMock()
        models.CidrDbRefreshLog.side_effect = lambda **kwargs: MagicMock(**kwargs)
        models.ProviderCidr.query.filter_by.return_value.count.return_value = 0
        models.ProviderAsn.query.filter_by.return_value.count.return_value = 0
        mocked_get_models.return_value = models

        db = MagicMock()
        svc = CidrDbUpdaterService(db=db)

        with (
            patch.object(svc, "_discover_provider_asns", return_value=([20940], {"source-meta"}, [])),
            patch.object(
                svc,
                "_download_asn_cidrs_with_meta",
                return_value=(
                    [{"cidr": "23.0.0.0/24", "region": None, "countries": None}],
                    "ripe-as20940",
                    None,
                ),
            ),
            patch.object(
                svc,
                "_download_cidrs_with_meta",
                return_value=(
                    [{"cidr": "23.1.0.0/24", "region": None, "countries": ["US"]}],
                    "ripe-as20940-geo, ripe-as20940-announced",
                    [{"name": "ripe-as20940-announced", "status": "ok", "count": 1, "error": None, "cache_hit": False}],
                ),
            ),
            patch.object(svc, "_upsert_provider_asns", return_value=[MagicMock(active=True, asn=20940)]),
            patch.object(svc, "_apply_provider_asn_runtime_meta"),
            patch.object(svc, "_upsert_provider_cidrs", return_value=2),
            patch.object(svc, "_write_provider_asn_snapshots"),
            patch.object(svc, "_update_provider_meta") as mocked_update_meta,
        ):
            result = svc.refresh_all_providers(
                selected_files=["akamai-ips.txt"],
                triggered_by="manual:test-akamai",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        provider_result = result["per_provider"]["akamai-ips.txt"]
        self.assertEqual(provider_result["status"], "ok")
        self.assertEqual(provider_result["asn_errors"], [])
        self.assertEqual(provider_result["expected_asn_min"], 1)

        update_kwargs = mocked_update_meta.call_args.kwargs
        self.assertEqual(update_kwargs["status"], "ok")
        self.assertEqual(update_kwargs["expected_asn_min"], 1)

    @patch("core.services.cidr.db_service._get_models")
    def test_refresh_digitalocean_ripe_only_keeps_status_ok(self, mocked_get_models):
        models = MagicMock()
        models.CidrDbRefreshLog.side_effect = lambda **kwargs: MagicMock(**kwargs)
        models.ProviderCidr.query.filter_by.return_value.count.return_value = 0
        models.ProviderAsn.query.filter_by.return_value.count.return_value = 0
        mocked_get_models.return_value = models

        db = MagicMock()
        svc = CidrDbUpdaterService(db=db)

        with (
            patch.object(svc, "_discover_provider_asns", return_value=([14061, 46652], {"source-meta"}, [])),
            patch.object(
                svc,
                "_download_asn_cidrs_with_meta",
                side_effect=[
                    ([{"cidr": "138.197.0.0/24", "region": None, "countries": None}], "ripe-as14061", None),
                    ([{"cidr": "167.99.0.0/24", "region": None, "countries": None}], "ripe-as46652", None),
                ],
            ),
            patch.object(
                svc,
                "_download_cidrs_with_meta",
                return_value=(
                    [{"cidr": "104.248.0.0/24", "region": None, "countries": None}],
                    "ripe-as14061-geo, ripe-as46652-announced",
                    [{"name": "ripe-as14061-geo", "status": "ok", "count": 1, "error": None, "cache_hit": False}],
                ),
            ),
            patch.object(svc, "_upsert_provider_asns", return_value=[MagicMock(active=True), MagicMock(active=True)]),
            patch.object(svc, "_apply_provider_asn_runtime_meta"),
            patch.object(svc, "_upsert_provider_cidrs", return_value=3),
            patch.object(svc, "_write_provider_asn_snapshots"),
            patch.object(svc, "_update_provider_meta") as mocked_update_meta,
        ):
            result = svc.refresh_all_providers(
                selected_files=["digitalocean-ips.txt"],
                triggered_by="manual:test-do",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        provider_result = result["per_provider"]["digitalocean-ips.txt"]
        self.assertEqual(provider_result["status"], "ok")
        self.assertEqual(provider_result["asn_errors"], [])
        self.assertEqual(provider_result["expected_asn_min"], 2)

        update_kwargs = mocked_update_meta.call_args.kwargs
        self.assertEqual(update_kwargs["status"], "ok")
        self.assertEqual(update_kwargs["expected_asn_min"], 2)

    def test_extract_asns_from_sources_reads_hetzner_ripe_urls(self):
        hetzner_sources = PROVIDER_SOURCES["hetzner-ips.txt"]
        asns = _extract_asns_from_sources(hetzner_sources)
        self.assertIn(24940, asns)
        self.assertIn(213230, asns)
        self.assertIn(212317, asns)
        self.assertIn(215859, asns)

    def test_extract_asns_from_sources_akamai_ripe_only(self):
        akamai_sources = PROVIDER_SOURCES["akamai-ips.txt"]
        asns = _extract_asns_from_sources(akamai_sources)
        self.assertEqual(asns, {20940})
        self.assertFalse(any("bgp-tools" in (source.get("name") or "") for source in akamai_sources))

    def test_extract_asns_from_sources_empty_for_json_and_official_cidr_providers(self):
        amazon_asns = _extract_asns_from_sources(PROVIDER_SOURCES["amazon-ips.txt"])
        google_asns = _extract_asns_from_sources(PROVIDER_SOURCES["google-ips.txt"])
        cloudflare_asns = _extract_asns_from_sources(PROVIDER_SOURCES["cloudflare-ips.txt"])
        self.assertEqual(amazon_asns, set())
        self.assertEqual(google_asns, set())
        self.assertEqual(cloudflare_asns, set())

    def test_provider_sources_do_not_use_bgp_tools(self):
        bgp_sources = []
        for provider_key, sources in PROVIDER_SOURCES.items():
            for source in sources:
                name = str(source.get("name") or "")
                url = str(source.get("url") or "")
                fmt = str(source.get("format") or "")
                if "bgp-tools" in name or "bgp.tools" in url or fmt == "cidr_text_scan":
                    bgp_sources.append((provider_key, name, fmt))
        self.assertEqual(bgp_sources, [])

    def test_clear_provider_data_rejects_invalid_targets(self):
        svc = CidrDbUpdaterService(db=MagicMock())
        result = svc.clear_provider_data(selected_files=["unknown-provider.txt"])
        self.assertFalse(result["success"])
        self.assertEqual(result["providers_cleared"], 0)

    @patch("core.services.cidr.db_service._get_models")
    def test_clear_provider_data_deletes_selected_provider_rows(self, mocked_get_models):
        models = MagicMock()
        mocked_get_models.return_value = models

        cidr_query = MagicMock()
        cidr_query.filter.return_value.delete.return_value = 120
        models.ProviderCidr.query = cidr_query

        asn_query = MagicMock()
        asn_query.filter.return_value.delete.return_value = 5
        models.ProviderAsn.query = asn_query

        snapshot_query = MagicMock()
        snapshot_query.filter.return_value.delete.return_value = 10
        models.ProviderAsnSnapshot.query = snapshot_query

        meta_query = MagicMock()
        meta_query.filter.return_value.delete.return_value = 1
        models.ProviderMeta.query = meta_query

        models.CidrDbRefreshLog = MagicMock()

        db = MagicMock()
        svc = CidrDbUpdaterService(db=db)
        result = svc.clear_provider_data(selected_files=["amazon-ips.txt"], triggered_by="manual:test")

        self.assertTrue(result["success"])
        self.assertEqual(result["providers_cleared"], 1)
        self.assertEqual(result["providers"], ["amazon-ips.txt"])
        self.assertEqual(result["deleted"]["provider_cidr"], 120)
        db.session.add.assert_called_once()
        db.session.commit.assert_called_once()

    @patch("core.services.cidr.db_service._get_models")
    def test_clear_provider_data_full_clear_removes_refresh_history(self, mocked_get_models):
        models = MagicMock()
        mocked_get_models.return_value = models

        cidr_query = MagicMock()
        cidr_query.filter.return_value.delete.return_value = 120
        models.ProviderCidr.query = cidr_query

        asn_query = MagicMock()
        asn_query.filter.return_value.delete.return_value = 5
        models.ProviderAsn.query = asn_query

        snapshot_query = MagicMock()
        snapshot_query.filter.return_value.delete.return_value = 10
        models.ProviderAsnSnapshot.query = snapshot_query

        meta_query = MagicMock()
        meta_query.filter.return_value.delete.return_value = 1
        models.ProviderMeta.query = meta_query

        refresh_log_query = MagicMock()
        refresh_log_query.delete.return_value = 7
        models.CidrDbRefreshLog.query = refresh_log_query

        db = MagicMock()
        svc = CidrDbUpdaterService(db=db)
        result = svc.clear_provider_data(triggered_by="manual:test-full")

        self.assertTrue(result["success"])
        self.assertIn("cidr_db_refresh_log", result["deleted"])
        self.assertEqual(result["deleted"]["cidr_db_refresh_log"], 7)
        db.session.add.assert_not_called()
        db.session.commit.assert_called_once()

    def test_download_cidrs_with_meta_uses_ttl_cache_for_repeated_calls(self):
        svc = CidrDbUpdaterService(db=None)
        CidrDbUpdaterService._source_cache = {}
        sources = [{"name": "source-a", "url": "https://example.test/a", "format": "cidr_text"}]

        with (
            patch("core.services.cidr_db_updater._download_text", return_value="1.1.1.0/24\n") as mocked_download,
            patch.object(svc, "_current_source_fetch_workers", return_value=1),
        ):
            first_items, _, first_details = svc._download_cidrs_with_meta(sources, return_source_details=True)
            second_items, _, second_details = svc._download_cidrs_with_meta(sources, return_source_details=True)

        self.assertEqual(len(first_items), 1)
        self.assertEqual(len(second_items), 1)
        self.assertEqual(mocked_download.call_count, 1)
        self.assertFalse(first_details[0]["cache_hit"])
        self.assertTrue(second_details[0]["cache_hit"])

    @patch("core.services.cidr.db_service._get_models")
    def test_refresh_all_providers_dry_run_skips_db_writes(self, mocked_get_models):
        models = MagicMock()
        models.ProviderCidr.query.filter_by.return_value.count.return_value = 0
        models.ProviderAsn.query.filter_by.return_value.count.return_value = 0
        mocked_get_models.return_value = models

        db = MagicMock()
        svc = CidrDbUpdaterService(db=db)

        with (
            patch.object(svc, "_discover_provider_asns", return_value=([], set(), [])),
            patch.object(
                svc,
                "_download_cidrs_with_meta",
                return_value=(
                    [{"cidr": "173.245.48.0/20", "region": None, "countries": None}],
                    "cloudflare-ips-v4",
                    [{"name": "cloudflare-ips-v4", "status": "ok", "count": 1, "error": None, "cache_hit": False}],
                ),
            ),
            patch.object(svc, "_upsert_provider_asns") as mocked_upsert_asns,
            patch.object(svc, "_upsert_provider_cidrs") as mocked_upsert_cidrs,
            patch.object(svc, "_update_provider_meta") as mocked_update_meta,
        ):
            result = svc.refresh_all_providers(
                selected_files=["cloudflare-ips.txt"],
                triggered_by="manual:test-dry-run",
                dry_run=True,
            )

        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        mocked_upsert_asns.assert_not_called()
        mocked_upsert_cidrs.assert_not_called()
        mocked_update_meta.assert_not_called()


if __name__ == "__main__":
    unittest.main()
