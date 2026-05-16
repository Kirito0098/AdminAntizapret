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
            window.showNotification?.('Не удалось обновить таблицы трафика', 'error');
        }
    }

    setInterval(function () {
        refreshTrafficTables();
    }, refreshIntervalMs);
})();
