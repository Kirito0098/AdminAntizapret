(function () {
  const TOAST_DURATION = { success: 5000, info: 5000, warning: 5000, error: 10000 };
  const TOAST_MAX_VISIBLE = 5;
  const TOAST_EXIT_MS = 200;

  function normalizeType(type) {
    const value = String(type || "info").toLowerCase();
    if (value === "danger") return "error";
    if (value === "ok") return "success";
    if (value === "warn") return "warning";
    if (["error", "success", "warning", "info"].includes(value)) return value;
    return "info";
  }

  function getToastStack() {
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
    toast._removeTimer = setTimeout(() => toast.remove(), TOAST_EXIT_MS);
  }

  function trimToastStack(stack) {
    const items = stack.querySelectorAll(".notification");
    const excess = items.length - TOAST_MAX_VISIBLE;
    if (excess <= 0) return;
    for (let i = 0; i < excess; i++) {
      dismissToast(items[i]);
    }
  }

  function showNotification(message, type) {
    const text = String(message || "").trim();
    if (!text) return;

    const level = normalizeType(type);
    const stack = getToastStack();
    const toast = document.createElement("div");
    toast.className = `notification notification-${level}`;
    toast.textContent = text;
    toast.setAttribute("role", level === "error" ? "alert" : "status");
    toast.setAttribute("aria-live", level === "error" ? "assertive" : "polite");
    toast.setAttribute("aria-atomic", "true");

    stack.appendChild(toast);
    trimToastStack(stack);

    const duration = TOAST_DURATION[level] ?? TOAST_DURATION.info;
    toast._hideTimer = setTimeout(() => dismissToast(toast), duration);
  }

  function createParticles() {
    const particlesContainer = document.getElementById("particles");
    if (!particlesContainer) return;

    const particleCount = 30;
    for (let i = 0; i < particleCount; i++) {
      const particle = document.createElement("div");
      particle.className = "particle";

      const size = Math.random() * 5 + 2;
      const left = Math.random() * 100;
      const delay = Math.random() * 20;
      const duration = Math.random() * 10 + 20;

      particle.style.width = `${size}px`;
      particle.style.height = `${size}px`;
      particle.style.left = `${left}%`;
      particle.style.animationDelay = `${delay}s`;
      particle.style.animationDuration = `${duration}s`;

      particlesContainer.appendChild(particle);
    }
  }

  function animateIp() {
    const ipElement = document.getElementById("ipDisplay");
    if (!ipElement) return;

    const ip = ipElement.textContent.trim();
    ipElement.textContent = "";

    let i = 0;
    function typeWriter() {
      if (i < ip.length) {
        ipElement.textContent += ip.charAt(i);
        i += 1;
        setTimeout(typeWriter, 50);
      }
    }

    setTimeout(typeWriter, 500);
  }

  function showFlashes() {
    const payloadEl = document.getElementById("blocked-flash-messages");
    if (!payloadEl) return;

    let flashes = [];
    try {
      flashes = JSON.parse(payloadEl.textContent || "[]");
    } catch (_e) {
      flashes = [];
    }

    flashes.forEach((entry, index) => {
      const category = Array.isArray(entry) ? entry[0] : "info";
      const message = Array.isArray(entry) ? entry[1] : String(entry || "");
      if (!message) return;
      setTimeout(() => showNotification(message, normalizeType(category)), index * 150);
    });
  }

  function readConfig() {
    const configEl = document.getElementById("ip-blocked-config");
    if (!configEl) return {};
    try {
      return JSON.parse(configEl.textContent || "{}");
    } catch (_e) {
      return {};
    }
  }

  function startIpBlockedDwellTracking() {
    const config = readConfig();
    if (!config.dwellEnabled) return;

    const pingUrl = config.pingUrl;
    const dwellSeconds = Number(config.dwellSeconds) || 120;
    if (!pingUrl) return;

    const pingIntervalMs = Math.min(30000, Math.max(10000, Math.floor((dwellSeconds * 1000) / 4)));

    const ping = () => {
      fetch(pingUrl, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      })
        .then((response) => {
          if (response.status === 403) {
            window.location.reload();
            return null;
          }
          return response.json();
        })
        .then((payload) => {
          if (!payload || payload.banned) {
            window.location.reload();
          }
        })
        .catch(() => {});
    };

    ping();
    window.setInterval(ping, pingIntervalMs);
  }

  document.addEventListener("DOMContentLoaded", () => {
    createParticles();
    animateIp();
    showFlashes();
    startIpBlockedDwellTracking();
  });
})();
