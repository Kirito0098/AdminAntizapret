(function () {
  const getThemeColor = (token, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(token).trim() || fallback;

  const protocolPalette = {
    openvpnBg: getThemeColor("--theme-protocol-openvpn-bg", "rgba(79, 140, 255, 0.82)"),
    openvpnBorder: getThemeColor("--theme-protocol-openvpn-border", "rgba(79, 140, 255, 1)"),
    wireguardBg: getThemeColor("--theme-protocol-wireguard-bg", "rgba(47, 194, 125, 0.82)"),
    wireguardBorder: getThemeColor("--theme-protocol-wireguard-border", "rgba(47, 194, 125, 1)"),
  };

  const chartColors = {
    openvpnBorder: getThemeColor("--theme-chart-openvpn-border", "#4f8cff"),
    openvpnFill: getThemeColor("--theme-chart-openvpn-fill", "rgba(79,140,255,0.14)"),
    wireguardBorder: getThemeColor("--theme-chart-wireguard-border", "#2fc27d"),
    wireguardFill: getThemeColor("--theme-chart-wireguard-fill", "rgba(47,194,125,0.14)"),
    legend: getThemeColor("--theme-chart-legend", "#fff"),
    axisX: getThemeColor("--theme-chart-axis-x", "#bbb"),
    axisY: getThemeColor("--theme-chart-axis-y", "#ddd"),
    gridSoft: getThemeColor("--theme-chart-grid-soft", "rgba(255,255,255,0.05)"),
    gridStrong: getThemeColor("--theme-chart-grid-strong", "rgba(255,255,255,0.1)"),
  };

  window.LogsDashboardChartTheme = {
    getThemeColor,
    protocolPalette,
    chartColors,
  };
})();
