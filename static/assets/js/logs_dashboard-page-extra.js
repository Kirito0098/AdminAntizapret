const logsBootstrap = window.__logsDashboardBootstrap || {};

(function () {
    // Cache buster for stale dashboard script versions in aggressive browser caches.
    window.__logsDashboardClientScriptVersion = '2026-04-03-client-sync-v2';
    const tabButtons = Array.from(document.querySelectorAll('.logs-tab-btn[data-tab-target]'));
    const tabPanes = Array.from(document.querySelectorAll('.logs-tab-pane[data-tab-pane]'));
    const storageKey = 'logs_dashboard_active_tab';

    if (!tabButtons.length || !tabPanes.length) {
        return;
    }

    function activateTab(tabName) {
        const hasPane = tabPanes.some(p => p.dataset.tabPane === tabName);
        const nextTab = hasPane ? tabName : 'overview';

        tabButtons.forEach(btn => {
            const isActive = btn.dataset.tabTarget === nextTab;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        tabPanes.forEach(pane => {
            pane.classList.toggle('is-active', pane.dataset.tabPane === nextTab);
        });

        localStorage.setItem(storageKey, nextTab);
        window.dispatchEvent(new CustomEvent('logsDashboardTabActivated', { detail: { tab: nextTab } }));
    }

    tabButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            activateTab(btn.dataset.tabTarget || 'overview');
        });
    });

    const savedTab = localStorage.getItem(storageKey) || 'overview';
    activateTab(savedTab);
})();

(function () {
    if (!logsBootstrap.openvpnLoggingEnabled) {
        return;
    }

    const groupedStatusRows = Array.isArray(logsBootstrap.groupedStatusRows)
        ? logsBootstrap.groupedStatusRows
        : [];
    const connectedClients = Array.isArray(logsBootstrap.connectedClients)
        ? logsBootstrap.connectedClients
        : [];
    const overviewSummary = logsBootstrap.overviewSummary || {};
    const overviewPane = document.querySelector('.logs-tab-pane[data-tab-pane="overview"]');

    const getThemeColor = (token, fallback) =>
        getComputedStyle(document.documentElement).getPropertyValue(token).trim() || fallback;

    const protocolPalette = {
        openvpnBg: getThemeColor('--theme-protocol-openvpn-bg', 'rgba(79, 140, 255, 0.82)'),
        openvpnBorder: getThemeColor('--theme-protocol-openvpn-border', 'rgba(79, 140, 255, 1)'),
        wireguardBg: getThemeColor('--theme-protocol-wireguard-bg', 'rgba(47, 194, 125, 0.82)'),
        wireguardBorder: getThemeColor('--theme-protocol-wireguard-border', 'rgba(47, 194, 125, 1)'),
    };

    const networkLabels = groupedStatusRows.map(item => item.network);
    const sessionsSeries = groupedStatusRows.map(item => Number(item.client_count || 0));

    const deviceCount = {};
    connectedClients.forEach(client => {
        const raw = String(client.device_types || '').trim();
        if (!raw || raw === '-' || raw === 'Не определено') {
            deviceCount['Не определено'] = (deviceCount['Не определено'] || 0) + 1;
            return;
        }
        raw.split(',').map(v => v.trim()).filter(Boolean).forEach(device => {
            deviceCount[device] = (deviceCount[device] || 0) + 1;
        });
    });

    const deviceLabels = Object.keys(deviceCount);
    const deviceValues = Object.values(deviceCount);

    function deviceColor(label) {
        const key = String(label || '').toLowerCase();
        if (key.includes('wireguard')) {
            return protocolPalette.wireguardBg;
        }
        if (key.includes('android')) {
            return getThemeColor('--theme-device-android-bg', 'rgba(201, 83, 112, 0.82)');
        }
        if (key.includes('ios') || key.includes('iphone') || key.includes('ipad')) {
            return getThemeColor('--theme-device-ios-bg', 'rgba(201, 167, 74, 0.82)');
        }
        if (key.includes('windows')) {
            return getThemeColor('--theme-device-windows-bg', 'rgba(87, 190, 189, 0.82)');
        }
        if (key.includes('mac')) {
            return getThemeColor('--theme-device-mac-bg', 'rgba(149, 125, 235, 0.82)');
        }
        if (key.includes('linux')) {
            return getThemeColor('--theme-device-linux-bg', 'rgba(86, 144, 228, 0.82)');
        }
        return getThemeColor('--theme-device-unknown-bg', 'rgba(201, 203, 207, 0.82)');
    }

    function deviceBorderColor(label) {
        const key = String(label || '').toLowerCase();
        if (key.includes('wireguard')) {
            return protocolPalette.wireguardBorder;
        }
        if (key.includes('android')) {
            return getThemeColor('--theme-device-android-border', 'rgba(201, 83, 112, 1)');
        }
        if (key.includes('ios') || key.includes('iphone') || key.includes('ipad')) {
            return getThemeColor('--theme-device-ios-border', 'rgba(201, 167, 74, 1)');
        }
        if (key.includes('windows')) {
            return getThemeColor('--theme-device-windows-border', 'rgba(87, 190, 189, 1)');
        }
        if (key.includes('mac')) {
            return getThemeColor('--theme-device-mac-border', 'rgba(149, 125, 235, 1)');
        }
        if (key.includes('linux')) {
            return getThemeColor('--theme-device-linux-border', 'rgba(86, 144, 228, 1)');
        }
        return getThemeColor('--theme-device-unknown-border', 'rgba(201, 203, 207, 1)');
    }

    const deviceBackgroundColors = deviceLabels.map(deviceColor);
    const deviceBorderColors = deviceLabels.map(deviceBorderColor);
    const protocolLabels = ['OpenVPN', 'WireGuard'];
    const protocolValues = [
        Number(overviewSummary?.total_openvpn_sessions || 0),
        Number(overviewSummary?.total_wireguard_sessions || 0)
    ];
    let overviewChartsReady = false;

    function initOverviewCharts() {
        if (overviewChartsReady) {
            return;
        }

        const sessionsCtx = document.getElementById('sessionsByNetworkChart');
        if (sessionsCtx) {
            new Chart(sessionsCtx, {
                type: 'doughnut',
                data: {
                    labels: networkLabels,
                    datasets: [{
                        data: sessionsSeries,
                        backgroundColor: [
                            getThemeColor('--theme-overview-cyan-bg', 'rgba(75, 192, 192, 0.78)'),
                            getThemeColor('--theme-overview-violet-bg', 'rgba(153, 102, 255, 0.78)')
                        ],
                        borderColor: [
                            getThemeColor('--theme-overview-cyan-border', 'rgba(75, 192, 192, 1)'),
                            getThemeColor('--theme-overview-violet-border', 'rgba(153, 102, 255, 1)')
                        ],
                        borderWidth: 1,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '52%',
                    animation: false,
                    layout: { padding: { top: 4, right: 4, bottom: 4, left: 4 } },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: getThemeColor('--theme-text-primary', '#e7fff7'),
                                boxWidth: 18,
                                padding: 12,
                                font: {
                                    family: 'Poppins, sans-serif',
                                    size: 12,
                                    weight: '600'
                                }
                            }
                        }
                    }
                }
            });
        }

        const devicesCtx = document.getElementById('devicesChart');
        if (devicesCtx) {
            new Chart(devicesCtx, {
                type: 'pie',
                data: {
                    labels: deviceLabels,
                    datasets: [{
                        data: deviceValues,
                        backgroundColor: deviceBackgroundColors,
                        borderColor: deviceBorderColors,
                        borderWidth: 1,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    layout: { padding: { top: 4, right: 4, bottom: 4, left: 4 } },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: getThemeColor('--theme-text-primary', '#e7fff7'),
                                boxWidth: 18,
                                padding: 12,
                                font: {
                                    family: 'Poppins, sans-serif',
                                    size: 12,
                                    weight: '600'
                                }
                            }
                        }
                    }
                }
            });
        }

        const protocolsCtx = document.getElementById('protocolsChart');
        if (protocolsCtx) {
            new Chart(protocolsCtx, {
                type: 'doughnut',
                data: {
                    labels: protocolLabels,
                    datasets: [{
                        data: protocolValues,
                        backgroundColor: [protocolPalette.openvpnBg, protocolPalette.wireguardBg],
                        borderColor: [protocolPalette.openvpnBorder, protocolPalette.wireguardBorder],
                        borderWidth: 1,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '52%',
                    animation: false,
                    layout: { padding: { top: 4, right: 4, bottom: 4, left: 4 } },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: getThemeColor('--theme-text-primary', '#e7fff7'),
                                boxWidth: 18,
                                padding: 12,
                                font: {
                                    family: 'Poppins, sans-serif',
                                    size: 12,
                                    weight: '600'
                                }
                            }
                        }
                    }
                }
            });
        }

        overviewChartsReady = true;
    }

    if (!overviewPane || overviewPane.classList.contains('is-active')) {
        initOverviewCharts();
    }

    window.addEventListener('logsDashboardTabActivated', function (event) {
        if ((event?.detail?.tab || '') === 'overview') {
            initOverviewCharts();
        }
    });

    const chartsGrid = document.getElementById('chartsGrid');
    const chartsToggle = document.getElementById('chartsToggle');
    const chartsStateKey = 'logs_dashboard_charts_collapsed';

    function setChartsCollapsed(collapsed) {
        if (!chartsGrid || !chartsToggle) {
            return;
        }
        chartsGrid.classList.toggle('is-collapsed', collapsed);
        chartsToggle.textContent = collapsed ? 'Развернуть' : 'Свернуть';
        localStorage.setItem(chartsStateKey, collapsed ? '1' : '0');
    }

    if (chartsGrid && chartsToggle) {
        const isCollapsed = localStorage.getItem(chartsStateKey) === '1';
        setChartsCollapsed(isCollapsed);
        chartsToggle.addEventListener('click', function () {
            setChartsCollapsed(!chartsGrid.classList.contains('is-collapsed'));
        });
    }
})();

(function () {
    const refreshIntervalMs = 60000;
    const trafficPaneSelector = '.logs-tab-pane[data-tab-pane="traffic"]';
    const trafficTableSelectors = ['#persistedTrafficTable', '#deletedPersistedTrafficTable'];

    function isTrafficPaneActive() {
        const trafficPane = document.querySelector(trafficPaneSelector);
        return !trafficPane || trafficPane.classList.contains('is-active');
    }

    async function refreshTrafficTables() {
        if (document.visibilityState !== 'visible' || !isTrafficPaneActive()) {
            return;
        }

        try {
            const response = await fetch(window.location.pathname + window.location.search, {
                cache: 'no-store',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const html = await response.text();
            const parser = new DOMParser();
            const nextDocument = parser.parseFromString(html, 'text/html');
            let hasUpdates = false;

            trafficTableSelectors.forEach(function (selector) {
                const currentTbody = document.querySelector(`${selector} tbody`);
                const nextTbody = nextDocument.querySelector(`${selector} tbody`);
                if (!currentTbody || !nextTbody) {
                    return;
                }
                currentTbody.innerHTML = nextTbody.innerHTML;
                hasUpdates = true;
            });

            if (hasUpdates) {
                window.dispatchEvent(new CustomEvent('logsDashboardTrafficTablesUpdated'));
            }
        } catch (err) {
            // Keep silent to avoid noisy UI if network hiccups occur.
        }
    }

    setInterval(function () {
        refreshTrafficTables();
    }, refreshIntervalMs);
})();

(function () {
    const taskId = logsBootstrap.refreshTaskId;
    if (!taskId) {
        return;
    }

    const statusUrl = `/api/logs_dashboard_refresh_status/${encodeURIComponent(taskId)}`;
    const pollIntervalMs = 3000;
    let stopPolling = false;

    async function pollRefreshStatus() {
        if (stopPolling) {
            return;
        }

        try {
            const response = await fetch(statusUrl, {
                cache: 'no-store',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const payload = await response.json();
            const status = String(payload.status || '').toLowerCase();

            if (status === 'completed') {
                window.location.reload();
                return;
            }

            if (status === 'failed') {
                stopPolling = true;
                return;
            }
        } catch (err) {
            // Оставляем штатный периодический reload как fallback.
        }

        window.setTimeout(pollRefreshStatus, pollIntervalMs);
    }

    pollRefreshStatus();
})();

(function () {
    const hideStaleToggle = document.getElementById('hideStaleSessionsToggle');
    const clientsProtocolFilter = document.getElementById('clientsProtocolFilter');
    const hideStaleStorageKey = 'logs_dashboard_hide_stale_sessions';
    const clientsProtocolStorageKey = 'logs_dashboard_clients_protocol_filter';

    function parseProtocolTokens(rawValue) {
        return String(rawValue || '')
            .toLowerCase()
            .split(',')
            .map(item => item.trim())
            .filter(Boolean);
    }

    function protocolMatches(rawValue, selectedProtocol) {
        const selected = String(selectedProtocol || 'all').toLowerCase();
        if (selected === 'all') {
            return true;
        }
        const tokens = parseProtocolTokens(rawValue);
        return tokens.includes(selected);
    }

    function getThemeColor(token, fallback) {
        const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
        return value || fallback;
    }

    function applyClientCardsFilters() {
        if (!hideStaleToggle && !clientsProtocolFilter) {
            return;
        }

        const hideStale = hideStaleToggle ? !!hideStaleToggle.checked : false;
        const selectedProtocol = clientsProtocolFilter ? String(clientsProtocolFilter.value || 'all').toLowerCase() : 'all';

        localStorage.setItem(hideStaleStorageKey, hideStale ? '1' : '0');
        localStorage.setItem(clientsProtocolStorageKey, selectedProtocol);

        document.querySelectorAll('.ip-device-list').forEach(function (list) {
            const items = Array.from(list.querySelectorAll('.ip-device-item[data-stale-candidate]'));
            let visibleCount = 0;

            items.forEach(function (item) {
                const isStale = item.getAttribute('data-stale-candidate') === '1';
                const shouldHide = hideStale && isStale;
                item.style.display = shouldHide ? 'none' : '';
                if (!shouldHide) {
                    visibleCount += 1;
                }
            });

            const emptyState = list.querySelector('.ip-device-empty-state');
            if (emptyState) {
                emptyState.style.display = visibleCount === 0 ? '' : 'none';
            }

            const clientCard = list.closest('[data-client-card]');
            if (clientCard) {
                const cardProtocols = clientCard.getAttribute('data-client-protocols') || '';
                const protocolVisible = protocolMatches(cardProtocols, selectedProtocol);
                const staleVisible = !(hideStale && visibleCount === 0);
                clientCard.classList.toggle('is-filtered-out', !(protocolVisible && staleVisible));
            }
        });
    }

    if (hideStaleToggle) {
        hideStaleToggle.checked = localStorage.getItem(hideStaleStorageKey) === '1';
        hideStaleToggle.addEventListener('change', applyClientCardsFilters);
    }

    if (clientsProtocolFilter) {
        const savedClientsProtocol = localStorage.getItem(clientsProtocolStorageKey) || 'all';
        if (Array.from(clientsProtocolFilter.options).some(opt => opt.value === savedClientsProtocol)) {
            clientsProtocolFilter.value = savedClientsProtocol;
        }
        clientsProtocolFilter.addEventListener('change', applyClientCardsFilters);
    }

    applyClientCardsFilters();

    function parseServerDateTime(rawValue) {
        const raw = String(rawValue || '').trim();
        if (!raw || raw === '-') {
            return null;
        }

        const utcLike = raw.replace(' ', 'T') + 'Z';
        const utcDate = new Date(utcLike);
        if (!Number.isNaN(utcDate.getTime())) {
            return utcDate;
        }

        const localLike = raw.replace(' ', 'T');
        const localDate = new Date(localLike);
        if (!Number.isNaN(localDate.getTime())) {
            return localDate;
        }

        return null;
    }

    const dtFormatter = new Intl.DateTimeFormat(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });

    function formatLocalDateTimeCells() {
        document.querySelectorAll('.local-datetime[data-datetime]').forEach(function (cell) {
            const raw = cell.getAttribute('data-datetime') || cell.textContent;
            const parsed = parseServerDateTime(raw);
            if (!parsed) {
                return;
            }
            cell.textContent = dtFormatter.format(parsed);
            cell.title = `UTC: ${String(raw).trim()}`;
        });
    }

    const trafficLabelFormatters = {
        minute5: new Intl.DateTimeFormat(undefined, {
            hour: '2-digit',
            minute: '2-digit'
        }),
        hour: new Intl.DateTimeFormat(undefined, {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        }),
        day: new Intl.DateTimeFormat(undefined, {
            day: '2-digit',
            month: '2-digit'
        }),
        month: new Intl.DateTimeFormat(undefined, {
            month: '2-digit',
            year: 'numeric'
        })
    };

    function formatTrafficChartLabels(data) {
        const labels = Array.isArray(data && data.labels) ? data.labels.slice() : [];
        const labelDatetimesUtc = Array.isArray(data && data.label_datetimes_utc)
            ? data.label_datetimes_utc
            : [];
        const bucket = String((data && data.bucket) || '').toLowerCase();
        const formatter = trafficLabelFormatters[bucket];

        if (!labels.length || labels.length !== labelDatetimesUtc.length || !formatter) {
            return labels;
        }

        return labels.map(function (fallbackLabel, index) {
            const parsed = new Date(labelDatetimesUtc[index]);
            if (Number.isNaN(parsed.getTime())) {
                return fallbackLabel;
            }
            return formatter.format(parsed);
        });
    }

    formatLocalDateTimeCells();

    function humanBytes(value) {
        let size = Number(value || 0);
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let idx = 0;
        while (size >= 1024 && idx < units.length - 1) {
            size /= 1024;
            idx += 1;
        }
        const precision = idx === 0 ? 0 : (size < 10 ? 2 : 1);
        return `${size.toFixed(precision)} ${units[idx]}`;
    }

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
        formatLocalDateTimeCells();
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

(function () {
    const modal = document.getElementById('clientDetailsModal');
    if (!modal) {
        return;
    }

    const modalTitle = document.getElementById('clientModalTitle');
    const modalSummary = document.getElementById('clientModalSummary');
    const modalConnections = document.getElementById('clientModalConnections');
    const modalTrafficMeta = document.getElementById('clientModalTrafficMeta');
    const modalChartCanvas = document.getElementById('clientModalTrafficChart');
    const modalRangeButtons = Array.from(document.querySelectorAll('.client-modal-range-btn[data-range]'));
    const cardButtons = Array.from(document.querySelectorAll('[data-client-card] [data-client-toggle]'));
    const hideStaleToggle = document.getElementById('hideStaleSessionsToggle');

    const modalRangeStorageKey = 'logs_dashboard_modal_selected_range';
    let currentClientName = '';
    let currentCard = null;
    let currentModalRange = localStorage.getItem(modalRangeStorageKey) || '7d';
    let modalChart = null;

    function getThemeColor(token, fallback) {
        const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
        return value || fallback;
    }

    if (!modalRangeButtons.some(btn => btn.dataset.range === currentModalRange)) {
        currentModalRange = '7d';
    }

    function humanBytes(value) {
        let size = Number(value || 0);
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let idx = 0;
        while (size >= 1024 && idx < units.length - 1) {
            size /= 1024;
            idx += 1;
        }
        const precision = idx === 0 ? 0 : (size < 10 ? 2 : 1);
        return `${size.toFixed(precision)} ${units[idx]}`;
    }

    const trafficLabelFormatters = {
        minute5: new Intl.DateTimeFormat(undefined, {
            hour: '2-digit',
            minute: '2-digit'
        }),
        hour: new Intl.DateTimeFormat(undefined, {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        }),
        day: new Intl.DateTimeFormat(undefined, {
            day: '2-digit',
            month: '2-digit'
        }),
        month: new Intl.DateTimeFormat(undefined, {
            month: '2-digit',
            year: 'numeric'
        })
    };

    function formatTrafficChartLabels(data) {
        const labels = Array.isArray(data && data.labels) ? data.labels.slice() : [];
        const labelDatetimesUtc = Array.isArray(data && data.label_datetimes_utc)
            ? data.label_datetimes_utc
            : [];
        const bucket = String((data && data.bucket) || '').toLowerCase();
        const formatter = trafficLabelFormatters[bucket];

        if (!labels.length || labels.length !== labelDatetimesUtc.length || !formatter) {
            return labels;
        }

        return labels.map(function (fallbackLabel, index) {
            const parsed = new Date(labelDatetimesUtc[index]);
            if (Number.isNaN(parsed.getTime())) {
                return fallbackLabel;
            }
            return formatter.format(parsed);
        });
    }

    function setModalOpen(isOpen) {
        if (isOpen) {
            modal.hidden = false;
            requestAnimationFrame(() => {
                modal.classList.add('is-open');
            });
        } else {
            modal.classList.remove('is-open');
            setTimeout(() => {
                modal.hidden = true;
            }, 180);
        }
        document.body.classList.toggle('client-modal-open', isOpen);
    }

    function closeModal() {
        setModalOpen(false);
    }

    function syncModalConnectionsFromCurrentCard() {
        if (!modalConnections) {
            return;
        }
        const body = currentCard ? currentCard.querySelector('[data-client-body]') : null;
        modalConnections.innerHTML = body ? body.innerHTML : '<div class="client-card-empty">Нет данных по подключениям</div>';
    }

    function setActiveModalRangeButtons() {
        modalRangeButtons.forEach(btn => {
            const active = btn.dataset.range === currentModalRange;
            btn.classList.toggle('active', active);
            btn.disabled = active;
        });
    }

    async function loadClientModalChart() {
        if (!currentClientName || !modalChartCanvas || !modalTrafficMeta) {
            return;
        }

        if (typeof Chart === 'undefined') {
            modalTrafficMeta.textContent = 'График недоступен: Chart.js не загружен';
            return;
        }

        modalTrafficMeta.textContent = 'Загрузка...';

        try {
            const url = `/api/user-traffic-chart?client=${encodeURIComponent(currentClientName)}&range=${encodeURIComponent(currentModalRange)}&protocol=all`;
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            const labels = formatTrafficChartLabels(data);
            const openvpnData = (data.openvpn_bytes || data.vpn_bytes || []).map(v => Number(v || 0));
            const wireguardData = (data.wireguard_bytes || []).map(v => Number(v || 0));

            if (!labels.length) {
                labels.push('Нет данных');
                openvpnData.push(0);
                wireguardData.push(0);
            }

            if (modalChart) {
                modalChart.destroy();
            }

            modalChart = new Chart(modalChartCanvas, {
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
                                maxTicksLimit: currentModalRange === '1h' ? 12 : (currentModalRange === '24h' ? 24 : 10)
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

            modalTrafficMeta.textContent =
                `OpenVPN: ${data.total_openvpn_human || humanBytes(data.total_openvpn)} | ` +
                `WireGuard: ${data.total_wireguard_human || humanBytes(data.total_wireguard)} | ` +
                `Итого: ${data.total_human || humanBytes(data.total)}`;
        } catch (err) {
            modalTrafficMeta.textContent = `Не удалось загрузить график: ${err.message}`;
        }
    }

    function openClientModal(card) {
        if (!card) {
            return;
        }

        currentCard = card;

        currentClientName = String(card.getAttribute('data-client-name') || '').trim();
        const sessions = String(card.getAttribute('data-client-sessions') || '-').trim();
        const profiles = String(card.getAttribute('data-client-profiles') || '-').trim();
        const rx = String(card.getAttribute('data-client-rx') || '-').trim();
        const tx = String(card.getAttribute('data-client-tx') || '-').trim();
        const total = String(card.getAttribute('data-client-total') || '-').trim();

        if (modalTitle) {
            modalTitle.textContent = currentClientName || 'Клиент';
        }
        if (modalSummary) {
            modalSummary.textContent = `Сессий: ${sessions} | Профили: ${profiles} | Rx: ${rx} | Tx: ${tx} | Итого: ${total}`;
        }

        syncModalConnectionsFromCurrentCard();

        setActiveModalRangeButtons();
        setModalOpen(true);
        loadClientModalChart();
    }

    modalRangeButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            currentModalRange = btn.dataset.range || '7d';
            localStorage.setItem(modalRangeStorageKey, currentModalRange);
            setActiveModalRangeButtons();
            loadClientModalChart();
        });
    });

    cardButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const card = btn.closest('[data-client-card]');
            openClientModal(card);
        });
    });

    modal.querySelectorAll('[data-client-modal-close]').forEach(node => {
        node.addEventListener('click', closeModal);
    });

    if (hideStaleToggle) {
        hideStaleToggle.addEventListener('change', function () {
            if (modal.hidden) {
                return;
            }
            window.setTimeout(syncModalConnectionsFromCurrentCard, 0);
        });
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !modal.hidden) {
            closeModal();
        }
    });
})();

(function () {
    const table = document.getElementById('persistedTrafficTable');
    const sortBtn = document.getElementById('sortByTotalTraffic');
    if (!table || !sortBtn) {
        return;
    }

    const tbody = table.querySelector('tbody');
    if (!tbody) {
        return;
    }

    let isDesc = true;

    function sortRows() {
        const rows = Array.from(tbody.querySelectorAll('tr[data-total-bytes]'));
        rows.sort(function (a, b) {
            const aVal = Number(a.getAttribute('data-total-bytes') || 0);
            const bVal = Number(b.getAttribute('data-total-bytes') || 0);
            return isDesc ? (bVal - aVal) : (aVal - bVal);
        });

        rows.forEach(function (row) {
            tbody.appendChild(row);
        });

        sortBtn.textContent = isDesc ? 'По убыванию' : 'По возрастанию';
    }

    sortBtn.addEventListener('click', function () {
        isDesc = !isDesc;
        sortRows();
    });

    sortRows();
})();

