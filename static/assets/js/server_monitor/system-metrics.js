(function () {
  const { chartColors, chartTypography } = window.ServerMonitorChartTheme;

  const cfg = window.ServerMonitorConfig || {};
  const METRICS_POLL_MS = Number(cfg.metricsPollIntervalMs) || 15000;
  const WS_PUSH_MS = Number(cfg.wsPushIntervalMs) || 2000;
  const MINI_HISTORY_LEN = Number(cfg.historyLen) || 30;

  function createTimestampSeries(length = MINI_HISTORY_LEN, intervalMs = METRICS_POLL_MS) {
    const now = Date.now();
    return Array.from({ length }, (_, i) => now - (length - 1 - i) * intervalMs);
  }

  function formatMiniChartTime(ts) {
    const ageSec = Math.max(0, Math.round((Date.now() - ts) / 1000));
    if (ageSec <= 3) return "сейчас";
    if (ageSec < 60) return `${ageSec} сек назад`;
    const ageMin = Math.round(ageSec / 60);
    return ageMin === 1 ? "1 мин назад" : `${ageMin} мин назад`;
  }

  function formatDurationShort(seconds) {
    const sec = Math.max(1, Math.round(seconds));
    if (sec < 60) return `${sec} сек`;
    const mins = Math.round(sec / 60);
    return mins === 1 ? "1 мин" : `${mins} мин`;
  }

  function getWindowStartLabel(timestamps) {
    if (!timestamps?.length) return "";
    const ageSec = Math.max(1, (Date.now() - timestamps[0]) / 1000);
    const label = formatDurationShort(ageSec);
    return `−${label}`;
  }

  function getWindowCaptionLabel(timestamps) {
    if (!timestamps || timestamps.length < 2) return "—";
    const spanSec = Math.max(1, (timestamps[timestamps.length - 1] - timestamps[0]) / 1000);
    return formatDurationShort(spanSec);
  }

  function updateMiniChartAriaLabels(timestamps) {
    const label = getWindowCaptionLabel(timestamps);
    const ariaSuffix = label === "—" ? "" : ` за ${label}`;
    document.getElementById("cpuChart")?.setAttribute(
      "aria-label",
      `График загрузки CPU${ariaSuffix}`
    );
    document.getElementById("memoryChart")?.setAttribute(
      "aria-label",
      `График загрузки памяти${ariaSuffix}`
    );
  }

  function buildMiniTimeLabels(timestamps) {
    const startLabel = getWindowStartLabel(timestamps);
    return Array.from({ length: timestamps.length }, (_, i) => {
      if (i === 0) return startLabel;
      if (i === timestamps.length - 1) return "сейчас";
      return "";
    });
  }

  function buildMiniDataset({ data, borderColor, backgroundColor }) {
    return {
      data,
      borderColor,
      backgroundColor,
      tension: 0.35,
      pointRadius: (ctx) => (ctx.dataIndex === ctx.dataset.data.length - 1 ? 5 : 0),
      pointHoverRadius: 5.5,
      pointBackgroundColor: borderColor,
      pointBorderColor: "#fff",
      pointBorderWidth: 2,
      borderWidth: 2.8,
      fill: true,
    };
  }

  const MINI_CHART_GRID = chartColors.miniGridStrong || chartColors.gridStrong;

  function buildMiniChartOptions({ getTimestamps, metricLabel }) {
    const tickFontSize = Math.max(chartTypography.size - 2, 9);

    return {
      responsive: true,
      maintainAspectRatio: false,
      layout: {
        padding: { left: 4, right: 10, top: 12, bottom: 2 },
      },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          padding: 8,
          callbacks: {
            title: (items) => {
              const idx = items[0]?.dataIndex;
              const ts = getTimestamps?.()[idx];
              return ts ? formatMiniChartTime(ts) : "";
            },
            label: (ctx) => `${metricLabel}: ${Number(ctx.parsed.y).toFixed(1)}%`,
          },
        },
      },
      scales: {
        y: {
          min: 0,
          max: 100,
          grace: 0,
          clip: false,
          position: "left",
          ticks: {
            color: chartColors.axisY,
            stepSize: 25,
            maxTicksLimit: 5,
            align: "end",
            crossAlign: "near",
            padding: 2,
            callback: (value) => `${value}%`,
            font: {
              family: chartTypography.family,
              size: tickFontSize,
            },
          },
          afterFit: (scale) => {
            scale.width = Math.max(scale.width, 34);
          },
          grid: {
            color: MINI_CHART_GRID,
            lineWidth: 1,
            drawBorder: false,
            tickLength: 0,
          },
          border: { display: false },
        },
        x: {
          display: true,
          ticks: {
            color: chartColors.axisX,
            maxTicksLimit: 2,
            autoSkip: false,
            align: "inner",
            padding: 4,
            font: {
              family: chartTypography.family,
              size: tickFontSize,
            },
            callback: (_value, index, ticks) => {
              const ts = getTimestamps?.();
              if (!ts?.length) return "";
              if (index === 0) return getWindowStartLabel(ts);
              if (index === ticks.length - 1) return "сейчас";
              return "";
            },
          },
          grid: { display: false },
          border: { display: false },
        },
      },
    };
  }

  const STATUS_LABELS = {
    green: "в норме",
    yellow: "повышенная нагрузка",
    red: "критическая нагрузка",
  };

  function updateStatusIndicator(elementId, value, thresholds = { yellow: 70, red: 90 }, labelPrefix = "Статус") {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.classList.remove("green", "yellow", "red");
    let state = "green";
    if (value >= thresholds.red) {
      state = "red";
    } else if (value >= thresholds.yellow) {
      state = "yellow";
    }
    el.classList.add(state);
    el.setAttribute("aria-label", `${labelPrefix}: ${STATUS_LABELS[state]}`);
  }

  function formatDiskGb(value) {
    const gb = Number(value) || 0;
    return `${gb.toFixed(2)} GB`;
  }

  function updateDiskFooter({ percent, usedGb, totalGb }) {
    const used = Number(usedGb) || 0;
    const total = Number(totalGb) || 0;
    const free = Math.max(0, total - used);
    const pct = Math.max(0, Math.min(100, Number(percent) || 0));

    const usedEl = document.getElementById("disk-used");
    const freeEl = document.getElementById("disk-free");
    const totalEl = document.getElementById("disk-total");
    const fillEl = document.getElementById("disk-bar-fill");
    const barEl = fillEl?.closest(".metric-disk-bar");

    if (usedEl) usedEl.textContent = formatDiskGb(used);
    if (freeEl) freeEl.textContent = formatDiskGb(free);
    if (totalEl) totalEl.textContent = formatDiskGb(total);

    if (fillEl) {
      fillEl.style.width = `${pct}%`;
      fillEl.classList.remove("is-warn", "is-danger");
      if (pct >= 90) {
        fillEl.classList.add("is-danger");
      } else if (pct >= 70) {
        fillEl.classList.add("is-warn");
      }
    }

    if (barEl) {
      barEl.setAttribute("aria-valuenow", String(Math.round(pct)));
      barEl.setAttribute("aria-valuetext", `${pct.toFixed(1)}% занято`);
    }
  }

  function updateLoadMetrics(loadAvg = {}) {
    const load1m = Number(loadAvg.load_1m);
    const load5m = Number(loadAvg.load_5m);
    const load15m = Number(loadAvg.load_15m);
    const cpuCount = Math.max(1, Number(loadAvg.cpu_count) || 1);
    const hasLoad = Number.isFinite(load1m);

    const l1 = document.getElementById("load-1m");
    const l5 = document.getElementById("load-5m");
    const l15 = document.getElementById("load-15m");
    const hero = document.getElementById("load-hero");
    const hint = document.getElementById("load-cpu-hint");

    if (l1) l1.textContent = hasLoad ? load1m.toFixed(2) : "—";
    if (l5) l5.textContent = Number.isFinite(load5m) ? load5m.toFixed(2) : "—";
    if (l15) l15.textContent = Number.isFinite(load15m) ? load15m.toFixed(2) : "—";
    if (hero) hero.textContent = hasLoad ? load1m.toFixed(2) : "—";
    if (hint) {
      hint.textContent = `${cpuCount} ${cpuCount === 1 ? "ядро" : cpuCount < 5 ? "ядра" : "ядер"} CPU`;
    }

    const loadPercent = hasLoad ? Math.min(100, (load1m / cpuCount) * 100) : 0;
    updateMetricRing("load-ring", loadPercent);
    updateStatusIndicator("load-indicator", loadPercent, { yellow: 70, red: 90 }, "Нагрузка");
  }

  function updateMetricRing(ringId, percent, thresholds = { yellow: 70, red: 90 }) {
    const ring = document.getElementById(ringId);
    if (!ring) return;
    const value = Math.max(0, Math.min(100, Number(percent) || 0));
    ring.style.setProperty("--ring-value", String(value));
    ring.classList.remove("metric-ring--warn", "metric-ring--danger");
    if (value >= thresholds.red) {
      ring.classList.add("metric-ring--danger");
    } else if (value >= thresholds.yellow) {
      ring.classList.add("metric-ring--warn");
    }
  }

  function syncMiniChartLabels(chart, timestamps) {
    chart.data.labels = buildMiniTimeLabels(timestamps);
    chart.update("none");
  }

  function initMiniCharts() {
    const cpuCtx = document.getElementById("cpuChart")?.getContext("2d");
    const memCtx = document.getElementById("memoryChart")?.getContext("2d");
    if (!cpuCtx || !memCtx) return null;

    const cpuText = document.getElementById("cpu-usage")?.textContent || "";
    const memText = document.getElementById("memory-usage")?.textContent || "";
    const initialCpu = cpuText.includes("—") ? 0 : parseFloat(cpuText) || 0;
    const initialMem = memText.includes("—") ? 0 : parseFloat(memText) || 0;

    updateMetricRing("cpu-ring", initialCpu);
    updateMetricRing("memory-ring", initialMem);

    const diskText = document.getElementById("disk-usage")?.textContent || "";
    const initialDisk = diskText.includes("—") ? 0 : parseFloat(diskText) || 0;
    updateMetricRing("disk-ring", initialDisk);

    const cpuData = Array(MINI_HISTORY_LEN).fill(initialCpu);
    const memoryData = Array(MINI_HISTORY_LEN).fill(initialMem);
    const cpuTimestamps = createTimestampSeries(MINI_HISTORY_LEN);
    const memoryTimestamps = createTimestampSeries(MINI_HISTORY_LEN);
    const miniLabels = buildMiniTimeLabels(cpuTimestamps);

    updateMiniChartAriaLabels(cpuTimestamps);

    const cpuChart = new Chart(cpuCtx, {
      type: "line",
      data: {
        labels: miniLabels.slice(),
        datasets: [buildMiniDataset({
          data: cpuData,
          borderColor: chartColors.cpuBorder,
          backgroundColor: chartColors.cpuFillStrong || chartColors.cpuFill,
        })],
      },
      options: buildMiniChartOptions({
        getTimestamps: () => cpuTimestamps,
        metricLabel: "CPU",
      }),
    });

    const memoryChart = new Chart(memCtx, {
      type: "line",
      data: {
        labels: miniLabels.slice(),
        datasets: [buildMiniDataset({
          data: memoryData,
          borderColor: chartColors.memoryBorder,
          backgroundColor: chartColors.memoryFillStrong || chartColors.memoryFill,
        })],
      },
      options: buildMiniChartOptions({
        getTimestamps: () => memoryTimestamps,
        metricLabel: "Память",
      }),
    });

    window.updateServerCharts = (cpu, memory) => {
      const now = Date.now();
      cpuData.push(cpu);
      cpuData.shift();
      cpuTimestamps.push(now);
      cpuTimestamps.shift();
      memoryData.push(memory);
      memoryData.shift();
      memoryTimestamps.push(now);
      memoryTimestamps.shift();
      cpuChart.data.datasets[0].data = cpuData;
      memoryChart.data.datasets[0].data = memoryData;
      syncMiniChartLabels(cpuChart, cpuTimestamps);
      syncMiniChartLabels(memoryChart, memoryTimestamps);
      updateMiniChartAriaLabels(cpuTimestamps);
      updateStatusIndicator("cpu-indicator", cpu, { yellow: 70, red: 90 }, "CPU");
      updateStatusIndicator("memory-indicator", memory, { yellow: 70, red: 90 }, "Память");
      updateMetricRing("cpu-ring", cpu);
      updateMetricRing("memory-ring", memory);
    };

    return { cpuChart, memoryChart };
  }

  async function loadSystemInfo({ accurate = false } = {}) {
    try {
      const url = accurate ? "/api/system-info?accurate=1" : "/api/system-info";
      const response = await fetch(url, { cache: "no-store" });
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

      updateDiskFooter({
        percent: disk,
        usedGb: data?.disk?.used_gb,
        totalGb: data?.disk?.total_gb,
      });

      updateLoadMetrics(data?.load_average || {});

      const sys = data?.system_info || {};
      const osEl = document.getElementById("systemOS");
      const kEl = document.getElementById("systemKernel");
      const hEl = document.getElementById("systemHostname");
      const uEl = document.getElementById("systemUptime");
      if (osEl) osEl.textContent = `${sys.os || "-"} ${sys.os_release || ""}`.trim();
      if (kEl) kEl.textContent = sys.kernel || "-";
      if (hEl) hEl.textContent = sys.hostname || "-";
      if (uEl) uEl.textContent = data?.uptime || "-";

      updateStatusIndicator("cpu-indicator", cpu, { yellow: 70, red: 90 }, "CPU");
      updateStatusIndicator("memory-indicator", mem, { yellow: 70, red: 90 }, "Память");
      updateStatusIndicator("disk-indicator", disk, { yellow: 70, red: 90 }, "Диск");
      updateMetricRing("cpu-ring", cpu);
      updateMetricRing("memory-ring", mem);
      updateMetricRing("disk-ring", disk);

      const ts = document.getElementById("lastUpdate");
      if (ts) ts.textContent = `Последнее обновление: ${new Date().toLocaleTimeString("ru-RU")}`;

      if (window.updateServerCharts) {
        window.updateServerCharts(cpu, mem);
      }
    } catch (e) {
      console.error("Ошибка загрузки /api/system-info:", e);
      window.showNotification?.("Не удалось загрузить метрики сервера", "error");
    }
  }

  function startWebSocket(onFallbackPoll, { onLive, onPoll } = {}) {
    let liveNotified = false;

    const notifyPoll = () => {
      liveNotified = false;
      if (typeof onPoll === "function") onPoll();
      if (typeof onFallbackPoll === "function") onFallbackPoll();
    };

    const notifyLive = () => {
      if (liveNotified) return;
      liveNotified = true;
      if (typeof onLive === "function") onLive();
    };

    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/monitor`);

      ws.onopen = () => {
        notifyLive();
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === "monitor_update" && window.updateServerCharts) {
            notifyLive();
            window.updateServerCharts(Number(data.cpu || 0), Number(data.memory || 0));
          }
        } catch (err) {
          console.error("Ошибка обработки WebSocket:", err);
        }
      };

      ws.onerror = () => {
        notifyPoll();
      };

      ws.onclose = () => {
        notifyPoll();
      };
    } catch (e) {
      notifyPoll();
    }
  }

  window.ServerMonitorSystemMetrics = {
    METRICS_POLL_MS,
    WS_PUSH_MS,
    MINI_HISTORY_LEN,
    updateStatusIndicator,
    updateMetricRing,
    updateDiskFooter,
    updateLoadMetrics,
    initMiniCharts,
    loadSystemInfo,
    startWebSocket,
  };
})();
