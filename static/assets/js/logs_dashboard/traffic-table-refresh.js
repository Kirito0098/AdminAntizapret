(function () {
    const refreshIntervalMs = 60000;
    const trafficPaneSelector = '.logs-tab-pane[data-tab-pane="traffic"]';
    const clientsPaneSelector = '.logs-tab-pane[data-tab-pane="clients"]';
    const trafficTableSelectors = ['#persistedTrafficTable', '#deletedPersistedTrafficTable'];
    const clientCardsListSelector = '#clientCardsList';

    function isPaneActive(selector) {
        const pane = document.querySelector(selector);
        return pane && pane.classList.contains('is-active');
    }

    function isTrafficPaneActive() {
        const trafficPane = document.querySelector(trafficPaneSelector);
        return !trafficPane || trafficPane.classList.contains('is-active');
    }

    async function refreshDashboardFragments() {
        if (document.visibilityState !== 'visible') {
            return;
        }

        const refreshTraffic = isTrafficPaneActive();
        const refreshClients = isPaneActive(clientsPaneSelector);
        if (!refreshTraffic && !refreshClients) {
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
            let trafficUpdated = false;
            let clientsUpdated = false;

            if (refreshTraffic) {
                trafficTableSelectors.forEach(function (selector) {
                    const currentTbody = document.querySelector(`${selector} tbody`);
                    const nextTbody = nextDocument.querySelector(`${selector} tbody`);
                    if (!currentTbody || !nextTbody) {
                        return;
                    }
                    currentTbody.innerHTML = nextTbody.innerHTML;
                    trafficUpdated = true;
                });
            }

            if (refreshClients) {
                const currentList = document.querySelector(clientCardsListSelector);
                const nextList = nextDocument.querySelector(clientCardsListSelector);
                if (currentList && nextList) {
                    currentList.innerHTML = nextList.innerHTML;
                    clientsUpdated = true;
                }
            }

            if (trafficUpdated) {
                window.dispatchEvent(new CustomEvent('logsDashboardTrafficTablesUpdated'));
            }
            if (clientsUpdated) {
                window.dispatchEvent(new CustomEvent('logsDashboardClientCardsUpdated'));
            }
        } catch (err) {
            if (refreshTraffic) {
                window.showNotification?.('Не удалось обновить таблицы трафика', 'error');
            } else if (refreshClients) {
                window.showNotification?.('Не удалось обновить список клиентов', 'error');
            }
        }
    }

    setInterval(refreshDashboardFragments, refreshIntervalMs);
})();
