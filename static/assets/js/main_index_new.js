// ============ INITIALIZATION ============
document.addEventListener('DOMContentLoaded', function () {
    initializeUI();
    initializeFormLogic();
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

// ============ STATE MANAGEMENT ============
let currentTab = 'openvpn';
let currentFilter = 'all';
let sortColumn = 'name';
let sortOrder = 'asc';
let clientExpiry = {};

// Extract cert expiry data from HTML on load
function extractCertExpiryData() {
    clientExpiry = {};
    const rows = document.querySelectorAll('.client-row');
    rows.forEach(row => {
        const clientName = row.getAttribute('data-client-name');
        if (!clientName) return;

        const certState = row.dataset.certState || 'active';
        const certDays = Number.parseInt(row.dataset.certDays || '999', 10);
        clientExpiry[clientName] = {
            status: certState,
            days: Number.isNaN(certDays) ? 999 : certDays,
        };
    });
}

// ============ UI INITIALIZATION ============
function initializeUI() {
    extractCertExpiryData();

    // Set first tab active
    document.querySelector('.tab-btn[data-protocol="openvpn"]').classList.add('active');
    document.querySelector('#openvpn-tab').classList.add('active');

    // Set "All" filter as active
    const allFilterButton = document.querySelector('[data-filter="all"]');
    if (allFilterButton) {
        allFilterButton.classList.add('active');
    }
}

// ============ FORM LOGIC ============
function initializeFormLogic() {
    const optionSelect = document.getElementById('option');
    const clientNameContainer = document.getElementById('client-name-container');
    const workTermContainer = document.getElementById('work-term-container');
    const clientSelectContainer = document.getElementById('client-select-container');
    const clientForm = document.getElementById('client-form');

    if (optionSelect) {
        optionSelect.addEventListener('change', function () {
            const value = this.value;

            clientNameContainer.style.display =
                (value === '1' || value === '4') ? 'flex' : 'none';
            workTermContainer.style.display =
                (value === '1') ? 'flex' : 'none';
            clientSelectContainer.style.display =
                (value === '2' || value === '5') ? 'flex' : 'none';

            if (value === '2' || value === '5') {
                populateClientSelect(value);
            }
        });
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

function populateClientSelect(option) {
    const clientSelect = document.getElementById('client-select');
    const clientNameInput = document.getElementById('client-name');

    clientSelect.innerHTML = '<option value="">-- Выберите клиента --</option>';

    const tableSelectors = option === '2'
        ? ['.config-table[data-protocol="openvpn"]']
        : ['.config-table[data-protocol="amneziawg"]', '.config-table[data-protocol="wg"]'];

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

    initializeTabSwitching();
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

    const csrfInput = document.getElementById('csrf-token-value');
    const csrfToken = csrfInput ? csrfInput.value : '';

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

                if (row) {
                    row.dataset.blocked = shouldBlock ? '1' : '0';
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

function showQRModal(configUrl) {
    const modal = document.getElementById('modalQRContainer');
    const img = document.getElementById('qrImage');
    const qrContainer = modal ? modal.querySelector('.qr-code-container') : null;
    const qrInfo = document.getElementById('qrInfoMessage');
    const qrCopyLinkButton = document.getElementById('qrCopyLinkButton');

    if (modal && img && configUrl) {
        modal.style.display = 'flex';
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

        // Close on backdrop click
        modal.addEventListener('click', function (e) {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });

        // Close on escape key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.style.display === 'flex') {
                modal.style.display = 'none';
            }
        });
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

// ============ CLIENT DETAILS MODAL ============
function getIndexClientDetailsPayload() {
    const dataNode = document.getElementById('index-client-details-data');
    if (!dataNode) {
        return { connected: {}, traffic: {} };
    }

    try {
        const parsed = JSON.parse(dataNode.textContent || '{}');
        return {
            connected: parsed && parsed.connected ? parsed.connected : {},
            traffic: parsed && parsed.traffic ? parsed.traffic : {},
        };
    } catch (error) {
        console.warn('Failed to parse index client details payload:', error);
        return { connected: {}, traffic: {} };
    }
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function initializeClientDetailsModal() {
    const modal = document.getElementById('clientDetailsModalMain');
    if (!modal || modal.dataset.bound === '1') {
        return;
    }
    modal.dataset.bound = '1';

    const modalTitle = document.getElementById('clientDetailsTitleMain');
    const modalSummary = document.getElementById('clientDetailsSummaryMain');
    const modalTrafficQuick = document.getElementById('clientDetailsTrafficQuickMain');
    const modalTrafficMeta = document.getElementById('clientDetailsTrafficMetaMain');
    const modalConnections = document.getElementById('clientDetailsConnectionsMain');
    const modalChartCanvas = document.getElementById('clientDetailsTrafficChartMain');
    const rangeButtons = Array.from(document.querySelectorAll('.client-details-range-btn[data-range]'));

    const modalRangeStorageKey = 'index_client_details_selected_range';
    let currentClientName = '';
    let currentRange = localStorage.getItem(modalRangeStorageKey) || '7d';
    let detailsChart = null;

    if (!rangeButtons.some(btn => btn.dataset.range === currentRange)) {
        currentRange = '7d';
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

    function setModalOpen(isOpen) {
        modal.hidden = !isOpen;
        document.body.classList.toggle('client-details-modal-open', isOpen);
    }

    function closeModal() {
        setModalOpen(false);
    }

    function setActiveRangeButtons() {
        rangeButtons.forEach(btn => {
            const isActive = btn.dataset.range === currentRange;
            btn.classList.toggle('active', isActive);
            btn.disabled = isActive;
        });
    }

    function renderConnections(clientName) {
        if (!modalConnections) {
            return;
        }

        const payload = getIndexClientDetailsPayload();
        const connectedItem = payload.connected[clientName];
        const ipDeviceMap = connectedItem && Array.isArray(connectedItem.ip_device_map)
            ? connectedItem.ip_device_map
            : [];

        if (!ipDeviceMap.length) {
            modalConnections.innerHTML = '<div class="client-details-note">Сейчас нет активных подключений по этому клиенту.</div>';
            return;
        }

        const rendered = ipDeviceMap.map(item => {
            const ip = escapeHtml(item.ip || '-');
            const profile = escapeHtml(item.profile_label || '-');
            const realAddress = escapeHtml(item.real_address || '');
            const showSession = !!item.show_real_address;
            const platform = escapeHtml(item.platform || 'Не определено');
            const version = escapeHtml(item.version || 'Не определено');
            const staleLine = item.stale_candidate
                ? '<div><span class="client-details-key">Статус:</span> возможно зависшая (есть более новая сессия с тем же IP и профилем)</div>'
                : '';

            return `
                <div class="client-details-ip-item">
                    <div><span class="client-details-key">IP:</span>${ip}</div>
                    <div><span class="client-details-key">Профиль:</span>${profile}</div>
                    ${showSession ? `<div><span class="client-details-key">Сессия:</span>${realAddress}</div>` : ''}
                    ${staleLine}
                    <div><span class="client-details-key">Устройство:</span>${platform}</div>
                    <div><span class="client-details-key">Версия:</span>${version}</div>
                </div>
            `;
        }).join('');

        modalConnections.innerHTML = rendered;
    }

    async function loadTrafficChart() {
        if (!currentClientName || !modalTrafficMeta || !modalChartCanvas) {
            return;
        }

        if (typeof Chart === 'undefined') {
            modalTrafficMeta.textContent = 'График недоступен: библиотека Chart.js не загружена';
            return;
        }

        modalTrafficMeta.textContent = 'Загрузка...';

        try {
            const url = `/api/user-traffic-chart?client=${encodeURIComponent(currentClientName)}&range=${encodeURIComponent(currentRange)}`;
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            const labels = (data.labels || []).slice();
            const vpnData = (data.vpn_bytes || []).map(v => Number(v || 0));
            const antData = (data.antizapret_bytes || []).map(v => Number(v || 0));

            if (!labels.length) {
                labels.push('Нет данных');
                vpnData.push(0);
                antData.push(0);
            }

            if (detailsChart) {
                detailsChart.destroy();
            }

            detailsChart = new Chart(modalChartCanvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        {
                            label: 'VPN',
                            data: vpnData,
                            borderColor: '#4caf50',
                            backgroundColor: 'rgba(76,175,80,0.12)',
                            borderWidth: 2,
                            fill: false,
                            tension: 0.2,
                        },
                        {
                            label: 'Antizapret',
                            data: antData,
                            borderColor: '#f44336',
                            backgroundColor: 'rgba(244,67,54,0.12)',
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
                                color: '#bbb',
                                autoSkip: true,
                                maxTicksLimit: currentRange === '1h' ? 12 : (currentRange === '24h' ? 24 : 10)
                            },
                            grid: { color: 'rgba(255,255,255,0.05)' }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: '#ddd',
                                callback: function (value) {
                                    return humanBytes(value);
                                }
                            },
                            grid: { color: 'rgba(255,255,255,0.1)' }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#fff' }
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
                `VPN: ${data.total_vpn_human || humanBytes(data.total_vpn)} | ` +
                `Antizapret: ${data.total_antizapret_human || humanBytes(data.total_antizapret)} | ` +
                `Итого: ${data.total_human || humanBytes(data.total)}`;
        } catch (error) {
            modalTrafficMeta.textContent = `Не удалось загрузить график: ${error.message}`;
        }
    }

    function openModal(clientName) {
        const name = String(clientName || '').trim();
        if (!name) {
            showNotification('Не удалось определить имя клиента', 'error');
            return;
        }

        currentClientName = name;

        const payload = getIndexClientDetailsPayload();
        const connectedItem = payload.connected[name] || {};
        const trafficItem = payload.traffic[name] || null;

        if (modalTitle) {
            modalTitle.textContent = name;
        }

        const sessions = connectedItem.sessions != null ? connectedItem.sessions : '-';
        const profiles = connectedItem.profiles || '-';
        const rx = connectedItem.bytes_received_human || '-';
        const tx = connectedItem.bytes_sent_human || '-';
        const total = connectedItem.total_bytes_human || '-';

        if (modalSummary) {
            modalSummary.textContent = `Сессий: ${sessions} | Профили: ${profiles} | Rx: ${rx} | Tx: ${tx} | Итого: ${total}`;
        }

        if (modalTrafficQuick) {
            if (trafficItem) {
                const statusText = trafficItem.is_active ? 'Онлайн' : 'Оффлайн';
                modalTrafficQuick.textContent =
                    `Статус: ${statusText} | 1 день: ${trafficItem.traffic_1d_human} | 7 дней: ${trafficItem.traffic_7d_human} | 30 дней: ${trafficItem.traffic_30d_human} | VPN: ${trafficItem.total_bytes_vpn_human} | Antizapret: ${trafficItem.total_bytes_antizapret_human}`;
            } else {
                modalTrafficQuick.textContent = 'В БД пока нет накопленной статистики по этому клиенту.';
            }
        }

        renderConnections(name);
        setActiveRangeButtons();
        setModalOpen(true);
        loadTrafficChart();
    }

    rangeButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            currentRange = btn.dataset.range || '7d';
            localStorage.setItem(modalRangeStorageKey, currentRange);
            setActiveRangeButtons();
            loadTrafficChart();
        });
    });

    document.addEventListener('click', function (event) {
        const btn = event.target.closest('.client-details-button');
        if (!btn) {
            return;
        }

        event.preventDefault();
        const clientName = btn.getAttribute('data-client-name') ||
            btn.closest('.client-row')?.getAttribute('data-client-name') || '';
        openModal(clientName);
    });

    modal.querySelectorAll('[data-client-details-close]').forEach(node => {
        node.addEventListener('click', closeModal);
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !modal.hidden) {
            closeModal();
        }
    });
}

// ============ NOTIFICATIONS ============
function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');

    if (notification) {
        notification.textContent = message;
        notification.className = `notification notification-${type}`;
        notification.style.display = 'block';

        setTimeout(() => {
            notification.style.display = 'none';
        }, 3000);
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
            })
            .catch(error => {
                console.error('Error:', error);
                showNotification(error.message || 'Ошибка при выполнении операции', 'error');
            });
    }
});

// ============ DOUBLE-CLICK DOWNLOAD ============
document.addEventListener('dblclick', function (e) {
    if (e.target.classList.contains('client-name')) {
        const row = e.target.closest('.client-row');
        const firstDownloadBtn = row.querySelector('.download-button:not(:disabled)');

        if (firstDownloadBtn) {
            firstDownloadBtn.click();
        }
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
            modal.style.display = 'none';
        }
    }
});
