def build_route_download_actions(public_download_enabled: bool, url_for) -> list[dict]:
    actions = [
        {
            "label": "Общий список IP",
            "href": url_for(
                "download",
                file_type="antizapret_result",
                filename="route-ips.txt",
            ),
            "open_in_new_tab": False,
        },
        {
            "label": "Keenetic WireGuard",
            "href": url_for(
                "download",
                file_type="antizapret_result",
                filename="keenetic-wireguard-routes.txt",
            ),
            "open_in_new_tab": False,
        },
        {
            "label": "MikroTik WireGuard",
            "href": url_for(
                "download",
                file_type="antizapret_result",
                filename="mikrotik-wireguard-routes.txt",
            ),
            "open_in_new_tab": False,
        },
        {
            "label": "TP-Link OpenVPN",
            "href": url_for(
                "download",
                file_type="antizapret_result",
                filename="tp-link-openvpn-routes.txt",
            ),
            "open_in_new_tab": False,
        },
    ]

    if not public_download_enabled:
        return actions

    actions.extend(
        [
            {
                "label": "Публично: Общий список IP",
                "href": url_for("public_download", router="ips"),
                "open_in_new_tab": True,
            },
            {
                "label": "Публично: Keenetic WireGuard",
                "href": url_for("public_download", router="keenetic"),
                "open_in_new_tab": True,
            },
            {
                "label": "Публично: MikroTik WireGuard",
                "href": url_for("public_download", router="mikrotik"),
                "open_in_new_tab": True,
            },
            {
                "label": "Публично: TP-Link OpenVPN",
                "href": url_for("public_download", router="tplink"),
                "open_in_new_tab": True,
            },
        ]
    )
    return actions
