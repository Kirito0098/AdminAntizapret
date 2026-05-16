document.addEventListener("DOMContentLoaded", () => {
  const { ifaceGroups } = window.ServerMonitorIfaceGroups;
  const { initMiniCharts, loadSystemInfo, startWebSocket } = window.ServerMonitorSystemMetrics;
  const { loadBandwidth, rebuildBwChartOnResize } = window.ServerMonitorBandwidth;

  let pollInterval = null;

  const page = {
    ifaceGroups,
    bwChart: null,
    currentIfaceGroup: localStorage.getItem("bw_iface_group") || "vpn",
    currentRange: localStorage.getItem("bw_range") || "1d",
    currentUnit: localStorage.getItem("bw_unit") || "MB",
  };

  const rangeBtns = Array.from(document.querySelectorAll(".bw-range-btn"));
  const ifaceBtns = Array.from(document.querySelectorAll(".iface-btn"));
  const unitBtns = Array.from(document.querySelectorAll(".unit-btn"));
  const monitorFiltersToggle = document.getElementById("monitorFiltersToggle");
  const bwControls = document.getElementById("bwControls");
  const monitorLiveBadge = document.getElementById("monitorLiveBadge");
  const lastUpdateEl = document.getElementById("lastUpdate");
  const mobileUiMedia = window.matchMedia("(max-width: 768px)");

  function setMonitorLiveMode(live) {
    if (monitorLiveBadge) {
      monitorLiveBadge.hidden = !live;
      monitorLiveBadge.classList.toggle("is-live", live);
    }
    if (lastUpdateEl) {
      lastUpdateEl.setAttribute("aria-live", live ? "off" : "polite");
    }
  }

  function setActiveBtns() {
    rangeBtns.forEach((b) => {
      const active = b.dataset.range === page.currentRange;
      b.classList.toggle("active", active);
      b.disabled = active;
    });

    ifaceBtns.forEach((b) => {
      const active = b.dataset.iface === page.currentIfaceGroup;
      b.classList.toggle("active", active);
      b.disabled = active;
    });

    unitBtns.forEach((b) => {
      const active = b.dataset.unit === page.currentUnit;
      b.classList.toggle("active", active);
      b.disabled = active;
    });
  }

  function initMobileFiltersMenu() {
    if (!monitorFiltersToggle || !bwControls) return;

    const setFiltersOpen = (open) => {
      const shouldOpen = !mobileUiMedia.matches || open;
      bwControls.classList.toggle("is-open", shouldOpen);
      monitorFiltersToggle.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
      monitorFiltersToggle.setAttribute(
        "aria-label",
        shouldOpen ? "Скрыть меню фильтров графика" : "Открыть меню фильтров графика"
      );
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

  function closeMobileFiltersMenu() {
    if (!mobileUiMedia.matches || !bwControls) return;
    bwControls.classList.remove("is-open");
    monitorFiltersToggle?.setAttribute("aria-expanded", "false");
    monitorFiltersToggle?.setAttribute("aria-label", "Открыть меню фильтров графика");
  }

  function ensureFallbackPoll() {
    setMonitorLiveMode(false);
    if (!pollInterval) {
      pollInterval = setInterval(() => loadSystemInfo(), 15000);
    }
  }

  rangeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      page.currentRange = btn.dataset.range;
      localStorage.setItem("bw_range", page.currentRange);
      setActiveBtns();
      loadBandwidth(page);
      closeMobileFiltersMenu();
    });
  });

  ifaceBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      page.currentIfaceGroup = btn.dataset.iface;
      localStorage.setItem("bw_iface_group", page.currentIfaceGroup);
      setActiveBtns();
      loadBandwidth(page);
      closeMobileFiltersMenu();
    });
  });

  unitBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      page.currentUnit = btn.dataset.unit;
      localStorage.setItem("bw_unit", page.currentUnit);
      setActiveBtns();
      loadBandwidth(page);
      closeMobileFiltersMenu();
    });
  });

  document.getElementById("refreshBtn")?.addEventListener("click", async () => {
    const btn = document.getElementById("refreshBtn");
    btn?.classList.add("loading");
    setActiveBtns();
    await Promise.all([loadSystemInfo({ accurate: true }), loadBandwidth(page)]);
    btn?.classList.remove("loading");
  });

  initMobileFiltersMenu();
  initMiniCharts();
  setActiveBtns();
  loadSystemInfo();
  loadBandwidth(page);
  startWebSocket(ensureFallbackPoll, {
    onLive: () => setMonitorLiveMode(true),
    onPoll: () => setMonitorLiveMode(false),
  });

  if (!pollInterval) {
    pollInterval = setInterval(() => loadSystemInfo(), 15000);
  }

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => rebuildBwChartOnResize(page), 250);
  });
});
