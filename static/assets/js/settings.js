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
  
          // Если вкладка "Настройки порта", деактивируем все вкладки управления пользователями
          if (tabId === "port-settings") {
            // Скрываем все вкладки "Управления пользователями"
            const userTabs = document.querySelectorAll(".subtab-content");
            userTabs.forEach((tab) => tab.classList.remove("active"));
          }
  
          if (tabId) {
            activateTab(tabId);
          }
  
          // Если открыта вкладка "Управление пользователями", активируем под-вкладку "Добавить"
          if (tabId === "user-management") {
            // Деактивируем все кнопки, чтобы не оставалась зелёная обводка
            const subtabButtons = document.querySelectorAll(".tab-button");
            subtabButtons.forEach((button) => {
              button.classList.remove("active");
            });
  
            // Активируем вкладку "Добавить"
            const defaultUserTab = document.querySelector(".tab-button[data-subtab='add-user']");
            if (defaultUserTab) {
              defaultUserTab.classList.add("active");
              const addUserTabContent = document.querySelector("#add-user");
              if (addUserTabContent) {
                addUserTabContent.classList.add("active");
              }
            }
          }
        });
  
        // Активация по хэшу URL
        if (window.location.hash === `#${item.getAttribute("data-tab")}`) {
          item.click();
        }
      });
  
      // Активация первой вкладки по умолчанию
      if (menuItems.length > 0 && !window.location.hash) {
        menuItems[0].click(); // Это может быть вкладка "Настройки порта"
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
  
      // Активация первой под-вкладки (по умолчанию)
      if (tabButtons.length > 0) {
        tabButtons[0].click(); // Это может быть вкладка "Добавить"
      }
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
  