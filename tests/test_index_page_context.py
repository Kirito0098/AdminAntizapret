import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from core.services.index import (
    build_client_table_rows,
    build_index_get_context,
    build_index_kpi,
    collect_grouped_service_statuses,
    group_config_files_by_client,
    resolve_openvpn_group_and_files,
)


def _extract_client_name(file_path):
    filename = os.path.basename(file_path)
    stem = filename.rsplit(".", 1)[0]
    for prefix in ("antizapret-", "vpn-"):
        if stem.lower().startswith(prefix):
            stem = stem[len(prefix) :]
            break
    return stem.split("-(")[0]


class IndexPageContextTests(unittest.TestCase):
    def test_group_config_files_by_client_splits_antizapret_and_vpn(self):
        files = [
            "/data/openvpn/vpn-client1-udp.ovpn",
            "/data/openvpn/antizapret-client1-tcp.ovpn",
            "/data/openvpn/vpn-client2-(extra).ovpn",
        ]
        grouped = group_config_files_by_client(files)

        self.assertEqual(list(grouped.keys()), ["client1", "client2"])
        self.assertTrue(grouped["client1"]["vpn"].endswith("vpn-client1-udp.ovpn"))
        self.assertTrue(grouped["client1"]["antizapret"].endswith("antizapret-client1-tcp.ovpn"))
        self.assertTrue(grouped["client2"]["vpn"].endswith("vpn-client2-(extra).ovpn"))
        self.assertIsNone(grouped["client2"]["antizapret"])

    def test_build_index_kpi_counts_expiring_and_expired(self):
        cert_expiry = {
            "alice": {"days_left": 45},
            "bob": {"days_left": 10},
            "carol": {"days_left": 0},
            "dave": {"days_left": -3},
            "eve": {"days_left": None},
        }
        kpi = build_index_kpi(
            cert_expiry,
            blocked_openvpn_count=1,
            blocked_wg_awg_count=2,
            openvpn_count=4,
            wg_awg_count=2,
        )

        self.assertEqual(kpi["expiring_count"], 1)
        self.assertEqual(kpi["expired_count"], 2)
        self.assertEqual(kpi["openvpn_clients_count"], 4)
        self.assertEqual(kpi["wg_awg_clients_count"], 2)
        self.assertEqual(kpi["blocked_openvpn_count"], 1)
        self.assertEqual(kpi["blocked_wg_awg_count"], 2)
        self.assertEqual(kpi["blocked_total_count"], 3)

    def test_build_index_get_context_counts_wg_awg_block_once_per_client(self):
        class FakeHandler:
            def __init__(self, config_paths):
                self.config_paths = dict(config_paths)

            def get_config_files(self):
                return (
                    ["/ovpn/vpn-ov-user-udp.ovpn"],
                    ["/wg/vpn-shared-user-wg.conf"],
                    ["/awg/antizapret-shared-user-am.conf"],
                )

            def get_openvpn_cert_expiry(self):
                return {}

            def _extract_client_name_from_ovpn(self, filename):
                stem = filename.rsplit(".", 1)[0]
                if stem.startswith("vpn-"):
                    stem = stem[4:]
                return stem.replace("-udp", "").replace("-tcp", "")

        session = {"openvpn_group": "GROUP_UDP\\TCP"}
        group_folders = {"GROUP_UDP\\TCP": ["/ovpn"]}
        admin = SimpleNamespace(role="admin", is_admin=lambda: True, allowed_configs=[])

        def fake_extract_name(path):
            stem = os.path.basename(path).rsplit(".", 1)[0]
            for prefix in ("vpn-", "antizapret-"):
                if stem.startswith(prefix):
                    stem = stem[len(prefix):]
                    break
            return stem.replace("-wg", "").replace("-am", "")

        context = build_index_get_context(
            session=session,
            group_folders=group_folders,
            config_file_handler=FakeHandler({"openvpn": ["/ovpn"], "wg": ["/wg"], "amneziawg": ["/awg"]}),
            idx_user=admin,
            read_banned_clients=lambda: {"ov-user"},
            openvpn_build_status_map=lambda names: {
                name: {
                    "is_blocked": name == "ov-user",
                    "reason": "manual_permanent" if name == "ov-user" else None,
                    "block_until": None,
                    "blocked_days_left": None,
                    "block_mode": "permanent" if name == "ov-user" else "none",
                    "block_duration_days": None,
                    "block_started_at": None,
                }
                for name in names
            },
            extract_client_name_from_config_file=fake_extract_name,
            wg_build_status_map=lambda names: {
                name.lower(): {
                    "is_blocked": True,
                    "reason": "manual_temp",
                    "expires_at": None,
                    "block_until": None,
                    "access_days_left": None,
                    "blocked_days_left": None,
                    "block_mode": "temp",
                    "block_duration_days": 7,
                }
                for name in names
            },
            url_for=lambda endpoint, **kwargs: f"/{endpoint}/{kwargs.get('file_type')}/{kwargs.get('filename')}",
        )

        self.assertEqual(context["blocked_openvpn_count"], 1)
        self.assertEqual(context["blocked_wg_awg_count"], 1)
        self.assertEqual(context["blocked_total_count"], 2)
        self.assertEqual(len(context["blocked_entries"]), 2)

    def test_build_client_table_rows_cert_state(self):
        grouped = {
            "active-user": {"vpn": "/x/vpn-active-user-udp.ovpn", "antizapret": None},
            "warn-user": {"vpn": "/x/vpn-warn-user-udp.ovpn", "antizapret": None},
            "dead-user": {"vpn": "/x/vpn-dead-user-udp.ovpn", "antizapret": None},
        }
        cert_expiry = {
            "active-user": {"days_left": 90, "expires_at": "2026-12-01 00:00:00"},
            "warn-user": {"days_left": 15, "expires_at": "2026-06-01 00:00:00"},
            "dead-user": {"days_left": -1, "expires_at": "2025-01-01 00:00:00"},
        }
        admin = SimpleNamespace(role="admin", is_admin=lambda: True)

        def fake_url_for(endpoint, **kwargs):
            return f"/{endpoint}/{kwargs.get('file_type')}/{kwargs.get('filename')}"

        rows = build_client_table_rows(
            "openvpn",
            grouped,
            current_user=admin,
            cert_expiry=cert_expiry,
            banned_clients=set(),
            openvpn_policy_status_by_client={},
            wg_policy_status_by_client={},
            url_for=fake_url_for,
        )
        by_name = {row["client_name"]: row for row in rows}

        self.assertEqual(by_name["active-user"]["cert_state"], "active")
        self.assertEqual(by_name["warn-user"]["cert_state"], "expiring")
        self.assertEqual(by_name["dead-user"]["cert_state"], "expired")
        self.assertTrue(by_name["active-user"]["show_cert_meta"])

    def test_resolve_openvpn_group_and_files_filters_viewer_configs(self):
        class FakeHandler:
            def __init__(self, openvpn_folders):
                self.config_paths = {
                    "openvpn": list(openvpn_folders),
                    "wg": ["/wg"],
                    "amneziawg": ["/awg"],
                }

            def get_config_files(self):
                return (
                    ["/ovpn/vpn-a.ovpn", "/ovpn/vpn-b.ovpn"],
                    ["/wg/vpn-c.conf"],
                    ["/awg/antizapret-d.conf"],
                )

        viewer = SimpleNamespace(
            role="viewer",
            allowed_configs=[
                SimpleNamespace(config_type="openvpn", config_name="vpn-a.ovpn"),
                SimpleNamespace(config_type="wg", config_name="vpn-c.conf"),
            ],
        )
        group_folders = {
            "GROUP_UDP\\TCP": ["/ovpn"],
            "GROUP_UDP": ["/ovpn-udp"],
            "GROUP_TCP": ["/ovpn-tcp"],
        }
        session = {"openvpn_group": "GROUP_UDP\\TCP"}

        (
            group,
            folders,
            handler,
            openvpn_files,
            wg_files,
            amneziawg_files,
        ) = resolve_openvpn_group_and_files(
            session,
            group_folders,
            FakeHandler(group_folders["GROUP_UDP\\TCP"]),
            viewer,
        )

        self.assertEqual(group, "GROUP_UDP\\TCP")
        self.assertEqual(openvpn_files, ["/ovpn/vpn-a.ovpn"])
        self.assertEqual(wg_files, ["/wg/vpn-c.conf"])
        self.assertEqual(amneziawg_files, [])
        self.assertIsInstance(handler, FakeHandler)

    def test_build_client_table_rows_wireguard_policy_block_state(self):
        grouped = {
            "wg-user": {"vpn": "/x/vpn-wg-user-wg.conf", "antizapret": "/x/antizapret-wg-user-wg.conf"},
        }
        admin = SimpleNamespace(role="admin", is_admin=lambda: True)

        def fake_url_for(endpoint, **kwargs):
            return f"/{endpoint}/{kwargs.get('file_type')}/{kwargs.get('filename')}"

        future_expiry = datetime.utcnow() + timedelta(days=10)
        rows = build_client_table_rows(
            "wireguard",
            grouped,
            current_user=admin,
            cert_expiry={},
            banned_clients=set(),
            openvpn_policy_status_by_client={},
            wg_policy_status_by_client={
                "wg-user": {
                    "is_blocked": False,
                    "reason": None,
                    "expires_at": future_expiry,
                    "block_until": None,
                    "access_days_left": 10,
                    "blocked_days_left": None,
                    "block_mode": "none",
                    "block_duration_days": None,
                }
            },
            url_for=fake_url_for,
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertFalse(row["is_blocked"])
        self.assertIsNone(row["wg_block_reason"])
        self.assertEqual(row["block_mode"], "none")
        self.assertEqual(row["access_expires_at"], row["wg_expires_at"])
        self.assertIsInstance(row["wg_days_left"], int)
        self.assertGreaterEqual(row["wg_days_left"], 8)
        self.assertLessEqual(row["wg_days_left"], 10)

    def test_build_client_table_rows_wireguard_shows_hours_when_less_than_day(self):
        grouped = {
            "wg-soon": {"vpn": "/x/vpn-wg-soon-wg.conf"},
        }
        admin = SimpleNamespace(role="admin", is_admin=lambda: True)
        now = datetime.utcnow()
        expires_in_five_hours = now + timedelta(hours=5, minutes=15)

        rows = build_client_table_rows(
            "wireguard",
            grouped,
            current_user=admin,
            cert_expiry={},
            banned_clients=set(),
            openvpn_policy_status_by_client={},
            wg_policy_status_by_client={
                "wg-soon": {
                    "is_blocked": False,
                    "reason": None,
                    "expires_at": expires_in_five_hours,
                    "block_until": None,
                    "access_days_left": 0,
                    "blocked_days_left": None,
                    "block_mode": "none",
                    "block_duration_days": None,
                }
            },
            url_for=lambda endpoint, **kwargs: f"/{endpoint}",
        )

        row = rows[0]
        self.assertEqual(row["access_days_left"], 0)
        self.assertIn("ч.", row["access_remaining_text"])
        self.assertNotIn("сегодня", row["access_remaining_text"])

    def test_collect_grouped_service_statuses_without_systemctl(self):
        statuses = collect_grouped_service_statuses()
        self.assertGreater(len(statuses), 0)
        first_service = statuses[0]["services"][0]
        self.assertIn("state_class", first_service)
        self.assertIn("state_label", first_service)


if __name__ == "__main__":
    unittest.main()
