(function () {
  const CARD_STATS_CACHE_KEY = "az_game_filters_card_stats_v1";
  const CARD_STATS_CACHE_TTL_MS = 12 * 60 * 60 * 1000;

  const state = {
    items: [],
    modeByGameKey: {},
    isBusy: false,
    onSelectionChanged: null,
    includeDomains: false,
    perGameStats: {},
    estimateRunId: 0,
    onEstimateGame: null,
  };

  const byId = (id) => document.getElementById(id);

  const loadCachedStats = () => {
    try {
      const raw = window.localStorage.getItem(CARD_STATS_CACHE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      const ts = Number(parsed?.ts || 0);
      const data = parsed?.data;
      if (!Number.isFinite(ts) || !data || typeof data !== "object") return {};
      if ((Date.now() - ts) > CARD_STATS_CACHE_TTL_MS) return {};
      return data;
    } catch (_error) {
      return {};
    }
  };

  const persistCachedStats = () => {
    try {
      window.localStorage.setItem(
        CARD_STATS_CACHE_KEY,
        JSON.stringify({
          ts: Date.now(),
          data: state.perGameStats || {},
        }),
      );
    } catch (_error) {
      // ignore private mode / quota errors
    }
  };

  const normalizeProviderName = (value) => String(value || "").trim();

  const inferProviderFromSubtitle = (subtitle) => {
    const raw = String(subtitle || "").trim();
    if (!raw) return "Unknown";
    const parts = raw.split("—");
    return normalizeProviderName(parts[0] || raw) || "Unknown";
  };

  const normalizeItem = (item) => {
    const key = String(item?.key || "").trim().toLowerCase();
    const title = String(item?.title || key || "Игра").trim();
    const subtitle = String(item?.subtitle || "").trim();
    const domainCount = Number(item?.domain_count || 0);
    const asnCount = Number(item?.asn_count || 0);
    const provider = normalizeProviderName(item?.provider) || inferProviderFromSubtitle(subtitle);
    const sourceType = String(item?.source_type || (asnCount > 0 ? "asn" : "dns")).trim().toLowerCase() || "dns";
    return {
      key,
      title,
      subtitle,
      domain_count: Number.isFinite(domainCount) ? domainCount : 0,
      asn_count: Number.isFinite(asnCount) ? asnCount : 0,
      provider,
      source_type: sourceType === "asn" ? "asn" : "dns",
    };
  };

  const getModeByKey = (key) => {
    const normalizedKey = String(key || "").trim().toLowerCase();
    const mode = String(state.modeByGameKey?.[normalizedKey] || "none").trim().toLowerCase();
    if (mode === "include" || mode === "exclude") return mode;
    return "none";
  };
  const getIncludeKeys = () => state.items.map((item) => item.key).filter((key) => getModeByKey(key) === "include");
  const getExcludeKeys = () => state.items.map((item) => item.key).filter((key) => getModeByKey(key) === "exclude");
  const getAssignedKeys = () => state.items.map((item) => item.key).filter((key) => getModeByKey(key) !== "none");
  const getIncludeDomains = () => Boolean(byId("cidr-games-include-domains")?.checked);

  const getPerGameStat = (key) => {
    const normalizedKey = String(key || "").trim().toLowerCase();
    const hasValue = Object.prototype.hasOwnProperty.call(state.perGameStats || {}, normalizedKey);
    const item = state.perGameStats?.[normalizedKey] || {};
    return {
      loading: !hasValue,
      cidr_count: Number(item.cidr_count || 0),
      overlap_count: Number(item.overlap_count || 0),
    };
  };

  const toCompactCount = (value, loading = false) => {
    if (loading) return "...";
    const num = Number(value || 0);
    if (!Number.isFinite(num) || num <= 0) return "0";
    return num > 10 ? "10+" : String(num);
  };

  const detectConflictedKeys = (includeGameKeys, excludeGameKeys) => {
    const includeSet = new Set((Array.isArray(includeGameKeys) ? includeGameKeys : []).map((key) => String(key || "").trim().toLowerCase()).filter(Boolean));
    const excludeSet = new Set((Array.isArray(excludeGameKeys) ? excludeGameKeys : []).map((key) => String(key || "").trim().toLowerCase()).filter(Boolean));
    return Array.from(includeSet).filter((key) => excludeSet.has(key));
  };

  const cardMatchesFilters = (card, query, provider, onlySelected) => {
    const title = String(card.querySelector(".cidr-game-chip__title")?.textContent || "").trim().toLowerCase();
    const subtitle = String(card.querySelector(".cidr-game-chip__sub")?.textContent || card.dataset.subtitle || "").trim().toLowerCase();
    const value = String(card.dataset.gameKey || "").trim().toLowerCase();
    const cardProvider = String(card.dataset.gameProvider || "").trim().toLowerCase();
    const mode = getModeByKey(value);
    if (query && !title.includes(query) && !subtitle.includes(query) && !value.includes(query)) return false;
    if (provider !== "all" && cardProvider !== provider) return false;
    if (onlySelected && mode === "none") return false;
    return true;
  };

  const updateTopStats = (visibleCount) => {
    const total = state.items.length;
    const selected = getAssignedKeys().length;
    const selectedEl = byId("cidr-games-selected-count");
    const visibleEl = byId("cidr-games-visible-count");
    const totalEl = byId("cidr-games-total-count");
    const searchMeta = byId("cidr-games-search-meta");
    if (selectedEl) selectedEl.textContent = String(selected);
    if (visibleEl) visibleEl.textContent = String(Number.isFinite(visibleCount) ? visibleCount : total);
    if (totalEl) totalEl.textContent = String(total);
    if (searchMeta) searchMeta.textContent = `Показано: ${Number.isFinite(visibleCount) ? visibleCount : total}/${total}`;
  };

  const notifySelectionChanged = () => {
    if (typeof state.onSelectionChanged === "function") {
      state.onSelectionChanged({
        includeGameKeys: getIncludeKeys(),
        excludeGameKeys: getExcludeKeys(),
      });
    }
  };

  const renderProviderOptions = () => {
    const providerSelect = byId("cidr-games-provider-filter");
    if (!providerSelect) return;
    const selectedValue = String(providerSelect.value || "all").trim().toLowerCase();
    const providers = Array.from(
      new Set(state.items.map((item) => normalizeProviderName(item.provider)).filter(Boolean))
    ).sort((a, b) => a.localeCompare(b, "ru"));
    providerSelect.innerHTML = [
      '<option value="all">Все провайдеры</option>',
      ...providers.map((provider) => `<option value="${provider.toLowerCase()}">${provider}</option>`),
    ].join("");
    providerSelect.value = providers.some((p) => p.toLowerCase() === selectedValue) ? selectedValue : "all";
  };

  const renderCards = () => {
    const container = byId("cidr-game-filters");
    if (!container) return;
    if (!state.items.length) {
      container.innerHTML = '<p class="no-data">Игровые фильтры недоступны</p>';
      updateTopStats(0);
      return;
    }

    container.innerHTML = state.items
      .map((item) => {
        const mode = getModeByKey(item.key);
        const subtitleHtml = item.subtitle
          ? `<span class="cidr-game-chip__sub">${item.subtitle}</span>`
          : "";
        const gameStats = getPerGameStat(item.key);
        const gameStatsHtml = `
          <span class="cidr-game-chip__stats">
            <small>CIDR: <strong class="${gameStats.loading ? "metric-loading" : ""}">${toCompactCount(gameStats.cidr_count, gameStats.loading)}</strong></small>
            <small>Пересечения: <strong class="${gameStats.loading ? "metric-loading" : ""}">${toCompactCount(gameStats.overlap_count, gameStats.loading)}</strong></small>
          </span>
        `;
        const domainMeta = state.includeDomains ? `<small>${item.domain_count} доменов</small>` : "";
        const asnMeta = item.asn_count > 0 ? `<small>${item.asn_count} ASN</small>` : "";
        return `
          <label class="cidr-scope-chip cidr-game-chip"
            data-game-key="${item.key}"
            data-game-provider="${item.provider.toLowerCase()}"
            data-subtitle="${item.subtitle}">
            <input type="hidden" class="cidr-game-mode-input" value="${mode}" data-game-key="${item.key}" />
            <div class="cidr-game-chip__body">
              <span class="cidr-game-chip__title">${item.title}</span>
              ${subtitleHtml}
              ${gameStatsHtml}
              <span class="cidr-game-chip__meta">
                ${domainMeta}
                ${asnMeta}
              </span>
            </div>
            <div class="cidr-game-chip__mode" data-mode="${mode}">
              <button type="button" class="cidr-game-mode-btn is-include ${mode === "include" ? "is-active" : ""}" data-game-mode-btn="include">VPN</button>
              <button type="button" class="cidr-game-mode-btn is-exclude ${mode === "exclude" ? "is-active" : ""}" data-game-mode-btn="exclude">DIRECT</button>
              <button type="button" class="cidr-game-mode-btn is-none ${mode === "none" ? "is-active" : ""}" data-game-mode-btn="none">Не выбрано</button>
            </div>
          </label>
        `;
      })
      .join("");
  };

  const applyFilters = () => {
    const query = String(byId("cidr-games-search-input")?.value || "").trim().toLowerCase();
    const provider = String(byId("cidr-games-provider-filter")?.value || "all").trim().toLowerCase();
    const onlySelected = Boolean(byId("cidr-games-only-selected")?.checked);
    const chips = Array.from(document.querySelectorAll("#cidr-game-filters .cidr-game-chip"));
    let visibleCount = 0;
    chips.forEach((chip) => {
      const matches = cardMatchesFilters(chip, query, provider, onlySelected);
      chip.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    updateTopStats(visibleCount);
    return visibleCount;
  };

  const setBusy = (isBusy) => {
    state.isBusy = Boolean(isBusy);
    document.querySelectorAll("[data-game-filter-control]").forEach((node) => {
      node.disabled = state.isBusy;
    });
  };

  const setMode = (key, mode) => {
    const normalizedKey = String(key || "").trim().toLowerCase();
    if (!normalizedKey) return;
    const nextMode = mode === "include" || mode === "exclude" ? mode : "none";
    state.modeByGameKey[normalizedKey] = nextMode;
  };

  const setModeForKeys = (keys, mode) => {
    (Array.isArray(keys) ? keys : []).forEach((key) => setMode(key, mode));
  };

  const setSelectedKeys = (keys) => {
    const next = new Set(
      (Array.isArray(keys) ? keys : [])
        .map((key) => String(key || "").trim().toLowerCase())
        .filter(Boolean)
    );
    state.items.forEach((item) => {
      state.modeByGameKey[item.key] = next.has(item.key) ? "include" : "none";
    });
    renderCards();
    applyFilters();
    notifySelectionChanged();
  };

  const setModeMapping = (modeByKey = {}) => {
    const next = {};
    state.items.forEach((item) => {
      const mode = String(modeByKey?.[item.key] || "none").trim().toLowerCase();
      next[item.key] = mode === "include" || mode === "exclude" ? mode : "none";
    });
    state.modeByGameKey = next;
    updateTopStats();
    renderCards();
    applyFilters();
    notifySelectionChanged();
  };

  const resetAllModes = () => {
    state.items.forEach((item) => {
      state.modeByGameKey[item.key] = "none";
    });
    renderCards();
    applyFilters();
    notifySelectionChanged();
  };

  const renderPreview = (payload) => {
    const panel = byId("cidr-games-preview-panel");
    if (!panel) return;
    const preview = payload?.preview || payload || {};
    const selectedCount = Number(preview.selected_game_count || preview.selected_count || 0);
    const domainCount = Number(preview.domain_count || 0);
    const cidrCount = Number(preview.cidr_count || 0);
    const unresolvedCount = Number(preview.unresolved_domain_count || 0);
    const warningMessage = String(preview.warning || preview.message || "").trim();
    const overlapSummary = preview?.overlap_summary || {};
    const overlapExamples = Array.isArray(overlapSummary.overlap_examples) ? overlapSummary.overlap_examples : [];
    const overlapCount = Number(overlapSummary.overlap_count || 0);
    const overlapGames = Number(overlapSummary.overlap_game_keys_count || 0);
    const includeDomains = Boolean(preview.include_game_domains);
    const domainsToAdd = Array.isArray(preview.domains_to_add) ? preview.domains_to_add : [];
    const perGameStats = (preview.per_game_stats && typeof preview.per_game_stats === "object")
      ? preview.per_game_stats
      : {};
    state.perGameStats = {
      ...(state.perGameStats || {}),
      ...perGameStats,
    };
    persistCachedStats();
    state.includeDomains = includeDomains;

    const selectedEl = byId("cidr-games-preview-selected");
    const domainsEl = byId("cidr-games-preview-domains");
    const cidrsEl = byId("cidr-games-preview-cidrs");
    const unresolvedEl = byId("cidr-games-preview-unresolved");
    const updatedEl = byId("cidr-games-preview-updated-at");
    const warningsEl = byId("cidr-games-preview-warnings");
    const overlapCountEl = byId("cidr-games-preview-overlap-count");
    const overlapGamesEl = byId("cidr-games-preview-overlap-games");
    const domainsEnabledEl = byId("cidr-games-preview-domains-enabled");
    const overlapWrapEl = byId("cidr-games-preview-overlap-wrap");
    const overlapListEl = byId("cidr-games-preview-overlap-list");
    const domainsWrapEl = byId("cidr-games-preview-domains-wrap");
    const domainsListEl = byId("cidr-games-preview-domains-list");

    if (selectedEl) selectedEl.textContent = String(selectedCount);
    if (domainsEl) domainsEl.textContent = String(domainCount);
    if (cidrsEl) cidrsEl.textContent = String(cidrCount);
    if (unresolvedEl) unresolvedEl.textContent = String(unresolvedCount);
    if (updatedEl) updatedEl.textContent = `Обновлено: ${new Date().toLocaleString()}`;
    if (overlapCountEl) overlapCountEl.textContent = String(overlapCount);
    if (overlapGamesEl) overlapGamesEl.textContent = String(overlapGames);
    if (domainsEnabledEl) domainsEnabledEl.textContent = includeDomains ? "да" : "нет";
    if (warningsEl) {
      const overlapText = overlapCount > 0
        ? `Пересечения с существующими списками: ${overlapCount}. `
        : "";
      warningsEl.textContent = `${overlapText}${warningMessage}`.trim();
    }

    if (overlapWrapEl && overlapListEl) {
      if (overlapExamples.length) {
        overlapWrapEl.hidden = false;
        overlapListEl.innerHTML = overlapExamples
          .slice(0, 30)
          .map((item) => {
            const gameCidr = String(item?.game_cidr || "—");
            const existingCidr = String(item?.existing_cidr || "—");
            const file = String(item?.file || "—");
            return `<li><code>${gameCidr}</code> пересекается с <code>${existingCidr}</code> в <code>${file}</code></li>`;
          })
          .join("");
      } else {
        overlapWrapEl.hidden = true;
        overlapListEl.innerHTML = "";
      }
    }

    if (domainsWrapEl && domainsListEl) {
      if (includeDomains && domainsToAdd.length) {
        domainsWrapEl.hidden = false;
        domainsListEl.innerHTML = domainsToAdd
          .slice(0, 100)
          .map((domain) => `<li><code>${String(domain || "")}</code></li>`)
          .join("");
      } else {
        domainsWrapEl.hidden = true;
        domainsListEl.innerHTML = "";
      }
    }

    renderCards();
    applyFilters();

    panel.classList.remove("is-success", "is-warning");
    if (unresolvedCount > 0 || overlapCount > 0) {
      panel.classList.add("is-warning");
    } else {
      panel.classList.add("is-success");
    }
    panel.hidden = false;
  };

  const setupInteractionHandlers = (callbacks) => {
    byId("cidr-games-search-input")?.addEventListener("input", applyFilters);
    byId("cidr-games-provider-filter")?.addEventListener("change", applyFilters);
    byId("cidr-games-only-selected")?.addEventListener("change", applyFilters);
    byId("cidr-games-include-domains")?.addEventListener("change", () => {
      state.includeDomains = getIncludeDomains();
      renderCards();
      applyFilters();
    });

    byId("cidr-game-filters")?.addEventListener("click", (event) => {
      const target = event.target;
      if (!target || !target.matches(".cidr-game-mode-btn")) return;
      const nextMode = String(target.getAttribute("data-game-mode-btn") || "none").trim().toLowerCase();
      const card = target.closest(".cidr-game-chip");
      const key = String(card?.dataset?.gameKey || "").trim().toLowerCase();
      if (!key) return;
      setMode(key, nextMode);
      renderCards();
      applyFilters();
      notifySelectionChanged();
    });

    byId("cidr-games-reset-all")?.addEventListener("click", () => {
      resetAllModes();
    });

    byId("cidr-games-preview-sync")?.addEventListener("click", async () => {
      if (typeof callbacks.onPreview !== "function") return;
      try {
        setBusy(true);
        const includeGameKeys = getIncludeKeys();
        const excludeGameKeys = getExcludeKeys();
        const conflicted = detectConflictedKeys(includeGameKeys, excludeGameKeys);
        if (conflicted.length) {
          throw new Error(`Конфликт назначения: ${conflicted.slice(0, 8).join(", ")}`);
        }
        const result = await callbacks.onPreview({
          includeGameKeys,
          excludeGameKeys,
          includeGameDomains: getIncludeDomains(),
        });
        if (result?.includePreview) {
          renderPreview(result.includePreview);
        } else if (result?.excludePreview) {
          renderPreview(result.excludePreview);
        } else {
          renderPreview(result);
        }
      } catch (error) {
        if (typeof callbacks.onError === "function") {
          callbacks.onError(error);
        }
      } finally {
        setBusy(false);
      }
    });

    byId("cidr-sync-games-apply")?.addEventListener("click", async () => {
      if (typeof callbacks.onApplyRoutes !== "function") return;
      try {
        setBusy(true);
        const includeGameKeys = getIncludeKeys();
        const excludeGameKeys = getExcludeKeys();
        const conflicted = detectConflictedKeys(includeGameKeys, excludeGameKeys);
        if (conflicted.length) {
          throw new Error(`Конфликт назначения: ${conflicted.slice(0, 8).join(", ")}`);
        }
        const result = await callbacks.onApplyRoutes({
          includeGameKeys,
          excludeGameKeys,
          includeGameDomains: getIncludeDomains(),
        });
        const previewPayload = result?.previewPayload || result?.preview || null;
        if (previewPayload) {
          renderPreview(previewPayload);
        }
      } catch (error) {
        if (typeof callbacks.onError === "function") {
          callbacks.onError(error);
        }
      } finally {
        setBusy(false);
      }
    });
  };

  const runProgressiveCardEstimates = async () => {
    if (typeof state.onEstimateGame !== "function" || !state.items.length) return;
    const runId = ++state.estimateRunId;
    const queue = state.items.map((item) => item.key).filter(Boolean);
    for (const key of queue) {
      if (runId !== state.estimateRunId) return;
      if (state.perGameStats[key]) continue;
      try {
        const previewPayload = await state.onEstimateGame(key);
        if (runId !== state.estimateRunId) return;
        const preview = previewPayload?.preview || previewPayload || {};
        const perGame = preview?.per_game_stats?.[key] || {};
        const overlapSummary = preview?.overlap_summary || {};
        const cidrCount = Number(perGame.cidr_count || preview.cidr_count || 0);
        const overlapCount = Number(perGame.overlap_count || overlapSummary.overlap_count || 0);
        state.perGameStats[key] = {
          cidr_count: Number.isFinite(cidrCount) ? cidrCount : 0,
          overlap_count: Number.isFinite(overlapCount) ? overlapCount : 0,
        };
        persistCachedStats();
        renderCards();
        applyFilters();
      } catch (_error) {
        // silent: keep card at zero if preload estimate fails
      }
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
  };

  const hydrateModesFromDom = () => {
    const next = {};
    document.querySelectorAll("#cidr-game-filters .cidr-game-mode-input").forEach((input) => {
      const key = String(input.getAttribute("data-game-key") || "").trim().toLowerCase();
      if (!key) return;
      const mode = String(input.value || "none").trim().toLowerCase();
      next[key] = mode === "include" || mode === "exclude" ? mode : "none";
    });
    state.modeByGameKey = next;
  };

  const setFilters = (items) => {
    state.estimateRunId += 1;
    state.items = (Array.isArray(items) ? items : []).map(normalizeItem).filter((item) => Boolean(item.key));
    state.includeDomains = getIncludeDomains();
    const cachedStats = loadCachedStats();
    const availableKeys = new Set(state.items.map((item) => item.key));
    state.perGameStats = Object.fromEntries(
      Object.entries(cachedStats).filter(([key]) => availableKeys.has(String(key || "").trim().toLowerCase()))
    );
    const modeBefore = { ...(state.modeByGameKey || {}) };
    renderProviderOptions();
    state.modeByGameKey = Object.fromEntries(
      state.items.map((item) => {
        const mode = String(modeBefore[item.key] || "none").trim().toLowerCase();
        return [item.key, (mode === "include" || mode === "exclude") ? mode : "none"];
      })
    );
    renderCards();
    if (Object.keys(modeBefore).length > 0) {
      setModeMapping(modeBefore);
    } else {
      hydrateModesFromDom();
    }
    applyFilters();
    notifySelectionChanged();
    runProgressiveCardEstimates();
  };

  const init = (callbacks = {}) => {
    state.onSelectionChanged =
      typeof callbacks.onSelectionChanged === "function" ? callbacks.onSelectionChanged : null;
    state.onEstimateGame =
      typeof callbacks.onEstimateGame === "function" ? callbacks.onEstimateGame : null;
    hydrateModesFromDom();
    setupInteractionHandlers({
      onPreview: callbacks.onPreview,
      onApplyRoutes: callbacks.onApplyRoutes,
      onError: callbacks.onError,
    });
    setFilters(state.items);
    return {
      setFilters,
      setBusy,
      applyFilters,
      setSelectedKeys,
      setModeMapping,
      getSelectedKeys: getIncludeKeys,
      getIncludeKeys,
      getExcludeKeys,
      renderPreview,
    };
  };

  window.AntiZapretGameFilters = {
    init,
    setFilters,
    setSelectedKeys,
    setModeMapping,
    getSelectedKeys: getIncludeKeys,
    getIncludeKeys,
    getExcludeKeys,
    setBusy,
    applyFilters,
    renderPreview,
  };
})();
