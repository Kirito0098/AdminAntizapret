(function () {
    const hideStaleToggle = document.getElementById('hideStaleSessionsToggle');
    const clientsProtocolFilter = document.getElementById('clientsProtocolFilter');
    const hideStaleStorageKey = 'logs_dashboard_hide_stale_sessions';
    const clientsProtocolStorageKey = 'logs_dashboard_clients_protocol_filter';
    const fmt = window.LogsDashboardFmt || {};
    const protocolMatches = fmt.protocolMatches || function () { return true; };

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

    if (fmt.formatLocalDateTimeCells) {
        fmt.formatLocalDateTimeCells();
    }
})();
