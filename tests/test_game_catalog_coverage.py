import unittest

from core.services.cidr.provider_sources import GAME_FILTER_CATALOG


class GameCatalogCoverageTests(unittest.TestCase):
    def test_every_game_has_server_ips_or_asns(self):
        for item in GAME_FILTER_CATALOG:
            key = item.get("key") or "<unknown>"
            has_server_ips = bool(item.get("server_ips"))
            has_asns = bool(item.get("asns"))
            self.assertTrue(
                has_server_ips or has_asns,
                f"{key} must define server_ips and/or asns (game infrastructure, not website DNS)",
            )

    def test_enriched_games_do_not_use_dns_or_cloudflare_subtitles(self):
        for item in GAME_FILTER_CATALOG:
            key = item.get("key") or "<unknown>"
            subtitle = str(item.get("subtitle") or "")
            if not (item.get("server_ips") or item.get("asns")):
                continue
            self.assertNotIn("— DNS", subtitle, key)
            self.assertNotIn("— Cloudflare", subtitle, key)

    def test_lol_catalog_entry_uses_riot_direct(self):
        lol = next(item for item in GAME_FILTER_CATALOG if item["key"] == "lol")
        self.assertIn("Riot Direct", lol.get("subtitle") or "")
        self.assertIn("104.160.141.3", lol.get("server_ips") or [])
        self.assertIn(6507, lol.get("asns") or [])
        self.assertTrue(lol.get("ip_source_url"))
