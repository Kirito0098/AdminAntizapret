(function () {
  const defaultIfaceGroups = {
    vpn: ["vpn", "vpn-udp", "vpn-tcp"],
    antizapret: ["antizapret", "antizapret-udp", "antizapret-tcp"],
    openvpn: ["vpn-udp", "vpn-tcp", "antizapret-udp", "antizapret-tcp"],
    wireguard: ["vpn", "antizapret"],
  };

  const runtimeIfaceGroups = window.__bwIfaceGroups || {};
  const pickIfaceGroup = (groupName) =>
    Array.isArray(runtimeIfaceGroups[groupName]) && runtimeIfaceGroups[groupName].length
      ? runtimeIfaceGroups[groupName]
      : defaultIfaceGroups[groupName] || [];

  const ifaceGroups = {
    vpn: pickIfaceGroup("vpn"),
    antizapret: pickIfaceGroup("antizapret"),
    openvpn: pickIfaceGroup("openvpn"),
    wireguard: pickIfaceGroup("wireguard"),
  };

  window.ServerMonitorIfaceGroups = {
    defaultIfaceGroups,
    ifaceGroups,
    pickIfaceGroup,
  };
})();
