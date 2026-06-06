/* exported getIndexClientDetailsPayload, initializeClientDetailsModal, initializeIndexTrafficMiniSummary, indexClientDetailsCache, indexClientDetailsFetchPromise */
let indexClientDetailsCache = null;
let indexClientDetailsFetchPromise = null;

// ============ CLIENT DETAILS MODAL ============
function getIndexClientDetailsPayload() {
    if (indexClientDetailsCache) {
        return indexClientDetailsCache;
    }

    const dataNode = document.getElementById('index-client-details-data');
    if (!dataNode) {
        indexClientDetailsCache = { connected: {}, traffic: {} };
        return indexClientDetailsCache;
    }

    try {
        const parsed = JSON.parse(dataNode.textContent || '{}');
        indexClientDetailsCache = {
            connected: parsed && parsed.connected ? parsed.connected : {},
            traffic: parsed && parsed.traffic ? parsed.traffic : {},
        };
        return indexClientDetailsCache;
    } catch (error) {
        console.warn('Failed to parse index client details payload:', error);
        indexClientDetailsCache = { connected: {}, traffic: {} };
        return indexClientDetailsCache;
    }
}

function hasClientDetailsData(payload) {
    if (!payload) {
        return false;
    }

    const connected = payload.connected || {};
    const traffic = payload.traffic || {};
    return Object.keys(connected).length > 0 || Object.keys(traffic).length > 0;
}

async function loadIndexClientDetailsPayload(force = false) {
    if (!force && hasClientDetailsData(indexClientDetailsCache)) {
        return indexClientDetailsCache;
    }

    if (!force && indexClientDetailsFetchPromise) {
        return indexClientDetailsFetchPromise;
    }

    indexClientDetailsFetchPromise = fetch('/api/index-client-details', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        },
    })
        .then(async (response) => {
            let payload = null;
            try {
                payload = await response.json();
            } catch (_error) {
                payload = null;
            }

            if (!response.ok || !payload) {
                throw new Error(`Не удалось загрузить данные клиента (HTTP ${response.status})`);
            }

            if (payload.success === false) {
                throw new Error(payload.message || payload.error || 'Ошибка загрузки данных клиента');
            }

            const raw = payload.payload || payload;
            indexClientDetailsCache = {
                connected: raw && raw.connected ? raw.connected : {},
                traffic: raw && raw.traffic ? raw.traffic : {},
            };
            return indexClientDetailsCache;
        })
        .finally(() => {
            indexClientDetailsFetchPromise = null;
        });

    return indexClientDetailsFetchPromise;
}

function humanBytesForRail(value) {
    let size = Number(value || 0);
    if (!Number.isFinite(size) || size < 0) {
        size = 0;
    }

    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }

    if (unitIndex === 0) {
        return `${Math.round(size)} ${units[unitIndex]}`;
    }

    const precision = size >= 100 ? 0 : (size >= 10 ? 1 : 2);
    return `${size.toFixed(precision)} ${units[unitIndex]}`;
}

function setIndexRailSummaryLoading(message) {
    const section = document.getElementById('indexTrafficMiniSummary');
    const noteNode = document.getElementById('indexTrafficMiniNote');
    if (!section) {
        return;
    }

    section.dataset.state = 'loading';
    if (noteNode) {
        noteNode.textContent = message || 'Загрузка данных из payload...';
    }
}

function renderIndexTrafficMiniSummary(payload) {
    const section = document.getElementById('indexTrafficMiniSummary');
    if (!section) {
        return;
    }

    const noteNode = document.getElementById('indexTrafficMiniNote');
    const setText = (id, value) => {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = value;
        }
    };

    const trafficEntries = Object.values((payload && payload.traffic) || {});
    const connectedEntries = Object.values((payload && payload.connected) || {});

    const totals = {
        traffic1d: 0,
        traffic7d: 0,
        traffic30d: 0,
        totalVpn: 0,
        totalAz: 0,
        totalAll: 0,
    };

    trafficEntries.forEach((entry) => {
        totals.traffic1d += Number(entry && entry.traffic_1d ? entry.traffic_1d : 0);
        totals.traffic7d += Number(entry && entry.traffic_7d ? entry.traffic_7d : 0);
        totals.traffic30d += Number(entry && entry.traffic_30d ? entry.traffic_30d : 0);
        totals.totalVpn += Number(entry && entry.total_bytes_vpn ? entry.total_bytes_vpn : 0);
        totals.totalAz += Number(entry && entry.total_bytes_antizapret ? entry.total_bytes_antizapret : 0);
        totals.totalAll += Number(entry && entry.total_bytes ? entry.total_bytes : 0);
    });

    const onlineClients = connectedEntries.filter((entry) => Number(entry && entry.sessions ? entry.sessions : 0) > 0).length;
    const trackedClients = trafficEntries.length;

    section.dataset.state = trackedClients > 0 ? 'ready' : 'empty';
    if (noteNode) {
        noteNode.textContent = trackedClients > 0
            ? `Обновлено: клиентов в статистике ${trackedClients}, онлайн ${onlineClients}.`
            : 'В payload пока нет накопленной статистики трафика.';
    }

    setText('indexTrafficClientsTotal', String(trackedClients));
    setText('indexTrafficClientsOnline', String(onlineClients));
    setText('indexTrafficTotal1d', humanBytesForRail(totals.traffic1d));
    setText('indexTrafficTotal7d', humanBytesForRail(totals.traffic7d));
    setText('indexTrafficTotal30d', humanBytesForRail(totals.traffic30d));
    setText('indexTrafficTotalVpn', humanBytesForRail(totals.totalVpn));
    setText('indexTrafficTotalAz', humanBytesForRail(totals.totalAz));
    setText('indexTrafficTotalAll', humanBytesForRail(totals.totalAll));
}

async function initializeIndexTrafficMiniSummary(force = false) {
    const section = document.getElementById('indexTrafficMiniSummary');
    if (!section) {
        return;
    }

    setIndexRailSummaryLoading('Загрузка данных из payload...');

    let payload = getIndexClientDetailsPayload();
    const hasLocalData = hasClientDetailsData(payload);

    if (force || !hasLocalData) {
        try {
            payload = await loadIndexClientDetailsPayload(force);
        } catch (error) {
            section.dataset.state = 'error';
            const noteNode = document.getElementById('indexTrafficMiniNote');
            if (noteNode) {
                noteNode.textContent = error && error.message
                    ? `Не удалось загрузить сводку: ${error.message}`
                    : 'Не удалось загрузить сводку трафика.';
            }
            if (typeof window.syncAllClientCardStats === 'function') {
                window.syncAllClientCardStats(payload, { payloadReady: true });
            }
            return;
        }
    }

    renderIndexTrafficMiniSummary(payload);

    if (typeof window.syncAllClientCardStats === 'function') {
        window.syncAllClientCardStats(payload, { payloadReady: true });
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
    const modalChips = document.getElementById('clientDetailsChipsMain');
    const modalSummary = document.getElementById('clientDetailsSummaryMain');
    const modalRestrictions = document.getElementById('clientDetailsRestrictionsMain');
    const modalTrafficQuick = document.getElementById('clientDetailsTrafficQuickMain');
    const modalTrafficMeta = document.getElementById('clientDetailsTrafficMetaMain');
    const modalConnections = document.getElementById('clientDetailsConnectionsMain');
    const modalActions = document.getElementById('clientDetailsActionsMain');
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

    function getClientRowByName(clientName) {
        const escapedName = (window.CSS && typeof window.CSS.escape === 'function')
            ? window.CSS.escape(clientName)
            : String(clientName || '').replace(/"/g, '\\"');
        const rowSelector = `.client-row[data-client-name="${escapedName}"]`;
        const activePane = document.querySelector('.tab-pane.active');
        return (activePane && activePane.querySelector(rowSelector)) || document.querySelector(rowSelector);
    }

    function renderDetailsStatPill(key, value, extraClass = '') {
        const safeKey = escapeHtml(key);
        const safeValue = escapeHtml(value);
        const className = extraClass ? `client-details-stat-pill ${extraClass}` : 'client-details-stat-pill';
        return `<span class="${className}"><span class="client-details-stat-pill-k">${safeKey}</span><span class="client-details-stat-pill-v">${safeValue}</span></span>`;
    }

    function renderDetailsPlaceholder(text, isLoading = false) {
        const loadingClass = isLoading ? ' is-loading' : '';
        return `<div class="client-details-placeholder${loadingClass}">${escapeHtml(text)}</div>`;
    }

    function renderHeaderChips(row) {
        if (!modalChips) {
            return;
        }

        if (!row) {
            modalChips.innerHTML = '';
            return;
        }

        const isBlocked = row.dataset.blocked === '1';
        const protocolLabel = getProtocolLabel(row.dataset.protocol);
        const chips = [
            `<span class="client-details-chip client-details-chip--protocol">${escapeHtml(protocolLabel)}</span>`,
            `<span class="client-details-chip ${isBlocked ? 'is-blocked' : 'is-active'}">${isBlocked ? 'Заблокирован' : 'Активен'}</span>`,
        ];

        const accessExpiresAt = formatRestrictionDate(row.dataset.accessExpiresAt || row.dataset.wgExpiresAt);
        if (accessExpiresAt) {
            const accessRemaining = typeof window.formatAccessRemaining === 'function'
                ? window.formatAccessRemaining(row.dataset.accessExpiresAt || row.dataset.wgExpiresAt || '')
                : null;
            if (accessRemaining === 'срок истёк') {
                chips.push('<span class="client-details-chip is-expired">Срок истёк</span>');
            } else if (accessRemaining) {
                chips.push(`<span class="client-details-chip is-expiring">${escapeHtml(accessRemaining)}</span>`);
            }
        }

        if (row.dataset.trafficLimitExceeded === '1') {
            chips.push('<span class="client-details-chip is-traffic-limit">Лимит превышен</span>');
        }

        modalChips.innerHTML = chips.join('');
    }

    function renderSummaryGrid(connectedItem, trafficItem) {
        if (!modalSummary) {
            return;
        }

        const pills = [];

        if (trafficItem) {
            pills.push(renderDetailsStatPill(
                'Статус',
                trafficItem.is_active ? 'Онлайн' : 'Оффлайн',
                trafficItem.is_active ? 'is-online' : 'is-offline',
            ));
            pills.push(renderDetailsStatPill('1 день', trafficItem.traffic_1d_human || '—'));
            pills.push(renderDetailsStatPill('7 дней', trafficItem.traffic_7d_human || '—'));
            pills.push(renderDetailsStatPill('30 дней', trafficItem.traffic_30d_human || '—'));
        }

        const sessions = connectedItem.sessions != null ? String(connectedItem.sessions) : '—';
        const profiles = connectedItem.profiles || '—';
        const rx = connectedItem.bytes_received_human || '—';
        const tx = connectedItem.bytes_sent_human || '—';
        const total = connectedItem.total_bytes_human || '—';

        pills.push(renderDetailsStatPill('Сессий', sessions));
        pills.push(renderDetailsStatPill('Профили', profiles));
        pills.push(renderDetailsStatPill('Rx', rx));
        pills.push(renderDetailsStatPill('Tx', tx));
        pills.push(renderDetailsStatPill('Итого', total));

        modalSummary.innerHTML = `<div class="client-details-summary-pills">${pills.join('')}</div>`;
    }

    function renderTrafficStats(trafficItem) {
        if (!modalTrafficQuick) {
            return;
        }

        if (!trafficItem) {
            modalTrafficQuick.innerHTML = renderDetailsPlaceholder('В БД пока нет накопленной статистики по этому клиенту.');
            return;
        }

        const pills = [
            renderDetailsStatPill(
                'Статус',
                trafficItem.is_active ? 'Онлайн' : 'Оффлайн',
                trafficItem.is_active ? 'is-online' : 'is-offline',
            ),
            renderDetailsStatPill('1 день', trafficItem.traffic_1d_human || '—'),
            renderDetailsStatPill('7 дней', trafficItem.traffic_7d_human || '—'),
            renderDetailsStatPill('30 дней', trafficItem.traffic_30d_human || '—'),
            renderDetailsStatPill('VPN', trafficItem.total_bytes_vpn_human || '—'),
            renderDetailsStatPill('Antizapret', trafficItem.total_bytes_antizapret_human || '—'),
        ];

        modalTrafficQuick.innerHTML = `<div class="client-details-traffic-pills">${pills.join('')}</div>`;
    }

    function renderTrafficMeta(metaParts) {
        if (!modalTrafficMeta) {
            return;
        }

        if (!metaParts.length) {
            modalTrafficMeta.innerHTML = '';
            return;
        }

        modalTrafficMeta.innerHTML = metaParts
            .map((part, index) => {
                const isLimit = index === metaParts.length - 1 && /лимит/i.test(part);
                const limitClass = isLimit ? ' client-details-meta-item--limit' : '';
                return `<span class="client-details-meta-item${limitClass}">${escapeHtml(part)}</span>`;
            })
            .join('');
        modalTrafficMeta.classList.remove('is-loading');
    }

    function renderRestrictionsForClient(clientName) {
        if (!modalRestrictions) {
            return;
        }

        const row = getClientRowByName(clientName);
        if (!row) {
            modalRestrictions.innerHTML = renderDetailsPlaceholder('Ограничения для этого клиента недоступны.');
            return;
        }

        modalRestrictions.innerHTML = '';
        modalRestrictions.appendChild(renderRestrictionsPanel(row));
    }

    function getChartRangeDays(range) {
        const normalized = (range || '7d').toLowerCase();
        if (normalized === '1h') {
            return 1 / 24;
        }
        if (normalized === '1d' || normalized === '24h') {
            return 1;
        }
        if (normalized === '7d') {
            return 7;
        }
        if (normalized === '30d') {
            return 30;
        }
        return null;
    }

    function getChartTrafficLimitDisplay(limitBytes, limitPeriodDays, chartRange) {
        const parsedLimit = Number(limitBytes || 0);
        if (!Number.isFinite(parsedLimit) || parsedLimit < 1) {
            return null;
        }

        const periodDays = Number(limitPeriodDays || 0);
        const hasPeriod = Number.isFinite(periodDays) && periodDays > 0;
        const rangeDays = getChartRangeDays(chartRange);
        const periodLabel = hasPeriod
            ? (periodDays === 1
                ? 'за сутки (календарный день)'
                : (periodDays === 7
                    ? 'за неделю (пн–вс)'
                    : (periodDays === 30 ? 'за месяц' : `${periodDays} дн.`)))
            : 'всё время';

        if (!hasPeriod || rangeDays === null) {
            return {
                value: parsedLimit,
                label: `Лимит: ${humanBytes(parsedLimit)} / ${periodLabel}`,
            };
        }

        const effectiveLimit = Math.round(parsedLimit * Math.min(rangeDays, periodDays) / periodDays);
        if (rangeDays < periodDays) {
            return {
                value: effectiveLimit,
                label: `Лимит: ${humanBytes(parsedLimit)} / ${periodLabel} (≈${humanBytes(effectiveLimit)} за период графика)`,
            };
        }

        return {
            value: parsedLimit,
            label: `Лимит: ${humanBytes(parsedLimit)} / ${periodLabel}`,
        };
    }

    const trafficLabelFormatters = {
        minute5: new Intl.DateTimeFormat(undefined, {
            hour: '2-digit',
            minute: '2-digit',
        }),
        hour: new Intl.DateTimeFormat(undefined, {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        }),
        day: new Intl.DateTimeFormat(undefined, {
            day: '2-digit',
            month: '2-digit',
        }),
        month: new Intl.DateTimeFormat(undefined, {
            month: '2-digit',
            year: 'numeric',
        }),
    };

    function formatTrafficChartLabels(data) {
        const labels = Array.isArray(data && data.labels) ? data.labels.slice() : [];
        const labelDatetimesUtc = Array.isArray(data && data.label_datetimes_utc)
            ? data.label_datetimes_utc
            : [];
        const bucket = String((data && data.bucket) || '').toLowerCase();
        const formatter = trafficLabelFormatters[bucket];

        if (!labels.length || labels.length !== labelDatetimesUtc.length || !formatter) {
            return labels;
        }

        return labels.map((fallbackLabel, index) => {
            const parsed = new Date(labelDatetimesUtc[index]);
            if (Number.isNaN(parsed.getTime())) {
                return fallbackLabel;
            }
            return formatter.format(parsed);
        });
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
        document.body.classList.toggle('client-details-modal-open', isOpen);
    }

    function closeModal() {
        setModalOpen(false);
    }

    async function generateOneTimeLink(endpoint) {
        if (!endpoint) {
            throw new Error('Не найден endpoint для генерации ссылки');
        }

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
            const message = payload && (payload.message || payload.error)
                ? (payload.message || payload.error)
                : `Не удалось создать ссылку (HTTP ${response.status})`;
            throw new Error(message);
        }

        await copyTextToClipboard(payload.download_url);
    }

    async function updateWgClientAccess(clientName, action, options = null) {
        const csrfInput = document.getElementById('csrf-token-value');
        const csrfToken = csrfInput ? csrfInput.value : '';
        const formData = new FormData();
        formData.append('client_name', clientName);
        formData.append('action', action);

        let days = null;
        let limitValue = null;
        let limitUnit = null;
        let limitPeriodDays = null;
        if (typeof options === 'number' || typeof options === 'string') {
            days = options;
        } else if (options && typeof options === 'object') {
            days = options.days ?? null;
            limitValue = options.limitValue ?? null;
            limitUnit = options.limitUnit ?? null;
            limitPeriodDays = options.limitPeriodDays ?? null;
        }

        if (days !== null && days !== undefined && String(days).trim() !== '') {
            formData.append('days', String(days).trim());
        }
        if (limitValue !== null && limitValue !== undefined && String(limitValue).trim() !== '') {
            formData.append('limit_value', String(limitValue).trim());
        }
        if (limitUnit !== null && limitUnit !== undefined && String(limitUnit).trim() !== '') {
            formData.append('limit_unit', String(limitUnit).trim());
        }
        if (limitPeriodDays !== null && limitPeriodDays !== undefined && String(limitPeriodDays).trim() !== '') {
            formData.append('limit_period_days', String(limitPeriodDays).trim());
        }
        if (csrfToken) {
            formData.append('csrf_token', csrfToken);
        }

        const response = await fetch('/api/wg/client-access', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        });
        let payload = null;
        try {
            payload = await response.json();
        } catch (_e) {
            payload = null;
        }
        if (!response.ok || !payload || !payload.success) {
            const msg = payload && (payload.message || payload.error) ? (payload.message || payload.error) : `HTTP error! status: ${response.status}`;
            const error = new Error(msg);
            error.errorCode = payload && payload.error_code ? payload.error_code : null;
            throw error;
        }
        return payload;
    }

    async function requestTrafficLimitInput(clientName, protocolLabel, row = null) {
        const defaultPeriodDays = (row && row.dataset.trafficLimitPeriodDays) ? row.dataset.trafficLimitPeriodDays : '7';
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'quick-action-modal';
            modal.innerHTML = `
                <div class="quick-action-backdrop"></div>
                <div class="quick-action-dialog traffic-limit-dialog" role="dialog" aria-modal="true" aria-labelledby="trafficLimitTitle">
                    <button type="button" class="quick-action-close" aria-label="Закрыть">×</button>
                    <div class="traffic-limit-header">
                        <div class="traffic-limit-icon" aria-hidden="true">📊</div>
                        <div class="traffic-limit-header-text">
                            <h4 id="trafficLimitTitle">Лимит трафика ${protocolLabel}</h4>
                            <p class="quick-action-message">Максимальный объём трафика за выбранный период</p>
                        </div>
                    </div>
                    <div class="traffic-limit-client-badge">${clientName}</div>
                    <form class="quick-action-form traffic-limit-form">
                        <div class="traffic-limit-fields">
                            <div class="traffic-limit-field">
                                <label class="quick-action-label" for="trafficLimitValue">Объём</label>
                                <input id="trafficLimitValue" name="trafficLimitValue" type="number" inputmode="decimal" min="0.01" step="any" value="10" placeholder="10" />
                            </div>
                            <div class="traffic-limit-field traffic-limit-field-unit">
                                <label class="quick-action-label" for="trafficLimitUnit">Единица</label>
                                <div class="traffic-limit-select-wrap">
                                    <select id="trafficLimitUnit" name="trafficLimitUnit" class="traffic-limit-select">
                                        <option value="mb">MB</option>
                                        <option value="gb" selected>GB</option>
                                        <option value="tb">TB</option>
                                    </select>
                                </div>
                            </div>
                            <div class="traffic-limit-field traffic-limit-field-period">
                                <label class="quick-action-label" for="trafficLimitPeriod">Период</label>
                                <div class="traffic-limit-select-wrap">
                                    <select id="trafficLimitPeriod" name="trafficLimitPeriod" class="traffic-limit-select">
                                        <option value="1"${defaultPeriodDays === '1' ? ' selected' : ''}>За сутки (календарный день)</option>
                                        <option value="7"${defaultPeriodDays === '7' ? ' selected' : ''}>За неделю (пн–вс)</option>
                                        <option value="30"${defaultPeriodDays === '30' ? ' selected' : ''}>За месяц</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                        <div class="traffic-limit-presets" role="group" aria-label="Быстрый выбор лимита">
                            <button type="button" class="traffic-limit-preset" data-value="1" data-unit="gb">1 GB</button>
                            <button type="button" class="traffic-limit-preset" data-value="10" data-unit="gb">10 GB</button>
                            <button type="button" class="traffic-limit-preset" data-value="50" data-unit="gb">50 GB</button>
                            <button type="button" class="traffic-limit-preset" data-value="100" data-unit="gb">100 GB</button>
                        </div>
                        <p class="traffic-limit-hint">При превышении лимита клиент будет автоматически заблокирован до конца выбранного периода; в начале нового периода блокировка снимается.</p>
                        <div class="quick-action-error" aria-live="polite"></div>
                        <div class="quick-action-actions traffic-limit-actions">
                            <button type="button" class="download-button quick-action-cancel">Отмена</button>
                            <button type="submit" class="btn-primary quick-action-submit">Установить</button>
                        </div>
                    </form>
                </div>
            `;

            const form = modal.querySelector('.quick-action-form');
            const valueInput = modal.querySelector('#trafficLimitValue');
            const unitSelect = modal.querySelector('#trafficLimitUnit');
            const periodSelect = modal.querySelector('#trafficLimitPeriod');
            const errorNode = modal.querySelector('.quick-action-error');
            const closeButton = modal.querySelector('.quick-action-close');
            const cancelButton = modal.querySelector('.quick-action-cancel');
            const backdrop = modal.querySelector('.quick-action-backdrop');
            const presetButtons = modal.querySelectorAll('.traffic-limit-preset');

            const syncPresetState = () => {
                const currentValue = Number.parseFloat((valueInput.value || '').trim());
                const currentUnit = (unitSelect.value || 'gb').trim().toLowerCase();
                presetButtons.forEach((presetButton) => {
                    const presetValue = Number.parseFloat(presetButton.dataset.value || '');
                    const presetUnit = (presetButton.dataset.unit || '').trim().toLowerCase();
                    const isActive = Number.isFinite(currentValue)
                        && currentValue === presetValue
                        && currentUnit === presetUnit;
                    presetButton.classList.toggle('is-active', isActive);
                });
            };

            presetButtons.forEach((presetButton) => {
                presetButton.addEventListener('click', () => {
                    valueInput.value = presetButton.dataset.value || '';
                    unitSelect.value = presetButton.dataset.unit || 'gb';
                    errorNode.textContent = '';
                    syncPresetState();
                    valueInput.focus();
                });
            });

            valueInput.addEventListener('input', syncPresetState);
            unitSelect.addEventListener('change', syncPresetState);

            let resolved = false;
            const cleanup = (value = null) => {
                if (resolved) {
                    return;
                }
                resolved = true;
                document.removeEventListener('keydown', onKeyDown);
                document.body.classList.remove('quick-action-modal-open');
                modal.remove();
                resolve(value);
            };

            const onKeyDown = (event) => {
                if (event.key === 'Escape') {
                    cleanup(null);
                }
            };

            form.addEventListener('submit', (event) => {
                event.preventDefault();
                const limitValue = Number.parseFloat((valueInput.value || '').trim());
                const limitUnit = (unitSelect.value || 'mb').trim().toLowerCase();
                const limitPeriodDays = (periodSelect && periodSelect.value) ? periodSelect.value.trim() : '7';
                if (!Number.isFinite(limitValue) || limitValue <= 0) {
                    errorNode.textContent = 'Укажите положительное значение лимита.';
                    return;
                }
                if (!['1', '7', '30'].includes(limitPeriodDays)) {
                    errorNode.textContent = 'Период лимита должен быть 1, 7 или 30 дней.';
                    return;
                }
                cleanup({ limitValue: String(limitValue), limitUnit, limitPeriodDays });
            });

            if (closeButton) closeButton.addEventListener('click', () => cleanup(null));
            if (cancelButton) cancelButton.addEventListener('click', () => cleanup(null));
            if (backdrop) backdrop.addEventListener('click', () => cleanup(null));

            document.body.appendChild(modal);
            document.body.classList.add('quick-action-modal-open');
            document.addEventListener('keydown', onKeyDown);
            requestAnimationFrame(() => {
                modal.classList.add('is-open');
                syncPresetState();
                valueInput.focus();
                valueInput.select();
            });
        });
    }

    function notifyWgAccessResult(payload, defaultSuccessMessage) {
        const runtimeErrorCount = Number(payload.runtime_error_count || 0);
        if (runtimeErrorCount > 0) {
            const detail = Array.isArray(payload.runtime_errors)
                ? payload.runtime_errors
                    .map((entry) => {
                        if (!entry || !entry.interface) {
                            return '';
                        }
                        const stderr = (entry.stderr || '').trim();
                        return stderr ? `${entry.interface}: ${stderr}` : entry.interface;
                    })
                    .filter(Boolean)
                    .join('; ')
                : '';
            const warningMessage = detail
                ? `${payload.message || defaultSuccessMessage}. WireGuard не перезагружен (${detail})`
                : `${payload.message || defaultSuccessMessage}. WireGuard не перезагружен — проверьте wg-quick@antizapret и wg-quick@vpn`;
            showNotification(warningMessage, 'warning');
            return;
        }
        showNotification(payload.message || defaultSuccessMessage, 'success');
    }

    function isWgAccessExpired(row) {
        if (!row) {
            return false;
        }
        const blockMode = (row.dataset.blockMode || 'none').toLowerCase();
        if (blockMode === 'expired') {
            return true;
        }
        if (typeof window.formatAccessRemaining !== 'function') {
            return false;
        }
        return window.formatAccessRemaining(row.dataset.accessExpiresAt || '') === 'срок истёк';
    }

    async function applyWgAccessPayload(clientName, row, payload) {
        if (typeof window.applyWgAccessPayloadToClientRows === 'function') {
            window.applyWgAccessPayloadToClientRows(clientName, payload);
        } else if (typeof window.applyWgAccessPayloadToRow === 'function') {
            window.applyWgAccessPayloadToRow(row, payload);
        } else {
            row.dataset.blocked = payload.is_blocked ? '1' : '0';
            syncClientBlockedBadge(row);
        }
        renderActions(clientName);
    }

    async function requestWgExtendDays(clientName, row) {
        const daysValue = await showActionModal({
            title: 'Продлить срок WG/AWG',
            message: `Укажите срок продления для клиента "${clientName}"`,
            mode: 'numberInput',
            inputLabel: 'Продлить срок действия на (дни, 1-3650)',
            inputDefault: '30',
            inputMin: 1,
            inputMax: 3650,
            confirmLabel: 'Продлить',
            cancelLabel: 'Отмена',
        });
        if (daysValue === null) {
            return null;
        }

        const payload = await updateWgClientAccess(clientName, 'extend', daysValue);
        await applyWgAccessPayload(clientName, row, payload);
        notifyWgAccessResult(payload, 'Срок WG/AWG обновлён');
        return payload;
    }

    function showExpiredWgExtendModal(clientName, row) {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'quick-action-modal';
            modal.innerHTML = `
                <div class="quick-action-backdrop"></div>
                <div class="quick-action-dialog" role="dialog" aria-modal="true" aria-labelledby="expiredWgTitle">
                    <button type="button" class="quick-action-close" aria-label="Закрыть">×</button>
                    <div class="quick-action-header">
                        <h4 id="expiredWgTitle">Срок действия истёк</h4>
                        <p class="quick-action-message">Клиент «${clientName}» отключён по истечении срока жизни. Для разблокировки необходимо продлить срок.</p>
                    </div>
                    <div class="quick-action-actions">
                        <button type="button" class="download-button quick-action-cancel">Закрыть</button>
                        <button type="button" class="btn-primary quick-action-extend">♻ Продлить срок WG/AWG</button>
                    </div>
                </div>
            `;

            const closeButton = modal.querySelector('.quick-action-close');
            const cancelButton = modal.querySelector('.quick-action-cancel');
            const extendButton = modal.querySelector('.quick-action-extend');
            const backdrop = modal.querySelector('.quick-action-backdrop');

            let resolved = false;
            const cleanup = (value = null) => {
                if (resolved) {
                    return;
                }
                resolved = true;
                document.removeEventListener('keydown', onKeyDown);
                document.body.classList.remove('quick-action-modal-open');
                modal.remove();
                resolve(value);
            };

            const onKeyDown = (event) => {
                if (event.key === 'Escape') {
                    cleanup(null);
                }
            };

            if (closeButton) {
                closeButton.addEventListener('click', () => cleanup(null));
            }
            if (cancelButton) {
                cancelButton.addEventListener('click', () => cleanup(null));
            }
            if (backdrop) {
                backdrop.addEventListener('click', () => cleanup(null));
            }
            if (extendButton) {
                extendButton.addEventListener('click', async () => {
                    extendButton.disabled = true;
                    try {
                        await requestWgExtendDays(clientName, row);
                        cleanup(true);
                    } catch (error) {
                        showNotification(error.message || 'Не удалось продлить срок WG/AWG', 'error');
                        extendButton.disabled = false;
                    }
                });
            }

            document.addEventListener('keydown', onKeyDown);
            document.body.appendChild(modal);
            document.body.classList.add('quick-action-modal-open');
            requestAnimationFrame(() => {
                modal.classList.add('is-open');
                if (extendButton) {
                    extendButton.focus();
                }
            });
        });
    }

    async function updateOpenVpnClientAccess(clientName, action, options = null) {
        const csrfInput = document.getElementById('csrf-token-value');
        const csrfToken = csrfInput ? csrfInput.value : '';
        const formData = new FormData();
        formData.append('client_name', clientName);
        formData.append('action', action);

        let days = null;
        let limitValue = null;
        let limitUnit = null;
        let limitPeriodDays = null;
        if (typeof options === 'number' || typeof options === 'string') {
            days = options;
        } else if (options && typeof options === 'object') {
            days = options.days ?? null;
            limitValue = options.limitValue ?? null;
            limitUnit = options.limitUnit ?? null;
            limitPeriodDays = options.limitPeriodDays ?? null;
        }

        if (days !== null && days !== undefined && String(days).trim() !== '') {
            formData.append('days', String(days).trim());
        }
        if (limitValue !== null && limitValue !== undefined && String(limitValue).trim() !== '') {
            formData.append('limit_value', String(limitValue).trim());
        }
        if (limitUnit !== null && limitUnit !== undefined && String(limitUnit).trim() !== '') {
            formData.append('limit_unit', String(limitUnit).trim());
        }
        if (limitPeriodDays !== null && limitPeriodDays !== undefined && String(limitPeriodDays).trim() !== '') {
            formData.append('limit_period_days', String(limitPeriodDays).trim());
        }
        if (csrfToken) {
            formData.append('csrf_token', csrfToken);
        }

        const response = await fetch('/api/openvpn/client-block', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        });
        let payload = null;
        try {
            payload = await response.json();
        } catch (_e) {
            payload = null;
        }
        if (!response.ok || !payload || !payload.success) {
            const msg = payload && (payload.message || payload.error) ? (payload.message || payload.error) : `HTTP error! status: ${response.status}`;
            throw new Error(msg);
        }
        return payload;
    }

    function showActionModal({
        title = 'Подтвердите действие',
        message = '',
        mode = 'confirm',
        confirmLabel = 'OK',
        cancelLabel = 'Отмена',
        inputLabel = 'Значение',
        inputDefault = '1',
        inputMin = 1,
        inputMax = 3650,
    } = {}) {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'quick-action-modal';
            modal.innerHTML = `
                <div class="quick-action-backdrop"></div>
                <div class="quick-action-dialog" role="dialog" aria-modal="true" aria-labelledby="quickActionTitle">
                    <button type="button" class="quick-action-close" aria-label="Закрыть">×</button>
                    <div class="quick-action-header">
                        <h4 id="quickActionTitle"></h4>
                        <p class="quick-action-message"></p>
                    </div>
                    <form class="quick-action-form">
                        <label class="quick-action-label" for="quickActionInput"></label>
                        <input id="quickActionInput" name="quickActionInput" type="number" inputmode="numeric" />
                        <div class="quick-action-error" aria-live="polite"></div>
                        <div class="quick-action-actions">
                            <button type="button" class="download-button quick-action-cancel"></button>
                            <button type="submit" class="btn-primary quick-action-submit"></button>
                        </div>
                    </form>
                </div>
            `;

            const titleNode = modal.querySelector('#quickActionTitle');
            const messageNode = modal.querySelector('.quick-action-message');
            const form = modal.querySelector('.quick-action-form');
            const inputLabelNode = modal.querySelector('.quick-action-label');
            const inputNode = modal.querySelector('#quickActionInput');
            const errorNode = modal.querySelector('.quick-action-error');
            const closeButton = modal.querySelector('.quick-action-close');
            const cancelButton = modal.querySelector('.quick-action-cancel');
            const submitButton = modal.querySelector('.quick-action-submit');
            const backdrop = modal.querySelector('.quick-action-backdrop');

            if (titleNode) {
                titleNode.textContent = String(title || 'Подтвердите действие');
            }
            if (messageNode) {
                messageNode.textContent = String(message || '');
            }
            if (cancelButton) {
                cancelButton.textContent = String(cancelLabel || 'Отмена');
            }
            if (submitButton) {
                submitButton.textContent = String(confirmLabel || 'OK');
            }

            const setError = (text = '') => {
                if (errorNode) {
                    errorNode.textContent = text;
                }
            };

            let resolved = false;
            const cleanup = (value = null) => {
                if (resolved) {
                    return;
                }
                resolved = true;
                document.removeEventListener('keydown', onKeyDown);
                document.body.classList.remove('quick-action-modal-open');
                modal.remove();
                resolve(value);
            };

            const onKeyDown = (event) => {
                if (event.key === 'Escape') {
                    cleanup(null);
                }
            };

            const useNumberInput = mode === 'numberInput';
            if (inputNode && inputLabelNode) {
                if (useNumberInput) {
                    inputLabelNode.textContent = String(inputLabel || 'Значение');
                    inputNode.value = String(inputDefault || '');
                    inputNode.min = String(inputMin);
                    inputNode.max = String(inputMax);
                    inputNode.required = true;
                } else {
                    inputLabelNode.style.display = 'none';
                    inputNode.style.display = 'none';
                    inputNode.required = false;
                }
            }

            if (form) {
                form.addEventListener('submit', (event) => {
                    event.preventDefault();
                    setError('');

                    if (!useNumberInput) {
                        cleanup(true);
                        return;
                    }

                    const raw = String(inputNode ? inputNode.value : '').trim();
                    if (!/^\d+$/.test(raw)) {
                        setError(`Введите целое число от ${inputMin} до ${inputMax}`);
                        return;
                    }

                    const parsed = Number.parseInt(raw, 10);
                    if (!Number.isFinite(parsed) || parsed < Number(inputMin) || parsed > Number(inputMax)) {
                        setError(`Значение должно быть в диапазоне ${inputMin}-${inputMax}`);
                        return;
                    }

                    cleanup(parsed);
                });
            }

            if (closeButton) {
                closeButton.addEventListener('click', () => cleanup(null));
            }
            if (cancelButton) {
                cancelButton.addEventListener('click', () => cleanup(null));
            }
            if (backdrop) {
                backdrop.addEventListener('click', () => cleanup(null));
            }
            document.addEventListener('keydown', onKeyDown);

            document.body.appendChild(modal);
            document.body.classList.add('quick-action-modal-open');
            requestAnimationFrame(() => {
                modal.classList.add('is-open');
                if (useNumberInput && inputNode) {
                    inputNode.focus();
                    inputNode.select();
                } else if (submitButton) {
                    submitButton.focus();
                }
            });
        });
    }

    function requestRenewDays(defaultDays) {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'renew-days-modal';
            modal.innerHTML = `
                <div class="renew-days-backdrop"></div>
                <div class="renew-days-dialog" role="dialog" aria-modal="true" aria-labelledby="renewDaysTitle">
                    <button type="button" class="renew-days-close" aria-label="Закрыть">×</button>
                    <div class="renew-days-header">
                        <h4 id="renewDaysTitle">Продлить сертификат</h4>
                        <p>Укажите новый срок сертификата для клиента.</p>
                    </div>
                    <form class="renew-days-form">
                        <label for="renewDaysInput">Срок действия (дни, 1-3650)</label>
                        <input id="renewDaysInput" name="renewDays" type="number" min="1" max="3650" inputmode="numeric" required />
                        <div class="renew-days-field-meta">или выберите дату окончания</div>
                        <label for="renewDateInput">Дата окончания сертификата</label>
                        <input id="renewDateInput" name="renewDate" type="date" required />
                        <p class="renew-days-hint">При выборе даты срок в днях рассчитывается автоматически.</p>
                        <div class="renew-days-error" aria-live="polite"></div>
                        <div class="renew-days-actions">
                            <button type="button" class="download-button renew-days-cancel">Отмена</button>
                            <button type="submit" class="btn-primary renew-days-submit">Сохранить</button>
                        </div>
                    </form>
                </div>
            `;

            const input = modal.querySelector('#renewDaysInput');
            const dateInput = modal.querySelector('#renewDateInput');
            const errorNode = modal.querySelector('.renew-days-error');
            const form = modal.querySelector('.renew-days-form');
            const closeButton = modal.querySelector('.renew-days-close');
            const cancelButton = modal.querySelector('.renew-days-cancel');
            const backdrop = modal.querySelector('.renew-days-backdrop');

            const initialValue = String(defaultDays || '365').trim();
            const initialDaysParsed = Number.parseInt(initialValue, 10);
            const initialDays = Number.isFinite(initialDaysParsed) && initialDaysParsed >= 1 && initialDaysParsed <= 3650
                ? initialDaysParsed
                : 365;
            input.value = String(initialDays);

            const MS_PER_DAY = 24 * 60 * 60 * 1000;
            const getToday = () => {
                const now = new Date();
                return new Date(now.getFullYear(), now.getMonth(), now.getDate());
            };

            const formatDateForInput = (date) => {
                const year = String(date.getFullYear());
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            };

            const parseInputDate = (raw) => {
                const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(raw || '').trim());
                if (!match) {
                    return null;
                }

                const year = Number.parseInt(match[1], 10);
                const month = Number.parseInt(match[2], 10);
                const day = Number.parseInt(match[3], 10);
                const parsed = new Date(year, month - 1, day);
                if (
                    parsed.getFullYear() !== year
                    || parsed.getMonth() !== month - 1
                    || parsed.getDate() !== day
                ) {
                    return null;
                }
                return parsed;
            };

            const today = getToday();

            const setDateFromDays = (days) => {
                const targetDate = new Date(today.getFullYear(), today.getMonth(), today.getDate() + days);
                dateInput.value = formatDateForInput(targetDate);
            };

            const calculateDaysFromDate = (selectedDate) => {
                const diffMs = selectedDate.getTime() - today.getTime();
                const diffDays = Math.round(diffMs / MS_PER_DAY);
                return Math.max(1, diffDays);
            };

            dateInput.min = formatDateForInput(today);
            setDateFromDays(initialDays);

            let activeSource = 'days';

            let resolved = false;

            const cleanup = (value) => {
                if (resolved) {
                    return;
                }
                resolved = true;
                document.removeEventListener('keydown', onKeyDown);
                document.body.classList.remove('renew-days-modal-open');
                modal.remove();
                resolve(value);
            };

            const setError = (message) => {
                if (!errorNode) {
                    return;
                }
                errorNode.textContent = message || '';
            };

            const parseDays = () => {
                const raw = String(input.value || '').trim();
                if (!/^\d+$/.test(raw)) {
                    setError('Введите целое число от 1 до 3650');
                    return null;
                }

                const days = Number.parseInt(raw, 10);
                if (!Number.isFinite(days) || days < 1 || days > 3650) {
                    setError('Срок должен быть в диапазоне 1-3650 дней');
                    return null;
                }

                setError('');
                return days;
            };

            const parseDateBasedDays = () => {
                const raw = String(dateInput.value || '').trim();
                if (!raw) {
                    setError('Выберите дату окончания сертификата');
                    return null;
                }

                const parsedDate = parseInputDate(raw);
                if (!parsedDate) {
                    setError('Выберите корректную дату окончания');
                    return null;
                }

                if (parsedDate.getTime() < today.getTime()) {
                    setError('Дата не может быть раньше сегодняшней');
                    return null;
                }

                const days = calculateDaysFromDate(parsedDate);
                if (!Number.isFinite(days) || days < 1 || days > 3650) {
                    setError('Выбранная дата должна быть в пределах 3650 дней');
                    return null;
                }

                input.value = String(days);
                setError('');
                return days;
            };

            const onKeyDown = (event) => {
                if (event.key === 'Escape') {
                    cleanup(null);
                }
            };

            form.addEventListener('submit', (event) => {
                event.preventDefault();
                const days = activeSource === 'date' ? parseDateBasedDays() : parseDays();
                if (days === null) {
                    return;
                }
                cleanup(days);
            });

            input.addEventListener('input', () => {
                activeSource = 'days';
                setError('');
                const days = Number.parseInt(String(input.value || '').trim(), 10);
                if (Number.isFinite(days) && days >= 1 && days <= 3650) {
                    setDateFromDays(days);
                }
            });

            dateInput.addEventListener('input', () => {
                activeSource = 'date';
                setError('');
                const parsedDate = parseInputDate(dateInput.value);
                if (!parsedDate || parsedDate.getTime() < today.getTime()) {
                    return;
                }

                const days = calculateDaysFromDate(parsedDate);
                if (days > 3650) {
                    setError('Выбранная дата должна быть в пределах 3650 дней');
                    return;
                }

                input.value = String(days);
            });

            closeButton.addEventListener('click', () => cleanup(null));
            cancelButton.addEventListener('click', () => cleanup(null));
            backdrop.addEventListener('click', () => cleanup(null));
            document.addEventListener('keydown', onKeyDown);

            document.body.appendChild(modal);
            document.body.classList.add('renew-days-modal-open');
            requestAnimationFrame(() => {
                modal.classList.add('is-open');
                input.focus();
                input.select();
            });
        });
    }

    function getBlockReasonText(blockMode, blockReason) {
        const reason = String(blockReason || '').toLowerCase();
        const mode = String(blockMode || 'none').toLowerCase();
        const labels = {
            manual_temp: 'Временная блокировка администратором',
            manual_permanent: 'Бессрочная блокировка (вручную)',
            expired: 'Срок действия профиля истёк',
            traffic_limit: 'Превышен лимит трафика',
        };

        if (labels[reason]) {
            return labels[reason];
        }
        if (labels[mode]) {
            return labels[mode];
        }
        if (mode === 'temp') {
            return 'Временная блокировка';
        }
        if (mode === 'permanent') {
            return 'Бессрочная блокировка';
        }
        return null;
    }

    function formatRestrictionDate(value) {
        const raw = String(value || '').trim();
        if (!raw) {
            return null;
        }
        return raw.split(' ')[0];
    }

    function getProtocolLabel(protocol) {
        const normalized = String(protocol || '').toLowerCase();
        if (normalized === 'openvpn') {
            return 'OpenVPN';
        }
        if (normalized === 'wireguard' || normalized === 'amneziawg') {
            return 'WG / AWG';
        }
        return protocol || '—';
    }

    function renderRestrictionsPanel(row) {
        const panel = document.createElement('div');
        panel.className = 'client-restrictions-panel';

        const isBlocked = row.dataset.blocked === '1';
        const blockMode = (row.dataset.blockMode || 'none').toLowerCase();
        const blockReason = row.dataset.blockReason || row.dataset.wgBlockReason || '';
        const blockedUntil = formatRestrictionDate(row.dataset.blockedUntil || row.dataset.wgBlockUntil);
        const blockedDaysLeft = Number.parseInt(row.dataset.blockedDaysLeft || row.dataset.wgBlockedDaysLeft || '', 10);
        const blockDurationDays = Number.parseInt(row.dataset.blockDurationDays || row.dataset.wgBlockDurationDays || '', 10);
        const accessExpiresAt = formatRestrictionDate(row.dataset.accessExpiresAt || row.dataset.wgExpiresAt);
        const accessRemaining = typeof window.formatAccessRemaining === 'function'
            ? window.formatAccessRemaining(row.dataset.accessExpiresAt || row.dataset.wgExpiresAt || '')
            : null;
        const protocolLabel = getProtocolLabel(row.dataset.protocol);

        const trafficLimitHuman = row.dataset.trafficLimitHuman || '';
        const trafficLimitPeriodLabel = row.dataset.trafficLimitPeriodLabel || '';
        const trafficConsumedHuman = row.dataset.trafficConsumedHuman || '0 B';
        const trafficBytesLeftHuman = row.dataset.trafficBytesLeftHuman || '';
        const trafficLimitExceeded = row.dataset.trafficLimitExceeded === '1';
        const trafficLimitUnblockLabel = row.dataset.trafficLimitUnblockLabel || '';
        const limitBytes = Number(row.dataset.trafficLimitBytes || 0);
        const consumedBytes = Number(row.dataset.trafficConsumedBytes || 0);
        const trafficPercent = limitBytes > 0
            ? Math.min(100, Math.round((consumedBytes / limitBytes) * 1000) / 10)
            : 0;

        let trafficProgressClass = 'is-normal';
        if (trafficLimitExceeded || trafficPercent >= 100) {
            trafficProgressClass = 'is-exceeded';
        } else if (trafficPercent >= 85) {
            trafficProgressClass = 'is-warning';
        }

        let displayBlockMode = blockMode;
        let displayBlockReasonText = getBlockReasonText(blockMode, blockReason);
        if (blockMode === 'temp') {
            displayBlockMode = 'temp';
            displayBlockReasonText = getBlockReasonText('temp', blockReason);
        } else if (trafficLimitExceeded && trafficLimitHuman) {
            displayBlockMode = 'traffic_limit';
            displayBlockReasonText = 'Превышен лимит трафика';
        }

        const cards = [];

        cards.push(`
            <div class="client-restriction-card client-restriction-card--status ${isBlocked ? 'is-blocked' : 'is-active'}">
                <div class="client-restriction-label">Статус доступа</div>
                <div class="client-restriction-value">
                    <span class="client-restriction-badge">${isBlocked ? 'Заблокирован' : 'Активен'}</span>
                </div>
                <div class="client-restriction-meta">${escapeHtml(protocolLabel)}</div>
            </div>
        `);

        let accessValue = accessExpiresAt ? `до ${escapeHtml(accessExpiresAt)}` : 'не ограничен';
        let accessMeta = accessRemaining
            ? (accessRemaining === 'срок истёк' ? 'Срок истёк' : `Осталось ${escapeHtml(accessRemaining)}`)
            : (accessExpiresAt ? 'Срок не определён' : 'Бессрочный доступ');
        cards.push(`
            <div class="client-restriction-card">
                <div class="client-restriction-label">Срок доступа</div>
                <div class="client-restriction-value">${accessValue}</div>
                <div class="client-restriction-meta">${accessMeta}</div>
            </div>
        `);

        if (isBlocked && displayBlockReasonText) {
            let blockMetaParts = [];
            if (displayBlockMode === 'temp') {
                if (Number.isFinite(blockDurationDays) && blockDurationDays > 0) {
                    blockMetaParts.push(`Срок: ${blockDurationDays} дн.`);
                } else if (Number.isFinite(blockedDaysLeft) && blockedDaysLeft >= 0) {
                    blockMetaParts.push(`Осталось ${blockedDaysLeft} дн.`);
                }
                if (blockedUntil) {
                    blockMetaParts.push(`до ${escapeHtml(blockedUntil)}`);
                }
            } else if (displayBlockMode === 'traffic_limit') {
                if (trafficLimitHuman) {
                    blockMetaParts.push(`Лимит: ${escapeHtml(trafficLimitHuman)}${trafficLimitPeriodLabel ? ` / ${escapeHtml(trafficLimitPeriodLabel)}` : ''}`);
                }
                if (trafficLimitUnblockLabel) {
                    blockMetaParts.push(escapeHtml(trafficLimitUnblockLabel));
                }
            } else if (displayBlockMode === 'permanent') {
                blockMetaParts.push('Снятие только вручную');
            }

            cards.push(`
                <div class="client-restriction-card client-restriction-card--block">
                    <div class="client-restriction-label">Причина блокировки</div>
                    <div class="client-restriction-value">${escapeHtml(displayBlockReasonText)}</div>
                    ${blockMetaParts.length ? `<div class="client-restriction-meta">${blockMetaParts.join(' · ')}</div>` : ''}
                </div>
            `);
        } else if (!isBlocked) {
            cards.push(`
                <div class="client-restriction-card client-restriction-card--clear">
                    <div class="client-restriction-label">Блокировка</div>
                    <div class="client-restriction-value">Не активна</div>
                    <div class="client-restriction-meta">Клиент может подключаться</div>
                </div>
            `);
        }

        if (trafficLimitHuman) {
            cards.push(`
                <div class="client-restriction-card client-restriction-card--traffic ${trafficLimitExceeded ? 'is-exceeded' : ''}">
                    <div class="client-restriction-label">Лимит трафика</div>
                    <div class="client-restriction-value">
                        ${escapeHtml(trafficLimitHuman)}${trafficLimitPeriodLabel ? ` <span class="client-restriction-period">/ ${escapeHtml(trafficLimitPeriodLabel)}</span>` : ''}
                    </div>
                    <div class="client-restriction-progress ${trafficProgressClass}" aria-hidden="true">
                        <span class="client-restriction-progress-bar" style="width: ${trafficPercent}%"></span>
                    </div>
                    <div class="client-restriction-meta">
                        Использовано ${escapeHtml(trafficConsumedHuman)}${trafficBytesLeftHuman ? ` · осталось ${escapeHtml(trafficBytesLeftHuman)}` : ''}
                        ${trafficLimitExceeded ? ' · <strong>превышен</strong>' : ` · ${trafficPercent}%`}
                        ${trafficLimitExceeded && trafficLimitUnblockLabel ? `<br>${escapeHtml(trafficLimitUnblockLabel)}` : ''}
                    </div>
                </div>
            `);
        } else {
            cards.push(`
                <div class="client-restriction-card client-restriction-card--traffic-empty">
                    <div class="client-restriction-label">Лимит трафика</div>
                    <div class="client-restriction-value">Не задан</div>
                    <div class="client-restriction-meta">Ограничение по объёму не установлено</div>
                </div>
            `);
        }

        panel.innerHTML = `<div class="client-restrictions-grid">${cards.join('')}</div>`;

        return panel;
    }

    function renderActions(clientName) {
        if (!modalActions) {
            return;
        }

        modalActions.innerHTML = '';

        const escapedName = (window.CSS && typeof window.CSS.escape === 'function')
            ? window.CSS.escape(clientName)
            : clientName.replace(/"/g, '\\"');

        const activePane = document.querySelector('.tab-pane.active');
        const rowSelector = `.client-row[data-client-name="${escapedName}"]`;
        const row = (activePane && activePane.querySelector(rowSelector)) || document.querySelector(rowSelector);

        if (!row) {
            modalActions.innerHTML = '<div class="client-details-actions-note">Действия для этого клиента недоступны.</div>';
            return;
        }

        const downloadVpnUrl = row.dataset.downloadVpnUrl || '';
        const downloadAzUrl = row.dataset.downloadAzUrl || '';
        const qrVpnUrl = row.dataset.qrVpnUrl || '';
        const qrAzUrl = row.dataset.qrAzUrl || '';
        const oneTimeVpnEndpoint = row.dataset.oneTimeVpnEndpoint || '';
        const oneTimeAzEndpoint = row.dataset.oneTimeAzEndpoint || '';
        const canBlock = row.dataset.canBlock === '1' && row.dataset.protocol === 'openvpn';
        const canManage = row.dataset.canManage === '1';
        const isWgFamily = row.dataset.protocol === 'wireguard' || row.dataset.protocol === 'amneziawg';
        const canWgManage = canManage && isWgFamily;
        const deleteOption = row.dataset.deleteOption || '';
        const isBlocked = row.dataset.blocked === '1';

        const groupTitles = {
            manage: 'Управление',
            'manage-block': 'Блокировка',
            'manage-traffic': 'Лимит трафика',
            'manage-access': 'Срок действия',
            'manage-danger': 'Удаление',
            download: 'Скачать',
            qr: 'QR-коды',
            links: 'Одноразовые ссылки',
        };

        const groupNodes = {};
        let manageParentSection = null;
        let manageSubgroupsContainer = null;

        const ensureManageParent = () => {
            if (manageParentSection) {
                return;
            }

            manageParentSection = document.createElement('div');
            manageParentSection.className = 'client-details-actions-group client-details-actions-group--parent';

            const parentTitle = document.createElement('div');
            parentTitle.className = 'client-details-actions-group-title client-details-actions-group-title--parent';
            parentTitle.textContent = groupTitles.manage;

            manageSubgroupsContainer = document.createElement('div');
            manageSubgroupsContainer.className = 'client-details-actions-subgroups';

            manageParentSection.appendChild(parentTitle);
            manageParentSection.appendChild(manageSubgroupsContainer);
            modalActions.appendChild(manageParentSection);
        };

        const ensureGroupNode = (groupKey) => {
            if (groupNodes[groupKey]) {
                return groupNodes[groupKey];
            }

            const isManageSubgroup = groupKey.startsWith('manage-');

            if (isManageSubgroup) {
                ensureManageParent();

                const subgroup = document.createElement('div');
                subgroup.className = 'client-details-actions-subgroup';

                const title = document.createElement('div');
                title.className = 'client-details-actions-subgroup-title';
                title.textContent = groupTitles[groupKey] || 'Действия';

                const buttons = document.createElement('div');
                buttons.className = 'client-details-actions-group-buttons';

                subgroup.appendChild(title);
                subgroup.appendChild(buttons);
                manageSubgroupsContainer.appendChild(subgroup);

                groupNodes[groupKey] = buttons;
                return buttons;
            }

            const section = document.createElement('div');
            section.className = 'client-details-actions-group';

            const title = document.createElement('div');
            title.className = 'client-details-actions-group-title';
            title.textContent = groupTitles[groupKey] || 'Действия';

            const buttons = document.createElement('div');
            buttons.className = 'client-details-actions-group-buttons';

            section.appendChild(title);
            section.appendChild(buttons);
            modalActions.appendChild(section);

            groupNodes[groupKey] = buttons;
            return buttons;
        };

        const setActionButtonBusy = (button, busy) => {
            if (!button) {
                return;
            }
            button.disabled = !!busy;
            button.classList.toggle('is-busy', !!busy);
            button.setAttribute('aria-busy', busy ? 'true' : 'false');
        };

        const makeActionButton = ({
            label,
            icon,
            title,
            subtitle,
            variant = 'neutral',
            onClick,
            groupKey = 'manage-block',
        }) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `download-button client-details-action-btn client-details-action-btn--${variant}`;

            let displayIcon = icon || '';
            let displayTitle = title || '';
            let displaySubtitle = subtitle || '';

            if (label && !displayTitle) {
                const labelMatch = String(label).match(/^(\S+)\s+(.+)$/u);
                if (labelMatch) {
                    displayIcon = displayIcon || labelMatch[1];
                    displayTitle = labelMatch[2];
                } else {
                    displayTitle = String(label);
                }
            }

            if (!displayIcon) {
                displayIcon = '•';
            }

            button.innerHTML = `
                <span class="client-details-action-icon" aria-hidden="true">${displayIcon}</span>
                <span class="client-details-action-text">
                    <span class="client-details-action-title">${displayTitle}</span>
                    ${displaySubtitle ? `<span class="client-details-action-subtitle">${displaySubtitle}</span>` : ''}
                </span>
            `;
            button.addEventListener('click', onClick);
            const groupButtons = ensureGroupNode(groupKey);
            groupButtons.appendChild(button);
        };

        let actionsCount = 0;

        const addActionButton = (config) => {
            actionsCount += 1;
            makeActionButton(config);
        };

        if (canBlock) {
            const openvpnBlocked = row.dataset.blocked === '1';

            addActionButton({
                icon: '⛔',
                title: 'Временная блокировка',
                subtitle: 'OpenVPN',
                variant: 'danger',
                groupKey: 'manage-block',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const inputValue = await showActionModal({
                        title: 'Временная блокировка OpenVPN',
                        message: `Укажите срок блокировки для клиента "${clientName}"`,
                        mode: 'numberInput',
                        inputLabel: 'Срок временной блокировки (дни, 1-3650)',
                        inputDefault: '7',
                        inputMin: 1,
                        inputMax: 3650,
                        confirmLabel: 'Применить',
                        cancelLabel: 'Отмена',
                    });
                    if (inputValue === null) {
                        return;
                    }

                    setActionButtonBusy(button, true);
                    try {
                        const payload = await updateOpenVpnClientAccess(clientName, 'temp_block', inputValue);
                        if (typeof window.applyOpenVpnAccessPayloadToClientRows === 'function') {
                            window.applyOpenVpnAccessPayloadToClientRows(clientName, payload);
                        } else {
                            row.dataset.blocked = payload.is_blocked ? '1' : '0';
                            syncClientBlockedBadge(row);
                        }
                        renderActions(clientName);
                        showNotification(payload.message || 'Статус OpenVPN обновлён', 'success');
                    } catch (error) {
                        showNotification(error.message || 'Не удалось изменить статус OpenVPN', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });

            if (!openvpnBlocked) {
                addActionButton({
                    icon: '⛔',
                    title: 'Бессрочная блокировка',
                    subtitle: 'до ручной разблокировки',
                    variant: 'danger',
                    groupKey: 'manage-block',
                    onClick: async (event) => {
                        const button = event.currentTarget;
                        const confirmed = await showActionModal({
                            title: 'Бессрочная блокировка OpenVPN',
                            message: `Заблокировать клиента "${clientName}" до ручной разблокировки?`,
                            mode: 'confirm',
                            confirmLabel: 'Заблокировать',
                            cancelLabel: 'Отмена',
                        });
                        if (!confirmed) {
                            return;
                        }

                        setActionButtonBusy(button, true);
                        try {
                            const payload = await updateOpenVpnClientAccess(clientName, 'permanent_block');
                            if (typeof window.applyOpenVpnAccessPayloadToClientRows === 'function') {
                                window.applyOpenVpnAccessPayloadToClientRows(clientName, payload);
                            } else {
                                row.dataset.blocked = payload.is_blocked ? '1' : '0';
                                syncClientBlockedBadge(row);
                            }
                            renderActions(clientName);
                            showNotification(payload.message || 'Клиент заблокирован', 'success');
                        } catch (error) {
                            showNotification(error.message || 'Не удалось заблокировать клиента', 'error');
                        } finally {
                            setActionButtonBusy(button, false);
                        }
                    }
                });
            }

            if (openvpnBlocked) {
                addActionButton({
                    icon: '🔓',
                    title: 'Снять блокировку',
                    subtitle: 'OpenVPN',
                    variant: 'success',
                    groupKey: 'manage-block',
                    onClick: async (event) => {
                        const button = event.currentTarget;
                        setActionButtonBusy(button, true);
                        try {
                            const payload = await updateOpenVpnClientAccess(clientName, 'unblock');
                            if (typeof window.applyOpenVpnAccessPayloadToClientRows === 'function') {
                                window.applyOpenVpnAccessPayloadToClientRows(clientName, payload);
                            } else {
                                row.dataset.blocked = payload.is_blocked ? '1' : '0';
                                syncClientBlockedBadge(row);
                            }
                            renderActions(clientName);
                            showNotification(payload.message || 'Блокировка снята', 'success');
                        } catch (error) {
                            if (error.errorCode === 'traffic_limit_exceeded') {
                                showNotification(error.message || 'Клиент заблокирован по лимиту трафика', 'warning');
                            } else {
                                showNotification(error.message || 'Не удалось снять блокировку', 'error');
                            }
                        } finally {
                            setActionButtonBusy(button, false);
                        }
                    }
                });
            }

            /*
             * Legacy single-toggle control removed in favor of explicit
             * temp/permanent/unblock actions for OpenVPN.
             */
        }

        if (canManage) {
            const hasTrafficLimit = Boolean(row.dataset.trafficLimitBytes || row.dataset.trafficLimitHuman);
            addActionButton({
                icon: '📊',
                title: hasTrafficLimit ? 'Изменить лимит' : 'Установить лимит',
                subtitle: 'трафик · OpenVPN',
                variant: 'info',
                groupKey: 'manage-traffic',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const limitInput = await requestTrafficLimitInput(clientName, 'OpenVPN', row);
                    if (!limitInput) {
                        return;
                    }
                    setActionButtonBusy(button, true);
                    try {
                        const payload = await updateOpenVpnClientAccess(clientName, 'set_traffic_limit', limitInput);
                        if (typeof window.applyOpenVpnAccessPayloadToClientRows === 'function') {
                            window.applyOpenVpnAccessPayloadToClientRows(clientName, payload);
                        } else {
                            row.dataset.blocked = payload.is_blocked ? '1' : '0';
                            syncClientBlockedBadge(row);
                        }
                        renderActions(clientName);
                        showNotification(payload.message || 'Лимит трафика OpenVPN обновлён', 'success');
                    } catch (error) {
                        showNotification(error.message || 'Не удалось установить лимит трафика', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });

            if (hasTrafficLimit) {
                addActionButton({
                    icon: '📊',
                    title: 'Снять лимит',
                    subtitle: 'трафик · OpenVPN',
                    variant: 'info',
                    groupKey: 'manage-traffic',
                    onClick: async (event) => {
                        const button = event.currentTarget;
                        const confirmed = await showActionModal({
                            title: 'Снять лимит трафика OpenVPN',
                            message: `Снять лимит трафика для клиента "${clientName}"?`,
                            mode: 'confirm',
                            confirmLabel: 'Снять',
                            cancelLabel: 'Отмена',
                        });
                        if (!confirmed) {
                            return;
                        }
                        setActionButtonBusy(button, true);
                        try {
                            const payload = await updateOpenVpnClientAccess(clientName, 'clear_traffic_limit');
                            if (typeof window.applyOpenVpnAccessPayloadToClientRows === 'function') {
                                window.applyOpenVpnAccessPayloadToClientRows(clientName, payload);
                            } else {
                                row.dataset.blocked = payload.is_blocked ? '1' : '0';
                                syncClientBlockedBadge(row);
                            }
                            renderActions(clientName);
                            showNotification(payload.message || 'Лимит трафика OpenVPN снят', 'success');
                        } catch (error) {
                            showNotification(error.message || 'Не удалось снять лимит трафика', 'error');
                        } finally {
                            setActionButtonBusy(button, false);
                        }
                    }
                });
            }
        }

        if (canManage && row.dataset.protocol === 'openvpn') {
            addActionButton({
                icon: '♻',
                title: 'Продлить сертификат',
                variant: 'primary',
                groupKey: 'manage-access',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    if (!button) {
                        showNotification('Кнопка продления недоступна', 'error');
                        return;
                    }

                    const certDaysRaw = Number.parseInt(row.dataset.certDays || '', 10);
                    const defaultDays = Number.isFinite(certDaysRaw) && certDaysRaw > 0 && certDaysRaw <= 3650
                        ? String(certDaysRaw)
                        : '365';

                    const renewDays = await requestRenewDays(defaultDays);
                    if (renewDays === null) {
                        return;
                    }

                    setActionButtonBusy(button, true);

                    try {
                        const formData = new FormData();
                        formData.append('option', '1');
                        formData.append('client-name', clientName);
                        formData.append('work-term', String(renewDays));

                        const csrfInput = document.getElementById('csrf-token-value');
                        const csrfToken = csrfInput ? csrfInput.value : '';
                        if (csrfToken) {
                            formData.append('csrf_token', csrfToken);
                        }

                        const response = await fetch('/', {
                            method: 'POST',
                            body: formData,
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

                        if (!response.ok || !payload || !payload.success) {
                            const message = payload && (payload.message || payload.error)
                                ? (payload.message || payload.error)
                                : `Не удалось продлить сертификат (HTTP ${response.status})`;
                            throw new Error(message);
                        }

                        showNotification(payload.message || 'Сертификат продлён', 'success');
                        closeModal();
                        await refreshMainContent();
                    } catch (error) {
                        showNotification(error.message || 'Ошибка продления сертификата', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });
        }

        if (canWgManage) {
            addActionButton({
                icon: '⛔',
                title: 'Временная блокировка',
                subtitle: 'WG / AWG',
                variant: 'danger',
                groupKey: 'manage-block',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const inputValue = await showActionModal({
                        title: 'Временная блокировка WG/AWG',
                        message: `Укажите срок блокировки для клиента "${clientName}"`,
                        mode: 'numberInput',
                        inputLabel: 'Срок временной блокировки (дни, 1-3650)',
                        inputDefault: '7',
                        inputMin: 1,
                        inputMax: 3650,
                        confirmLabel: 'Применить',
                        cancelLabel: 'Отмена',
                    });
                    if (inputValue === null) {
                        return;
                    }

                    setActionButtonBusy(button, true);
                    try {
                        const payload = await updateWgClientAccess(clientName, 'temp_block', inputValue);
                        if (typeof window.applyWgAccessPayloadToClientRows === 'function') {
                            window.applyWgAccessPayloadToClientRows(clientName, payload);
                        } else if (typeof window.applyWgAccessPayloadToRow === 'function') {
                            window.applyWgAccessPayloadToRow(row, payload);
                        } else {
                            row.dataset.blocked = payload.is_blocked ? '1' : '0';
                            syncClientBlockedBadge(row);
                        }
                        renderActions(clientName);
                        showNotification(payload.message || 'Статус WG/AWG обновлён', 'success');
                    } catch (error) {
                        showNotification(error.message || 'Не удалось изменить статус WG/AWG', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });

            if (!isBlocked) {
                addActionButton({
                    icon: '⛔',
                    title: 'Бессрочная блокировка',
                    subtitle: 'до ручной разблокировки',
                    variant: 'danger',
                    groupKey: 'manage-block',
                    onClick: async (event) => {
                        const button = event.currentTarget;
                        const confirmed = await showActionModal({
                            title: 'Бессрочная блокировка WG/AWG',
                            message: `Заблокировать клиента "${clientName}" до ручной разблокировки?`,
                            mode: 'confirm',
                            confirmLabel: 'Заблокировать',
                            cancelLabel: 'Отмена',
                        });
                        if (!confirmed) {
                            return;
                        }

                        setActionButtonBusy(button, true);
                        try {
                            const payload = await updateWgClientAccess(clientName, 'permanent_block');
                            if (typeof window.applyWgAccessPayloadToClientRows === 'function') {
                                window.applyWgAccessPayloadToClientRows(clientName, payload);
                            } else if (typeof window.applyWgAccessPayloadToRow === 'function') {
                                window.applyWgAccessPayloadToRow(row, payload);
                            } else {
                                row.dataset.blocked = payload.is_blocked ? '1' : '0';
                                syncClientBlockedBadge(row);
                            }
                            renderActions(clientName);
                            showNotification(payload.message || 'Клиент заблокирован', 'success');
                        } catch (error) {
                            showNotification(error.message || 'Не удалось заблокировать клиента', 'error');
                        } finally {
                            setActionButtonBusy(button, false);
                        }
                    }
                });
            }

            const blockMode = (row.dataset.blockMode || 'none').toLowerCase();
            if (blockMode === 'temp' || blockMode === 'permanent' || blockMode === 'expired' || blockMode === 'traffic_limit') {
                addActionButton({
                    icon: '🔓',
                    title: 'Снять блокировку',
                    subtitle: 'WG / AWG',
                    variant: 'success',
                    groupKey: 'manage-block',
                    onClick: async (event) => {
                        const button = event.currentTarget;
                        if (isWgAccessExpired(row)) {
                            await showExpiredWgExtendModal(clientName, row);
                            return;
                        }

                        setActionButtonBusy(button, true);
                        try {
                            const payload = await updateWgClientAccess(clientName, 'unblock');
                            await applyWgAccessPayload(clientName, row, payload);
                            notifyWgAccessResult(payload, 'Блокировка снята');
                        } catch (error) {
                            if (error.errorCode === 'expired_requires_extend') {
                                await showExpiredWgExtendModal(clientName, row);
                            } else if (error.errorCode === 'traffic_limit_exceeded') {
                                showNotification(error.message || 'Клиент заблокирован по лимиту трафика', 'warning');
                            } else {
                                showNotification(error.message || 'Не удалось снять блокировку', 'error');
                            }
                        } finally {
                            setActionButtonBusy(button, false);
                        }
                    }
                });
            }

            const hasTrafficLimit = Boolean(row.dataset.trafficLimitBytes || row.dataset.trafficLimitHuman);
            addActionButton({
                icon: '📊',
                title: hasTrafficLimit ? 'Изменить лимит' : 'Установить лимит',
                subtitle: 'трафик · WG / AWG',
                variant: 'info',
                groupKey: 'manage-traffic',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const limitInput = await requestTrafficLimitInput(clientName, 'WG/AWG', row);
                    if (!limitInput) {
                        return;
                    }
                    setActionButtonBusy(button, true);
                    try {
                        const payload = await updateWgClientAccess(clientName, 'set_traffic_limit', limitInput);
                        await applyWgAccessPayload(clientName, row, payload);
                        notifyWgAccessResult(payload, 'Лимит трафика WG/AWG обновлён');
                        renderActions(clientName);
                    } catch (error) {
                        showNotification(error.message || 'Не удалось установить лимит трафика', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });

            if (hasTrafficLimit) {
                addActionButton({
                    icon: '📊',
                    title: 'Снять лимит',
                    subtitle: 'трафик · WG / AWG',
                    variant: 'info',
                    groupKey: 'manage-traffic',
                    onClick: async (event) => {
                        const button = event.currentTarget;
                        const confirmed = await showActionModal({
                            title: 'Снять лимит трафика WG/AWG',
                            message: `Снять лимит трафика для клиента "${clientName}"?`,
                            mode: 'confirm',
                            confirmLabel: 'Снять',
                            cancelLabel: 'Отмена',
                        });
                        if (!confirmed) {
                            return;
                        }
                        setActionButtonBusy(button, true);
                        try {
                            const payload = await updateWgClientAccess(clientName, 'clear_traffic_limit');
                            await applyWgAccessPayload(clientName, row, payload);
                            notifyWgAccessResult(payload, 'Лимит трафика WG/AWG снят');
                            renderActions(clientName);
                        } catch (error) {
                            showNotification(error.message || 'Не удалось снять лимит трафика', 'error');
                        } finally {
                            setActionButtonBusy(button, false);
                        }
                    }
                });
            }

            addActionButton({
                icon: '♻',
                title: 'Продлить срок',
                subtitle: 'WG / AWG',
                variant: 'primary',
                groupKey: 'manage-access',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    setActionButtonBusy(button, true);
                    try {
                        await requestWgExtendDays(clientName, row);
                    } catch (error) {
                        showNotification(error.message || 'Не удалось продлить срок WG/AWG', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });
        }

        if (canManage && deleteOption) {
            addActionButton({
                icon: '🗑',
                title: 'Удалить профиль',
                variant: 'destructive',
                groupKey: 'manage-danger',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const confirmed = await showActionModal({
                        title: 'Подтверждение удаления',
                        message: `Удалить профиль "${clientName}"?`,
                        mode: 'confirm',
                        confirmLabel: 'Удалить',
                        cancelLabel: 'Отмена',
                    });
                    if (!confirmed) {
                        return;
                    }

                    setActionButtonBusy(button, true);

                    try {
                        const formData = new FormData();
                        formData.append('option', deleteOption);
                        formData.append('client-name', clientName);

                        const csrfInput = document.getElementById('csrf-token-value');
                        const csrfToken = csrfInput ? csrfInput.value : '';
                        if (csrfToken) {
                            formData.append('csrf_token', csrfToken);
                        }

                        const response = await fetch('/', {
                            method: 'POST',
                            body: formData,
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

                        if (!response.ok || !payload || !payload.success) {
                            const message = payload && (payload.message || payload.error)
                                ? (payload.message || payload.error)
                                : `Не удалось удалить профиль (HTTP ${response.status})`;
                            throw new Error(message);
                        }

                        showNotification(payload.message || 'Профиль удалён', 'success');
                        closeModal();
                        await refreshMainContent();
                    } catch (error) {
                        showNotification(error.message || 'Ошибка удаления профиля', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });
        }

        if (downloadVpnUrl) {
            addActionButton({
                icon: '⬇️',
                title: 'Скачать VPN',
                variant: 'download',
                groupKey: 'download',
                onClick: () => {
                    window.location.href = downloadVpnUrl;
                }
            });
        }

        if (downloadAzUrl) {
            addActionButton({
                icon: '⬇️',
                title: 'Скачать AZ',
                variant: 'download',
                groupKey: 'download',
                onClick: () => {
                    window.location.href = downloadAzUrl;
                }
            });
        }

        if (qrVpnUrl) {
            addActionButton({
                icon: '📱',
                title: 'QR-код',
                subtitle: 'VPN',
                variant: 'neutral',
                groupKey: 'qr',
                onClick: () => {
                    showQRModal(qrVpnUrl);
                }
            });
        }

        if (qrAzUrl) {
            addActionButton({
                icon: '📱',
                title: 'QR-код',
                subtitle: 'Antizapret',
                variant: 'neutral',
                groupKey: 'qr',
                onClick: () => {
                    showQRModal(qrAzUrl);
                }
            });
        }

        if (oneTimeVpnEndpoint) {
            addActionButton({
                icon: '🔗',
                title: 'Одноразовая ссылка',
                subtitle: 'VPN',
                variant: 'neutral',
                groupKey: 'links',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    setActionButtonBusy(button, true);
                    try {
                        await generateOneTimeLink(oneTimeVpnEndpoint);
                        showNotification('Одноразовая ссылка скопирована в буфер', 'success');
                    } catch (error) {
                        showNotification(error.message || 'Ошибка формирования ссылки', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });
        }

        if (oneTimeAzEndpoint) {
            addActionButton({
                icon: '🔗',
                title: 'Одноразовая ссылка',
                subtitle: 'Antizapret',
                variant: 'neutral',
                groupKey: 'links',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    setActionButtonBusy(button, true);
                    try {
                        await generateOneTimeLink(oneTimeAzEndpoint);
                        showNotification('Одноразовая ссылка скопирована в буфер', 'success');
                    } catch (error) {
                        showNotification(error.message || 'Ошибка формирования ссылки', 'error');
                    } finally {
                        setActionButtonBusy(button, false);
                    }
                }
            });
        }

        if (actionsCount === 0) {
            modalActions.innerHTML = '<div class="client-details-actions-note">Для этого клиента нет доступных действий.</div>';
        }
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
            modalTrafficMeta.classList.remove('is-loading');
            modalTrafficMeta.innerHTML = renderDetailsPlaceholder('График недоступен: библиотека Chart.js не загружена');
            return;
        }

        modalTrafficMeta.classList.add('is-loading');
        modalTrafficMeta.innerHTML = renderDetailsPlaceholder('Загрузка графика...', true);

        try {
            const url = `/api/user-traffic-chart?client=${encodeURIComponent(currentClientName)}&range=${encodeURIComponent(currentRange)}`;
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            const labels = formatTrafficChartLabels(data);
            const vpnData = (data.vpn_bytes || []).map(v => Number(v || 0));
            const antData = (data.antizapret_bytes || []).map(v => Number(v || 0));

            if (!labels.length) {
                labels.push('Нет данных');
                vpnData.push(0);
                antData.push(0);
            }

            const clientRow = getClientRowByName(currentClientName);
            const limitBytes = clientRow ? clientRow.dataset.trafficLimitBytes : '';
            const limitPeriodDays = clientRow ? clientRow.dataset.trafficLimitPeriodDays : '';
            const limitDisplay = getChartTrafficLimitDisplay(limitBytes, limitPeriodDays, currentRange);

            const cumulativeData = [];
            let cumulativeTotal = 0;
            for (let index = 0; index < labels.length; index += 1) {
                cumulativeTotal += (vpnData[index] || 0) + (antData[index] || 0);
                cumulativeData.push(cumulativeTotal);
            }

            const datasets = [
                {
                    label: 'VPN',
                    data: vpnData,
                    borderColor: getThemeColor('--theme-chart-vpn-border', '#4caf50'),
                    backgroundColor: getThemeColor('--theme-chart-vpn-fill', 'rgba(76,175,80,0.12)'),
                    borderWidth: 2.2,
                    fill: false,
                    tension: 0.2,
                    pointRadius: 0,
                },
                {
                    label: 'Antizapret',
                    data: antData,
                    borderColor: getThemeColor('--theme-chart-antizapret-border', '#f44336'),
                    backgroundColor: getThemeColor('--theme-chart-antizapret-fill', 'rgba(244,67,54,0.12)'),
                    borderWidth: 1.6,
                    borderDash: [6, 4],
                    fill: false,
                    tension: 0.2,
                    pointRadius: 0,
                },
                {
                    label: 'Накоплено',
                    data: cumulativeData,
                    borderColor: getThemeColor('--theme-chart-cumulative-border', '#ffb74d'),
                    backgroundColor: 'rgba(255,183,77,0.08)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.2,
                    pointRadius: 0,
                },
            ];

            if (limitDisplay) {
                datasets.push({
                    label: limitDisplay.label,
                    data: labels.map(() => limitDisplay.value),
                    borderColor: getThemeColor('--theme-chart-limit-border', '#ffb74d'),
                    backgroundColor: 'rgba(255,183,77,0.1)',
                    borderWidth: 2.6,
                    borderDash: [8, 5],
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                });
            }

            if (detailsChart) {
                detailsChart.destroy();
            }

            detailsChart = new Chart(modalChartCanvas, {
                type: 'line',
                data: {
                    labels,
                    datasets,
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
                                maxTicksLimit: currentRange === '1h' ? 12 : (currentRange === '24h' ? 24 : 10)
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

            const metaParts = [
                `VPN: ${data.total_vpn_human || humanBytes(data.total_vpn)}`,
                `Antizapret: ${data.total_antizapret_human || humanBytes(data.total_antizapret)}`,
                `Итого: ${data.total_human || humanBytes(data.total)}`,
            ];
            if (limitDisplay) {
                metaParts.push(limitDisplay.label);
            }
            renderTrafficMeta(metaParts);
        } catch (error) {
            modalTrafficMeta.classList.remove('is-loading');
            modalTrafficMeta.innerHTML = renderDetailsPlaceholder(`Не удалось загрузить график: ${error.message}`);
        }
    }

    function applyClientDetailsToModal(name, payload) {
        const connectedItem = payload.connected[name] || {};
        const trafficItem = payload.traffic[name] || null;

        renderSummaryGrid(connectedItem, trafficItem);
        renderTrafficStats(trafficItem);
        renderConnections(name);
    }

    async function openModal(clientName) {
        const name = String(clientName || '').trim();
        if (!name) {
            showNotification('Не удалось определить имя клиента', 'error');
            return;
        }

        currentClientName = name;

        if (modalTitle) {
            modalTitle.textContent = name;
        }

        const row = getClientRowByName(name);
        renderHeaderChips(row);

        if (modalSummary) {
            modalSummary.innerHTML = renderDetailsPlaceholder('Загрузка сведений...', true);
        }

        if (modalTrafficQuick) {
            modalTrafficQuick.innerHTML = renderDetailsPlaceholder('Загрузка статистики...', true);
        }

        if (modalTrafficMeta) {
            modalTrafficMeta.classList.add('is-loading');
            modalTrafficMeta.innerHTML = renderDetailsPlaceholder('Загрузка графика...', true);
        }

        if (modalConnections) {
            modalConnections.innerHTML = renderDetailsPlaceholder('Загрузка подключений...', true);
        }

        renderRestrictionsForClient(name);
        renderActions(name);
        setActiveRangeButtons();
        setModalOpen(true);

        let payload = getIndexClientDetailsPayload();
        if (!hasClientDetailsData(payload)) {
            try {
                payload = await loadIndexClientDetailsPayload();
            } catch (error) {
                if (modalSummary) {
                    modalSummary.innerHTML = renderDetailsPlaceholder(`Не удалось загрузить сведения: ${error.message}`);
                }
                if (modalTrafficQuick) {
                    modalTrafficQuick.innerHTML = renderDetailsPlaceholder('Повторите попытку позже.');
                }
                if (modalConnections) {
                    modalConnections.innerHTML = '<div class="client-details-note">Данные подключений недоступны.</div>';
                }
                showNotification(error.message || 'Не удалось загрузить данные клиента', 'error');
                loadTrafficChart();
                return;
            }
        }

        applyClientDetailsToModal(name, payload);
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
        const row = event.target.closest('.client-row');
        if (!row) {
            return;
        }

        if (event.target.closest('button, a, input, label, textarea, select')) {
            return;
        }

        event.preventDefault();
        const clientName = row.getAttribute('data-client-name') || '';
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
