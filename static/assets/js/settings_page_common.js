/**
 * Shared tab navigation and background task polling for /settings and /routing.
 * Toast API: notifications.js (window.showNotification, window.hideNotificationWithFx).
 */

function createUserActionConfirm() {
  const modal = document.getElementById("userActionModal");
  const titleEl = document.getElementById("userActionModalTitle");
  const textEl = document.getElementById("userActionModalText");
  const confirmBtn = document.getElementById("userActionModalConfirm");
  const closeBtn = modal?.querySelector(".user-action-modal__close");

  if (!modal || !titleEl || !textEl || !confirmBtn) {
    return async ({ message = "Подтвердить действие?" } = {}) => window.confirm(message);
  }

  const closeTargets = modal.querySelectorAll("[data-user-action-close]");

  const closeModal = () => {
    modal.classList.remove("is-open", "user-action-modal--native");
    document.body.classList.remove("user-action-modal-open");
    if (closeBtn) closeBtn.hidden = false;
    setTimeout(() => {
      modal.setAttribute("hidden", "");
    }, 180);
  };

  const defaultHostTitle = () => {
    const host = String(window.location.hostname || "панели").trim() || "панели";
    return `Подтвердите действие на ${host}`;
  };

  return ({
    title,
    message = "Изменение будет применено сразу.",
    confirmText = "Подтвердить",
    cancelText = "Отмена",
    confirmVariant = "danger",
    appearance = "panel",
  } = {}) => {
    const isNative = appearance === "native";
    titleEl.textContent = title || (isNative ? defaultHostTitle() : "Подтвердите действие");
    textEl.textContent = message;
    confirmBtn.textContent = confirmText;
    closeTargets.forEach((target) => {
      if (target.classList.contains("user-action-modal__btn-cancel")) {
        target.textContent = cancelText;
      }
    });
    confirmBtn.classList.remove("is-danger", "is-primary", "is-ok");
    if (confirmVariant === "danger") {
      confirmBtn.classList.add("is-danger");
    } else if (confirmVariant === "ok" || isNative) {
      confirmBtn.classList.add("is-ok");
    } else {
      confirmBtn.classList.add("is-primary");
    }
    modal.classList.toggle("user-action-modal--native", isNative);
    if (closeBtn) closeBtn.hidden = isNative;

    modal.removeAttribute("hidden");
    requestAnimationFrame(() => {
      modal.classList.add("is-open");
      if (isNative) {
        confirmBtn.focus();
      }
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
        } else if (event.key === "Enter") {
          cleanup(true);
        }
      };

      confirmBtn.addEventListener("click", onConfirm);
      closeTargets.forEach((target) => {
        target.addEventListener("click", onCancel);
      });
      document.addEventListener("keydown", onEsc);
    });
  };
}

let _userActionConfirmFn = null;

function showUserActionConfirm(options) {
  if (!_userActionConfirmFn) {
    _userActionConfirmFn = createUserActionConfirm();
  }
  return _userActionConfirmFn(options);
}

window.showUserActionConfirm = showUserActionConfirm;

window.getCsrfToken = () =>
  document.querySelector('input[name="csrf_token"]')?.value ||
  document.querySelector('meta[name="csrf-token"]')?.content ||
  "";

async function pollBackgroundTask(taskId, options = {}) {
  const intervalMs = options.intervalMs || 3000;
  const timeoutMs = options.timeoutMs || 600000;
  const maxConsecutiveErrors = options.maxConsecutiveErrors ?? 3;
  const startedAt = Date.now();
  let consecutiveErrors = 0;

  while (Date.now() - startedAt < timeoutMs) {
    let response;
    try {
      response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
        cache: "no-store",
      });
    } catch (networkErr) {
      consecutiveErrors++;
      if (consecutiveErrors >= maxConsecutiveErrors) {
        throw new Error(`Ошибка запроса статуса задачи: ${networkErr.message}`);
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      continue;
    }

    if (!response.ok) {
      if (response.status >= 500) {
        consecutiveErrors++;
        if (consecutiveErrors >= maxConsecutiveErrors) {
          throw new Error(`Ошибка запроса статуса задачи (HTTP ${response.status})`);
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
        continue;
      }
      throw new Error(`Ошибка запроса статуса задачи (HTTP ${response.status})`);
    }

    consecutiveErrors = 0;
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
}

window.pollBackgroundTask = pollBackgroundTask;

function initContentTabs() {
  const navLinks = document.querySelectorAll(".nav-sublink[data-settings-tab]");
  const contentTabs = document.querySelectorAll(".content-tab");

  if (!contentTabs.length) return;

  const syncNavLinks = (tabId) => {
    navLinks.forEach((link) => {
      link.classList.toggle("is-active", link.getAttribute("data-settings-tab") === tabId);
    });
  };

  const activateTab = (tabId) => {
    contentTabs.forEach((tab) => {
      tab.classList.remove("active");
      if (tab.id === tabId) tab.classList.add("active");
    });
    syncNavLinks(tabId);
    document.body.setAttribute("data-active-settings-tab", tabId);
    window.dispatchEvent(new CustomEvent("settings:tab-changed", { detail: { tabId } }));
  };

  const resolveTabFromHash = () => {
    const tabId = (window.location.hash || "").replace(/^#/, "").trim();
    return tabId && document.getElementById(tabId)?.classList.contains("content-tab") ? tabId : "";
  };

  window.addEventListener("hashchange", () => {
    const tabId = resolveTabFromHash();
    if (!tabId) return;
    activateTab(tabId);
    if (tabId === "antizapret-config") window.loadAntizapretSettings?.();
  });

  const initialTabId = resolveTabFromHash() || contentTabs[0]?.id || "";
  if (initialTabId) {
    activateTab(initialTabId);
    if (initialTabId === "antizapret-config") window.loadAntizapretSettings?.();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initContentTabs();
});
