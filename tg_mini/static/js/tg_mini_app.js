document.addEventListener("DOMContentLoaded", function () {
    const appRoot = document.getElementById("tgMiniApp");
    if (!appRoot) {
        return;
    }

    const state = {
        dashboard: null,
        selectedRange: "1d",
        selectedClient: "",
        mainProtocol: "openvpn",
        mainSearch: "",
        mainStatusFilter: "all",
        dashboardShowAllConnected: false,
        dashboardShowAllTraffic: false,
        dashboardPreviewLimit: 6,
        mainData: {
            openvpn: [],
            amneziawg: [],
            wireguard: [],
        },
        protocolChart: null,
        trafficChart: null,
        antizapretSchema: [],
    };

    const DASHBOARD_UI_PREFS_KEY = "tgMiniDashboardUiPrefsV1";

    const isAdmin = appRoot.dataset.isAdmin === "1";

    const dashboardStatusEl = document.getElementById("tgMiniDashboardStatus");
    const settingsStatusEl = document.getElementById("tgMiniSettingsStatus");
    const mainStatusEl = document.getElementById("tgMiniMainStatus");
    const botDeliveryIndicatorEl = document.getElementById("tgMiniBotDeliveryIndicator");
    const botDeliveryTextEl = document.getElementById("tgMiniBotDeliveryText");

    function setThemeClass(_scheme) {
        /* Внешний вид совпадает с веб-панелью (theme.css); не переключаем палитру по Telegram. */
    }

    function applyTelegramThemeParams(_themeParams) {
        /* Не подменяем CSS-переменные панели цветами Telegram — дизайн как на сайте. */
    }

    function applySystemThemeFallback() {
        /* Браузер без Telegram WebApp: остаёмся на стилях панели из base.html. */
    }

    function initTelegramWebApp() {
        try {
            if (window.Telegram && window.Telegram.WebApp) {
                document.body.classList.add("is-telegram-webview");
                const tg = window.Telegram.WebApp;
                tg.ready();
                tg.expand();
                if (typeof tg.enableClosingConfirmation === "function") {
                    tg.enableClosingConfirmation();
                }
                if (typeof tg.onEvent === "function") {
                    tg.onEvent("themeChanged", function () {
                        /* Зарезервировано: при необходимости можно подстроить только мелочи. */
                    });
                }
                return;
            }

            applySystemThemeFallback();
        } catch (_error) {
            applySystemThemeFallback();
        }
    }

    function renderEmptyState(title, hint, icon) {
        return (
            '<div class="tg-mini-empty">' +
            '<div class="tg-mini-empty-icon" aria-hidden="true">' + (icon || "📭") + "</div>" +
            '<p class="tg-mini-empty-title">' + escapeHtml(title || "Нет данных") + "</p>" +
            (hint ? '<p class="tg-mini-empty-hint">' + escapeHtml(hint) + "</p>" : "") +
            "</div>"
        );
    }

    function bindCollapsibleToggle(toggleEl, targetEl, options) {
        if (!toggleEl || !targetEl) {
            return;
        }

        const opts = options || {};
        const storageKey = opts.storageKey || "";
        const defaultExpanded = Boolean(opts.defaultExpanded);

        function setExpanded(expanded) {
            toggleEl.setAttribute("aria-expanded", expanded ? "true" : "false");
            targetEl.hidden = !expanded;
            if (opts.itemClass && opts.itemEl) {
                opts.itemEl.classList.toggle(opts.itemClass, expanded);
            }
            if (storageKey) {
                try {
                    window.localStorage.setItem(storageKey, expanded ? "1" : "0");
                } catch (_error) {
                    // Ignore storage errors.
                }
            }
        }

        let initialExpanded = defaultExpanded;
        if (storageKey) {
            try {
                const stored = window.localStorage.getItem(storageKey);
                if (stored === "1") {
                    initialExpanded = true;
                } else if (stored === "0") {
                    initialExpanded = false;
                }
            } catch (_error) {
                // Ignore storage errors.
            }
        }

        setExpanded(initialExpanded);

        toggleEl.addEventListener("click", function () {
            const nextExpanded = toggleEl.getAttribute("aria-expanded") !== "true";
            setExpanded(nextExpanded);
        });
    }

    function initMobileChrome() {
        bindCollapsibleToggle(
            document.getElementById("tgMiniHeaderToggle"),
            document.getElementById("tgMiniHeaderDetails"),
            { defaultExpanded: false }
        );

        bindCollapsibleToggle(
            document.getElementById("tgMiniToolbarFiltersToggle"),
            document.getElementById("tgMiniToolbarFiltersBody"),
            {
                storageKey: "tgMiniToolbarFiltersOpenV1",
                defaultExpanded: false,
            }
        );
    }

    function bindClientActionToggles(container) {
        if (!container) {
            return;
        }

        container.querySelectorAll(".tg-mini-main-actions-toggle").forEach(function (toggleBtn) {
            toggleBtn.addEventListener("click", function () {
                const item = toggleBtn.closest(".tg-mini-main-item");
                const expandBlock = item ? item.querySelector(".tg-mini-main-actions-expand") : null;
                if (!item || !expandBlock) {
                    return;
                }

                const nextOpen = !item.classList.contains("is-actions-open");
                item.classList.toggle("is-actions-open", nextOpen);
                toggleBtn.setAttribute("aria-expanded", nextOpen ? "true" : "false");
            });
        });
    }

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return (meta && meta.content) || "";
    }

    function setStatus(element, text, kind) {
        if (!element) {
            return;
        }
        element.textContent = text;
        element.classList.remove("is-error", "is-success", "is-loading");
        if (kind === "error") {
            element.classList.add("is-error");
        }
        if (kind === "success") {
            element.classList.add("is-success");
        }
        if (kind === "loading") {
            element.classList.add("is-loading");
        }
    }

    function loadDashboardUiPrefs() {
        try {
            const raw = window.localStorage.getItem(DASHBOARD_UI_PREFS_KEY);
            if (!raw) {
                return;
            }

            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === "object") {
                if (typeof parsed.showAllConnected === "boolean") {
                    state.dashboardShowAllConnected = parsed.showAllConnected;
                }
                if (typeof parsed.showAllTraffic === "boolean") {
                    state.dashboardShowAllTraffic = parsed.showAllTraffic;
                }
            }
        } catch (_error) {
            // Ignore storage parsing/access errors.
        }
    }

    function saveDashboardUiPrefs() {
        try {
            window.localStorage.setItem(
                DASHBOARD_UI_PREFS_KEY,
                JSON.stringify({
                    showAllConnected: Boolean(state.dashboardShowAllConnected),
                    showAllTraffic: Boolean(state.dashboardShowAllTraffic),
                })
            );
        } catch (_error) {
            // Ignore storage quota/access errors.
        }
    }

    function setBotDeliveryIndicator(kind, text) {
        if (!botDeliveryIndicatorEl || !botDeliveryTextEl) {
            return;
        }

        botDeliveryIndicatorEl.classList.remove("is-idle", "is-checking", "is-ok", "is-error");
        if (kind === "checking") {
            botDeliveryIndicatorEl.classList.add("is-checking");
        } else if (kind === "ok") {
            botDeliveryIndicatorEl.classList.add("is-ok");
        } else if (kind === "error") {
            botDeliveryIndicatorEl.classList.add("is-error");
        } else {
            botDeliveryIndicatorEl.classList.add("is-idle");
        }

        botDeliveryTextEl.textContent = text || "Статус не проверен";
    }

    function shortBotDeliveryErrorMessage(errorText) {
        const text = String(errorText || "");
        const lower = text.toLowerCase();
        if (lower.includes("start") || lower.includes("forbidden") || lower.includes("chat not found")) {
            return "Нажмите Start у бота";
        }
        return "Связь с ботом недоступна";
    }

    async function parseJsonResponse(response) {
        let payload = {};
        try {
            payload = await response.json();
        } catch (_error) {
            payload = {};
        }
        return payload;
    }

    function openTgMiniModalShell(contentHtml) {
        const modal = document.createElement("div");
        modal.className = "tg-mini-modal";
        modal.innerHTML =
            '<div class="tg-mini-modal-backdrop"></div>' +
            '<div class="tg-mini-modal-dialog" role="dialog" aria-modal="true">' +
            '<div class="tg-mini-modal-handle" aria-hidden="true"></div>' +
            contentHtml +
            "</div>";
        return modal;
    }

    function showTgMiniActionModal(options) {
        const config = options || {};
        const mode = config.mode || "confirm";

        return new Promise(function (resolve) {
            const useNumberInput = mode === "numberInput";
            const modal = openTgMiniModalShell(
                '<button type="button" class="tg-mini-modal-close" aria-label="Закрыть">×</button>' +
                '<div class="tg-mini-modal-header">' +
                '<h4>' + escapeHtml(config.title || "Подтвердите действие") + "</h4>" +
                (config.message ? '<p class="tg-mini-modal-message">' + escapeHtml(config.message) + "</p>" : "") +
                "</div>" +
                '<form class="tg-mini-modal-form">' +
                (useNumberInput
                    ? '<label for="tgMiniModalInput">' + escapeHtml(config.inputLabel || "Значение") + "</label>" +
                      '<input id="tgMiniModalInput" type="number" inputmode="numeric" min="' +
                      escapeHtml(String(config.inputMin || 1)) +
                      '" max="' +
                      escapeHtml(String(config.inputMax || 3650)) +
                      '" value="' +
                      escapeHtml(String(config.inputDefault || "1")) +
                      '" required />'
                    : "") +
                '<div class="tg-mini-modal-error" aria-live="polite"></div>' +
                '<div class="tg-mini-modal-actions">' +
                '<button type="button" class="tg-mini-btn tg-mini-btn-ghost tg-mini-modal-cancel">' +
                escapeHtml(config.cancelLabel || "Отмена") +
                "</button>" +
                '<button type="submit" class="tg-mini-btn tg-mini-modal-submit">' +
                escapeHtml(config.confirmLabel || "OK") +
                "</button>" +
                "</div>" +
                "</form>"
            );

            const form = modal.querySelector(".tg-mini-modal-form");
            const inputNode = modal.querySelector("#tgMiniModalInput");
            const errorNode = modal.querySelector(".tg-mini-modal-error");
            const closeButton = modal.querySelector(".tg-mini-modal-close");
            const cancelButton = modal.querySelector(".tg-mini-modal-cancel");
            const backdrop = modal.querySelector(".tg-mini-modal-backdrop");

            let resolved = false;
            const cleanup = function (value) {
                if (resolved) {
                    return;
                }
                resolved = true;
                document.removeEventListener("keydown", onKeyDown);
                document.body.classList.remove("tg-mini-modal-open");
                modal.remove();
                resolve(value === undefined ? null : value);
            };

            const onKeyDown = function (event) {
                if (event.key === "Escape") {
                    cleanup(null);
                }
            };

            form.addEventListener("submit", function (event) {
                event.preventDefault();
                if (errorNode) {
                    errorNode.textContent = "";
                }

                if (!useNumberInput) {
                    cleanup(true);
                    return;
                }

                const raw = String((inputNode && inputNode.value) || "").trim();
                if (!/^\d+$/.test(raw)) {
                    if (errorNode) {
                        errorNode.textContent =
                            "Введите целое число от " + config.inputMin + " до " + config.inputMax;
                    }
                    return;
                }

                const parsed = Number.parseInt(raw, 10);
                if (
                    !Number.isFinite(parsed) ||
                    parsed < Number(config.inputMin || 1) ||
                    parsed > Number(config.inputMax || 3650)
                ) {
                    if (errorNode) {
                        errorNode.textContent =
                            "Значение должно быть в диапазоне " + config.inputMin + "-" + config.inputMax;
                    }
                    return;
                }

                cleanup(parsed);
            });

            if (closeButton) {
                closeButton.addEventListener("click", function () {
                    cleanup(null);
                });
            }
            if (cancelButton) {
                cancelButton.addEventListener("click", function () {
                    cleanup(null);
                });
            }
            if (backdrop) {
                backdrop.addEventListener("click", function () {
                    cleanup(null);
                });
            }

            document.body.appendChild(modal);
            document.body.classList.add("tg-mini-modal-open");
            document.addEventListener("keydown", onKeyDown);
            requestAnimationFrame(function () {
                modal.classList.add("is-open");
                if (useNumberInput && inputNode) {
                    inputNode.focus();
                    inputNode.select();
                }
            });
        });
    }

    function isWgProtocol(protocol) {
        const key = String(protocol || "").toLowerCase();
        return key === "wireguard" || key === "amneziawg";
    }

    function getProtocolManageLabels(protocol) {
        const key = String(protocol || "").toLowerCase();
        if (key === "openvpn") {
            return { short: "OpenVPN", traffic: "OpenVPN" };
        }
        if (key === "wireguard") {
            return { short: "WireGuard", traffic: "WireGuard" };
        }
        if (key === "amneziawg") {
            return { short: "AmneziaWG", traffic: "AmneziaWG" };
        }
        return { short: "WG/AWG", traffic: "WG/AWG" };
    }

    function showTgMiniTrafficLimitInput(clientName, protocolLabel, defaultPeriodDays) {
        const period = String(defaultPeriodDays || "7");
        const label = String(protocolLabel || "OpenVPN");

        return new Promise(function (resolve) {
            const modal = openTgMiniModalShell(
                '<button type="button" class="tg-mini-modal-close" aria-label="Закрыть">×</button>' +
                '<div class="tg-mini-modal-header">' +
                '<h4>Лимит трафика ' + escapeHtml(label) + "</h4>" +
                '<p class="tg-mini-modal-message">Максимальный объём трафика за выбранный период</p>' +
                "</div>" +
                '<div class="tg-mini-modal-client">' + escapeHtml(clientName) + "</div>" +
                '<form class="tg-mini-modal-form">' +
                '<div class="tg-mini-modal-fields">' +
                '<div><label for="tgMiniLimitValue">Объём</label><input id="tgMiniLimitValue" type="number" min="0.01" step="any" value="10" /></div>' +
                '<div><label for="tgMiniLimitUnit">Единица</label><select id="tgMiniLimitUnit"><option value="mb">MB</option><option value="gb" selected>GB</option><option value="tb">TB</option></select></div>' +
                '<div class="tg-mini-modal-field-period"><label for="tgMiniLimitPeriod">Период</label><select id="tgMiniLimitPeriod">' +
                '<option value="1"' + (period === "1" ? " selected" : "") + ">За сутки</option>" +
                '<option value="7"' + (period === "7" ? " selected" : "") + ">За неделю</option>" +
                '<option value="30"' + (period === "30" ? " selected" : "") + ">За месяц</option>" +
                "</select></div></div>" +
                '<div class="tg-mini-modal-presets" role="group" aria-label="Быстрый выбор лимита">' +
                '<button type="button" class="tg-mini-modal-preset" data-value="1" data-unit="gb">1 GB</button>' +
                '<button type="button" class="tg-mini-modal-preset" data-value="10" data-unit="gb">10 GB</button>' +
                '<button type="button" class="tg-mini-modal-preset" data-value="50" data-unit="gb">50 GB</button>' +
                '<button type="button" class="tg-mini-modal-preset" data-value="100" data-unit="gb">100 GB</button>' +
                "</div>" +
                '<p class="tg-mini-modal-hint">При превышении лимита клиент будет автоматически заблокирован до конца выбранного периода.</p>' +
                '<div class="tg-mini-modal-error" aria-live="polite"></div>' +
                '<div class="tg-mini-modal-actions">' +
                '<button type="button" class="tg-mini-btn tg-mini-btn-ghost tg-mini-modal-cancel">Отмена</button>' +
                '<button type="submit" class="tg-mini-btn">Установить</button>' +
                "</div></form>"
            );

            const form = modal.querySelector(".tg-mini-modal-form");
            const valueInput = modal.querySelector("#tgMiniLimitValue");
            const unitSelect = modal.querySelector("#tgMiniLimitUnit");
            const periodSelect = modal.querySelector("#tgMiniLimitPeriod");
            const errorNode = modal.querySelector(".tg-mini-modal-error");
            const closeButton = modal.querySelector(".tg-mini-modal-close");
            const cancelButton = modal.querySelector(".tg-mini-modal-cancel");
            const backdrop = modal.querySelector(".tg-mini-modal-backdrop");
            const presetButtons = modal.querySelectorAll(".tg-mini-modal-preset");

            const syncPresetState = function () {
                const currentValue = Number.parseFloat(String((valueInput && valueInput.value) || "").trim());
                const currentUnit = String((unitSelect && unitSelect.value) || "gb").trim().toLowerCase();
                presetButtons.forEach(function (presetButton) {
                    const presetValue = Number.parseFloat(presetButton.getAttribute("data-value") || "");
                    const presetUnit = String(presetButton.getAttribute("data-unit") || "").trim().toLowerCase();
                    const isActive =
                        Number.isFinite(currentValue) && currentValue === presetValue && currentUnit === presetUnit;
                    presetButton.classList.toggle("is-active", isActive);
                });
            };

            presetButtons.forEach(function (presetButton) {
                presetButton.addEventListener("click", function () {
                    if (valueInput) {
                        valueInput.value = presetButton.getAttribute("data-value") || "";
                    }
                    if (unitSelect) {
                        unitSelect.value = presetButton.getAttribute("data-unit") || "gb";
                    }
                    if (errorNode) {
                        errorNode.textContent = "";
                    }
                    syncPresetState();
                    if (valueInput) {
                        valueInput.focus();
                    }
                });
            });

            if (valueInput) {
                valueInput.addEventListener("input", syncPresetState);
            }
            if (unitSelect) {
                unitSelect.addEventListener("change", syncPresetState);
            }

            let resolved = false;
            const cleanup = function (value) {
                if (resolved) {
                    return;
                }
                resolved = true;
                document.removeEventListener("keydown", onKeyDown);
                document.body.classList.remove("tg-mini-modal-open");
                modal.remove();
                resolve(value === undefined ? null : value);
            };

            const onKeyDown = function (event) {
                if (event.key === "Escape") {
                    cleanup(null);
                }
            };

            form.addEventListener("submit", function (event) {
                event.preventDefault();
                const limitValue = Number.parseFloat(String((valueInput && valueInput.value) || "").trim());
                const limitUnit = String((unitSelect && unitSelect.value) || "mb").trim().toLowerCase();
                const limitPeriodDays = String((periodSelect && periodSelect.value) || "7").trim();
                if (!Number.isFinite(limitValue) || limitValue <= 0) {
                    if (errorNode) {
                        errorNode.textContent = "Укажите положительное значение лимита.";
                    }
                    return;
                }
                if (!["1", "7", "30"].includes(limitPeriodDays)) {
                    if (errorNode) {
                        errorNode.textContent = "Период лимита должен быть 1, 7 или 30 дней.";
                    }
                    return;
                }
                cleanup({
                    limitValue: String(limitValue),
                    limitUnit: limitUnit,
                    limitPeriodDays: limitPeriodDays,
                });
            });

            if (closeButton) {
                closeButton.addEventListener("click", function () {
                    cleanup(null);
                });
            }
            if (cancelButton) {
                cancelButton.addEventListener("click", function () {
                    cleanup(null);
                });
            }
            if (backdrop) {
                backdrop.addEventListener("click", function () {
                    cleanup(null);
                });
            }

            document.body.appendChild(modal);
            document.body.classList.add("tg-mini-modal-open");
            document.addEventListener("keydown", onKeyDown);
            requestAnimationFrame(function () {
                modal.classList.add("is-open");
                syncPresetState();
                if (valueInput) {
                    valueInput.focus();
                    valueInput.select();
                }
            });
        });
    }

    function showTgMiniRenewDays(defaultDays) {
        const initialDays = Number.parseInt(String(defaultDays || "365"), 10);
        const safeDays =
            Number.isFinite(initialDays) && initialDays >= 1 && initialDays <= 3650 ? initialDays : 365;

        return showTgMiniActionModal({
            title: "Продлить сертификат",
            message: "Укажите новый срок сертификата для клиента.",
            mode: "numberInput",
            inputLabel: "Срок действия (дни, 1-3650)",
            inputDefault: String(safeDays),
            inputMin: 1,
            inputMax: 3650,
            confirmLabel: "Продлить",
            cancelLabel: "Отмена",
        });
    }

    function showTgMiniExtendDays(clientName, protocolLabel, defaultDays) {
        const initialDays = Number.parseInt(String(defaultDays || "30"), 10);
        const safeDays =
            Number.isFinite(initialDays) && initialDays >= 1 && initialDays <= 3650 ? initialDays : 30;
        const label = String(protocolLabel || "WG/AWG");

        return showTgMiniActionModal({
            title: "Продлить срок " + label,
            message: 'Укажите срок продления для клиента "' + clientName + '"',
            mode: "numberInput",
            inputLabel: "Продлить срок действия на (дни, 1-3650)",
            inputDefault: String(safeDays),
            inputMin: 1,
            inputMax: 3650,
            confirmLabel: "Продлить",
            cancelLabel: "Отмена",
        });
    }

    async function updateOpenVpnClientAccess(clientName, action, options) {
        const formData = new FormData();
        formData.append("client_name", clientName);
        formData.append("action", action);

        let days = null;
        let limitValue = null;
        let limitUnit = null;
        let limitPeriodDays = null;

        if (typeof options === "number" || typeof options === "string") {
            days = options;
        } else if (options && typeof options === "object") {
            days = options.days !== undefined ? options.days : null;
            limitValue = options.limitValue !== undefined ? options.limitValue : null;
            limitUnit = options.limitUnit !== undefined ? options.limitUnit : null;
            limitPeriodDays = options.limitPeriodDays !== undefined ? options.limitPeriodDays : null;
        }

        if (days !== null && days !== undefined && String(days).trim() !== "") {
            formData.append("days", String(days).trim());
        }
        if (limitValue !== null && limitValue !== undefined && String(limitValue).trim() !== "") {
            formData.append("limit_value", String(limitValue).trim());
        }
        if (limitUnit !== null && limitUnit !== undefined && String(limitUnit).trim() !== "") {
            formData.append("limit_unit", String(limitUnit).trim());
        }
        if (limitPeriodDays !== null && limitPeriodDays !== undefined && String(limitPeriodDays).trim() !== "") {
            formData.append("limit_period_days", String(limitPeriodDays).trim());
        }

        const csrfToken = getCsrfToken();
        if (csrfToken) {
            formData.append("csrf_token", csrfToken);
        }

        const response = await fetch("/api/openvpn/client-block", {
            method: "POST",
            body: formData,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        const payload = await parseJsonResponse(response);
        if (!response.ok || !payload || payload.success === false) {
            const error = new Error(payload.message || payload.error || "HTTP " + response.status);
            error.errorCode = payload.error_code || "";
            throw error;
        }

        return payload;
    }

    function applyOpenVpnAccessToMainRow(clientName, payload) {
        const rows = state.mainData.openvpn || [];
        rows.forEach(function (row) {
            if (row.client_name !== clientName) {
                return;
            }

            row.blocked = Boolean(payload.is_blocked);
            row.block_mode = payload.block_mode || "none";
            row.traffic_limit_bytes =
                payload.traffic_limit_bytes !== undefined && payload.traffic_limit_bytes !== null
                    ? String(payload.traffic_limit_bytes)
                    : "";
            row.traffic_limit_human = payload.traffic_limit_human || "";
            row.traffic_limit_period_days =
                payload.traffic_limit_period_days !== undefined && payload.traffic_limit_period_days !== null
                    ? String(payload.traffic_limit_period_days)
                    : "";
            row.traffic_limit_period_label = payload.traffic_limit_period_label || "";
        });
    }

    async function updateWgClientAccess(clientName, action, options) {
        const formData = new FormData();
        formData.append("client_name", clientName);
        formData.append("action", action);

        let days = null;
        let limitValue = null;
        let limitUnit = null;
        let limitPeriodDays = null;

        if (typeof options === "number" || typeof options === "string") {
            days = options;
        } else if (options && typeof options === "object") {
            days = options.days !== undefined ? options.days : null;
            limitValue = options.limitValue !== undefined ? options.limitValue : null;
            limitUnit = options.limitUnit !== undefined ? options.limitUnit : null;
            limitPeriodDays = options.limitPeriodDays !== undefined ? options.limitPeriodDays : null;
        }

        if (days !== null && days !== undefined && String(days).trim() !== "") {
            formData.append("days", String(days).trim());
        }
        if (limitValue !== null && limitValue !== undefined && String(limitValue).trim() !== "") {
            formData.append("limit_value", String(limitValue).trim());
        }
        if (limitUnit !== null && limitUnit !== undefined && String(limitUnit).trim() !== "") {
            formData.append("limit_unit", String(limitUnit).trim());
        }
        if (limitPeriodDays !== null && limitPeriodDays !== undefined && String(limitPeriodDays).trim() !== "") {
            formData.append("limit_period_days", String(limitPeriodDays).trim());
        }

        const csrfToken = getCsrfToken();
        if (csrfToken) {
            formData.append("csrf_token", csrfToken);
        }

        const response = await fetch("/api/wg/client-access", {
            method: "POST",
            body: formData,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        const payload = await parseJsonResponse(response);
        if (!response.ok || !payload || payload.success === false) {
            const error = new Error(payload.message || payload.error || "HTTP " + response.status);
            error.errorCode = payload.error_code || "";
            throw error;
        }

        return payload;
    }

    function applyWgAccessFieldsToRow(row, payload) {
        row.blocked = Boolean(payload.is_blocked);
        row.block_mode = payload.block_mode || "none";
        row.access_expires_at = payload.expires_at || row.access_expires_at || "";
        row.access_days_left =
            payload.access_days_left !== undefined && payload.access_days_left !== null
                ? String(payload.access_days_left)
                : row.access_days_left || "";
        row.traffic_limit_bytes =
            payload.traffic_limit_bytes !== undefined && payload.traffic_limit_bytes !== null
                ? String(payload.traffic_limit_bytes)
                : "";
        row.traffic_limit_human = payload.traffic_limit_human || "";
        row.traffic_limit_period_days =
            payload.traffic_limit_period_days !== undefined && payload.traffic_limit_period_days !== null
                ? String(payload.traffic_limit_period_days)
                : "";
        row.traffic_limit_period_label = payload.traffic_limit_period_label || "";
    }

    function applyWgAccessToMainRow(clientName, payload) {
        ["wireguard", "amneziawg"].forEach(function (protocol) {
            const rows = state.mainData[protocol] || [];
            rows.forEach(function (row) {
                if (row.client_name !== clientName) {
                    return;
                }
                applyWgAccessFieldsToRow(row, payload);
            });
        });
    }

    function openVpnActionButton(action, clientName, icon, title, subtitle, variant) {
        return (
            '<button type="button" class="tg-mini-action-card tg-mini-action-card-' +
            escapeHtml(variant || "primary") +
            '" data-main-action="' +
            escapeHtml(action) +
            '" data-client-name="' +
            escapeHtml(clientName) +
            '">' +
            '<span class="tg-mini-action-icon" aria-hidden="true">' +
            icon +
            "</span>" +
            '<span class="tg-mini-action-text">' +
            '<span class="tg-mini-action-title">' +
            escapeHtml(title) +
            "</span>" +
            (subtitle ? '<span class="tg-mini-action-subtitle">' + escapeHtml(subtitle) + "</span>" : "") +
            "</span></button>"
        );
    }

    function buildOpenVpnManageActions(row) {
        if (!isAdmin || state.mainProtocol !== "openvpn") {
            return "";
        }

        const actions = [];

        if (row.can_block) {
            actions.push(
                openVpnActionButton(
                    "temp-block",
                    row.client_name,
                    "⛔",
                    "Временная блокировка",
                    "OpenVPN",
                    "danger"
                )
            );

            if (!row.blocked) {
                actions.push(
                    openVpnActionButton(
                        "permanent-block",
                        row.client_name,
                        "⛔",
                        "Бессрочная блокировка",
                        "до ручной разблокировки",
                        "danger"
                    )
                );
            } else {
                actions.push(
                    openVpnActionButton("unblock", row.client_name, "🔓", "Снять блокировку", "OpenVPN", "success")
                );
            }
        }

        if (row.can_manage) {
            const hasTrafficLimit = Boolean(row.traffic_limit_bytes || row.traffic_limit_human);
            actions.push(
                openVpnActionButton(
                    "set-traffic-limit",
                    row.client_name,
                    "📊",
                    hasTrafficLimit ? "Изменить лимит" : "Установить лимит",
                    "трафик · OpenVPN",
                    "info"
                )
            );

            if (hasTrafficLimit) {
                actions.push(
                    openVpnActionButton(
                        "clear-traffic-limit",
                        row.client_name,
                        "📊",
                        "Снять лимит",
                        "трафик · OpenVPN",
                        "info"
                    )
                );
            }

            actions.push(
                openVpnActionButton("renew-cert", row.client_name, "♻", "Продлить сертификат", "", "primary")
            );
        }

        if (!actions.length) {
            return "";
        }

        return '<div class="tg-mini-main-actions-manage">' + actions.join("") + "</div>";
    }

    function buildWgManageActions(row, protocol) {
        if (!isAdmin || !isWgProtocol(protocol)) {
            return "";
        }

        const labels = getProtocolManageLabels(protocol);
        const blockMode = String(row.block_mode || "none").toLowerCase();
        const hasActiveBlock =
            blockMode === "temp" ||
            blockMode === "permanent" ||
            blockMode === "expired" ||
            blockMode === "traffic_limit";
        const actions = [];

        if (row.can_manage) {
            actions.push(
                openVpnActionButton(
                    "temp-block",
                    row.client_name,
                    "⛔",
                    "Временная блокировка",
                    labels.short,
                    "danger"
                )
            );

            if (!row.blocked) {
                actions.push(
                    openVpnActionButton(
                        "permanent-block",
                        row.client_name,
                        "⛔",
                        "Бессрочная блокировка",
                        "до ручной разблокировки",
                        "danger"
                    )
                );
            }

            if (hasActiveBlock) {
                actions.push(
                    openVpnActionButton("unblock", row.client_name, "🔓", "Снять блокировку", labels.short, "success")
                );
            }

            const hasTrafficLimit = Boolean(row.traffic_limit_bytes || row.traffic_limit_human);
            actions.push(
                openVpnActionButton(
                    "set-traffic-limit",
                    row.client_name,
                    "📊",
                    hasTrafficLimit ? "Изменить лимит" : "Установить лимит",
                    "трафик · " + labels.traffic,
                    "info"
                )
            );

            if (hasTrafficLimit) {
                actions.push(
                    openVpnActionButton(
                        "clear-traffic-limit",
                        row.client_name,
                        "📊",
                        "Снять лимит",
                        "трафик · " + labels.traffic,
                        "info"
                    )
                );
            }

            actions.push(
                openVpnActionButton(
                    "extend-days",
                    row.client_name,
                    "♻",
                    "Продлить срок",
                    labels.short,
                    "primary"
                )
            );
        }

        if (!actions.length) {
            return "";
        }

        return '<div class="tg-mini-main-actions-manage">' + actions.join("") + "</div>";
    }

    function findMainOpenVpnRow(clientName) {
        const rows = state.mainData.openvpn || [];
        return rows.find(function (row) {
            return row.client_name === clientName;
        }) || null;
    }

    function findMainWgRow(clientName) {
        const rows = state.mainData[state.mainProtocol] || [];
        return rows.find(function (row) {
            return row.client_name === clientName;
        }) || null;
    }

    async function runWgExtendFlow(clientName, defaultDays) {
        const labels = getProtocolManageLabels(state.mainProtocol);
        const extendDays = await showTgMiniExtendDays(clientName, labels.short, defaultDays || "30");
        if (extendDays === null) {
            return null;
        }

        const payload = await updateWgClientAccess(clientName, "extend", extendDays);
        applyWgAccessToMainRow(clientName, payload);
        renderMainClients();
        setStatus(mainStatusEl, payload.message || "Срок WG/AWG обновлён", "success");
        return payload;
    }

    async function requestJson(url, options) {
        const response = await fetch(url, options || { cache: "no-store" });
        const payload = await parseJsonResponse(response);

        if (!response.ok || payload.success === false) {
            const message = payload.message || payload.error || "Ошибка запроса";
            throw new Error(message);
        }

        return payload;
    }

    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    function detectDevicePlatform() {
        try {
            const tgPlatform = String(
                (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.platform) || ""
            ).toLowerCase();

            if (tgPlatform === "android") {
                return "android";
            }
            if (tgPlatform === "ios" || tgPlatform === "macos") {
                return "apple";
            }
        } catch (_error) {
            // no-op fallback to User-Agent parsing
        }

        const ua = String(navigator.userAgent || "").toLowerCase();
        if (ua.includes("android")) {
            return "android";
        }
        if (ua.includes("iphone") || ua.includes("ipad") || ua.includes("ios") || ua.includes("mac os x") || ua.includes("macintosh")) {
            return "apple";
        }
        if (ua.includes("windows") || ua.includes("win64") || ua.includes("win32")) {
            return "windows";
        }
        return "unknown";
    }

    async function sendConfigToTelegram(downloadUrl) {
        const csrfToken = getCsrfToken();
        return requestJson("/api/tg-mini/send-config", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({
                download_url: downloadUrl,
                device_platform: detectDevicePlatform(),
            }),
        });
    }

    async function checkTelegramBotDelivery() {
        const csrfToken = getCsrfToken();
        return requestJson("/api/tg-mini/check-bot-delivery", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({
                probe: true,
            }),
        });
    }

    async function runBotDeliveryCheck(options) {
        const opts = options || {};
        const silent = Boolean(opts.silent);

        setBotDeliveryIndicator("checking", "Проверяем связь...");
        if (!silent) {
            setStatus(mainStatusEl, "Проверка связи с Telegram ботом...", "");
        }

        try {
            const payload = await checkTelegramBotDelivery();
            setBotDeliveryIndicator("ok", "Бот на связи");
            if (!silent) {
                setStatus(mainStatusEl, payload.message || "Связь с ботом в порядке", "success");
            }
            return payload;
        } catch (error) {
            const message = error && error.message ? error.message : "Проверка не пройдена";
            setBotDeliveryIndicator("error", shortBotDeliveryErrorMessage(message));
            if (!silent) {
                setStatus(mainStatusEl, "Проверка не пройдена: " + message, "error");
            }
            return null;
        }
    }

    async function pollTask(taskId, statusElement, successMessage) {
        const started = Date.now();
        const timeoutMs = 15 * 60 * 1000;

        while (Date.now() - started < timeoutMs) {
            const payload = await requestJson("/api/tasks/" + encodeURIComponent(taskId), { cache: "no-store" });

            if (payload.status === "completed") {
                setStatus(statusElement, successMessage || payload.message || "Задача завершена", "success");
                return payload;
            }

            if (payload.status === "failed") {
                throw new Error(payload.error || payload.message || "Задача завершилась с ошибкой");
            }

            setStatus(statusElement, payload.message || "Задача выполняется...", "");
            await sleep(2500);
        }

        throw new Error("Превышено время ожидания задачи");
    }

    function initTabs() {
        const tabs = Array.from(document.querySelectorAll(".tg-mini-tab[data-pane]"));
        const panes = Array.from(document.querySelectorAll(".tg-mini-pane[data-pane]"));

        function activate(name) {
            tabs.forEach(function (btn) {
                btn.classList.toggle("is-active", btn.dataset.pane === name);
            });
            panes.forEach(function (pane) {
                pane.classList.toggle("is-active", pane.dataset.pane === name);
            });
        }

        tabs.forEach(function (btn) {
            btn.addEventListener("click", function () {
                activate(btn.dataset.pane || "dashboard");
            });
        });
    }

    function renderSummary(summary) {
        const cards = document.querySelectorAll("#tgMiniSummaryCards [data-key]");
        cards.forEach(function (el) {
            const key = el.dataset.key;
            el.textContent = summary && summary[key] !== undefined ? String(summary[key]) : "-";
        });
    }

    function renderTableRows(body, rows, renderCells, colSpan) {
        if (!body) {
            return;
        }

        if (!rows || rows.length === 0) {
            body.innerHTML = "<tr><td colspan=\"" + String(colSpan) + "\">Нет данных</td></tr>";
            return;
        }

        body.innerHTML = rows
            .map(function (row) {
                return "<tr>" + renderCells(row) + "</tr>";
            })
            .join("");
    }

    function updateDashboardToggleButton(button, expanded, totalCount) {
        if (!button) {
            return;
        }

        const total = Number(totalCount || 0);
        if (total <= state.dashboardPreviewLimit) {
            button.style.display = "none";
            return;
        }

        button.style.display = "inline-flex";
        if (expanded) {
            button.textContent = "Свернуть список";
        } else {
            button.textContent = "Показать полный список (" + String(total) + ")";
        }
    }

    function renderDashboardTopTables(payload) {
        const connectedRowsAll = payload.top_connected || [];
        const trafficRowsAll = payload.top_traffic || [];

        const connectedRows = state.dashboardShowAllConnected
            ? connectedRowsAll
            : connectedRowsAll.slice(0, state.dashboardPreviewLimit);
        const trafficRows = state.dashboardShowAllTraffic
            ? trafficRowsAll
            : trafficRowsAll.slice(0, state.dashboardPreviewLimit);

        renderTableRows(
            document.getElementById("tgMiniConnectedBody"),
            connectedRows,
            function (item) {
                const protocolList = String(item.protocols || "")
                    .split(",")
                    .map(function (token) {
                        const name = String(token || "").trim().toLowerCase();
                        if (!name) return "";
                        if (name.includes("wireguard")) return protocolChip("wireguard");
                        if (name.includes("openvpn")) return protocolChip("openvpn");
                        if (name.includes("amnezia")) return protocolChip("amneziawg");
                        return "";
                    })
                    .filter(Boolean)
                    .join(" ");

                return (
                    "<td>" +
                    escapeHtml(item.common_name || "-") +
                    (protocolList ? '<div class="tg-mini-main-meta">' + protocolList + "</div>" : "") +
                    "</td><td>" +
                    String(item.sessions || 0) +
                    "</td><td>" +
                    escapeHtml(item.total_bytes_human || "0 B") +
                    "</td>"
                );
            },
            3
        );

        renderTableRows(
            document.getElementById("tgMiniTrafficBody"),
            trafficRows,
            function (item) {
                return (
                    "<td>" +
                    escapeHtml(item.common_name || "-") +
                    '<div class="tg-mini-main-meta">' + activityChip(item.is_active) + "</div>" +
                    "</td><td>" +
                    escapeHtml(item.traffic_1h_human || "0 B") +
                    "</td><td>" +
                    escapeHtml(item.traffic_1d_human || "0 B") +
                    "</td><td>" +
                    escapeHtml(item.total_bytes_human || "0 B") +
                    "</td>"
                );
            },
            4
        );

        updateDashboardToggleButton(
            document.getElementById("tgMiniToggleConnected"),
            state.dashboardShowAllConnected,
            payload.top_connected_count || connectedRowsAll.length
        );
        updateDashboardToggleButton(
            document.getElementById("tgMiniToggleTraffic"),
            state.dashboardShowAllTraffic,
            payload.top_traffic_count || trafficRowsAll.length
        );
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function normalizeClientName(raw) {
        return String(raw || "")
            .replace(/[^a-zA-Z0-9_-]/g, "")
            .slice(0, 15);
    }

    function protocolLabel(protocolKey) {
        const key = String(protocolKey || "").toLowerCase();
        if (key === "openvpn") return "OpenVPN";
        if (key === "wireguard") return "WireGuard";
        if (key === "amneziawg") return "AmneziaWG";
        return key || "-";
    }

    function protocolChip(protocolKey) {
        const key = String(protocolKey || "").toLowerCase();
        const cssMap = {
            openvpn: "tg-mini-chip-proto-openvpn",
            wireguard: "tg-mini-chip-proto-wireguard",
            amneziawg: "tg-mini-chip-proto-amneziawg",
        };
        const css = cssMap[key] || "tg-mini-chip-network-vpn";
        return '<span class="tg-mini-chip ' + css + '">' + escapeHtml(protocolLabel(key)) + "</span>";
    }

    function certChip(certState, certDays) {
        const key = String(certState || "").toLowerCase();
        const readable = {
            active: "cert active",
            expiring: "cert expiring",
            expired: "cert expired",
        };
        const css = {
            active: "tg-mini-chip-cert-active",
            expiring: "tg-mini-chip-cert-expiring",
            expired: "tg-mini-chip-cert-expired",
        };
        if (!readable[key]) {
            return "";
        }
        let text = readable[key];
        if (String(certDays || "").trim() !== "") {
            text += " (" + escapeHtml(certDays) + "d)";
        }
        return '<span class="tg-mini-chip ' + css[key] + '">' + text + "</span>";
    }

    function activityChip(isActive) {
        if (Boolean(isActive)) {
            return '<span class="tg-mini-chip tg-mini-chip-online">online</span>';
        }
        return '<span class="tg-mini-chip tg-mini-chip-offline">offline</span>';
    }

    function networkChip(networkName) {
        const name = String(networkName || "-");
        const low = name.toLowerCase();
        const css = low.includes("antizapret") ? "tg-mini-chip-network-az" : "tg-mini-chip-network-vpn";
        return '<span class="tg-mini-chip ' + css + '">' + escapeHtml(name) + "</span>";
    }

    function isConfigDisabled(protocol, row) {
        if (!row || !row.blocked) {
            return false;
        }
        return protocol === "openvpn" || isWgProtocol(protocol);
    }

    function configStateChip(protocol, row) {
        if (isConfigDisabled(protocol, row)) {
            return '<span class="tg-mini-chip tg-mini-chip-disabled">disabled</span>';
        }
        return '<span class="tg-mini-chip tg-mini-chip-enabled">enabled</span>';
    }

    function syncMainProtocolControls() {
        const protocolButtons = Array.from(document.querySelectorAll('[data-main-protocol]'));
        if (!protocolButtons.length) {
            return;
        }

        const availableProtocols = protocolButtons
            .map(function (button) {
                return button.getAttribute("data-main-protocol") || "";
            })
            .filter(function (protocol) {
                return protocol && (state.mainData[protocol] || []).length > 0;
            });

        protocolButtons.forEach(function (button) {
            const protocol = button.getAttribute("data-main-protocol") || "";
            const isVisible = availableProtocols.includes(protocol);
            button.hidden = !isVisible;
            button.disabled = !isVisible;
        });

        const protocolRange = document.querySelector(".tg-mini-main-protocol-range");
        const protocolGroup = protocolRange ? protocolRange.closest(".tg-mini-main-control-group") : null;
        if (protocolGroup) {
            protocolGroup.style.display = availableProtocols.length <= 1 ? "none" : "";
        }

        if (availableProtocols.length > 0 && !availableProtocols.includes(state.mainProtocol)) {
            state.mainProtocol = availableProtocols[0];
        }

        protocolButtons.forEach(function (button) {
            const protocol = button.getAttribute("data-main-protocol") || "";
            button.classList.toggle("is-active", protocol === state.mainProtocol);
        });
    }

    async function loadMainData() {
        if (!mainStatusEl) {
            return;
        }

        setStatus(mainStatusEl, "Загрузка данных главной страницы...", "loading");

        try {
            const response = await fetch("/", {
                cache: "no-store",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            });

            const html = await response.text();
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }

            const doc = new DOMParser().parseFromString(html, "text/html");
            const protocolSelectors = {
                openvpn: '.config-table[data-protocol="openvpn"] .client-row',
                amneziawg: '.config-table[data-protocol="amneziawg"] .client-row',
                wireguard: '.config-table[data-protocol="wireguard"] .client-row',
            };

            Object.keys(protocolSelectors).forEach(function (protocol) {
                const rows = Array.from(doc.querySelectorAll(protocolSelectors[protocol]));
                state.mainData[protocol] = rows.map(function (row) {
                    return {
                        client_name: row.getAttribute("data-client-name") || "-",
                        can_manage: (row.getAttribute("data-can-manage") || "0") === "1",
                        can_block: (row.getAttribute("data-can-block") || "0") === "1",
                        delete_option: row.getAttribute("data-delete-option") || "",
                        blocked: (row.getAttribute("data-blocked") || "0") === "1",
                        block_mode: row.getAttribute("data-block-mode") || "none",
                        cert_state: row.getAttribute("data-cert-state") || "",
                        cert_days: row.getAttribute("data-cert-days") || "",
                        traffic_limit_bytes: row.getAttribute("data-traffic-limit-bytes") || "",
                        traffic_limit_human: row.getAttribute("data-traffic-limit-human") || "",
                        traffic_limit_period_days: row.getAttribute("data-traffic-limit-period-days") || "",
                        traffic_limit_period_label: row.getAttribute("data-traffic-limit-period-label") || "",
                        access_expires_at: row.getAttribute("data-access-expires-at") || "",
                        access_days_left: row.getAttribute("data-access-days-left") || "",
                        download_vpn_url: row.getAttribute("data-download-vpn-url") || "",
                        download_az_url: row.getAttribute("data-download-az-url") || "",
                    };
                });
            });

            syncMainProtocolControls();
            renderMainClients();
            setStatus(mainStatusEl, "Данные главной страницы обновлены", "success");
        } catch (error) {
            setStatus(mainStatusEl, "Ошибка загрузки главной: " + error.message, "error");
        }
    }

    function renderMainClients() {
        const container = document.getElementById("tgMiniMainClients");
        if (!container) {
            return;
        }

        const protocolRows = state.mainData[state.mainProtocol] || [];
        const search = String(state.mainSearch || "").trim().toLowerCase();
        const statusFilter = String(state.mainStatusFilter || "all").toLowerCase();
        const rows = protocolRows
            .filter(function (row) {
                if (search && !String(row.client_name || "").toLowerCase().includes(search)) {
                    return false;
                }

                const disabled = isConfigDisabled(state.mainProtocol, row);
                if (statusFilter === "enabled") {
                    return !disabled;
                }
                if (statusFilter === "disabled") {
                    return disabled;
                }
                return true;
            })
            .slice()
            .sort(function (a, b) {
                const aDisabled = isConfigDisabled(state.mainProtocol, a);
                const bDisabled = isConfigDisabled(state.mainProtocol, b);

                if (statusFilter === "all" && aDisabled !== bDisabled) {
                    return Number(aDisabled) - Number(bDisabled);
                }

                return String(a.client_name || "").localeCompare(String(b.client_name || ""), "ru", {
                    sensitivity: "base",
                });
            });

        if (!rows.length) {
            let emptyTitle = "Клиенты не найдены";
            let emptyHint = "Попробуйте изменить поиск или фильтр протокола.";
            if (statusFilter === "enabled") {
                emptyTitle = "Включенные конфиги не найдены";
                emptyHint = "Нет активных конфигов для выбранного протокола.";
            } else if (statusFilter === "disabled") {
                emptyTitle = "Выключенные конфиги не найдены";
                emptyHint = "Все конфиги сейчас включены.";
            } else if (search) {
                emptyHint = "По запросу «" + search + "» ничего не найдено.";
            }
            container.innerHTML = renderEmptyState(emptyTitle, emptyHint, "👤");
            return;
        }

        container.innerHTML = rows
            .map(function (row) {
                const sendActions = [];
                if (row.download_vpn_url) {
                    sendActions.push(
                        '<button type="button" class="tg-mini-btn tg-mini-btn-secondary tg-mini-btn-send" data-main-action="send-config" data-download-url="' + escapeHtml(row.download_vpn_url) + '">VPN в Telegram</button>'
                    );
                }
                if (row.download_az_url) {
                    sendActions.push(
                        '<button type="button" class="tg-mini-btn tg-mini-btn-secondary tg-mini-btn-send" data-main-action="send-config" data-download-url="' + escapeHtml(row.download_az_url) + '">AZ в Telegram</button>'
                    );
                }

                let meta = "";
                if (isAdmin) {
                    const metaParts = [];
                    if (state.mainProtocol === "openvpn" && row.cert_state) {
                        metaParts.push(certChip(row.cert_state, row.cert_days));
                    }
                    if (isWgProtocol(state.mainProtocol) && String(row.access_days_left || "").trim() !== "") {
                        metaParts.push(
                            '<span class="tg-mini-chip tg-mini-chip-cert-active">срок ' +
                            escapeHtml(row.access_days_left) +
                            "д</span>"
                        );
                    }
                    if (row.blocked) {
                        metaParts.push('<span class="tg-mini-chip tg-mini-chip-blocked">blocked</span>');
                    }
                    if (row.traffic_limit_human) {
                        let limitText = "лимит " + escapeHtml(row.traffic_limit_human);
                        if (row.traffic_limit_period_label) {
                            limitText += " · " + escapeHtml(row.traffic_limit_period_label);
                        }
                        metaParts.push('<span class="tg-mini-chip tg-mini-chip-traffic-limit">' + limitText + "</span>");
                    }
                    if (metaParts.length) {
                        meta = metaParts.join(" ");
                    }
                }

                const stateChip = configStateChip(state.mainProtocol, row);
                const manageActions =
                    buildOpenVpnManageActions(row) || buildWgManageActions(row, state.mainProtocol);

                const deleteBtn = row.can_manage && row.delete_option
                    ? '<button type="button" class="tg-mini-btn tg-mini-btn-danger tg-mini-btn-compact" data-main-action="delete" data-option="' + escapeHtml(row.delete_option) + '" data-client-name="' + escapeHtml(row.client_name) + '">Удалить</button>'
                    : "";

                const hasSecondary = Boolean(manageActions || deleteBtn);
                const primaryBlock = sendActions.length
                    ? '<div class="tg-mini-main-actions-primary">' + sendActions.join("") + "</div>"
                    : "";
                const secondaryBlock = [
                    manageActions,
                    deleteBtn ? '<div class="tg-mini-main-actions-secondary">' + deleteBtn + "</div>" : "",
                ].join("");

                const expandToggle = hasSecondary
                    ? '<button type="button" class="tg-mini-main-actions-toggle" aria-expanded="false">' +
                      '<span class="tg-mini-main-actions-toggle-label-more">Ещё действия</span>' +
                      '<span class="tg-mini-main-actions-toggle-label-less">Свернуть</span>' +
                      '<span class="tg-mini-main-actions-toggle-icon" aria-hidden="true"></span>' +
                      "</button>"
                    : "";

                const expandBlock = hasSecondary
                    ? '<div class="tg-mini-main-actions-expand">' + secondaryBlock + "</div>"
                    : "";

                const actionsBlock = primaryBlock + expandToggle + expandBlock;

                return (
                    '<article class="tg-mini-main-item">' +
                    '<div class="tg-mini-main-top">' +
                    '<div class="tg-mini-main-name">' + escapeHtml(row.client_name) + '</div>' +
                    '<div class="tg-mini-main-meta">' + protocolChip(state.mainProtocol) + ' ' + stateChip + '</div>' +
                    '</div>' +
                    (meta ? '<div class="tg-mini-main-meta">' + meta + '</div>' : '') +
                    (actionsBlock ? '<div class="tg-mini-main-actions">' + actionsBlock + '</div>' : '') +
                    '</article>'
                );
            })
            .join("");

        bindClientActionToggles(container);

        container.querySelectorAll('[data-main-action="send-config"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const downloadUrl = btn.getAttribute("data-download-url") || "";
                if (!downloadUrl) {
                    return;
                }

                try {
                    btn.disabled = true;
                    setStatus(mainStatusEl, "Отправка конфига в Telegram...", "");
                    const payload = await sendConfigToTelegram(downloadUrl);
                    setStatus(mainStatusEl, payload.message || "Конфиг отправлен в Telegram", "success");
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка отправки: " + error.message, "error");
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="temp-block"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!clientName) {
                    return;
                }

                const labels = getProtocolManageLabels(state.mainProtocol);
                const days = await showTgMiniActionModal({
                    title: "Временная блокировка " + labels.short,
                    message: 'Укажите срок блокировки для клиента "' + clientName + '"',
                    mode: "numberInput",
                    inputLabel: "Срок временной блокировки (дни, 1-3650)",
                    inputDefault: "7",
                    inputMin: 1,
                    inputMax: 3650,
                    confirmLabel: "Применить",
                    cancelLabel: "Отмена",
                });
                if (days === null) {
                    return;
                }

                try {
                    btn.disabled = true;
                    let payload;
                    if (state.mainProtocol === "openvpn") {
                        payload = await updateOpenVpnClientAccess(clientName, "temp_block", days);
                        applyOpenVpnAccessToMainRow(clientName, payload);
                    } else if (isWgProtocol(state.mainProtocol)) {
                        payload = await updateWgClientAccess(clientName, "temp_block", days);
                        applyWgAccessToMainRow(clientName, payload);
                    } else {
                        return;
                    }
                    renderMainClients();
                    setStatus(mainStatusEl, payload.message || "Временная блокировка применена", "success");
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка блокировки: " + error.message, "error");
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="permanent-block"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!clientName) {
                    return;
                }

                const labels = getProtocolManageLabels(state.mainProtocol);
                const confirmed = await showTgMiniActionModal({
                    title: "Бессрочная блокировка " + labels.short,
                    message: 'Заблокировать клиента "' + clientName + '" до ручной разблокировки?',
                    mode: "confirm",
                    confirmLabel: "Заблокировать",
                    cancelLabel: "Отмена",
                });
                if (!confirmed) {
                    return;
                }

                try {
                    btn.disabled = true;
                    let payload;
                    if (state.mainProtocol === "openvpn") {
                        payload = await updateOpenVpnClientAccess(clientName, "permanent_block");
                        applyOpenVpnAccessToMainRow(clientName, payload);
                    } else if (isWgProtocol(state.mainProtocol)) {
                        payload = await updateWgClientAccess(clientName, "permanent_block");
                        applyWgAccessToMainRow(clientName, payload);
                    } else {
                        return;
                    }
                    renderMainClients();
                    setStatus(mainStatusEl, payload.message || "Клиент заблокирован", "success");
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка блокировки: " + error.message, "error");
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="unblock"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!clientName) {
                    return;
                }

                if (isWgProtocol(state.mainProtocol)) {
                    const wgRow = findMainWgRow(clientName);
                    if (wgRow && String(wgRow.block_mode || "").toLowerCase() === "expired") {
                        try {
                            btn.disabled = true;
                            await runWgExtendFlow(clientName, "30");
                        } catch (error) {
                            setStatus(mainStatusEl, "Ошибка продления: " + error.message, "error");
                        } finally {
                            btn.disabled = false;
                        }
                        return;
                    }
                }

                try {
                    btn.disabled = true;
                    let payload;
                    if (state.mainProtocol === "openvpn") {
                        payload = await updateOpenVpnClientAccess(clientName, "unblock");
                        applyOpenVpnAccessToMainRow(clientName, payload);
                    } else if (isWgProtocol(state.mainProtocol)) {
                        payload = await updateWgClientAccess(clientName, "unblock");
                        applyWgAccessToMainRow(clientName, payload);
                    } else {
                        return;
                    }
                    renderMainClients();
                    setStatus(mainStatusEl, payload.message || "Блокировка снята", "success");
                } catch (error) {
                    if (error.errorCode === "expired_requires_extend" && isWgProtocol(state.mainProtocol)) {
                        try {
                            await runWgExtendFlow(clientName, "30");
                        } catch (extendError) {
                            setStatus(mainStatusEl, "Ошибка продления: " + extendError.message, "error");
                        }
                    } else if (error.errorCode === "traffic_limit_exceeded") {
                        setStatus(
                            mainStatusEl,
                            error.message || "Клиент заблокирован по лимиту трафика",
                            "error"
                        );
                    } else {
                        setStatus(mainStatusEl, "Ошибка разблокировки: " + error.message, "error");
                    }
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="set-traffic-limit"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!clientName) {
                    return;
                }

                const labels = getProtocolManageLabels(state.mainProtocol);
                const row =
                    state.mainProtocol === "openvpn"
                        ? findMainOpenVpnRow(clientName)
                        : findMainWgRow(clientName);
                const limitInput = await showTgMiniTrafficLimitInput(
                    clientName,
                    labels.traffic,
                    row ? row.traffic_limit_period_days : "7"
                );
                if (!limitInput) {
                    return;
                }

                try {
                    btn.disabled = true;
                    let payload;
                    if (state.mainProtocol === "openvpn") {
                        payload = await updateOpenVpnClientAccess(clientName, "set_traffic_limit", limitInput);
                        applyOpenVpnAccessToMainRow(clientName, payload);
                    } else if (isWgProtocol(state.mainProtocol)) {
                        payload = await updateWgClientAccess(clientName, "set_traffic_limit", limitInput);
                        applyWgAccessToMainRow(clientName, payload);
                    } else {
                        return;
                    }
                    renderMainClients();
                    setStatus(mainStatusEl, payload.message || "Лимит трафика обновлён", "success");
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка лимита трафика: " + error.message, "error");
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="clear-traffic-limit"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!clientName) {
                    return;
                }

                const labels = getProtocolManageLabels(state.mainProtocol);
                const confirmed = await showTgMiniActionModal({
                    title: "Снять лимит трафика " + labels.short,
                    message: 'Снять лимит трафика для клиента "' + clientName + '"?',
                    mode: "confirm",
                    confirmLabel: "Снять",
                    cancelLabel: "Отмена",
                });
                if (!confirmed) {
                    return;
                }

                try {
                    btn.disabled = true;
                    let payload;
                    if (state.mainProtocol === "openvpn") {
                        payload = await updateOpenVpnClientAccess(clientName, "clear_traffic_limit");
                        applyOpenVpnAccessToMainRow(clientName, payload);
                    } else if (isWgProtocol(state.mainProtocol)) {
                        payload = await updateWgClientAccess(clientName, "clear_traffic_limit");
                        applyWgAccessToMainRow(clientName, payload);
                    } else {
                        return;
                    }
                    renderMainClients();
                    setStatus(mainStatusEl, payload.message || "Лимит трафика снят", "success");
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка снятия лимита: " + error.message, "error");
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="extend-days"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!clientName || !isWgProtocol(state.mainProtocol)) {
                    return;
                }

                const wgRow = findMainWgRow(clientName);
                const daysRaw = Number.parseInt(String((wgRow && wgRow.access_days_left) || ""), 10);
                const defaultDays =
                    Number.isFinite(daysRaw) && daysRaw > 0 && daysRaw <= 3650 ? String(daysRaw) : "30";

                try {
                    btn.disabled = true;
                    await runWgExtendFlow(clientName, defaultDays);
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка продления: " + error.message, "error");
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="renew-cert"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!clientName) {
                    return;
                }

                const row = findMainOpenVpnRow(clientName);
                const certDaysRaw = Number.parseInt(String((row && row.cert_days) || ""), 10);
                const defaultDays =
                    Number.isFinite(certDaysRaw) && certDaysRaw > 0 && certDaysRaw <= 3650
                        ? String(certDaysRaw)
                        : "365";
                const renewDays = await showTgMiniRenewDays(defaultDays);
                if (renewDays === null) {
                    return;
                }

                try {
                    btn.disabled = true;
                    const payload = await submitMainAction("1", clientName, renewDays);
                    setStatus(mainStatusEl, payload.message || "Сертификат продлён", "success");
                    await loadMainData();
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка продления: " + error.message, "error");
                } finally {
                    btn.disabled = false;
                }
            });
        });

        container.querySelectorAll('[data-main-action="delete"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const option = btn.getAttribute("data-option") || "";
                const clientName = btn.getAttribute("data-client-name") || "";
                if (!option || !clientName) {
                    return;
                }

                const confirmed = await showTgMiniActionModal({
                    title: "Удалить конфигурацию",
                    message: 'Удалить конфигурацию клиента "' + clientName + '"? Это действие необратимо.',
                    mode: "confirm",
                    confirmLabel: "Удалить",
                    cancelLabel: "Отмена",
                });
                if (!confirmed) {
                    return;
                }

                try {
                    await submitMainAction(option, clientName, "");
                    setStatus(mainStatusEl, "Конфигурация удалена: " + clientName, "success");
                    await loadMainData();
                    await loadDashboard();
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка удаления: " + error.message, "error");
                }
            });
        });
    }

    async function submitMainAction(option, clientName, certExpire) {
        const params = new URLSearchParams();
        params.set("csrf_token", getCsrfToken());
        params.set("option", String(option || ""));
        params.set("client-name", String(clientName || ""));
        if (certExpire) {
            params.set("work-term", String(certExpire));
        }

        const response = await fetch("/", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
            body: params.toString(),
        });

        const payload = await parseJsonResponse(response);
        if (!response.ok || payload.success === false) {
            throw new Error(payload.message || payload.error || ("HTTP " + response.status));
        }

        return payload;
    }

    function bindMainControls() {
        const protocolButtons = Array.from(document.querySelectorAll('[data-main-protocol]'));
        protocolButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                const protocol = button.getAttribute("data-main-protocol") || "openvpn";
                state.mainProtocol = protocol;
                protocolButtons.forEach(function (btn) {
                    btn.classList.toggle("is-active", btn === button);
                });
                renderMainClients();
            });
        });

        const searchInput = document.getElementById("tgMiniMainSearch");
        if (searchInput) {
            searchInput.addEventListener("input", function () {
                state.mainSearch = searchInput.value || "";
                renderMainClients();
            });
        }

        const statusFilterButtons = Array.from(document.querySelectorAll('[data-main-status-filter]'));
        statusFilterButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                const filterName = button.getAttribute("data-main-status-filter") || "all";
                state.mainStatusFilter = filterName;
                statusFilterButtons.forEach(function (btn) {
                    btn.classList.toggle("is-active", btn === button);
                });
                renderMainClients();
            });
        });

        const createType = document.getElementById("tgMiniCreateType");
        const createDaysWrap = document.getElementById("tgMiniCreateDaysWrap");
        const createForm = document.getElementById("tgMiniMainCreateForm");

        if (createType && createDaysWrap) {
            const updateDaysVisibility = function () {
                createDaysWrap.style.display = createType.value === "1" ? "block" : "none";
            };
            createType.addEventListener("change", updateDaysVisibility);
            updateDaysVisibility();
        }

        if (createForm) {
            createForm.addEventListener("submit", async function (event) {
                event.preventDefault();

                const option = (document.getElementById("tgMiniCreateType") || {}).value || "1";
                const nameRaw = (document.getElementById("tgMiniCreateClientName") || {}).value || "";
                const clientName = normalizeClientName(nameRaw);
                const days = String((document.getElementById("tgMiniCreateDays") || {}).value || "").trim();

                if (!clientName) {
                    setStatus(mainStatusEl, "Укажите корректное имя клиента", "error");
                    return;
                }

                if (option === "1") {
                    if (!/^\d+$/.test(days) || Number(days) < 1 || Number(days) > 3650) {
                        setStatus(mainStatusEl, "Срок OpenVPN должен быть в диапазоне 1..3650", "error");
                        return;
                    }
                }

                try {
                    setStatus(mainStatusEl, "Создаем конфигурацию...", "");
                    await submitMainAction(option, clientName, option === "1" ? days : "");
                    setStatus(mainStatusEl, "Конфигурация создана: " + clientName, "success");
                    (document.getElementById("tgMiniCreateClientName") || {}).value = "";
                    await loadMainData();
                    await loadDashboard();
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка создания: " + error.message, "error");
                }
            });
        }
    }

    function renderProtocolChart(summary) {
        const canvas = document.getElementById("tgMiniProtocolChart");
        if (!canvas || !window.Chart) {
            return;
        }

        const labels = ["OpenVPN", "WireGuard"];
        const values = [
            Number((summary && summary.total_openvpn_sessions) || 0),
            Number((summary && summary.total_wireguard_sessions) || 0),
        ];

        if (state.protocolChart) {
            state.protocolChart.destroy();
            state.protocolChart = null;
        }

        state.protocolChart = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [
                    {
                        data: values,
                        backgroundColor: ["rgba(11, 91, 211, 0.82)", "rgba(15, 118, 110, 0.82)"],
                        borderColor: ["rgba(11, 91, 211, 1)", "rgba(15, 118, 110, 1)"],
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: {
                        position: "bottom",
                    },
                },
            },
        });
    }

    function updateTrafficClientOptions(clientNames) {
        const select = document.getElementById("tgMiniTrafficClient");
        if (!select) {
            return;
        }

        select.innerHTML = "";

        if (!clientNames || clientNames.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "Нет клиентов";
            select.appendChild(option);
            state.selectedClient = "";
            return;
        }

        clientNames.forEach(function (name) {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            select.appendChild(option);
        });

        if (!state.selectedClient || !clientNames.includes(state.selectedClient)) {
            state.selectedClient = clientNames[0];
        }

        select.value = state.selectedClient;
    }

    async function loadUserTrafficChart() {
        const meta = document.getElementById("tgMiniTrafficMeta");
        const canvas = document.getElementById("tgMiniTrafficChart");

        if (!canvas || !state.selectedClient) {
            setStatus(meta, "Выберите клиента для графика", "");
            return;
        }

        setStatus(meta, "Загрузка трафика...", "");

        try {
            const url =
                "/api/user-traffic-chart?client=" +
                encodeURIComponent(state.selectedClient) +
                "&range=" +
                encodeURIComponent(state.selectedRange);

            const payload = await requestJson(url, { cache: "no-store" });

            const labels = payload.labels || [];
            const vpn = payload.vpn_bytes || [];
            const antizapret = payload.antizapret_bytes || [];

            if (state.trafficChart) {
                state.trafficChart.destroy();
                state.trafficChart = null;
            }

            state.trafficChart = new Chart(canvas, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: "VPN",
                            data: vpn,
                            borderColor: "rgba(11, 91, 211, 1)",
                            backgroundColor: "rgba(11, 91, 211, 0.16)",
                            borderWidth: 2,
                            pointRadius: 0,
                            tension: 0.28,
                            fill: true,
                        },
                        {
                            label: "Antizapret",
                            data: antizapret,
                            borderColor: "rgba(197, 127, 17, 1)",
                            backgroundColor: "rgba(197, 127, 17, 0.14)",
                            borderWidth: 2,
                            pointRadius: 0,
                            tension: 0.28,
                            fill: true,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    scales: {
                        y: {
                            ticks: {
                                callback: function (value) {
                                    const num = Number(value || 0);
                                    if (num >= 1024 * 1024 * 1024) return (num / (1024 * 1024 * 1024)).toFixed(1) + " GB";
                                    if (num >= 1024 * 1024) return (num / (1024 * 1024)).toFixed(1) + " MB";
                                    if (num >= 1024) return (num / 1024).toFixed(1) + " KB";
                                    return String(num) + " B";
                                },
                            },
                        },
                    },
                },
            });

            setStatus(
                meta,
                "Клиент: " +
                state.selectedClient +
                " | 1h: " +
                String(payload.total_1h_human || "0 B") +
                " | 1d: " +
                String(payload.total_1d_human || "0 B") +
                " | VPN: " +
                String(payload.total_vpn_human || "0 B") +
                " | AZ: " +
                String(payload.total_antizapret_human || "0 B") +
                " | Всего: " +
                String(payload.total_human || "0 B"),
                ""
            );
        } catch (error) {
            setStatus(meta, "Ошибка загрузки графика: " + error.message, "error");
        }
    }

    async function loadDashboard() {
        if (!dashboardStatusEl) {
            return;
        }

        setStatus(dashboardStatusEl, "Загрузка dashboard...", "loading");

        try {
            const payload = await requestJson("/api/tg-mini/dashboard", { cache: "no-store" });
            state.dashboard = payload;

            renderSummary(payload.summary || {});
            renderProtocolChart(payload.summary || {});
            updateTrafficClientOptions(payload.traffic_clients || []);

            renderTableRows(
                document.getElementById("tgMiniNetworksBody"),
                payload.top_networks || [],
                function (item) {
                    return (
                        "<td>" +
                        networkChip(item.network || "-") +
                        "</td><td>" +
                        String(item.client_count || 0) +
                        "</td><td>" +
                        escapeHtml(item.total_traffic_human || "0 B") +
                        "</td>"
                    );
                },
                3
            );

            renderDashboardTopTables(payload);

            const generatedAt = payload.generated_at ? " | Обновлено: " + payload.generated_at : "";
            setStatus(dashboardStatusEl, "Дашборд готов" + generatedAt, "success");

            await loadUserTrafficChart();
        } catch (error) {
            setStatus(dashboardStatusEl, "Ошибка dashboard: " + error.message, "error");
        }
    }

    function bindDashboardControls() {
        const select = document.getElementById("tgMiniTrafficClient");
        if (select) {
            select.addEventListener("change", function () {
                state.selectedClient = select.value || "";
                loadUserTrafficChart();
            });
        }

        const rangeButtons = Array.from(document.querySelectorAll(".tg-mini-range-btn[data-range]"));
        rangeButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                const nextRange = button.dataset.range || "1d";
                state.selectedRange = nextRange;
                rangeButtons.forEach(function (btn) {
                    btn.classList.toggle("is-active", btn === button);
                });
                loadUserTrafficChart();
            });
        });

        const toggleConnected = document.getElementById("tgMiniToggleConnected");
        if (toggleConnected) {
            toggleConnected.addEventListener("click", function () {
                state.dashboardShowAllConnected = !state.dashboardShowAllConnected;
                saveDashboardUiPrefs();
                if (state.dashboard) {
                    renderDashboardTopTables(state.dashboard);
                }
            });
        }

        const toggleTraffic = document.getElementById("tgMiniToggleTraffic");
        if (toggleTraffic) {
            toggleTraffic.addEventListener("click", function () {
                state.dashboardShowAllTraffic = !state.dashboardShowAllTraffic;
                saveDashboardUiPrefs();
                if (state.dashboard) {
                    renderDashboardTopTables(state.dashboard);
                }
            });
        }
    }

    function prettifyKey(key) {
        const dictionary = {
            route_all: "Route all",
            discord_include: "Discord",
            cloudflare_include: "Cloudflare",
            telegram_include: "Telegram",
            block_ads: "AdBlock",
            whatsapp_include: "WhatsApp",
            roblox_include: "Roblox",
            OPENVPN_BACKUP_TCP: "OpenVPN backup TCP",
            OPENVPN_BACKUP_UDP: "OpenVPN backup UDP",
            WIREGUARD_BACKUP: "WireGuard backup",
            ANTIZAPRET_WARP: "Antizapret WARP",
            VPN_WARP: "VPN WARP",
            ssh_protection: "SSH protection",
            attack_protection: "Attack protection",
            scan_protection: "Scan protection",
            torrent_guard: "Torrent guard",
            restrict_forward: "Restrict forward",
            clear_hosts: "Clear hosts",
        };
        return dictionary[key] || String(key || "").replace(/_/g, " ");
    }

    function antizapretFlagDescription(item) {
        if (item && item.description) {
            return String(item.description);
        }

        const key = String((item && item.key) || "");
        const descriptionMap = {
            route_all: "Почти весь трафик пойдет через Antizapret по умолчанию.",
            discord_include: "Маршрутизировать Discord через Antizapret.",
            cloudflare_include: "Маршрутизировать сервисы Cloudflare через Antizapret.",
            telegram_include: "Маршрутизировать Telegram через Antizapret.",
            block_ads: "Включить фильтрацию рекламы в трафике.",
            whatsapp_include: "Маршрутизировать WhatsApp через Antizapret.",
            roblox_include: "Маршрутизировать Roblox через Antizapret.",
            OPENVPN_BACKUP_TCP: "Резервный OpenVPN TCP-порт для обхода блокировок.",
            OPENVPN_BACKUP_UDP: "Резервный OpenVPN UDP-порт для обхода блокировок.",
            WIREGUARD_BACKUP: "Резервный WireGuard-порт для обхода блокировок.",
            ANTIZAPRET_WARP: "Использовать WARP для трафика Antizapret.",
            VPN_WARP: "Использовать WARP как исходящий маршрут для VPN трафика.",
            ssh_protection: "Базовая защита SSH от подозрительных подключений.",
            attack_protection: "Блокирует подозрительную сетевую активность: превышение лимита подключений и попытки подключения по нетипичным портам.",
            scan_protection: "Скрывает сервер от простого сканирования: отключает ответ на ping и на запросы к закрытым портам.",
            torrent_guard: "Ограничивать подозрительный P2P/torrent-трафик.",
            restrict_forward: "Ограничить нежелательный forward между сетями.",
            clear_hosts: "Очищать hosts от конфликтных/лишних записей.",
        };
        return descriptionMap[key] || "Управляет параметром маршрутизации и фильтрации Antizapret.";
    }

    function antizapretFlagTitle(item) {
        if (item && item.title) {
            return String(item.title);
        }
        return prettifyKey(item && item.key);
    }

    function renderAntizapretToggles(settings) {
        const grid = document.getElementById("tgMiniAntizapretGrid");
        if (!grid) {
            return;
        }

        const flags = state.antizapretSchema.filter(function (item) {
            return item.type === "flag";
        });

        if (!flags.length) {
            grid.innerHTML = renderEmptyState("Нет toggle-параметров", "Схема Antizapret недоступна или пуста.", "⚙️");
            return;
        }

        grid.innerHTML = flags
            .map(function (item) {
                const checked = String(settings[item.key] || "n").toLowerCase() === "y" ? "checked" : "";
                return (
                    "<div class=\"tg-mini-toggle-item\">" +
                    "<div class=\"tg-mini-toggle-copy\">" +
                    "<label class=\"tg-mini-toggle-title\" for=\"tg-az-" +
                    escapeHtml(item.key) +
                    "\">" +
                    escapeHtml(antizapretFlagTitle(item)) +
                    "</label>" +
                    "<div class=\"tg-mini-toggle-desc\">" +
                    ((item.param_label || item.env) ? '<span class=\"tg-mini-toggle-param\">(' + escapeHtml(item.param_label || item.env) + ')</span> ' : "") +
                    escapeHtml(antizapretFlagDescription(item)) +
                    "</div>" +
                    "</div>" +
                    "<input id=\"tg-az-" +
                    escapeHtml(item.key) +
                    "\" data-az-key=\"" +
                    escapeHtml(item.key) +
                    "\" type=\"checkbox\" " +
                    checked +
                    " />" +
                    "</div>"
                );
            })
            .join("");
    }

    async function loadSettings() {
        if (!isAdmin) {
            return;
        }

        setStatus(settingsStatusEl, "Загрузка настроек...", "loading");

        try {
            const payload = await requestJson("/api/tg-mini/settings", { cache: "no-store" });
            const settings = payload.settings || {};

            const portInput = document.getElementById("tgMiniPortInput");
            const nightlyEnabled = document.getElementById("tgMiniNightlyEnabled");
            const nightlyTime = document.getElementById("tgMiniNightlyTime");
            const sessionTtl = document.getElementById("tgMiniSessionTtl");
            const sessionTouch = document.getElementById("tgMiniSessionTouch");
            const botUsername = document.getElementById("tgMiniBotUsername");
            const botMaxAge = document.getElementById("tgMiniAuthMaxAge");

            if (portInput) portInput.value = settings.app_port || "5050";
            if (nightlyEnabled) nightlyEnabled.checked = Boolean(settings.nightly_idle_restart_enabled);
            if (nightlyTime) nightlyTime.value = settings.nightly_idle_restart_time || "04:00";
            if (sessionTtl) sessionTtl.value = String(settings.active_web_session_ttl_seconds || 600);
            if (sessionTouch) sessionTouch.value = String(settings.active_web_session_touch_interval_seconds || 60);
            if (botUsername) botUsername.value = settings.telegram_auth_bot_username || "";
            if (botMaxAge) botMaxAge.value = String(settings.telegram_auth_max_age_seconds || 300);

            setStatus(settingsStatusEl, "Настройки загружены", "success");
        } catch (error) {
            setStatus(settingsStatusEl, "Ошибка загрузки настроек: " + error.message, "error");
        }
    }

    async function loadAntizapretSettings() {
        if (!isAdmin) {
            return;
        }

        try {
            const pair = await Promise.all([
                requestJson("/antizapret_settings_schema", { cache: "no-store" }),
                requestJson("/get_antizapret_settings", { cache: "no-store" }),
            ]);

            state.antizapretSchema = Array.isArray(pair[0]) ? pair[0] : [];
            renderAntizapretToggles(pair[1] || {});
        } catch (error) {
            setStatus(settingsStatusEl, "Ошибка antizapret настроек: " + error.message, "error");
        }
    }

    async function postMiniSettings(payload) {
        return requestJson("/api/tg-mini/settings", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
            },
            body: JSON.stringify(payload),
        });
    }

    function bindSettingsForms() {
        if (!isAdmin) {
            return;
        }

        const portForm = document.getElementById("tgMiniPortForm");
        if (portForm) {
            portForm.addEventListener("submit", async function (event) {
                event.preventDefault();
                const portInput = document.getElementById("tgMiniPortInput");
                const restartCheckbox = document.getElementById("tgMiniPortRestart");

                try {
                    setStatus(settingsStatusEl, "Сохранение порта...", "");
                    const payload = await postMiniSettings({
                        section: "port",
                        port: portInput ? portInput.value : "",
                        restart_service: restartCheckbox ? restartCheckbox.checked : true,
                    });

                    setStatus(settingsStatusEl, payload.message || "Порт сохранен", "success");
                    if (payload.restart_task_id) {
                        await pollTask(payload.restart_task_id, settingsStatusEl, "Порт сохранен и служба перезапущена");
                    }
                } catch (error) {
                    setStatus(settingsStatusEl, "Ошибка сохранения порта: " + error.message, "error");
                }
            });
        }

        const nightlyForm = document.getElementById("tgMiniNightlyForm");
        if (nightlyForm) {
            nightlyForm.addEventListener("submit", async function (event) {
                event.preventDefault();

                try {
                    setStatus(settingsStatusEl, "Сохранение nightly settings...", "");
                    const payload = await postMiniSettings({
                        section: "nightly",
                        nightly_idle_restart_enabled: document.getElementById("tgMiniNightlyEnabled").checked,
                        nightly_idle_restart_time: document.getElementById("tgMiniNightlyTime").value,
                        active_web_session_ttl_seconds: document.getElementById("tgMiniSessionTtl").value,
                        active_web_session_touch_interval_seconds: document.getElementById("tgMiniSessionTouch").value,
                    });
                    setStatus(settingsStatusEl, payload.message || "Nightly settings сохранены", "success");
                } catch (error) {
                    setStatus(settingsStatusEl, "Ошибка nightly settings: " + error.message, "error");
                }
            });
        }

        const telegramForm = document.getElementById("tgMiniTelegramForm");
        if (telegramForm) {
            telegramForm.addEventListener("submit", async function (event) {
                event.preventDefault();

                try {
                    setStatus(settingsStatusEl, "Сохранение Telegram auth...", "");
                    const botToken = (document.getElementById("tgMiniBotToken").value || "").trim();
                    const payloadToSend = {
                        section: "telegram_auth",
                        telegram_auth_bot_username: document.getElementById("tgMiniBotUsername").value,
                        telegram_auth_max_age_seconds: document.getElementById("tgMiniAuthMaxAge").value,
                    };

                    if (botToken) {
                        payloadToSend.telegram_auth_bot_token = botToken;
                    }

                    const payload = await postMiniSettings(payloadToSend);
                    setStatus(settingsStatusEl, payload.message || "Telegram auth сохранен", "success");
                    document.getElementById("tgMiniBotToken").value = "";
                } catch (error) {
                    setStatus(settingsStatusEl, "Ошибка Telegram auth: " + error.message, "error");
                }
            });
        }

        const applyAntizapretButton = document.getElementById("tgMiniApplyAntizapret");
        if (applyAntizapretButton) {
            applyAntizapretButton.addEventListener("click", async function () {
                const toggles = document.querySelectorAll("input[data-az-key]");
                const settingsPayload = {};

                toggles.forEach(function (toggle) {
                    const key = toggle.getAttribute("data-az-key");
                    if (!key) {
                        return;
                    }
                    settingsPayload[key] = toggle.checked ? "y" : "n";
                });

                try {
                    applyAntizapretButton.disabled = true;
                    setStatus(settingsStatusEl, "Сохранение antizapret settings...", "");

                    const saveResponse = await requestJson("/update_antizapret_settings", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRFToken": getCsrfToken(),
                        },
                        body: JSON.stringify(settingsPayload),
                    });

                    setStatus(settingsStatusEl, saveResponse.message || "Настройки antizapret сохранены", "success");
                    const applyResponse = await requestJson("/run-doall", {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": getCsrfToken(),
                        },
                    });

                    if (applyResponse.queued && applyResponse.task_id) {
                        await pollTask(applyResponse.task_id, settingsStatusEl, "Antizapret настройки применены");
                    } else {
                        setStatus(settingsStatusEl, applyResponse.message || "Применение завершено", "success");
                    }
                } catch (error) {
                    setStatus(settingsStatusEl, "Ошибка применения antizapret: " + error.message, "error");
                } finally {
                    applyAntizapretButton.disabled = false;
                }
            });
        }

        const restartButton = document.getElementById("tgMiniRestartService");
        if (restartButton) {
            restartButton.addEventListener("click", async function () {
                try {
                    restartButton.disabled = true;
                    setStatus(settingsStatusEl, "Запуск перезапуска службы...", "");
                    const payload = await requestJson("/api/restart-service", {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": getCsrfToken(),
                        },
                    });
                    if (payload.queued && payload.task_id) {
                        await pollTask(payload.task_id, settingsStatusEl, "Служба перезапущена");
                    } else {
                        setStatus(settingsStatusEl, payload.message || "Перезапуск выполнен", "success");
                    }
                } catch (error) {
                    setStatus(settingsStatusEl, "Ошибка перезапуска: " + error.message, "error");
                } finally {
                    restartButton.disabled = false;
                }
            });
        }

        const updateButton = document.getElementById("tgMiniUpdateSystem");
        if (updateButton) {
            updateButton.addEventListener("click", async function () {
                try {
                    updateButton.disabled = true;
                    setStatus(settingsStatusEl, "Запуск обновления системы...", "");
                    const payload = await requestJson("/update_system", {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": getCsrfToken(),
                        },
                    });

                    if (payload.queued && payload.task_id) {
                        await pollTask(payload.task_id, settingsStatusEl, "Обновление системы завершено");
                    } else {
                        setStatus(settingsStatusEl, payload.message || "Обновление выполнено", "success");
                    }
                } catch (error) {
                    setStatus(settingsStatusEl, "Ошибка обновления: " + error.message, "error");
                } finally {
                    updateButton.disabled = false;
                }
            });
        }
    }

    initTelegramWebApp();
    initMobileChrome();
    loadDashboardUiPrefs();
    initTabs();
    bindMainControls();
    bindDashboardControls();
    bindSettingsForms();

    runBotDeliveryCheck({ silent: true });

    loadMainData();
    if (dashboardStatusEl) {
        loadDashboard();
    }

    if (isAdmin) {
        loadSettings();
        loadAntizapretSettings();
    }
});
