document.addEventListener("DOMContentLoaded", function () {
  // Загрузка текущих настроек Antizapret
  let antizapretSchema = null;

  let antizapretHasUnsavedChanges = false;
  let antizapretNeedsApply = false;

  const sectionStatusMap = {
    unsaved: "изменено",
    pending: "требуется применить",
    applied: "применено",
    idle: "актуально",
  };

  const setSectionStatus = (state, sectionName = null) => {
    const value = sectionStatusMap[state] || sectionStatusMap.idle;
    const selector = sectionName
      ? `[data-section-status='${sectionName}']`
      : "[data-section-status]";

    document.querySelectorAll(selector).forEach((badge) => {
      badge.textContent = value;
      badge.classList.remove("state-unsaved", "state-pending", "state-applied", "state-idle");
      badge.classList.add(`state-${state}`);
    });
  };

  const setWorkbenchState = (state) => {
    const value = sectionStatusMap[state] || sectionStatusMap.idle;
    const targetIds = ["workbench-dirty-state", "sticky-dirty-status"];

    targetIds.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = value.charAt(0).toUpperCase() + value.slice(1);
      el.classList.remove("workbench-state-unsaved", "workbench-state-pending", "workbench-state-applied");
      el.classList.add(`workbench-state-${state}`);
    });
  };

  const updateActionSurface = () => {
    const activeTabId = document.querySelector(".content-tab.active")?.id;
    const isAntizapretTab = activeTabId === "antizapret-config";

    const sticky = document.getElementById("settingsStickyActions");
    const saveBtn = document.getElementById("sticky-save");
    const cancelBtn = document.getElementById("sticky-cancel");
    const applyBtn = document.getElementById("sticky-apply");
    const topApplyBtn = document.getElementById("workbench-primary-apply");

    if (sticky) {
      sticky.hidden = !isAntizapretTab || (!antizapretHasUnsavedChanges && !antizapretNeedsApply);
    }

    if (saveBtn) {
      saveBtn.disabled = !isAntizapretTab || !antizapretHasUnsavedChanges;
    }
    if (cancelBtn) {
      cancelBtn.disabled = !isAntizapretTab || !antizapretHasUnsavedChanges;
    }
    if (applyBtn) {
      applyBtn.disabled = !isAntizapretTab || (!antizapretHasUnsavedChanges && !antizapretNeedsApply);
    }
    if (topApplyBtn) {
      topApplyBtn.disabled = !isAntizapretTab || (!antizapretHasUnsavedChanges && !antizapretNeedsApply);
    }

    if (antizapretHasUnsavedChanges) {
      setWorkbenchState("unsaved");
      return;
    }

    if (antizapretNeedsApply) {
      setWorkbenchState("pending");
      return;
    }

    setWorkbenchState("applied");
  };

  // Snapshot-based dirty tracking: panel appears only when values differ from baseline.
  let _dirtySnapshot = new Map();
  let _pendingDoallContext = null;

  const _getControlValue = (control) =>
    control.type === "checkbox" ? control.checked : control.value;

  const _rebuildDirtySnapshot = () => {
    const root = document.getElementById("antizapret-config");
    if (!root) return;
    _dirtySnapshot = new Map();
    root.querySelectorAll("input, select, textarea").forEach((control) => {
      if (control.type === "hidden") return;
      _dirtySnapshot.set(control, _getControlValue(control));
    });
  };

  const _checkAntizapretDirty = (changedElement) => {
    let isDirty = false;
    _dirtySnapshot.forEach((initial, control) => {
      if (_getControlValue(control) !== initial) isDirty = true;
    });

    antizapretHasUnsavedChanges = isDirty;

    const groupSection = changedElement?.closest("[data-antizapret-group]");
    const sectionName = groupSection?.getAttribute("data-antizapret-group");
    if (sectionName) {
      setSectionStatus(isDirty ? "unsaved" : "applied", sectionName);
    }
    updateActionSurface();
  };

  // Call after save or cancel to make current values the new baseline.
  const refreshDirtySnapshot = () => {
    _rebuildDirtySnapshot();
    antizapretHasUnsavedChanges = false;
    updateActionSurface();
  };

  // Returns list of human-readable change strings for IP file toggles (e.g. ["вкл: Amazon", "выкл: Google"])
  const _collectIpFileChanges = () => {
    const changes = [];
    _dirtySnapshot.forEach((initialValue, control) => {
      if (!control.classList.contains("ip-file-toggle")) return;
      const currentValue = _getControlValue(control);
      if (currentValue === initialValue) return;
      const name = control.dataset.ipFileName || control.dataset.ipFile || "";
      if (!name) return;
      changes.push((currentValue ? "вкл" : "выкл") + ": " + name);
    });
    return changes;
  };

  const initAntizapretDirtyTracking = () => {
    const root = document.getElementById("antizapret-config");
    if (!root) return;

    _rebuildDirtySnapshot();

    root.querySelectorAll("input, select, textarea").forEach((control) => {
      if (control.type === "hidden") return;
      control.addEventListener("input", () => _checkAntizapretDirty(control));
      control.addEventListener("change", () => _checkAntizapretDirty(control));
    });
  };

  const initConfigItemDetails = () => {
    const tooltips = document.querySelectorAll("#antizapret-config .config-item-tooltip");

    tooltips.forEach((tooltip) => {
      if (tooltip.parentElement?.classList.contains("config-item-details")) {
        return;
      }

      const details = document.createElement("details");
      details.className = "config-item-details";

      const summary = document.createElement("summary");
      summary.textContent = "Подробнее";
      details.appendChild(summary);

      tooltip.classList.add("config-item-tooltip--details");
      tooltip.parentNode.insertBefore(details, tooltip);
      details.appendChild(tooltip);
    });
  };

  const collectIpFileStates = () => {
    const states = {};
    document.querySelectorAll(".ip-file-toggle[data-ip-file]").forEach((input) => {
      const fileName = input.getAttribute("data-ip-file");
      if (!fileName) return;
      states[fileName] = Boolean(input.checked);
    });
    return states;
  };

  const applyIpFileStates = (states, sourceStates) => {
    if (!states || typeof states !== "object") return;
    document.querySelectorAll(".ip-file-toggle[data-ip-file]").forEach((input) => {
      const fileName = input.getAttribute("data-ip-file");
      if (!fileName) return;
      if (Object.prototype.hasOwnProperty.call(states, fileName)) {
        input.checked = Boolean(states[fileName]);
      }
      if (sourceStates && Object.prototype.hasOwnProperty.call(sourceStates, fileName)) {
        const hasSource = Boolean(sourceStates[fileName]);
        input.disabled = !hasSource;
        input.setAttribute("data-source-exists", hasSource ? "true" : "false");
        const item = input.closest(".config-item");
        if (item) item.classList.toggle("ip-file-item--no-source", !hasSource);
        const badge = item?.querySelector(".ip-file-no-source-badge");
        const hint = item?.querySelector(".ip-file-no-source-hint");
        if (badge) badge.hidden = hasSource;
        if (hint) hint.hidden = hasSource;
      }
    });
  };

  const saveIpFileStates = async () => {
    const getCsrfToken = () => {
      return document.querySelector('input[name="csrf_token"]')?.value ||
        document.querySelector('meta[name="csrf-token"]')?.content ||
        "";
    };
    const response = await fetch("/api/antizapret/ip-files", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ states: collectIpFileStates() }),
    });

    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.message || "Ошибка сохранения состояний IP-файлов");
    }

    applyIpFileStates(payload.states || {});
    return {
      changes: Number(payload.changes || 0),
      message: payload.message || "Состояния IP-файлов сохранены",
    };
  };

  let cidrIpFileSyncTimer = null;
  let cidrIpFileSyncInFlight = false;
  let cidrIpFileSyncQueued = false;
  let cidrIpFileSyncOptions = { persist: true, strict: false };

  const syncCidrSelectionToIpFileToggles = async ({ persist = true, strict = false } = {}) => {
    const cidrCheckboxes = Array.from(document.querySelectorAll(".cidr-region-checkbox"));
    const ipFileToggles = Array.from(document.querySelectorAll(".ip-file-toggle[data-ip-file]"));

    if (!cidrCheckboxes.length || !ipFileToggles.length) {
      return { changed: 0, synced: 0, persisted: false };
    }

    const cidrKnownKeys = new Set(
      cidrCheckboxes
        .map((input) => String(input.value || "").trim())
        .filter(Boolean)
    );
    const selectedKeys = new Set(
      cidrCheckboxes
        .filter((input) => input.checked)
        .map((input) => String(input.value || "").trim())
        .filter(Boolean)
    );

    let changed = 0;
    let synced = 0;
    ipFileToggles.forEach((toggle) => {
      const fileName = String(toggle.getAttribute("data-ip-file") || "").trim();
      if (!fileName || !cidrKnownKeys.has(fileName)) return;

      synced += 1;
      const shouldBeChecked = selectedKeys.has(fileName);

      if (strict) {
        if (toggle.checked !== shouldBeChecked) {
          toggle.checked = shouldBeChecked;
          changed += 1;
        }
      } else {
        // Safety rule: CIDR autosync can auto-enable matching files,
        // but must not auto-disable already enabled IP ranges.
        if (shouldBeChecked && !toggle.checked) {
          toggle.checked = true;
          changed += 1;
        }
      }
    });

    if (!persist || changed === 0) {
      return { changed, synced, persisted: false };
    }

    const saveResult = await saveIpFileStates();
    return { changed, synced, persisted: true, saveResult };
  };

  const scheduleCidrToIpFileSync = (delay = 220, options = {}) => {
    cidrIpFileSyncOptions = {
      ...cidrIpFileSyncOptions,
      ...options,
    };

    if (cidrIpFileSyncTimer) {
      window.clearTimeout(cidrIpFileSyncTimer);
    }

    cidrIpFileSyncTimer = window.setTimeout(async () => {
      if (cidrIpFileSyncInFlight) {
        cidrIpFileSyncQueued = true;
        return;
      }

      cidrIpFileSyncInFlight = true;
      try {
        await syncCidrSelectionToIpFileToggles(cidrIpFileSyncOptions);
      } catch (error) {
        console.error("CIDR/IP-files autosync error:", error);
      } finally {
        cidrIpFileSyncInFlight = false;
        if (cidrIpFileSyncQueued) {
          cidrIpFileSyncQueued = false;
          scheduleCidrToIpFileSync(90, cidrIpFileSyncOptions);
        }
      }
    }, delay);
  };

  const loadIpFileStates = async () => {
    const response = await fetch("/api/antizapret/ip-files", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.message || "Ошибка загрузки состояний IP-файлов");
    }
    applyIpFileStates(payload.states || {}, payload.source_states);
  };

  const syncIpFilesFromList = async () => {
    const getCsrfToken = () => {
      return document.querySelector('input[name="csrf_token"]')?.value ||
        document.querySelector('meta[name="csrf-token"]')?.content ||
        "";
    };
    const response = await fetch("/api/antizapret/ip-files", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ action: "sync_with_list" }),
    });

    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.message || "Ошибка сверки IP-файлов");
    }

    applyIpFileStates(payload.states || {});
    return payload;
  };

  const getCidrStatusElement = () => document.getElementById("cidr-update-status");

  const setCidrStatus = (message, level = "info") => {
    const statusElement = getCidrStatusElement();
    if (!statusElement) return;

    if (level === "success" || level === "error") {
      window.showNotification?.(message, level);
      statusElement.hidden = true;
      statusElement.textContent = "";
      statusElement.style.display = "none";
      return;
    }

    statusElement.textContent = message;
    statusElement.className = `notification notification-${level} notification-inline-progress`;
    statusElement.hidden = false;
    statusElement.style.display = "block";
  };

  const CIDR_BUSY_SELECTOR = [
    "#cidr-select-all",
    "#cidr-clear-all",
    "#cidr-ip-files-hard-sync",
    "#cidr-refresh-regions",
    "#cidr-update-selected",
    "#cidr-update-all",
    "#cidr-rollback-selected",
    "#cidr-rollback-all",
    "#cidr-preset-europe",
    "#cidr-preset-europe-asia",
    "#cidr-preset-eu-na",
    "#cidr-preset-americas",
    "#cidr-preset-asia-focus",
    "#cidr-preset-gov-global",
    "#cidr-preset-all-fallback",
    "#cidr-preset-all-no-ru",
    "#cidr-games-select-all",
    "#cidr-games-clear-all",
    "#cidr-sync-games-hosts",
    "#cidr-games-search-input",
    "#cidr-save-total-limit",
    "#cidr-dpi-analyze",
  ].join(", ");

  const cidrProgressState = {
    timerId: null,
    stageIndex: 0,
    percent: 0,
  };
  const CIDR_TOTAL_LIMIT_MAX_IOS = 900;
  const dpiMiniReportState = {
    foundInLog: 0,
    selectedForBuild: 0,
    mandatoryDetected: 0,
    priorityForBudget: 0,
    criticalProviders: 0,
    limitValue: 0,
    clippedByLimit: null,
    originalTotal: 0,
    compressedTotal: 0,
  };

  const getCidrProgressElements = () => ({
    section: document.getElementById("cidr-update"),
    container: document.getElementById("cidr-progress"),
    label: document.getElementById("cidr-progress-label"),
    stage: document.getElementById("cidr-progress-stage"),
    percent: document.getElementById("cidr-progress-percent"),
    fill: document.getElementById("cidr-progress-fill"),
    track: document.getElementById("cidr-progress-track"),
  });

  const setCidrBusy = (isBusy) => {
    const section = document.getElementById("cidr-update");
    if (!section) return;

    section.classList.toggle("cidr-busy", Boolean(isBusy));
    section.querySelectorAll(CIDR_BUSY_SELECTOR).forEach((node) => {
      node.disabled = Boolean(isBusy);
    });

    section.querySelectorAll(
      ".cidr-region-checkbox, .cidr-scope-checkbox, .cidr-game-checkbox, #cidr-include-non-geo-fallback, #cidr-strict-geo-filter, #cidr-exclude-ru-cidrs, #cidr-total-limit-input, #cidr-filter-by-antifilter"
    ).forEach((node) => {
      node.disabled = Boolean(isBusy);
    });
  };

  const renderCidrProgress = ({ percent, stageText }) => {
    const elements = getCidrProgressElements();
    if (!elements.container) return;

    const safePercent = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
    if (elements.fill) {
      elements.fill.style.width = `${safePercent}%`;
    }
    if (elements.percent) {
      elements.percent.textContent = `${safePercent}%`;
    }
    if (elements.stage && stageText) {
      elements.stage.textContent = stageText;
    }
    if (elements.track) {
      elements.track.setAttribute("aria-valuenow", String(safePercent));
      elements.track.setAttribute("aria-valuetext", `${safePercent}%`);
    }
  };

  const stopCidrProgressTimer = () => {
    if (!cidrProgressState.timerId) return;
    window.clearInterval(cidrProgressState.timerId);
    cidrProgressState.timerId = null;
  };

  const startCidrProgress = (labelText = "Выполняется операция...", options = {}) => {
    const simulated = options.simulated !== false;
    const elements = getCidrProgressElements();
    if (!elements.container) return;

    stopCidrProgressTimer();
    cidrProgressState.percent = 4;
    cidrProgressState.stageIndex = 0;

    elements.container.hidden = false;
    if (elements.label) {
      elements.label.textContent = labelText;
    }

    const stageTexts = [
      "Подготовка запроса...",
      "Получение данных от источников...",
      "Фильтрация и объединение CIDR...",
      "Сохранение результатов...",
    ];

    renderCidrProgress({
      percent: cidrProgressState.percent,
      stageText: stageTexts[cidrProgressState.stageIndex],
    });

    if (!simulated) {
      return;
    }

    cidrProgressState.timerId = window.setInterval(() => {
      const delta = Math.floor(Math.random() * 4) + 2;
      cidrProgressState.percent = Math.min(92, cidrProgressState.percent + delta);

      if (cidrProgressState.percent >= 30) {
        cidrProgressState.stageIndex = Math.max(cidrProgressState.stageIndex, 1);
      }
      if (cidrProgressState.percent >= 55) {
        cidrProgressState.stageIndex = Math.max(cidrProgressState.stageIndex, 2);
      }
      if (cidrProgressState.percent >= 78) {
        cidrProgressState.stageIndex = Math.max(cidrProgressState.stageIndex, 3);
      }

      renderCidrProgress({
        percent: cidrProgressState.percent,
        stageText: stageTexts[cidrProgressState.stageIndex],
      });
    }, 500);
  };

  const finishCidrProgress = ({ success = true, stageText = "Готово" } = {}) => {
    const elements = getCidrProgressElements();
    if (!elements.container) return;

    stopCidrProgressTimer();
    renderCidrProgress({ percent: 100, stageText });

    if (elements.label) {
      elements.label.textContent = success ? "Операция завершена" : "Операция завершена с ошибкой";
    }

    window.setTimeout(() => {
      elements.container.hidden = true;
    }, success ? 1400 : 2200);
  };

  const getSelectedCidrRegions = () => {
    const selected = [];
    document.querySelectorAll(".cidr-region-checkbox:checked").forEach((input) => {
      const value = (input.value || "").trim();
      if (value) selected.push(value);
    });
    return selected;
  };

  const setAllCidrRegionsChecked = (checked) => {
    document.querySelectorAll(".cidr-region-checkbox").forEach((input) => {
      input.checked = Boolean(checked);
    });
  };

  const getSelectedCidrGames = () => {
    return Array.from(document.querySelectorAll(".cidr-game-checkbox:checked"))
      .map((input) => (input.value || "").trim().toLowerCase())
      .filter(Boolean);
  };

  const setAllCidrGamesChecked = (checked) => {
    document.querySelectorAll(".cidr-game-checkbox").forEach((input) => {
      input.checked = Boolean(checked);
    });
  };

  const renderCidrMeta = () => {
    const selectedProvidersCount = getSelectedCidrRegions().length;
    const { regionScopes, includeGameKeys } = getCidrRegionSettings();

    const providersEl = document.getElementById("cidr-meta-selected-providers");
    const scopesEl = document.getElementById("cidr-meta-selected-scopes");
    const gamesSelectedEl = document.getElementById("cidr-meta-games-selected");

    if (providersEl) providersEl.textContent = String(selectedProvidersCount);
    if (scopesEl) scopesEl.textContent = String(regionScopes.length);
    if (gamesSelectedEl) gamesSelectedEl.textContent = String(includeGameKeys.length);

    const cidrTotalEl = document.getElementById("cidr-meta-total-cidr");
    if (cidrTotalEl) {
      const counts = window._cidrDbProviderCounts;
      if (counts && Object.keys(counts).length > 0) {
        const selected = getSelectedCidrRegions();
        const total = selected.reduce((sum, key) => sum + (counts[key] || 0), 0);
        if (total === 0) {
          cidrTotalEl.textContent = "—";
          cidrTotalEl.className = "cidr-meta-item__value";
        } else {
          cidrTotalEl.textContent = `${total.toLocaleString("ru-RU")} / ${CIDR_TOTAL_LIMIT_MAX_IOS}`;
          if (total > CIDR_TOTAL_LIMIT_MAX_IOS) {
            cidrTotalEl.className = "cidr-meta-item__value cidr-meta-item__value--error";
          } else if (total > CIDR_TOTAL_LIMIT_MAX_IOS * 0.85) {
            cidrTotalEl.className = "cidr-meta-item__value cidr-meta-item__value--warn";
          } else {
            cidrTotalEl.className = "cidr-meta-item__value cidr-meta-item__value--ok";
          }
        }
      } else {
        cidrTotalEl.textContent = "нет данных БД";
        cidrTotalEl.className = "cidr-meta-item__value";
      }
    }
  };

  const renderCidrResultDetails = (result) => {
    const panel = document.getElementById("cidr-result-panel");
    if (!panel) return;

    const updated = Array.isArray(result?.updated) ? result.updated : [];
    const skipped = Array.isArray(result?.skipped) ? result.skipped : [];
    const failed = Array.isArray(result?.failed) ? result.failed : [];

    const updatedCountEl = document.getElementById("cidr-result-updated-count");
    const skippedCountEl = document.getElementById("cidr-result-skipped-count");
    const failedCountEl = document.getElementById("cidr-result-failed-count");
    if (updatedCountEl) updatedCountEl.textContent = String(updated.length);
    if (skippedCountEl) skippedCountEl.textContent = String(skipped.length);
    if (failedCountEl) failedCountEl.textContent = String(failed.length);

    const updatedListEl = document.getElementById("cidr-result-updated-list");
    const skippedListEl = document.getElementById("cidr-result-skipped-list");
    const failedListEl = document.getElementById("cidr-result-failed-list");
    const quality = result?.quality_report || {};
    const qualityTotals = quality?.totals || {};
    const qualityWarnings = Array.isArray(quality?.warnings) ? quality.warnings : [];
    const qualityHeadline = Number.isFinite(Number(qualityTotals.final_after_limit_cidrs))
      ? `<li><strong>Pipeline:</strong> raw ${Number(qualityTotals.raw_db_cidrs || 0)} → scope ${Number(qualityTotals.after_scope_cidrs || 0)} → ru ${Number(qualityTotals.after_ru_exclusion_cidrs || 0)} → antifilter ${Number(qualityTotals.after_antifilter_cidrs || 0)} → final ${Number(qualityTotals.final_after_limit_cidrs || 0)}</li>`
      : "";

    if (updatedListEl) {
      updatedListEl.innerHTML = updated.length
        ? `${qualityHeadline}${updated.map((item) => `<li>${item.file}: ${item.cidr_count} CIDR (${item.source || "source"})</li>`).join("")}`
        : '<li class="no-data">Нет обновленных файлов</li>';
    }

    if (skippedListEl) {
      skippedListEl.innerHTML = skipped.length
        ? skipped.map((item) => `<li>${item.file}: ${item.reason || "skipped"}</li>`).join("")
        : '<li class="no-data">Нет пропущенных файлов</li>';
    }

    if (failedListEl) {
      const warningHtml = qualityWarnings.length
        ? qualityWarnings.map((warning) => `<li>warning: ${warning}</li>`).join("")
        : "";
      failedListEl.innerHTML = failed.length
        ? `${warningHtml}${failed.map((item) => `<li>${item.file}: ${item.error || "error"}</li>`).join("")}`
        : warningHtml || '<li class="no-data">Нет ошибок</li>';
    }

    const timeEl = document.getElementById("cidr-result-timestamp");
    if (timeEl) {
      const now = new Date();
      timeEl.textContent = `Последний запуск: ${now.toLocaleString()}`;
    }

    panel.hidden = false;
    applyLimitStatsToDpiMiniReport(result);
  };

  const renderDpiMiniReport = () => {
    const el = document.getElementById("cidr-dpi-mini-report");
    if (!el) return;

    const found = Number(dpiMiniReportState.foundInLog || 0);
    const selected = Number(dpiMiniReportState.selectedForBuild || 0);
    const mandatoryDetected = Number(dpiMiniReportState.mandatoryDetected || 0);
    const priority = Number(dpiMiniReportState.priorityForBudget || 0);
    const critical = Number(dpiMiniReportState.criticalProviders || 0);
    const limit = Number(dpiMiniReportState.limitValue || 0);
    const clipped = dpiMiniReportState.clippedByLimit;
    const original = Number(dpiMiniReportState.originalTotal || 0);
    const compressed = Number(dpiMiniReportState.compressedTotal || 0);

    let clippingText = "Срез лимитом: не оценен";
    if (clipped === 0) {
      clippingText = "Срез лимитом: нет";
    } else if (Number.isFinite(clipped) && clipped > 0) {
      clippingText = `Срез лимитом: -${clipped} CIDR (${compressed}/${original})`;
      if (limit >= CIDR_TOTAL_LIMIT_MAX_IOS) {
        clippingText += `, потолок iOS ${CIDR_TOTAL_LIMIT_MAX_IOS}`;
      }
    }

    el.textContent = `Лог: найдено ${found} | В сборку: ${selected} | Обяз. detected: ${mandatoryDetected} | Приоритет: ${priority} | Критичные: ${critical} | ${clippingText}`;
    el.className = "help-text";
  };

  const updateDpiMiniReport = (patch = {}) => {
    Object.assign(dpiMiniReportState, patch || {});
    renderDpiMiniReport();
  };

  const applyLimitStatsToDpiMiniReport = (payload) => {
    const meta = payload?.global_route_optimization;
    const fallbackLimit = Number(document.getElementById("cidr-total-limit-input")?.value || 0);

    if (!meta || typeof meta !== "object") {
      updateDpiMiniReport({
        limitValue: Number.isFinite(fallbackLimit) ? fallbackLimit : 0,
        clippedByLimit: 0,
        originalTotal: 0,
        compressedTotal: 0,
      });
      return;
    }

    const original = Number(meta.original_total_cidr_count || 0);
    const compressed = Number(meta.compressed_total_cidr_count || 0);
    const limit = Number(meta.limit || 0);
    const clipped = Math.max(0, original - compressed);

    updateDpiMiniReport({
      limitValue: Number.isFinite(limit) ? limit : (Number.isFinite(fallbackLimit) ? fallbackLimit : 0),
      clippedByLimit: clipped,
      originalTotal: Number.isFinite(original) ? original : 0,
      compressedTotal: Number.isFinite(compressed) ? compressed : 0,
    });
  };

  const buildRouteLimitWarning = (result) => {
    const meta = result?.global_route_optimization;
    if (!meta || typeof meta !== "object") return "";

    const droppedMandatory = Array.isArray(meta?.dpi_mandatory?.dropped_mandatory_files)
      ? meta.dpi_mandatory.dropped_mandatory_files
      : [];
    if (droppedMandatory.length) {
      return `Лимит слишком низкий: обязательные detected-провайдеры не влезли (${droppedMandatory.join(", ")}). Увеличьте лимит до потолка iOS ${CIDR_TOTAL_LIMIT_MAX_IOS}.`;
    }

    const original = Number(meta.original_total_cidr_count || 0);
    const compressed = Number(meta.compressed_total_cidr_count || 0);
    const limit = Number(meta.limit || 0);
    if (!Number.isFinite(original) || !Number.isFinite(compressed) || original <= compressed) {
      return "";
    }

    if (limit >= CIDR_TOTAL_LIMIT_MAX_IOS) {
      return `Достигнут потолок iOS (${CIDR_TOTAL_LIMIT_MAX_IOS} CIDR): больше увеличить нельзя.`;
    }

    const target = Math.min(CIDR_TOTAL_LIMIT_MAX_IOS, original);
    return `Лимит ${limit} сжал маршруты (${compressed} из ${original}). Можно увеличить до ${target} (максимум для iOS: ${CIDR_TOTAL_LIMIT_MAX_IOS}).`;
  };

  const getCidrRegionSettings = () => {
    let selected = Array.from(document.querySelectorAll(".cidr-scope-checkbox:checked"))
      .map((input) => (input.value || "").trim().toLowerCase())
      .filter(Boolean);

    if (!selected.length) {
      selected = ["all"];
    } else if (selected.includes("all") && selected.length > 1) {
      selected = ["all"];
    }

    const includeNonGeoFallback = Boolean(
      document.getElementById("cidr-include-non-geo-fallback")?.checked
    );
    const excludeRuCidrs = Boolean(document.getElementById("cidr-exclude-ru-cidrs")?.checked);
    const includeGameKeys = getSelectedCidrGames();
    const strictGeoFilter = Boolean(document.getElementById("cidr-strict-geo-filter")?.checked);

    return {
      regionScopes: selected,
      includeNonGeoFallback,
      excludeRuCidrs,
      includeGameKeys,
      strictGeoFilter,
    };
  };

  const getDpiPriorityMinBudget = () => {
    const raw = String(document.getElementById("cidr-dpi-priority-min-budget")?.value || "").trim();
    if (!/^\d+$/.test(raw)) return 0;
    const value = Number(raw);
    if (!Number.isFinite(value) || value <= 0) return 0;
    return Math.floor(value);
  };

  const normalizeDpiFileName = (value) => String(value || "").trim().toLowerCase();

  const applyDpiAutoSelection = ({ allSeenFiles = [], priorityFiles = [], providers = [] } = {}) => {
    const normalizedSeen = Array.isArray(allSeenFiles)
      ? allSeenFiles.map(normalizeDpiFileName).filter(Boolean)
      : [];
    const normalizedPriority = Array.isArray(priorityFiles)
      ? priorityFiles.map(normalizeDpiFileName).filter(Boolean)
      : [];
    const normalizedProviders = Array.isArray(providers)
      ? providers
        .map((item) => normalizeDpiFileName(item?.file))
        .filter(Boolean)
      : [];

    const wantedFiles = normalizedSeen.length
      ? Array.from(new Set(normalizedSeen))
      : normalizedPriority.length
        ? normalizedPriority
        : Array.from(new Set(normalizedProviders));

    if (wantedFiles.length) {
      const wantedSet = new Set(wantedFiles);
      document.querySelectorAll(".cidr-region-checkbox").forEach((input) => {
        const key = normalizeDpiFileName(input.value);
        input.checked = wantedSet.has(key);
      });
    }

    document.querySelectorAll(".cidr-scope-checkbox").forEach((input) => {
      const isAll = String(input.value || "").trim().toLowerCase() === "all";
      input.checked = isAll;
    });

    const fallbackToggle = document.getElementById("cidr-include-non-geo-fallback");
    const strictToggle = document.getElementById("cidr-strict-geo-filter");
    const excludeRuToggle = document.getElementById("cidr-exclude-ru-cidrs");
    const antifilterToggle = document.getElementById("cidr-filter-by-antifilter");
    if (fallbackToggle) fallbackToggle.checked = true;
    if (strictToggle) strictToggle.checked = false;
    if (excludeRuToggle) excludeRuToggle.checked = true;
    if (antifilterToggle) antifilterToggle.checked = true;

    return wantedFiles;
  };

  const renderDpiSummary = (payload, priorityFiles) => {
    const summaryEl = document.getElementById("cidr-dpi-summary");
    if (!summaryEl) return;

    if (!payload || !payload.success) {
      summaryEl.textContent = "DPI-анализ не выполнен.";
      summaryEl.className = "help-text";
      return;
    }

    const summary = payload.summary || {};
    const providers = Array.isArray(payload.providers) ? payload.providers : [];
    const hot = providers
      .filter((p) => Number(p.max_severity_score || -1) >= 2)
      .map((p) => p.file)
      .slice(0, 8);

    const pieces = [
      `Узлов: ${Number(summary.total_nodes || 0)}`,
      `Сопоставлено: ${Number(summary.matched_nodes || 0)}`,
      `Приоритетных провайдеров: ${Array.isArray(priorityFiles) ? priorityFiles.length : 0}`,
    ];
    if (hot.length) {
      pieces.push(`Критичные: ${hot.join(", ")}`);
    }

    summaryEl.textContent = pieces.join(" | ");
    summaryEl.className = "help-text";
  };

  const applyCidrRegionPreset = ({
    scopes = ["all"],
    includeNonGeoFallback = false,
    excludeRuCidrs = false,
    includeGameKeys = null,
    strictGeoFilter = false,
    label = "",
  } = {}) => {
    const fallbackToggle = document.getElementById("cidr-include-non-geo-fallback");
    const excludeRuToggle = document.getElementById("cidr-exclude-ru-cidrs");
    const strictToggle = document.getElementById("cidr-strict-geo-filter");
    const checkboxes = Array.from(document.querySelectorAll(".cidr-scope-checkbox"));
    const gameCheckboxes = Array.from(document.querySelectorAll(".cidr-game-checkbox"));

    if (checkboxes.length) {
      const normalizedScopes = Array.isArray(scopes) && scopes.length ? scopes : ["all"];
      const effectiveScopes = normalizedScopes.includes("all") ? ["all"] : normalizedScopes;
      const wanted = new Set(effectiveScopes);

      checkboxes.forEach((input) => {
        input.checked = wanted.has((input.value || "").trim().toLowerCase());
      });
    }

    if (fallbackToggle) {
      fallbackToggle.checked = Boolean(includeNonGeoFallback);
    }

    if (excludeRuToggle) {
      excludeRuToggle.checked = Boolean(excludeRuCidrs);
    }

    if (Array.isArray(includeGameKeys) && gameCheckboxes.length) {
      const wantedGames = new Set(includeGameKeys.map((key) => String(key || "").trim().toLowerCase()).filter(Boolean));
      gameCheckboxes.forEach((input) => {
        input.checked = wantedGames.has(String(input.value || "").trim().toLowerCase());
      });
    }

    if (strictToggle) {
      strictToggle.checked = Boolean(strictGeoFilter);
    }

    if (label) {
      setCidrStatus(`Применен пресет: ${label}`, "info");
    }

    renderCidrMeta();
  };

  const renderCidrRegions = (regions) => {
    const grid = document.getElementById("cidr-regions-grid");
    if (!grid) return;

    if (!Array.isArray(regions) || !regions.length) {
      grid.innerHTML = '<p class="no-data">Нет доступных CIDR-регионов</p>';
      return;
    }

    const html = regions.map((item) => {
      const region = String(item.region || item.file || "Неизвестно");
      const fileName = String(item.file || "");
      const desc = String(item.description || "");
      const supportsGeo = Boolean(item.supports_geo_filter);
      const geoBadgeClass = supportsGeo ? "cidr-region-badge" : "cidr-region-badge cidr-region-badge--muted";
      const geoBadgeText = supportsGeo ? "Geo-фильтр: да" : "Geo-фильтр: нет";
      return `
        <label class="cidr-region-card" data-cidr-file="${fileName}">
          <input type="checkbox" class="cidr-region-checkbox" value="${fileName}" />
          <span class="cidr-region-title">${region}</span>
          <span class="cidr-region-file">${fileName}</span>
          <small class="cidr-region-desc">${desc}</small>
          <span class="${geoBadgeClass}">${geoBadgeText}</span>
        </label>
      `;
    }).join("");

    grid.innerHTML = html;
  };

  const renderCidrGameFilters = (gameFilters) => {
    const container = document.getElementById("cidr-game-filters");
    if (!container) return;

    const selectedBeforeRender = new Set(getSelectedCidrGames());

    if (!Array.isArray(gameFilters) || !gameFilters.length) {
      container.innerHTML = '<p class="no-data">Игровые фильтры недоступны</p>';
      return;
    }

    container.innerHTML = gameFilters.map((item) => {
      const key = String(item?.key || "").trim().toLowerCase();
      const title = String(item?.title || key || "Игра");
      const checked = selectedBeforeRender.has(key) ? "checked" : "";
      return `
        <label class="cidr-scope-chip cidr-game-chip">
          <input type="checkbox" class="cidr-game-checkbox" value="${key}" ${checked} />
          <span>${title}</span>
        </label>
      `;
    }).join("");

    applyCidrGameSearchFilter();
  };

  const applyCidrGameSearchFilter = () => {
    const searchInput = document.getElementById("cidr-games-search-input");
    const metaElement = document.getElementById("cidr-games-search-meta");
    const chips = Array.from(document.querySelectorAll("#cidr-game-filters .cidr-game-chip"));
    if (!chips.length) {
      if (metaElement) metaElement.textContent = "Показано: 0/0";
      return;
    }

    const query = String(searchInput?.value || "").trim().toLowerCase();
    let visibleCount = 0;

    chips.forEach((chip) => {
      const title = String(chip.querySelector(".cidr-game-chip__title")?.textContent || chip.querySelector("span")?.textContent || "").trim().toLowerCase();
      const subtitle = String(chip.querySelector(".cidr-game-chip__sub")?.textContent || chip.querySelector("input")?.dataset?.subtitle || "").trim().toLowerCase();
      const value = String(chip.querySelector(".cidr-game-checkbox")?.value || "").trim().toLowerCase();
      const matches = !query || title.includes(query) || subtitle.includes(query) || value.includes(query);
      chip.hidden = !matches;
      if (matches) visibleCount += 1;
    });

    if (metaElement) {
      metaElement.textContent = `Показано: ${visibleCount}/${chips.length}`;
    }
  };

  const fetchCidrRegions = async () => {
    const response = await fetch("/api/cidr-lists", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.message || "Не удалось получить список CIDR-регионов");
    }
    renderCidrRegions(payload.regions || []);
    renderCidrGameFilters(payload.game_filters || []);

    const totalLimitInput = document.getElementById("cidr-total-limit-input");
    const totalLimitValue = Number(payload?.settings?.openvpn_route_total_cidr_limit || 0);
    if (totalLimitInput && Number.isFinite(totalLimitValue) && totalLimitValue > 0) {
      totalLimitInput.value = String(totalLimitValue);
    }

    renderCidrMeta();
    return payload;
  };

  const runCidrAction = async ({
    action,
    regions,
    regionScopes = ["all"],
    includeNonGeoFallback = false,
    excludeRuCidrs = false,
    includeGameKeys = [],
    strictGeoFilter = false,
    openvpnRouteTotalCidrLimit = null,
    dpiLogText = "",
    dpiPriorityFiles = [],
    dpiMandatoryFiles = [],
    dpiPriorityMinBudget = 0,
    endpoint = "/api/cidr-lists",
  }) => {
    const getCsrfToken = () => {
      return document.querySelector('input[name="csrf_token"]')?.value ||
        document.querySelector('meta[name="csrf-token"]')?.content ||
        "";
    };
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({
        action,
        regions,
        region_scopes: regionScopes,
        include_non_geo_fallback: includeNonGeoFallback,
        exclude_ru_cidrs: excludeRuCidrs,
        include_game_hosts: Array.isArray(includeGameKeys) && includeGameKeys.length > 0,
        include_game_keys: includeGameKeys,
        strict_geo_filter: strictGeoFilter,
        openvpn_route_total_cidr_limit: openvpnRouteTotalCidrLimit,
        dpi_log_text: dpiLogText,
        dpi_priority_files: dpiPriorityFiles,
        dpi_mandatory_files: dpiMandatoryFiles,
        dpi_priority_min_budget: dpiPriorityMinBudget,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.message || "Ошибка операции с CIDR-списками");
    }

    // If the action was queued as a background task, poll for the result
    if (payload.queued && payload.task_id) {
      const isEstimate = String(action || "").toLowerCase() === "estimate";
      return await pollCidrTask(payload.task_id, {
        intervalMs: isEstimate ? 1200 : 800,
        timeoutMs: isEstimate ? 240000 : 1800000,
      });
    }

    if (!payload.success) {
      throw new Error(payload.message || "Ошибка операции с CIDR-списками");
    }
    return payload;
  };

  const pollCidrTask = async (taskId, options = {}) => {
    const intervalMs = options.intervalMs || 1200;
    const timeoutMs = options.timeoutMs || 1800000;
    const onProgress = typeof options.onProgress === "function" ? options.onProgress : null;
    const startedAt = Date.now();

    while (Date.now() - startedAt < timeoutMs) {
      const response = await fetch(`/api/cidr-lists/task/${encodeURIComponent(taskId)}`, {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Ошибка запроса статуса CIDR-задачи (HTTP ${response.status})`);
      }

      const task = await response.json();
      if (!task.success) {
        throw new Error(task.message || "Не удалось получить статус CIDR-задачи");
      }

      if (onProgress) {
        onProgress(task);
      }

      if (task.status === "completed") {
        return task.result || task;
      }

      if (task.status === "failed") {
        throw new Error(task.error || task.message || "CIDR-задача завершилась с ошибкой");
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }

    throw new Error("Превышено время ожидания CIDR-задачи");
  };

  const pollTaskByStatusUrl = async (statusUrl, options = {}) => {
    const intervalMs = options.intervalMs || 1200;
    const timeoutMs = options.timeoutMs || 1800000;
    const onProgress = typeof options.onProgress === "function" ? options.onProgress : null;
    const startedAt = Date.now();

    while (Date.now() - startedAt < timeoutMs) {
      const response = await fetch(statusUrl, {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Ошибка запроса статуса задачи (HTTP ${response.status})`);
      }

      const task = await response.json();
      if (!task.success) {
        throw new Error(task.message || "Не удалось получить статус задачи");
      }

      if (onProgress) {
        onProgress(task);
      }

      if (task.status === "completed") {
        return task.result || task;
      }

      if (task.status === "failed") {
        throw new Error(task.error || task.message || "Задача завершилась с ошибкой");
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }

    throw new Error("Превышено время ожидания задачи");
  };

  const executeCidrLongAction = async ({
    action,
    regions,
    regionScopes,
    includeNonGeoFallback,
    excludeRuCidrs,
    includeGameKeys,
    strictGeoFilter,
    dpiPriorityFiles = [],
    dpiMandatoryFiles = [],
    dpiPriorityMinBudget = 0,
    progressLabel,
  }) => {
    startCidrProgress(progressLabel || "Выполняется операция...", { simulated: false });

    try {
      const queued = await runCidrAction({
        action,
        regions,
        regionScopes,
        includeNonGeoFallback,
        excludeRuCidrs,
        includeGameKeys,
        strictGeoFilter,
        dpiPriorityFiles,
        dpiMandatoryFiles,
        dpiPriorityMinBudget,
      });

      if (!queued?.queued || !queued?.task_id) {
        finishCidrProgress({ success: true, stageText: "Операция завершена" });
        return queued;
      }

      const result = await pollCidrTask(queued.task_id, {
        onProgress: (task) => {
          const percent = Number(task.progress_percent || 0);
          const stageText = String(task.progress_stage || task.message || "Выполняется операция");
          renderCidrProgress({ percent, stageText });
        },
      });

      finishCidrProgress({ success: true, stageText: "Операция завершена" });
      return result;
    } catch (error) {
      finishCidrProgress({ success: false, stageText: "Операция завершилась с ошибкой" });
      throw error;
    }
  };

  const initCidrUpdateControls = () => {
    const section = document.getElementById("cidr-update");
    if (!section) return;

    let regionsLoaded = false;
    let dpiPriorityFiles = [];
    let dpiMandatoryFiles = [];
    window._cidrDpiPriorityFiles = [];
    window._cidrDpiMandatoryFiles = [];

    const ensureLoaded = async () => {
      if (regionsLoaded) return;
      await fetchCidrRegions();
      regionsLoaded = true;
    };

    const scheduleCidrEstimateRefresh = () => { };

    document.getElementById("cidr-select-all")?.addEventListener("click", () => {
      setAllCidrRegionsChecked(true);
      renderCidrMeta();
      scheduleCidrEstimateRefresh();
      scheduleCidrToIpFileSync();
    });

    document.getElementById("cidr-clear-all")?.addEventListener("click", () => {
      setAllCidrRegionsChecked(false);
      renderCidrMeta();
      scheduleCidrEstimateRefresh();
      scheduleCidrToIpFileSync();
    });

    document.getElementById("cidr-ip-files-hard-sync")?.addEventListener("click", async () => {
      const cidrCheckboxes = Array.from(document.querySelectorAll(".cidr-region-checkbox"));
      const ipFileToggles = Array.from(document.querySelectorAll(".ip-file-toggle[data-ip-file]"));

      if (!cidrCheckboxes.length || !ipFileToggles.length) {
        setCidrStatus("Нет данных для синхронизации CIDR/IP-файлов", "warning");
        return;
      }

      const cidrKnownKeys = new Set(
        cidrCheckboxes
          .map((input) => String(input.value || "").trim())
          .filter(Boolean)
      );
      const selectedKeys = new Set(
        cidrCheckboxes
          .filter((input) => input.checked)
          .map((input) => String(input.value || "").trim())
          .filter(Boolean)
      );

      let toEnable = 0;
      let toDisable = 0;
      ipFileToggles.forEach((toggle) => {
        const fileName = String(toggle.getAttribute("data-ip-file") || "").trim();
        if (!fileName || !cidrKnownKeys.has(fileName)) return;
        const shouldBeChecked = selectedKeys.has(fileName);
        if (!toggle.checked && shouldBeChecked) toEnable += 1;
        if (toggle.checked && !shouldBeChecked) toDisable += 1;
      });

      if (toEnable === 0 && toDisable === 0) {
        setCidrStatus("Жесткая синхронизация не требуется: состояния уже совпадают", "info");
        return;
      }

      const confirmMessage = [
        "Жесткая синхронизация CIDR → IP-файлы:",
        `- Будет включено: ${toEnable}`,
        `- Будет выключено: ${toDisable}`,
        "Продолжить?",
      ].join("\n");

      if (!window.confirm(confirmMessage)) {
        return;
      }

      try {
        setCidrBusy(true);
        const result = await syncCidrSelectionToIpFileToggles({ persist: true, strict: true });
        renderCidrMeta();
        setCidrStatus(`Жесткая синхронизация выполнена: изменений ${result.changed}`, "success");
      } catch (error) {
        setCidrStatus(`Ошибка жесткой синхронизации: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-games-select-all")?.addEventListener("click", () => {
      setAllCidrGamesChecked(true);
      renderCidrMeta();
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-games-clear-all")?.addEventListener("click", () => {
      setAllCidrGamesChecked(false);
      renderCidrMeta();
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-games-search-input")?.addEventListener("input", () => {
      applyCidrGameSearchFilter();
    });

    document.getElementById("cidr-save-total-limit")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        const input = document.getElementById("cidr-total-limit-input");
        const rawValue = String(input?.value || "").trim();

        if (!/^\d+$/.test(rawValue)) {
          setCidrStatus("Лимит CIDR должен быть целым числом", "warning");
          return;
        }

        const limitValue = Number(rawValue);
        if (!Number.isFinite(limitValue) || limitValue <= 0 || limitValue > CIDR_TOTAL_LIMIT_MAX_IOS) {
          setCidrStatus(`Лимит CIDR должен быть в диапазоне 1..${CIDR_TOTAL_LIMIT_MAX_IOS} (ограничение iOS)`, "warning");
          return;
        }

        startCidrProgress("Сохранение лимита CIDR...", { simulated: true });
        const result = await runCidrAction({
          action: "set_total_limit",
          regions: [],
          openvpnRouteTotalCidrLimit: limitValue,
        });

        if (input && Number.isFinite(Number(result?.openvpn_route_total_cidr_limit))) {
          input.value = String(Number(result.openvpn_route_total_cidr_limit));
        }

        finishCidrProgress({ success: true, stageText: "Лимит сохранен" });
        setCidrStatus(result?.message || "Лимит CIDR сохранен", "success");
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        finishCidrProgress({ success: false, stageText: "Ошибка сохранения лимита" });
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-sync-games-hosts")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        await ensureLoaded();
        const { includeGameKeys } = getCidrRegionSettings();
        setCidrStatus("Синхронизация include-hosts/include-ips по выбранным играм...", "info");
        startCidrProgress("Синхронизация include-hosts/include-ips...", { simulated: true });

        const result = await runCidrAction({
          action: "sync_games_hosts",
          regions: [],
          includeGameKeys,
        });

        finishCidrProgress({ success: true, stageText: "include-hosts/include-ips синхронизированы" });

        const info = result?.game_hosts_filter || {};
        const ipsInfo = result?.game_ips_filter || {};
        const selectedCount = Number(info.selected_game_count || 0);
        const domainCount = Number(info.domain_count || 0);
        const cidrCount = Number(ipsInfo.cidr_count || 0);
        const changed = Boolean(info.changed || ipsInfo.changed);
        const baseMessage = result?.message || "Игровые фильтры синхронизированы";
        const suffix = changed
          ? ` (игр: ${selectedCount}, доменов: ${domainCount}, CIDR: ${cidrCount})`
          : " (изменений не было)";

        setCidrStatus(`${baseMessage}${suffix}`, "success");
        renderCidrMeta();
      } catch (error) {
        finishCidrProgress({ success: false, stageText: "Ошибка синхронизации include-hosts/include-ips" });
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-dpi-analyze")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        await ensureLoaded();

        const dpiLogText = String(document.getElementById("cidr-dpi-log-input")?.value || "").trim();
        if (!dpiLogText) {
          setCidrStatus("Вставьте лог DPI-checkers для анализа", "warning");
          return;
        }

        startCidrProgress("Анализ DPI-лога...", { simulated: true });
        const result = await runCidrAction({
          action: "analyze_dpi_log",
          regions: [],
          dpiLogText,
        });

        const allSeenFiles = Array.isArray(result.all_seen_files) ? result.all_seen_files : [];
        const detectedFiles = Array.isArray(result.detected_files) ? result.detected_files : [];
        dpiPriorityFiles = Array.isArray(result.priority_files) ? result.priority_files : [];
        const criticalFiles = Array.isArray(result.critical_files) ? result.critical_files : [];
        const providers = Array.isArray(result.providers) ? result.providers : [];
        const selectedFiles = applyDpiAutoSelection({
          allSeenFiles,
          priorityFiles: dpiPriorityFiles,
          providers,
        });
        window._cidrDpiPriorityFiles = [...dpiPriorityFiles];
        dpiMandatoryFiles = [...detectedFiles];
        window._cidrDpiMandatoryFiles = [...dpiMandatoryFiles];

        updateDpiMiniReport({
          foundInLog: allSeenFiles.length,
          selectedForBuild: selectedFiles.length,
          mandatoryDetected: dpiMandatoryFiles.length,
          priorityForBudget: dpiPriorityFiles.length,
          criticalProviders: criticalFiles.length,
          clippedByLimit: null,
          originalTotal: 0,
          compressedTotal: 0,
        });

        renderDpiSummary(result, dpiPriorityFiles);
        renderCidrMeta();
        finishCidrProgress({ success: true, stageText: "DPI-анализ завершен" });
        setCidrStatus(
          `DPI-анализ готов: выбрано ${selectedFiles.length}, обязательных detected ${dpiMandatoryFiles.length}, приоритетных ${dpiPriorityFiles.length}`,
          selectedFiles.length ? "success" : "warning"
        );
        scheduleCidrToIpFileSync(60);
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        finishCidrProgress({ success: false, stageText: "Ошибка DPI-анализа" });
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-refresh-regions")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        startCidrProgress("Обновление списка регионов...");
        await fetchCidrRegions();
        regionsLoaded = true;
        finishCidrProgress({ success: true, stageText: "Список регионов обновлен" });
        setCidrStatus("Список регионов обновлен", "success");
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        finishCidrProgress({ success: false, stageText: "Ошибка обновления" });
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-preset-europe")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["europe"],
        includeNonGeoFallback: false,
        strictGeoFilter: false,
        label: "Только Европа",
      });
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-preset-europe-asia")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["europe", "asia-pacific"],
        includeNonGeoFallback: false,
        strictGeoFilter: false,
        label: "Европа + Азия",
      });
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-preset-eu-na")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["europe", "north-america"],
        includeNonGeoFallback: false,
        strictGeoFilter: false,
        label: "Европа + Северная Америка",
      });
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-preset-americas")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["north-america", "central-america", "south-america"],
        includeNonGeoFallback: false,
        strictGeoFilter: false,
        label: "Обе Америки",
      });
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-preset-asia-focus")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["asia-east", "asia-south", "asia-southeast", "china", "oceania"],
        includeNonGeoFallback: false,
        strictGeoFilter: false,
        label: "Азия расширенно",
      });
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-preset-gov-global")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["government", "china", "global"],
        includeNonGeoFallback: true,
        strictGeoFilter: false,
        label: "Gov + China + Global",
      });
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-preset-all-fallback")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["all"],
        includeNonGeoFallback: true,
        excludeRuCidrs: false,
        strictGeoFilter: false,
        label: "Все + fallback",
      });
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-preset-all-no-ru")?.addEventListener("click", () => {
      applyCidrRegionPreset({
        scopes: ["all"],
        includeNonGeoFallback: false,
        excludeRuCidrs: true,
        strictGeoFilter: false,
        label: "Все регионы без RU",
      });
      scheduleCidrEstimateRefresh();
    });

    const normalizeScopeSelection = (changedValue) => {
      const checkboxes = Array.from(document.querySelectorAll(".cidr-scope-checkbox"));
      if (!checkboxes.length) return;

      const allCheckbox = checkboxes.find((input) => (input.value || "").trim().toLowerCase() === "all");
      if (!allCheckbox) return;

      const hasOtherChecked = checkboxes.some(
        (input) => (input.value || "").trim().toLowerCase() !== "all" && input.checked
      );

      if (String(changedValue || "").trim().toLowerCase() === "all" && allCheckbox.checked) {
        checkboxes.forEach((input) => {
          if ((input.value || "").trim().toLowerCase() !== "all") {
            input.checked = false;
          }
        });
        return;
      }

      if (hasOtherChecked) {
        allCheckbox.checked = false;
      } else {
        allCheckbox.checked = true;
      }
    };

    document.getElementById("cidr-update-selected")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        await ensureLoaded();
        const selected = getSelectedCidrRegions();
        if (!selected.length) {
          setCidrStatus("Выберите хотя бы один регион", "warning");
          return;
        }
        const { regionScopes, includeNonGeoFallback, excludeRuCidrs, includeGameKeys, strictGeoFilter } = getCidrRegionSettings();
        setCidrStatus("Обновление выбранных CIDR-файлов...", "info");
        const result = await executeCidrLongAction({
          action: "update",
          regions: selected,
          regionScopes,
          includeNonGeoFallback,
          excludeRuCidrs,
          includeGameKeys,
          strictGeoFilter,
          dpiPriorityFiles,
          dpiMandatoryFiles,
          dpiPriorityMinBudget: getDpiPriorityMinBudget(),
          progressLabel: "Обновление выбранных CIDR-файлов...",
        });
        const updatedCount = Array.isArray(result.updated) ? result.updated.length : 0;
        const failedCount = Array.isArray(result.failed) ? result.failed.length : 0;
        const skippedNames = (Array.isArray(result.skipped) ? result.skipped : [])
          .map((item) => item?.file)
          .filter(Boolean)
          .join(", ");
        const failedNames = (Array.isArray(result.failed) ? result.failed : [])
          .map((item) => item?.file)
          .filter(Boolean)
          .join(", ");
        const routeLimitWarning = buildRouteLimitWarning(result);
        const level = failedCount > 0 || skippedNames || routeLimitWarning ? "warning" : "success";
        const details = failedNames ? ` (${failedNames})` : "";
        const skippedDetails = skippedNames ? `; пропущено: ${skippedNames}` : "";
        const warningDetails = routeLimitWarning ? `; ${routeLimitWarning}` : "";
        setCidrStatus(`Готово: обновлено ${updatedCount}, ошибок ${failedCount}${details}${skippedDetails}${warningDetails}`, level);
        renderCidrResultDetails(result);
        applyLimitStatsToDpiMiniReport(result);
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-update-all")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        await ensureLoaded();
        const { regionScopes, includeNonGeoFallback, excludeRuCidrs, includeGameKeys, strictGeoFilter } = getCidrRegionSettings();
        setCidrStatus("Обновление всех CIDR-файлов...", "info");
        const result = await executeCidrLongAction({
          action: "update",
          regions: [],
          regionScopes,
          includeNonGeoFallback,
          excludeRuCidrs,
          includeGameKeys,
          strictGeoFilter,
          dpiPriorityFiles,
          dpiMandatoryFiles,
          dpiPriorityMinBudget: getDpiPriorityMinBudget(),
          progressLabel: "Обновление всех CIDR-файлов...",
        });
        const updatedCount = Array.isArray(result.updated) ? result.updated.length : 0;
        const failedCount = Array.isArray(result.failed) ? result.failed.length : 0;
        const skippedNames = (Array.isArray(result.skipped) ? result.skipped : [])
          .map((item) => item?.file)
          .filter(Boolean)
          .join(", ");
        const failedNames = (Array.isArray(result.failed) ? result.failed : [])
          .map((item) => item?.file)
          .filter(Boolean)
          .join(", ");
        const routeLimitWarning = buildRouteLimitWarning(result);
        const level = failedCount > 0 || skippedNames || routeLimitWarning ? "warning" : "success";
        const details = failedNames ? ` (${failedNames})` : "";
        const skippedDetails = skippedNames ? `; пропущено: ${skippedNames}` : "";
        const warningDetails = routeLimitWarning ? `; ${routeLimitWarning}` : "";
        setCidrStatus(`Готово: обновлено ${updatedCount}, ошибок ${failedCount}${details}${skippedDetails}${warningDetails}`, level);
        renderCidrResultDetails(result);
        applyLimitStatsToDpiMiniReport(result);
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-rollback-selected")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        await ensureLoaded();
        const selected = getSelectedCidrRegions();
        if (!selected.length) {
          setCidrStatus("Выберите хотя бы один регион", "warning");
          return;
        }
        setCidrStatus("Откат выбранных CIDR-файлов...", "info");
        const result = await executeCidrLongAction({
          action: "rollback",
          regions: selected,
          progressLabel: "Откат выбранных CIDR-файлов...",
        });
        const restoredCount = Array.isArray(result.restored) ? result.restored.length : 0;
        setCidrStatus(`Откат выполнен: восстановлено ${restoredCount}`, "success");
        renderCidrResultDetails({
          updated: (Array.isArray(result.restored) ? result.restored : []).map((file) => ({
            file,
            cidr_count: "-",
            source: "baseline",
          })),
          skipped: [],
          failed: [],
        });
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    document.getElementById("cidr-rollback-all")?.addEventListener("click", async () => {
      try {
        setCidrBusy(true);
        await ensureLoaded();
        setCidrStatus("Откат всех CIDR-файлов к эталону...", "info");
        const result = await executeCidrLongAction({
          action: "rollback",
          regions: [],
          progressLabel: "Откат всех CIDR-файлов...",
        });
        const restoredCount = Array.isArray(result.restored) ? result.restored.length : 0;
        setCidrStatus(`Откат выполнен: восстановлено ${restoredCount}`, "success");
        renderCidrResultDetails({
          updated: (Array.isArray(result.restored) ? result.restored : []).map((file) => ({
            file,
            cidr_count: "-",
            source: "baseline",
          })),
          skipped: [],
          failed: [],
        });
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      } finally {
        setCidrBusy(false);
      }
    });

    section.addEventListener("change", (event) => {
      const target = event.target;
      if (!target) return;
      if (target.matches(".cidr-scope-checkbox")) {
        normalizeScopeSelection(target.value);
      }
      if (
        target.matches(".cidr-region-checkbox")
        || target.matches(".cidr-scope-checkbox")
        || target.matches(".cidr-game-checkbox")
        || target.id === "cidr-include-non-geo-fallback"
        || target.id === "cidr-exclude-ru-cidrs"
        || target.id === "cidr-strict-geo-filter"
      ) {
        renderCidrMeta();
        scheduleCidrEstimateRefresh();
        if (target.matches(".cidr-region-checkbox")) {
          scheduleCidrToIpFileSync();
        }
      }
    });

    window.addEventListener("settings:tab-changed", async (event) => {
      const tabId = event?.detail?.tabId;
      if (tabId !== "cidr-update") return;
      try {
        await ensureLoaded();
        renderCidrMeta();
        scheduleCidrEstimateRefresh(50);
      } catch (error) {
        setCidrStatus(`Ошибка: ${error.message}`, "error");
      }
    });

    scheduleCidrEstimateRefresh(120);
  };

  async function loadSchema() {
    try {
      const r = await fetch("/antizapret_settings_schema");
      antizapretSchema = await r.json();
    } catch (e) {
      console.error("Не удалось загрузить схему", e);
    }
  }

  async function loadAntizapretSettings() {
    if (!antizapretSchema) await loadSchema();
    if (!antizapretSchema) return;

    const data = await (await fetch("/get_antizapret_settings")).json();

    antizapretSchema.forEach(f => {
      const el = document.getElementById(f.html_id);
      if (!el) return;
      const v = data[f.key];
      if (f.type === "flag") {
        el.checked = v === "y";
      } else {
        el.value = v || "";
      }
    });

    await loadIpFileStates();

    if (!antizapretNeedsApply) {
      setSectionStatus("idle");
    }
    refreshDirtySnapshot();
  }

  async function applyAntizapretChanges(statusElement) {
    statusElement.textContent = "Применение изменений...";

    const getCsrfToken = () => {
      return document.querySelector('input[name="csrf_token"]')?.value ||
        document.querySelector('meta[name="csrf-token"]')?.content ||
        "";
    };
    const _ctx = _pendingDoallContext || "Применение настроек Antizapret";
    _pendingDoallContext = null;
    const applyResponse = await fetch("/run-doall", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ context: _ctx }),
    });

    const applyData = await applyResponse.json();

    if (applyData.queued && applyData.task_id) {
      statusElement.textContent = "Применение запущено в фоне...";
      const task = await pollBackgroundTask(applyData.task_id, { timeoutMs: 900000 });
      statusElement.textContent = task.message || "Изменения успешно применены.";
      statusElement.className = "notification notification-success";
      return true;
    }

    if (applyData.success) {
      statusElement.textContent = "Изменения успешно применены.";
      statusElement.className = "notification notification-success";
      return true;
    }

    statusElement.textContent = "Настройки сохранены, но ошибка при применении";
    statusElement.className = "notification notification-warning";
    return false;
  }

  async function saveAntizapretSettings({ applyChanges = false } = {}) {
    if (!antizapretSchema) await loadSchema();
    if (!antizapretSchema) return;

    const settings = {};
    antizapretSchema.forEach(f => {
      const el = document.getElementById(f.html_id);
      if (!el) return;
      settings[f.key] = f.type === "flag"
        ? (el.checked ? "y" : "n")
        : el.value.trim();
    });

    const statusElement = document.getElementById("config-status");
    statusElement.textContent = "Сохранение настроек...";
    statusElement.className = "notification notification-info notification-inline-progress";
    statusElement.hidden = false;
    statusElement.style.display = "block";

    try {
      const getCsrfToken = () => {
        return document.querySelector('input[name="csrf_token"]')?.value ||
          document.querySelector('meta[name="csrf-token"]')?.content ||
          "";
      };
      const saveResponse = await fetch("/update_antizapret_settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify(settings),
      });

      const saveData = await saveResponse.json();

      if (!saveData.success) {
        throw new Error(saveData.message || "Ошибка сохранения настроек");
      }

      const _ipChanges = _collectIpFileChanges();
      if (_ipChanges.length) {
        _pendingDoallContext = "Изменения: " + _ipChanges.slice(0, 6).join(", ") + (_ipChanges.length > 6 ? "…" : "");
      }
      const ipFilesResult = await saveIpFileStates();
      const antizapretChanges = Number(saveData.changes || 0);
      const hasAntizapretChanges = antizapretChanges > 0;

      refreshDirtySnapshot();

      let toastMessage = "";

      if (!applyChanges) {
        if (hasAntizapretChanges) {
          antizapretNeedsApply = true;
          setSectionStatus("pending");
          toastMessage = "Настройки сохранены. Нажмите «Применить» для запуска изменений.";
        } else {
          setSectionStatus("applied");
          toastMessage = ipFilesResult.message || "Изменения сохранены.";
        }
      } else if (hasAntizapretChanges || antizapretNeedsApply) {
        const applied = await applyAntizapretChanges(statusElement);
        antizapretNeedsApply = !applied;
        setSectionStatus(applied ? "applied" : "pending");
        if (applied) {
          toastMessage = statusElement.textContent || "Изменения применены.";
        }
      } else {
        antizapretNeedsApply = false;
        setSectionStatus("applied");
        toastMessage = ipFilesResult.message || "Изменения сохранены.";
      }

      if (toastMessage) {
        window.showNotification?.(toastMessage, "success");
      }
    } catch (error) {
      window.showNotification?.(`Ошибка: ${error.message}`, "error");
      console.error("Error:", error);
    } finally {
      if (statusElement) {
        statusElement.hidden = true;
        statusElement.textContent = "";
        statusElement.style.display = "none";
      }
      updateActionSurface();
    }
  };

  const cancelAntizapretChanges = async () => {
    await loadAntizapretSettings();
    if (antizapretNeedsApply) {
      setSectionStatus("pending");
    } else {
      setSectionStatus("idle");
    }
    refreshDirtySnapshot();
  };

  const applyPendingAntizapretChanges = async () => {
    const statusElement = document.getElementById("config-status");
    if (!statusElement) return;

    statusElement.textContent = "Применение изменений...";
    statusElement.className = "notification notification-info notification-inline-progress";
    statusElement.hidden = false;
    statusElement.style.display = "block";

    try {
      const applied = await applyAntizapretChanges(statusElement);
      antizapretNeedsApply = !applied;
      setSectionStatus(applied ? "applied" : "pending");
      if (applied) {
        window.showNotification?.(statusElement.textContent || "Изменения применены.", "success");
      }
    } catch (error) {
      window.showNotification?.(`Ошибка: ${error.message}`, "error");
    } finally {
      statusElement.hidden = true;
      statusElement.textContent = "";
      statusElement.style.display = "none";
      updateActionSurface();
    }
  };

  // Обработчик изменения размера экрана
  const handleResize = () => {
    if (window.innerWidth >= 992) {
      document.querySelector(".settings-content").style.maxHeight = "";
    }
  };

  // Обработчик ориентации
  const handleOrientationChange = () => {
    setTimeout(() => {
      const activeTab = document.querySelector(".content-tab.active");
      if (activeTab) {
        activeTab.scrollIntoView({
          behavior: "auto",
          block: "start",
        });
      }
    }, 300);
  };

  // Запуск routing
  initConfigItemDetails();
  initAntizapretDirtyTracking();
  initCidrUpdateControls();

  document.getElementById("sticky-save")?.addEventListener("click", () => {
    saveAntizapretSettings({ applyChanges: false });
  });

  document.getElementById("sticky-cancel")?.addEventListener("click", () => {
    cancelAntizapretChanges();
  });

  document.getElementById("sticky-apply")?.addEventListener("click", () => {
    if (antizapretHasUnsavedChanges) {
      saveAntizapretSettings({ applyChanges: true });
      return;
    }
    if (antizapretNeedsApply) {
      applyPendingAntizapretChanges();
    }
  });

  document.getElementById("workbench-primary-apply")?.addEventListener("click", () => {
    if (antizapretHasUnsavedChanges) {
      saveAntizapretSettings({ applyChanges: true });
      return;
    }
    if (antizapretNeedsApply) {
      applyPendingAntizapretChanges();
    }
  });

  document.getElementById("ip-files-sync-btn")?.addEventListener("click", async () => {
    const statusElement = document.getElementById("config-status");
    if (!statusElement) return;

    statusElement.textContent = "Сверка IP-файлов...";
    statusElement.className = "notification notification-info notification-inline-progress";
    statusElement.hidden = false;
    statusElement.style.display = "block";

    try {
      const result = await syncIpFilesFromList();
      const message = result.message || "Сверка IP-файлов завершена.";
      const level = (result.missing_sources || []).length > 0 ? "warning" : "success";

      if (!antizapretHasUnsavedChanges) {
        setSectionStatus(antizapretNeedsApply ? "pending" : "applied", "routing");
      }
      window.showNotification?.(message, level);
    } catch (error) {
      window.showNotification?.(`Ошибка: ${error.message}`, "error");
      console.error("IP files sync error:", error);
    } finally {
      statusElement.hidden = true;
      statusElement.textContent = "";
      statusElement.style.display = "none";
      updateActionSurface();
    }
  });

  window.addEventListener("settings:tab-changed", () => {
    updateActionSurface();
  });

  document.querySelectorAll(".save-config-btn").forEach(btn => {
    btn.addEventListener("click", () => saveAntizapretSettings({ applyChanges: false }));
  });
  window.addEventListener("resize", handleResize);
  window.addEventListener("orientationchange", handleOrientationChange);
  // ── Reverse sync: IP-file toggle → CIDR checkbox ──────────────────────
  // When user enables/disables a provider in "Фильтры и сервисы",
  // reflect that in the CIDR providers grid so both sections stay in sync.
  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!target?.matches(".ip-file-toggle[data-ip-file]")) return;
    const fileName = target.getAttribute("data-ip-file");
    if (!fileName) return;
    const cidrCheckbox = document.querySelector(`.cidr-region-checkbox[value="${CSS.escape(fileName)}"]`);
    if (cidrCheckbox && cidrCheckbox.checked !== target.checked) {
      cidrCheckbox.checked = target.checked;
      renderCidrMeta();
    }
  });

  // Initial sync: mark CIDR checkboxes that already have IP-file toggles enabled.
  // Runs once after DOMContentLoaded so the CIDR grid reflects the saved state.
  (function syncCidrFromIpTogglesOnLoad() {
    document.querySelectorAll(".ip-file-toggle[data-ip-file]").forEach((toggle) => {
      if (!toggle.checked) return;
      const fileName = toggle.getAttribute("data-ip-file");
      const cidrCheckbox = document.querySelector(`.cidr-region-checkbox[value="${CSS.escape(fileName)}"]`);
      if (cidrCheckbox && !cidrCheckbox.checked) {
        cidrCheckbox.checked = true;
      }
    });
    renderCidrMeta();
  })();

  // ── Navigation: data-go-tab links ─────────────────────────────────────
  // Clicking <a data-go-tab="cidr-update"> switches to that tab.
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-go-tab]");
    if (!link) return;
    event.preventDefault();
    const tabId = link.getAttribute("data-go-tab");
    if (!tabId) return;
    const newHash = "#" + tabId;
    if (window.location.hash === newHash) {
      window.dispatchEvent(new Event("hashchange"));
    } else {
      window.location.hash = newHash;
    }
  });

  // Expose helpers for inline scripts (settings.html DB/preset blocks)
  window._cidrRenderMeta = renderCidrMeta;
  window._scheduleCidrToIpFileSync = scheduleCidrToIpFileSync;
  window._syncCidrSelectionToIpFileToggles = syncCidrSelectionToIpFileToggles;

  // ── Step list helpers ──────────────────────────────────────────────────
  const _cidrStepShow = (steps) => {
    const list = document.getElementById("cidr-step-list");
    const items = document.getElementById("cidr-step-items");
    if (!list || !items) return;
    items.innerHTML = steps.map((s, i) =>
      `<li class="cidr-step-item" id="cidr-step-item-${i}">` +
      `<span class="cidr-step-icon">○</span>` +
      `<span class="cidr-step-text">Шаг ${i + 1} из ${steps.length}: ${s.label}</span>` +
      `</li>`
    ).join("");
    list.hidden = false;
  };

  const _cidrStepUpdate = (index, state, text) => {
    const el = document.getElementById(`cidr-step-item-${index}`);
    if (!el) return;
    const icons = { pending: "○", active: "⏳", done: "✓", error: "✗" };
    el.className = `cidr-step-item${state !== "pending" ? ` cidr-step-item--${state}` : ""}`;
    const icon = el.querySelector(".cidr-step-icon");
    const span = el.querySelector(".cidr-step-text");
    if (icon) icon.textContent = icons[state] || "○";
    if (span && text) span.textContent = text;
  };

  const _cidrStepHide = () => {
    const list = document.getElementById("cidr-step-list");
    if (list) list.hidden = true;
  };

  // ── Sequential multi-step runner exposed to inline HTML scripts ────────
  //
  // steps = [{ label: string, start: async () => task_id }]
  //
  // Each step's local 0-100% progress is mapped into its slice of the global
  // progress bar (e.g. 2 steps → step 0 uses 0-45%, step 1 uses 45-100%).
  window._pollCidrTaskExternal = async (steps) => {
    if (!Array.isArray(steps) || !steps.length) return;

    setCidrBusy(true);
    _cidrStepShow(steps);

    const sliceSize = Math.floor(90 / steps.length); // reserve last 10% for "done" animation
    let lastResult = null;
    let failed = false;

    startCidrProgress(steps[0].label + "…", { simulated: false });
    renderCidrProgress({ percent: 2, stageText: "Подготовка…" });

    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const pctStart = 2 + i * sliceSize;
      const pctEnd = 2 + (i + 1) * sliceSize;

      _cidrStepUpdate(i, "active", `Шаг ${i + 1} из ${steps.length}: ${step.label}…`);

      let taskId;
      let taskStatusUrl = "";
      try {
        const stepTask = await step.start();
        if (typeof stepTask === "string") {
          taskId = stepTask;
        } else if (stepTask && typeof stepTask === "object") {
          taskId = stepTask.taskId || stepTask.task_id || "";
          taskStatusUrl = stepTask.statusUrl || stepTask.status_url || "";
        }
        if (!taskId) {
          throw new Error("Не получен task_id");
        }
      } catch (e) {
        _cidrStepUpdate(i, "error", `Шаг ${i + 1}: ${step.label} — ошибка запуска: ${e.message}`);
        setCidrStatus("Ошибка: " + (e.message || e), "error");
        failed = true;
        break;
      }

      try {
        const isCidrStatusUrl = taskStatusUrl.includes("/api/cidr-lists/task/");
        const poller = taskStatusUrl && !isCidrStatusUrl ? pollTaskByStatusUrl : pollCidrTask;
        const pollTarget = taskStatusUrl && !isCidrStatusUrl ? taskStatusUrl : taskId;

        const result = await poller(pollTarget, {
          onProgress: (task) => {
            const rawProgress = Number(task.progress_percent);
            const localFrac = Number.isFinite(rawProgress)
              ? Math.max(0, Math.min(1, rawProgress / 100))
              : 0.5;
            const globalPct = pctStart + Math.round(localFrac * (pctEnd - pctStart));
            const stageText = String(task.progress_stage || task.message || step.label);
            renderCidrProgress({ percent: globalPct, stageText });
            _cidrStepUpdate(i, "active", `Шаг ${i + 1} из ${steps.length}: ${stageText}`);
          },
        });

        _cidrStepUpdate(i, "done", `Шаг ${i + 1} из ${steps.length}: ${step.label} — готово`);
        renderCidrProgress({ percent: pctEnd, stageText: step.label + " — готово" });
        lastResult = result;
      } catch (e) {
        _cidrStepUpdate(i, "error", `Шаг ${i + 1}: ${step.label} — ошибка: ${e.message}`);
        setCidrStatus("Ошибка на шаге «" + step.label + "»: " + (e.message || e), "error");
        failed = true;
        break;
      }
    }

    if (!failed) {
      renderCidrProgress({ percent: 100, stageText: "Все операции выполнены" });
      if (lastResult) renderCidrResultDetails(lastResult);
      finishCidrProgress({ success: true, stageText: "Выполнено" });
      setCidrStatus("Операции выполнены успешно", "success");
    } else {
      finishCidrProgress({ success: false, stageText: "Операция завершилась с ошибкой" });
    }

    window.setTimeout(_cidrStepHide, failed ? 8000 : 5000);
    setCidrBusy(false);
  };

  window.loadAntizapretSettings = loadAntizapretSettings;
  updateActionSurface();
});
