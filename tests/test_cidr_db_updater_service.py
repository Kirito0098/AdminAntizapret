import unittest
from unittest.mock import patch

from core.services.cidr_db_updater import (
    CidrDbUpdaterService,
    _read_positive_int_env,
    _extract_asns_from_text,
    _extract_asns_from_url,
)


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
            asn_errors=[],
        )
        self.assertEqual(level, "critical")
        self.assertIn("CIDR упали", reason)

    def test_should_preserve_previous_pool_on_hard_drop_without_errors(self):
        self.assertTrue(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=1000,
                candidate_cidr_count=70,
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


if __name__ == "__main__":
    unittest.main()
