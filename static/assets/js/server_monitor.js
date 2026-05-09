document.addEventListener("DOMContentLoaded", () => {
  let cpuChart = null;
  let memoryChart = null;
  let bwChart = null;
  let pollInterval = null;

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

  let currentIfaceGroup = localStorage.getItem("bw_iface_group") || "vpn";
  let currentRange = localStorage.getItem("bw_range") || "1d";
  let currentUnit = localStorage.getItem("bw_unit") || "MB";

  const rangeBtns = Array.from(document.querySelectorAll(".bw-range-btn"));
  const ifaceBtns = Array.from(document.querySelectorAll(".iface-btn"));
  const unitBtns = Array.from(document.querySelectorAll(".unit-btn"));
  const monitorFiltersToggle = document.getElementById("monitorFiltersToggle");
  const bwControls = document.getElementById("bwControls");
  const mobileUiMedia = window.matchMedia("(max-width: 768px)");

  const elLoad = document.getElementById("network_load");
  const elIface = document.getElementById("bwIface");
  const elNetIf = document.getElementById("network_interface");
  const elRx = document.getElementById("rx_bytes");
  const elTx = document.getElementById("tx_bytes");

  function initMobileFiltersMenu() {
    if (!monitorFiltersToggle || !bwControls) return;

    const setFiltersOpen = (open) => {
      const shouldOpen = !mobileUiMedia.matches || open;
      bwControls.classList.toggle("is-open", shouldOpen);
      monitorFiltersToggle.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
      monitorFiltersToggle.setAttribute("aria-label", shouldOpen ? "Скрыть меню фильтров графика" : "Открыть меню фильтров графика");
    };

    const syncFiltersMode = () => {
      const isMobile = mobileUiMedia.matches;
      monitorFiltersToggle.hidden = !isMobile;
      setFiltersOpen(!isMobile);
    };

    monitorFiltersToggle.addEventListener("click", () => {
      if (!mobileUiMedia.matches) return;
      setFiltersOpen(!bwControls.classList.contains("is-open"));
    });

    if (typeof mobileUiMedia.addEventListener === "function") {
      mobileUiMedia.addEventListener("change", syncFiltersMode);
    } else if (typeof mobileUiMedia.addListener === "function") {
      mobileUiMedia.addListener(syncFiltersMode);
    }

    syncFiltersMode();
  }

  function updateStatusIndicator(elementId, value, thresholds = { yellow: 70, red: 90 }) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.classList.remove("green", "yellow", "red");
    if (value >= thresholds.red) {
      el.classList.add("red");
    } else if (value >= thresholds.yellow) {
      el.classList.add("yellow");
    } else {
      el.classList.add("green");
    }
  }

  function fmtRate(val) {
    const v = Number(val) || 0;
    return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2);
  }

  function fmtVolume(val, unit) {
    const v = Number(val) || 0;
    const units = unit === "MB" ? ["МБ", "ГБ", "ТБ", "ПБ"] : ["Мбит", "Гбит", "Тбит", "Пбит"];
    let i = 0;
    let x = v;
    while (x >= 1024 && i < units.length - 1) {
      x /= 1024;
      i += 1;
    }
    return `${x.toFixed(x >= 100 ? 0 : x >= 10 ? 1 : 2)} ${units[i]}`;
  }

  function fmtVolumeFromBytes(bytes, unit) {
    const mb = (Number(bytes) || 0) / (1024 * 1024);
    return fmtVolume(unit === "MB" ? mb : mb * 8, unit);
  }

  function setActiveBtns() {
    rangeBtns.forEach((b) => {
      const active = b.dataset.range === currentRange;
      b.classList.toggle("active", active);
      b.disabled = active;
    });

    ifaceBtns.forEach((b) => {
      const active = b.dataset.iface === currentIfaceGroup;
      b.classList.toggle("active", active);
      b.disabled = active;
    });

    unitBtns.forEach((b) => {
      const active = b.dataset.unit === currentUnit;
      b.classList.toggle("active", active);
      b.disabled = active;
    });
  }

  function initMiniCharts() {
    const cpuCtx = document.getElementById("cpuChart")?.getContext("2d");
    const memCtx = document.getElementById("memoryChart")?.getContext("2d");
    if (!cpuCtx || !memCtx) return;

    const initialCpu = parseFloat(document.getElementById("cpu-usage")?.textContent) || 0;
    const initialMem = parseFloat(document.getElementById("memory-usage")?.textContent) || 0;

    const cpuData = Array(30).fill(initialCpu);
    const memoryData = Array(30).fill(initialMem);

    cpuChart = new Chart(cpuCtx, {
      type: "line",
      data: {
        labels: Array(30).fill(""),
        datasets: [{
          data: cpuData,
          borderColor: chartColors.cpuBorder,
          backgroundColor: chartColors.cpuFill,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { min: 0, max: 100, ticks: { color: chartColors.legend }, grid: { color: chartColors.miniGrid } },
          x: { display: false },
        },
      },
    });

    memoryChart = new Chart(memCtx, {
      type: "line",
      data: {
        labels: Array(30).fill(""),
        datasets: [{
          data: memoryData,
          borderColor: chartColors.memoryBorder,
          backgroundColor: chartColors.memoryFill,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { min: 0, max: 100, ticks: { color: chartColors.legend }, grid: { color: chartColors.miniGrid } },
          x: { display: false },
        },
      },
    });

    window.updateServerCharts = (cpu, memory) => {
      cpuData.push(cpu);
      cpuData.shift();
      memoryData.push(memory);
      memoryData.shift();
      cpuChart.data.datasets[0].data = cpuData;
      memoryChart.data.datasets[0].data = memoryData;
      cpuChart.update();
      memoryChart.update();
      updateStatusIndicator("cpu-indicator", cpu);
      updateStatusIndicator("memory-indicator", memory);
    };
  }

  async function loadSystemInfo() {
    try {
      const response = await fetch("/api/system-info", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();

      const cpu = Number(data?.cpu?.usage || 0);
      const mem = Number(data?.memory?.usage || 0);
      const disk = Number(data?.disk?.usage_percent || 0);

      const cpuEl = document.getElementById("cpu-usage");
      const memEl = document.getElementById("memory-usage");
      const diskEl = document.getElementById("disk-usage");

      if (cpuEl) cpuEl.textContent = `${cpu.toFixed(1)}%`;
      if (memEl) memEl.textContent = `${mem.toFixed(1)}%`;
      if (diskEl) diskEl.textContent = `${disk.toFixed(1)}%`;

      const diskDetails = document.getElementById("disk-details");
      if (diskDetails) {
        diskDetails.textContent = `${Number(data?.disk?.used_gb || 0).toFixed(2)} GB / ${Number(data?.disk?.total_gb || 0).toFixed(2)} GB`;
      }

      const loadAvg = data?.load_average || {};
      const l1 = document.getElementById("load-1m");
      const l5 = document.getElementById("load-5m");
      const l15 = document.getElementById("load-15m");
      if (l1) l1.textContent = loadAvg.load_1m ?? "-";
      if (l5) l5.textContent = loadAvg.load_5m ?? "-";
      if (l15) l15.textContent = loadAvg.load_15m ?? "-";

      const sys = data?.system_info || {};
      const osEl = document.getElementById("systemOS");
      const kEl = document.getElementById("systemKernel");
      const hEl = document.getElementById("systemHostname");
      const uEl = document.getElementById("systemUptime");
      if (osEl) osEl.textContent = `${sys.os || "-"} ${sys.os_release || ""}`.trim();
      if (kEl) kEl.textContent = sys.kernel || "-";
      if (hEl) hEl.textContent = sys.hostname || "-";
      if (uEl) uEl.textContent = data?.uptime || "-";

      updateStatusIndicator("cpu-indicator", cpu);
      updateStatusIndicator("memory-indicator", mem);
      updateStatusIndicator("disk-indicator", disk);

      const ts = document.getElementById("lastUpdate");
      if (ts) ts.textContent = `Последнее обновление: ${new Date().toLocaleTimeString("ru-RU")}`;

      if (window.updateServerCharts) {
        window.updateServerCharts(cpu, mem);
      }
    } catch (e) {
      console.error("Ошибка загрузки /api/system-info:", e);
    }
  }

  function buildOrUpdateBwChart(labels, rxSeries, txSeries, isRateMode) {
    const ctx = document.getElementById("bwChart")?.getContext("2d");
    if (!ctx) return;

    const unitLabel = currentUnit === "MB" ? "МБ/с" : "Мбит/с";
    const yTitle = isRateMode ? unitLabel : `Трафик за день (${currentUnit === "MB" ? "МБ/ГБ/ТБ" : "Мбит/Гбит/Тбит"})`;

    const config = {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: isRateMode ? `Rx (${unitLabel})` : "Rx (в день)", data: rxSeries, borderColor: chartColors.rxBorder, fill: false, tension: 0.2 },
          { label: isRateMode ? `Tx (${unitLabel})` : "Tx (в день)", data: txSeries, borderColor: chartColors.txBorder, fill: false, tension: 0.2 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        normalized: true,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: chartColors.legend,
              boxWidth: 16,
              boxHeight: 10,
              padding: 14,
              font: {
                family: chartTypography.family,
                size: Math.max(chartTypography.size - 1, 11),
                weight: "600",
              },
            },
          },
          tooltip: {
            callbacks: {
              label: (ctx2) => {
                const v = Number(ctx2.parsed.y) || 0;
                if (isRateMode) return `${ctx2.dataset.label}: ${fmtRate(v)} ${unitLabel}`;
                return `${ctx2.dataset.label}: ${fmtVolume(v, currentUnit)}`;
              },
            },
          },
        },
        scales: {
          y: {
            title: {
              display: true,
              text: yTitle,
              color: chartColors.axisY,
              font: {
                family: chartTypography.family,
                size: Math.max(chartTypography.size - 1, 11),
                weight: "600",
              },
            },
            ticks: {
              color: chartColors.axisY,
              callback: isRateMode ? undefined : (v) => fmtVolume(v, currentUnit),
              maxTicksLimit: 8,
              font: {
                family: chartTypography.family,
                size: Math.max(chartTypography.size - 1, 11),
              },
            },
            grid: { color: chartColors.gridStrong },
          },
          x: {
            ticks: {
              color: chartColors.axisX,
              autoSkip: true,
              maxTicksLimit: currentRange === "1d" ? 14 : 10,
              maxRotation: 0,
              minRotation: 0,
              padding: 8,
              font: {
                family: chartTypography.family,
                size: Math.max(chartTypography.size - 1, 11),
                weight: "500",
              },
            },
            grid: { color: chartColors.gridSoft },
          },
        },
      },
    };

    if (!bwChart) {
      bwChart = new Chart(ctx, config);
    } else {
      bwChart.data = config.data;
      bwChart.options = config.options;
      bwChart.update();
    }
  }

  function sumInterfaceData(datasets) {
    if (!datasets.length) return { labels: [], rx_mbps: [], tx_mbps: [], totals: {} };

    const labelsSource = datasets.find((d) => Array.isArray(d?.labels) && d.labels.length) || datasets[0] || {};
    const labels = Array.isArray(labelsSource.labels) ? labelsSource.labels : [];
    const rx = new Array(labels.length).fill(0);
    const tx = new Array(labels.length).fill(0);
    const totals = {
      "1d": { rx_bytes: 0, tx_bytes: 0, total_bytes: 0 },
      "7d": { rx_bytes: 0, tx_bytes: 0, total_bytes: 0 },
      "30d": { rx_bytes: 0, tx_bytes: 0, total_bytes: 0 },
    };

    datasets.forEach((d) => {
      (d.rx_mbps || []).forEach((v, i) => {
        if (i < rx.length) {
          rx[i] += Number(v) || 0;
        }
      });
      (d.tx_mbps || []).forEach((v, i) => {
        if (i < tx.length) {
          tx[i] += Number(v) || 0;
        }
      });
      ["1d", "7d", "30d"].forEach((p) => {
        totals[p].rx_bytes += Number(d?.totals?.[p]?.rx_bytes || 0);
        totals[p].tx_bytes += Number(d?.totals?.[p]?.tx_bytes || 0);
        totals[p].total_bytes += Number(d?.totals?.[p]?.total_bytes || 0);
      });
    });

    return { labels, rx_mbps: rx, tx_mbps: tx, totals };
  }

  function aggregateToDaily(labels, rxMbps, txMbps, unit, isRateMode) {
    const buckets = new Map();
    const secondsPerDay = 86400;

    labels.forEach((label, i) => {
      const day = String(label || "").split(" ")[0];
      const prev = buckets.get(day) || { rx: 0, tx: 0 };
      const factor = unit === "MB" ? 8 : 1;

      // Для режимов 7d/30d нужно конвертировать средние скорости в общие объемы за день
      const rxVal = isRateMode ? Number(rxMbps[i]) || 0 : (Number(rxMbps[i]) || 0) * secondsPerDay;
      const txVal = isRateMode ? Number(txMbps[i]) || 0 : (Number(txMbps[i]) || 0) * secondsPerDay;

      prev.rx += rxVal / factor;
      prev.tx += txVal / factor;
      buckets.set(day, prev);
    });

    const days = Array.from(buckets.keys());
    return {
      labels: days,
      rx: days.map((d) => buckets.get(d).rx),
      tx: days.map((d) => buckets.get(d).tx),
    };
  }

  function setAggText(id, period, bytes) {
    const labels = { "1d": "за 1 день", "7d": "за 7 дней", "30d": "за 30 дней" };
    const el = document.getElementById(id);
    if (!el) return;
    if (bytes == null) {
      el.textContent = `- ${labels[period]}`;
      return;
    }
    el.innerHTML = `<span class="bw-k">${labels[period]}:</span> <span class="bw-v">${fmtVolumeFromBytes(bytes, currentUnit)}</span>`;
  }

  async function loadBandwidth() {
    try {
      setActiveBtns();
      if (elLoad) elLoad.textContent = "Загрузка...";

      const interfaces = ifaceGroups[currentIfaceGroup] || [currentIfaceGroup];
      if (!interfaces.length) {
        if (elLoad) {
          elLoad.textContent = `Нет интерфейсов для группы ${currentIfaceGroup}`;
        }
        return;
      }
      const responses = await Promise.all(
        interfaces.map((iface) =>
          fetch(`/api/bw?iface=${encodeURIComponent(iface)}&range=${encodeURIComponent(currentRange)}`, { cache: "no-store" }).then((r) => r.json())
        )
      );

      const data = sumInterfaceData(responses);
      const labels = data.labels || [];
      const factor = currentUnit === "MB" ? 8 : 1;

      if (elIface) elIface.textContent = currentIfaceGroup;
      if (elNetIf) elNetIf.textContent = currentIfaceGroup;

      let rxSeries = (data.rx_mbps || []).map((v) => (Number(v) || 0) / factor);
      let txSeries = (data.tx_mbps || []).map((v) => (Number(v) || 0) / factor);
      let chartLabels = labels;
      let isRateMode = currentRange === "1d";

      if (!isRateMode) {
        const daily = aggregateToDaily(labels, data.rx_mbps || [], data.tx_mbps || [], currentUnit, isRateMode);
        chartLabels = daily.labels;
        rxSeries = daily.rx;
        txSeries = daily.tx;
      }

      buildOrUpdateBwChart(chartLabels, rxSeries, txSeries, isRateMode);

      const lastRx = rxSeries.at(-1) || 0;
      const lastTx = txSeries.at(-1) || 0;

      if (isRateMode) {
        // Для режима 1d это скорости
        const speedUnit = currentUnit === "MB" ? "МБ/с" : "Мбит/с";
        if (elRx) elRx.textContent = `${fmtRate(lastRx)} ${speedUnit}`;
        if (elTx) elTx.textContent = `${fmtRate(lastTx)} ${speedUnit}`;
        if (elLoad) elLoad.textContent = `Текущая нагрузка: Rx ${fmtRate(lastRx)} ${speedUnit}, Tx ${fmtRate(lastTx)} ${speedUnit}`;
      } else {
        // Для режимов 7d/30d это объемы за день
        if (elRx) elRx.textContent = `${fmtVolume(lastRx, currentUnit)}`;
        if (elTx) elTx.textContent = `${fmtVolume(lastTx, currentUnit)}`;
        if (elLoad) elLoad.textContent = `Последний день: Rx ${fmtVolume(lastRx, currentUnit)}, Tx ${fmtVolume(lastTx, currentUnit)}`;
      }

      setAggText("bw-rx-1d", "1d", data?.totals?.["1d"]?.rx_bytes);
      setAggText("bw-rx-7d", "7d", data?.totals?.["7d"]?.rx_bytes);
      setAggText("bw-rx-30d", "30d", data?.totals?.["30d"]?.rx_bytes);
      setAggText("bw-tx-1d", "1d", data?.totals?.["1d"]?.tx_bytes);
      setAggText("bw-tx-7d", "7d", data?.totals?.["7d"]?.tx_bytes);
      setAggText("bw-tx-30d", "30d", data?.totals?.["30d"]?.tx_bytes);
      setAggText("bw-total-1d", "1d", data?.totals?.["1d"]?.total_bytes);
      setAggText("bw-total-7d", "7d", data?.totals?.["7d"]?.total_bytes);
      setAggText("bw-total-30d", "30d", data?.totals?.["30d"]?.total_bytes);
    } catch (e) {
      console.error("Ошибка загрузки /api/bw:", e);
      if (elLoad) elLoad.textContent = "Ошибка загрузки данных vnStat.";
    }
  }

  function startWebSocket() {
    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/monitor`);

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === "monitor_update" && window.updateServerCharts) {
            window.updateServerCharts(Number(data.cpu || 0), Number(data.memory || 0));
          }
        } catch (err) {
          console.error("Ошибка обработки WebSocket:", err);
        }
      };

      ws.onerror = () => {
        if (!pollInterval) {
          pollInterval = setInterval(loadSystemInfo, 15000);
        }
      };

      ws.onclose = () => {
        if (!pollInterval) {
          pollInterval = setInterval(loadSystemInfo, 15000);
        }
      };
    } catch (e) {
      if (!pollInterval) {
        pollInterval = setInterval(loadSystemInfo, 15000);
      }
    }
  }

  function closeMobileFiltersMenu() {
    if (!mobileUiMedia.matches || !bwControls) return;
    bwControls.classList.remove("is-open");
    monitorFiltersToggle?.setAttribute("aria-expanded", "false");
    monitorFiltersToggle?.setAttribute("aria-label", "Открыть меню фильтров графика");
  }

  rangeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      currentRange = btn.dataset.range;
      localStorage.setItem("bw_range", currentRange);
      loadBandwidth();
      closeMobileFiltersMenu();
    });
  });

  ifaceBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      currentIfaceGroup = btn.dataset.iface;
      localStorage.setItem("bw_iface_group", currentIfaceGroup);
      loadBandwidth();
      closeMobileFiltersMenu();
    });
  });

  unitBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      currentUnit = btn.dataset.unit;
      localStorage.setItem("bw_unit", currentUnit);
      loadBandwidth();
      closeMobileFiltersMenu();
    });
  });

  document.getElementById("refreshBtn")?.addEventListener("click", async () => {
    const btn = document.getElementById("refreshBtn");
    btn?.classList.add("loading");
    await Promise.all([loadSystemInfo(), loadBandwidth()]);
    btn?.classList.remove("loading");
  });

  initMobileFiltersMenu();
  initMiniCharts();
  setActiveBtns();
  loadSystemInfo();
  loadBandwidth();
  startWebSocket();

  if (!pollInterval) {
    pollInterval = setInterval(loadSystemInfo, 15000);
  }
});
