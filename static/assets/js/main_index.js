
const optionSelect = document.getElementById('option');
const clientNameInput = document.getElementById('client-name');
const clientNameContainer = document.getElementById('client-name-container');
const clientSelectContainer = document.getElementById('client-select-container');
const clientSelect = document.getElementById('client-select');
const workTermContainer = document.getElementById('work-term-container');

// Функция для извлечения имени клиента
function extractClientName(filename) {
    const parts = filename.split('-');
    if (parts.length >= 2) {
        return parts[1]; // Возвращаем вторую часть (имя клиента)
    }
    return filename; // Если не удалось извлечь имя, возвращаем полное имя файла
}

// Функция для обновления видимости элементов формы
function updateFormVisibility() {
    const selectedOption = optionSelect.value;

    if (selectedOption === '1') {
        // Показываем поле "Имя клиента" и "Срок работы" для добавления OpenVPN
        clientNameContainer.style.display = 'flex';
        workTermContainer.style.display = 'flex';
        clientSelectContainer.style.display = 'none';
    } else if (selectedOption === '2' || selectedOption === '5') {
        // Показываем выпадающий список для удаления клиента
        clientNameContainer.style.display = 'none';
        workTermContainer.style.display = 'none';
        clientSelectContainer.style.display = 'flex';
        populateClientSelect(selectedOption);
    } else if (selectedOption === '4') {
        // Показываем только поле "Имя клиента" для добавления WireGuard
        clientNameContainer.style.display = 'flex';
        workTermContainer.style.display = 'none';
        clientSelectContainer.style.display = 'none';
    } else {
// Скрываем все дополнительные поля для других опций
clientNameContainer.style.display = 'none';
workTermContainer.style.display = 'none';
clientSelectContainer.style.display = 'none';
}
}

// Функция для заполнения выпадающего списка клиентами
function populateClientSelect(option) {
    // Очищаем список, кроме первой пустой опции
    clientSelect.innerHTML = '<option value="">-- Выберите клиента --</option>';

    // Используем Set для хранения уникальных имён
    const uniqueClientNames = new Set();

    // Определяем, какие таблицы использовать (OpenVPN или WireGuard)
    const table = option === '2' 
        ? document.querySelector('.file-list .column:first-child table') 
        : document.querySelector('.file-list .column:last-child table');

    // Получаем все строки таблицы
    const rows = table.querySelectorAll('tbody tr');

// Добавляем клиентов в выпадающий список
rows.forEach(row => {
const filename = row.querySelector('td').textContent; // Полное имя файла
const clientName = extractClientName(filename); // Извлекаем имя клиента

// Проверяем, что имя клиента не содержит слово "client"
if (!clientName.toLowerCase().includes('client')) {
    // Добавляем имя клиента в Set (дубликаты будут автоматически удалены)
    uniqueClientNames.add(clientName);
}
})

    // Преобразуем Set в массив и добавляем имена в выпадающий список
    uniqueClientNames.forEach(clientName => {
        const optionElement = document.createElement('option');
        optionElement.value = clientName; // Значение для отправки на сервер
        optionElement.textContent = clientName; // Отображаемое имя
        clientSelect.appendChild(optionElement);
    });

    // Автоматически заполняем поле "Имя клиента" при выборе из списка
    clientSelect.addEventListener('change', function() {
        clientNameInput.value = clientSelect.value;
    });
}

// Обработка отправки формы
const form = document.querySelector('form');
form.addEventListener('submit', function(event) {
    event.preventDefault();

    const formData = new FormData(form);

    fetch('/', {
        method: 'POST',
        body: formData
    })
    .then(response => response.text())
    .then(html => {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;

        // Обновляем таблицы
        const newOpenVPNTable = tempDiv.querySelector('.file-list .column:first-child table');
        const newWireGuardTable = tempDiv.querySelector('.file-list .column:last-child table');

        const currentOpenVPNTable = document.querySelector('.file-list .column:first-child table');
        const currentWireGuardTable = document.querySelector('.file-list .column:last-child table');

        if (newOpenVPNTable && newWireGuardTable) {
            currentOpenVPNTable.innerHTML = newOpenVPNTable.innerHTML;
            currentWireGuardTable.innerHTML = newWireGuardTable.innerHTML;
        }

        // Обновляем выпадающий список клиентов
        const selectedOption = optionSelect.value;
        if (selectedOption === '2' || selectedOption === '5') {
            populateClientSelect(selectedOption);
        }

        // Показываем уведомление об успешном удалении
        Swal.fire({
            icon: 'success',
            title: 'Клиент успешно удалён!',
            showConfirmButton: false,
            timer: 2000
        });
    })
    .catch(error => {
        console.error('Ошибка:', error);
        Swal.fire({
            icon: 'error',
            title: 'Ошибка',
            text: 'Произошла ошибка при удалении клиента.'
        });
    });
});


// Обновляем видимость элементов при изменении выбора
optionSelect.addEventListener('change', updateFormVisibility);