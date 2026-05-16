(function () {
    const logsBootstrap = window.__logsDashboardBootstrap || {};
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

    const theme = window.LogsDashboardChartTheme || {};
    const getThemeColor = theme.getThemeColor || function (_t, fb) { return fb; };
    const protocolPalette = theme.protocolPalette || {
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
