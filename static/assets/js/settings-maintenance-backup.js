(function () {
  const section = document.querySelector(".maintenance-section--backup");
  if (!section) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const tableBody = document.getElementById("maintenanceBackupTableBody");
  const listHost = document.getElementById("maintenanceBackupListHost");
  const emptyState = document.getElementById("maintenanceBackupEmpty");

  const notify = (message, type) => {
    if (typeof window.showNotification === "function") {
      window.showNotification(message, type || "info");
      return;
    }
    window.alert(message);
  };

  const escapeHtml = (value) => {
    const node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
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
        <td>${escapeHtml(item.created_at || "—")}</td>
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

  const renderBackupTable = (backups) => {
    if (!tableBody) return;
    const items = Array.isArray(backups) ? backups : [];
    tableBody.innerHTML = items.map(renderBackupRow).join("");
    toggleListVisibility(items.length > 0);
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
    return true;
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

  section.querySelector(".js-backup-test-tg")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    if (btn.disabled) return;
    if (
      !window.confirm(
        "Создать бэкапы панели и AntiZapret (если включён) и отправить архивы выбранным админам в Telegram?"
      )
    ) {
      return;
    }
    setBusy(btn, true);
    try {
      const data = await apiFetch("/api/backups/test-telegram", { method: "POST" });
      handleApiMessages(data, data.success ? "info" : "error");
      if (data.success) {
        window.setTimeout(() => {
          refreshBackupList();
        }, 5000);
      }
    } catch (_err) {
      notify("Ошибка сети при тестовом бэкапе", "error");
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
        window.setTimeout(() => {
          refreshBackupList();
        }, 3000);
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
      if (!window.confirm(`Восстановить из бэкапа ${fileName}? Сервис будет перезапущен.`)) {
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

    if (!window.confirm(`Удалить бэкап ${fileName}? Это действие нельзя отменить.`)) {
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
