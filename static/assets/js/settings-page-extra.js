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

// ── Action logs: day/session collapse + filter ─────────────────────────────
(function () {
  const table = document.getElementById("auditLogTable");
  if (!table) return;

  const searchEl      = document.getElementById("auditSearch");
  const sourcePills   = document.getElementById("auditSourcePills");
  const userSelect    = document.getElementById("auditUserFilter");
  const countBadge    = document.getElementById("auditLogCount");
  const clearBtn      = document.getElementById("auditClearBtn");
  const emptyClearBtn = document.getElementById("auditEmptyClearBtn");
  const emptyState    = document.getElementById("auditEmptyFilter");
  const alertToggle   = document.getElementById("auditAlertToggle");

  const allRows   = Array.from(table.querySelectorAll("tr.audit-action-row"));
  const allBodies = Array.from(table.querySelectorAll("tbody.audit-session-tbody"));
  const total     = allRows.length;

  // ── Populate user dropdown ──
  const users = [...new Set(allRows.map(r => r.dataset.user).filter(Boolean))].sort();
  users.forEach(u => {
    const opt = document.createElement("option");
    opt.value = u; opt.textContent = u;
    userSelect?.appendChild(opt);
  });

  // ── Threat button label ──
  const threatCount = allRows.filter(r => r.dataset.alert === "true").length;
  if (alertToggle) {
    if (threatCount === 0) {
      alertToggle.hidden = true;
    } else {
      alertToggle.title = `Показать только подозрительные события (${threatCount})`;
      const textNode = Array.from(alertToggle.childNodes).find(n => n.nodeType === 3);
      if (textNode) textNode.textContent = ` Угрозы (${threatCount})`;
    }
  }

  // ── Collapse state ──
  const collapsedSessions = new Set();
  const collapsedDays     = new Set();

  // All sessions collapsed on load
  allBodies.forEach(tb => {
    collapsedSessions.add(tb.dataset.sessionId);
    tb.classList.add("is-collapsed");
  });

  // ── Filter state ──
  let activeSrc = "";
  let alertOnly = false;

  function getSearch() {
    return (searchEl?.value || "").trim().toLowerCase();
  }

  // ── Build day groups using CLIENT local timezone ──────────────────────────
  // Done once at init. Reads data-session-end (UTC ISO) and converts to
  // local date — so the same local calendar day is always one group,
  // even if UTC midnight falls mid-session.
  let allDayBodies = [];

  function buildDayGroups() {
    const pad = n => String(n).padStart(2, "0");

    // Tag each session tbody with its local date (from session_end UTC)
    allBodies.forEach(tb => {
      const el     = tb.querySelector(".audit-session-timerange[data-session-end]");
      const endIso = el?.dataset.sessionEnd;
      if (!endIso) { tb.dataset.dayId = ""; return; }
      const d = new Date(endIso + "Z");
      tb.dataset.dayId = isNaN(d)
        ? ""
        : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    });

    // Insert a day-header <tbody> before the first session of each local date
    const seenDays = new Set();
    allBodies.forEach(tb => {
      const dayId = tb.dataset.dayId;
      if (!dayId || seenDays.has(dayId)) return;
      seenDays.add(dayId);

      const daySessions  = allBodies.filter(t => t.dataset.dayId === dayId);
      const sessionCount = daySessions.length;
      const alertCount   = daySessions.reduce((s, t) => s + (parseInt(t.dataset.alertCount) || 0), 0);
      const plural = sessionCount === 1 ? "сессия" : sessionCount <= 4 ? "сессии" : "сессий";
      const alertBadge = alertCount > 0
        ? `<span class="audit-alert-badge audit-day-alert-badge" title="Подозрительные события в этот день">⚠ ${alertCount}</span>`
        : "";

      const dayTbody = document.createElement("tbody");
      dayTbody.className = "audit-day-hdr-tbody";
      dayTbody.dataset.dayId = dayId;
      dayTbody.innerHTML =
        `<tr class="audit-day-hdr"><td colspan="5" class="audit-day-hdr-cell">` +
        `<div class="audit-day-hdr-inner">` +
        `<span class="audit-day-chevron" aria-hidden="true"></span>` +
        `<span class="audit-day-date">${dayId}</span>` +
        `<span class="audit-day-sep">·</span>` +
        `<span class="audit-day-count">${sessionCount} ${plural}</span>` +
        alertBadge +
        `</div></td></tr>`;

      tb.parentNode.insertBefore(dayTbody, tb);
      allDayBodies.push(dayTbody);
    });
  }

  // ─────────────────────────────────────────────────────────────────────────

  function applyFilters() {
    const q    = getSearch();
    const src  = activeSrc;
    const user = userSelect?.value || "";

    let visible = 0;
    for (const row of allRows) {
      const match =
        (!src       || row.dataset.src  === src)  &&
        (!user      || row.dataset.user === user) &&
        (!q         || (row.dataset.text || "").includes(q)) &&
        (!alertOnly || row.dataset.alert === "true");
      row.dataset.filterHidden = match ? "0" : "1";
      const sessionCollapsed = collapsedSessions.has(row.dataset.sessionId);
      row.hidden = !match || sessionCollapsed;
      if (match) visible++;
    }

    // Session tbodies
    allBodies.forEach(tb => {
      const dayCollapsed = collapsedDays.has(tb.dataset.dayId);
      const bodyRows     = tb.querySelectorAll("tr.audit-action-row");
      const anyPass      = Array.from(bodyRows).some(r => r.dataset.filterHidden === "0");
      tb.hidden = dayCollapsed;
      const hdr = tb.querySelector(".audit-session-hdr");
      if (hdr) hdr.hidden = !anyPass || dayCollapsed;
    });

    // Day header tbodies
    allDayBodies.forEach(db => {
      const dayId      = db.dataset.dayId;
      const daySessions = allBodies.filter(tb => tb.dataset.dayId === dayId);
      const anyPass    = daySessions.some(tb =>
        Array.from(tb.querySelectorAll("tr.audit-action-row")).some(r => r.dataset.filterHidden === "0")
      );
      db.hidden = !anyPass;
      db.classList.toggle("is-collapsed", collapsedDays.has(dayId));
    });

    const isFiltered = !!(q || src || user || alertOnly);
    if (countBadge) {
      countBadge.innerHTML = isFiltered
        ? `<strong>${visible}</strong> из ${total}`
        : `${total} записей`;
    }

    const showEmpty = visible === 0 && isFiltered;
    if (emptyState) emptyState.hidden = !showEmpty;
    if (table)      table.style.display = showEmpty ? "none" : "";
    if (clearBtn)   clearBtn.style.opacity = isFiltered ? "1" : "0.4";
  }

  function clearFilters() {
    if (searchEl)   searchEl.value = "";
    activeSrc = "";
    alertOnly = false;
    if (userSelect) userSelect.value = "";
    sourcePills?.querySelectorAll(".audit-pill").forEach((p, i) =>
      p.classList.toggle("audit-pill--active", i === 0)
    );
    if (alertToggle) {
      alertToggle.dataset.active = "false";
      alertToggle.classList.remove("audit-pill--active");
    }
    applyFilters();
  }

  // ── Click handler: day header + session header ──
  table.addEventListener("click", e => {
    const dayHdrRow = e.target.closest(".audit-day-hdr");
    if (dayHdrRow) {
      const dayBody = dayHdrRow.closest("tbody.audit-day-hdr-tbody");
      const dayId   = dayBody?.dataset.dayId;
      if (!dayId) return;
      if (collapsedDays.has(dayId)) collapsedDays.delete(dayId);
      else collapsedDays.add(dayId);
      applyFilters();
      return;
    }

    const sessionHdrRow = e.target.closest(".audit-session-hdr");
    if (!sessionHdrRow) return;

    const tbody     = sessionHdrRow.closest("tbody.audit-session-tbody");
    const sessionId = tbody?.dataset.sessionId;
    if (!sessionId) return;

    // Block session toggle when its day is collapsed
    if (collapsedDays.has(tbody.dataset.dayId)) return;

    const wasCollapsed = collapsedSessions.has(sessionId);
    if (wasCollapsed) {
      collapsedSessions.delete(sessionId);
      tbody.classList.remove("is-collapsed");
    } else {
      collapsedSessions.add(sessionId);
      tbody.classList.add("is-collapsed");
    }

    tbody.querySelectorAll("tr.audit-action-row").forEach(row => {
      row.hidden = row.dataset.filterHidden === "1" || !wasCollapsed;
    });
  });

  // ── Source pill clicks ──
  sourcePills?.addEventListener("click", e => {
    const pill = e.target.closest(".audit-pill");
    if (!pill) return;
    activeSrc = pill.dataset.src ?? "";
    sourcePills.querySelectorAll(".audit-pill").forEach(p =>
      p.classList.toggle("audit-pill--active", p === pill)
    );
    applyFilters();
  });

  searchEl?.addEventListener("input", applyFilters);
  userSelect?.addEventListener("change", applyFilters);
  clearBtn?.addEventListener("click", clearFilters);
  emptyClearBtn?.addEventListener("click", clearFilters);
  alertToggle?.addEventListener("click", () => {
    alertOnly = !alertOnly;
    alertToggle.dataset.active = alertOnly ? "true" : "false";
    alertToggle.classList.toggle("audit-pill--active", alertOnly);
    applyFilters();
  });

  // ── Convert UTC to local time ──
  (function convertTimesToLocal() {
    const pad = n => String(n).padStart(2, "0");

    table.querySelectorAll(".audit-td-time[data-utc]").forEach(td => {
      const iso = td.dataset.utc;
      if (!iso) return;
      const d = new Date(iso.includes("T") ? iso + "Z" : iso);
      if (isNaN(d)) return;
      const dateEl  = td.querySelector(".audit-time-date");
      const clockEl = td.querySelector(".audit-time-clock");
      if (dateEl)  dateEl.textContent  = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
      if (clockEl) clockEl.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    });

    table.querySelectorAll(".audit-session-timerange[data-session-start]").forEach(el => {
      const startIso = el.dataset.sessionStart;
      const endIso   = el.dataset.sessionEnd;
      if (!startIso || !endIso) return;
      const s = new Date(startIso + "Z");
      const e = new Date(endIso   + "Z");
      if (isNaN(s) || isNaN(e)) return;

      const fmtDate    = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
      const fmtTime    = d => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
      const fmtTimeSec = d => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

      const sameDay  = fmtDate(s) === fmtDate(e);
      const sameTime = s.getTime() === e.getTime();

      if (sameTime) {
        el.textContent = `${fmtDate(s)}, ${fmtTimeSec(s)}`;
      } else if (sameDay) {
        el.textContent = `${fmtDate(s)}, ${fmtTime(s)} — ${fmtTime(e)}`;
      } else {
        el.textContent = `${fmtDate(s)} ${fmtTime(s)} — ${fmtDate(e)} ${fmtTime(e)}`;
      }
    });

    const header = document.getElementById("auditTimeHeader");
    if (header) header.textContent = "Время (местное)";
  })();

  // Build day groups from local dates, collapse all days, then run initial filter pass
  buildDayGroups();
  allDayBodies.forEach(db => collapsedDays.add(db.dataset.dayId));
  applyFilters();
})();
