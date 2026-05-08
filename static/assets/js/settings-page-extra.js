// RBAC: управление доступом viewer к конфигам
document.querySelectorAll('.viewer-access-cb').forEach(function (cb) {
  cb.addEventListener('change', function () {
    const userId = parseInt(this.dataset.userId);
    const configName = this.dataset.configName;
    const configLabel = this.dataset.configLabel || configName;
    const configType = this.dataset.configType;
    const action = this.checked ? 'grant' : 'revoke';
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    fetch('/api/viewer-access', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({
        user_id: userId,
        config_name: configName,
        config_type: configType,
        action: action
      })
    })
      .then(r => r.json())
      .then(data => {
        const statusEl = document.getElementById('viewer-access-status');
        if (data.success) {
          statusEl.textContent = (action === 'grant' ? '✅ Доступ выдан: ' : '🚫 Доступ отозван: ') + configLabel;
          statusEl.className = 'notification notification-success viewer-access-notice';
        } else {
          statusEl.textContent = '❌ Ошибка: ' + (data.message || 'unknown');
          statusEl.className = 'notification notification-error viewer-access-notice';
          this.checked = !this.checked; // откат
        }
        statusEl.style.display = 'block';
        setTimeout(() => {
          statusEl.classList.add('notification-exit');
          setTimeout(() => {
            statusEl.classList.remove('notification-exit');
            statusEl.style.display = 'none';
          }, 180);
        }, 3000);
      })
      .catch(() => {
        this.checked = !this.checked; // откат при сетевой ошибке
      });
  });
});

const openViewerProfileModal = (modal) => {
  if (!modal) return;
  modal.removeAttribute('hidden');
  requestAnimationFrame(() => {
    modal.classList.add('is-open');
  });
  document.body.classList.add('viewer-profile-modal-open');
};

const closeViewerProfileModal = (modal) => {
  if (!modal) return;
  modal.classList.remove('is-open');
  setTimeout(() => {
    modal.setAttribute('hidden', '');
  }, 180);
  if (!document.querySelector('.viewer-profile-modal.is-open')) {
    document.body.classList.remove('viewer-profile-modal-open');
  }
};

document.querySelectorAll('[data-viewer-modal-open]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const modalId = btn.getAttribute('data-viewer-modal-open');
    const modal = document.getElementById(modalId);
    openViewerProfileModal(modal);
  });
});

document.querySelectorAll('.viewer-profile-modal').forEach((modal) => {
  modal.querySelectorAll('[data-viewer-modal-close]').forEach((closer) => {
    closer.addEventListener('click', () => closeViewerProfileModal(modal));
  });
});

const initViewerConfigPanels = () => {
  document.querySelectorAll('[data-config-group]').forEach((group) => {
    const list = group.querySelector('[data-config-list]');
    if (!list) return;

    const items = Array.from(list.querySelectorAll('.viewer-config-item-compact'));
    const searchInput = group.querySelector('[data-config-filter]');
    const onlyGrantedInput = group.querySelector('[data-config-only-granted]');

    const applyFilter = () => {
      const query = (searchInput?.value || '').trim().toLowerCase();
      const onlyGranted = Boolean(onlyGrantedInput?.checked);

      items.forEach((item) => {
        const checkbox = item.querySelector('input[type="checkbox"]');
        const itemText = item.textContent.toLowerCase();
        const matchesQuery = !query || itemText.includes(query);
        const matchesGranted = !onlyGranted || Boolean(checkbox?.checked);
        const shouldShow = matchesQuery && matchesGranted;

        item.classList.toggle('is-hidden', !shouldShow);
      });
    };

    searchInput?.addEventListener('input', applyFilter);
    onlyGrantedInput?.addEventListener('change', applyFilter);
    list.querySelectorAll('.viewer-access-cb').forEach((cb) => {
      cb.addEventListener('change', applyFilter);
    });

    applyFilter();
  });
};

initViewerConfigPanels();

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  const openedModal = document.querySelector('.viewer-profile-modal.is-open');
  if (openedModal) {
    closeViewerProfileModal(openedModal);
  }
});

// ── CIDR DB + Presets ─────────────────────────────────────────────────
(function () {
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || document.querySelector('input[name="csrf_token"]')?.value || "";

  // ── DB Status ──────────────────────────────────────────────────────
  const dbBadge = document.getElementById("cidr-db-badge");
  const dbTotal = document.getElementById("cidr-db-total");
  const dbTs = document.getElementById("cidr-db-ts");
  const dbTbody = document.getElementById("cidr-db-providers-tbody");
  const dbSearch = document.getElementById("cidr-db-search");
  const dbFilterStatus = document.getElementById("cidr-db-filter-status");
  const dbFilterCategory = document.getElementById("cidr-db-filter-category");
  const dbSort = document.getElementById("cidr-db-sort");
  const dbVisibleCount = document.getElementById("cidr-db-visible-count");
  const dbHistoryList = document.getElementById("cidr-db-history-list");
  const dbMsg = document.getElementById("cidr-db-status-msg");
  const dbAlerts = document.getElementById("cidr-db-alerts");
  const dbTableState = { providers: [] };

  const catLabel = { cdn: "CDN", cloud: "Облако", hosting: "Хостинг" };
  const statusLabel = { ok: "OK", partial: "Частично", error: "Ошибка", never: "Нет данных", running: "Обновляется" };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function timestampValue(iso) {
    if (!iso) return 0;
    const parsed = Date.parse(iso);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function getDbTableViewOptions() {
    return {
      search: String(dbSearch?.value || "").trim().toLowerCase(),
      status: String(dbFilterStatus?.value || "all").toLowerCase(),
      category: String(dbFilterCategory?.value || "all").toLowerCase(),
      sort: String(dbSort?.value || "cidr-desc"),
    };
  }

  function renderDbProvidersTable() {
    if (!dbTbody) return;

    const options = getDbTableViewOptions();
    const filtered = (dbTableState.providers || []).filter((row) => {
      if (options.status !== "all" && String(row.refresh_status || "never") !== options.status) {
        return false;
      }
      if (options.category !== "all" && String(row.category || "") !== options.category) {
        return false;
      }
      if (!options.search) return true;

      const haystack = [
        row.key,
        row.name,
        row.category,
        row.what_hosts,
        (row.as_numbers || []).join(" "),
        row.source_used,
      ].join(" ").toLowerCase();
      return haystack.includes(options.search);
    });

    filtered.sort((a, b) => {
      switch (options.sort) {
        case "cidr-asc":
          return Number(a.cidr_count || 0) - Number(b.cidr_count || 0);
        case "name-asc":
          return String(a.name || a.key || "").localeCompare(String(b.name || b.key || ""), "ru");
        case "updated-desc":
          return timestampValue(b.last_refreshed_at) - timestampValue(a.last_refreshed_at);
        case "cidr-desc":
        default:
          return Number(b.cidr_count || 0) - Number(a.cidr_count || 0);
      }
    });

    if (dbVisibleCount) {
      dbVisibleCount.textContent = `Показано: ${filtered.length}/${(dbTableState.providers || []).length}`;
    }

    if (!filtered.length) {
      dbTbody.innerHTML = '<tr><td colspan="7" class="help-text cidr-db-table__placeholder">Нет провайдеров по текущим фильтрам</td></tr>';
      return;
    }

    const rowsHtml = filtered.map((p) => {
      const asList = Array.isArray(p.as_numbers) ? p.as_numbers : [];
      const asVisible = asList.slice(0, 10);
      const asHtml = asVisible.map((a) => `<span class="cidr-db-as-badge">${escapeHtml(a)}</span>`).join("")
        + (asList.length > 10 ? `<span class="cidr-db-as-badge">+${asList.length - 10}</span>` : "");

      const cat = p.category || "";
      const catHtml = cat ? `<span class="cidr-db-cat cidr-db-cat--${escapeHtml(cat)}">${escapeHtml(catLabel[cat] || cat)}</span>` : "—";
      const st = String(p.refresh_status || "never");
      const stLbl = statusLabel[st] || st;
      const stCls = `cidr-db-status-pill cidr-db-status-pill--${st}`;
      const errTip = p.refresh_error ? ` title="${escapeHtml(p.refresh_error)}"` : "";

      const anomaly = p.anomaly_level && p.anomaly_level !== "none"
        ? `<div class="cidr-db-anomaly" title="${escapeHtml(p.anomaly_reason || "")}">⚠ ${escapeHtml(p.anomaly_level)}</div>`
        : "";
      const asnMeta = (p.active_asn_count || p.asn_count)
        ? `<div class="cidr-db-as-meta">ASN: ${Number(p.active_asn_count || 0)}/${Number(p.asn_count || 0)}</div>`
        : "";

      const providerName = escapeHtml(p.name || p.key || "—");
      const providerKey = escapeHtml(p.key || "");
      const sourceUsed = escapeHtml(p.source_used || "источник не указан");
      const whatHosts = escapeHtml(p.what_hosts || "—");
      const cidrCount = p.cidr_count ? Number(p.cidr_count).toLocaleString("ru-RU") : "—";
      const rowClass = p.anomaly_level && p.anomaly_level !== "none" ? "cidr-db-row--anomaly" : "";

      return `<tr class="${rowClass}">
              <td data-label="Провайдер">
                <div class="cidr-db-provider-cell">
                  <strong>${providerName}</strong>
                  <span class="cidr-db-provider-key">${providerKey}</span>
                  <span class="cidr-db-provider-source" title="${sourceUsed}">${sourceUsed}</span>
                </div>
              </td>
              <td data-label="AS"><div class="cidr-db-as">${asHtml || "—"}</div>${asnMeta}</td>
              <td data-label="Категория">${catHtml}</td>
              <td data-label="CIDR в БД" class="cidr-db-num">${cidrCount}</td>
              <td data-label="Обновлено">${fmtDt(p.last_refreshed_at)}</td>
              <td data-label="Статус"><span class="${stCls}"${errTip}>${escapeHtml(stLbl)}</span>${anomaly}</td>
              <td data-label="Что размещено"><span class="cidr-db-what" title="${whatHosts}">${whatHosts}</span></td>
            </tr>`;
    });

    dbTbody.innerHTML = rowsHtml.join("");
  }

  function setDbMsg(text, level) {
    if (!dbMsg) return;
    dbMsg.textContent = text;
    dbMsg.className = "notification " + (level === "error" ? "notification--error" : level === "success" ? "notification--success" : "notification--info");
    dbMsg.hidden = !text;
  }

  function fmtDt(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch { return iso; }
  }

  function renderDbStatus(data) {
    if (!dbBadge) return;
    const st = data.last_refresh_status || "never";
    const labels = { ok: "OK", partial: "Частично", error: "Ошибка", never: "Нет данных", running: "Обновляется" };
    dbBadge.textContent = labels[st] || st;
    dbBadge.className = "cidr-db-badge cidr-db-badge--" + st;
    if (dbTotal) dbTotal.textContent = data.total_cidrs ? `${data.total_cidrs.toLocaleString("ru-RU")} CIDR` : "";
    if (dbTs && data.last_refresh_finished) dbTs.textContent = "Обновлено: " + fmtDt(data.last_refresh_finished);

    if (dbAlerts) {
      const alerts = Array.isArray(data.alerts) ? data.alerts : [];
      if (!alerts.length) {
        dbAlerts.hidden = true;
      } else {
        const lines = alerts.slice(0, 8).map((alert) => {
          const provider = alert.provider_key ? `[${alert.provider_key}] ` : "";
          return `• ${provider}${alert.message || "Обнаружена деградация"}`;
        });
        dbAlerts.textContent = lines.join("\n");
        dbAlerts.className = "notification " + (alerts.some(a => a.level === "critical") ? "notification--error" : "notification--warning");
        dbAlerts.hidden = false;
      }
    }

    // Expose per-provider CIDR counts for the 900-limit counter
    window._cidrDbProviderCounts = {};
    Object.entries(data.providers || {}).forEach(([key, p]) => {
      if (p.cidr_count) window._cidrDbProviderCounts[key] = p.cidr_count;
    });
    if (typeof window._cidrRenderMeta === "function") window._cidrRenderMeta();

    dbTableState.providers = Object.entries(data.providers || {}).map(([key, provider]) => ({
      key,
      ...provider,
    }));
    renderDbProvidersTable();

    if (dbHistoryList) {
      const hist = data.history || [];
      dbHistoryList.innerHTML = hist.map(h => {
        const stLbl = h.status === "ok" ? "OK" : h.status === "partial" ? "Частично" : h.status === "error" ? "Ошибка" : h.status;
        const by = h.triggered_by || "";
        return `<li><strong>${fmtDt(h.started_at)}</strong> — ${stLbl} | обновлено: ${h.providers_updated}, ошибок: ${h.providers_failed}, CIDR: ${h.total_cidrs} ${by ? `[${by}]` : ""}</li>`;
      }).join("") || "<li>Нет истории</li>";
    }
  }

  async function loadDbStatus() {
    try {
      const r = await fetch("/api/cidr-db/status", { cache: "no-store" });
      const d = await r.json();
      if (d.success) renderDbStatus(d);
    } catch (e) {
      if (dbBadge) { dbBadge.textContent = "Ошибка"; dbBadge.className = "cidr-db-badge cidr-db-badge--error"; }
    }
  }

  async function triggerDbRefresh(selectedFiles) {
    const section = document.getElementById("cidr-update");
    if (section && section.classList.contains("cidr-busy")) return;

    setDbMsg("Запускаю обновление БД…", "info");
    try {
      if (typeof window._pollCidrTaskExternal === "function") {
        await window._pollCidrTaskExternal([
          {
            label: "Обновление CIDR БД",
            start: async () => {
              const r = await fetch("/api/cidr-db/refresh", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
                body: JSON.stringify({ selected_files: selectedFiles || null }),
              });
              const d = await r.json();
              if (!d.success) throw new Error(d.message || "Ошибка обновления CIDR БД");
              return d.task_id;
            },
          },
        ]);
        await loadDbStatus();
        setDbMsg("Обновление БД завершено. Детали прогресса показаны в панели операций.", "success");
        return;
      }

      const r = await fetch("/api/cidr-db/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ selected_files: selectedFiles || null }),
      });
      const d = await r.json();
      if (!d.success) throw new Error(d.message || "Ошибка");
      setDbMsg("Обновление запущено в фоне. Это займёт 1–3 минуты.", "success");

      const taskId = d.task_id;
      if (!taskId) return;
      const poll = setInterval(async () => {
        try {
          const tr = await fetch(`/api/cidr-lists/task/${encodeURIComponent(taskId)}`, { cache: "no-store" });
          const td = await tr.json();
          if (td.status === "running") {
            const pct = Number(td.progress_percent || 0);
            const stage = String(td.progress_stage || td.message || "Выполняется");
            setDbMsg(`Обновление БД: ${pct}% — ${stage}`, "info");
            return;
          }
          if (td.status === "completed" || td.status === "failed") {
            clearInterval(poll);
            await loadDbStatus();
            setDbMsg(td.status === "completed" ? "БД обновлена успешно." : "Обновление завершено с ошибками.", td.status === "completed" ? "success" : "error");
          }
        } catch {
          clearInterval(poll);
        }
      }, 1500);
    } catch (e) {
      setDbMsg("Ошибка: " + (e.message || e), "error");
    }
  }

  document.getElementById("cidr-db-refresh-all")?.addEventListener("click", () => triggerDbRefresh(null));
  document.getElementById("cidr-db-refresh-selected")?.addEventListener("click", () => {
    const checked = Array.from(document.querySelectorAll(".cidr-region-checkbox:checked")).map(el => el.value);
    triggerDbRefresh(checked.length ? checked : null);
  });
  document.getElementById("cidr-db-toggle-history")?.addEventListener("click", () => {
    const h = document.getElementById("cidr-db-history");
    if (h) h.hidden = !h.hidden;
  });

  [dbSearch, dbFilterStatus, dbFilterCategory, dbSort].forEach((control) => {
    if (!control) return;
    const eventName = control.tagName === "INPUT" ? "input" : "change";
    control.addEventListener(eventName, renderDbProvidersTable);
  });

  // ── Generate from DB ───────────────────────────────────────────────
  document.getElementById("cidr-generate-from-db")?.addEventListener("click", async () => {
    const section = document.getElementById("cidr-update");
    if (section && section.classList.contains("cidr-busy")) return;

    const selectedRegions = Array.from(document.querySelectorAll(".cidr-region-checkbox:checked")).map(el => el.value);
    const regionScopes = Array.from(document.querySelectorAll(".cidr-scope-checkbox:checked")).map(el => el.value);
    const includeNonGeo = document.getElementById("cidr-include-non-geo-fallback")?.checked || false;
    const excludeRu = document.getElementById("cidr-exclude-ru-cidrs")?.checked || false;
    const strictGeo = document.getElementById("cidr-strict-geo-filter")?.checked || false;
    const gameKeys = Array.from(document.querySelectorAll(".cidr-game-checkbox:checked")).map(el => el.value);
    const filterByAntifilter = document.getElementById("cidr-filter-by-antifilter")?.checked || false;
    const dpiPriorityFiles = Array.isArray(window._cidrDpiPriorityFiles) ? window._cidrDpiPriorityFiles : [];
    const dpiMandatoryFiles = Array.isArray(window._cidrDpiMandatoryFiles) ? window._cidrDpiMandatoryFiles : [];
    const dpiPriorityMinBudgetRaw = String(document.getElementById("cidr-dpi-priority-min-budget")?.value || "").trim();
    const dpiPriorityMinBudget = /^\d+$/.test(dpiPriorityMinBudgetRaw) ? Number(dpiPriorityMinBudgetRaw) : 0;

    const statusEl = document.getElementById("cidr-update-status");

    if (typeof window._pollCidrTaskExternal !== "function") {
      if (statusEl) { statusEl.textContent = "Ошибка: интерфейс не готов, обновите страницу"; statusEl.className = "notification notification--error"; statusEl.hidden = false; }
      return;
    }

    const steps = [];

    if (filterByAntifilter) {
      steps.push({
        label: "Обновление антифильтра",
        start: async () => {
          const r = await fetch("/api/antifilter/refresh", {
            method: "POST",
            headers: { "X-CSRFToken": csrf() },
          });
          const d = await r.json();
          if (!d.success) throw new Error(d.message || "Ошибка обновления антифильтра");
          return d.task_id;
        },
      });
    }

    steps.push({
      label: "Генерация маршрутов из БД",
      start: async () => {
        const r = await fetch("/api/cidr-db/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
          body: JSON.stringify({
            action: "generate",
            regions: selectedRegions,
            region_scopes: regionScopes,
            include_non_geo_fallback: includeNonGeo,
            exclude_ru_cidrs: excludeRu,
            strict_geo_filter: strictGeo,
            include_game_keys: gameKeys,
            filter_by_antifilter: filterByAntifilter,
            dpi_priority_files: dpiPriorityFiles,
            dpi_mandatory_files: dpiMandatoryFiles,
            dpi_priority_min_budget: dpiPriorityMinBudget,
          }),
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.message || "Ошибка генерации");
        return d.task_id;
      },
    });

    steps.push({
      label: "Применение изменений (doall.sh)",
      start: async () => {
        const r = await fetch("/run-doall", {
          method: "POST",
          headers: { "X-CSRFToken": csrf() },
        });
        const d = await r.json();
        if (!r.ok || !d.success) throw new Error(d.message || "Ошибка запуска doall");
        if (!d.task_id) throw new Error("Не получен task_id для doall");
        return {
          task_id: d.task_id,
          status_url: d.status_url || `/api/tasks/${encodeURIComponent(d.task_id)}`,
        };
      },
    });

    window._pollCidrTaskExternal(steps);
  });

  // ── Antifilter.download ─────────────────────────────────────────────
  (function () {
    const badge = document.getElementById("antifilter-badge");
    const total = document.getElementById("antifilter-total");
    const ts = document.getElementById("antifilter-ts");
    const msg = document.getElementById("antifilter-status-msg");

    function fmtDt(iso) {
      if (!iso) return "—";
      try { return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); } catch { return iso; }
    }
    function setMsg(text, level) {
      if (!msg) return;
      msg.textContent = text;
      msg.className = "notification " + (level === "error" ? "notification--error" : level === "success" ? "notification--success" : "notification--info");
      msg.hidden = !text;
    }

    async function loadStatus() {
      try {
        const r = await fetch("/api/antifilter/status", { cache: "no-store" });
        const d = await r.json();
        if (!d.success) return;
        const st = d.refresh_status || "never";
        const labels = { ok: "OK", error: "Ошибка", never: "Нет данных", running: "Обновляется" };
        if (badge) { badge.textContent = labels[st] || st; badge.className = "cidr-db-badge cidr-db-badge--" + st; }
        if (total) total.textContent = d.cidr_count ? `${d.cidr_count.toLocaleString("ru-RU")} заблок. подсетей` : "";
        if (ts && d.last_refreshed_at) ts.textContent = "Обновлено: " + fmtDt(d.last_refreshed_at);
      } catch { }
    }

    document.getElementById("antifilter-refresh-btn")?.addEventListener("click", async () => {
      setMsg("Запускаю обновление антифильтра…", "info");
      try {
        const r = await fetch("/api/antifilter/refresh", {
          method: "POST",
          headers: { "X-CSRFToken": csrf() },
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.message || "Ошибка");
        setMsg("Обновление запущено. Займёт ~1–2 минуты.", "success");
        const taskId = d.task_id;
        if (taskId) {
          const poll = setInterval(async () => {
            try {
              const tr = await fetch(`/api/cidr-lists/task/${encodeURIComponent(taskId)}`, { cache: "no-store" });
              const td = await tr.json();
              if (td.status === "completed" || td.status === "failed") {
                clearInterval(poll);
                await loadStatus();
                setMsg(td.status === "completed" ? "Антифильтр обновлён." : "Ошибка обновления антифильтра.", td.status === "completed" ? "success" : "error");
              }
            } catch { clearInterval(poll); }
          }, 3000);
        }
      } catch (e) { setMsg("Ошибка: " + (e.message || e), "error"); }
    });

    // Load on tab activation
    const cidrTabMenuItem = document.querySelector('[data-tab="cidr-update"]');
    if (cidrTabMenuItem) {
      cidrTabMenuItem.addEventListener("click", loadStatus);
    }
    if (document.getElementById("cidr-update")?.classList.contains("active")) {
      loadStatus();
    }
  })();

  // ── Presets ────────────────────────────────────────────────────────
  const presetsGrid = document.getElementById("cidr-presets-grid");
  let _presetsData = [];

  function providerName(key) {
    // Try to get from DB providers table first, then strip -ips.txt
    const row = document.querySelector(`[data-cidr-file="${key}"] .cidr-region-title`);
    if (row) return row.textContent.trim();
    return key.replace(/-ips\.txt$/, "");
  }

  function renderPresets(presets) {
    if (!presetsGrid) return;
    if (!presets.length) { presetsGrid.innerHTML = '<div class="help-text" style="padding:.5rem">Нет пресетов</div>'; return; }
    presetsGrid.innerHTML = presets.map(p => {
      const providers = Array.isArray(p.providers) ? p.providers : [];
      const provBadges = providers.slice(0, 6)
        .map(k => `<span class="cidr-preset-prov-badge">${escapeHtml(providerName(k))}</span>`)
        .join("");
      const more = providers.length > 6 ? `<span class="cidr-preset-prov-badge">+${providers.length - 6}</span>` : "";

      const manageBtns = !p.is_builtin ? `
              <button class="button cidr-preset-card__icon-btn" data-preset-edit="${p.id}" title="Редактировать">✏️</button>
              <button class="button delete-button cidr-preset-card__icon-btn" data-preset-delete="${p.id}" title="Удалить">🗑</button>
            ` : `
              <button class="button cidr-preset-card__icon-btn" data-preset-reset="${p.id}" title="Сбросить к умолчанию">↩</button>
            `;

      const typeLabel = p.is_builtin ? "Встроенный" : "Пользовательский";
      return `<article class="cidr-preset-card cidr-preset-card--${p.is_builtin ? 'builtin' : 'custom'}" data-preset-id="${p.id}">
            <div class="cidr-preset-card__head">
              <div class="cidr-preset-card__name">${escapeHtml(p.name || "Без названия")}</div>
              <span class="cidr-preset-card__type">${typeLabel}</span>
            </div>
            <div class="cidr-preset-card__desc">${escapeHtml(p.description || "Без описания")}</div>
            <div class="cidr-preset-card__providers">${provBadges}${more}</div>

            <div class="cidr-preset-card__actions-main">
              <button class="button save-button" data-preset-apply="${p.id}">Заменить</button>
              <button class="button" data-preset-add="${p.id}">Добавить</button>
              <button class="button" data-preset-remove="${p.id}">Убрать</button>
            </div>

            <div class="cidr-preset-card__actions-meta">
              <label class="cidr-preset-card__mark">
                <input type="checkbox" data-preset-select="${p.id}">
                <span>Отметить</span>
              </label>
              <div class="cidr-preset-card__manage">${manageBtns}</div>
            </div>
          </article>`;
    }).join("");

    presetsGrid.querySelectorAll("[data-preset-apply]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = _presetsData.find(x => x.id === parseInt(btn.dataset.presetApply));
        if (p) applyPreset(p, "replace");
      });
    });
    presetsGrid.querySelectorAll("[data-preset-add]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = _presetsData.find(x => x.id === parseInt(btn.dataset.presetAdd));
        if (p) applyPreset(p, "add");
      });
    });
    presetsGrid.querySelectorAll("[data-preset-remove]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = _presetsData.find(x => x.id === parseInt(btn.dataset.presetRemove));
        if (p) applyPreset(p, "remove");
      });
    });
    presetsGrid.querySelectorAll("[data-preset-edit]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = _presetsData.find(x => x.id === parseInt(btn.dataset.presetEdit));
        if (p) openPresetForm(p);
      });
    });
    presetsGrid.querySelectorAll("[data-preset-delete]").forEach(btn => {
      btn.addEventListener("click", () => deletePreset(parseInt(btn.dataset.presetDelete)));
    });
    presetsGrid.querySelectorAll("[data-preset-reset]").forEach(btn => {
      btn.addEventListener("click", () => resetPreset(parseInt(btn.dataset.presetReset)));
    });
  }

  async function loadPresets() {
    try {
      const r = await fetch("/api/cidr-presets", { cache: "no-store" });
      const d = await r.json();
      if (d.success) { _presetsData = d.presets; renderPresets(d.presets); }
    } catch (e) {
      if (presetsGrid) presetsGrid.innerHTML = '<div class="help-text" style="padding:.5rem;color:#e06060">Ошибка загрузки пресетов</div>';
    }
  }

  function _collectMarkedPresets() {
    const markedIds = Array.from(document.querySelectorAll('[data-preset-select]:checked'))
      .map(el => parseInt(el.dataset.presetSelect))
      .filter(id => Number.isFinite(id));
    return _presetsData.filter(p => markedIds.includes(p.id));
  }

  function applyPreset(preset, mode = "replace") {
    applyPresetBatch([preset], mode);
  }

  function applyPresetBatch(presets, mode = "replace") {
    if (!Array.isArray(presets) || !presets.length) return;

    const selectedProviders = new Set(Array.from(document.querySelectorAll(".cidr-region-checkbox:checked")).map(el => el.value));
    if (mode === "replace") selectedProviders.clear();

    presets.forEach((preset) => {
      (preset.providers || []).forEach((key) => {
        if (mode === "remove") selectedProviders.delete(key);
        else selectedProviders.add(key);
      });
    });

    document.querySelectorAll(".cidr-region-checkbox").forEach((cb) => {
      cb.checked = selectedProviders.has(cb.value);
    });

    const selectedScopes = new Set(Array.from(document.querySelectorAll(".cidr-scope-checkbox:checked")).map(el => el.value));
    const presetScopes = new Set();
    let fallbackPreset = false;
    let excludeRuPreset = false;
    presets.forEach((preset) => {
      const settings = preset.settings || {};
      (settings.region_scopes || []).forEach((scope) => presetScopes.add(scope));
      fallbackPreset = fallbackPreset || !!settings.include_non_geo_fallback;
      excludeRuPreset = excludeRuPreset || !!settings.exclude_ru_cidrs;
    });

    const finalScopes = new Set();
    if (mode === "replace") {
      (presetScopes.size ? presetScopes : new Set(["all"]))
        .forEach((scope) => finalScopes.add(scope));
    } else if (mode === "add") {
      selectedScopes.forEach((scope) => finalScopes.add(scope));
      presetScopes.forEach((scope) => finalScopes.add(scope));
    } else {
      selectedScopes.forEach((scope) => finalScopes.add(scope));
    }

    document.querySelectorAll(".cidr-scope-checkbox").forEach((cb) => {
      cb.checked = finalScopes.has(cb.value);
    });

    const fallbackCb = document.getElementById("cidr-include-non-geo-fallback");
    if (fallbackCb) {
      if (mode === "replace") fallbackCb.checked = fallbackPreset;
      else if (mode === "add") fallbackCb.checked = fallbackCb.checked || fallbackPreset;
    }
    const excludeRuCb = document.getElementById("cidr-exclude-ru-cidrs");
    if (excludeRuCb) {
      if (mode === "replace") excludeRuCb.checked = excludeRuPreset;
      else if (mode === "add") excludeRuCb.checked = excludeRuCb.checked || excludeRuPreset;
    }

    if (typeof window._cidrRenderMeta === "function") window._cidrRenderMeta();
    if (typeof window._scheduleCidrToIpFileSync === "function") {
      window._scheduleCidrToIpFileSync(40, { persist: true });
    }

    const statusEl = document.getElementById("cidr-update-status");
    if (statusEl) {
      const modeLabel = mode === "replace" ? "заменён" : mode === "add" ? "добавлен" : "убран";
      statusEl.textContent = `Пресет(ы) ${modeLabel}: активно ${selectedProviders.size} провайдеров.`;
      statusEl.className = "notification notification--success";
      statusEl.hidden = false;
      setTimeout(() => { statusEl.hidden = true; }, 4500);
    }
  }

  function openPresetForm(preset) {
    const wrap = document.getElementById("cidr-preset-form-wrap");
    if (!wrap) return;
    wrap.hidden = false;
    document.getElementById("cidr-preset-form-title").textContent = preset ? "Редактировать пресет" : "Новый пресет";
    document.getElementById("cidr-preset-edit-id").value = preset ? preset.id : "";
    document.getElementById("cidr-preset-name-input").value = preset ? preset.name : "";
    document.getElementById("cidr-preset-desc-input").value = preset ? preset.description : "";
    wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function savePreset() {
    const id = document.getElementById("cidr-preset-edit-id").value;
    const name = document.getElementById("cidr-preset-name-input").value.trim();
    const desc = document.getElementById("cidr-preset-desc-input").value.trim();
    const formMsg = document.getElementById("cidr-preset-form-msg");
    if (!name) { if (formMsg) { formMsg.textContent = "Введите название"; formMsg.className = "notification notification--error"; formMsg.hidden = false; } return; }

    const providers = Array.from(document.querySelectorAll(".cidr-region-checkbox:checked")).map(el => el.value);
    const regionScopes = Array.from(document.querySelectorAll(".cidr-scope-checkbox:checked")).map(el => el.value);
    const settings = {
      region_scopes: regionScopes,
      include_non_geo_fallback: document.getElementById("cidr-include-non-geo-fallback")?.checked || false,
      exclude_ru_cidrs: document.getElementById("cidr-exclude-ru-cidrs")?.checked || false,
    };

    const url = id ? `/api/cidr-presets/${id}` : "/api/cidr-presets";
    const method = id ? "PUT" : "POST";
    try {
      const r = await fetch(url, { method, headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify({ name, description: desc, providers, settings }) });
      const d = await r.json();
      if (!d.success) throw new Error(d.message || "Ошибка сохранения");
      document.getElementById("cidr-preset-form-wrap").hidden = true;
      await loadPresets();
    } catch (e) {
      if (formMsg) { formMsg.textContent = "Ошибка: " + (e.message || e); formMsg.className = "notification notification--error"; formMsg.hidden = false; }
    }
  }

  async function deletePreset(id) {
    if (!confirm("Удалить пресет?")) return;
    try {
      const r = await fetch(`/api/cidr-presets/${id}`, { method: "DELETE", headers: { "X-CSRFToken": csrf() } });
      const d = await r.json();
      if (d.success) await loadPresets();
    } catch (e) { }
  }

  async function resetPreset(id) {
    if (!confirm("Сбросить пресет к встроенным значениям?")) return;
    try {
      const r = await fetch(`/api/cidr-presets/${id}/reset`, { method: "POST", headers: { "X-CSRFToken": csrf() } });
      const d = await r.json();
      if (d.success) await loadPresets();
    } catch (e) { }
  }

  document.getElementById("cidr-preset-create-btn")?.addEventListener("click", () => openPresetForm(null));
  document.getElementById("cidr-preset-save-btn")?.addEventListener("click", savePreset);
  document.getElementById("cidr-preset-cancel-btn")?.addEventListener("click", () => {
    document.getElementById("cidr-preset-form-wrap").hidden = true;
  });
  document.getElementById("cidr-presets-apply-selected")?.addEventListener("click", () => {
    const selected = _collectMarkedPresets();
    if (!selected.length) return;
    applyPresetBatch(selected, "replace");
  });
  document.getElementById("cidr-presets-add-selected")?.addEventListener("click", () => {
    const selected = _collectMarkedPresets();
    if (!selected.length) return;
    applyPresetBatch(selected, "add");
  });
  document.getElementById("cidr-presets-clear-selection")?.addEventListener("click", () => {
    document.querySelectorAll('[data-preset-select]').forEach((cb) => { cb.checked = false; });
  });

  // ── Init: load on tab activation ──────────────────────────────────
  let _dbLoaded = false;
  let _presetsLoaded = false;

  function onCidrTabActive() {
    if (!_dbLoaded) { _dbLoaded = true; loadDbStatus(); }
    if (!_presetsLoaded) { _presetsLoaded = true; loadPresets(); }
  }

  // Watch for tab activation via the existing menu system
  const cidrTabMenuItem = document.querySelector('[data-tab="cidr-update"]');
  if (cidrTabMenuItem) {
    cidrTabMenuItem.addEventListener("click", onCidrTabActive);
  }
  // Also load if already active
  if (document.getElementById("cidr-update")?.classList.contains("active")) {
    onCidrTabActive();
  }
})();

