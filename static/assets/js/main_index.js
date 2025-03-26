document.addEventListener('DOMContentLoaded', function() {
    // Элементы формы
    const optionSelect = document.getElementById('option');
    const clientNameInput = document.getElementById('client-name');
    const clientNameContainer = document.getElementById('client-name-container');
    const clientSelectContainer = document.getElementById('client-select-container');
    const clientSelect = document.getElementById('client-select');
    const workTermContainer = document.getElementById('work-term-container');
    const workTermInput = document.getElementById('work-term');
    const form = document.querySelector('form');

    // Функция для извлечения имени клиента из имени файла
    function extractClientName(filename) {
        const parts = filename.split('-');
        if (parts.length >= 2) {
            return parts[1];
        }
        return filename;
    }

    // Функция для обновления видимости элементов формы
    function updateFormVisibility() {
        const selectedOption = optionSelect.value;

        // Сброс значений при изменении опции
        if (selectedOption !== '1') {
            workTermInput.value = '';
        }
        if (selectedOption !== '1' && selectedOption !== '4') {
            clientNameInput.value = '';
        }

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
        let tableIndex;
        if (option === '2') tableIndex = 0;      // OpenVPN
        else if (option === '5') tableIndex = 1; // WireGuard
        else if (option === '6') tableIndex = 2; // AmneziaWG

        const table = document.querySelectorAll('.file-list .column')[tableIndex]?.querySelector('table');
        
        if (table) {
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const clientNameCell = row.querySelector('td:first-child');
                if (clientNameCell) {
                    const clientName = extractClientName(clientNameCell.textContent);
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

        // Автозаполнение поля имени клиента при выборе из списка
        clientSelect.addEventListener('change', function() {
            clientNameInput.value = clientSelect.value;
        });
    }

    // Обработчик отправки формы
    form.addEventListener('submit', function(event) {
        event.preventDefault();
        const formData = new FormData(form);

        fetch('/', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.text();
        })
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            
            // Обновляем все таблицы конфигураций
            const newTables = doc.querySelectorAll('.file-list .column table');
            const currentTables = document.querySelectorAll('.file-list .column table');
            
            newTables.forEach((newTable, index) => {
                if (currentTables[index]) {
                    currentTables[index].innerHTML = newTable.innerHTML;
                }
            });

            // Показываем уведомление об успехе
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'success',
                    title: 'Операция выполнена успешно!',
                    showConfirmButton: false,
                    timer: 2000
                });
            }

            // Обновляем выпадающий список, если нужно
            const selectedOption = optionSelect.value;
            if (selectedOption === '2' || selectedOption === '5' || selectedOption === '6') {
                populateClientSelect(selectedOption);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'error',
                    title: 'Ошибка',
                    text: 'Произошла ошибка при выполнении операции: ' + error.message
                });
            }
        });
    });

    // Инициализация при загрузке
    updateFormVisibility();
    optionSelect.addEventListener('change', updateFormVisibility);
});