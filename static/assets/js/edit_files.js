// === Уведомления ===
const notifyEl = document.getElementById('notification');
let notifyTimeout;

function showNotify(msg, type = 'success') {
    notifyEl.textContent = msg;
    notifyEl.className = `notification notification-${type}`;
    notifyEl.hidden = false;
    clearTimeout(notifyTimeout);
    notifyTimeout = setTimeout(() => { notifyEl.hidden = true; }, 5000);
}

// === Навигация форм ===
const navItems = document.querySelectorAll('.nav-item');
const editForms = document.querySelectorAll('.edit-form');

navItems.forEach(btn => {
    btn.addEventListener('click', () => {
        navItems.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        editForms.forEach(f => f.hidden = true);
        const targetForm = document.getElementById(`form-${btn.dataset.file}`);
        if (targetForm) targetForm.hidden = false;
    });
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

            showNotify(data.message || 'Изменения сохранены', data.success ? 'success' : 'error');
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
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (!csrfInput) throw new Error('CSRF-токен не найден');

        const res = await fetch('/run-doall', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfInput.value,
            },
            body: `csrf_token=${encodeURIComponent(csrfInput.value)}`
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        let data;
        try {
            data = await res.json();
        } catch {
            throw new Error('Некорректный ответ сервера');
        }

        showNotify(data.message || 'Список успешно обновлён', data.success ? 'success' : 'error');
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
    activeBtn.classList.add('active');
    inactiveBtn.classList.remove('active');
    showPanel.style.display = 'block';
    hidePanel.style.display = 'none';
}

btnLists.addEventListener('click', () => switchPanel(btnLists, btnRoutes, listsPanel, routesPanel));
btnRoutes.addEventListener('click', () => switchPanel(btnRoutes, btnLists, routesPanel, listsPanel));
