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

        // Загружаем настройки при открытии вкладки Antizapret
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
  const loadAntizapretSettings = () => {
    fetch("/get_antizapret_settings")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();
      })
      .then((data) => {
        document.getElementById("route-all-toggle").checked =
          data.route_all === "y";
        document.getElementById("discord-toggle").checked =
          data.discord_include === "y";
        document.getElementById("cloudflare-toggle").checked =
          data.cloudflare_include === "y";
        document.getElementById("amazon-toggle").checked =
          data.amazon_include === "y";
        document.getElementById("hetzner-toggle").checked =
          data.hetzner_include === "y";
        document.getElementById("digitalocean-toggle").checked =
          data.digitalocean_include === "y";
        document.getElementById("ovh-toggle").checked =
          data.ovh_include === "y";
        document.getElementById("akamai-toggle").checked =
          data.akamai_include === "y";
        document.getElementById("telegram-toggle").checked =
          data.telegram_include === "y";
        document.getElementById("AdBlock-toggle").checked =
          data.block_ads === "y";
        document.getElementById("google-toggle").checked =
          data.google_include === "y";
        document.getElementById("tcp_80_443-toggle").checked =
          data.openvpn_80_443_tcp === "y";
        document.getElementById("udp_80_443-toggle").checked =
          data.openvpn_80_443_udp === "y";
        document.getElementById("ssh_protection-toggle").checked =
          data.ssh_protection === "y";
        document.getElementById("attack_protection-toggle").checked =
          data.attack_protection === "y";
        document.getElementById("torrent_guard-toggle").checked =
          data.torrent_guard === "y";
        document.getElementById("restrict_forward-toggle").checked =
          data.restrict_forward === "y";
        document.getElementById("clear-hosts-toggle").checked =
          data.clear_hosts === "y";
        document.getElementById("openvpn-host-input").value = data.openvpn_host;
        document.getElementById("wireguard-host-input").value =
          data.wireguard_host;
      })
      .catch((error) => {
        console.error("Error loading Antizapret settings:", error);
        showNotification("Ошибка загрузки настроек", "error");
      });
  };

  // Сохранение всех настроек Antizapret
  const saveAntizapretSettings = async () => {
    const settings = {
      route_all: document.getElementById("route-all-toggle").checked
        ? "y"
        : "n",
      discord_include: document.getElementById("discord-toggle").checked
        ? "y"
        : "n",
      cloudflare_include: document.getElementById("cloudflare-toggle").checked
        ? "y"
        : "n",
      amazon_include: document.getElementById("amazon-toggle").checked
        ? "y"
        : "n",
      hetzner_include: document.getElementById("hetzner-toggle").checked
        ? "y"
        : "n",
      digitalocean_include: document.getElementById("digitalocean-toggle")
        .checked
        ? "y"
        : "n",
      ovh_include: document.getElementById("ovh-toggle").checked ? "y" : "n",
      akamai_include: document.getElementById("akamai-toggle").checked
        ? "y"
        : "n",
      telegram_include: document.getElementById("telegram-toggle").checked
        ? "y"
        : "n",
      block_ads: document.getElementById("AdBlock-toggle").checked ? "y" : "n",
      google_include: document.getElementById("google-toggle").checked
        ? "y"
        : "n",
      openvpn_80_443_tcp: document.getElementById("tcp_80_443-toggle").checked
        ? "y"
        : "n",
      openvpn_80_443_udp: document.getElementById("udp_80_443-toggle").checked
        ? "y"
        : "n",
      ssh_protection: document.getElementById("ssh_protection-toggle").checked
        ? "y"
        : "n",
      attack_protection: document.getElementById("attack_protection-toggle")
        .checked
        ? "y"
        : "n",
      torrent_guard: document.getElementById("torrent_guard-toggle").checked
        ? "y"
        : "n",
      restrict_forward: document.getElementById("restrict_forward-toggle")
        .checked
        ? "y"
        : "n",
      clear_hosts: document.getElementById("clear-hosts-toggle").checked
        ? "y"
        : "n",
      openvpn_host: document.getElementById("openvpn-host-input").value.trim(),
      wireguard_host: document
        .getElementById("wireguard-host-input")
        .value.trim(),
    };

    const statusElement = document.getElementById("config-status");
    statusElement.textContent = "Сохранение настроек...";
    statusElement.className = "notification notification-info";
    statusElement.style.display = "block";

    try {
      // 1. Сначала сохраняем настройки
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

      // 2. Если сохранение успешно, применяем изменения
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

  // Инициализация
  initMenu();
  initUserTabs();

  // Назначение обработчика сохранения настроек
  document
    .getElementById("save-config")
    ?.addEventListener("click", saveAntizapretSettings);

  // События
  window.addEventListener("resize", handleResize);
  window.addEventListener("orientationchange", handleOrientationChange);

  // Сохраняем ссылки на вкладки
  if (history.pushState) {
    const menuLinks = document.querySelectorAll(".menu-item[data-tab]");
    menuLinks.forEach((link) => {
      link.addEventListener("click", function () {
        const tabId = this.getAttribute("data-tab");
        history.pushState(null, null, `#${tabId}`);
      });
    });
  }
});
