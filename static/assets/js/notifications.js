(function () {
  const DURATION = { success: 5000, info: 5000, warning: 5000, error: 10000 };
  const MAX_VISIBLE = 5;
  const EXIT_MS = 200;

  function normalizeType(type) {
    const t = String(type || "info").toLowerCase();
    if (t === "danger") return "error";
    if (t === "ok") return "success";
    if (t === "warn") return "warning";
    if (["error", "success", "warning", "info"].includes(t)) return t;
    return "info";
  }

  function getStack() {
    let stack = document.getElementById("notification-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.id = "notification-stack";
      stack.className = "notification-stack";
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    return stack;
  }

  function dismissToast(toast) {
    if (!toast || toast.dataset.dismissing === "1") return;
    toast.dataset.dismissing = "1";
    clearTimeout(toast._hideTimer);
    clearTimeout(toast._removeTimer);
    toast.classList.add("notification-exit");
    toast._removeTimer = setTimeout(() => {
      toast.remove();
    }, EXIT_MS);
  }

  function trimStack(stack) {
    const items = stack.querySelectorAll(".notification");
    const excess = items.length - MAX_VISIBLE;
    if (excess <= 0) return;
    for (let i = 0; i < excess; i++) {
      dismissToast(items[i]);
    }
  }

  function showNotification(message, type = "success") {
    const text = String(message || "").trim();
    if (!text) return;

    const level = normalizeType(type);
    const stack = getStack();
    const toast = document.createElement("div");
    toast.className = `notification notification-${level}`;
    toast.textContent = text;
    toast.setAttribute("role", level === "error" ? "alert" : "status");
    toast.setAttribute("aria-live", level === "error" ? "assertive" : "polite");
    toast.setAttribute("aria-atomic", "true");

    stack.appendChild(toast);
    trimStack(stack);

    const duration = DURATION[level] ?? DURATION.info;
    toast._hideTimer = setTimeout(() => dismissToast(toast), duration);
  }

  function hideNotificationWithFx(element, delayMs = 0) {
    if (!element) return;
    setTimeout(() => {
      element.classList.add("notification-exit");
      setTimeout(() => {
        element.classList.remove("notification-exit");
        element.hidden = true;
        element.style.display = "none";
        element.textContent = "";
      }, EXIT_MS);
    }, delayMs);
  }

  window.showNotification = showNotification;
  window.hideNotificationWithFx = hideNotificationWithFx;
  window.normalizeNotificationType = normalizeType;
})();
