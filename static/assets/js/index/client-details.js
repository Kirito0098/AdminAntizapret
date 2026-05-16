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
                throw new Error(payload.message || 'Ошибка загрузки данных клиента');
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
            return;
        }
    }

    renderIndexTrafficMiniSummary(payload);
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
            const message = payload && payload.message
                ? payload.message
                : `Не удалось создать ссылку (HTTP ${response.status})`;
            throw new Error(message);
        }

        await copyTextToClipboard(payload.download_url);
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
        const deleteOption = row.dataset.deleteOption || '';
        const isBlocked = row.dataset.blocked === '1';

        const groupTitles = {
            manage: 'Управление',
            download: 'Скачать',
            qr: 'QR',
            links: 'Одноразовые ссылки',
        };

        const groupNodes = {};

        const ensureGroupNode = (groupKey) => {
            if (groupNodes[groupKey]) {
                return groupNodes[groupKey];
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

        const makeActionButton = ({ label, onClick, groupKey = 'manage' }) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'download-button client-details-action-btn';
            button.textContent = label;
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
            addActionButton({
                label: isBlocked ? '🔓 Разблокировать' : '⛔ Заблокировать',
                groupKey: 'manage',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const currentlyBlocked = row.dataset.blocked === '1';
                    const nextBlocked = !currentlyBlocked;
                    const originalText = button.textContent;

                    button.disabled = true;
                    button.textContent = '...';

                    try {
                        const payload = await updateClientBlockState(clientName, nextBlocked);
                        row.dataset.blocked = nextBlocked ? '1' : '0';
                        syncClientBlockedBadge(row);
                        button.textContent = nextBlocked
                            ? '🔓 Разблокировать'
                            : '⛔ Заблокировать';
                        showNotification(payload.message || 'Статус блокировки обновлён', 'success');
                    } catch (error) {
                        button.textContent = originalText;
                        showNotification(error.message || 'Не удалось изменить блокировку клиента', 'error');
                    } finally {
                        button.disabled = false;
                    }
                }
            });
        }

        if (canManage && row.dataset.protocol === 'openvpn') {
            addActionButton({
                label: '♻ Продлить сертификат',
                groupKey: 'manage',
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

                    const originalText = button.textContent;
                    button.disabled = true;
                    button.textContent = '...';

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
                            const message = payload && payload.message
                                ? payload.message
                                : `Не удалось продлить сертификат (HTTP ${response.status})`;
                            throw new Error(message);
                        }

                        showNotification(payload.message || 'Сертификат продлён', 'success');
                        closeModal();
                        await refreshMainContent();
                    } catch (error) {
                        showNotification(error.message || 'Ошибка продления сертификата', 'error');
                    } finally {
                        button.disabled = false;
                        button.textContent = originalText;
                    }
                }
            });
        }

        if (canManage && deleteOption) {
            addActionButton({
                label: '🗑 Удалить профиль',
                groupKey: 'manage',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const confirmed = window.confirm(`Удалить профиль "${clientName}"?`);
                    if (!confirmed) {
                        return;
                    }

                    const originalText = button.textContent;
                    button.disabled = true;
                    button.textContent = '...';

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
                            const message = payload && payload.message
                                ? payload.message
                                : `Не удалось удалить профиль (HTTP ${response.status})`;
                            throw new Error(message);
                        }

                        showNotification(payload.message || 'Профиль удалён', 'success');
                        closeModal();
                        await refreshMainContent();
                    } catch (error) {
                        showNotification(error.message || 'Ошибка удаления профиля', 'error');
                    } finally {
                        button.disabled = false;
                        button.textContent = originalText;
                    }
                }
            });
        }

        if (downloadVpnUrl) {
            addActionButton({
                label: '⬇️ Скачать VPN',
                groupKey: 'download',
                onClick: () => {
                    window.location.href = downloadVpnUrl;
                }
            });
        }

        if (downloadAzUrl) {
            addActionButton({
                label: '⬇️ Скачать AZ',
                groupKey: 'download',
                onClick: () => {
                    window.location.href = downloadAzUrl;
                }
            });
        }

        if (qrVpnUrl) {
            addActionButton({
                label: '📱 QR VPN',
                groupKey: 'qr',
                onClick: () => {
                    showQRModal(qrVpnUrl);
                }
            });
        }

        if (qrAzUrl) {
            addActionButton({
                label: '📱 QR AZ',
                groupKey: 'qr',
                onClick: () => {
                    showQRModal(qrAzUrl);
                }
            });
        }

        if (oneTimeVpnEndpoint) {
            addActionButton({
                label: '🔗 Ссылка VPN',
                groupKey: 'links',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const originalText = button.textContent;
                    button.disabled = true;
                    button.textContent = '...';
                    try {
                        await generateOneTimeLink(oneTimeVpnEndpoint);
                        showNotification('Одноразовая ссылка скопирована в буфер', 'success');
                    } catch (error) {
                        showNotification(error.message || 'Ошибка формирования ссылки', 'error');
                    } finally {
                        button.disabled = false;
                        button.textContent = originalText;
                    }
                }
            });
        }

        if (oneTimeAzEndpoint) {
            addActionButton({
                label: '🔗 Ссылка AZ',
                groupKey: 'links',
                onClick: async (event) => {
                    const button = event.currentTarget;
                    const originalText = button.textContent;
                    button.disabled = true;
                    button.textContent = '...';
                    try {
                        await generateOneTimeLink(oneTimeAzEndpoint);
                        showNotification('Одноразовая ссылка скопирована в буфер', 'success');
                    } catch (error) {
                        showNotification(error.message || 'Ошибка формирования ссылки', 'error');
                    } finally {
                        button.disabled = false;
                        button.textContent = originalText;
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
            const labels = formatTrafficChartLabels(data);
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

            modalTrafficMeta.textContent =
                `VPN: ${data.total_vpn_human || humanBytes(data.total_vpn)} | ` +
                `Antizapret: ${data.total_antizapret_human || humanBytes(data.total_antizapret)} | ` +
                `Итого: ${data.total_human || humanBytes(data.total)}`;
        } catch (error) {
            modalTrafficMeta.textContent = `Не удалось загрузить график: ${error.message}`;
        }
    }

    function applyClientDetailsToModal(name, payload) {
        const connectedItem = payload.connected[name] || {};
        const trafficItem = payload.traffic[name] || null;

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

        if (modalSummary) {
            modalSummary.textContent = 'Загрузка сведений о клиенте...';
        }

        if (modalTrafficQuick) {
            modalTrafficQuick.textContent = 'Загрузка статистики...';
        }

        renderActions(name);
        setActiveRangeButtons();
        setModalOpen(true);

        let payload = getIndexClientDetailsPayload();
        if (!hasClientDetailsData(payload)) {
            try {
                payload = await loadIndexClientDetailsPayload();
            } catch (error) {
                if (modalSummary) {
                    modalSummary.textContent = `Не удалось загрузить сведения: ${error.message}`;
                }
                if (modalTrafficQuick) {
                    modalTrafficQuick.textContent = 'Повторите попытку позже.';
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
