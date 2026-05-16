(function () {
    const fmt = window.LogsDashboardFmt || {};
    const theme = window.LogsDashboardChartTheme || {};
    const humanBytes = fmt.humanBytes || function (v) { return String(v || 0); };
    const formatTrafficChartLabels = fmt.formatTrafficChartLabels || function (d) { return (d && d.labels) || []; };
    const protocolMatches = fmt.protocolMatches || function () { return true; };
    const getThemeColor = theme.getThemeColor || function (_t, fb) { return fb; };
    const clientInput = document.getElementById('trafficClientSelect');
    const clientCombobox = document.getElementById('trafficClientCombobox');
    const clientClearButton = document.getElementById('trafficClientClear');
    const clientToggle = document.getElementById('trafficClientToggle');
    const clientDropdown = document.getElementById('trafficClientDropdown');
    const clientList = document.getElementById('trafficClientList');
    const trafficProtocolFilter = document.getElementById('trafficProtocolFilter');
    const rangeButtons = Array.from(document.querySelectorAll('.bw-range-btn'));
    const chartCanvas = document.getElementById('userTrafficRangeChart');
    const chartMeta = document.getElementById('trafficChartMeta');
    const storageClientKey = 'logs_dashboard_selected_client';
    const storageRangeKey = 'logs_dashboard_selected_range';
    const storageTrafficProtocolKey = 'logs_dashboard_traffic_protocol_filter';
    const storagePersistedOnlineOnlyKey = 'logs_dashboard_persisted_online_only';
    const chartPane = chartCanvas ? chartCanvas.closest('.logs-tab-pane') : null;
    const persistedTrafficTable = document.getElementById('persistedTrafficTable');
    const deletedPersistedTrafficTable = document.getElementById('deletedPersistedTrafficTable');
    const persistedTrafficOnlineOnlyToggle = document.getElementById('persistedTrafficOnlineOnlyToggle');

    if (!clientInput || !clientCombobox || !clientClearButton || !clientToggle || !clientDropdown || !clientList || !rangeButtons.length || !chartCanvas || !chartMeta || typeof Chart === 'undefined') {
        return;
    }

    const allClientOptionsMap = new Map();
    Array.from(clientList.options).forEach(option => {
        const value = String(option.value || '').trim();
        if (!value) {
            return;
        }

        const protocolTokens = String(option.getAttribute('data-client-protocols') || '')
            .toLowerCase()
            .split(',')
            .map(item => item.trim())
            .filter(Boolean);

        if (!allClientOptionsMap.has(value)) {
            allClientOptionsMap.set(value, new Set());
        }
        const merged = allClientOptionsMap.get(value);
        protocolTokens.forEach(token => merged.add(token));
    });

    const allClientOptions = Array.from(allClientOptionsMap.entries()).map(([value, tokens]) => ({
        value,
        protocols: Array.from(tokens).join(','),
    }));

    if (!allClientOptions.length) {
        chartMeta.textContent = 'Нет клиентов для построения графика';
        return;
    }

    const savedClient = localStorage.getItem(storageClientKey);
    let currentRange = localStorage.getItem(storageRangeKey) || '7d';
    let currentTrafficProtocol = localStorage.getItem(storageTrafficProtocolKey) || 'all';
    if (savedClient && allClientOptions.some(opt => opt.value === savedClient)) {
        clientInput.value = savedClient;
    }
    if (!rangeButtons.some(btn => btn.dataset.range === currentRange)) {
        currentRange = '7d';
    }
    if (currentTrafficProtocol !== 'all' && currentTrafficProtocol !== 'openvpn' && currentTrafficProtocol !== 'wireguard') {
        currentTrafficProtocol = 'all';
    }
    if (trafficProtocolFilter && Array.from(trafficProtocolFilter.options).some(opt => opt.value === currentTrafficProtocol)) {
        trafficProtocolFilter.value = currentTrafficProtocol;
    }

    let showPersistedOnlineOnly = localStorage.getItem(storagePersistedOnlineOnlyKey) === '1';
    if (persistedTrafficOnlineOnlyToggle) {
        persistedTrafficOnlineOnlyToggle.checked = showPersistedOnlineOnly;
    }

    function setActiveRangeButtons() {
        rangeButtons.forEach(btn => {
            const active = btn.dataset.range === currentRange;
            btn.classList.toggle('active', active);
            btn.disabled = active;
        });
    }

    let clientTrafficChart = null;
    let visibleClientOptions = allClientOptions.slice();
    let clientDropdownOpen = false;
    let isSelectingClientFromDropdown = false;
    let currentSelectedClient = savedClient && allClientOptions.some(opt => opt.value === savedClient)
        ? savedClient
        : allClientOptions[0].value;
    clientInput.value = currentSelectedClient;

    function updateClientClearButtonVisibility() {
        const hasValue = String(clientInput.value || '').trim().length > 0;
        clientClearButton.hidden = !hasValue;
    }

    updateClientClearButtonVisibility();

    function isChartPaneVisible() {
        return !chartPane || chartPane.classList.contains('is-active');
    }

    function optionMatchesTrafficProtocol(option, selectedProtocol) {
        if (!option) {
            return false;
        }
        const selected = String(selectedProtocol || 'all').toLowerCase();
        if (selected === 'all') {
            return true;
        }
        return protocolMatches(option.protocols || '', selected);
    }

    function findClientOptionByName(clientName, options) {
        const needle = String(clientName || '').trim().toLowerCase();
        if (!needle) {
            return null;
        }
        return (options || []).find(option => option.value.toLowerCase() === needle) || null;
    }

    function getFilteredVisibleClientOptions() {
        const needle = String(clientInput.value || '').trim().toLowerCase();
        if (!needle) {
            return visibleClientOptions.slice();
        }
        return visibleClientOptions.filter(option => option.value.toLowerCase().includes(needle));
    }

    function renderClientDropdown() {
        clientDropdown.innerHTML = '';
        const filtered = getFilteredVisibleClientOptions();

        if (!filtered.length) {
            const empty = document.createElement('div');
            empty.className = 'traffic-client-option-empty';
            empty.textContent = 'Совпадений не найдено';
            clientDropdown.appendChild(empty);
            return;
        }

        filtered.forEach(function (option) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'traffic-client-option';
            button.textContent = option.value;
            button.setAttribute('data-value', option.value);
            clientDropdown.appendChild(button);
        });
    }

    function openClientDropdown() {
        renderClientDropdown();
        clientDropdown.hidden = false;
        clientCombobox.classList.add('is-open');
        clientDropdownOpen = true;
    }

    function closeClientDropdown() {
        clientDropdown.hidden = true;
        clientCombobox.classList.remove('is-open');
        clientDropdownOpen = false;
    }

    function ensureClientSelection(options, preferredValue) {
        const list = Array.isArray(options) ? options : visibleClientOptions;
        if (!list.length) {
            return null;
        }

        const preferred = String(preferredValue || '').trim();
        const selected = findClientOptionByName(preferred || clientInput.value, list);
        if (selected) {
            currentSelectedClient = selected.value;
            return selected;
        }

        const typedValue = String(preferred || clientInput.value || '').trim().toLowerCase();
        if (typedValue) {
            const startsWithMatch = list.find(option => option.value.toLowerCase().startsWith(typedValue));
            if (startsWithMatch) {
                currentSelectedClient = startsWithMatch.value;
                clientInput.value = startsWithMatch.value;
                return startsWithMatch;
            }
            const containsMatch = list.find(option => option.value.toLowerCase().includes(typedValue));
            if (containsMatch) {
                currentSelectedClient = containsMatch.value;
                clientInput.value = containsMatch.value;
                return containsMatch;
            }
        }

        const selectedByState = findClientOptionByName(currentSelectedClient, list);
        if (selectedByState) {
            currentSelectedClient = selectedByState.value;
            clientInput.value = selectedByState.value;
            return selectedByState;
        }

        currentSelectedClient = list[0].value;
        clientInput.value = list[0].value;
        return list[0];
    }

    function applyTrafficProtocolFilter(forceSelection) {
        localStorage.setItem(storageTrafficProtocolKey, currentTrafficProtocol);

        visibleClientOptions = allClientOptions.filter(function (option) {
            return optionMatchesTrafficProtocol(option, currentTrafficProtocol);
        });
        if (clientDropdownOpen) {
            renderClientDropdown();
        }

        if (persistedTrafficTable) {
            persistedTrafficTable.querySelectorAll('tbody tr[data-total-bytes]').forEach(function (row) {
                const protocolVisible = protocolMatches(row.getAttribute('data-client-protocols') || '', currentTrafficProtocol);
                const isOnline = row.getAttribute('data-is-active') === '1';
                const onlineVisible = !showPersistedOnlineOnly || isOnline;
                const visible = protocolVisible && onlineVisible;
                row.style.display = visible ? '' : 'none';
            });
        }

        if (deletedPersistedTrafficTable) {
            deletedPersistedTrafficTable.querySelectorAll('tbody tr[data-total-bytes]').forEach(function (row) {
                const visible = protocolMatches(row.getAttribute('data-client-protocols') || '', currentTrafficProtocol);
                row.style.display = visible ? '' : 'none';
            });
        }

        if (!visibleClientOptions.length) {
            if (clientTrafficChart) {
                clientTrafficChart.destroy();
                clientTrafficChart = null;
            }
            currentSelectedClient = '';
            clientInput.value = '';
            updateClientClearButtonVisibility();
            closeClientDropdown();
            chartMeta.textContent = 'Нет клиентов для выбранного протокола';
            return false;
        }

        if (forceSelection !== false) {
            ensureClientSelection(visibleClientOptions, currentSelectedClient || clientInput.value);
        }

        return true;
    }

    async function loadClientChart(targetClient) {
        if (!applyTrafficProtocolFilter(false)) {
            return;
        }

        const selectedClient = ensureClientSelection(
            visibleClientOptions,
            targetClient || clientInput.value || currentSelectedClient
        );
        if (!selectedClient) {
            chartMeta.textContent = 'Нет клиентов для построения графика';
            return;
        }

        const client = selectedClient.value;
        currentSelectedClient = client;
        localStorage.setItem(storageClientKey, client);
        localStorage.setItem(storageRangeKey, currentRange);
        clientInput.value = client;
        updateClientClearButtonVisibility();
        closeClientDropdown();
        setActiveRangeButtons();

        try {
            const url = `/api/user-traffic-chart?client=${encodeURIComponent(client)}&range=${encodeURIComponent(currentRange)}&protocol=${encodeURIComponent(currentTrafficProtocol)}`;
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            if (data && data.client) {
                currentSelectedClient = String(data.client).trim() || client;
            }
            clientInput.value = currentSelectedClient;
            updateClientClearButtonVisibility();

            const labels = formatTrafficChartLabels(data);
            const openvpnData = (data.openvpn_bytes || data.vpn_bytes || []).map(v => Number(v || 0));
            const wireguardData = (data.wireguard_bytes || []).map(v => Number(v || 0));

            if (!labels.length) {
                labels.push('Нет данных');
                openvpnData.push(0);
                wireguardData.push(0);
            }

            if (clientTrafficChart) {
                clientTrafficChart.destroy();
            }

            clientTrafficChart = new Chart(chartCanvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        {
                            label: 'OpenVPN',
                            data: openvpnData,
                            borderColor: getThemeColor('--theme-chart-openvpn-border', '#4f8cff'),
                            backgroundColor: getThemeColor('--theme-chart-openvpn-fill', 'rgba(79,140,255,0.14)'),
                            borderWidth: 2,
                            fill: false,
                            tension: 0.2,
                        },
                        {
                            label: 'WireGuard',
                            data: wireguardData,
                            borderColor: getThemeColor('--theme-chart-wireguard-border', '#2fc27d'),
                            backgroundColor: getThemeColor('--theme-chart-wireguard-fill', 'rgba(47,194,125,0.14)'),
                            borderWidth: 2,
                            fill: false,
                            tension: 0.2,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        x: {
                            ticks: {
                                color: getThemeColor('--theme-chart-axis-x', '#bbb'),
                                autoSkip: true,
                                maxTicksLimit: currentRange === '1h' ? 12 : (currentRange === '24h' ? 24 : 10)
                            },
                            grid: { color: getThemeColor('--theme-chart-grid-soft', 'rgba(255,255,255,0.05)') }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: getThemeColor('--theme-chart-axis-y', '#ddd'),
                                callback: function (value) {
                                    return humanBytes(value);
                                }
                            },
                            grid: { color: getThemeColor('--theme-chart-grid-strong', 'rgba(255,255,255,0.1)') }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: getThemeColor('--theme-chart-legend', '#fff') }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    return `${ctx.dataset.label}: ${humanBytes(ctx.parsed.y)}`;
                                }
                            }
                        }
                    }
                }
            });

            chartMeta.textContent =
                `OpenVPN: ${data.total_openvpn_human || humanBytes(data.total_openvpn)} | ` +
                `WireGuard: ${data.total_wireguard_human || humanBytes(data.total_wireguard)} | ` +
                `Итого: ${data.total_human || humanBytes(data.total)}`;
        } catch (err) {
            chartMeta.textContent = `Не удалось загрузить график: ${err.message}`;
        }
    }

    clientInput.addEventListener('change', function () {
        if (isSelectingClientFromDropdown) {
            isSelectingClientFromDropdown = false;
            return;
        }
        const typedClient = String(clientInput.value || '').trim();
        updateClientClearButtonVisibility();
        if (!typedClient) {
            return;
        }
        loadClientChart(typedClient);
    });
    clientInput.addEventListener('focus', function () {
        openClientDropdown();
    });
    clientInput.addEventListener('keydown', function (event) {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            openClientDropdown();
            return;
        }
        if (event.key === 'Escape') {
            closeClientDropdown();
            return;
        }
        if (event.key === 'Enter') {
            event.preventDefault();
            const typedClient = String(clientInput.value || '').trim();
            if (!typedClient) {
                openClientDropdown();
                return;
            }
            loadClientChart(typedClient);
        }
    });
    clientInput.addEventListener('input', function () {
        updateClientClearButtonVisibility();
        openClientDropdown();
        if (!findClientOptionByName(clientInput.value, visibleClientOptions)) {
            chartMeta.textContent = 'Поиск клиента... выберите вариант из списка.';
        }
    });
    clientClearButton.addEventListener('click', function () {
        clientInput.value = '';
        updateClientClearButtonVisibility();
        openClientDropdown();
        clientInput.focus();
    });
    clientToggle.addEventListener('click', function () {
        if (clientDropdownOpen) {
            closeClientDropdown();
        } else {
            openClientDropdown();
            clientInput.focus();
        }
    });
    clientDropdown.addEventListener('mousedown', function (event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const selectedValue = target.getAttribute('data-value');
        if (!selectedValue) {
            return;
        }
        event.preventDefault();
        isSelectingClientFromDropdown = true;
        currentSelectedClient = selectedValue;
        clientInput.value = selectedValue;
        updateClientClearButtonVisibility();
        loadClientChart(selectedValue);
    });
    document.addEventListener('click', function (event) {
        const target = event.target;
        if (!(target instanceof Node)) {
            return;
        }
        if (clientCombobox.contains(target)) {
            return;
        }
        closeClientDropdown();
    });
    if (trafficProtocolFilter) {
        trafficProtocolFilter.addEventListener('change', function () {
            currentTrafficProtocol = String(trafficProtocolFilter.value || 'all').toLowerCase();
            loadClientChart(currentSelectedClient || clientInput.value);
        });
    }
    if (persistedTrafficOnlineOnlyToggle) {
        persistedTrafficOnlineOnlyToggle.addEventListener('change', function () {
            showPersistedOnlineOnly = !!persistedTrafficOnlineOnlyToggle.checked;
            localStorage.setItem(storagePersistedOnlineOnlyKey, showPersistedOnlineOnly ? '1' : '0');
            applyTrafficProtocolFilter(false);
        });
    }
    window.addEventListener('logsDashboardTrafficTablesUpdated', function () {
        if (fmt.formatLocalDateTimeCells) {
            fmt.formatLocalDateTimeCells();
        }
        applyTrafficProtocolFilter(false);
    });
    rangeButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            currentRange = btn.dataset.range || '7d';
            loadClientChart(currentSelectedClient || clientInput.value);
        });
    });

    window.addEventListener('logsDashboardTabActivated', function (event) {
        if ((event?.detail?.tab || '') === 'traffic') {
            loadClientChart();
        }
    });

    setActiveRangeButtons();
    applyTrafficProtocolFilter(true);
    if (isChartPaneVisible()) {
        loadClientChart(currentSelectedClient || clientInput.value);
    } else {
        chartMeta.textContent = 'Откройте вкладку "Трафик (БД)", чтобы загрузить график.';
    }
})();
