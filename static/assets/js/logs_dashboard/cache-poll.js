(function () {
    const taskId = (window.__logsDashboardBootstrap || {}).refreshTaskId;
    if (!taskId) {
        return;
    }

    const statusUrl = `/api/logs_dashboard_refresh_status/${encodeURIComponent(taskId)}`;
    const pollIntervalMs = 3000;
    const maxPollMs = 10 * 60 * 1000;
    const pollStartedAt = Date.now();
    let stopPolling = false;

    async function pollRefreshStatus() {
        if (stopPolling) {
            return;
        }

        if (Date.now() - pollStartedAt > maxPollMs) {
            window.location.reload();
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
                window.showNotification?.(
                    payload.error || 'Не удалось обновить кэш dashboard',
                    'error'
                );
                window.setTimeout(() => window.location.reload(), 1500);
                return;
            }
        } catch (err) {
            window.showNotification?.('Не удалось проверить статус обновления логов', 'error');
        }

        window.setTimeout(pollRefreshStatus, pollIntervalMs);
    }

    pollRefreshStatus();
})();
