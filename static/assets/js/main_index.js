document.addEventListener('DOMContentLoaded', function() {
    // Элементы формы
    const qrImage = document.getElementById('qrImage');
    const modalContainer = document.getElementById('modalQRContainer');
    const optionSelect = document.getElementById('option');
    const clientNameInput = document.getElementById('client-name');
    const clientNameContainer = document.getElementById('client-name-container');
    const clientSelectContainer = document.getElementById('client-select-container');
    const clientSelect = document.getElementById('client-select');
    const workTermContainer = document.getElementById('work-term-container');
    const workTermInput = document.getElementById('work-term');
    const notification = document.getElementById('notification');
    const clientForm = document.getElementById('client-form');

    // Элемент для ненавязчивого уведомления загрузки
    const loadingIndicator = document.createElement('div');
    loadingIndicator.id = 'loading-indicator';
    loadingIndicator.style.display = 'none';
    loadingIndicator.innerHTML = `
        <div class="loading-indicator-text">Выполняется запрос...</div>
    `;
    document.body.appendChild(loadingIndicator);

    // Функция для отображения/скрытия индикатора загрузки
    function toggleLoadingIndicator(show) {
        loadingIndicator.style.display = show ? 'block' : 'none';
    }

    // Функция для извлечения имени клиента из имени файла
    function extractClientName(filename) {
        const parts = filename.split('-');
        return parts.slice(1, -2).join('-'); // Извлекаем имя клиента между первым и предпоследними частями
    }

    // Функция для обновления видимости элементов формы
    function updateFormVisibility() {
        const selectedOption = optionSelect.value;

        // Сброс значений при изменении опции
        if (selectedOption !== '1') workTermInput.value = '';
        if (selectedOption !== '1' && selectedOption !== '4') clientNameInput.value = '';

        // Управление видимостью полей
        clientNameContainer.style.display = (selectedOption === '1' || selectedOption === '4') ? 'flex' : 'none';
        workTermContainer.style.display = selectedOption === '1' ? 'flex' : 'none';
        clientSelectContainer.style.display = (selectedOption === '2' || selectedOption === '5' || selectedOption === '6') ? 'flex' : 'none';

        // Заполнение выпадающего списка клиентов при необходимости
        if (selectedOption === '2' || selectedOption === '5' || selectedOption === '6') {
            populateClientSelect(selectedOption);
        }
    }

    // Функция для заполнения выпадающего списка клиентами
    function populateClientSelect(option) {
        clientSelect.innerHTML = '<option value="">-- Выберите клиента --</option>';
        const uniqueClientNames = new Set();

        // Определяем, какую таблицу использовать в зависимости от выбранной опции
        let tableIndex = option === '2' ? 0 : option === '5' ? 1 : 2;
        const table = document.querySelectorAll('.file-list .column')[tableIndex]?.querySelector('table');

        if (table) {
            const rows = table.querySelectorAll('tbody tr:nth-child(odd)'); // Берем только строки с именами клиентов
            rows.forEach(row => {
                const clientNameCell = row.querySelector('td:first-child');
                if (clientNameCell) {
                    const clientName = clientNameCell.textContent.trim();
                    if (clientName) {
                        uniqueClientNames.add(clientName);
                    }
                }
            });
        }

        // Добавляем клиентов в выпадающий список
        uniqueClientNames.forEach(clientName => {
            const optionElement = document.createElement('option');
            optionElement.value = clientName;
            optionElement.textContent = clientName;
            clientSelect.appendChild(optionElement);
        });

        // Автозаполнение поля имени клиента при выборе из списка
        clientSelect.addEventListener('change', function() {
            clientNameInput.value = clientSelect.value;
        });
    }

    // Функция для отображения уведомлений
    function showNotification(message, type = 'success') {
        notification.textContent = message;
        notification.className = `notification notification-${type}`;
        notification.style.display = 'block';
        setTimeout(() => {
            notification.style.display = 'none';
        }, 3000);
    }

    // Функция для обновления таблиц конфигураций
    function updateConfigTables() {
        fetch('/')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ошибка: ${response.status}`);
                }
                return response.text(); // Получаем HTML главной страницы
            })
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');

                // Обновляем содержимое таблиц
                const newTables = doc.querySelectorAll('.file-list .column table');
                const currentTables = document.querySelectorAll('.file-list .column table');

                newTables.forEach((newTable, index) => {
                    if (currentTables[index]) {
                        currentTables[index].innerHTML = newTable.innerHTML;
                    }
                });
            })
            .catch(error => {
                console.error('Ошибка обновления таблиц конфигураций:', error);
            });
    }

    // Функция для обновления выпадающего списка клиентов
    function updateClientSelect(option) {
        clientSelect.innerHTML = '<option value="">-- Выберите клиента --</option>';
        const uniqueClientNames = new Set();

        // Определяем, какую таблицу использовать в зависимости от выбранной опции
        let tableIndex = option === '2' ? 0 : option === '5' ? 1 : 2;
        const table = document.querySelectorAll('.file-list .column')[tableIndex]?.querySelector('table');

        if (table) {
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const clientNameCell = row.querySelector('td:first-child');
                if (clientNameCell) {
                    const clientName = extractClientName(clientNameCell.textContent.trim());
                    if (clientName && !clientName.toLowerCase().includes('client')) {
                        uniqueClientNames.add(clientName);
                    }
                }
            });
        }

        // Добавляем клиентов в выпадающий список
        uniqueClientNames.forEach(clientName => {
            const optionElement = document.createElement('option');
            optionElement.value = clientName;
            optionElement.textContent = clientName;
            clientSelect.appendChild(optionElement);
        });
    }

    // Функция для обновления таблиц конфигураций и выпадающего списка клиентов
    function refreshData() {
        fetch('/')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ошибка: ${response.status}`);
                }
                return response.text(); // Получаем HTML главной страницы
            })
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');

                // Обновляем содержимое таблиц
                const newTables = doc.querySelectorAll('.file-list .column table');
                const currentTables = document.querySelectorAll('.file-list .column table');

                newTables.forEach((newTable, index) => {
                    if (currentTables[index]) {
                        currentTables[index].innerHTML = newTable.innerHTML;
                    }
                });
                 // Обновляем выпадающий список клиентов
                const selectedOption = optionSelect.value;
            })
            .catch(error => {
                console.error('Ошибка обновления данных:', error);
            });
    }

    // Функция для обновления данных о сервере
    function updateServerInfo() {
        if (window.location.pathname !== '/server_monitor') {
            return; 
        }
    
        fetch('/server_monitor', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Ошибка:', data.error);
                return;
            }
            const cpuElement = document.getElementById('cpu-usage');
            const memoryElement = document.getElementById('memory-usage');
            const uptimeElement = document.getElementById('uptime');
    
            if (cpuElement) cpuElement.textContent = data.cpu_usage + '%';
            if (memoryElement) memoryElement.textContent = data.memory_usage + '%';
            if (uptimeElement) uptimeElement.textContent = data.uptime;
        })
        .catch(error => console.error('Ошибка при обновлении данных:', error));
    }

    // Проверяем, находимся ли мы на странице мониторинга
    if (window.location.pathname === '/server_monitor') {
        // Запускаем первоначальное обновление
        updateServerInfo();
        // Запускаем периодическое обновление каждые 5 секунд
        setInterval(updateServerInfo, 5000);
    }

    // Обработчик отправки формы
    clientForm.addEventListener('submit', function(event) {
        event.preventDefault();
        const option = optionSelect.value;
        const clientName = clientNameInput.value.trim();

        // Проверка обязательных полей
        if (!option || !clientName) {
            showNotification('Пожалуйста, заполните все обязательные поля.', 'error');
            return;
        }

        if (option === '2' || option === '5') {
            // Подтверждение удаления
            const confirmDelete = confirm('Вы уверены, что хотите удалить клиента?');
            if (!confirmDelete) return;
        }

        const formData = new FormData(clientForm);

        // Показываем индикатор загрузки
        toggleLoadingIndicator(true);

        fetch('/', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ошибка: ${response.status}`);
            }
            return response.json(); // Предполагаем, что сервер возвращает JSON
        })
        .then(data => {
            // Скрываем индикатор загрузки
            toggleLoadingIndicator(false);

            if (data.success) {
                showNotification(data.message, 'success');
                refreshData(); // Обновляем таблицы и выпадающий список
            } else {
                showNotification(data.message || 'Неизвестная ошибка', 'error');
            }
        })
        .catch(error => {
            // Скрываем индикатор загрузки
            toggleLoadingIndicator(false);

            showNotification(`Ошибка выполнения запроса: ${error.message}`, 'error');
            console.error('Ошибка:', error);
        });
    });   
 
    // Обработчик для модального окна
    document.addEventListener('click', function(event) {
        // Проверка на клик по модальному окну
        if (event.target === modalContainer || 
            event.target.closest('.qr-modal-container')) {
            modalContainer.style.display = 'none';
            return;
        } 
        // Открытие модального окна
        if (event.target.classList.contains('vpn-qr-button')) {
            const configUrl = event.target.dataset.config;
            if (configUrl) {
                qrImage.src = configUrl;
                modalContainer.style.display = 'flex';
            }
        }
    });
    // Проверка на клик вне модального окна
    window.addEventListener('click', function(event) {
        if (event.target === modalContainer) {
            modalContainer.style.display = 'none';
        }
    }); 
    // Инициализация при загрузке
    updateFormVisibility();
    optionSelect.addEventListener('change', updateFormVisibility);
    
    if (window.location.pathname === '/server_monitor') {
        updateServerInfo();
        setInterval(updateServerInfo, 5000);
    }
});