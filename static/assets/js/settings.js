document.addEventListener("DOMContentLoaded", function () {
  const hideNotificationWithFx = (element, delayMs = 0) => {
    if (!element) return;
    setTimeout(() => {
      element.classList.add("notification-exit");
      setTimeout(() => {
        element.classList.remove("notification-exit");
        element.style.display = "none";
      }, 180);
    }, delayMs);
  };

  const pollBackgroundTask = async (taskId, options = {}) => {
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
  };

  // Инициализация меню
  const initMenu = () => {
    const menuItems = document.querySelectorAll(".menu-item");
    const contentTabs = document.querySelectorAll(".content-tab");

    const syncMainNavSettingsLinks = (tabId) => {
      const links = document.querySelectorAll(".nav-sublink[data-settings-tab]");
      if (!links.length) return;

      let hasActive = false;
      links.forEach((link) => {
        const isActive = link.getAttribute("data-settings-tab") === tabId;
        link.classList.toggle("is-active", isActive);
        if (isActive) hasActive = true;
      });

      if (!hasActive && links.length) {
        links[0].classList.add("is-active");
      }
    };

    const activateTab = (tabId) => {
      contentTabs.forEach((tab) => {
        tab.classList.remove("active");
        if (tab.id === tabId) tab.classList.add("active");
      });
      syncMainNavSettingsLinks(tabId);
    };

    menuItems.forEach((item) => {
      item.addEventListener("click", function () {
        menuItems.forEach((i) => i.classList.remove("active"));
        this.classList.add("active");
        const tabId = this.getAttribute("data-tab");

        if (tabId) {
          activateTab(tabId);
        }

        if (tabId === "antizapret-config") {
          loadAntizapretSettings();
        }
      });

      if (window.location.hash === `#${item.getAttribute("data-tab")}`) {
        item.click();
      }
    });

    if (menuItems.length > 0 && !window.location.hash) {
      const activeMenuItem = document.querySelector(".menu-item.active");
      (activeMenuItem || menuItems[0]).click();
    }

    window.addEventListener("hashchange", () => {
      const tabId = (window.location.hash || "").replace(/^#/, "").trim();
      if (!tabId) return;

      const hashMenuItem = document.querySelector(`.menu-item[data-tab='${tabId}']`);
      if (hashMenuItem) {
        hashMenuItem.click();
        return;
      }

      syncMainNavSettingsLinks(tabId);
    });
  };

  const createUserActionConfirm = () => {
    const modal = document.getElementById("userActionModal");
    const titleEl = document.getElementById("userActionModalTitle");
    const textEl = document.getElementById("userActionModalText");
    const confirmBtn = document.getElementById("userActionModalConfirm");

    if (!modal || !titleEl || !textEl || !confirmBtn) {
      return async ({ message = "Подтвердить действие?" } = {}) => window.confirm(message);
    }

    const closeTargets = modal.querySelectorAll("[data-user-action-close]");
    const closeModal = () => {
      modal.classList.remove("is-open");
      document.body.classList.remove("user-action-modal-open");
      setTimeout(() => {
        modal.setAttribute("hidden", "");
      }, 180);
    };

    return ({
      title = "Подтвердите действие",
      message = "Изменение будет применено сразу.",
      confirmText = "Подтвердить",
      confirmVariant = "danger",
    } = {}) => {
      titleEl.textContent = title;
      textEl.textContent = message;
      confirmBtn.textContent = confirmText;
      confirmBtn.classList.toggle("is-danger", confirmVariant === "danger");

      modal.removeAttribute("hidden");
      requestAnimationFrame(() => {
        modal.classList.add("is-open");
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
          }
        };

        confirmBtn.addEventListener("click", onConfirm);
        closeTargets.forEach((target) => {
          target.addEventListener("click", onCancel);
        });
        document.addEventListener("keydown", onEsc);
      });
    };
  };

  const initUserActionPopups = () => {
    const askConfirm = createUserActionConfirm();

    const bindConfirm = (selector, getOptions) => {
      document.querySelectorAll(selector).forEach((form) => {
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const confirmed = await askConfirm(getOptions(form));
          if (confirmed) {
            form.submit();
          }
        });
      });
    };

    bindConfirm("form[data-user-action='delete-user']", (form) => {
      const username = form.querySelector("input[name='delete_username']")?.value.trim() || "этого пользователя";
      return {
        title: "Удалить пользователя?",
        message: `Пользователь «${username}» будет удален без возможности восстановления.`,
        confirmText: "Удалить",
        confirmVariant: "danger",
      };
    });

    bindConfirm("form[data-user-action='change-role']", (form) => {
      const username = form.querySelector("input[name='change_role_username']")?.value || "пользователя";
      const role = form.querySelector("select[name='new_role']")?.value || "новую роль";
      return {
        title: "Изменить роль?",
        message: `Для «${username}» будет установлена роль «${role}».`,
        confirmText: "Изменить",
        confirmVariant: "primary",
      };
    });

    bindConfirm("form[data-user-action='change-password']", (form) => {
      const username = form.querySelector("input[name='change_password_username']")?.value || "пользователя";
      return {
        title: "Сменить пароль?",
        message: `Пароль пользователя «${username}» будет обновлен сразу после подтверждения.`,
        confirmText: "Сменить пароль",
        confirmVariant: "danger",
      };
    });
  };

  // Загрузка текущих настроек Antizapret
  let antizapretSchema = null;

  async function loadSchema() {
    try {
      const r = await fetch("/antizapret_settings_schema");
      antizapretSchema = await r.json();
    } catch (e) {
      console.error("Не удалось загрузить схему", e);
    }
  }

  async function loadAntizapretSettings() {
    if (!antizapretSchema) await loadSchema();
    if (!antizapretSchema) return;

    const data = await (await fetch("/get_antizapret_settings")).json();

    antizapretSchema.forEach(f => {
      const el = document.getElementById(f.html_id);
      if (!el) return;
      const v = data[f.key];
      if (f.type === "flag") {
        el.checked = v === "y";
      } else {
        el.value = v || "";
      }
    });
  }

  async function saveAntizapretSettings() {
    if (!antizapretSchema) await loadSchema();
    if (!antizapretSchema) return;

    const settings = {};
    antizapretSchema.forEach(f => {
      const el = document.getElementById(f.html_id);
      if (!el) return;
      settings[f.key] = f.type === "flag"
        ? (el.checked ? "y" : "n")
        : el.value.trim();
    });

    const statusElement = document.getElementById("config-status");
    statusElement.textContent = "Сохранение настроек...";
    statusElement.className = "notification notification-info";
    statusElement.style.display = "block";

    try {
      const saveResponse = await fetch("/update_antizapret_settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector('input[name="csrf_token"]')
            .value,
        },
        body: JSON.stringify(settings),
      });

      const saveData = await saveResponse.json();

      if (!saveData.success) {
        throw new Error(saveData.message || "Ошибка сохранения настроек");
      }

      statusElement.textContent = "Применение изменений...";

      const applyResponse = await fetch("/run-doall", {
        method: "POST",
        headers: {
          "X-CSRFToken": document.querySelector('input[name="csrf_token"]')
            .value,
        },
      });

      const applyData = await applyResponse.json();

      if (applyData.queued && applyData.task_id) {
        statusElement.textContent = "Применение запущено в фоне...";
        const task = await pollBackgroundTask(applyData.task_id, { timeoutMs: 900000 });
        statusElement.textContent = task.message || "Настройки успешно сохранены и применены!";
        statusElement.className = "notification notification-success";
      } else if (applyData.success) {
        statusElement.textContent = "Настройки успешно сохранены и применены!";
        statusElement.className = "notification notification-success";
      } else {
        statusElement.textContent =
          "Настройки сохранены, но ошибка при применении";
        statusElement.className = "notification notification-warning";
      }
    } catch (error) {
      statusElement.textContent = `Ошибка: ${error.message}`;
      statusElement.className = "notification notification-error";
      console.error("Error:", error);
    } finally {
      hideNotificationWithFx(statusElement, 5000);
    }
  };

  // Показать уведомление
  const showNotification = (message, type) => {
    const notification = document.createElement("div");
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
      notification.classList.add("notification-exit");
    }, 2800);

    setTimeout(() => {
      notification.remove();
    }, 3000);
  };

  // Обработчик изменения размера экрана
  const handleResize = () => {
    if (window.innerWidth >= 992) {
      document.querySelector(".settings-content").style.maxHeight = "";
    }
  };

  // Обработчик ориентации
  const handleOrientationChange = () => {
    setTimeout(() => {
      const activeTab = document.querySelector(".content-tab.active");
      if (activeTab) {
        activeTab.scrollIntoView({
          behavior: "auto",
          block: "start",
        });
      }
    }, 300);
  };

  const initMiniAppLinkCopy = () => {
    const input = document.getElementById("tg-mini-link-input");
    const button = document.getElementById("copy-tg-mini-link-btn");
    const status = document.getElementById("copy-tg-mini-link-status");

    if (!input || !button || !status) {
      return;
    }

    const setStatus = (text, isError = false) => {
      status.textContent = text;
      status.classList.toggle("miniapp-link-status-error", Boolean(isError));
    };

    const fallbackCopy = (text) => {
      input.removeAttribute("readonly");
      input.focus();
      input.select();
      input.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      input.setAttribute("readonly", "readonly");
      return ok;
    };

    button.addEventListener("click", async () => {
      const text = (input.value || "").trim();
      if (!text) {
        setStatus("Ссылка пуста", true);
        return;
      }

      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else if (!fallbackCopy(text)) {
          throw new Error("clipboard_unavailable");
        }

        setStatus("Ссылка скопирована");
      } catch {
        setStatus("Не удалось скопировать автоматически. Скопируйте ссылку вручную.", true);
        input.focus();
        input.select();
      }
    });
  };

  const initSettingsRangeControls = () => {
    const formatSecondsHuman = (rawSeconds) => {
      const seconds = Number(rawSeconds);
      if (!Number.isFinite(seconds) || seconds < 0) {
        return "";
      }

      if (seconds < 60) {
        return `${seconds} сек`;
      }

      if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const restSeconds = seconds % 60;
        return restSeconds > 0 ? `${mins} мин ${restSeconds} сек` : `${mins} мин`;
      }

      if (seconds < 86400) {
        const hours = Math.floor(seconds / 3600);
        const restMins = Math.floor((seconds % 3600) / 60);
        return restMins > 0 ? `${hours} ч ${restMins} мин` : `${hours} ч`;
      }

      const days = Math.floor(seconds / 86400);
      const restHours = Math.floor((seconds % 86400) / 3600);
      return restHours > 0 ? `${days} д ${restHours} ч` : `${days} д`;
    };

    const controls = document.querySelectorAll("input[type='range'][data-slider-target]");
    controls.forEach((slider) => {
      const targetId = slider.getAttribute("data-slider-target");
      if (!targetId) return;

      const input = document.getElementById(targetId);
      const valueBadge = document.querySelector(`[data-slider-value-for='${targetId}']`);
      if (!input) return;

      const unit = slider.getAttribute("data-unit") || "";
      const humanize = slider.getAttribute("data-humanize") || "";
      const min = Number(slider.min);
      const max = Number(slider.max);

      const clamp = (raw) => {
        const numeric = Number(raw);
        if (!Number.isFinite(numeric)) {
          return Number.isFinite(min) ? min : 0;
        }

        if (Number.isFinite(min) && numeric < min) {
          return min;
        }
        if (Number.isFinite(max) && numeric > max) {
          return max;
        }
        return numeric;
      };

      const renderLabel = (rawValue) => {
        const numericValue = clamp(rawValue);
        const base = unit ? `${numericValue} ${unit}` : String(numericValue);

        if (humanize === "seconds") {
          const human = formatSecondsHuman(numericValue);
          if (human && human !== base) {
            return `${base} (${human})`;
          }
        }

        return base;
      };

      const applyValue = (rawValue, source) => {
        const normalized = clamp(rawValue);
        slider.value = String(normalized);
        input.value = String(normalized);

        if (valueBadge) {
          valueBadge.textContent = renderLabel(normalized);
        }

        if (source === "input") {
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      };

      const initialValue = (input.value || "").trim() || slider.value;
      applyValue(initialValue, "init");

      slider.addEventListener("input", () => {
        applyValue(slider.value, "slider");
      });

      slider.addEventListener("change", () => {
        applyValue(slider.value, "slider");
      });

      input.addEventListener("input", () => {
        const raw = (input.value || "").trim();
        if (!raw) return;
        applyValue(raw, "input");
      });

      input.addEventListener("change", () => {
        const raw = (input.value || "").trim();
        if (!raw) {
          applyValue(slider.value, "input");
          return;
        }
        applyValue(raw, "input");
      });
    });
  };

  // === ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ СИСТЕМЫ ===
  const updateSystem = async () => {
    const statusElement = document.getElementById("update-status");
    const button = document.getElementById("update-system");

    statusElement.textContent = "Обновление системы...";
    statusElement.className = "notification notification-info";
    statusElement.style.display = "block";

    try {
      const response = await fetch("/update_system", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken":
            document.querySelector('input[name="csrf_token"]')?.value || "",
        },
      });

      const data = await response.json();

      if (data.queued && data.task_id) {
        statusElement.textContent = data.message || "Обновление запущено в фоне...";
        const task = await pollBackgroundTask(data.task_id, { timeoutMs: 1200000 });
        statusElement.textContent = task.message || "Обновление завершено!";
        statusElement.className = "notification notification-success";
      } else if (data.success) {
        statusElement.textContent = data.message || "Обновление завершено!";
        statusElement.className = "notification notification-success";
      } else {
        statusElement.textContent = data.message || "Ошибка обновления";
        statusElement.className = "notification notification-error";
      }
    } catch (error) {
      statusElement.textContent = "Ошибка соединения";
      statusElement.className = "notification notification-error";
    } finally {
      hideNotificationWithFx(statusElement, 10000);
    }
  };

  // === УМНАЯ КНОПКА: ПРОВЕРКА ОБНОВЛЕНИЙ ===
  const updateButton = document.getElementById("update-system");
  const checkForUpdates = async () => {
    try {
      const response = await fetch("/check_updates");
      const data = await response.json();

      if (data.update_available) {
        updateButton.textContent = "Доступно обновление!";
        updateButton.style.background = "var(--theme-update-available, #e74c3c)";
        updateButton.disabled = false;
      } else {
        updateButton.textContent = "У вас последняя версия";
        updateButton.style.background = "var(--theme-update-latest, #27ae60)";
        updateButton.disabled = true;
      }
    } catch {
      updateButton.textContent = "Проверка недоступна";
      updateButton.style.background = "var(--theme-update-unavailable, #95a5a6)";
      updateButton.disabled = true;
    }
  };

  updateButton.addEventListener("click", () => {
    if (updateButton.disabled) return;
    if (
      confirm(
        "ВНИМАНИЕ!\nВсе ваши изменения будут удалены навсегда.\nПродолжить обновление?"
      )
    ) {
      updateSystem();
    }
  });

  // Запуск
  initMenu();
  initUserActionPopups();
  document
    .getElementById("save-config")
    ?.addEventListener("click", saveAntizapretSettings);
  document.querySelectorAll(".save-config-btn").forEach(btn => {
    btn.addEventListener("click", saveAntizapretSettings);
  });
  window.addEventListener("resize", handleResize);
  window.addEventListener("orientationchange", handleOrientationChange);
  initMiniAppLinkCopy();
  initSettingsRangeControls();

  if (history.pushState) {
    document.querySelectorAll(".menu-item[data-tab]").forEach((link) => {
      link.addEventListener("click", () => {
        history.pushState(null, null, "#" + link.getAttribute("data-tab"));
      });
    });
  }

  // Проверяем обновления при загрузке
  checkForUpdates();
});
// Обработка перезапуска службы
document
  .getElementById("restartServiceBtn")
  ?.addEventListener("click", function () {
    if (
      confirm(
        "Вы уверены? Служба будет перезапущена на 5-10 секунд.\n\nВо время перезапуска страница будет заблокирована."
      )
    ) {
      startRestartProcess();
    }
  });

function startRestartProcess() {
  const overlay = document.getElementById("loadingOverlay");
  const countdownElement = document.getElementById("countdownTimer");
  const restartForm = document.getElementById("restartForm");

  // Показываем оверлей
  overlay.style.display = "flex";
  requestAnimationFrame(() => {
    overlay.classList.add("is-open");
  });

  let countdown = 5;

  // Запускаем обратный отсчет
  const countdownInterval = setInterval(() => {
    countdown--;
    countdownElement.textContent = countdown;

    if (countdown <= 0) {
      clearInterval(countdownInterval);

      // Меняем сообщение
      document.querySelector(".loading-title").textContent =
        "⚡ Выполняется перезапуск...";
      document.querySelector(".loading-message").textContent =
        "Выполняется команда перезапуска службы.";
      countdownElement.style.display = "none";

      // Отправляем форму через 1 секунду
      setTimeout(() => {
        restartForm.submit();
      }, 1000);
    }
  }, 1000);

  // Блокируем все действия пользователя
  document.body.style.overflow = "hidden";

  // Показываем анимацию пульсации
  countdownElement.classList.add("pulse");
}

// Заблокировать клавиши во время загрузки
document.addEventListener(
  "keydown",
  function (e) {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay && overlay.style.display === "flex") {
      e.preventDefault();
      return false;
    }
  },
  false
);

// Заблокировать клики по странице во время загрузки
document.addEventListener(
  "click",
  function (e) {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay && overlay.style.display === "flex") {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
  },
  true
);

document.addEventListener('DOMContentLoaded', () => {
  const hamburger = document.getElementById('openSidebar');
  const sidebar = document.getElementById('sidebar');

  if (!hamburger || !sidebar) return;

  // Открытие/закрытие по клику на гамбургер
  hamburger.addEventListener('click', (e) => {
    e.stopPropagation();
    sidebar.classList.toggle('active');
    document.body.classList.toggle('menu-open', sidebar.classList.contains('active'));
  });

  // Закрытие по клику вне меню
  document.addEventListener('click', (e) => {
    if (sidebar.classList.contains('active') &&
      !sidebar.contains(e.target) &&
      !hamburger.contains(e.target)) {
      sidebar.classList.remove('active');
      document.body.classList.remove('menu-open');
    }
  });
});
