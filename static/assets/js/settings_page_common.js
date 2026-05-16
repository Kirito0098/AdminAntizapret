/**
 * Shared tab navigation, notifications, and background task polling for
 * /settings and /routing pages.
 */
function hideNotificationWithFx(element, delayMs = 0) {
  if (!element) return;
  setTimeout(() => {
    element.classList.add("notification-exit");
    setTimeout(() => {
      element.classList.remove("notification-exit");
      element.style.display = "none";
    }, 180);
  }, delayMs);
}

async function pollBackgroundTask(taskId, options = {}) {
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
}

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
