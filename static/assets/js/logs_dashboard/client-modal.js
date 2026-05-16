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

    const theme = window.LogsDashboardChartTheme || {};
    const fmt = window.LogsDashboardFmt || {};
    const getThemeColor = theme.getThemeColor || function (_t, fb) { return fb; };
    const humanBytes = fmt.humanBytes || function (v) { return String(v || 0); };
    const formatTrafficChartLabels = fmt.formatTrafficChartLabels || function (d) { return (d && d.labels) || []; };

    if (!modalRangeButtons.some(btn => btn.dataset.range === currentModalRange)) {
        currentModalRange = '7d';
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
