(function () {
  const section = document.querySelector(".maintenance-section--backup");
  if (!section) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const tableBody = document.getElementById("maintenanceBackupTableBody");
  const listHost = document.getElementById("maintenanceBackupListHost");
  const emptyState = document.getElementById("maintenanceBackupEmpty");
  const archivesTitle = section.querySelector(".maintenance-backup-block--archives .maintenance-backup-block__title");

  const clientTimezone = (() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (_err) {
      return "";
    }
  })();

  const backupDateFormatter = (() => {
    try {
      return new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short",
      });
    } catch (_err) {
      return null;
    }
  })();

  const notify = (message, type) => {
    if (typeof window.showNotification === "function") {
      window.showNotification(message, type || "info");
      return;
    }
    window.alert(message);
  };

  const askBackupConfirm = async ({ message, confirmText = "OK", confirmVariant = "ok" }) => {
    if (typeof window.showUserActionConfirm === "function") {
      return window.showUserActionConfirm({
        appearance: "native",
        message,
        confirmText,
        cancelText: "Отмена",
        confirmVariant,
      });
    }
    return window.confirm(message);
  };

  const escapeHtml = (value) => {
    const node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  };

  const formatBackupDate = (raw) => {
    const text = String(raw || "").trim();
    if (!text) return "—";
    const parsed = Date.parse(text);
    if (Number.isNaN(parsed) || !backupDateFormatter) {
      return text;
    }
    try {
      return backupDateFormatter.format(new Date(parsed));
    } catch (_err) {
      return text;
    }
  };

  const updateArchivesTitle = (count) => {
    if (!archivesTitle) return;
    const n = Math.max(0, Number(count) || 0);
    archivesTitle.textContent = `Сохранённые архивы (${n} / 5)`;
  };

  const renderContentCell = (item) => {
    const parts = [];
    if (item.content_description) {
      parts.push(`<p class="maintenance-backup-content__title">${escapeHtml(item.content_description)}</p>`);
    }
    const components = item.components || [];
    const labels = item.component_labels || [];
    if (components.length) {
      const badges = components
        .map((comp, index) => {
          const title = labels[index] || comp;
          return `<span class="maintenance-badge maintenance-badge--${escapeHtml(comp)}" role="listitem" title="${escapeHtml(title)}">${escapeHtml(comp)}</span>`;
        })
        .join("");
      parts.push(`<div class="maintenance-backup-content__badges" role="list">${badges}</div>`);
      if (labels.length) {
        const listItems = labels.map((label) => `<li>${escapeHtml(label)}</li>`).join("");
        parts.push(`<ul class="maintenance-backup-content__list">${listItems}</ul>`);
      }
    } else {
      parts.push(
        '<p class="maintenance-backup-content__title maintenance-backup-content__title--muted">Состав не определён</p>'
      );
    }
    if (item.content_detail) {
      parts.push(`<p class="maintenance-backup-table__meta">${escapeHtml(item.content_detail)}</p>`);
    } else if (item.summary && item.summary !== item.content_description) {
      parts.push(`<p class="maintenance-backup-table__meta">${escapeHtml(item.summary)}</p>`);
    }
    return `<div class="maintenance-backup-content">${parts.join("")}</div>`;
  };

  const renderBackupRow = (item) => {
    const fileName = item.file_name || "";
    return `
      <tr data-backup-file="${escapeHtml(fileName)}">
        <td class="maintenance-backup-table__file">${escapeHtml(fileName)}</td>
        <td>${escapeHtml(formatBackupDate(item.created_at))}</td>
        <td>${escapeHtml(item.size_human || "")}</td>
        <td class="maintenance-backup-table__content">${renderContentCell(item)}</td>
        <td class="maintenance-backup-table__actions">
          <div class="maintenance-backup-actions">
            <button type="button" class="button maintenance-backup-btn maintenance-backup-btn--restore js-backup-restore"
              data-file-name="${escapeHtml(fileName)}">Восстановить</button>
            <button type="button" class="button maintenance-backup-btn maintenance-backup-btn--delete js-backup-delete"
              data-file-name="${escapeHtml(fileName)}">Удалить</button>
          </div>
        </td>
      </tr>`;
  };

  const toggleListVisibility = (hasItems) => {
    if (listHost) listHost.hidden = !hasItems;
    if (emptyState) emptyState.hidden = hasItems;
  };

  const latestBackupNeedsMetadataRetry = (backups) => {
    const items = Array.isArray(backups) ? backups : [];
    if (!items.length) return false;
    const latest = items[0];
    const hasComponents = Array.isArray(latest.components) && latest.components.length > 0;
    const hasItemsCount = Number(latest.items_count) > 0;
    const hasSummary = String(latest.summary || "").trim().length > 0;
    return !hasComponents && !hasItemsCount && !hasSummary;
  };

  const renderBackupTable = (backups) => {
    if (!tableBody) return;
    const items = Array.isArray(backups) ? backups : [];
    tableBody.innerHTML = items.map(renderBackupRow).join("");
    toggleListVisibility(items.length > 0);
    updateArchivesTitle(items.length);
  };

  const setBusy = (element, busy) => {
    if (!element) return;
    element.disabled = !!busy;
    element.setAttribute("aria-busy", busy ? "true" : "false");
    element.classList.toggle("is-busy", !!busy);
  };

  const apiFetch = async (url, options = {}) => {
    const headers = Object.assign(
      {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfToken,
      },
      options.headers || {}
    );
    if (clientTimezone) {
      headers["X-Client-Timezone"] = clientTimezone;
    }
    const response = await fetch(url, Object.assign({}, options, { headers }));
    let data = {};
    try {
      data = await response.json();
    } catch (_err) {
      data = {};
    }
    if (!response.ok && data.success !== false) {
      data.success = false;
      data.message = data.message || `Ошибка HTTP ${response.status}`;
    }
    return data;
  };

  const refreshBackupList = async () => {
    const data = await apiFetch("/api/backups", { method: "GET" });
    if (!data.success) {
      notify(data.message || "Не удалось обновить список бэкапов", "error");
      return false;
    }
    renderBackupTable(data.backups);
    return data.backups;
  };

  const refreshBackupListWithRetry = async () => {
    let backups = await refreshBackupList();
    if (backups && latestBackupNeedsMetadataRetry(backups)) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      backups = await refreshBackupList();
    }
    return backups;
  };

  const waitForBackupTaskAndRefresh = async (data, options = {}) => {
    const timeoutMs = options.timeoutMs || 900000;
    if (!data?.task_id || typeof pollBackgroundTask !== "function") {
      await refreshBackupListWithRetry();
      return;
    }
    try {
      const task = await pollBackgroundTask(data.task_id, { timeoutMs });
      if (task.status === "completed") {
        await refreshBackupListWithRetry();
        return;
      }
      notify(task.error || task.message || "Фоновая задача завершилась с ошибкой", "error");
    } catch (err) {
      notify(err.message || "Ошибка ожидания фоновой задачи", "error");
    }
  };

  const handleApiMessages = (data, fallbackType) => {
    const messages = Array.isArray(data.messages) ? data.messages : [];
    if (messages.length) {
      messages.forEach((item) => notify(item.message, item.category || fallbackType));
      return;
    }
    if (data.message) {
      notify(data.message, data.category || fallbackType);
    }
  };

  section.querySelector(".js-backup-settings-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitBtn = form.querySelector('button[type="submit"]');
    setBusy(submitBtn, true);
    try {
      const data = await apiFetch("/api/backups/settings", {
        method: "POST",
        body: new FormData(form),
      });
      handleApiMessages(data, data.success ? "success" : "error");
    } catch (_err) {
      notify("Ошибка сети при сохранении настроек", "error");
    } finally {
      setBusy(submitBtn, false);
    }
  });

  section.querySelector(".js-backup-send-tg")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    if (btn.disabled) return;
    const confirmed = await askBackupConfirm({
      message:
        "Создать бэкапы панели и AntiZapret (если включён) и отправить архивы выбранным админам в Telegram?",
    });
    if (!confirmed) {
      return;
    }
    setBusy(btn, true);
    try {
      const data = await apiFetch("/api/backups/test-telegram", { method: "POST" });
      handleApiMessages(data, data.success ? "info" : "error");
      if (data.success) {
        await waitForBackupTaskAndRefresh(data);
      }
    } catch (_err) {
      notify("Ошибка сети при создании бэкапа и отправке в Telegram", "error");
    } finally {
      setBusy(btn, false);
    }
  });

  section.querySelector(".js-backup-create-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitBtn = form.querySelector('button[type="submit"]');
    setBusy(submitBtn, true);
    try {
      const data = await apiFetch("/api/backups/create", { method: "POST" });
      handleApiMessages(data, "info");
      if (data.success) {
        await waitForBackupTaskAndRefresh(data, { timeoutMs: 600000 });
      }
    } catch (_err) {
      notify("Ошибка сети при создании бэкапа", "error");
    } finally {
      setBusy(submitBtn, false);
    }
  });

  section.addEventListener("click", async (event) => {
    const restoreBtn = event.target.closest(".js-backup-restore");
    const deleteBtn = event.target.closest(".js-backup-delete");
    if (!restoreBtn && !deleteBtn) return;

    const fileName = (restoreBtn || deleteBtn).dataset.fileName || "";
    if (!fileName) return;

    if (restoreBtn) {
      const restoreConfirmed = await askBackupConfirm({
        message: `Восстановить из бэкапа ${fileName}? Сервис будет перезапущен.`,
      });
      if (!restoreConfirmed) {
        return;
      }
      setBusy(restoreBtn, true);
      try {
        const data = await apiFetch("/api/backups/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file_name: fileName }),
        });
        handleApiMessages(data, "warning");
      } catch (_err) {
        notify("Ошибка сети при восстановлении", "error");
      } finally {
        setBusy(restoreBtn, false);
      }
      return;
    }

    const deleteConfirmed = await askBackupConfirm({
      message: `Удалить бэкап ${fileName}? Это действие нельзя отменить.`,
      confirmVariant: "danger",
    });
    if (!deleteConfirmed) {
      return;
    }
    setBusy(deleteBtn, true);
    try {
      const data = await apiFetch("/api/backups/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_name: fileName }),
      });
      handleApiMessages(data, data.success ? "success" : "error");
      if (data.success && Array.isArray(data.backups)) {
        renderBackupTable(data.backups);
      } else if (data.success) {
        await refreshBackupList();
      }
    } catch (_err) {
      notify("Ошибка сети при удалении", "error");
    } finally {
      setBusy(deleteBtn, false);
    }
  });
})();
