(function () {
  const CARD_STATS_CACHE_KEY = "az_provider_filters_card_stats_v1";
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

  const progressState = {
    timerId: null,
    percent: 0,
    stageIndex: 0,
    stages: [],
  };

  const PREVIEW_PROGRESS_STAGES = [
    "Подготовка проверки...",
    "Загрузка игровых IP и ASN...",
    "Проверка VPN-маршрутов...",
    "Проверка DIRECT-маршрутов...",
    "Анализ пересечений...",
  ];

  const APPLY_PROGRESS_STAGES = [
    "Подготовка применения...",
    "Синхронизация VPN (include)...",
    "Синхронизация DIRECT (exclude)...",
    "Запись AZ-Game файлов...",
  ];

  const byId = (id) => document.getElementById(id);

  const getProgressElements = () => ({
    container: byId("cidr-games-progress"),
    label: byId("cidr-games-progress-label"),
    stage: byId("cidr-games-progress-stage"),
    percent: byId("cidr-games-progress-percent"),
    fill: byId("cidr-games-progress-fill"),
    track: byId("cidr-games-progress-track"),
    overlay: byId("cidr-games-busy-overlay"),
    overlayLabel: byId("cidr-games-busy-overlay-label"),
  });

  const renderProgress = ({ percent, stageText, labelText }) => {
    const elements = getProgressElements();
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
    if (elements.label && labelText) {
      elements.label.textContent = labelText;
    }
    if (elements.overlayLabel && labelText) {
      elements.overlayLabel.textContent = labelText;
    }
    if (elements.track) {
      elements.track.setAttribute("aria-valuenow", String(safePercent));
      elements.track.setAttribute("aria-valuetext", `${safePercent}%`);
    }
  };

  const stopProgressTimer = () => {
    if (!progressState.timerId) return;
    window.clearInterval(progressState.timerId);
    progressState.timerId = null;
  };

  const startProgress = ({
    label = "Выполняется операция...",
    stages = PREVIEW_PROGRESS_STAGES,
    simulated = true,
  } = {}) => {
    const elements = getProgressElements();
    if (!elements.container) return;

    stopProgressTimer();
    progressState.percent = 4;
    progressState.stageIndex = 0;
    progressState.stages = Array.isArray(stages) && stages.length ? stages : PREVIEW_PROGRESS_STAGES;

    elements.container.hidden = false;
    if (elements.overlay) {
      elements.overlay.hidden = false;
    }

    renderProgress({
      percent: progressState.percent,
      stageText: progressState.stages[0],
      labelText: label,
    });

    if (!simulated) return;

    progressState.timerId = window.setInterval(() => {
      const delta = Math.floor(Math.random() * 4) + 2;
      progressState.percent = Math.min(92, progressState.percent + delta);

      const stageCount = progressState.stages.length;
      if (stageCount > 1) {
        const threshold = 92 / (stageCount - 1);
        progressState.stageIndex = Math.min(
          stageCount - 1,
          Math.floor(progressState.percent / threshold),
        );
      }

      renderProgress({
        percent: progressState.percent,
        stageText: progressState.stages[progressState.stageIndex],
        labelText: label,
      });
    }, 480);
  };

  const finishProgress = ({ success = true, stageText = "Готово", labelText = null } = {}) => {
    const elements = getProgressElements();
    if (!elements.container) return;

    stopProgressTimer();
    renderProgress({
      percent: 100,
      stageText,
      labelText: labelText || (success ? "Операция завершена" : "Операция завершена с ошибкой"),
    });

    window.setTimeout(() => {
      elements.container.hidden = true;
      if (elements.overlay) {
        elements.overlay.hidden = true;
      }
    }, success ? 1200 : 2000);
  };

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

  const formatGamesSubtitle = (item) => {
    const gameTitles = Array.isArray(item?.game_titles) ? item.game_titles.filter(Boolean) : [];
    const gameCount = Number(item?.game_count || gameTitles.length || 0);
    if (gameCount > 0 && gameTitles.length) {
      const noun = gameCount === 1 ? "игра" : (gameCount < 5 ? "игры" : "игр");
      const previewTitles = gameTitles.slice(0, 4).join(", ");
      const suffix = gameTitles.length > 4 ? "…" : "";
      return `${gameCount} ${noun}: ${previewTitles}${suffix}`;
    }
    return String(item?.subtitle || "").trim();
  };

  const normalizeItem = (item) => {
    const key = String(item?.key || "").trim().toLowerCase();
    const title = String(item?.title || key || "Провайдер").trim();
    const subtitle = formatGamesSubtitle(item);
    const gameTitles = Array.isArray(item?.game_titles) ? item.game_titles.map((value) => String(value || "").trim()).filter(Boolean) : [];
    const gameCount = Number(item?.game_count || gameTitles.length || 0);
    const domainCount = Number(item?.domain_count || 0);
    const asnCount = Number(item?.asn_count || 0);
    const serverIpCount = Number(item?.server_ip_count || 0);
    const provider = normalizeProviderName(item?.provider || title) || title;
    const sourceTypeRaw = String(item?.source_type || "").trim().toLowerCase();
    const sourceType = sourceTypeRaw === "servers" || sourceTypeRaw === "asn" || sourceTypeRaw === "mixed"
      ? sourceTypeRaw
      : (serverIpCount > 0 ? "servers" : (asnCount > 0 ? "asn" : "dns"));
    const tags = Array.isArray(item?.tags)
      ? item.tags.map((tag) => String(tag || "").trim()).filter(Boolean)
      : [];
    return {
      key,
      title,
      subtitle,
      game_titles: gameTitles,
      game_count: Number.isFinite(gameCount) ? gameCount : 0,
      domain_count: Number.isFinite(domainCount) ? domainCount : 0,
      asn_count: Number.isFinite(asnCount) ? asnCount : 0,
      server_ip_count: Number.isFinite(serverIpCount) ? serverIpCount : 0,
      provider,
      source_type: sourceType,
      network: String(item?.network || inferNetworkFromSubtitle(subtitle) || "").trim(),
      tags,
    };
  };

  const inferNetworkFromSubtitle = (subtitle) => {
    const parts = String(subtitle || "").trim().split("—");
    if (parts.length < 2) return "";
    const network = parts.slice(1).join("—").trim();
    if (!network || network.toUpperCase() === "DNS") return "";
    return network;
  };

  const getModeLabel = (mode) => {
    if (mode === "include") return "VPN";
    if (mode === "exclude") return "DIRECT";
    return "Не назначено";
  };

  const getNetworkLabel = (item) => {
    if (item.network) return item.network;
    if (item.source_type === "servers") return "Игровые IP";
    if (item.source_type === "asn") return "RIPE";
    return "По доменам";
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
      routes_count: Number(item.routes_count ?? item.cidr_count ?? 0),
      covered_count: Number(item.covered_count || 0),
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

  const cardMatchesFilters = (card, query, onlySelected) => {
    const title = String(card.querySelector(".cidr-game-chip__title")?.textContent || "").trim().toLowerCase();
    const subtitle = String(card.querySelector(".cidr-game-chip__sub")?.textContent || card.dataset.subtitle || "").trim().toLowerCase();
    const value = String(card.dataset.providerKey || card.dataset.gameKey || "").trim().toLowerCase();
    const mode = getModeByKey(value);
    if (query && !title.includes(query) && !subtitle.includes(query) && !value.includes(query)) return false;
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

  const renderConfigRouteBudget = (stats = {}) => {
    const countEl = byId("cidr-games-config-routes-count");
    const limitEl = byId("cidr-games-config-routes-limit");
    const wrapEl = byId("cidr-games-config-routes-stat");
    const limit = Number(stats.limit || 900);
    const limitEnforced = stats.limit_enforced !== false;
    const total = Number(
      stats.total_routes_planned ?? stats.total_routes ?? stats.planned_total ?? 0
    );
    if (limitEl) limitEl.textContent = limitEnforced ? String(limit) : "∞";
    if (countEl) countEl.textContent = String(total);
    if (wrapEl) {
      wrapEl.classList.toggle("is-limit-disabled", !limitEnforced);
      wrapEl.classList.toggle("is-over-limit", limitEnforced && total > limit);
      wrapEl.classList.toggle("is-near-limit", limitEnforced && total <= limit && total > limit * 0.85);
    }
  };

  const renderRouteLimitSettings = (settings = {}, stats = {}) => {
    if (window.AntiZapretRouteLimitOverride?.render) {
      window.AntiZapretRouteLimitOverride.render(settings, stats);
      return;
    }
    renderConfigRouteBudget(stats);
  };

  const saveRouteLimitSettings = async (options = {}) => {
    if (window.AntiZapretRouteLimitOverride?.save) {
      return window.AntiZapretRouteLimitOverride.save(options);
    }
    throw new Error("Не удалось сохранить настройки лимита маршрутов");
  };

  const notifySelectionChanged = () => {
    if (typeof state.onSelectionChanged === "function") {
      const includeProviderKeys = getIncludeKeys();
      const excludeProviderKeys = getExcludeKeys();
      state.onSelectionChanged({
        includeProviderKeys,
        excludeProviderKeys,
        includeGameKeys: includeProviderKeys,
        excludeGameKeys: excludeProviderKeys,
      });
    }
  };

  const sortProviderItems = (items) => [...items].sort((left, right) =>
    String(left.title || left.key || "").localeCompare(String(right.title || right.key || ""), "ru")
  );

  const renderCards = () => {
    const container = byId("cidr-game-filters");
    if (!container) return;
    if (!state.items.length) {
      container.innerHTML = '<p class="no-data">Игровые фильтры недоступны</p>';
      updateTopStats(0);
      return;
    }

    container.innerHTML = sortProviderItems(state.items)
      .map((item) => {
        const mode = getModeByKey(item.key);
        const subtitleHtml = item.subtitle
          ? `<span class="cidr-game-chip__sub">${item.subtitle}</span>`
          : "";
        const gameStats = getPerGameStat(item.key);
        const modeBadgeClass = mode === "include" ? "is-include" : (mode === "exclude" ? "is-exclude" : "is-none");
        const statsGridHtml = `
          <div class="cidr-game-chip__stats-grid">
            <div class="cidr-game-chip__stat">
              <span>К добавлению</span>
              <strong class="${gameStats.loading ? "metric-loading" : ""}">${toCompactCount(gameStats.routes_count ?? gameStats.cidr_count, gameStats.loading)}</strong>
            </div>
            <div class="cidr-game-chip__stat">
              <span>${gameStats.covered_count > 0 ? "Через VPN" : "Пересечения"}</span>
              <strong class="${gameStats.loading ? "metric-loading" : ""}">${toCompactCount(gameStats.covered_count > 0 ? gameStats.covered_count : gameStats.overlap_count, gameStats.loading)}</strong>
            </div>
            <div class="cidr-game-chip__stat">
              <span>Домены</span>
              <strong>${item.domain_count}</strong>
            </div>
          </div>
        `;
        return `
          <label class="cidr-scope-chip cidr-game-chip"
            data-provider-key="${item.key}"
            data-game-key="${item.key}"
            data-subtitle="${item.subtitle}">
            <input type="hidden" class="cidr-game-mode-input" value="${mode}" data-provider-key="${item.key}" data-game-key="${item.key}" />
            <div class="cidr-game-chip__body">
              <div class="cidr-game-chip__head">
                <span class="cidr-game-chip__title">${item.title}</span>
                <span class="cidr-game-chip__mode-badge ${modeBadgeClass}">${getModeLabel(mode)}</span>
              </div>
              ${subtitleHtml}
              <div class="cidr-game-chip__facts">
                <span class="cidr-game-chip__fact">
                  <span>Сеть</span>
                  <strong>${getNetworkLabel(item)}</strong>
                </span>
                <span class="cidr-game-chip__fact">
                  <span>Игр</span>
                  <strong>${item.game_count || 0}</strong>
                </span>
              </div>
              ${statsGridHtml}
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
    const onlySelected = Boolean(byId("cidr-games-only-selected")?.checked);
    const chips = Array.from(document.querySelectorAll("#cidr-game-filters .cidr-game-chip"));
    let visibleCount = 0;
    chips.forEach((chip) => {
      const matches = cardMatchesFilters(chip, query, onlySelected);
      chip.hidden = !matches;
      chip.classList.toggle("is-filter-hidden", !matches);
      if (matches) visibleCount += 1;
    });
    updateTopStats(visibleCount);
    return visibleCount;
  };

  const setBusy = (isBusy, progressOptions = null) => {
    state.isBusy = Boolean(isBusy);
    const shell = document.querySelector("#game-filters .game-filters-shell");
    if (shell) {
      shell.classList.toggle("game-filters-shell--busy", state.isBusy);
    }

    document.querySelectorAll("[data-game-filter-control]").forEach((node) => {
      node.disabled = state.isBusy;
      node.classList.remove("is-busy");
    });
    document.querySelectorAll("#cidr-game-filters .cidr-game-mode-btn").forEach((node) => {
      node.disabled = state.isBusy;
    });

    if (state.isBusy) {
      const triggerId = String(progressOptions?.triggerId || "").trim();
      if (triggerId) {
        const trigger = byId(triggerId);
        trigger?.classList.add("is-busy");
      }
      if (progressOptions) {
        startProgress(progressOptions);
      }
      return;
    }

    stopProgressTimer();
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

  const mergeChangeLogs = (includeLog, excludeLog) => {
    if (includeLog && excludeLog) {
      return {
        filter_kind: "mixed",
        sections: [includeLog, excludeLog],
        lines: [...(includeLog.lines || []), "", ...(excludeLog.lines || [])],
      };
    }
    return includeLog || excludeLog || null;
  };

  const mergeOverlapSummaries = (includeSummary = {}, excludeSummary = {}) => ({
    overlap_count: Number(includeSummary.overlap_count || 0) + Number(excludeSummary.overlap_count || 0),
    overlap_game_keys_count: Number(includeSummary.overlap_game_keys_count || 0) + Number(excludeSummary.overlap_game_keys_count || 0),
    fully_covered_count: Number(includeSummary.fully_covered_count || 0) + Number(excludeSummary.fully_covered_count || 0),
    partial_trimmed_count: Number(includeSummary.partial_trimmed_count || 0) + Number(excludeSummary.partial_trimmed_count || 0),
    routes_written_count: Number(includeSummary.routes_written_count || 0) + Number(excludeSummary.routes_written_count || 0),
    original_cidr_count: Number(includeSummary.original_cidr_count || 0) + Number(excludeSummary.original_cidr_count || 0),
    include_patches_count: Number(includeSummary.include_patches_count || 0) + Number(excludeSummary.include_patches_count || 0),
    include_patches_skipped_count: Number(includeSummary.include_patches_skipped_count || 0) + Number(excludeSummary.include_patches_skipped_count || 0),
    overlap_examples: [
      ...(Array.isArray(includeSummary.overlap_examples) ? includeSummary.overlap_examples : []),
      ...(Array.isArray(excludeSummary.overlap_examples) ? excludeSummary.overlap_examples : []),
    ],
    trim_details: [
      ...(Array.isArray(includeSummary.trim_details) ? includeSummary.trim_details : []),
      ...(Array.isArray(excludeSummary.trim_details) ? excludeSummary.trim_details : []),
    ],
    include_patches: [
      ...(Array.isArray(includeSummary.include_patches) ? includeSummary.include_patches : []),
      ...(Array.isArray(excludeSummary.include_patches) ? excludeSummary.include_patches : []),
    ],
    include_patches_skip_reasons: [
      ...(Array.isArray(includeSummary.include_patches_skip_reasons) ? includeSummary.include_patches_skip_reasons : []),
      ...(Array.isArray(excludeSummary.include_patches_skip_reasons) ? excludeSummary.include_patches_skip_reasons : []),
    ],
    include_patches_skip_summary: [
      ...(Array.isArray(includeSummary.include_patches_skip_summary) ? includeSummary.include_patches_skip_summary : []),
      ...(Array.isArray(excludeSummary.include_patches_skip_summary) ? excludeSummary.include_patches_skip_summary : []),
    ],
    punch_warnings: [
      ...(Array.isArray(includeSummary.punch_warnings) ? includeSummary.punch_warnings : []),
      ...(Array.isArray(excludeSummary.punch_warnings) ? excludeSummary.punch_warnings : []),
    ],
    punch_limitations: [
      ...(Array.isArray(includeSummary.punch_limitations) ? includeSummary.punch_limitations : []),
      ...(Array.isArray(excludeSummary.punch_limitations) ? excludeSummary.punch_limitations : []),
    ],
  });

  const mergeGamePreviewPayloads = (includePayload, excludePayload) => {
    const includePreview = includePayload?.preview || {};
    const excludePreview = excludePayload?.preview || {};
    const includeCount = Number(includePreview.selected_provider_count || includePreview.selected_game_count || 0);
    const excludeCount = Number(excludePreview.selected_provider_count || excludePreview.selected_game_count || 0);
    if (includeCount > 0 && excludeCount > 0) {
      return {
        success: Boolean(includePayload?.success || excludePayload?.success),
        message: [includePayload?.message, excludePayload?.message].filter(Boolean).join(" · "),
        preview: {
          selected_provider_count: includeCount + excludeCount,
          selected_game_count: includeCount + excludeCount,
          domain_count: Number(includePreview.domain_count || 0) + Number(excludePreview.domain_count || 0),
          cidr_count: Number(includePreview.cidr_count || 0) + Number(excludePreview.cidr_count || 0),
          original_cidr_count: Number(includePreview.original_cidr_count || 0) + Number(excludePreview.original_cidr_count || 0),
          unresolved_domain_count: Number(includePreview.unresolved_domain_count || 0) + Number(excludePreview.unresolved_domain_count || 0),
          include_game_domains: Boolean(includePreview.include_game_domains || excludePreview.include_game_domains),
          domains_to_add: [
            ...(Array.isArray(includePreview.domains_to_add) ? includePreview.domains_to_add : []),
            ...(Array.isArray(excludePreview.domains_to_add) ? excludePreview.domains_to_add : []),
          ],
          overlap_summary: mergeOverlapSummaries(
            includePreview.overlap_summary || {},
            excludePreview.overlap_summary || {},
          ),
          change_log: mergeChangeLogs(includePreview.change_log, excludePreview.change_log),
          punch_warnings: [
            ...(Array.isArray(includePreview.punch_warnings) ? includePreview.punch_warnings : []),
            ...(Array.isArray(excludePreview.punch_warnings) ? excludePreview.punch_warnings : []),
          ],
          per_game_stats: {
            ...(includePreview.per_game_stats && typeof includePreview.per_game_stats === "object" ? includePreview.per_game_stats : {}),
            ...(excludePreview.per_game_stats && typeof excludePreview.per_game_stats === "object" ? excludePreview.per_game_stats : {}),
          },
          host_block_preview: [
            ...(Array.isArray(includePreview.host_block_preview) ? includePreview.host_block_preview : []),
            ...(Array.isArray(excludePreview.host_block_preview) ? excludePreview.host_block_preview : []),
          ].slice(0, 20),
          ips_block_preview: [
            ...(Array.isArray(includePreview.ips_block_preview) ? includePreview.ips_block_preview : []),
            ...(Array.isArray(excludePreview.ips_block_preview) ? excludePreview.ips_block_preview : []),
          ].slice(0, 20),
          warning: [includePreview.warning, excludePreview.warning, includePayload?.message, excludePayload?.message]
            .filter(Boolean)
            .join(" · "),
        },
      };
    }
    if (excludeCount > 0 && excludePayload) return excludePayload;
    if (includeCount > 0 && includePayload) return includePayload;
    if (excludePayload?.preview) return excludePayload;
    return includePayload || excludePayload || {};
  };

  const renderPreview = (payload) => {
    const panel = byId("cidr-games-preview-panel");
    if (!panel) return;
    const preview = payload?.preview || payload || {};
    const selectedCount = Number(
      preview.selected_provider_count || preview.selected_game_count || preview.selected_count || 0
    );
    const domainCount = Number(preview.domain_count || 0);
    const cidrCount = Number(preview.cidr_count || 0);
    const unresolvedCount = Number(preview.unresolved_domain_count || 0);
    const warningMessage = String(preview.warning || preview.message || "").trim();
    const overlapSummary = preview?.overlap_summary || {};
    const includePatchesCount = Number(overlapSummary.include_patches_count || 0);
    const includePatches = Array.isArray(overlapSummary.include_patches) ? overlapSummary.include_patches : [];
    const includePatchesSkipped = Number(overlapSummary.include_patches_skipped_count || 0);
    const includePatchSkipReasons = Array.isArray(overlapSummary.include_patches_skip_summary)
      ? overlapSummary.include_patches_skip_summary
      : (Array.isArray(overlapSummary.include_patches_skip_reasons)
        ? overlapSummary.include_patches_skip_reasons
        : []);
    const punchWarnings = Array.isArray(preview?.punch_warnings) && preview.punch_warnings.length
      ? preview.punch_warnings
      : (Array.isArray(overlapSummary.punch_warnings) ? overlapSummary.punch_warnings : []);
    const overlapExamples = Array.isArray(overlapSummary.overlap_examples) ? overlapSummary.overlap_examples : [];
    const overlapCount = Number(overlapSummary.overlap_count || 0);
    const overlapGames = Number(overlapSummary.overlap_game_keys_count || 0);
    const fullyCovered = Number(overlapSummary.fully_covered_count || 0);
    const partialTrimmed = Number(overlapSummary.partial_trimmed_count || 0);
    const routesWritten = Number(preview.cidr_count ?? overlapSummary.routes_written_count ?? 0);
    const originalCidrCount = Number(preview.original_cidr_count ?? overlapSummary.original_cidr_count ?? routesWritten);
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
    const punchWarningsWrapEl = byId("cidr-games-preview-punch-warnings-wrap");
    const punchWarningsEl = byId("cidr-games-preview-punch-warnings");
    const overlapGamesEl = byId("cidr-games-preview-overlap-games");
    const vpnCoveredEl = byId("cidr-games-preview-vpn-covered");
    const partialTrimmedEl = byId("cidr-games-preview-partial-trimmed");
    const domainsEnabledEl = byId("cidr-games-preview-domains-enabled");
    const overlapWrapEl = byId("cidr-games-preview-overlap-wrap");
    const overlapListEl = byId("cidr-games-preview-overlap-list");
    const changeLogWrapEl = byId("cidr-games-preview-changelog-wrap");
    const changeLogEl = byId("cidr-games-preview-changelog");
    const includeSplitEl = byId("cidr-games-preview-include-split");
    const domainsWrapEl = byId("cidr-games-preview-domains-wrap");
    const domainsListEl = byId("cidr-games-preview-domains-list");

    if (selectedEl) selectedEl.textContent = String(selectedCount);
    if (domainsEl) domainsEl.textContent = String(domainCount);
    if (cidrsEl) cidrsEl.textContent = String(routesWritten);
    if (unresolvedEl) unresolvedEl.textContent = String(unresolvedCount);
    if (updatedEl) updatedEl.textContent = `Обновлено: ${new Date().toLocaleString()}`;
    if (vpnCoveredEl) vpnCoveredEl.textContent = String(fullyCovered);
    if (partialTrimmedEl) partialTrimmedEl.textContent = String(partialTrimmed);
    if (overlapGamesEl) overlapGamesEl.textContent = String(overlapGames);
    if (includeSplitEl) includeSplitEl.textContent = String(includePatchesCount);
    if (domainsEnabledEl) domainsEnabledEl.textContent = includeDomains ? "да" : "нет";
    if (warningsEl) {
      const overlapParts = [];
      if (fullyCovered > 0) overlapParts.push(`уже через VPN: ${fullyCovered}`);
      if (partialTrimmed > 0) overlapParts.push(`частично обрезано: ${partialTrimmed}`);
      if (includePatchesCount > 0) overlapParts.push(`include будет разбито: ${includePatchesCount}`);
      if (includePatchesSkipped > 0) {
        const broadSkipped = includePatchSkipReasons.filter(
          (item) => String(item?.reason || "") === "include_route_too_broad",
        ).length;
        if (broadSkipped > 0) {
          overlapParts.push(`punch пропущен (широкие include /16): ${broadSkipped}`);
        } else {
          overlapParts.push(`punch пропущен: ${includePatchesSkipped}`);
        }
      }
      if (overlapCount > 0 && !fullyCovered && !partialTrimmed && !includePatchesCount && !includePatchesSkipped) {
        overlapParts.push(`пересечений: ${overlapCount}`);
      }
      const routeBudget = overlapSummary.route_budget || preview.route_budget || {};
      if (routeBudget.compression_applied) {
        overlapParts.push(
          `сжато под лимит config: ${Number(routeBudget.game_routes_before || 0)} → ${Number(routeBudget.game_routes_planned || 0)} игровых маршрутов`
        );
      }
      if (Number(routeBudget.over_limit || 0) > 0) {
        overlapParts.push(`превышение лимита config include-ips: ${Number(routeBudget.over_limit || 0)}`);
      }
      const overlapText = overlapParts.length ? `${overlapParts.join(", ")}. ` : "";
      const originalSuffix = originalCidrCount > routesWritten
        ? `Будет добавлено ${routesWritten} маршрутов из ${originalCidrCount} исходных. `
        : "";
      warningsEl.textContent = `${originalSuffix}${overlapText}${warningMessage}`.trim();
    }

    if (punchWarningsWrapEl && punchWarningsEl) {
      if (punchWarnings.length) {
        punchWarningsWrapEl.hidden = false;
        punchWarningsEl.textContent = punchWarnings.join("\n\n");
      } else {
        punchWarningsWrapEl.hidden = true;
        punchWarningsEl.textContent = "";
      }
    }

    if (overlapWrapEl && overlapListEl) {
      if (preview?.change_log?.lines?.length) {
        overlapWrapEl.hidden = true;
        overlapListEl.innerHTML = "";
      } else {
      const patchItems = includePatches.map((patch) => {
        const file = String(patch?.file || "—").split(/[/\\]/).pop() || String(patch?.file || "—");
        const oldCidr = String(patch?.old_cidr || "—");
        const newCidrs = Array.isArray(patch?.new_cidrs) ? patch.new_cidrs : [];
        const target = newCidrs.length ? newCidrs.join(", ") : "(удалено)";
        return `<li><code>${file}</code>: <code>${oldCidr}</code> → <code>${target}</code></li>`;
      });
      const skipItems = includePatchSkipReasons.slice(0, 10).map((item) => {
        const file = String(item?.file || "—").split(/[/\\]/).pop() || String(item?.file || "—");
        const oldCidr = String(item?.old_cidr || "—");
        const reason = String(item?.reason || "skipped");
        return `<li><code>${file}</code>: <code>${oldCidr}</code> — punch пропущен (${reason})</li>`;
      });
      const exampleItems = overlapExamples
        .slice(0, 30)
        .map((item) => {
          const gameCidr = String(item?.game_cidr || "—");
          const existingCidr = String(item?.existing_cidr || "—");
          const file = String(item?.file || "—").split(/[/\\]/).pop() || String(item?.file || "—");
          const type = String(item?.type || "").trim().toLowerCase();
          const comment = String(item?.comment || "").trim();
          const isExclude = comment.includes("include");
          const typeLabel = type === "full"
            ? (isExclude ? "полностью в include" : "полностью через VPN")
            : (type === "partial" ? (isExclude ? "частично в include" : "частично обрезано") : "пересечение");
          if (comment) {
            return `<li>${comment.replace(/^#\s*/, "")}</li>`;
          }
          return `<li><code>${gameCidr}</code> — ${typeLabel} с <code>${existingCidr}</code> в <code>${file}</code></li>`;
        });
      const overlapItems = [...exampleItems, ...patchItems, ...skipItems];
      if (overlapItems.length) {
        overlapWrapEl.hidden = false;
        overlapListEl.innerHTML = overlapItems.join("");
      } else {
        overlapWrapEl.hidden = true;
        overlapListEl.innerHTML = "";
      }
      }
    }

    if (changeLogWrapEl && changeLogEl) {
      const changeLogLines = Array.isArray(preview?.change_log?.lines) ? preview.change_log.lines : [];
      if (changeLogLines.length) {
        changeLogWrapEl.hidden = false;
        changeLogEl.textContent = changeLogLines.join("\n");
      } else {
        changeLogWrapEl.hidden = true;
        changeLogEl.textContent = "";
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
    if (overlapSummary.route_budget || preview.route_budget) {
      renderConfigRouteBudget(overlapSummary.route_budget || preview.route_budget);
    }

    panel.classList.remove("is-success", "is-warning");
    if (
      unresolvedCount > 0
      || overlapCount > 0
      || fullyCovered > 0
      || partialTrimmed > 0
      || includePatchesCount > 0
      || includePatchesSkipped > 0
      || punchWarnings.length > 0
    ) {
      panel.classList.add("is-warning");
    } else {
      panel.classList.add("is-success");
    }
    panel.hidden = false;
  };

  const setupInteractionHandlers = (callbacks) => {
    byId("cidr-games-search-input")?.addEventListener("input", applyFilters);
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
      const key = String(card?.dataset?.providerKey || card?.dataset?.gameKey || "").trim().toLowerCase();
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
      let success = false;
      try {
        setBusy(true, {
          label: "Проверка перед применением...",
          triggerId: "cidr-games-preview-sync",
          stages: PREVIEW_PROGRESS_STAGES,
        });
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
        renderPreview(mergeGamePreviewPayloads(result?.includePreview, result?.excludePreview));
        success = true;
      } catch (error) {
        if (typeof callbacks.onError === "function") {
          callbacks.onError(error);
        }
      } finally {
        finishProgress({
          success,
          stageText: success ? "Проверка завершена" : "Ошибка проверки",
        });
        setBusy(false);
      }
    });

    byId("cidr-sync-games-apply")?.addEventListener("click", async () => {
      if (typeof callbacks.onApplyRoutes !== "function") return;
      let success = false;
      try {
        setBusy(true, {
          label: "Применение игровых маршрутов...",
          triggerId: "cidr-sync-games-apply",
          stages: APPLY_PROGRESS_STAGES,
        });
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
        if (result?.includePreview || result?.excludePreview) {
          renderPreview(mergeGamePreviewPayloads(result?.includePreview, result?.excludePreview));
        } else if (previewPayload) {
          renderPreview(previewPayload);
        }
        success = true;
      } catch (error) {
        if (typeof callbacks.onError === "function") {
          callbacks.onError(error);
        }
      } finally {
        finishProgress({
          success,
          stageText: success ? "Игровые маршруты применены" : "Ошибка применения",
        });
        setBusy(false);
      }
    });
  };

  const runProgressiveCardEstimates = async () => {
    const batchEstimate = state.onBatchEstimate || state.onEstimateGame;
    if (typeof batchEstimate !== "function" || !state.items.length) return;
    const runId = ++state.estimateRunId;
    const queue = state.items.map((item) => item.key).filter(Boolean);
    const pendingKeys = queue.filter((key) => !state.perGameStats[key]);
    if (!pendingKeys.length) return;
    try {
      const previewPayload = typeof state.onBatchEstimate === "function"
        ? await state.onBatchEstimate(pendingKeys)
        : await state.onEstimateGame(pendingKeys[0]);
      if (runId !== state.estimateRunId) return;
      const preview = previewPayload?.preview || previewPayload || {};
      const perGameStats = (preview.per_game_stats && typeof preview.per_game_stats === "object")
        ? preview.per_game_stats
        : {};
      pendingKeys.forEach((key) => {
        const normalizedKey = String(key || "").trim().toLowerCase();
        const perGame = perGameStats[normalizedKey] || {};
        const cidrCount = Number(perGame.cidr_count || 0);
        const overlapCount = Number(perGame.overlap_count || 0);
        state.perGameStats[normalizedKey] = {
          cidr_count: Number.isFinite(cidrCount) ? cidrCount : 0,
          routes_count: Number.isFinite(Number(perGame.routes_count)) ? Number(perGame.routes_count) : cidrCount,
          covered_count: Number.isFinite(Number(perGame.covered_count)) ? Number(perGame.covered_count) : 0,
          overlap_count: Number.isFinite(overlapCount) ? overlapCount : 0,
        };
      });
      persistCachedStats();
      renderCards();
      applyFilters();
    } catch (_error) {
      // silent: keep card at zero if preload estimate fails
    }
  };

  const hydrateModesFromDom = () => {
    const next = {};
    document.querySelectorAll("#cidr-game-filters .cidr-game-mode-input").forEach((input) => {
      const key = String(input.getAttribute("data-provider-key") || input.getAttribute("data-game-key") || "").trim().toLowerCase();
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
    state.onBatchEstimate =
      typeof callbacks.onBatchEstimate === "function" ? callbacks.onBatchEstimate : null;
    hydrateModesFromDom();
    setupInteractionHandlers({
      onPreview: callbacks.onPreview,
      onApplyRoutes: callbacks.onApplyRoutes,
      onError: callbacks.onError,
    });
    const hasDomCatalog = Boolean(document.querySelector("#cidr-game-filters .cidr-game-chip"));
    if (state.items.length) {
      setFilters(state.items);
    } else if (hasDomCatalog) {
      applyFilters();
    }
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
      renderConfigRouteBudget,
      renderRouteLimitSettings,
      saveRouteLimitSettings,
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
    renderConfigRouteBudget,
  };
})();
