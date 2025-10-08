// Инициализация логики после загрузки DOM
document.addEventListener("DOMContentLoaded", function () {
  // Получение контекстов холстов и стартовых значений CPU/памяти
  const cpuChartCtx = document.getElementById("cpuChart").getContext("2d");
  const memoryChartCtx = document
    .getElementById("memoryChart")
    .getContext("2d");
  const initialCpu =
    parseFloat(document.getElementById("cpu-usage")?.textContent) || 0;
  const initialMem =
    parseFloat(document.getElementById("memory-usage")?.textContent) || 0;

  // Буферы с последними точками для графиков CPU и памяти
  let cpuData = Array(30).fill(initialCpu);
  let memoryData = Array(30).fill(initialMem);

  // Создание линейного графика загрузки CPU (Chart.js)
  const cpuChart = new Chart(cpuChartCtx, {
    type: "line",
    data: {
      labels: Array(30).fill(""),
      datasets: [
        {
          label: "CPU (%)",
          data: cpuData,
          borderColor: "#4caf50",
          backgroundColor: "rgba(76,175,80,0.1)",
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
        },
      ],
    },
    options: {
      responsive: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          min: 0,
          max: 100,
          ticks: { color: "#fff" },
          grid: { color: "#444" },
        },
        x: { display: false },
      },
    },
  });

  // Создание линейного графика загрузки памяти (Chart.js)
  const memoryChart = new Chart(memoryChartCtx, {
    type: "line",
    data: {
      labels: Array(30).fill(""),
      datasets: [
        {
          label: "Память (%)",
          data: memoryData,
          borderColor: "#2196f3",
          backgroundColor: "rgba(33,150,243,0.1)",
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
        },
      ],
    },
    options: {
      responsive: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          min: 0,
          max: 100,
          ticks: { color: "#fff" },
          grid: { color: "#444" },
        },
        x: { display: false },
      },
    },
  });

  // Функция обновления данных и перерисовки графиков CPU/памяти
  function updateCharts(cpu, memory) {
    cpuData.push(cpu);
    cpuData.shift();
    memoryData.push(memory);
    memoryData.shift();
    cpuChart.data.datasets[0].data = cpuData;
    memoryChart.data.datasets[0].data = memoryData;
    cpuChart.update();
    memoryChart.update();
  }

  // Экспорт функции обновления в глобальную область для внешних вызовов
  window.updateServerCharts = updateCharts;

  // Маппинг интерфейсов на группы
  const ifaceGroups = {
    vpn: ["vpn", "vpn-udp", "vpn-tcp"],
    antizapret: ["antizapret", "antizapret-udp", "antizapret-tcp"],
  };

  // Ссылки на элементы DOM для раздела сетевого трафика
  const elChart = document.getElementById("bwChart");
  const elIface = document.getElementById("bwIface");
  const elNetIf = document.getElementById("network_interface");
  const elLoad = document.getElementById("network_load");
  const elRx = document.getElementById("rx_bytes");
  const elTx = document.getElementById("tx_bytes");

  // Элементы суммарной статистики за периоды
  const sum1d = document.getElementById("bw-sum-1d");
  const sum7d = document.getElementById("bw-sum-7d");
  const sum30d = document.getElementById("bw-sum-30d");

  // Кнопки выбора диапазона, группы интерфейсов и единицы измерения
  const rangeBtns = Array.from(document.querySelectorAll(".bw-range-btn"));
  const ifaceBtns = Array.from(document.querySelectorAll(".iface-btn"));
  const unitBtns = Array.from(document.querySelectorAll(".unit-btn"));

  // Состояние текущей группы интерфейсов, диапазона и единицы измерения
  let currentIfaceGroup = localStorage.getItem("bw_iface_group") || "vpn";
  let currentRange = localStorage.getItem("bw_range") || "1d";
  let currentUnit = localStorage.getItem("bw_unit") || "MB"; // MB или Mbit

  // Переключение активных/неактивных кнопок согласно выбранным параметрам
  function setActiveBtns() {
    rangeBtns.forEach((b) =>
      b.classList.toggle("active", b.dataset.range === currentRange)
    );
    ifaceBtns.forEach((b) =>
      b.classList.toggle("active", b.dataset.iface === currentIfaceGroup)
    );
    unitBtns.forEach((b) =>
      b.classList.toggle("active", b.dataset.unit === currentUnit)
    );
    rangeBtns.forEach((b) => (b.disabled = b.dataset.range === currentRange));
    ifaceBtns.forEach(
      (b) => (b.disabled = b.dataset.iface === currentIfaceGroup)
    );
    unitBtns.forEach((b) => (b.disabled = b.dataset.unit === currentUnit));
  }

  // Форматирование скорости с адаптивной точностью
  const fmtRate = (val, unit) => {
    const v = Number(val) || 0;
    return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2);
  };

  // Преобразование объёма в строку с МБ/ГБ/ТБ или Мбит/Гбит/Тбит
  function fmtVolume(val, unit) {
    const v = Number(val) || 0;
    const units =
      unit === "MB"
        ? ["МБ", "ГБ", "ТБ", "ПБ"]
        : ["Мбит", "Гбит", "Тбит", "Пбит"];
    let i = 0,
      x = v;
    while (x >= 1024 && i < units.length - 1) {
      x /= 1024;
      i++;
    }
    return `${x.toFixed(x >= 100 ? 0 : x >= 10 ? 1 : 2)} ${units[i]}`;
  }

  // Преобразование объёма из байт в строку МБ/ГБ/ТБ или Мбит/Гбит/Тбит
  function fmtVolumeFromBytes(bytes, unit) {
    const mb = (Number(bytes) || 0) / (1024 * 1024);
    const value = unit === "MB" ? mb : mb * 8; // МБ или Мбит
    return fmtVolume(value, unit);
  }

  // Константы длительности интервалов в секундах
  const SEC = { "5min": 300, hour: 3600, day: 86400 };

  // Получение ключа «день» из подписи метки (для агрегации)
  function extractDayKey(label) {
    if (!label) return "";
    return String(label).trim().split(/\s+/)[0];
  }

  // Определение длительности одной точки временного ряда по меткам и подсказкам API
  function detectSecPerPoint(labels, apiInterval, rangestatInterval) {
    if (apiInterval && SEC[apiInterval]) return SEC[apiInterval];

    const parse = (s) => {
      let t = Date.parse(s);
      if (!isNaN(t)) return t;
      const m = String(s).match(
        /^(\d{1,2})\.(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?/
      );
      if (m) {
        const [_, dd, MM, hh = "00", mm = "00"] = m;
        const year = new Date().getFullYear();
        const iso = `${year}-${MM.padStart(2, "0")}-${dd.padStart(
          2,
          "0"
        )}T${hh.padStart(2, "0")}:${mm.padStart(2, "0")}:00`;
        t = Date.parse(iso);
        if (!isNaN(t)) return t;
      }
      return NaN;
    };

    for (let i = 1; i < labels.length; i++) {
      const t0 = parse(labels[i - 1]);
      const t1 = parse(labels[i]);
      if (!isNaN(t0) && !isNaN(t1)) {
        const diff = Math.max(1, Math.abs(t1 - t0) / 1000);
        const candidates = [300, 3600, 86400];
        let best = candidates[0],
          bestErr = Math.abs(diff - best);
        for (const c of candidates.slice(1)) {
          const err = Math.abs(diff - c);
          if (err < bestErr) {
            bestErr = err;
            best = c;
          }
        }
        return best;
      }
    }

    // Используем currentRange вместо rangeHint
    if (currentRange === "7d") return SEC.hour;
    if (currentRange === "30d") return SEC.day;
    return SEC["5min"];
  }

  // Суммирование данных по интерфейсам в группе
  function sumInterfaceData(datasets) {
    if (!datasets || datasets.length === 0)
      return { labels: [], rx_mbps: [], tx_mbps: [], totals: {} };

    const labels = datasets[0].labels || [];
    const rx_mbps = new Array(labels.length).fill(0);
    const tx_mbps = new Array(labels.length).fill(0);
    const totals = {
      "1d": { rx_bytes: 0, tx_bytes: 0, total_bytes: 0 },
      "7d": { rx_bytes: 0, tx_bytes: 0, total_bytes: 0 },
      "30d": { rx_bytes: 0, tx_bytes: 0, total_bytes: 0 },
    };

    datasets.forEach((data) => {
      data.rx_mbps.forEach((val, i) => {
        rx_mbps[i] += Number(val) || 0;
      });
      data.tx_mbps.forEach((val, i) => {
        tx_mbps[i] += Number(val) || 0;
      });
      if (data.totals) {
        for (const period of ["1d", "7d", "30d"]) {
          if (data.totals[period]) {
            totals[period].rx_bytes +=
              Number(data.totals[period].rx_bytes) || 0;
            totals[period].tx_bytes +=
              Number(data.totals[period].tx_bytes) || 0;
            totals[period].total_bytes +=
              Number(data.totals[period].total_bytes) || 0;
          }
        }
      }
    });

    return { labels, rx_mbps, tx_mbps, totals, iface: currentIfaceGroup };
  }

  // Агрегация скоростей (Мбит/с) в суточные объёмы
  function aggregateDaily(labels, rx_mbps, tx_mbps, secPerPoint, unit) {
    const dayBuckets = new Map();
    for (let i = 0; i < labels.length; i++) {
      const day = extractDayKey(labels[i]);
      const rxMbps = Number(rx_mbps[i]) || 0;
      const txMbps = Number(tx_mbps[i]) || 0;
      const factor = unit === "MB" ? 8 : 1; // МБ/с = Мбит/с / 8
      const rxVolume = (rxMbps / factor) * secPerPoint;
      const txVolume = (txMbps / factor) * secPerPoint;
      const cur = dayBuckets.get(day) || { rxVolume: 0, txVolume: 0 };
      cur.rxVolume += rxVolume;
      cur.txVolume += txVolume;
      dayBuckets.set(day, cur);
    }

    const seen = new Set(),
      dayOrder = [];
    for (const lab of labels) {
      const k = extractDayKey(lab);
      if (!seen.has(k)) {
        seen.add(k);
        dayOrder.push(k);
      }
    }

    return {
      labels: dayOrder,
      rxVolumeArr: dayOrder.map((k) => dayBuckets.get(k)?.rxVolume || 0),
      txVolumeArr: dayOrder.map((k) => dayBuckets.get(k)?.txVolume || 0),
    };
  }

  // Создание/обновление графика сетевого трафика
  let bwChart = null;
  function buildOrUpdateChart({ labels, rxSeries, txSeries, mode }) {
    const isRate = mode === "rate";
    const unitLabel = currentUnit === "MB" ? "МБ/с" : "Мбит/с";
    const yTitle = isRate
      ? unitLabel
      : `Трафик за день (${
          currentUnit === "MB" ? "МБ/ГБ/ТБ" : "Мбит/Гбит/Тбит"
        })`;
    const dsLabelRx = isRate ? `Rx (${unitLabel})` : "Rx (в день)";
    const dsLabelTx = isRate ? `Tx (${unitLabel})` : "Tx (в день)";

    const options = {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: {
          title: { display: true, text: yTitle },
          grid: { color: "rgba(255,255,255,0.10)" },
          ticks: {
            color: "#ddd",
            callback: isRate ? (v) => v : (v) => fmtVolume(v, currentUnit),
          },
        },
        x: {
          title: {
            display: true,
            text: currentRange === "1d" ? "Время" : "Дата",
          },
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: {
            color: "#bbb",
            autoSkip: true,
            maxTicksLimit: currentRange === "1d" ? 24 : 10,
          },
        },
      },
      plugins: {
        legend: { position: "bottom", labels: { color: "#fff" } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = Number(ctx.parsed.y) || 0;
              return isRate
                ? `${ctx.dataset.label}: ${fmtRate(
                    v,
                    currentUnit
                  )} ${unitLabel}`
                : `${ctx.dataset.label}: ${fmtVolume(v, currentUnit)}`;
            },
          },
        },
      },
    };

    if (!bwChart) {
      bwChart = new Chart(elChart.getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: dsLabelRx,
              data: rxSeries,
              fill: false,
              tension: 0.2,
              borderColor: "#4caf50",
            },
            {
              label: dsLabelTx,
              data: txSeries,
              fill: false,
              tension: 0.2,
              borderColor: "#f44336",
            },
          ],
        },
        options,
      });
    } else {
      bwChart.data.labels = labels;
      bwChart.data.datasets[0].label = dsLabelRx;
      bwChart.data.datasets[1].label = dsLabelTx;
      bwChart.data.datasets[0].data = rxSeries;
      bwChart.data.datasets[1].data = txSeries;
      bwChart.options = { ...bwChart.options, ...options };
      bwChart.update();
    }
  }

  // Загрузка данных с бэкенда, подготовка рядов и отрисовка графика
  async function loadData() {
    setActiveBtns();
    elLoad.textContent = "Загрузка...";

    try {
      const interfaces = ifaceGroups[currentIfaceGroup] || [currentIfaceGroup];
      const fetchPromises = interfaces.map((iface) =>
        fetch(
          `/api/bw?iface=${encodeURIComponent(
            iface
          )}&range=${encodeURIComponent(currentRange)}`,
          { cache: "no-store" }
        ).then((res) => res.json())
      );
      const datasets = await Promise.all(fetchPromises);
      const data = sumInterfaceData(datasets);

      if (!data || !data.labels) throw new Error("Bad payload");

      elIface.textContent = data.iface || "—";
      elNetIf.textContent = data.iface || "—";

      const labels = data.labels || [];
      const rx_mbps = data.rx_mbps || [];
      const tx_mbps = data.tx_mbps || [];
      const apiInterval = data.interval;

      const factor = currentUnit === "MB" ? 8 : 1; // МБ/с = Мбит/с / 8

      if (currentRange === "1d") {
        const rxSeries = rx_mbps.map((v) => (Number(v) || 0) / factor);
        const txSeries = tx_mbps.map((v) => (Number(v) || 0) / factor);
        const lastRx = rxSeries.at(-1) || 0;
        const lastTx = txSeries.at(-1) || 0;

        elRx.textContent = `${fmtRate(lastRx, currentUnit)} ${
          currentUnit === "MB" ? "МБ/с" : "Мбит/с"
        }`;
        elTx.textContent = `${fmtRate(lastTx, currentUnit)} ${
          currentUnit === "MB" ? "МБ/с" : "Мбит/с"
        }`;
        elLoad.textContent = `Текущая нагрузка: Rx ${fmtRate(
          lastRx,
          currentUnit
        )} ${currentUnit === "MB" ? "МБ/с" : "Мбит/с"}, Tx ${fmtRate(
          lastTx,
          currentUnit
        )} ${
          currentUnit === "MB" ? "МБ/с" : "Мбит/с"
        } (${currentRange}, ${currentIfaceGroup})`;

        buildOrUpdateChart({
          labels,
          rxSeries,
          txSeries,
          mode: "rate",
        });
      } else {
        const secPerPoint = detectSecPerPoint(
          labels,
          apiInterval,
          currentRange
        );
        const daily = aggregateDaily(
          labels,
          rx_mbps,
          tx_mbps,
          secPerPoint,
          currentUnit
        );

        const lastRxRate = (Number(rx_mbps.at(-1)) || 0) / factor;
        const lastTxRate = (Number(tx_mbps.at(-1)) || 0) / factor;
        elRx.textContent = `${fmtRate(lastRxRate, currentUnit)} ${
          currentUnit === "MB" ? "МБ/с" : "Мбит/с"
        }`;
        elTx.textContent = `${fmtRate(lastTxRate, currentUnit)} ${
          currentUnit === "MB" ? "МБ/с" : "Мбит/с"
        }`;
        elLoad.textContent = `Режим: суточные объёмы. Последняя скорость: Rx ${fmtRate(
          lastRxRate,
          currentUnit
        )} ${currentUnit === "MB" ? "МБ/с" : "Мбит/с"}, Tx ${fmtRate(
          lastTxRate,
          currentUnit
        )} ${
          currentUnit === "MB" ? "МБ/с" : "Мбит/с"
        } (${currentRange}, ${currentIfaceGroup})`;

        buildOrUpdateChart({
          labels: daily.labels,
          rxSeries: daily.rxVolumeArr,
          txSeries: daily.txVolumeArr,
          mode: "daily",
        });

        const rxSum = daily.rxVolumeArr.reduce((a, b) => a + b, 0);
        const txSum = daily.txVolumeArr.reduce((a, b) => a + b, 0);
        const totals = data.totals?.[currentRange];
        const rxTotalBackend = totals
          ? (totals.rx_bytes / (1024 * 1024)) * (currentUnit === "MB" ? 1 : 8)
          : null;
        const txTotalBackend = totals
          ? (totals.tx_bytes / (1024 * 1024)) * (currentUnit === "MB" ? 1 : 8)
          : null;
        console.log(
          `[check] ${currentRange}: chartSum=`,
          fmtVolume(rxSum, currentUnit),
          "+",
          fmtVolume(txSum, currentUnit),
          "backend=",
          totals
            ? fmtVolume(rxTotalBackend, currentUnit) +
                " + " +
                fmtVolume(txTotalBackend, currentUnit)
            : "n/a",
          "secPerPoint=",
          secPerPoint
        );
      }

      const PERIOD_LABEL = {
        "1d": "за 1 день",
        "7d": "за 7 дней",
        "30d": "за 30 дней",
      };

      function setStatText(id, periodKey, bytes) {
        const el = document.getElementById(id);
        if (!el) return;
        if (bytes == null) {
          el.textContent = `— ${PERIOD_LABEL[periodKey]}`;
          return;
        }
        el.innerHTML = `<span class="bw-k">${
          PERIOD_LABEL[periodKey]
        }:</span> <span class="bw-v">${fmtVolumeFromBytes(
          bytes,
          currentUnit
        )}</span>`;
      }

      if (data.totals) {
        const t1 = data.totals["1d"];
        const t7 = data.totals["7d"];
        const t30 = data.totals["30d"];

        setStatText("bw-rx-1d", "1d", t1?.rx_bytes);
        setStatText("bw-rx-7d", "7d", t7?.rx_bytes);
        setStatText("bw-rx-30d", "30d", t30?.rx_bytes);

        setStatText("bw-tx-1d", "1d", t1?.tx_bytes);
        setStatText("bw-tx-7d", "7d", t7?.tx_bytes);
        setStatText("bw-tx-30d", "30d", t30?.tx_bytes);

        setStatText("bw-total-1d", "1d", t1?.total_bytes);
        setStatText("bw-total-7d", "7d", t7?.total_bytes);
        setStatText("bw-total-30d", "30d", t30?.total_bytes);
      } else {
        ["rx", "tx", "total"].forEach((kind) => {
          ["1d", "7d", "30d"].forEach((p) =>
            setStatText(`bw-${kind}-${p}`, p, null)
          );
        });
      }
    } catch (e) {
      console.error("Ошибка /api/bw:", e);
      elLoad.textContent = "Ошибка загрузки данных vnStat.";
    }
  }

  // Обработчик кликов по кнопкам диапазона
  rangeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      currentRange = btn.dataset.range;
      localStorage.setItem("bw_range", currentRange);
      loadData();
    });
  });

  // Обработчик кликов по кнопкам группы интерфейсов
  ifaceBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      currentIfaceGroup = btn.dataset.iface;
      localStorage.setItem("bw_iface_group", currentIfaceGroup);
      loadData();
    });
  });

  // Обработчик кликов по кнопкам единицы измерения
  unitBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      currentUnit = btn.dataset.unit;
      localStorage.setItem("bw_unit", currentUnit);
      loadData();
    });
  });

  // Начальная инициализация состояния и первичная загрузка данных
  setActiveBtns();
  loadData();
});
