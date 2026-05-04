document.addEventListener("DOMContentLoaded", function () {
  const hideNotificationWithFx = (element, delayMs = 0) => {
    if (!element) return;
    setTimeout(() => {
      element.classList.add("notification-exit");
      setTimeout(() => {
        element.classList.remove("notification-exit");
        element.style.display = "none";
      }, 180);
    }, delayMs);
  };

  const pollBackgroundTask = async (taskId, options = {}) => {
    const intervalMs = options.intervalMs || 3000;
    const timeoutMs = options.timeoutMs || 600000;
    const startedAt = Date.now();

    while (Date.now() - startedAt < timeoutMs) {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Ошибка запроса статуса задачи (HTTP ${response.status})`);
      }

      const task = await response.json();
      if (task.status === "completed") {
        return task;
      }
      if (task.status === "failed") {
        throw new Error(task.error || task.message || "Фоновая задача завершилась с ошибкой");
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }

    throw new Error("Превышено время ожидания фоновой задачи");
  };

  // Инициализация меню
  const initMenu = () => {
    const menuItems = document.querySelectorAll(".menu-item");
    const contentTabs = document.querySelectorAll(".content-tab");

    const syncMainNavSettingsLinks = (tabId) => {
      const links = document.querySelectorAll(".nav-sublink[data-settings-tab]");
      if (!links.length) return;

      let hasActive = false;
      links.forEach((link) => {
        const isActive = link.getAttribute("data-settings-tab") === tabId;
        link.classList.toggle("is-active", isActive);
        if (isActive) hasActive = true;
      });

      if (!hasActive && links.length) {
        links[0].classList.add("is-active");
      }
    };

    const activateTab = (tabId) => {
      contentTabs.forEach((tab) => {
        tab.classList.remove("active");
        if (tab.id === tabId) tab.classList.add("active");
      });
      syncMainNavSettingsLinks(tabId);
      document.body.setAttribute("data-active-settings-tab", tabId);
      window.dispatchEvent(new CustomEvent("settings:tab-changed", { detail: { tabId } }));
    };

    menuItems.forEach((item) => {
      item.addEventListener("click", function () {
        menuItems.forEach((i) => i.classList.remove("active"));
        this.classList.add("active");
        const tabId = this.getAttribute("data-tab");

        if (tabId) {
          activateTab(tabId);
        }

        if (tabId === "antizapret-config") {
          loadAntizapretSettings();
        }
      });

      if (window.location.hash === `#${item.getAttribute("data-tab")}`) {
        item.click();
      }
    });

    if (menuItems.length > 0 && !window.location.hash) {
      const activeMenuItem = document.querySelector(".menu-item.active");
      (activeMenuItem || menuItems[0]).click();
    }

    window.addEventListener("hashchange", () => {
      const tabId = (window.location.hash || "").replace(/^#/, "").trim();
      if (!tabId) return;

      const hashMenuItem = document.querySelector(`.menu-item[data-tab='${tabId}']`);
      if (hashMenuItem) {
        hashMenuItem.click();
        return;
      }

      syncMainNavSettingsLinks(tabId);
    });
  };

  const createUserActionConfirm = () => {
    const modal = document.getElementById("userActionModal");
    const titleEl = document.getElementById("userActionModalTitle");
    const textEl = document.getElementById("userActionModalText");
    const confirmBtn = document.getElementById("userActionModalConfirm");

    if (!modal || !titleEl || !textEl || !confirmBtn) {
      return async ({ message = "Подтвердить действие?" } = {}) => window.confirm(message);
    }

    const closeTargets = modal.querySelectorAll("[data-user-action-close]");
    const closeModal = () => {
      modal.classList.remove("is-open");
      document.body.classList.remove("user-action-modal-open");
      setTimeout(() => {
        modal.setAttribute("hidden", "");
      }, 180);
    };

    return ({
      title = "Подтвердите действие",
      message = "Изменение будет применено сразу.",
      confirmText = "Подтвердить",
      confirmVariant = "danger",
    } = {}) => {
      titleEl.textContent = title;
      textEl.textContent = message;
      confirmBtn.textContent = confirmText;
      confirmBtn.classList.toggle("is-danger", confirmVariant === "danger");

      modal.removeAttribute("hidden");
      requestAnimationFrame(() => {
        modal.classList.add("is-open");
      });
      document.body.classList.add("user-action-modal-open");

      return new Promise((resolve) => {
        let done = false;

        const cleanup = (result) => {
          if (done) return;
          done = true;
          closeModal();
          confirmBtn.removeEventListener("click", onConfirm);
          closeTargets.forEach((target) => {
            target.removeEventListener("click", onCancel);
          });
          document.removeEventListener("keydown", onEsc);
          resolve(result);
        };

        const onConfirm = () => cleanup(true);
        const onCancel = () => cleanup(false);
        const onEsc = (event) => {
          if (event.key === "Escape") {
            cleanup(false);
          }
        };

        confirmBtn.addEventListener("click", onConfirm);
        closeTargets.forEach((target) => {
          target.addEventListener("click", onCancel);
        });
        document.addEventListener("keydown", onEsc);
      });
    };
  };

  const initUserActionPopups = () => {
    const askConfirm = createUserActionConfirm();

    const bindConfirm = (selector, getOptions) => {
      document.querySelectorAll(selector).forEach((form) => {
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const confirmed = await askConfirm(getOptions(form));
          if (confirmed) {
            form.submit();
          }
        });
      });
    };

    bindConfirm("form[data-user-action='delete-user']", (form) => {
      const username = form.querySelector("input[name='delete_username']")?.value.trim() || "этого пользователя";
      return {
        title: "Удалить пользователя?",
        message: `Пользователь «${username}» будет удален без возможности восстановления.`,
        confirmText: "Удалить",
        confirmVariant: "danger",
      };
    });

    bindConfirm("form[data-user-action='change-role']", (form) => {
      const username = form.querySelector("input[name='change_role_username']")?.value || "пользователя";
      const role = form.querySelector("select[name='new_role']")?.value || "новую роль";
      return {
        title: "Изменить роль?",
        message: `Для «${username}» будет установлена роль «${role}».`,
        confirmText: "Изменить",
        confirmVariant: "primary",
      };
    });

    bindConfirm("form[data-user-action='change-password']", (form) => {
      const username = form.querySelector("input[name='change_password_username']")?.value || "пользователя";
      return {
        title: "Сменить пароль?",
        message: `Пароль пользователя «${username}» будет обновлен сразу после подтверждения.`,
        confirmText: "Сменить пароль",
        confirmVariant: "danger",
      };
    });
  };

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
      sticky.hidden = !isAntizapretTab;
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

  const markAntizapretDirty = (element) => {
    antizapretHasUnsavedChanges = true;
    const groupSection = element?.closest("[data-antizapret-group]");
    const sectionName = groupSection?.getAttribute("data-antizapret-group");
    if (sectionName) {
      setSectionStatus("unsaved", sectionName);
    }
    updateActionSurface();
  };

  const initAntizapretDirtyTracking = () => {
    const root = document.getElementById("antizapret-config");
    if (!root) return;

    const controls = root.querySelectorAll("input, select, textarea");
    controls.forEach((control) => {
      if (control.type === "hidden") return;
      const markDirty = () => markAntizapretDirty(control);
      control.addEventListener("input", markDirty);
      control.addEventListener("change", markDirty);
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

  const applyIpFileStates = (states) => {
    if (!states || typeof states !== "object") return;
    document.querySelectorAll(".ip-file-toggle[data-ip-file]").forEach((input) => {
      const fileName = input.getAttribute("data-ip-file");
      if (!fileName) return;
      if (Object.prototype.hasOwnProperty.call(states, fileName)) {
        input.checked = Boolean(states[fileName]);
      }
    });
  };

  const saveIpFileStates = async () => {
    const response = await fetch("/api/antizapret/ip-files", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": document.querySelector('input[name="csrf_token"]')?.value || "",
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

  const loadIpFileStates = async () => {
    const response = await fetch("/api/antizapret/ip-files", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.message || "Ошибка загрузки состояний IP-файлов");
    }
    applyIpFileStates(payload.states || {});
  };

  const syncIpFilesFromList = async () => {
    const response = await fetch("/api/antizapret/ip-files", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": document.querySelector('input[name="csrf_token"]')?.value || "",
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
    statusElement.textContent = message;
    statusElement.className = `notification notification-${level}`;
    statusElement.style.display = "block";
    hideNotificationWithFx(statusElement, 9000);
  };

  const CIDR_BUSY_SELECTOR = [
    "#cidr-select-all",
    "#cidr-clear-all",
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

  const getCidrEstimatePlaceholder = () => {
    const strictGeoFilter = Boolean(document.getElementById("cidr-strict-geo-filter")?.checked);
    return strictGeoFilter ? "Под фильтр (strict): —" : "Под фильтр: —";
  };

  const renderCidrEstimateModeBadge = (strictGeoFilter) => {
    const badge = document.getElementById("cidr-estimate-mode-badge");
    if (!badge) return;
    badge.hidden = !strictGeoFilter;
  };

  const renderCidrMeta = () => {
    const selectedProvidersCount = getSelectedCidrRegions().length;
    const { regionScopes, includeNonGeoFallback, excludeRuCidrs, includeGameKeys, strictGeoFilter } = getCidrRegionSettings();

    const providersEl = document.getElementById("cidr-meta-selected-providers");
    const scopesEl = document.getElementById("cidr-meta-selected-scopes");
    const fallbackEl = document.getElementById("cidr-meta-fallback-state");
    const strictEl = document.getElementById("cidr-meta-strict-state");
    const ruExclusionEl = document.getElementById("cidr-meta-ru-exclusion-state");
    const gamesSelectedEl = document.getElementById("cidr-meta-games-selected");

    if (providersEl) providersEl.textContent = String(selectedProvidersCount);
    if (scopesEl) scopesEl.textContent = String(regionScopes.length);
    if (fallbackEl) fallbackEl.textContent = includeNonGeoFallback ? "on" : "off";
    if (strictEl) strictEl.textContent = strictGeoFilter ? "on" : "off";
    if (ruExclusionEl) ruExclusionEl.textContent = regionScopes.includes("all") && excludeRuCidrs ? "on" : "off";
    if (gamesSelectedEl) gamesSelectedEl.textContent = String(includeGameKeys.length);
    renderCidrEstimateModeBadge(strictGeoFilter);

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
          <small class="cidr-region-estimate" data-cidr-estimate-for="${fileName}">Под фильтр: —</small>
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
      if (metaElement) metaElement.textContent = "Показано игр: 0/0";
      return;
    }

    const query = String(searchInput?.value || "").trim().toLowerCase();
    let visibleCount = 0;

    chips.forEach((chip) => {
      const title = String(chip.querySelector("span")?.textContent || "").trim().toLowerCase();
      const value = String(chip.querySelector(".cidr-game-checkbox")?.value || "").trim().toLowerCase();
      const matches = !query || title.includes(query) || value.includes(query);
      chip.hidden = !matches;
      if (matches) visibleCount += 1;
    });

    if (metaElement) {
      metaElement.textContent = `Показано игр: ${visibleCount}/${chips.length}`;
    }
  };

  const resetCidrEstimateBadges = () => {
    const placeholder = getCidrEstimatePlaceholder();
    document.querySelectorAll(".cidr-region-estimate").forEach((el) => {
      el.textContent = placeholder;
      el.classList.remove("cidr-region-estimate--ok", "cidr-region-estimate--warn", "cidr-region-estimate--error");
      el.removeAttribute("title");
    });
  };

  const setCidrEstimateBadge = (fileName, text, level = "ok", titleText = "") => {
    if (!fileName) return;

    const badge = Array.from(document.querySelectorAll(".cidr-region-estimate")).find(
      (node) => String(node.getAttribute("data-cidr-estimate-for") || "") === String(fileName)
    );
    if (!badge) return;

    badge.textContent = text;
    badge.classList.remove("cidr-region-estimate--ok", "cidr-region-estimate--warn", "cidr-region-estimate--error");
    badge.classList.add(`cidr-region-estimate--${level}`);
    if (titleText) {
      badge.setAttribute("title", titleText);
    } else {
      badge.removeAttribute("title");
    }
  };

  const renderCidrEstimatePreview = (payload) => {
    resetCidrEstimateBadges();
    const { strictGeoFilter } = getCidrRegionSettings();
    const estimatePrefix = strictGeoFilter ? "Под фильтр (strict)" : "Под фильтр";

    const estimated = Array.isArray(payload?.estimated) ? payload.estimated : [];
    const skipped = Array.isArray(payload?.skipped) ? payload.skipped : [];
    const failed = Array.isArray(payload?.failed) ? payload.failed : [];

    estimated.forEach((item) => {
      const count = Number(item?.cidr_count || 0);
      const source = String(item?.source || "source");
      setCidrEstimateBadge(
        item?.file,
        `${estimatePrefix}: ${count} CIDR`,
        "ok",
        `Источник: ${source}`
      );
    });

    skipped.forEach((item) => {
      const reason = String(item?.reason || "skipped");
      setCidrEstimateBadge(item?.file, `${estimatePrefix}: пропуск (${reason})`, "warn");
    });

    failed.forEach((item) => {
      const errorText = String(item?.error || "error");
      setCidrEstimateBadge(item?.file, `${estimatePrefix}: ошибка источника`, "error", errorText);
    });

    applyLimitStatsToDpiMiniReport(payload);
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
    resetCidrEstimateBadges();
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
  }) => {
    const response = await fetch("/api/cidr-lists", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": document.querySelector('input[name="csrf_token"]')?.value || "",
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
    if (!response.ok || !payload.success) {
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
    let estimateTimer = null;
    let estimateRequestSeq = 0;
    let dpiPriorityFiles = [];
    let dpiMandatoryFiles = [];
    window._cidrDpiPriorityFiles = [];
    window._cidrDpiMandatoryFiles = [];

    const ensureLoaded = async () => {
      if (regionsLoaded) return;
      await fetchCidrRegions();
      regionsLoaded = true;
    };

    const refreshCidrEstimatePreview = async () => {
      await ensureLoaded();
      const requestId = ++estimateRequestSeq;
      const { regionScopes, includeNonGeoFallback, excludeRuCidrs, includeGameKeys, strictGeoFilter } = getCidrRegionSettings();

      try {
        const result = await runCidrAction({
          action: "estimate",
          regions: [],
          regionScopes,
          includeNonGeoFallback,
          excludeRuCidrs,
          includeGameKeys,
          strictGeoFilter,
          dpiPriorityFiles,
          dpiMandatoryFiles,
          dpiPriorityMinBudget: getDpiPriorityMinBudget(),
        });
        if (requestId !== estimateRequestSeq) return { stale: true };
        renderCidrEstimatePreview(result);
        return { stale: false };
      } catch (error) {
        if (requestId !== estimateRequestSeq) {
          return { stale: true };
        }
        throw error;
      }
    };

    const scheduleCidrEstimateRefresh = (delay = 280) => {
      if (estimateTimer) {
        window.clearTimeout(estimateTimer);
      }
      estimateTimer = window.setTimeout(async () => {
        const renderEstimateError = (error) => {
          resetCidrEstimateBadges();
          const { strictGeoFilter } = getCidrRegionSettings();
          const estimatePrefix = strictGeoFilter ? "Под фильтр (strict)" : "Под фильтр";
          document.querySelectorAll(".cidr-region-estimate").forEach((el) => {
            el.textContent = `${estimatePrefix}: недоступно`;
            el.classList.remove("cidr-region-estimate--ok", "cidr-region-estimate--warn");
            el.classList.add("cidr-region-estimate--error");
            el.setAttribute("title", error.message || "estimate error");
          });
        };

        try {
          const result = await refreshCidrEstimatePreview();
          if (result?.stale) return;
        } catch (error) {
          // A single retry helps when upstream providers respond slowly.
          try {
            const retryResult = await refreshCidrEstimatePreview();
            if (retryResult?.stale) return;
          } catch (retryError) {
            renderEstimateError(retryError || error);
          }
        }
      }, delay);
    };

    document.getElementById("cidr-select-all")?.addEventListener("click", () => {
      setAllCidrRegionsChecked(true);
      renderCidrMeta();
      scheduleCidrEstimateRefresh();
    });

    document.getElementById("cidr-clear-all")?.addEventListener("click", () => {
      setAllCidrRegionsChecked(false);
      renderCidrMeta();
      scheduleCidrEstimateRefresh();
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
    antizapretHasUnsavedChanges = false;
    updateActionSurface();
  }

  async function applyAntizapretChanges(statusElement) {
    statusElement.textContent = "Применение изменений...";

    const applyResponse = await fetch("/run-doall", {
      method: "POST",
      headers: {
        "X-CSRFToken": document.querySelector('input[name="csrf_token"]')
          .value,
      },
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
    statusElement.className = "notification notification-info";
    statusElement.style.display = "block";

    try {
      const saveResponse = await fetch("/update_antizapret_settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector('input[name="csrf_token"]')
            .value,
        },
        body: JSON.stringify(settings),
      });

      const saveData = await saveResponse.json();

      if (!saveData.success) {
        throw new Error(saveData.message || "Ошибка сохранения настроек");
      }

      const ipFilesResult = await saveIpFileStates();
      const antizapretChanges = Number(saveData.changes || 0);
      const hasAntizapretChanges = antizapretChanges > 0;

      antizapretHasUnsavedChanges = false;

      if (!applyChanges) {
        if (hasAntizapretChanges) {
          antizapretNeedsApply = true;
          setSectionStatus("pending");
          statusElement.textContent = "Настройки сохранены. Нажмите «Применить» для запуска изменений.";
        } else {
          setSectionStatus("applied");
          statusElement.textContent = ipFilesResult.message || "Изменения сохранены.";
        }
        statusElement.className = "notification notification-success";
      } else {
        if (hasAntizapretChanges || antizapretNeedsApply) {
          const applied = await applyAntizapretChanges(statusElement);
          antizapretNeedsApply = !applied;
          setSectionStatus(applied ? "applied" : "pending");
        } else {
          antizapretNeedsApply = false;
          setSectionStatus("applied");
          statusElement.textContent = ipFilesResult.message || "Изменения сохранены.";
          statusElement.className = "notification notification-success";
        }
      }
    } catch (error) {
      statusElement.textContent = `Ошибка: ${error.message}`;
      statusElement.className = "notification notification-error";
      console.error("Error:", error);
    } finally {
      updateActionSurface();
      hideNotificationWithFx(statusElement, 5000);
    }
  };

  const cancelAntizapretChanges = async () => {
    await loadAntizapretSettings();
    antizapretHasUnsavedChanges = false;
    if (antizapretNeedsApply) {
      setSectionStatus("pending");
    } else {
      setSectionStatus("idle");
    }
    updateActionSurface();
  };

  const applyPendingAntizapretChanges = async () => {
    const statusElement = document.getElementById("config-status");
    if (!statusElement) return;

    statusElement.textContent = "Применение изменений...";
    statusElement.className = "notification notification-info";
    statusElement.style.display = "block";

    try {
      const applied = await applyAntizapretChanges(statusElement);
      antizapretNeedsApply = !applied;
      setSectionStatus(applied ? "applied" : "pending");
    } catch (error) {
      statusElement.textContent = `Ошибка: ${error.message}`;
      statusElement.className = "notification notification-error";
    } finally {
      updateActionSurface();
      hideNotificationWithFx(statusElement, 5000);
    }
  };

  // Показать уведомление
  const showNotification = (message, type) => {
    const notification = document.createElement("div");
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
      notification.classList.add("notification-exit");
    }, 2800);

    setTimeout(() => {
      notification.remove();
    }, 3000);
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

  const initMiniAppLinkCopy = () => {
    const input = document.getElementById("tg-mini-link-input");
    const button = document.getElementById("copy-tg-mini-link-btn");
    const status = document.getElementById("copy-tg-mini-link-status");

    if (!input || !button || !status) {
      return;
    }

    const setStatus = (text, isError = false) => {
      status.textContent = text;
      status.classList.toggle("miniapp-link-status-error", Boolean(isError));
    };

    const fallbackCopy = (text) => {
      input.removeAttribute("readonly");
      input.focus();
      input.select();
      input.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      input.setAttribute("readonly", "readonly");
      return ok;
    };

    button.addEventListener("click", async () => {
      const text = (input.value || "").trim();
      if (!text) {
        setStatus("Ссылка пуста", true);
        return;
      }

      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else if (!fallbackCopy(text)) {
          throw new Error("clipboard_unavailable");
        }

        setStatus("Ссылка скопирована");
      } catch {
        setStatus("Не удалось скопировать автоматически. Скопируйте ссылку вручную.", true);
        input.focus();
        input.select();
      }
    });
  };

  const initSettingsRangeControls = () => {
    const formatSecondsHuman = (rawSeconds) => {
      const seconds = Number(rawSeconds);
      if (!Number.isFinite(seconds) || seconds < 0) {
        return "";
      }

      if (seconds < 60) {
        return `${seconds} сек`;
      }

      if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const restSeconds = seconds % 60;
        return restSeconds > 0 ? `${mins} мин ${restSeconds} сек` : `${mins} мин`;
      }

      if (seconds < 86400) {
        const hours = Math.floor(seconds / 3600);
        const restMins = Math.floor((seconds % 3600) / 60);
        return restMins > 0 ? `${hours} ч ${restMins} мин` : `${hours} ч`;
      }

      const days = Math.floor(seconds / 86400);
      const restHours = Math.floor((seconds % 86400) / 3600);
      return restHours > 0 ? `${days} д ${restHours} ч` : `${days} д`;
    };

    const controls = document.querySelectorAll("input[type='range'][data-slider-target]");
    controls.forEach((slider) => {
      const targetId = slider.getAttribute("data-slider-target");
      if (!targetId) return;

      const input = document.getElementById(targetId);
      const valueBadge = document.querySelector(`[data-slider-value-for='${targetId}']`);
      if (!input) return;

      const unit = slider.getAttribute("data-unit") || "";
      const humanize = slider.getAttribute("data-humanize") || "";
      const min = Number(slider.min);
      const max = Number(slider.max);

      const clamp = (raw) => {
        const numeric = Number(raw);
        if (!Number.isFinite(numeric)) {
          return Number.isFinite(min) ? min : 0;
        }

        if (Number.isFinite(min) && numeric < min) {
          return min;
        }
        if (Number.isFinite(max) && numeric > max) {
          return max;
        }
        return numeric;
      };

      const renderLabel = (rawValue) => {
        const numericValue = clamp(rawValue);
        const base = unit ? `${numericValue} ${unit}` : String(numericValue);

        if (humanize === "seconds") {
          const human = formatSecondsHuman(numericValue);
          if (human && human !== base) {
            return `${base} (${human})`;
          }
        }

        return base;
      };

      const applyValue = (rawValue, source) => {
        const normalized = clamp(rawValue);
        slider.value = String(normalized);
        input.value = String(normalized);

        if (valueBadge) {
          valueBadge.textContent = renderLabel(normalized);
        }

        if (source === "input") {
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      };

      const initialValue = (input.value || "").trim() || slider.value;
      applyValue(initialValue, "init");

      slider.addEventListener("input", () => {
        applyValue(slider.value, "slider");
      });

      slider.addEventListener("change", () => {
        applyValue(slider.value, "slider");
      });

      input.addEventListener("input", () => {
        const raw = (input.value || "").trim();
        if (!raw) return;
        applyValue(raw, "input");
      });

      input.addEventListener("change", () => {
        const raw = (input.value || "").trim();
        if (!raw) {
          applyValue(slider.value, "input");
          return;
        }
        applyValue(raw, "input");
      });
    });
  };

  // === ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ СИСТЕМЫ ===
  const updateSystem = async () => {
    const statusElement = document.getElementById("update-status");
    const button = document.getElementById("update-system");

    statusElement.textContent = "Обновление системы...";
    statusElement.className = "notification notification-info";
    statusElement.style.display = "block";

    try {
      const response = await fetch("/update_system", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken":
            document.querySelector('input[name="csrf_token"]')?.value || "",
        },
      });

      const data = await response.json();

      if (data.queued && data.task_id) {
        statusElement.textContent = data.message || "Обновление запущено в фоне...";
        const task = await pollBackgroundTask(data.task_id, { timeoutMs: 1200000 });
        statusElement.textContent = task.message || "Обновление завершено!";
        statusElement.className = "notification notification-success";
      } else if (data.success) {
        statusElement.textContent = data.message || "Обновление завершено!";
        statusElement.className = "notification notification-success";
      } else {
        statusElement.textContent = data.message || "Ошибка обновления";
        statusElement.className = "notification notification-error";
      }
    } catch (error) {
      statusElement.textContent = "Ошибка соединения";
      statusElement.className = "notification notification-error";
    } finally {
      hideNotificationWithFx(statusElement, 10000);
    }
  };

  // === УМНАЯ КНОПКА: ПРОВЕРКА ОБНОВЛЕНИЙ ===
  const updateButton = document.getElementById("update-system");
  const checkForUpdates = async () => {
    try {
      const response = await fetch("/check_updates");
      const data = await response.json();

      if (data.update_available) {
        updateButton.textContent = "Доступно обновление!";
        updateButton.style.background = "var(--theme-update-available, #e74c3c)";
        updateButton.disabled = false;
      } else {
        updateButton.textContent = "У вас последняя версия";
        updateButton.style.background = "var(--theme-update-latest, #27ae60)";
        updateButton.disabled = true;
      }
    } catch {
      updateButton.textContent = "Проверка недоступна";
      updateButton.style.background = "var(--theme-update-unavailable, #95a5a6)";
      updateButton.disabled = true;
    }
  };

  updateButton.addEventListener("click", () => {
    if (updateButton.disabled) return;
    if (
      confirm(
        "ВНИМАНИЕ!\nВсе ваши изменения будут удалены навсегда.\nПродолжить обновление?"
      )
    ) {
      updateSystem();
    }
  });

  // Запуск
  initConfigItemDetails();
  initMenu();
  initUserActionPopups();
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
    statusElement.className = "notification notification-info";
    statusElement.style.display = "block";

    try {
      const result = await syncIpFilesFromList();
      statusElement.textContent = result.message || "Сверка IP-файлов завершена.";

      if ((result.missing_sources || []).length > 0) {
        statusElement.className = "notification notification-warning";
      } else {
        statusElement.className = "notification notification-success";
      }

      if (!antizapretHasUnsavedChanges) {
        setSectionStatus(antizapretNeedsApply ? "pending" : "applied", "routing");
      }
    } catch (error) {
      statusElement.textContent = `Ошибка: ${error.message}`;
      statusElement.className = "notification notification-error";
      console.error("IP files sync error:", error);
    } finally {
      updateActionSurface();
      hideNotificationWithFx(statusElement, 7000);
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
  initMiniAppLinkCopy();
  initSettingsRangeControls();

  if (history.pushState) {
    document.querySelectorAll(".menu-item[data-tab]").forEach((link) => {
      link.addEventListener("click", () => {
        history.pushState(null, null, "#" + link.getAttribute("data-tab"));
      });
    });
  }

  // Expose helpers for inline scripts (settings.html DB/preset blocks)
  window._cidrRenderMeta = renderCidrMeta;

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
      try {
        taskId = await step.start();
      } catch (e) {
        _cidrStepUpdate(i, "error", `Шаг ${i + 1}: ${step.label} — ошибка запуска: ${e.message}`);
        setCidrStatus("Ошибка: " + (e.message || e), "error");
        failed = true;
        break;
      }

      try {
        const result = await pollCidrTask(taskId, {
          onProgress: (task) => {
            const localFrac = Math.max(0, Math.min(1, Number(task.progress_percent || 0) / 100));
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

  // Проверяем обновления при загрузке
  checkForUpdates();
  updateActionSurface();
});
// Обработка перезапуска службы
document
  .getElementById("restartServiceBtn")
  ?.addEventListener("click", function () {
    if (
      confirm(
        "Вы уверены? Служба будет перезапущена на 5-10 секунд.\n\nВо время перезапуска страница будет заблокирована."
      )
    ) {
      startRestartProcess();
    }
  });

function startRestartProcess() {
  const overlay = document.getElementById("loadingOverlay");
  const countdownElement = document.getElementById("countdownTimer");
  const restartForm = document.getElementById("restartForm");

  // Показываем оверлей
  overlay.style.display = "flex";
  requestAnimationFrame(() => {
    overlay.classList.add("is-open");
  });

  let countdown = 5;

  // Запускаем обратный отсчет
  const countdownInterval = setInterval(() => {
    countdown--;
    countdownElement.textContent = countdown;

    if (countdown <= 0) {
      clearInterval(countdownInterval);

      // Меняем сообщение
      document.querySelector(".loading-title").textContent =
        "⚡ Выполняется перезапуск...";
      document.querySelector(".loading-message").textContent =
        "Выполняется команда перезапуска службы.";
      countdownElement.style.display = "none";

      // Отправляем форму через 1 секунду
      setTimeout(() => {
        restartForm.submit();
      }, 1000);
    }
  }, 1000);

  // Блокируем все действия пользователя
  document.body.style.overflow = "hidden";

  // Показываем анимацию пульсации
  countdownElement.classList.add("pulse");
}

// Заблокировать клавиши во время загрузки
document.addEventListener(
  "keydown",
  function (e) {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay && overlay.style.display === "flex") {
      e.preventDefault();
      return false;
    }
  },
  false
);

// Заблокировать клики по странице во время загрузки
document.addEventListener(
  "click",
  function (e) {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay && overlay.style.display === "flex") {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
  },
  true
);

