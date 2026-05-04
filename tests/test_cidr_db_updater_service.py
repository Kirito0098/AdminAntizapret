import unittest
from unittest.mock import patch

from core.services.cidr_db_updater import (
    CidrDbUpdaterService,
    _extract_asns_from_text,
    _extract_asns_from_url,
)


class CidrDbUpdaterServiceHelperTests(unittest.TestCase):
    def test_extract_asns_from_url_supports_query_and_path(self):
        url = "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS13335&other=1"
        self.assertIn(13335, _extract_asns_from_url(url))

        path_url = "https://example.test/as15169/overview"
        self.assertIn(15169, _extract_asns_from_url(path_url))

    def test_extract_asns_from_text(self):
        text = "provider list: AS13335, as15169, AS209242"
        parsed = _extract_asns_from_text(text)
        self.assertEqual(parsed, {13335, 15169, 209242})

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

    def test_should_preserve_previous_pool_on_medium_drop_with_errors(self):
        self.assertTrue(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=1000,
                candidate_cidr_count=520,
                asn_errors=["AS123: timeout"],
            )
        )

    def test_should_not_preserve_previous_pool_on_medium_drop_without_errors(self):
        self.assertFalse(
            CidrDbUpdaterService._should_preserve_previous_pool(
                previous_cidr_count=1000,
                candidate_cidr_count=520,
                asn_errors=[],
            )
        )

    def test_merge_anomaly_reason_keeps_higher_severity_and_appends_reason(self):
        level, reason = CidrDbUpdaterService._merge_anomaly_reason(
            level="critical",
            reason="CIDR упали на 63%",
            extra_level="warning",
            extra_reason="Применен safe-fallback",
        )
        self.assertEqual(level, "critical")
        self.assertIn("CIDR упали", reason)
        self.assertIn("safe-fallback", reason)

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


if __name__ == "__main__":
    unittest.main()
