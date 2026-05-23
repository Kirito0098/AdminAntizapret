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
        if (data.success) {
          window.showNotification?.(
            (action === 'grant' ? 'Доступ выдан: ' : 'Доступ отозван: ') + configLabel,
            'success'
          );
        } else {
          window.showNotification?.('Ошибка: ' + (data.message || 'unknown'), 'error');
          this.checked = !this.checked; // откат
        }
      })
      .catch(() => {
        window.showNotification?.('Ошибка сети', 'error');
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

// ── Action logs: grouped table + filters + sort + export ────────────────────
(function () {
  const table = document.getElementById("auditLogTable");
  if (!table) return;

  const STORAGE_KEY = "actionLogsFilterStateV2";
  const searchEl = document.getElementById("auditSearch");
  const sourcePills = document.getElementById("auditSourcePills");
  const userSelect = document.getElementById("auditUserFilter");
  const statusSelect = document.getElementById("auditStatusFilter");
  const sortSelect = document.getElementById("auditSortSelect");
  const countBadge = document.getElementById("auditLogCount");
  const clearBtn = document.getElementById("auditClearBtn");
  const exportBtn = document.getElementById("auditExportBtn");
  const emptyClearBtn = document.getElementById("auditEmptyClearBtn");
  const emptyState = document.getElementById("auditEmptyFilter");
  const alertToggle = document.getElementById("auditAlertToggle");

  const allRows = Array.from(table.querySelectorAll("tr.audit-action-row"));
  const allBodies = Array.from(table.querySelectorAll("tbody.audit-session-tbody"));
  const allDayBodies = Array.from(table.querySelectorAll("tbody.audit-day-hdr-tbody"));
  const total = allRows.length;

  const collapsedSessions = new Set();
  const collapsedDays = new Set();
  const daySessionMap = new Map();
  allDayBodies.forEach((dayBody) => {
    const dayId = dayBody.dataset.dayId;
    daySessionMap.set(dayId, allBodies.filter((sessionBody) => sessionBody.dataset.dayId === dayId));
  });

  const users = [...new Set(allRows.map((row) => row.dataset.user).filter(Boolean))].sort();
  users.forEach((user) => {
    const opt = document.createElement("option");
    opt.value = user;
    opt.textContent = user;
    userSelect?.appendChild(opt);
  });

  const threatCount = allRows.filter((row) => row.dataset.alert === "true").length;
  if (alertToggle) {
    if (threatCount === 0) {
      alertToggle.hidden = true;
    } else {
      alertToggle.title = `Показать только подозрительные события (${threatCount})`;
      const textNode = Array.from(alertToggle.childNodes).find((node) => node.nodeType === 3);
      if (textNode) textNode.textContent = ` Угрозы (${threatCount})`;
    }
  }

  allBodies.forEach((tb) => {
    collapsedSessions.add(tb.dataset.sessionId);
    tb.classList.add("is-collapsed");
  });
  allDayBodies.forEach((db, index) => {
    if (index > 0) {
      collapsedDays.add(db.dataset.dayId);
      db.classList.add("is-collapsed");
    }
  });

  let activeSrc = "";
  let alertOnly = false;
  let activeSort = sortSelect?.value || "time_desc";

  function persistFilterState() {
    const payload = {
      q: (searchEl?.value || "").trim(),
      src: activeSrc,
      user: userSelect?.value || "",
      status: statusSelect?.value || "",
      alertOnly,
      sort: activeSort,
    };
    window.sessionStorage?.setItem(STORAGE_KEY, JSON.stringify(payload));
  }

  function restoreFilterState() {
    const raw = window.sessionStorage?.getItem(STORAGE_KEY);
    if (!raw) return;
    try {
      const data = JSON.parse(raw);
      if (searchEl && typeof data.q === "string") searchEl.value = data.q;
      if (typeof data.src === "string") activeSrc = data.src;
      if (userSelect && typeof data.user === "string") userSelect.value = data.user;
      if (statusSelect && typeof data.status === "string") statusSelect.value = data.status;
      if (typeof data.alertOnly === "boolean") alertOnly = data.alertOnly;
      if (typeof data.sort === "string") activeSort = data.sort;
    } catch (_err) {
      // Ignore broken session storage payloads.
    }
  }

  function syncFilterUi() {
    sourcePills?.querySelectorAll(".audit-pill").forEach((pill) => {
      pill.classList.toggle("audit-pill--active", (pill.dataset.src || "") === activeSrc);
    });
    if (sortSelect) sortSelect.value = activeSort;
    if (alertToggle) {
      alertToggle.dataset.active = alertOnly ? "true" : "false";
      alertToggle.classList.toggle("audit-pill--active", alertOnly);
    }
  }

  function getSearch() {
    return (searchEl?.value || "").trim().toLowerCase();
  }

  function rowSortValue(row, sortMode) {
    if (sortMode === "user_asc") return (row.dataset.user || "").toLowerCase();
    if (sortMode === "result_asc") return (row.dataset.statusDisplay || row.dataset.status || "").toLowerCase();
    return Number(row.dataset.ts || 0);
  }

  function sortRowsInSession(sessionBody, sortMode) {
    const rows = Array.from(sessionBody.querySelectorAll("tr.audit-action-row"));
    rows.sort((a, b) => {
      const av = rowSortValue(a, sortMode);
      const bv = rowSortValue(b, sortMode);
      if (sortMode === "time_asc") return av - bv;
      if (sortMode === "time_desc") return bv - av;
      return String(av).localeCompare(String(bv), "ru", { sensitivity: "base" });
    });
    rows.forEach((row) => sessionBody.appendChild(row));
  }

  function sortSessionsWithinDay(dayId, sortMode) {
    const sessions = daySessionMap.get(dayId) || [];
    if (sortMode === "time_desc" || sortMode === "time_asc") {
      sessions.sort((a, b) => {
        const aTopTs = Number(a.querySelector("tr.audit-action-row")?.dataset.ts || 0);
        const bTopTs = Number(b.querySelector("tr.audit-action-row")?.dataset.ts || 0);
        return sortMode === "time_desc" ? bTopTs - aTopTs : aTopTs - bTopTs;
      });
    } else if (sortMode === "user_asc") {
      sessions.sort((a, b) =>
        String(a.dataset.sessionUser || "").localeCompare(String(b.dataset.sessionUser || ""), "ru", { sensitivity: "base" })
      );
    } else if (sortMode === "result_asc") {
      sessions.sort((a, b) => {
        const aStatus = (a.querySelector("tr.audit-action-row")?.dataset.statusDisplay || "").toLowerCase();
        const bStatus = (b.querySelector("tr.audit-action-row")?.dataset.statusDisplay || "").toLowerCase();
        return aStatus.localeCompare(bStatus, "ru", { sensitivity: "base" });
      });
    }
    const dayHeaderBody = allDayBodies.find((body) => body.dataset.dayId === dayId);
    if (!dayHeaderBody || !dayHeaderBody.parentNode) return;
    let insertAfter = dayHeaderBody;
    sessions.forEach((sessionBody) => {
      dayHeaderBody.parentNode.insertBefore(sessionBody, insertAfter.nextSibling);
      insertAfter = sessionBody;
    });
  }

  function applySort() {
    allBodies.forEach((sessionBody) => sortRowsInSession(sessionBody, activeSort));
    allDayBodies.forEach((dayBody) => sortSessionsWithinDay(dayBody.dataset.dayId, activeSort));
  }

  function applyFilters() {
    const q = getSearch();
    const src = activeSrc;
    const user = userSelect?.value || "";
    const status = statusSelect?.value || "";

    let visible = 0;
    allRows.forEach((row) => {
      const rowStatus = (row.dataset.status || "").toLowerCase();
      const rowText = (row.dataset.text || "").toLowerCase();
      const matches =
        (!src || row.dataset.src === src) &&
        (!user || row.dataset.user === user) &&
        (!status || rowStatus === status) &&
        (!q || rowText.includes(q)) &&
        (!alertOnly || row.dataset.alert === "true");
      row.dataset.filterHidden = matches ? "0" : "1";
      const sessionCollapsed = collapsedSessions.has(row.dataset.sessionId);
      row.hidden = !matches || sessionCollapsed;
      if (matches) visible += 1;
    });

    allBodies.forEach((sessionBody) => {
      const dayCollapsed = collapsedDays.has(sessionBody.dataset.dayId);
      const anyPass = Array.from(sessionBody.querySelectorAll("tr.audit-action-row"))
        .some((row) => row.dataset.filterHidden === "0");
      const hdr = sessionBody.querySelector(".audit-session-hdr");
      sessionBody.hidden = dayCollapsed;
      if (hdr) hdr.hidden = !anyPass || dayCollapsed;
      sessionBody.dataset.hasVisibleRows = anyPass ? "1" : "0";
    });

    allDayBodies.forEach((dayBody) => {
      const dayId = dayBody.dataset.dayId;
      const sessions = daySessionMap.get(dayId) || [];
      const anyPass = sessions.some((sessionBody) => sessionBody.dataset.hasVisibleRows === "1");
      dayBody.hidden = !anyPass;
      dayBody.classList.toggle("is-collapsed", collapsedDays.has(dayId));
    });

    const isFiltered = !!(q || src || user || status || alertOnly);
    if (countBadge) {
      countBadge.innerHTML = isFiltered
        ? `<strong>${visible}</strong> из ${total}`
        : `${total} записей`;
    }

    const showEmpty = visible === 0 && isFiltered;
    if (emptyState) emptyState.hidden = !showEmpty;
    table.style.display = showEmpty ? "none" : "";
    if (clearBtn) clearBtn.style.opacity = isFiltered ? "1" : "0.4";
    persistFilterState();
  }

  function clearFilters() {
    if (searchEl) searchEl.value = "";
    if (userSelect) userSelect.value = "";
    if (statusSelect) statusSelect.value = "";
    activeSrc = "";
    alertOnly = false;
    activeSort = "time_desc";
    syncFilterUi();
    applySort();
    applyFilters();
  }

  function applyInitialFilterFromQuery() {
    const params = new URLSearchParams(window.location.search || "");
    const src = (params.get("action_src") || "").trim().toLowerCase();
    if (src) activeSrc = src;
  }

  function getExportEndpoint() {
    const template = document.getElementById("auditExportPayloadTemplate");
    if (!template) return "";
    try {
      const parsed = JSON.parse(template.textContent || "{}");
      return String(parsed.endpoint || "");
    } catch (_err) {
      return "";
    }
  }

  function triggerCsvExport() {
    const endpoint = getExportEndpoint();
    if (!endpoint) return;
    const params = new URLSearchParams();
    const q = (searchEl?.value || "").trim();
    if (q) params.set("q", q);
    if (activeSrc) params.set("src", activeSrc);
    if (userSelect?.value) params.set("user", userSelect.value);
    if (statusSelect?.value) params.set("status", statusSelect.value);
    if (alertOnly) params.set("alert_only", "1");
    params.set("sort", activeSort);
    const url = params.toString() ? `${endpoint}?${params.toString()}` : endpoint;
    window.location.href = url;
  }

  table.addEventListener("click", (event) => {
    const dayHdrRow = event.target.closest(".audit-day-hdr");
    if (dayHdrRow) {
      const dayBody = dayHdrRow.closest("tbody.audit-day-hdr-tbody");
      const dayId = dayBody?.dataset.dayId;
      if (!dayId) return;
      if (collapsedDays.has(dayId)) collapsedDays.delete(dayId);
      else collapsedDays.add(dayId);
      applyFilters();
      return;
    }

    const sessionHdrRow = event.target.closest(".audit-session-hdr");
    if (!sessionHdrRow) return;
    const sessionBody = sessionHdrRow.closest("tbody.audit-session-tbody");
    const sessionId = sessionBody?.dataset.sessionId;
    if (!sessionId || !sessionBody) return;
    if (collapsedDays.has(sessionBody.dataset.dayId)) return;

    const wasCollapsed = collapsedSessions.has(sessionId);
    if (wasCollapsed) {
      collapsedSessions.delete(sessionId);
      sessionBody.classList.remove("is-collapsed");
    } else {
      collapsedSessions.add(sessionId);
      sessionBody.classList.add("is-collapsed");
    }
    sessionBody.querySelectorAll("tr.audit-action-row").forEach((row) => {
      row.hidden = row.dataset.filterHidden === "1" || !wasCollapsed;
    });
  });

  sourcePills?.addEventListener("click", (event) => {
    const pill = event.target.closest(".audit-pill");
    if (!pill) return;
    activeSrc = pill.dataset.src || "";
    syncFilterUi();
    applyFilters();
  });

  searchEl?.addEventListener("input", applyFilters);
  userSelect?.addEventListener("change", applyFilters);
  statusSelect?.addEventListener("change", applyFilters);
  sortSelect?.addEventListener("change", () => {
    activeSort = sortSelect.value || "time_desc";
    applySort();
    applyFilters();
  });
  alertToggle?.addEventListener("click", () => {
    alertOnly = !alertOnly;
    syncFilterUi();
    applyFilters();
  });
  clearBtn?.addEventListener("click", clearFilters);
  emptyClearBtn?.addEventListener("click", clearFilters);
  exportBtn?.addEventListener("click", triggerCsvExport);

  (function convertTimesToLocal() {
    const pad = (n) => String(n).padStart(2, "0");
    table.querySelectorAll(".audit-td-time[data-utc]").forEach((td) => {
      const iso = td.dataset.utc;
      if (!iso) return;
      const date = new Date(iso.includes("T") ? `${iso}Z` : iso);
      if (isNaN(date)) return;
      const dateEl = td.querySelector(".audit-time-date");
      const clockEl = td.querySelector(".audit-time-clock");
      if (dateEl) dateEl.textContent = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
      if (clockEl) clockEl.textContent = `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    });

    table.querySelectorAll(".audit-session-timerange[data-session-start]").forEach((el) => {
      const startIso = el.dataset.sessionStart;
      const endIso = el.dataset.sessionEnd;
      if (!startIso || !endIso) return;
      const start = new Date(`${startIso}Z`);
      const end = new Date(`${endIso}Z`);
      if (isNaN(start) || isNaN(end)) return;

      const fmtDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
      const fmtTime = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
      const fmtTimeSec = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
      const sameDay = fmtDate(start) === fmtDate(end);
      const sameTime = start.getTime() === end.getTime();

      if (sameTime) {
        el.textContent = `${fmtDate(start)}, ${fmtTimeSec(start)}`;
      } else if (sameDay) {
        el.textContent = `${fmtDate(start)}, ${fmtTime(start)} — ${fmtTime(end)}`;
      } else {
        el.textContent = `${fmtDate(start)} ${fmtTime(start)} — ${fmtDate(end)} ${fmtTime(end)}`;
      }
    });

    const header = document.getElementById("auditTimeHeader");
    if (header) header.textContent = "Время (местное)";
  })();

  restoreFilterState();
  applyInitialFilterFromQuery();
  syncFilterUi();
  applySort();
  applyFilters();
})();

// ── Telegram audit filter table ─────────────────────────────────────────────
(function () {
  const table = document.getElementById("tgAuditTable");
  if (!table) return;

  const rows = Array.from(table.querySelectorAll(".tg-audit-row"));
  const searchEl = document.getElementById("tgAuditSearch");
  const sourcePills = document.getElementById("tgAuditSourcePills");
  const userSelect = document.getElementById("tgAuditUserFilter");
  const countBadge = document.getElementById("tgAuditCount");
  const clearBtn = document.getElementById("tgAuditClearBtn");
  const emptyState = document.getElementById("tgAuditEmpty");
  const total = rows.length;
  let activeSrc = "";

  const users = [...new Set(rows.map((row) => row.dataset.user).filter(Boolean))].sort();
  users.forEach((user) => {
    const option = document.createElement("option");
    option.value = user;
    option.textContent = user;
    userSelect?.appendChild(option);
  });

  const getSearch = () => (searchEl?.value || "").trim().toLowerCase();

  function applyFilters() {
    const q = getSearch();
    const user = userSelect?.value || "";
    let visible = 0;

    rows.forEach((row) => {
      const match =
        (!activeSrc || row.dataset.src === activeSrc) &&
        (!user || row.dataset.user === user) &&
        (!q || (row.dataset.text || "").includes(q));
      row.hidden = !match;
      if (match) visible += 1;
    });

    const isFiltered = !!(q || activeSrc || user);
    if (countBadge) {
      countBadge.innerHTML = isFiltered ? `<strong>${visible}</strong> из ${total}` : `${total} записей`;
    }
    if (emptyState) emptyState.hidden = visible !== 0;
    table.style.display = visible === 0 ? "none" : "";
  }

  function clearFilters() {
    if (searchEl) searchEl.value = "";
    if (userSelect) userSelect.value = "";
    activeSrc = "";
    sourcePills?.querySelectorAll(".audit-pill").forEach((pill, index) => {
      pill.classList.toggle("audit-pill--active", index === 0);
    });
    applyFilters();
  }

  function convertTimesToLocal() {
    const pad = (n) => String(n).padStart(2, "0");
    table.querySelectorAll(".tg-audit-time[data-utc]").forEach((cell) => {
      const iso = cell.dataset.utc;
      if (!iso) return;
      const date = new Date(iso.includes("T") ? `${iso}Z` : iso);
      if (isNaN(date)) return;
      cell.textContent = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    });
  }

  searchEl?.addEventListener("input", applyFilters);
  userSelect?.addEventListener("change", applyFilters);
  clearBtn?.addEventListener("click", clearFilters);
  sourcePills?.addEventListener("click", (event) => {
    const pill = event.target.closest(".audit-pill");
    if (!pill) return;
    activeSrc = pill.dataset.src || "";
    sourcePills.querySelectorAll(".audit-pill").forEach((item) => {
      item.classList.toggle("audit-pill--active", item === pill);
    });
    applyFilters();
  });

  convertTimesToLocal();
  applyFilters();
})();

// Maintenance: синхронизация класса is-on у чипов получателей TG
document.querySelectorAll(".maintenance-recipient-chip__input").forEach((input) => {
  const syncChipState = () => {
    const chip = input.closest(".maintenance-recipient-chip");
    if (!chip) return;
    chip.classList.toggle("is-on", input.checked);
    const counter = document.querySelector(".maintenance-recipient-field__count");
    if (counter) {
      const total = document.querySelectorAll(".maintenance-recipient-chip__input").length;
      const selected = document.querySelectorAll(".maintenance-recipient-chip__input:checked").length;
      counter.textContent = `${selected} из ${total}`;
    }
  };
  input.addEventListener("change", syncChipState);
  syncChipState();
});
