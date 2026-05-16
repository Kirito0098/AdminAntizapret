(function () {
  const { chartColors } = window.ServerMonitorChartTheme;

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

    const cpuData = Array(30).fill(initialCpu);
    const memoryData = Array(30).fill(initialMem);

    const cpuChart = new Chart(cpuCtx, {
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

    const memoryChart = new Chart(memCtx, {
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
    updateStatusIndicator,
    updateMetricRing,
    initMiniCharts,
    loadSystemInfo,
    startWebSocket,
  };
})();
