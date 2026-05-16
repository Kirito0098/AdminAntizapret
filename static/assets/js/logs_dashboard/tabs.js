const logsBootstrap = window.__logsDashboardBootstrap || {};

(function () {
    // Cache buster for stale dashboard script versions in aggressive browser caches.
    window.__logsDashboardClientScriptVersion = '2026-05-09-nav-tabs-sync-v1';
    const tabButtons = Array.from(document.querySelectorAll('.logs-tab-btn[data-tab-target]'));
    const tabPanes = Array.from(document.querySelectorAll('.logs-tab-pane[data-tab-pane]'));
    const navTabLinks = Array.from(document.querySelectorAll('.nav-sublink[data-logs-tab]'));
    const storageKey = 'logs_dashboard_active_tab';
    const validTabs = new Set(
        tabPanes
            .map(pane => pane.dataset.tabPane)
            .filter(Boolean)
    );

    if (!tabPanes.length) {
        return;
    }

    function normalizeTabName(rawTabName) {
        const nextName = String(rawTabName || '')
            .replace(/^#/, '')
            .trim()
            .toLowerCase();

        if (nextName === 'traffic-db' || nextName === 'traffic_db') {
            return 'traffic';
        }

        return nextName;
    }

    function getTabFromHash() {
        const tabFromHash = normalizeTabName(window.location.hash || '');
        return validTabs.has(tabFromHash) ? tabFromHash : '';
    }

    function syncNavTabLinks(tabName) {
        if (!navTabLinks.length) {
            return;
        }

        navTabLinks.forEach(link => {
            const isActive = normalizeTabName(link.dataset.logsTab) === tabName;
            link.classList.toggle('is-active', isActive);
        });
    }

    function updateHash(tabName) {
        const nextHash = `#${tabName}`;
        if (window.location.hash === nextHash) {
            return;
        }

        if (history.replaceState) {
            history.replaceState(null, '', nextHash);
            return;
        }

        window.location.hash = nextHash;
    }

    function activateTab(tabName, options = {}) {
        const shouldSyncHash = options.syncHash !== false;
        const normalizedTab = normalizeTabName(tabName);
        const nextTab = validTabs.has(normalizedTab) ? normalizedTab : 'overview';

        tabButtons.forEach(btn => {
            const isActive = btn.dataset.tabTarget === nextTab;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        tabPanes.forEach(pane => {
            pane.classList.toggle('is-active', pane.dataset.tabPane === nextTab);
        });

        syncNavTabLinks(nextTab);

        if (shouldSyncHash) {
            updateHash(nextTab);
        }

        localStorage.setItem(storageKey, nextTab);
        window.dispatchEvent(new CustomEvent('logsDashboardTabActivated', { detail: { tab: nextTab } }));
    }

    tabButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            activateTab(btn.dataset.tabTarget || 'overview');
        });
    });

    navTabLinks.forEach(link => {
        link.addEventListener('click', function (e) {
            const tabName = normalizeTabName(link.dataset.logsTab);
            if (validTabs.has(tabName)) {
                e.preventDefault();
                activateTab(tabName);
            }
        });
    });

    window.addEventListener('hashchange', function () {
        const tabFromHash = getTabFromHash();
        if (!tabFromHash) {
            return;
        }
        activateTab(tabFromHash, { syncHash: false });
    });

    const tabFromHash = getTabFromHash();
    const savedTab = normalizeTabName(localStorage.getItem(storageKey) || '');
    activateTab(tabFromHash || savedTab || 'overview', { syncHash: false });
})();
