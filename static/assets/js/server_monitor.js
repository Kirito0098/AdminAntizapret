// Инициализация логики после загрузки DOM
document.addEventListener('DOMContentLoaded', function () {
  // Получение контекстов холстов и стартовых значений CPU/памяти
  const cpuChartCtx = document.getElementById('cpuChart').getContext('2d');
  const memoryChartCtx = document
    .getElementById('memoryChart')
    .getContext('2d');
  const initialCpu =
    parseFloat(document.getElementById('cpu-usage')?.textContent) || 0;
  const initialMem =
    parseFloat(document.getElementById('memory-usage')?.textContent) || 0;

  // Буферы с последними точками для графиков CPU и памяти
  let cpuData = Array(30).fill(initialCpu);
  let memoryData = Array(30).fill(initialMem);

  // Создание линейного графика загрузки CPU (Chart.js)
  const cpuChart = new Chart(cpuChartCtx, {
    type: 'line',
    data: {
      labels: Array(30).fill(''),
      datasets: [
        {
          label: 'CPU (%)',
          data: cpuData,
          borderColor: '#4caf50',
          backgroundColor: 'rgba(76,175,80,0.1)',
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
          ticks: { color: '#fff' },
          grid: { color: '#444' },
        },
        x: { display: false },
      },
    },
  });

  // Создание линейного графика загрузки памяти (Chart.js)
  const memoryChart = new Chart(memoryChartCtx, {
    type: 'line',
    data: {
      labels: Array(30).fill(''),
      datasets: [
        {
          label: 'Память (%)',
          data: memoryData,
          borderColor: '#2196f3',
          backgroundColor: 'rgba(33,150,243,0.1)',
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
          ticks: { color: '#fff' },
          grid: { color: '#444' },
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

  // Ссылки на элементы DOM для раздела сетевого трафика
  const elChart = document.getElementById('bwChart');
  const elIface = document.getElementById('bwIface');
  const elNetIf = document.getElementById('network_interface');
  const elLoad = document.getElementById('network_load');
  const elRx = document.getElementById('rx_bytes');
  const elTx = document.getElementById('tx_bytes');

  // Элементы суммарной статистики за периоды
  const sum1d = document.getElementById('bw-sum-1d');
  const sum7d = document.getElementById('bw-sum-7d');
  const sum30d = document.getElementById('bw-sum-30d');

  // Кнопки выбора диапазона и интерфейса
  const rangeBtns = Array.from(document.querySelectorAll('.bw-range-btn'));
  const ifaceBtns = Array.from(document.querySelectorAll('.iface-btn'));

  // Состояние текущего интерфейса и выбранного диапазона (сохранение в localStorage)
  let currentIface = localStorage.getItem('bw_iface') || 'ens3';
  let currentRange = localStorage.getItem('bw_range') || '1d';

  // Переключение активных/неактивных кнопок согласно выбранным параметрам
  function setActiveBtns() {
    rangeBtns.forEach((b) =>
      b.classList.toggle('active', b.dataset.range === currentRange),
    );
    ifaceBtns.forEach((b) =>
      b.classList.toggle('active', b.dataset.iface === currentIface),
    );
    rangeBtns.forEach((b) => (b.disabled = b.dataset.range === currentRange));
    ifaceBtns.forEach((b) => (b.disabled = b.dataset.iface === currentIface));
  }

  // Форматирование скорости в МБ/с с адаптивной точностью
  const fmtRateMBps = (val) => {
    const v = Number(val) || 0;
    return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2);
  };

  // Преобразование объёма из МБ в строку с МБ/ГБ/ТБ (автовыбор единицы)
  function fmtMBGBTBFromMB(mb) {
    const v = Number(mb) || 0;
    const units = ['МБ', 'ГБ', 'ТБ', 'ПБ'];
    let i = 0,
      x = v;
    while (x >= 1024 && i < units.length - 1) {
      x /= 1024;
      i++;
    }
    return `${x.toFixed(x >= 100 ? 0 : x >= 10 ? 1 : 2)} ${units[i]}`;
  }

  // Преобразование объёма из байт в строку МБ/ГБ/ТБ
  function fmtMBGBTBFromBytes(bytes) {
    const mb = (Number(bytes) || 0) / (1024 * 1024);
    return fmtMBGBTBFromMB(mb);
  }

  // Константы длительности интервалов в секундах
  const SEC = { '5min': 300, hour: 3600, day: 86400 };

  // Получение ключа «день» из подписи метки (для агрегации)
  function extractDayKey(label) {
    if (!label) return '';
    return String(label).trim().split(/\s+/)[0];
  }

  // Определение длительности одной точки временного ряда по меткам и подсказкам API
  function detectSecPerPoint(labels, apiInterval, rangeHint) {
    if (apiInterval && SEC[apiInterval]) return SEC[apiInterval];

    const parse = (s) => {
      let t = Date.parse(s);
      if (!isNaN(t)) return t;
      const m = String(s).match(
        /^(\d{1,2})\.(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?/,
      );
      if (m) {
        const [_, dd, MM, hh = '00', mm = '00'] = m;
        const year = new Date().getFullYear();
        const iso = `${year}-${MM.padStart(2, '0')}-${dd.padStart(
          2,
          '0',
        )}T${hh.padStart(2, '0')}:${mm.padStart(2, '0')}:00`;
        t = Date.parse(iso);
        if (!isNaN(t)) return t;
      }
      return NaN;
    };

    // Поиск ближайшей реальной разницы между соседними точками и выбор подходящего интервала
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

    // Подбор интервала по выбранному диапазону, если парсинг не удался
    if (rangeHint === '7d') return SEC.hour;
    if (rangeHint === '30d') return SEC.day;
    return SEC['5min'];
  }

  // Агрегация скоростей (Мбит/с) в суточные объёмы (МБ) по дням
  function aggregateDaily(labels, rx_mbps, tx_mbps, secPerPoint) {
    const dayBuckets = new Map();
    for (let i = 0; i < labels.length; i++) {
      const day = extractDayKey(labels[i]);
      const rxMbps = Number(rx_mbps[i]) || 0;
      const txMbps = Number(tx_mbps[i]) || 0;
      const rxMB = (rxMbps / 8) * secPerPoint;
      const txMB = (txMbps / 8) * secPerPoint;
      const cur = dayBuckets.get(day) || { rxMB: 0, txMB: 0 };
      cur.rxMB += rxMB;
      cur.txMB += txMB;
      dayBuckets.set(day, cur);
    }

    // Сохранение порядка дней согласно порядку меток
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
      rxMBarr: dayOrder.map((k) => dayBuckets.get(k)?.rxMB || 0),
      txMBarr: dayOrder.map((k) => dayBuckets.get(k)?.txMB || 0),
    };
  }

  // Создание/обновление графика сетевого трафика (скорость или суточные объёмы)
  let bwChart = null;
  function buildOrUpdateChart({ labels, rxSeries, txSeries, mode }) {
    const isRate = mode === 'rate';
    const yTitle = isRate ? 'МБ/с' : 'Трафик за день (МБ/ГБ/ТБ)';
    const dsLabelRx = isRate ? 'Rx (МБ/с)' : 'Rx (в день)';
    const dsLabelTx = isRate ? 'Tx (МБ/с)' : 'Tx (в день)';

    const options = {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      scales: {
        y: {
          title: { display: true, text: yTitle },
          grid: { color: 'rgba(255,255,255,0.10)' },
          ticks: {
            color: '#ddd',
            callback: isRate ? (v) => v : (v) => fmtMBGBTBFromMB(v),
          },
        },
        x: {
          title: {
            display: true,
            text: currentRange === '1d' ? 'Время' : 'Дата',
          },
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: {
            color: '#bbb',
            autoSkip: true,
            maxTicksLimit: currentRange === '1d' ? 24 : 10,
          },
        },
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: '#fff' } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = Number(ctx.parsed.y) || 0;
              return isRate
                ? `${ctx.dataset.label}: ${fmtRateMBps(v)} МБ/с`
                : `${ctx.dataset.label}: ${fmtMBGBTBFromMB(v)}`;
            },
          },
        },
      },
    };

    // Инициализация нового графика либо обновление существующего
    if (!bwChart) {
      bwChart = new Chart(elChart.getContext('2d'), {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: dsLabelRx,
              data: rxSeries,
              fill: false,
              tension: 0.2,
              borderColor: '#4caf50',
            },
            {
              label: dsLabelTx,
              data: txSeries,
              fill: false,
              tension: 0.2,
              borderColor: '#f44336',
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
    elLoad.textContent = 'Загрузка...';

    try {
      const url = `/api/bw?iface=${encodeURIComponent(
        currentIface,
      )}&range=${encodeURIComponent(currentRange)}`;
      const res = await fetch(url, { cache: 'no-store' });
      const data = await res.json();
      if (!data || !data.labels) throw new Error('Bad payload');

      // Обновление отображаемого интерфейса в шапке
      elIface.textContent = data.iface || '—';
      elNetIf.textContent = data.iface || '—';

      // Извлечение массивов меток и рядов скоростей
      const labels = data.labels || [];
      const rx_mbps = data.rx_mbps || [];
      const tx_mbps = data.tx_mbps || [];
      const apiInterval = data.interval;

      // Ветвление по режиму: «за 1 день» показываем скорость, иначе — суточные объёмы
      if (currentRange === '1d') {
        // Подготовка рядов скорости в МБ/с и обновление карточек текущей нагрузки
        const rxMBps = rx_mbps.map((v) => (Number(v) || 0) / 8);
        const txMBps = tx_mbps.map((v) => (Number(v) || 0) / 8);
        const lastRx = rxMBps.at(-1) || 0;
        const lastTx = txMBps.at(-1) || 0;

        elRx.textContent = `${fmtRateMBps(lastRx)} МБ/с`;
        elTx.textContent = `${fmtRateMBps(lastTx)} МБ/с`;
        elLoad.textContent = `Текущая нагрузка: Rx ${fmtRateMBps(
          lastRx,
        )} МБ/с, Tx ${fmtRateMBps(
          lastTx,
        )} МБ/с (${currentRange}, ${currentIface})`;

        // Построение графика скорости
        buildOrUpdateChart({
          labels,
          rxSeries: rxMBps,
          txSeries: txMBps,
          mode: 'rate',
        });
      } else {
        // Определение длительности точки и агрегация скоростей в суточные объёмы
        const secPerPoint = detectSecPerPoint(
          labels,
          apiInterval,
          currentRange,
        );
        const daily = aggregateDaily(labels, rx_mbps, tx_mbps, secPerPoint);

        // Отображение текущей скорости в карточках при режимах 7/30 дней
        const lastRxMBps = (Number(rx_mbps.at(-1)) || 0) / 8;
        const lastTxMBps = (Number(tx_mbps.at(-1)) || 0) / 8;
        elRx.textContent = `${fmtRateMBps(lastRxMBps)} МБ/с`;
        elTx.textContent = `${fmtRateMBps(lastTxMBps)} МБ/с`;
        elLoad.textContent = `Режим: суточные объёмы. Последняя скорость: Rx ${fmtRateMBps(
          lastRxMBps,
        )} МБ/с, Tx ${fmtRateMBps(
          lastTxMBps,
        )} МБ/с (${currentRange}, ${currentIface})`;

        // Построение графика суточных объёмов
        buildOrUpdateChart({
          labels: daily.labels,
          rxSeries: daily.rxMBarr,
          txSeries: daily.txMBarr,
          mode: 'daily',
        });

        // Диагностический вывод соответствия сумм графика и бэкенда
        const rxSumMB = daily.rxMBarr.reduce((a, b) => a + b, 0);
        const txSumMB = daily.txMBarr.reduce((a, b) => a + b, 0);
        const totals = data.totals?.[currentRange];
        const rxTotalBackend = totals ? totals.rx_bytes / 1024 / 1024 : null;
        const txTotalBackend = totals ? totals.tx_bytes / 1024 / 1024 : null;
        console.log(
          `[check] ${currentRange}: chartSum=`,
          fmtMBGBTBFromMB(rxSumMB),
          '+',
          fmtMBGBTBFromMB(txSumMB),
          'backend=',
          totals
            ? fmtMBGBTBFromMB(rxTotalBackend) +
                ' + ' +
                fmtMBGBTBFromMB(txTotalBackend)
            : 'n/a',
          'secPerPoint=',
          secPerPoint,
        );
      }

      // Карта строк для подписей периодов
      const PERIOD_LABEL = {
        '1d': 'за 1 день',
        '7d': 'за 7 дней',
        '30d': 'за 30 дней',
      };

      // Вспомогательная функция вывода суммарной статистики в карточки
      function setStatText(id, periodKey, bytes) {
        const el = document.getElementById(id);
        if (!el) return;
        if (bytes == null) {
          el.textContent = `— ${PERIOD_LABEL[periodKey]}`;
          return;
        }
        el.innerHTML = `<span class="bw-k">${
          PERIOD_LABEL[periodKey]
        }:</span> <span class="bw-v">${fmtMBGBTBFromBytes(bytes)}</span>`;
      }

      // Обновление карточек итогов по данным от бэкенда или показ «—», если totals нет
      if (data.totals) {
        const t1 = data.totals['1d'];
        const t7 = data.totals['7d'];
        const t30 = data.totals['30d'];

        // Обновление карточек Rx
        setStatText('bw-rx-1d', '1d', t1?.rx_bytes);
        setStatText('bw-rx-7d', '7d', t7?.rx_bytes);
        setStatText('bw-rx-30d', '30d', t30?.rx_bytes);

        // Обновление карточек Tx
        setStatText('bw-tx-1d', '1d', t1?.tx_bytes);
        setStatText('bw-tx-7d', '7d', t7?.tx_bytes);
        setStatText('bw-tx-30d', '30d', t30?.tx_bytes);

        // Обновление карточек Total
        setStatText('bw-total-1d', '1d', t1?.total_bytes);
        setStatText('bw-total-7d', '7d', t7?.total_bytes);
        setStatText('bw-total-30d', '30d', t30?.total_bytes);
      } else {
        // Заполнение карточек прочерками, если totals отсутствуют
        ['rx', 'tx', 'total'].forEach((kind) => {
          ['1d', '7d', '30d'].forEach((p) =>
            setStatText(`bw-${kind}-${p}`, p, null),
          );
        });
      }
    } catch (e) {
      // Обработка ошибок загрузки/парсинга ответа API
      console.error('Ошибка /api/bw:', e);
      elLoad.textContent = 'Ошибка загрузки данных vnStat.';
    }
  }

  // Обработчик кликов по кнопкам диапазона (смена периода и перезагрузка данных)
  rangeBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      currentRange = btn.dataset.range;
      localStorage.setItem('bw_range', currentRange);
      loadData();
    });
  });

  // Обработчик кликов по кнопкам интерфейса (смена NIC и перезагрузка данных)
  ifaceBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      currentIface = btn.dataset.iface;
      localStorage.setItem('bw_iface', currentIface);
      loadData();
    });
  });

  // Начальная инициализация состояния и первичная загрузка данных
  setActiveBtns();
  loadData();
});
