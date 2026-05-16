(function () {
    const taskId = (window.__logsDashboardBootstrap || {}).refreshTaskId;
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
