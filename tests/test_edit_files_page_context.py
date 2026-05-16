import unittest
from types import SimpleNamespace

from core.services.edit_files import (
    build_edit_files_get_context,
    build_route_download_actions,
    resolve_file_nav_group,
    validate_editor_content,
)


class EditFilesPageContextTests(unittest.TestCase):
    def test_resolve_file_nav_group_domains(self):
        self.assertEqual(resolve_file_nav_group("include_hosts"), "Домены")
        self.assertEqual(resolve_file_nav_group("exclude_hosts"), "Домены")
        self.assertEqual(resolve_file_nav_group("remove-hosts"), "Домены")

    def test_resolve_file_nav_group_ip_routing(self):
        for file_type in ("include_ips", "exclude-ips", "forward-ips", "drop-ips"):
            self.assertEqual(resolve_file_nav_group(file_type), "IP и маршрутизация")

    def test_resolve_file_nav_group_adblock(self):
        self.assertEqual(resolve_file_nav_group("include-adblock-hosts"), "Рекламные фильтры")
        self.assertEqual(resolve_file_nav_group("exclude-adblock-hosts"), "Рекламные фильтры")

    def test_resolve_file_nav_group_allow_ips(self):
        self.assertEqual(resolve_file_nav_group("allow-ips"), "Безопасность")

    def test_resolve_file_nav_group_other(self):
        self.assertEqual(resolve_file_nav_group("unknown-list"), "Прочее")

    def test_build_edit_files_get_context_first_item_active(self):
        file_editor = SimpleNamespace(
            get_file_contents=lambda: {
                "include_hosts": "a.example.com\n",
                "drop-ips": "10.0.0.0/8\n",
            },
            get_file_display_titles=lambda: {
                "include_hosts": "# Hosts List",
                "drop-ips": "# Drop IPs",
            },
        )

        def fake_url_for(endpoint, **kwargs):
            return f"/{endpoint}"

        context = build_edit_files_get_context(
            file_editor,
            get_public_download_enabled=lambda: False,
            url_for=fake_url_for,
        )

        self.assertEqual(len(context["file_nav_items"]), 2)
        self.assertTrue(context["file_nav_items"][0]["is_active"])
        self.assertFalse(context["file_nav_items"][1]["is_active"])
        self.assertEqual(context["file_nav_items"][0]["title"], "# Hosts List")
        self.assertEqual(context["editor_forms"][0]["title"], "# Hosts List")
        self.assertEqual(context["editor_forms"][0]["content"], "a.example.com\n")
        self.assertEqual(context["editor_forms"][0]["form_id"], "form-include_hosts")
        self.assertIn("домену или IP", context["editor_forms"][0]["subtitle"])
        self.assertIn("CIDR", context["editor_forms"][1]["subtitle"])

    def test_validate_editor_content_null_byte(self):
        ok, message = validate_editor_content("line\x00break")
        self.assertFalse(ok)
        self.assertIn("нулевой байт", message)

    def test_validate_editor_content_too_large(self):
        ok, message = validate_editor_content("x" * (1024 * 1024 + 1))
        self.assertFalse(ok)
        self.assertIn("1 MiB", message)

    def test_validate_editor_content_valid(self):
        ok, message = validate_editor_content("example.com\n# comment\n")
        self.assertTrue(ok)
        self.assertEqual(message, "")

    def test_build_route_download_actions_without_public(self):
        def fake_url_for(endpoint, **kwargs):
            return f"{endpoint}:{kwargs}"

        actions = build_route_download_actions(False, fake_url_for)
        self.assertEqual(len(actions), 4)
        self.assertTrue(all(not action["open_in_new_tab"] for action in actions))

    def test_build_route_download_actions_with_public(self):
        def fake_url_for(endpoint, **kwargs):
            return f"{endpoint}:{kwargs}"

        actions = build_route_download_actions(True, fake_url_for)
        self.assertEqual(len(actions), 8)
        public_actions = [action for action in actions if action["open_in_new_tab"]]
        self.assertEqual(len(public_actions), 4)
        self.assertTrue(all("Публично" in action["label"] for action in public_actions))


if __name__ == "__main__":
    unittest.main()
