(function () {
  const { chartColors, chartTypography } = window.ServerMonitorChartTheme;
  const { fmtRate, fmtVolume, fmtVolumeFromBytes } = window.ServerMonitorFmt;

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

  function buildOrUpdateBwChart(page, labels, rxSeries, txSeries, isRateMode) {
    const ctx = document.getElementById("bwChart")?.getContext("2d");
    if (!ctx) return;

    const unitLabel = page.currentUnit === "MB" ? "МБ/с" : "Мбит/с";
    const yTitle = isRateMode
      ? unitLabel
      : `Трафик за день (${page.currentUnit === "MB" ? "МБ/ГБ/ТБ" : "Мбит/Гбит/Тбит"})`;

    const vw = window.innerWidth;
    const isMobile = vw < 480;
    const isNarrow = vw < 768;
    const tickFontSize = isMobile
      ? Math.max(chartTypography.size - 2, 10)
      : Math.max(chartTypography.size - 1, 11);
    const xMaxTicks = isMobile ? 5 : isNarrow ? 8 : page.currentRange === "1d" ? 14 : 10;

    const config = {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: isRateMode ? `Rx (${unitLabel})` : "Rx (в день)",
            data: rxSeries,
            borderColor: chartColors.rxBorder,
            fill: false,
            tension: 0.2,
          },
          {
            label: isRateMode ? `Tx (${unitLabel})` : "Tx (в день)",
            data: txSeries,
            borderColor: chartColors.txBorder,
            fill: false,
            tension: 0.2,
          },
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
              boxWidth: isMobile ? 12 : 16,
              boxHeight: isMobile ? 8 : 10,
              padding: isMobile ? 8 : 14,
              font: {
                family: chartTypography.family,
                size: tickFontSize,
                weight: "600",
              },
            },
          },
          tooltip: {
            callbacks: {
              label: (ctx2) => {
                const v = Number(ctx2.parsed.y) || 0;
                if (isRateMode) return `${ctx2.dataset.label}: ${fmtRate(v)} ${unitLabel}`;
                return `${ctx2.dataset.label}: ${fmtVolume(v, page.currentUnit)}`;
              },
            },
          },
        },
        scales: {
          y: {
            title: {
              display: !isMobile,
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
              callback: isRateMode ? undefined : (v) => fmtVolume(v, page.currentUnit),
              maxTicksLimit: isMobile ? 5 : 8,
              font: {
                family: chartTypography.family,
                size: tickFontSize,
              },
            },
            grid: { color: chartColors.gridStrong },
          },
          x: {
            ticks: {
              color: chartColors.axisX,
              autoSkip: true,
              maxTicksLimit: xMaxTicks,
              maxRotation: 0,
              minRotation: 0,
              padding: isMobile ? 4 : 8,
              font: {
                family: chartTypography.family,
                size: tickFontSize,
                weight: "500",
              },
            },
            grid: { color: chartColors.gridSoft },
          },
        },
      },
    };

    if (!page.bwChart) {
      page.bwChart = new Chart(ctx, config);
    } else {
      page.bwChart.data = config.data;
      page.bwChart.options = config.options;
      page.bwChart.update();
    }
  }

  function setAggText(id, period, bytes, unit) {
    const labels = { "1d": "за 1 день", "7d": "за 7 дней", "30d": "за 30 дней" };
    const el = document.getElementById(id);
    if (!el) return;
    if (bytes == null) {
      el.textContent = `- ${labels[period]}`;
      return;
    }
    el.innerHTML = `<span class="bw-k">${labels[period]}:</span> <span class="bw-v">${fmtVolumeFromBytes(bytes, unit)}</span>`;
  }

  async function loadBandwidth(page) {
    const elLoad = document.getElementById("network_load");
    const elIface = document.getElementById("bwIface");
    const elNetIf = document.getElementById("network_interface");
    const elRx = document.getElementById("rx_bytes");
    const elTx = document.getElementById("tx_bytes");

    try {
      if (elLoad) elLoad.textContent = "Загрузка...";

      const interfaces = page.ifaceGroups[page.currentIfaceGroup] || [page.currentIfaceGroup];
      if (!interfaces.length) {
        if (elLoad) {
          elLoad.textContent = `Нет интерфейсов для группы ${page.currentIfaceGroup}`;
        }
        return;
      }

      const responses = await Promise.all(
        interfaces.map((iface) =>
          fetch(
            `/api/bw?iface=${encodeURIComponent(iface)}&range=${encodeURIComponent(page.currentRange)}`,
            { cache: "no-store" }
          ).then((r) => r.json())
        )
      );

      const data = sumInterfaceData(responses);
      const labels = data.labels || [];
      const factor = page.currentUnit === "MB" ? 8 : 1;

      if (elIface) elIface.textContent = page.currentIfaceGroup;
      if (elNetIf) elNetIf.textContent = page.currentIfaceGroup;

      let rxSeries = (data.rx_mbps || []).map((v) => (Number(v) || 0) / factor);
      let txSeries = (data.tx_mbps || []).map((v) => (Number(v) || 0) / factor);
      let chartLabels = labels;
      const isRateMode = page.currentRange === "1d";

      if (!isRateMode) {
        const daily = aggregateToDaily(labels, data.rx_mbps || [], data.tx_mbps || [], page.currentUnit, isRateMode);
        chartLabels = daily.labels;
        rxSeries = daily.rx;
        txSeries = daily.tx;
      }

      buildOrUpdateBwChart(page, chartLabels, rxSeries, txSeries, isRateMode);

      const lastRx = rxSeries.at(-1) || 0;
      const lastTx = txSeries.at(-1) || 0;

      if (isRateMode) {
        const speedUnit = page.currentUnit === "MB" ? "МБ/с" : "Мбит/с";
        if (elRx) elRx.textContent = `${fmtRate(lastRx)} ${speedUnit}`;
        if (elTx) elTx.textContent = `${fmtRate(lastTx)} ${speedUnit}`;
        if (elLoad) {
          elLoad.textContent = `Текущая нагрузка: Rx ${fmtRate(lastRx)} ${speedUnit}, Tx ${fmtRate(lastTx)} ${speedUnit}`;
        }
      } else {
        if (elRx) elRx.textContent = `${fmtVolume(lastRx, page.currentUnit)}`;
        if (elTx) elTx.textContent = `${fmtVolume(lastTx, page.currentUnit)}`;
        if (elLoad) {
          elLoad.textContent = `Последний день: Rx ${fmtVolume(lastRx, page.currentUnit)}, Tx ${fmtVolume(lastTx, page.currentUnit)}`;
        }
      }

      setAggText("bw-rx-1d", "1d", data?.totals?.["1d"]?.rx_bytes, page.currentUnit);
      setAggText("bw-rx-7d", "7d", data?.totals?.["7d"]?.rx_bytes, page.currentUnit);
      setAggText("bw-rx-30d", "30d", data?.totals?.["30d"]?.rx_bytes, page.currentUnit);
      setAggText("bw-tx-1d", "1d", data?.totals?.["1d"]?.tx_bytes, page.currentUnit);
      setAggText("bw-tx-7d", "7d", data?.totals?.["7d"]?.tx_bytes, page.currentUnit);
      setAggText("bw-tx-30d", "30d", data?.totals?.["30d"]?.tx_bytes, page.currentUnit);
      setAggText("bw-total-1d", "1d", data?.totals?.["1d"]?.total_bytes, page.currentUnit);
      setAggText("bw-total-7d", "7d", data?.totals?.["7d"]?.total_bytes, page.currentUnit);
      setAggText("bw-total-30d", "30d", data?.totals?.["30d"]?.total_bytes, page.currentUnit);
    } catch (e) {
      console.error("Ошибка загрузки /api/bw:", e);
      if (elLoad) elLoad.textContent = "Ошибка загрузки данных vnStat.";
      window.showNotification?.("Ошибка загрузки данных vnStat", "error");
    }
  }

  function rebuildBwChartOnResize(page) {
    if (!page.bwChart) return;
    page.bwChart.destroy();
    page.bwChart = null;
    loadBandwidth(page);
  }

  window.ServerMonitorBandwidth = {
    loadBandwidth,
    rebuildBwChartOnResize,
  };
})();
