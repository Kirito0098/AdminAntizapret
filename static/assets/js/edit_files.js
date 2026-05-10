// === Уведомления ===
const notifyEl = document.getElementById('notification');
let notifyTimeout;
let notifyExitTimeout;

function safeTrim(value) {
    return (value || '').trim();
}

function splitLines(value) {
    if (!value) {
        return [];
    }
    return value.split(/\r?\n/);
}

function groupOrderRank(groupName) {
    const order = {
        'Домены': 10,
        'IP и маршрутизация': 20,
        'Рекламные фильтры': 30,
        'Безопасность': 40,
        'Прочее': 90,
    };
    return order[groupName] || 999;
}

function groupNavItems() {
    const nav = document.querySelector('.file-nav');
    if (!nav) {
        return;
    }

    const buttons = Array.from(nav.querySelectorAll('.nav-item'));
    if (!buttons.length) {
        return;
    }

    const groups = new Map();
    buttons.forEach((btn) => {
        const group = btn.dataset.group || 'Прочее';
        if (!groups.has(group)) {
            groups.set(group, []);
        }
        groups.get(group).push(btn);
    });

    const sortedGroupNames = Array.from(groups.keys()).sort((a, b) => {
        const byRank = groupOrderRank(a) - groupOrderRank(b);
        if (byRank !== 0) {
            return byRank;
        }
        return a.localeCompare(b, 'ru');
    });

    nav.innerHTML = '';
    sortedGroupNames.forEach((groupName) => {
        const section = document.createElement('section');
        section.className = 'ef-nav-group';
        section.dataset.group = groupName;

        const title = document.createElement('h3');
        title.className = 'ef-nav-group-title';
        title.textContent = groupName;
        section.appendChild(title);

        const itemsWrap = document.createElement('div');
        itemsWrap.className = 'ef-nav-group-items';
        groups.get(groupName).forEach((btn) => itemsWrap.appendChild(btn));
        section.appendChild(itemsWrap);

        nav.appendChild(section);
    });
}

function buildIndexedDiff(baseLines, currentLines) {
    const ops = [];
    const maxLen = Math.max(baseLines.length, currentLines.length);

    for (let i = 0; i < maxLen; i += 1) {
        const baseLine = baseLines[i];
        const currentLine = currentLines[i];

        if (baseLine === currentLine) {
            continue;
        }

        if (typeof baseLine !== 'undefined') {
            ops.push({ type: 'remove', lineNumber: i + 1, text: baseLine });
        }
        if (typeof currentLine !== 'undefined') {
            ops.push({ type: 'add', lineNumber: i + 1, text: currentLine });
        }
    }

    return ops;
}

function buildMyersDiff(baseLines, currentLines) {
    const n = baseLines.length;
    const m = currentLines.length;
    const max = n + m;
    const v = new Map();
    const trace = [];
    v.set(1, 0);

    for (let d = 0; d <= max; d += 1) {
        trace.push(new Map(v));
        for (let k = -d; k <= d; k += 2) {
            const xFromKMinus = v.get(k - 1);
            const xFromKPlus = v.get(k + 1);

            let x;
            if (k === -d || (k !== d && (xFromKMinus ?? -Infinity) < (xFromKPlus ?? -Infinity))) {
                x = xFromKPlus ?? 0;
            } else {
                x = (xFromKMinus ?? 0) + 1;
            }

            let y = x - k;
            while (x < n && y < m && baseLines[x] === currentLines[y]) {
                x += 1;
                y += 1;
            }

            v.set(k, x);

            if (x >= n && y >= m) {
                const ops = [];
                let backX = n;
                let backY = m;

                for (let backD = trace.length - 1; backD > 0; backD -= 1) {
                    const prevV = trace[backD - 1];
                    const backK = backX - backY;
                    let prevK;

                    if (backK === -backD || (backK !== backD && (prevV.get(backK - 1) ?? -Infinity) < (prevV.get(backK + 1) ?? -Infinity))) {
                        prevK = backK + 1;
                    } else {
                        prevK = backK - 1;
                    }

                    const prevX = prevV.get(prevK) ?? 0;
                    const prevY = prevX - prevK;

                    while (backX > prevX && backY > prevY) {
                        backX -= 1;
                        backY -= 1;
                    }

                    if (backX === prevX && backY > prevY) {
                        backY -= 1;
                        ops.push({ type: 'add', lineNumber: backY + 1, text: currentLines[backY] });
                    } else if (backX > prevX && backY === prevY) {
                        backX -= 1;
                        ops.push({ type: 'remove', lineNumber: backX + 1, text: baseLines[backX] });
                    }
                }

                while (backX > 0) {
                    backX -= 1;
                    ops.push({ type: 'remove', lineNumber: backX + 1, text: baseLines[backX] });
                }
                while (backY > 0) {
                    backY -= 1;
                    ops.push({ type: 'add', lineNumber: backY + 1, text: currentLines[backY] });
                }

                ops.reverse();
                return ops;
            }
        }
    }

    return buildIndexedDiff(baseLines, currentLines);
}

function buildLightDiff(baseValue, currentValue) {
    const baseLines = splitLines(baseValue);
    const currentLines = splitLines(currentValue);

    const complexity = baseLines.length * currentLines.length;
    if (complexity > 220000) {
        return {
            mode: 'indexed',
            ops: buildIndexedDiff(baseLines, currentLines),
        };
    }

    return {
        mode: 'myers',
        ops: buildMyersDiff(baseLines, currentLines),
    };
}

async function pollBackgroundTask(taskId, options = {}) {
    const intervalMs = options.intervalMs || 3000;
    const timeoutMs = options.timeoutMs || 900000;
    const startedAt = Date.now();

    while (Date.now() - startedAt < timeoutMs) {
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
            cache: 'no-store'
        });
        if (!response.ok) {
            throw new Error(`Ошибка запроса статуса задачи (HTTP ${response.status})`);
        }

        const task = await response.json();
        if (task.status === 'completed') {
            return task;
        }
        if (task.status === 'failed') {
            throw new Error(task.error || task.message || 'Фоновая задача завершилась с ошибкой');
        }

        await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }

    throw new Error('Превышено время ожидания фоновой задачи');
}

function showNotify(msg, type = 'success') {
    if (!notifyEl) {
        return;
    }

    notifyEl.textContent = msg;
    notifyEl.className = `notification notification-${type}`;
    notifyEl.classList.remove('notification-exit');
    notifyEl.hidden = false;

    clearTimeout(notifyTimeout);
    clearTimeout(notifyExitTimeout);

    notifyTimeout = setTimeout(() => {
        notifyEl.classList.add('notification-exit');
        notifyExitTimeout = setTimeout(() => {
            notifyEl.classList.remove('notification-exit');
            notifyEl.hidden = true;
        }, 180);
    }, 4700);
}

// === Навигация форм ===
groupNavItems();

const navItems = Array.from(document.querySelectorAll('.nav-item'));
const editForms = Array.from(document.querySelectorAll('.edit-form'));
const fileFilterInput = document.getElementById('file-filter');
const editfilesLayout = document.querySelector('.editfiles-layout');
const mobileSidebarToggle = document.getElementById('editfiles-mobile-toggle');
const mobileSidebarMedia = window.matchMedia('(max-width: 768px)');

let activeForm = editForms.find((form) => !form.hidden) || null;
const formMeta = new Map();

function setSidebarMenuOpen(isOpen) {
    if (!editfilesLayout || !mobileSidebarToggle) {
        return;
    }

    editfilesLayout.classList.toggle('is-sidebar-open', isOpen);
    mobileSidebarToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    mobileSidebarToggle.setAttribute(
        'aria-label',
        isOpen ? 'Скрыть меню редактирования' : 'Открыть меню редактирования'
    );
}

function syncSidebarMobileMode() {
    if (!editfilesLayout || !mobileSidebarToggle) {
        return;
    }

    const isMobile = mobileSidebarMedia.matches;
    editfilesLayout.classList.toggle('is-mobile-collapsible', isMobile);
    if (isMobile) {
        setSidebarMenuOpen(false);
    } else {
        editfilesLayout.classList.remove('is-sidebar-open');
        mobileSidebarToggle.setAttribute('aria-expanded', 'false');
    }
}

mobileSidebarToggle?.addEventListener('click', () => {
    if (!editfilesLayout || !mobileSidebarMedia.matches) {
        return;
    }

    const shouldOpen = !editfilesLayout.classList.contains('is-sidebar-open');
    setSidebarMenuOpen(shouldOpen);
});

if (typeof mobileSidebarMedia.addEventListener === 'function') {
    mobileSidebarMedia.addEventListener('change', syncSidebarMobileMode);
} else if (typeof mobileSidebarMedia.addListener === 'function') {
    mobileSidebarMedia.addListener(syncSidebarMobileMode);
}
syncSidebarMobileMode();

function getFormForNav(btn) {
    return document.getElementById(`form-${btn.dataset.file}`);
}

function updateFormCounters(form) {
    const meta = formMeta.get(form);
    if (!meta) {
        return;
    }

    const value = meta.textarea.value || '';
    const lines = value.length ? value.split(/\r?\n/).length : 0;
    const nonEmpty = value.split(/\r?\n/).filter((line) => safeTrim(line).length > 0).length;

    meta.linesEl.textContent = String(lines);
    meta.nonEmptyEl.textContent = String(nonEmpty);
    meta.charsEl.textContent = String(value.length);
}

function setDirtyState(form, isDirty) {
    const meta = formMeta.get(form);
    if (!meta) {
        return;
    }

    meta.isDirty = isDirty;
    meta.stateEl.textContent = isDirty ? 'Есть несохраненные изменения' : 'Без изменений';
    meta.stateEl.classList.toggle('is-dirty', isDirty);

    const nav = meta.navBtn;
    if (nav) {
        nav.classList.toggle('is-dirty', isDirty);
    }
}

function refreshFormState(form) {
    const meta = formMeta.get(form);
    if (!meta) {
        return;
    }

    updateFormCounters(form);
    setDirtyState(form, meta.textarea.value !== meta.initialValue);
}

function hasDirtyForms() {
    for (const [, meta] of formMeta) {
        if (meta.isDirty) {
            return true;
        }
    }
    return false;
}

function showForm(form) {
    editForms.forEach((f) => {
        f.hidden = f !== form;
    });
    activeForm = form;
    if (activeForm) {
        refreshFormState(activeForm);
    }
}

function selectNav(navBtn) {
    navItems.forEach((btn) => btn.classList.remove('active'));
    navBtn.classList.add('active');

    const targetForm = getFormForNav(navBtn);
    if (targetForm) {
        showForm(targetForm);
    }
}

function applyFileFilter(rawQuery) {
    const query = safeTrim(rawQuery).toLowerCase();
    let visibleCount = 0;

    navItems.forEach((btn) => {
        const text = btn.textContent.toLowerCase();
        const isVisible = !query || text.includes(query);
        btn.hidden = !isVisible;
        if (isVisible) {
            visibleCount += 1;
        }
    });

    const groupSections = Array.from(document.querySelectorAll('.file-nav .ef-nav-group'));
    groupSections.forEach((section) => {
        const hasVisible = Array.from(section.querySelectorAll('.nav-item')).some((btn) => !btn.hidden);
        section.hidden = !hasVisible;
    });

    if (visibleCount === 0) {
        return;
    }

    const currentActiveVisible = navItems.find((btn) => btn.classList.contains('active') && !btn.hidden);
    if (currentActiveVisible) {
        return;
    }

    const firstVisible = navItems.find((btn) => !btn.hidden);
    if (firstVisible) {
        selectNav(firstVisible);
    }
}

editForms.forEach((form) => {
    const textarea = form.querySelector('.code-area');
    const linesEl = form.querySelector('[data-lines-count]');
    const nonEmptyEl = form.querySelector('[data-nonempty-count]');
    const charsEl = form.querySelector('[data-chars-count]');
    const stateEl = form.querySelector('[data-editor-state]');
    const resetBtn = form.querySelector('[data-reset-content]');
    const diffSummaryEl = form.querySelector('[data-diff-summary]');
    const diffPanelEl = form.querySelector('[data-diff-panel]');
    const diffListEl = form.querySelector('[data-diff-list]');
    const diffToggleBtn = form.querySelector('[data-toggle-diff]');

    const navBtn = navItems.find((btn) => btn.dataset.file === form.id.replace('form-', ''));
    if (!textarea || !linesEl || !nonEmptyEl || !charsEl || !stateEl || !diffSummaryEl || !diffPanelEl || !diffListEl || !diffToggleBtn) {
        return;
    }

    formMeta.set(form, {
        textarea,
        linesEl,
        nonEmptyEl,
        charsEl,
        stateEl,
        resetBtn,
        diffSummaryEl,
        diffPanelEl,
        diffListEl,
        diffToggleBtn,
        navBtn,
        initialValue: textarea.value,
        isDirty: false,
        diffOps: [],
        diffMode: 'myers',
    });

    function updateDiffView() {
        const currentMeta = formMeta.get(form);
        if (!currentMeta) {
            return;
        }

        const diffResult = buildLightDiff(currentMeta.initialValue, currentMeta.textarea.value);
        currentMeta.diffOps = diffResult.ops;
        currentMeta.diffMode = diffResult.mode;

        const addedCount = currentMeta.diffOps.filter((op) => op.type === 'add').length;
        const removedCount = currentMeta.diffOps.filter((op) => op.type === 'remove').length;

        if (!addedCount && !removedCount) {
            currentMeta.diffSummaryEl.textContent = 'Нет отличий от сохраненной версии';
        } else {
            currentMeta.diffSummaryEl.textContent = `Добавлено: ${addedCount}, удалено: ${removedCount}`;
        }

        if (currentMeta.diffPanelEl.hidden) {
            return;
        }

        currentMeta.diffListEl.innerHTML = '';
        if (!currentMeta.diffOps.length) {
            const empty = document.createElement('div');
            empty.className = 'diff-empty';
            empty.textContent = 'Изменений не найдено.';
            currentMeta.diffListEl.appendChild(empty);
            return;
        }

        const maxLines = 300;
        currentMeta.diffOps.slice(0, maxLines).forEach((op) => {
            const row = document.createElement('div');
            row.className = `diff-line ${op.type === 'add' ? 'diff-line-add' : 'diff-line-remove'}`;

            const sign = document.createElement('span');
            sign.className = 'diff-line-sign';
            sign.textContent = op.type === 'add' ? '+' : '-';

            const lineNumber = document.createElement('span');
            lineNumber.className = 'diff-line-num';
            lineNumber.textContent = `L${op.lineNumber}`;

            const text = document.createElement('span');
            text.className = 'diff-line-text';
            text.textContent = op.text || ' ';

            row.appendChild(sign);
            row.appendChild(lineNumber);
            row.appendChild(text);
            currentMeta.diffListEl.appendChild(row);
        });

        if (currentMeta.diffOps.length > maxLines) {
            const rest = document.createElement('div');
            rest.className = 'diff-empty';
            rest.textContent = `Показаны первые ${maxLines} строк diff.`;
            currentMeta.diffListEl.appendChild(rest);
        }

        if (currentMeta.diffMode === 'indexed') {
            const modeNote = document.createElement('div');
            modeNote.className = 'diff-empty';
            modeNote.textContent = 'Для большого файла включен быстрый режим diff.';
            currentMeta.diffListEl.appendChild(modeNote);
        }
    }

    textarea.addEventListener('input', () => {
        refreshFormState(form);
        updateDiffView();
    });

    resetBtn?.addEventListener('click', () => {
        const meta = formMeta.get(form);
        if (!meta) {
            return;
        }
        meta.textarea.value = meta.initialValue;
        refreshFormState(form);
        updateDiffView();
        showNotify('Изменения в форме сброшены', 'success');
    });

    diffToggleBtn.addEventListener('click', () => {
        const meta = formMeta.get(form);
        if (!meta) {
            return;
        }

        const shouldOpen = meta.diffPanelEl.hidden;
        meta.diffPanelEl.hidden = !shouldOpen;
        meta.diffToggleBtn.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
        meta.diffToggleBtn.textContent = shouldOpen ? 'Скрыть diff' : 'Показать diff';
        updateDiffView();
    });

    refreshFormState(form);
    updateDiffView();
});

navItems.forEach(btn => {
    btn.addEventListener('click', () => {
        selectNav(btn);
        if (mobileSidebarMedia.matches) {
            setSidebarMenuOpen(false);
        }
    });
});

const defaultNavItem = navItems.find((btn) => btn.classList.contains('active')) || navItems[0];
if (defaultNavItem) {
    selectNav(defaultNavItem);
}

fileFilterInput?.addEventListener('input', (event) => {
    applyFileFilter(event.target.value);
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && mobileSidebarMedia.matches && editfilesLayout?.classList.contains('is-sidebar-open')) {
        setSidebarMenuOpen(false);
        return;
    }

    const isSave = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's';
    if (!isSave) {
        return;
    }

    if (!activeForm) {
        return;
    }

    event.preventDefault();
    activeForm.requestSubmit();
});

window.addEventListener('beforeunload', (event) => {
    if (!hasDirtyForms()) {
        return;
    }

    event.preventDefault();
    event.returnValue = '';
});

// === Обработка форм ===
editForms.forEach(form => {
    form.addEventListener('submit', async e => {
        e.preventDefault();

        const submitBtn = form.querySelector('.btn-save');
        const originalText = submitBtn.textContent;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Сохраняем...';

        try {
            const res = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form)
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            let data;
            try {
                data = await res.json();
            } catch {
                throw new Error('Некорректный ответ сервера');
            }

            if (data.queued && data.task_id) {
                showNotify(data.message || 'Изменения сохранены. Применение запущено в фоне.', 'success');
                const task = await pollBackgroundTask(data.task_id);
                showNotify(task.message || 'Изменения успешно применены', 'success');
            } else {
                showNotify(data.message || 'Изменения сохранены', data.success ? 'success' : 'error');
            }

            const meta = formMeta.get(form);
            if (meta) {
                meta.initialValue = meta.textarea.value;
                refreshFormState(form);
                const diffResult = buildLightDiff(meta.initialValue, meta.textarea.value);
                meta.diffOps = diffResult.ops;
                meta.diffMode = diffResult.mode;
                meta.diffSummaryEl.textContent = 'Нет отличий от сохраненной версии';
                if (!meta.diffPanelEl.hidden) {
                    meta.diffListEl.innerHTML = '';
                    const empty = document.createElement('div');
                    empty.className = 'diff-empty';
                    empty.textContent = 'Изменений не найдено.';
                    meta.diffListEl.appendChild(empty);
                }
            }
        } catch (err) {
            showNotify('Ошибка при сохранении', 'error');
            console.error('Ошибка сохранения:', err);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    });
});

// === Массовое обновление (Run DoAll) ===
const runDoAllBtn = document.getElementById('run-doall');
runDoAllBtn?.addEventListener('click', async () => {
    if (!confirm('Применить все изменения и обновить список АнтиЗапрета?')) return;

    const originalText = runDoAllBtn.textContent;
    runDoAllBtn.disabled = true;
    runDoAllBtn.textContent = 'Обновляем...';

    try {
        const getCsrfToken = () => {
            return document.querySelector('input[name="csrf_token"]')?.value ||
                document.querySelector('meta[name="csrf-token"]')?.content ||
                "";
        };
        const csrfToken = getCsrfToken();
        if (!csrfToken) throw new Error('CSRF-токен не найден');

        const res = await fetch('/run-doall', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfToken,
            },
            body: `csrf_token=${encodeURIComponent(csrfToken)}`
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        let data;
        try {
            data = await res.json();
        } catch {
            throw new Error('Некорректный ответ сервера');
        }

        if (data.queued && data.task_id) {
            showNotify(data.message || 'Обновление списка запущено в фоне', 'success');
            const task = await pollBackgroundTask(data.task_id);
            showNotify(task.message || 'Список успешно обновлён', 'success');
        } else {
            showNotify(data.message || 'Список успешно обновлён', data.success ? 'success' : 'error');
        }
    } catch (err) {
        showNotify('Не удалось обновить список', 'error');
        console.error('Ошибка обновления:', err);
    } finally {
        runDoAllBtn.disabled = false;
        runDoAllBtn.textContent = originalText;
    }
});

// === Переключение панелей Lists / Routes ===
const btnLists = document.getElementById('btn-lists');
const btnRoutes = document.getElementById('btn-routes');
const listsPanel = document.getElementById('lists-panel');
const routesPanel = document.getElementById('routes-panel');

function switchPanel(activeBtn, inactiveBtn, showPanel, hidePanel) {
    if (!activeBtn || !inactiveBtn || !showPanel || !hidePanel) {
        return;
    }

    activeBtn.classList.add('active');
    inactiveBtn.classList.remove('active');
    activeBtn.setAttribute('aria-selected', 'true');
    inactiveBtn.setAttribute('aria-selected', 'false');
    showPanel.style.display = 'block';
    hidePanel.style.display = 'none';
}

btnLists?.addEventListener('click', () => switchPanel(btnLists, btnRoutes, listsPanel, routesPanel));
btnRoutes?.addEventListener('click', () => switchPanel(btnRoutes, btnLists, routesPanel, listsPanel));
