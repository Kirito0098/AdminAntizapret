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

    function setThemeClass(scheme) {
        const isDark = String(scheme || "").toLowerCase() === "dark";
        document.body.classList.toggle("tg-mini-theme-dark", isDark);
        document.body.classList.toggle("tg-mini-theme-light", !isDark);
    }

    function hexToRgba(hexColor, alpha) {
        const value = String(hexColor || "").trim();
        if (!value.startsWith("#")) {
            return value;
        }

        const hex = value.slice(1);
        if (hex.length === 3) {
            const r = parseInt(hex[0] + hex[0], 16);
            const g = parseInt(hex[1] + hex[1], 16);
            const b = parseInt(hex[2] + hex[2], 16);
            return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
        }

        if (hex.length === 6) {
            const r = parseInt(hex.slice(0, 2), 16);
            const g = parseInt(hex.slice(2, 4), 16);
            const b = parseInt(hex.slice(4, 6), 16);
            return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
        }

        return value;
    }

    function applyTelegramThemeParams(themeParams) {
        if (!themeParams || typeof themeParams !== "object") {
            return;
        }

        const rootStyle = document.documentElement.style;
        const setVar = function (name, value) {
            if (!value) {
                return;
            }
            rootStyle.setProperty(name, value);
        };

        setVar("--tg-bg", themeParams.bg_color);
        setVar("--tg-ink", themeParams.text_color);
        setVar("--tg-ink-soft", themeParams.hint_color);
        setVar("--tg-accent", themeParams.link_color);
        setVar("--tg-accent-3", themeParams.button_color);
        setVar("--tg-danger", themeParams.destructive_text_color);

        if (themeParams.button_color) {
            setVar("--tg-primary-start", themeParams.button_color);
            setVar("--tg-secondary-end", themeParams.button_color);
        }
        if (themeParams.link_color) {
            setVar("--tg-primary-end", themeParams.link_color);
        }
        if (themeParams.bg_color) {
            setVar("--tg-secondary-start", hexToRgba(themeParams.bg_color, 0.85));
        }

        if (themeParams.secondary_bg_color) {
            setVar("--tg-card", hexToRgba(themeParams.secondary_bg_color, 0.8));
            setVar("--tg-card-strong", hexToRgba(themeParams.secondary_bg_color, 0.92));
        }

        if (themeParams.section_bg_color) {
            setVar("--tg-surface-from", themeParams.section_bg_color);
            setVar("--tg-surface-to", themeParams.section_bg_color);
        }
    }

    function applySystemThemeFallback() {
        const media = window.matchMedia("(prefers-color-scheme: dark)");
        const sync = function () {
            setThemeClass(media.matches ? "dark" : "light");
        };

        sync();
        if (typeof media.addEventListener === "function") {
            media.addEventListener("change", sync);
        } else if (typeof media.addListener === "function") {
            media.addListener(sync);
        }
    }

    function initTelegramWebApp() {
        try {
            if (window.Telegram && window.Telegram.WebApp) {
                document.body.classList.add("is-telegram-webview");
                const tg = window.Telegram.WebApp;
                tg.ready();
                tg.expand();
                setThemeClass(tg.colorScheme || "light");
                applyTelegramThemeParams(tg.themeParams || {});
                if (typeof tg.onEvent === "function") {
                    tg.onEvent("themeChanged", function () {
                        setThemeClass(tg.colorScheme || "light");
                        applyTelegramThemeParams(tg.themeParams || {});
                    });
                }
                return;
            }

            applySystemThemeFallback();
        } catch (_error) {
            applySystemThemeFallback();
        }
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
        element.classList.remove("is-error", "is-success");
        if (kind === "error") {
            element.classList.add("is-error");
        }
        if (kind === "success") {
            element.classList.add("is-success");
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
        return protocol === "openvpn" ? Boolean(row && row.blocked) : false;
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

        setStatus(mainStatusEl, "Загрузка данных главной страницы...", "");

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
                wireguard: '.config-table[data-protocol="wg"] .client-row',
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
                        cert_state: row.getAttribute("data-cert-state") || "",
                        cert_days: row.getAttribute("data-cert-days") || "",
                        download_vpn_url: row.getAttribute("data-download-vpn-url") || "",
                        download_az_url: row.getAttribute("data-download-az-url") || "",
                        qr_vpn_url: row.getAttribute("data-qr-vpn-url") || "",
                        qr_az_url: row.getAttribute("data-qr-az-url") || "",
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
            let emptyText = "Клиенты не найдены";
            if (statusFilter === "enabled") {
                emptyText = "Включенные конфиги не найдены";
            } else if (statusFilter === "disabled") {
                emptyText = "Выключенные конфиги не найдены";
            }
            container.innerHTML = '<div class="tg-mini-main-item"><div class="tg-mini-main-meta">' + emptyText + "</div></div>";
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

                const secondaryActions = [];
                if (row.qr_vpn_url) {
                    secondaryActions.push(
                        '<a class="tg-mini-btn tg-mini-btn-ghost tg-mini-btn-compact" target="_blank" rel="noopener" href="' + escapeHtml(row.qr_vpn_url) + '">QR VPN</a>'
                    );
                }
                if (row.qr_az_url) {
                    secondaryActions.push(
                        '<a class="tg-mini-btn tg-mini-btn-ghost tg-mini-btn-compact" target="_blank" rel="noopener" href="' + escapeHtml(row.qr_az_url) + '">QR AZ</a>'
                    );
                }

                let meta = "";
                if (isAdmin && state.mainProtocol === "openvpn" && row.cert_state) {
                    const certBadge = certChip(row.cert_state, row.cert_days);
                    const blockedBadge = row.blocked ? '<span class="tg-mini-chip tg-mini-chip-blocked">blocked</span>' : "";
                    meta = certBadge + (blockedBadge ? " " + blockedBadge : "");
                } else if (isAdmin && state.mainProtocol === "openvpn" && row.blocked) {
                    meta = '<span class="tg-mini-chip tg-mini-chip-blocked">blocked</span>';
                }

                const stateChip = configStateChip(state.mainProtocol, row);

                const toggleBtn = state.mainProtocol === "openvpn" && row.can_block
                    ? '<button type="button" class="tg-mini-btn tg-mini-btn-compact ' + (row.blocked ? "tg-mini-btn-toggle-on" : "tg-mini-btn-toggle-off") + '" data-main-action="toggle-block" data-client-name="' + escapeHtml(row.client_name) + '" data-next-blocked="' + (row.blocked ? "0" : "1") + '">' + (row.blocked ? "Включить" : "Выключить") + '</button>'
                    : "";
                if (toggleBtn) {
                    secondaryActions.push(toggleBtn);
                }

                const deleteBtn = row.can_manage && row.delete_option
                    ? '<button type="button" class="tg-mini-btn tg-mini-btn-danger tg-mini-btn-compact" data-main-action="delete" data-option="' + escapeHtml(row.delete_option) + '" data-client-name="' + escapeHtml(row.client_name) + '">Удалить</button>'
                    : "";
                if (deleteBtn) {
                    secondaryActions.push(deleteBtn);
                }

                const actionsBlock = [
                    sendActions.length ? '<div class="tg-mini-main-actions-grid">' + sendActions.join("") + '</div>' : "",
                    secondaryActions.length ? '<div class="tg-mini-main-actions-secondary">' + secondaryActions.join("") + '</div>' : "",
                ].join("");

                return (
                    '<article class="tg-mini-main-item">' +
                    '<div class="tg-mini-main-top">' +
                    '<div class="tg-mini-main-name">' + escapeHtml(row.client_name) + '</div>' +
                    '<div class="tg-mini-main-meta">' + protocolChip(state.mainProtocol) + ' ' + stateChip + '</div>' +
                    '</div>' +
                    (meta ? '<div class="tg-mini-main-meta">' + meta + '</div>' : '') +
                    '<div class="tg-mini-main-actions">' +
                    actionsBlock +
                    '</div>' +
                    '</article>'
                );
            })
            .join("");

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

        container.querySelectorAll('[data-main-action="toggle-block"]').forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const clientName = btn.getAttribute("data-client-name") || "";
                const nextBlocked = (btn.getAttribute("data-next-blocked") || "0") === "1";

                if (!clientName) {
                    return;
                }

                try {
                    btn.disabled = true;
                    const payload = await updateMainConfigState(clientName, nextBlocked);

                    const openvpnRows = state.mainData.openvpn || [];
                    openvpnRows.forEach(function (row) {
                        if (row.client_name === clientName) {
                            row.blocked = nextBlocked;
                        }
                    });

                    renderMainClients();
                    setStatus(mainStatusEl, payload.message || "Статус конфига обновлен", "success");
                } catch (error) {
                    setStatus(mainStatusEl, "Ошибка изменения статуса: " + error.message, "error");
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

                if (!window.confirm("Удалить конфигурацию клиента " + clientName + "?")) {
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

    async function updateMainConfigState(clientName, shouldBlock) {
        const formData = new FormData();
        formData.append("client_name", clientName);
        formData.append("blocked", shouldBlock ? "1" : "0");

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

        setStatus(dashboardStatusEl, "Загрузка dashboard...", "");

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
            setStatus(dashboardStatusEl, "Dashboard готов" + generatedAt, "success");

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
            WARP_OUTBOUND: "Warp outbound",
            ssh_protection: "SSH protection",
            attack_protection: "Attack protection",
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
            WARP_OUTBOUND: "Использовать WARP как исходящий маршрут для трафика.",
            ssh_protection: "Базовая защита SSH от подозрительных подключений.",
            attack_protection: "Усиленная защита от массовых сетевых атак.",
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
            grid.innerHTML = "<p>Нет доступных toggle параметров</p>";
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

        setStatus(settingsStatusEl, "Загрузка настроек...", "");

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
