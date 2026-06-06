// ============ INITIALIZATION ============
document.addEventListener('DOMContentLoaded', function () {
    initializeUI();
    initializeFormLogic();
    initializeAddClientModal();
    initializeTabSwitching();
    initializeSearch();
    initializeFiltering();
    initializeTableSorting();
    initializeOpenVpnGroupSwitching();
    initializeQRButtons();
    initializeOneTimeLinkButtons();
    initializeClientBanToggles();
    initializeClientDetailsModal();
});

let currentTab = 'openvpn';
let currentFilter = 'all';
let sortColumn = 'name';
let sortOrder = 'asc';
let clientExpiry = {};

function getThemeColor(token, fallback) {
    const bodyValue = document.body
        ? getComputedStyle(document.body).getPropertyValue(token).trim()
        : '';

    if (bodyValue) {
        return bodyValue;
    }

    const rootValue = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
    return rootValue || fallback;
}

// Extract cert expiry data from HTML on load
function extractCertExpiryData() {
    clientExpiry = {};
    const rows = document.querySelectorAll('.client-row');
    rows.forEach(row => {
        const clientName = row.getAttribute('data-client-name');
        if (!clientName) return;

        syncClientBlockedBadge(row);
        syncClientAccessMeta(row);

        const certState = row.dataset.certState || 'active';
        const certDays = Number.parseInt(row.dataset.certDays || '999', 10);
        clientExpiry[clientName] = {
            status: certState,
            days: Number.isNaN(certDays) ? 999 : certDays,
        };
    });
}

function syncClientBlockedBadge(row) {
    if (!row) {
        return;
    }

    const badge = row.querySelector('.client-block-badge');
    if (!badge) {
        return;
    }

    const isBlocked = row.dataset.blocked === '1';
    badge.textContent = isBlocked ? 'Заблокирован' : 'Активный';
    badge.classList.toggle('is-blocked', isBlocked);
    badge.classList.toggle('is-active', !isBlocked);
}

function parseNullableInt(value) {
    const raw = String(value ?? '').trim();
    if (!raw || !/^-?\d+$/.test(raw)) {
        return null;
    }
    const parsed = Number.parseInt(raw, 10);
    return Number.isNaN(parsed) ? null : parsed;
}

function parseAccessExpiresAt(value) {
    const raw = String(value ?? '').trim();
    if (!raw) {
        return null;
    }
    const normalized = raw.endsWith(' UTC')
        ? `${raw.slice(0, -4).replace(' ', 'T')}Z`
        : `${raw.replace(' ', 'T')}Z`;
    const parsed = Date.parse(normalized);
    if (Number.isNaN(parsed)) {
        return null;
    }
    return new Date(parsed);
}

function formatAccessRemaining(accessExpiresAt) {
    const expiresAt = parseAccessExpiresAt(accessExpiresAt);
    if (!expiresAt) {
        return null;
    }

    const nowMs = Date.now();
    const totalSeconds = Math.floor((expiresAt.getTime() - nowMs) / 1000);
    if (totalSeconds <= 0) {
        return 'срок истёк';
    }

    const days = Math.floor(totalSeconds / 86400);
    if (days >= 1) {
        return `${days} дн.`;
    }

    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    if (hours > 0 && minutes > 0) {
        return `${hours} ч. ${minutes} мин.`;
    }
    if (hours > 0) {
        return `${hours} ч.`;
    }
    if (minutes > 0) {
        return `${minutes} мин.`;
    }
    return 'менее минуты';
}

window.parseAccessExpiresAt = parseAccessExpiresAt;
window.formatAccessRemaining = formatAccessRemaining;

function setRowDatasetValue(row, key, value) {
    if (!row || !key) {
        return;
    }
    if (value === null || value === undefined || value === '') {
        delete row.dataset[key];
        return;
    }
    row.dataset[key] = String(value);
}

function syncClientAccessMeta(row) {
    if (!row) {
        return;
    }

    const metaNode = row.querySelector('.client-cert-meta');
    if (!metaNode) {
        return;
    }

    const clientName = row.dataset.clientName || '-';
    const accessExpiresAt = row.dataset.accessExpiresAt || '';
    const blockMode = (row.dataset.blockMode || 'none').toLowerCase();
    const blockedUntil = row.dataset.blockedUntil || '';
    const blockedDaysLeft = parseNullableInt(row.dataset.blockedDaysLeft);
    const blockDurationDays = parseNullableInt(row.dataset.blockDurationDays);
    const certState = (row.dataset.certState || 'active').toLowerCase();
    const trafficLimitHuman = row.dataset.trafficLimitHuman || '';
    const trafficLimitPeriodLabel = row.dataset.trafficLimitPeriodLabel || '';
    const trafficConsumedHuman = row.dataset.trafficConsumedHuman || '';
    const trafficBytesLeftHuman = row.dataset.trafficBytesLeftHuman || '';
    const trafficLimitExceeded = row.dataset.trafficLimitExceeded === '1';
    const trafficLimitUnblockLabel = row.dataset.trafficLimitUnblockLabel || '';

    const lines = [];
    lines.push(`Отключение: ${accessExpiresAt ? accessExpiresAt.split(' ')[0] : 'не ограничено'}`);
    const accessRemainingText = formatAccessRemaining(accessExpiresAt);
    lines.push(`Осталось: ${accessRemainingText || 'неизвестно'}`);

    if (trafficLimitHuman) {
        let trafficLine = `Лимит трафика: ${trafficLimitHuman}`;
        if (trafficLimitPeriodLabel) {
            trafficLine += ` / ${trafficLimitPeriodLabel}`;
        }
        trafficLine += ` (использовано ${trafficConsumedHuman || '0 B'}`;
        if (trafficBytesLeftHuman) {
            trafficLine += `, осталось ${trafficBytesLeftHuman}`;
        }
        trafficLine += ')';
        if (trafficLimitExceeded) {
            trafficLine += ' — превышен';
        }
        lines.push(trafficLine);
    }

    if (blockMode === 'temp') {
        if (blockDurationDays !== null) {
            lines.push(`Блокировка: на ${blockDurationDays} дн.`);
        } else if (blockedDaysLeft !== null && blockedDaysLeft >= 0) {
            lines.push(`Блокировка: на ${blockedDaysLeft} дн.`);
        } else {
            lines.push('Блокировка: временная');
        }
        if (blockedUntil) {
            lines.push(`Разблокировка: ${blockedUntil.split(' ')[0]}`);
        }
    } else if (blockMode === 'traffic_limit' || (trafficLimitExceeded && trafficLimitHuman)) {
        let trafficBlockLine = 'Блокировка: превышен лимит трафика';
        if (trafficLimitHuman) {
            trafficBlockLine += ` (${trafficLimitHuman}`;
            if (trafficLimitPeriodLabel) {
                trafficBlockLine += ` / ${trafficLimitPeriodLabel}`;
            }
            trafficBlockLine += ')';
        }
        lines.push(trafficBlockLine);
        if (trafficLimitUnblockLabel) {
            lines.push(trafficLimitUnblockLabel);
        }
    } else if (blockMode === 'permanent') {
        lines.push('Блокировка: бессрочная (вручную)');
    } else if (blockMode === 'expired') {
        lines.push('Блокировка: до ручной разблокировки');
    } else {
        lines.push('Блокировка: нет');
    }

    const fragment = document.createDocumentFragment();
    lines.forEach((text) => {
        const lineNode = document.createElement('div');
        lineNode.textContent = text;
        fragment.appendChild(lineNode);
    });
    metaNode.replaceChildren(fragment);

    const forceExpired = blockMode === 'temp' || blockMode === 'permanent' || blockMode === 'expired' || blockMode === 'traffic_limit' || certState === 'expired';
    metaNode.classList.remove('active', 'expiring', 'expired');
    if (forceExpired) {
        metaNode.classList.add('expired');
    } else if (certState === 'expiring') {
        metaNode.classList.add('expiring');
    } else {
        metaNode.classList.add('active');
    }
}

function applyTrafficPayloadToRow(row, payload) {
    if (!row || !payload) {
        return;
    }
    setRowDatasetValue(row, 'trafficLimitBytes', payload.traffic_limit_bytes);
    setRowDatasetValue(row, 'trafficLimitPeriodDays', payload.traffic_limit_period_days);
    setRowDatasetValue(row, 'trafficLimitPeriodLabel', payload.traffic_limit_period_label || '');
    setRowDatasetValue(row, 'trafficLimitUnblockAt', payload.traffic_limit_unblock_at || '');
    setRowDatasetValue(row, 'trafficLimitUnblockLabel', payload.traffic_limit_unblock_label || '');
    setRowDatasetValue(row, 'trafficConsumedBytes', payload.traffic_consumed_bytes);
    setRowDatasetValue(row, 'trafficBytesLeft', payload.traffic_bytes_left);
    setRowDatasetValue(row, 'trafficLimitExceeded', payload.traffic_limit_exceeded ? '1' : '0');
    setRowDatasetValue(row, 'trafficLimitHuman', payload.traffic_limit_human || '');
    setRowDatasetValue(row, 'trafficConsumedHuman', payload.traffic_consumed_human || '');
    setRowDatasetValue(row, 'trafficBytesLeftHuman', payload.traffic_bytes_left_human || '');
}

function applyWgAccessPayloadToRow(row, payload) {
    if (!row || !payload) {
        return;
    }
    row.dataset.blocked = payload.is_blocked ? '1' : '0';
    setRowDatasetValue(row, 'blockMode', payload.block_mode || 'none');
    setRowDatasetValue(row, 'blockReason', payload.reason || '');
    setRowDatasetValue(row, 'accessExpiresAt', payload.expires_at || '');
    setRowDatasetValue(row, 'accessDaysLeft', payload.access_days_left);
    setRowDatasetValue(row, 'blockedUntil', payload.block_until || '');
    setRowDatasetValue(row, 'blockedDaysLeft', payload.blocked_days_left);
    setRowDatasetValue(row, 'blockDurationDays', payload.block_duration_days);
    setRowDatasetValue(row, 'wgBlockReason', payload.reason || '');
    setRowDatasetValue(row, 'wgExpiresAt', payload.expires_at || '');
    setRowDatasetValue(row, 'wgBlockUntil', payload.block_until || '');
    setRowDatasetValue(row, 'wgDaysLeft', payload.access_days_left);
    setRowDatasetValue(row, 'wgBlockedDaysLeft', payload.blocked_days_left);
    setRowDatasetValue(row, 'wgBlockMode', payload.block_mode || 'none');
    setRowDatasetValue(row, 'wgBlockDurationDays', payload.block_duration_days);
    applyTrafficPayloadToRow(row, payload);
    syncClientBlockedBadge(row);
    syncClientAccessMeta(row);
}

function applyWgAccessPayloadToClientRows(clientName, payload) {
    const name = String(clientName || '').trim();
    if (!name || !payload) {
        return;
    }
    const escapedName = (window.CSS && typeof window.CSS.escape === 'function')
        ? window.CSS.escape(name)
        : name.replace(/"/g, '\\"');
    const rows = document.querySelectorAll(`.client-row[data-client-name="${escapedName}"]`);
    rows.forEach((row) => {
        applyWgAccessPayloadToRow(row, payload);
    });
}

function applyOpenVpnAccessPayloadToRow(row, payload) {
    if (!row || !payload) {
        return;
    }
    row.dataset.blocked = payload.is_blocked ? '1' : '0';
    setRowDatasetValue(row, 'blockMode', payload.block_mode || 'none');
    setRowDatasetValue(row, 'blockReason', payload.reason || '');
    setRowDatasetValue(row, 'blockedUntil', payload.block_until || '');
    setRowDatasetValue(row, 'blockedDaysLeft', payload.blocked_days_left);
    setRowDatasetValue(row, 'blockDurationDays', payload.block_duration_days);
    applyTrafficPayloadToRow(row, payload);
    syncClientBlockedBadge(row);
    syncClientAccessMeta(row);
}

function applyOpenVpnAccessPayloadToClientRows(clientName, payload) {
    const name = String(clientName || '').trim();
    if (!name || !payload) {
        return;
    }
    const escapedName = (window.CSS && typeof window.CSS.escape === 'function')
        ? window.CSS.escape(name)
        : name.replace(/"/g, '\\"');
    const rows = document.querySelectorAll(`.config-table[data-protocol="openvpn"] .client-row[data-client-name="${escapedName}"]`);
    rows.forEach((row) => {
        applyOpenVpnAccessPayloadToRow(row, payload);
    });
}

window.syncClientAccessMeta = syncClientAccessMeta;
window.applyWgAccessPayloadToRow = applyWgAccessPayloadToRow;
window.applyWgAccessPayloadToClientRows = applyWgAccessPayloadToClientRows;
window.applyOpenVpnAccessPayloadToClientRows = applyOpenVpnAccessPayloadToClientRows;

// ============ UI INITIALIZATION ============
function initializeUI() {
    if (document.body) {
        document.body.classList.add('index-page-dark');
    }

    extractCertExpiryData();

    // Set first tab active
    document.querySelector('.tab-btn[data-protocol="openvpn"]').classList.add('active');
    document.querySelector('#openvpn-tab').classList.add('active');

    // Set "All" filter as active
    const allFilterButton = document.querySelector('[data-filter="all"]');
    if (allFilterButton) {
        allFilterButton.classList.add('active');
    }

    initializeIndexTrafficMiniSummary();
}

// ============ FORM LOGIC ============
function initializeFormLogic() {
    const optionInput = document.getElementById('option');
    const optionButtons = document.querySelectorAll('.add-client-option-btn[data-option]');
    const clientNameContainer = document.getElementById('client-name-container');
    const workTermContainer = document.getElementById('work-term-container');
    const clientSelectContainer = document.getElementById('client-select-container');
    const clientForm = document.getElementById('client-form');

    const updateFormByOption = (value) => {
        if (clientNameContainer) {
            clientNameContainer.style.display =
                (value === '1' || value === '4') ? 'flex' : 'none';
        }
        if (workTermContainer) {
            workTermContainer.style.display =
                (value === '1' || value === '4') ? 'flex' : 'none';
        }
        if (clientSelectContainer) {
            clientSelectContainer.style.display =
                (value === '2' || value === '5') ? 'flex' : 'none';
        }

        if (value === '2' || value === '5') {
            populateClientSelect(value);
        }
    };

    const setOptionValue = (value) => {
        if (!optionInput) {
            return;
        }

        optionInput.value = value;
        optionButtons.forEach(btn => {
            const isActive = btn.dataset.option === value;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
        updateFormByOption(value);
    };

    if (optionButtons.length) {
        optionButtons.forEach(btn => {
            if (btn.dataset.bound === '1') {
                return;
            }
            btn.dataset.bound = '1';
            btn.addEventListener('click', function () {
                setOptionValue(this.dataset.option || '');
            });
        });
    }

    if (optionInput) {
        optionInput.addEventListener('change', function () {
            updateFormByOption(this.value || '');
        });
        updateFormByOption(optionInput.value || '');
    }

    const clientSelect = document.getElementById('client-select');
    const clientNameInput = document.getElementById('client-name');
    if (clientSelect && clientNameInput) {
        clientSelect.addEventListener('change', function () {
            clientNameInput.value = this.value || '';
        });
    }

    if (clientForm) {
        clientForm.addEventListener('submit', function (e) {
            const option = document.getElementById('option').value;
            if (!option) {
                e.preventDefault();
                showNotification('Выберите действие', 'error');
                return false;
            }
        });
    }
}

function initializeAddClientModal() {
    const modal = document.getElementById('addClientModal');
    const openButton = document.getElementById('openAddClientModalBtn');
    const form = document.getElementById('client-form');

    if (!modal || !openButton) {
        return;
    }

    const setModalOpen = (isOpen) => {
        if (isOpen) {
            modal.hidden = false;
            requestAnimationFrame(() => {
                modal.classList.add('is-open');
            });
            document.body.classList.add('add-client-modal-open');
        } else {
            modal.classList.remove('is-open');
            setTimeout(() => {
                modal.hidden = true;
            }, 180);
            document.body.classList.remove('add-client-modal-open');
            if (form) {
                form.reset();
            }
        }
    };

    if (openButton.dataset.bound !== '1') {
        openButton.dataset.bound = '1';
        openButton.addEventListener('click', () => {
            setModalOpen(true);
        });
    }

    if (modal.dataset.bound === '1') {
        return;
    }
    modal.dataset.bound = '1';

    modal.querySelectorAll('[data-add-client-close]').forEach(node => {
        node.addEventListener('click', () => {
            setModalOpen(false);
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !modal.hidden) {
            setModalOpen(false);
        }
    });

    if (form) {
        form.addEventListener('reset', () => {
            const clientNameContainer = document.getElementById('client-name-container');
            const workTermContainer = document.getElementById('work-term-container');
            const clientSelectContainer = document.getElementById('client-select-container');
            const optionButtons = document.querySelectorAll('.add-client-option-btn[data-option]');
            const optionInput = document.getElementById('option');

            if (clientNameContainer) clientNameContainer.style.display = 'none';
            if (workTermContainer) workTermContainer.style.display = 'none';
            if (clientSelectContainer) clientSelectContainer.style.display = 'none';
            if (optionInput) optionInput.value = '';

            optionButtons.forEach(btn => {
                btn.classList.remove('active');
                btn.setAttribute('aria-pressed', 'false');
            });
        });
    }
}

function populateClientSelect(option) {
    const clientSelect = document.getElementById('client-select');
    const clientNameInput = document.getElementById('client-name');

    clientSelect.innerHTML = '<option value="">-- Выберите клиента --</option>';

    const tableSelectors = option === '2'
        ? ['.config-table[data-protocol="openvpn"]']
        : ['.config-table[data-protocol="amneziawg"]', '.config-table[data-protocol="wireguard"]'];

    const uniqueNames = new Set();
    tableSelectors.forEach(selector => {
        const table = document.querySelector(selector);
        if (!table) {
            return;
        }
        table.querySelectorAll('.client-row').forEach(row => {
            const name = row.getAttribute('data-client-name');
            if (name) {
                uniqueNames.add(name);
            }
        });
    });

    Array.from(uniqueNames).sort().forEach(clientName => {
        const opt = document.createElement('option');
        opt.value = clientName;
        opt.textContent = clientName;
        clientSelect.appendChild(opt);
    });

    if (clientNameInput) {
        clientNameInput.value = '';
    }
}

async function refreshMainContent() {
    const response = await fetch(window.location.pathname, {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const html = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    const newTabContent = doc.querySelector('.tab-content');
    const currentTabContent = document.querySelector('.tab-content');
    if (newTabContent && currentTabContent) {
        currentTabContent.innerHTML = newTabContent.innerHTML;
    }

    const newProtocolTabs = doc.querySelector('.protocol-tabs');
    const currentProtocolTabs = document.querySelector('.protocol-tabs');
    if (newProtocolTabs && currentProtocolTabs) {
        currentProtocolTabs.innerHTML = newProtocolTabs.innerHTML;
    }

    const newClientDetailsData = doc.querySelector('#index-client-details-data');
    const currentClientDetailsData = document.querySelector('#index-client-details-data');
    if (newClientDetailsData && currentClientDetailsData) {
        currentClientDetailsData.textContent = newClientDetailsData.textContent;
    }

    indexClientDetailsCache = null;
    indexClientDetailsFetchPromise = null;

    initializeTabSwitching();
    initializeAddClientModal();
    initializeTableSorting();
    initializeOpenVpnGroupSwitching();
    initializeQRButtons();
    initializeOneTimeLinkButtons();
    initializeClientBanToggles();
    initializeClientDetailsModal();

    switchTab(currentTab);

    const optionSelect = document.getElementById('option');
    if (optionSelect && (optionSelect.value === '2' || optionSelect.value === '5')) {
        populateClientSelect(optionSelect.value);
    }

    initializeIndexTrafficMiniSummary(true);
}

// ============ TAB SWITCHING ============
function initializeTabSwitching() {
    const tabButtons = document.querySelectorAll('.tab-btn');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const tabName = this.getAttribute('data-protocol');
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Remove active class from all tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });

    // Add active class to selected tab
    document.querySelector(`.tab-btn[data-protocol="${tabName}"]`).classList.add('active');

    const tabId = tabName === 'amneziawg' ? `${tabName}-tab` :
        tabName === 'wireguard' ? `${tabName}-tab` : `${tabName}-tab`;
    document.getElementById(tabId).classList.add('active');

    currentTab = tabName;
    filterTable();
}

// ============ SEARCH FUNCTIONALITY ============
function initializeSearch() {
    const searchInput = document.getElementById('search-clients');
    const clearBtn = document.getElementById('clear-search');

    if (searchInput) {
        searchInput.addEventListener('input', filterTable);
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', function () {
            searchInput.value = '';
            filterTable();
        });
    }
}

// ============ FILTERING ============
function initializeFiltering() {
    const filterBtns = document.querySelectorAll('.filter-btn');

    filterBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            // Remove active class from all filter buttons
            filterBtns.forEach(b => b.classList.remove('active'));

            // Add active class to selected filter
            this.classList.add('active');

            currentFilter = this.getAttribute('data-filter');
            filterTable();
        });
    });
}

function getFilterStatus(row) {
    if (row && row.dataset && row.dataset.certState) {
        return row.dataset.certState;
    }

    const badge = row.querySelector('.status-badge');
    if (!badge) return 'active';

    if (badge.classList.contains('expired')) return 'expired';
    if (badge.classList.contains('expiring')) return 'expiring';
    return 'active';
}

// ============ TABLE FILTERING & SEARCH ============
function filterTable() {
    const searchInput = document.getElementById('search-clients');
    const searchValue = searchInput ? searchInput.value.toLowerCase() : '';
    const table = document.querySelector(`.config-table[data-protocol="${currentTab}"]`);

    if (!table) return;

    const rows = table.querySelectorAll('.client-row');

    rows.forEach(row => {
        const clientName = row.getAttribute('data-client-name').toLowerCase();
        const matchSearch = clientName.includes(searchValue);

        let matchFilter = true;
        if (currentFilter !== 'all') {
            const status = getFilterStatus(row);
            matchFilter = (currentFilter === 'active' && status === 'active') ||
                (currentFilter === 'expiring' && status === 'expiring') ||
                (currentFilter === 'expired' && status === 'expired');
        }

        row.style.display = (matchSearch && matchFilter) ? '' : 'none';
    });
}

// ============ TABLE SORTING ============
function initializeTableSorting() {
    const headers = document.querySelectorAll('.config-table th.sortable');

    headers.forEach(header => {
        if (header.dataset.sortBound === '1') {
            return;
        }
        header.dataset.sortBound = '1';

        header.addEventListener('click', function () {
            const column = this.getAttribute('data-sort');
            const table = this.closest('.config-table');

            // Remove sort class from all headers in this table
            table.querySelectorAll('th.sortable').forEach(h => {
                h.classList.remove('sort-asc', 'sort-desc');
            });

            // Toggle sort order
            if (sortColumn === column) {
                sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                sortColumn = column;
                sortOrder = 'asc';
            }

            // Add sort class to current header
            this.classList.add(`sort-${sortOrder}`);

            sortTable(table, column, sortOrder);
        });
    });
}

function sortTable(table, column, order) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('.client-row'));

    rows.sort((a, b) => {
        let aValue, bValue;

        if (column === 'name') {
            aValue = a.getAttribute('data-client-name');
            bValue = b.getAttribute('data-client-name');
        } else if (column === 'status') {
            if (table.dataset.protocol === 'openvpn') {
                aValue = Number.parseInt(a.dataset.blocked || '0', 10);
                bValue = Number.parseInt(b.dataset.blocked || '0', 10);
            } else {
                const aStatus = getFilterStatus(a);
                const bStatus = getFilterStatus(b);
                const statusOrder = { 'active': 1, 'expiring': 2, 'expired': 3 };
                aValue = statusOrder[aStatus];
                bValue = statusOrder[bStatus];
            }
        }

        if (order === 'asc') {
            return aValue > bValue ? 1 : -1;
        } else {
            return aValue < bValue ? 1 : -1;
        }
    });

    tbody.innerHTML = '';
    rows.forEach(row => tbody.appendChild(row));
}

// ============ QR BUTTON FUNCTIONALITY ============
function initializeQRButtons() {
    const qrButtons = document.querySelectorAll('.vpn-qr-button');

    qrButtons.forEach(btn => {
        if (btn.dataset.qrBound === '1') {
            return;
        }
        btn.dataset.qrBound = '1';

        btn.addEventListener('click', function (e) {
            if (this.disabled) return;

            e.preventDefault();
            const configUrl = this.getAttribute('data-config');
            showQRModal(configUrl);
        });
    });
}

function initializeOpenVpnGroupSwitching() {
    const forms = document.querySelectorAll('.folder-group-buttons form[action*="set_openvpn_group"]');

    forms.forEach(form => {
        if (form.dataset.ajaxBound === '1') {
            return;
        }
        form.dataset.ajaxBound = '1';

        form.addEventListener('submit', async function (e) {
            e.preventDefault();

            const submitButton = form.querySelector('button[type="submit"]');
            const originalButtonText = submitButton ? submitButton.textContent : '';

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = '...';
            }

            try {
                const formData = new FormData(form);
                const response = await fetch(form.action, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const html = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newOpenVpnTab = doc.getElementById('openvpn-tab');
                const currentOpenVpnTab = document.getElementById('openvpn-tab');
                const newClientDetailsData = doc.querySelector('#index-client-details-data');
                const currentClientDetailsData = document.querySelector('#index-client-details-data');

                if (!newOpenVpnTab || !currentOpenVpnTab) {
                    throw new Error('OpenVPN tab content not found');
                }

                const wasOpenVpnActive = currentOpenVpnTab.classList.contains('active');
                currentOpenVpnTab.innerHTML = newOpenVpnTab.innerHTML;
                if (wasOpenVpnActive) {
                    currentOpenVpnTab.classList.add('active');
                }

                initializeOpenVpnGroupSwitching();
                initializeTableSorting();
                initializeQRButtons();
                initializeOneTimeLinkButtons();
                initializeClientBanToggles();
                initializeClientDetailsModal();

                if (newClientDetailsData && currentClientDetailsData) {
                    currentClientDetailsData.textContent = newClientDetailsData.textContent;
                }

                if (currentTab === 'openvpn') {
                    filterTable();
                }

                initializeIndexTrafficMiniSummary(true);

                showNotification('Группа OpenVPN обновлена', 'success');
            } catch (error) {
                console.error('OpenVPN group switch error:', error);
                showNotification('Не удалось обновить группу OpenVPN', 'error');
            } finally {
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = originalButtonText;
                }
            }
        });
    });
}

function initializeClientBanToggles() {
    const toggles = document.querySelectorAll('.client-ban-toggle');
    if (!toggles.length) {
        return;
    }

    toggles.forEach(toggle => {
        if (toggle.dataset.blockBound === '1') {
            return;
        }
        toggle.dataset.blockBound = '1';

        toggle.addEventListener('change', async function () {
            const checkbox = this;
            const row = checkbox.closest('.client-row');
            const clientName = checkbox.dataset.clientName || '';
            const shouldBlock = checkbox.checked;
            const previousState = !shouldBlock;

            if (!clientName) {
                checkbox.checked = previousState;
                showNotification('Не удалось определить CN клиента', 'error');
                return;
            }

            checkbox.disabled = true;

            try {
                const payload = await updateClientBlockState(clientName, shouldBlock);

                if (row) {
                    if (typeof window.applyOpenVpnAccessPayloadToClientRows === 'function') {
                        window.applyOpenVpnAccessPayloadToClientRows(clientName, payload);
                    } else {
                        row.dataset.blocked = payload.blocked ? '1' : '0';
                        syncClientBlockedBadge(row);
                    }
                }

                showNotification(payload.message || 'Статус блокировки обновлён', 'success');
            } catch (error) {
                checkbox.checked = previousState;
                showNotification(error.message || 'Не удалось изменить блокировку клиента', 'error');
            } finally {
                checkbox.disabled = false;
            }
        });
    });
}

async function updateClientBlockState(clientName, shouldBlock) {
    const csrfInput = document.getElementById('csrf-token-value');
    const csrfToken = csrfInput ? csrfInput.value : '';

    const formData = new FormData();
    formData.append('client_name', clientName);
    formData.append('blocked', shouldBlock ? '1' : '0');
    if (csrfToken) {
        formData.append('csrf_token', csrfToken);
    }

    const response = await fetch('/api/openvpn/client-block', {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        },
    });

    let payload = null;
    try {
        payload = await response.json();
    } catch (_e) {
        payload = null;
    }

    if (!response.ok || !payload || !payload.success) {
        const msg = payload && payload.message ? payload.message : `HTTP error! status: ${response.status}`;
        throw new Error(msg);
    }

    return payload;
}

function showQRModal(configUrl) {
    const modal = document.getElementById('modalQRContainer');
    const img = document.getElementById('qrImage');
    const qrContainer = modal ? modal.querySelector('.qr-code-container') : null;
    const qrInfo = document.getElementById('qrInfoMessage');
    const qrCopyLinkButton = document.getElementById('qrCopyLinkButton');

    const openQrModal = () => {
        modal.style.display = 'flex';
        requestAnimationFrame(() => {
            modal.classList.add('is-open');
        });
    };

    const closeQrModal = () => {
        modal.classList.remove('is-open');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 180);
    };

    if (modal && img && configUrl) {
        openQrModal();
        img.removeAttribute('src');

        if (qrContainer) {
            qrContainer.style.display = 'inline-block';
        }

        if (qrInfo) {
            qrInfo.textContent = 'Загрузка QR...';
            qrInfo.style.display = 'block';
        }
        if (qrCopyLinkButton) {
            qrCopyLinkButton.style.display = 'none';
            qrCopyLinkButton.dataset.link = '';
            qrCopyLinkButton.onclick = null;
        }

        fetch(configUrl, {
            method: 'GET',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(async (response) => {
                if (!response.ok) {
                    throw new Error(`Не удалось сформировать QR (HTTP ${response.status})`);
                }

                const mode = response.headers.get('X-QR-Mode') || 'config';
                const messageCode = response.headers.get('X-QR-Message-Code') || '';
                const oneTimeDownloadUrl = response.headers.get('X-QR-Download-Url') || '';
                const blob = await response.blob();

                if (!blob || !blob.size) {
                    throw new Error('Получено пустое изображение QR');
                }

                if (qrInfo) {
                    if (mode === 'download-url') {
                        qrInfo.textContent = 'Конфиг слишком большой для стабильного QR. Скопируйте одноразовую ссылку на скачивание конфигурации.';
                    } else {
                        qrInfo.textContent = 'Сканируйте QR в приложении.';
                    }
                }

                if (mode === 'download-url') {
                    if (qrContainer) {
                        qrContainer.style.display = 'none';
                    }

                    if (qrCopyLinkButton) {
                        const linkToCopy = oneTimeDownloadUrl || '';
                        qrCopyLinkButton.dataset.link = linkToCopy;
                        qrCopyLinkButton.style.display = linkToCopy ? 'inline-flex' : 'none';
                        qrCopyLinkButton.onclick = async function () {
                            try {
                                await copyTextToClipboard(linkToCopy);
                                showNotification('Одноразовая ссылка скопирована', 'success');
                            } catch (copyError) {
                                showNotification(copyError.message || 'Ошибка копирования ссылки', 'error');
                            }
                        };
                    }
                } else {
                    const objectUrl = URL.createObjectURL(blob);
                    img.onload = () => {
                        URL.revokeObjectURL(objectUrl);
                    };
                    img.onerror = () => {
                        URL.revokeObjectURL(objectUrl);
                        showNotification('Ошибка отображения QR изображения', 'error');
                    };
                    img.src = objectUrl;
                }
            })
            .catch((error) => {
                if (qrInfo) {
                    qrInfo.textContent = error.message || 'Ошибка загрузки QR';
                }
                showNotification(error.message || 'Не удалось загрузить QR', 'error');
            });

        if (!modal.dataset.popupBound) {
            modal.dataset.popupBound = '1';

            // Close on backdrop click
            modal.addEventListener('click', function (e) {
                if (e.target === modal) {
                    closeQrModal();
                }
            });

            // Close on escape key
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape' && modal.style.display === 'flex') {
                    closeQrModal();
                }
            });
        }
    }
}

function initializeOneTimeLinkButtons() {
    const linkButtons = document.querySelectorAll('.one-time-link-button');

    linkButtons.forEach(btn => {
        if (btn.dataset.oneTimeBound === '1') {
            return;
        }
        btn.dataset.oneTimeBound = '1';

        btn.addEventListener('click', async function (e) {
            if (this.disabled) return;

            e.preventDefault();
            const endpoint = this.getAttribute('data-link-endpoint');
            if (!endpoint) {
                showNotification('Не найден endpoint для генерации ссылки', 'error');
                return;
            }

            const originalText = this.textContent;
            this.disabled = true;
            this.textContent = '...';

            try {
                const response = await fetch(endpoint, {
                    method: 'GET',
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                let payload = null;
                try {
                    payload = await response.json();
                } catch (_error) {
                    payload = null;
                }

                if (!response.ok || !payload || !payload.success || !payload.download_url) {
                    const message = payload && payload.message
                        ? payload.message
                        : `Не удалось создать ссылку (HTTP ${response.status})`;
                    throw new Error(message);
                }

                await copyTextToClipboard(payload.download_url);
                showNotification('Одноразовая ссылка скопирована в буфер', 'success');
            } catch (error) {
                showNotification(error.message || 'Ошибка формирования ссылки', 'error');
            } finally {
                this.disabled = false;
                this.textContent = originalText;
            }
        });
    });
}

async function copyTextToClipboard(text) {
    if (!text) {
        throw new Error('Ссылка для копирования отсутствует');
    }

    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.setAttribute('readonly', '');
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.select();
    const copied = document.execCommand('copy');
    document.body.removeChild(textArea);

    if (!copied) {
        throw new Error('Не удалось скопировать ссылку');
    }
}

// ============ FORM SUBMISSION ============
document.addEventListener('submit', function (e) {
    const form = e.target;

    if (form.id === 'client-form') {
        e.preventDefault();

        const formData = new FormData(form);
        const option = formData.get('option');
        const selectedClient = formData.get('client-select');

        if ((option === '2' || option === '5') && !selectedClient) {
            showNotification('Выберите клиента для удаления', 'warning');
            return;
        }

        if ((option === '2' || option === '5') && selectedClient) {
            formData.set('client-name', selectedClient);
        }

        fetch(form.action || '/', {
            method: 'POST',
            body: formData
        })
            .then(response => {
                if (!response.ok) {
                    return response.json()
                        .then(err => {
                            throw new Error(err.message || `HTTP error! status: ${response.status}`);
                        })
                        .catch(() => {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        });
                }
                return response.json();
            })
            .then(async (data) => {
                showNotification(data.message || 'Операция выполнена успешно', 'success');
                await refreshMainContent();

                const addClientForm = document.getElementById('client-form');
                if (addClientForm) {
                    addClientForm.reset();
                }

                const addClientModal = document.getElementById('addClientModal');
                if (addClientModal && !addClientModal.hidden) {
                    addClientModal.classList.remove('is-open');
                    addClientModal.hidden = true;
                    document.body.classList.remove('add-client-modal-open');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showNotification(error.message || 'Ошибка при выполнении операции', 'error');
            });
    }
});

// ============ KEYBOARD SHORTCUTS ============
document.addEventListener('keydown', function (e) {
    // Ctrl/Cmd + F: focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        const searchInput = document.getElementById('search-clients');
        if (searchInput) {
            searchInput.focus();
        }
    }

    // ESC: close modal
    if (e.key === 'Escape') {
        const modal = document.getElementById('modalQRContainer');
        if (modal) {
            modal.classList.remove('is-open');
            setTimeout(() => {
                modal.style.display = 'none';
            }, 180);
        }
    }
});
