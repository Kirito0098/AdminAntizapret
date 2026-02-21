document.addEventListener("DOMContentLoaded", function () {
  // Инициализация меню
  const initMenu = () => {
    const menuItems = document.querySelectorAll(".menu-item");
    const contentTabs = document.querySelectorAll(".content-tab");

    const activateTab = (tabId) => {
      contentTabs.forEach((tab) => {
        tab.classList.remove("active");
        if (tab.id === tabId) tab.classList.add("active");
      });
    };

    menuItems.forEach((item) => {
      item.addEventListener("click", function () {
        menuItems.forEach((i) => i.classList.remove("active"));
        this.classList.add("active");
        const tabId = this.getAttribute("data-tab");

        if (tabId === "port-settings") {
          const userTabs = document.querySelectorAll(".subtab-content");
          userTabs.forEach((tab) => tab.classList.remove("active"));
        }

        if (tabId) {
          activateTab(tabId);
        }

        if (tabId === "user-management") {
          const subtabButtons = document.querySelectorAll(".tab-button");
          subtabButtons.forEach((button) => {
            button.classList.remove("active");
          });

          const defaultUserTab = document.querySelector(
            ".tab-button[data-subtab='add-user']"
          );
          if (defaultUserTab) {
            defaultUserTab.classList.add("active");
            const addUserTabContent = document.querySelector("#add-user");
            if (addUserTabContent) {
              addUserTabContent.classList.add("active");
            }
          }
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
      menuItems[0].click();
    }
  };

  // Инициализация вкладок пользователей
  const initUserTabs = () => {
    const tabButtons = document.querySelectorAll(".tab-button");
    const subtabContents = document.querySelectorAll(".subtab-content");

    tabButtons.forEach((button) => {
      button.addEventListener("click", function () {
        tabButtons.forEach((btn) => btn.classList.remove("active"));
        this.classList.add("active");

        const subtabId = this.getAttribute("data-subtab");
        subtabContents.forEach((content) => {
          content.classList.remove("active");
          if (content.id === subtabId) content.classList.add("active");
        });
      });
    });

    if (tabButtons.length > 0) {
      tabButtons[0].click();
    }
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

      if (applyData.success) {
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
      setTimeout(() => {
        statusElement.style.display = "none";
      }, 5000);
    }
  };

  // Показать уведомление
  const showNotification = (message, type) => {
    const notification = document.createElement("div");
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

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

      if (data.success) {
        statusElement.textContent = data.message || "Обновление завершено!";
        statusElement.className = "notification notification-success";
        setTimeout(() => location.reload(), 3000);
      } else {
        statusElement.textContent = data.message || "Ошибка обновления";
        statusElement.className = "notification notification-error";
      }
    } catch (error) {
      statusElement.textContent = "Ошибка соединения";
      statusElement.className = "notification notification-error";
    } finally {
      setTimeout(() => (statusElement.style.display = "none"), 10000);
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
        updateButton.style.background = "#e74c3c";
        updateButton.disabled = false;
      } else {
        updateButton.textContent = "У вас последняя версия";
        updateButton.style.background = "#27ae60";
        updateButton.disabled = true;
      }
    } catch {
      updateButton.textContent = "Проверка недоступна";
      updateButton.style.background = "#95a5a6";
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
  initUserTabs();
  document
    .getElementById("save-config")
    ?.addEventListener("click", saveAntizapretSettings);
  window.addEventListener("resize", handleResize);
  window.addEventListener("orientationchange", handleOrientationChange);

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
