document.addEventListener("DOMContentLoaded", function () {
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

  // === ВКЛАДКА ОБНОВЛЕНИЙ СИСТЕМЫ ===
  const initUpdatesTab = () => {
    const els = {
      hero:            document.getElementById("upd-hero"),
      heroIcon:        document.getElementById("upd-hero-icon"),
      heroLabel:       document.getElementById("upd-hero-label"),
      heroSub:         document.getElementById("upd-hero-sub"),
      checkBtn:        document.getElementById("upd-check-btn"),
      branch:          document.getElementById("upd-branch"),
      localHash:       document.getElementById("upd-local-hash"),
      localDate:       document.getElementById("upd-local-date"),
      remoteHash:      document.getElementById("upd-remote-hash"),
      releaseCard:     document.getElementById("upd-release-card"),
      releaseVersion:  document.getElementById("upd-release-version"),
      releaseDate:     document.getElementById("upd-release-date"),
      releaseSections: document.getElementById("upd-release-sections"),
      changelogCard:   document.getElementById("upd-changelog-card"),
      changelogCount:  document.getElementById("upd-changelog-count"),
      changelogList:   document.getElementById("upd-changelog-list"),
      applyBtn:        document.getElementById("upd-apply-btn"),
      progress:        document.getElementById("upd-progress"),
      progressFill:   document.getElementById("upd-progress-fill"),
      progressLabel:  document.getElementById("upd-progress-label"),
      resultMsg:      document.getElementById("upd-result-msg"),
      menuItem:       document.querySelector(".nav-sublink[data-settings-tab='system-updates']"),
    };

    if (!els.checkBtn) return;

    const getCsrfToken = () =>
      document.querySelector('input[name="csrf_token"]')?.value ||
      document.querySelector('meta[name="csrf-token"]')?.content || "";

    const ICONS = {
      loading: `<svg class="upd-hero__icon upd-hero__icon--spin" viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <circle cx="20" cy="20" r="16" stroke="currentColor" stroke-width="2.4" stroke-dasharray="60 40" stroke-linecap="round"/>
      </svg>`,
      ok: `<svg class="upd-hero__icon" viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <circle cx="20" cy="20" r="17" stroke="currentColor" stroke-width="2.2"/>
        <path d="M12 20l6 6 10-12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`,
      available: `<svg class="upd-hero__icon" viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <circle cx="20" cy="20" r="17" stroke="currentColor" stroke-width="2.2"/>
        <path d="M20 10v14M13 18l7 7 7-7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`,
      error: `<svg class="upd-hero__icon" viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <circle cx="20" cy="20" r="17" stroke="currentColor" stroke-width="2.2"/>
        <path d="M20 12v11M20 27v2" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
      </svg>`,
    };

    const setHeroState = (state) => {
      if (!els.hero) return;
      els.hero.dataset.state = state;
      if (els.heroIcon) els.heroIcon.innerHTML = ICONS[state] || ICONS.loading;
    };

    const pluralCommit = (n) => {
      if (n % 10 === 1 && n % 100 !== 11) return `${n} коммит`;
      if ([2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100)) return `${n} коммита`;
      return `${n} коммитов`;
    };

    const esc = (s) => String(s).replace(/[&<>"']/g, c =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    const renderChangelog = (commits) => {
      if (!commits?.length) { els.changelogCard.hidden = true; return; }
      els.changelogCount.textContent = commits.length;
      els.changelogList.innerHTML = commits.map(c => `
        <div class="upd-commit">
          <code class="upd-commit__hash">${esc(c.hash)}</code>
          <span class="upd-commit__subject">${esc(c.subject)}</span>
          <span class="upd-commit__meta">
            <span class="upd-commit__date">${esc(c.date)}</span>
            <span class="upd-commit__author">${esc(c.author)}</span>
          </span>
        </div>`).join("");
      els.changelogCard.hidden = false;
    };

    const animateProgress = (duration = 90000) => {
      if (!els.progressFill) return;
      let start = null;
      const tick = (ts) => {
        if (!start) start = ts;
        const pct = Math.min(92, ((ts - start) / duration) * 92);
        els.progressFill.style.width = `${pct}%`;
        if (pct < 92) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };

    const checkForUpdates = async () => {
      setHeroState("loading");
      els.heroLabel.textContent = "Проверяем обновления…";
      els.heroSub.textContent   = "Получаем данные из репозитория";
      els.checkBtn.disabled = true;
      els.applyBtn.disabled = true;
      els.changelogCard.hidden = true;

      try {
        const resp = await fetch("/check_updates");
        const data = await resp.json();

        if (els.branch)     els.branch.textContent    = data.branch        || "—";
        if (els.localHash)  els.localHash.textContent  = data.local_commit  || "—";
        if (els.remoteHash) els.remoteHash.textContent = data.remote_commit || "—";
        if (els.localDate)  els.localDate.textContent  = data.local_date    || "—";

        if (data.update_available) {
          setHeroState("available");
          els.heroLabel.textContent = `Доступно обновление — ${pluralCommit(data.pending_count)}`;
          els.heroSub.textContent   = "Нажмите «Установить», чтобы применить изменения";
          els.applyBtn.disabled = false;
          els.menuItem?.classList.add("upd-menu-badge");
          renderChangelog(data.pending_commits || []);
        } else {
          setHeroState("ok");
          els.heroLabel.textContent = "Система обновлена";
          els.heroSub.textContent   = "Установлена последняя версия из репозитория";
          els.menuItem?.classList.remove("upd-menu-badge");
        }
      } catch {
        setHeroState("error");
        els.heroLabel.textContent = "Ошибка проверки";
        els.heroSub.textContent   = "Нет соединения с репозиторием";
      } finally {
        els.checkBtn.disabled = false;
      }
    };

    const applyUpdate = async () => {
      if (!confirm("ВНИМАНИЕ!\nВсе локальные изменения файлов будут перезаписаны.\nПродолжить обновление?")) return;

      els.applyBtn.disabled = true;
      els.checkBtn.disabled = true;
      els.progress.hidden = false;
      if (els.progressFill) els.progressFill.style.width = "0%";
      if (els.resultMsg) {
        els.resultMsg.textContent = "Выполняется обновление…";
        els.resultMsg.className = "notification notification-info notification-inline-progress";
        els.resultMsg.hidden = false;
        els.resultMsg.style.display = "block";
      }
      animateProgress();

      try {
        const resp = await fetch("/update_system", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
        });
        const data = await resp.json();

        if (data.queued && data.task_id) {
          if (els.progressLabel) els.progressLabel.textContent = "Выполняется обновление…";
          const task = await pollBackgroundTask(data.task_id, { timeoutMs: 1200000 });
          const ok = task.status === "done";
          if (els.progressFill) els.progressFill.style.width = "100%";
          window.showNotification?.(
            task.message || (ok ? "Обновление завершено!" : "Ошибка обновления"),
            ok ? "success" : "error"
          );
          if (ok) {
            setHeroState("ok");
            els.heroLabel.textContent = "Обновление установлено";
            els.heroSub.textContent   = "Служба будет перезапущена автоматически";
            els.changelogCard.hidden = true;
            els.menuItem?.classList.remove("upd-menu-badge");
          }
        } else {
          window.showNotification?.(data.message || "Ошибка обновления", "error");
        }
      } catch {
        window.showNotification?.("Ошибка соединения", "error");
      } finally {
        els.progress.hidden = true;
        els.checkBtn.disabled = false;
        if (els.resultMsg) {
          els.resultMsg.hidden = true;
          els.resultMsg.textContent = "";
          els.resultMsg.style.display = "none";
        }
      }
    };

    const renderReleaseNotes = (data) => {
      if (!data?.success || !data.sections?.length) return;
      if (els.releaseVersion) els.releaseVersion.textContent = `v${data.version}`;
      if (els.releaseDate)    els.releaseDate.textContent    = data.date;
      if (els.releaseSections) {
        els.releaseSections.innerHTML = data.sections.map(sec => `
          <div class="upd-release-section">
            <p class="upd-release-section__title">${esc(sec.title)}</p>
            <ul class="upd-release-section__list">
              ${sec.items.map(item => `<li>${esc(item)}</li>`).join("")}
            </ul>
          </div>`).join("");
      }
    };

    const loadReleaseNotes = async () => {
      try {
        const resp = await fetch("/api/latest-changelog", { cache: "no-store" });
        const data = await resp.json();
        renderReleaseNotes(data);
      } catch { /* silent — non-critical */ }
    };

    els.checkBtn.addEventListener("click", checkForUpdates);
    els.applyBtn.addEventListener("click", applyUpdate);

    window.addEventListener("settings:tab-changed", (e) => {
      if (e.detail?.tabId === "system-updates") checkForUpdates();
    });

    loadReleaseNotes();

    if (document.getElementById("system-updates")?.classList.contains("active")) {
      checkForUpdates();
    }
  };

  initUpdatesTab();
  initUserActionPopups();
  initMiniAppLinkCopy();
  initSettingsRangeControls();
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

