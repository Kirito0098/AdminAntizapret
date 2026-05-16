import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.services.antizapret_settings import read_antizapret_settings
from core.services.openvpn_route_limits import (
    clamp_openvpn_route_total_cidr_limit,
    resolve_openvpn_route_total_cidr_limit,
)
from core.services.routing.page_context import build_routing_page_context


class RoutingPageContextTests(unittest.TestCase):
    def test_build_routing_page_context_keys(self):
        ip_manager = MagicMock()
        ip_manager.list_ip_files.return_value = {"include_ips": {}}
        ip_manager.get_file_states.return_value = {"include_ips": True}
        ip_manager.get_source_states.return_value = {"include_ips": "manual"}

        get_env_value = MagicMock(return_value="500")

        with patch(
            "core.services.routing.page_context.get_available_regions",
            return_value=["eu"],
        ), patch(
            "core.services.routing.page_context.get_available_game_filters",
            return_value=["steam"],
        ), patch(
            "core.services.routing.page_context.get_saved_game_keys",
            return_value=["steam"],
        ), patch(
            "core.services.routing.page_context.read_antizapret_settings",
            return_value={"route_all": "n"},
        ):
            context = build_routing_page_context(
                ip_manager=ip_manager,
                get_env_value=get_env_value,
            )

        ip_manager.sync_enabled.assert_called_once()
        ip_manager.restore_source_from_config.assert_called_once()
        self.assertEqual(context["ip_files"], {"include_ips": {}})
        self.assertEqual(context["ip_file_states"], {"include_ips": True})
        self.assertEqual(context["ip_source_states"], {"include_ips": "manual"})
        self.assertEqual(context["cidr_regions"], ["eu"])
        self.assertEqual(context["cidr_game_filters"], ["steam"])
        self.assertEqual(context["saved_game_keys"], ["steam"])
        self.assertEqual(context["cidr_total_limit"], "500")
        self.assertEqual(context["antizapret_settings"], {"route_all": "n"})

    def test_clamp_openvpn_route_total_cidr_limit_boundaries(self):
        self.assertEqual(clamp_openvpn_route_total_cidr_limit(""), 900)
        self.assertEqual(clamp_openvpn_route_total_cidr_limit("1200"), 900)
        self.assertEqual(clamp_openvpn_route_total_cidr_limit("-5"), 900)
        self.assertEqual(clamp_openvpn_route_total_cidr_limit("450"), 450)

    def test_resolve_openvpn_route_total_cidr_limit(self):
        get_env_value = MagicMock(side_effect=lambda key, default: "1500" if key == "OPENVPN_ROUTE_TOTAL_CIDR_LIMIT" else default)
        self.assertEqual(resolve_openvpn_route_total_cidr_limit(get_env_value), "900")

        get_env_value = MagicMock(return_value=None)
        self.assertEqual(resolve_openvpn_route_total_cidr_limit(get_env_value), "900")

    def test_read_antizapret_settings_from_fixture(self):
        content = "ROUTE_ALL=y\nDISCORD_INCLUDE=n\n"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        settings = read_antizapret_settings(path=tmp_path)
        self.assertEqual(settings.get("route_all"), "y")
        self.assertEqual(settings.get("discord_include"), "n")


if __name__ == "__main__":
    unittest.main()
