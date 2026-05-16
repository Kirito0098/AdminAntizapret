(function () {
  const getThemeColor = (token, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(token).trim() || fallback;

  const chartColors = {
    cpuBorder: getThemeColor("--theme-chart-vpn-border", "#4caf50"),
    cpuFill: getThemeColor("--theme-chart-vpn-fill", "rgba(76, 175, 80, 0.12)"),
    memoryBorder: getThemeColor("--theme-secondary", "#2196f3"),
    memoryFill: getThemeColor("--theme-secondary-alpha-10", "rgba(33, 150, 243, 0.1)"),
    rxBorder: getThemeColor("--theme-chart-vpn-border", "#4caf50"),
    txBorder: getThemeColor("--theme-chart-antizapret-border", "#f44336"),
    legend: getThemeColor("--theme-chart-legend", "#fff"),
    axisX: getThemeColor("--theme-chart-axis-x", "#bbb"),
    axisY: getThemeColor("--theme-chart-axis-y", "#ddd"),
    gridSoft: getThemeColor("--theme-chart-grid-soft", "rgba(255, 255, 255, 0.05)"),
    gridStrong: getThemeColor("--theme-chart-grid-strong", "rgba(255, 255, 255, 0.1)"),
    miniGrid: getThemeColor("--theme-chart-grid-monitor", "#444"),
  };

  const chartTypography = {
    family: getThemeColor("--chart-font-family", "Segoe UI, DejaVu Sans, Liberation Sans, Arial, sans-serif"),
    size: parseInt(getThemeColor("--chart-font-size", "12px"), 10) || 12,
  };

  if (typeof Chart !== "undefined") {
    Chart.defaults.font.family = chartTypography.family;
    Chart.defaults.font.size = chartTypography.size;
    Chart.defaults.color = chartColors.legend;
  }

  window.ServerMonitorChartTheme = {
    chartColors,
    chartTypography,
    getThemeColor,
  };
})();
