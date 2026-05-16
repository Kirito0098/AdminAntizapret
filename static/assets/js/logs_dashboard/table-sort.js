(function () {
    const table = document.getElementById('persistedTrafficTable');
    const sortBtn = document.getElementById('sortByTotalTraffic');
    if (!table || !sortBtn) {
        return;
    }

    const tbody = table.querySelector('tbody');
    if (!tbody) {
        return;
    }

    let isDesc = true;

    function sortRows() {
        const rows = Array.from(tbody.querySelectorAll('tr[data-total-bytes]'));
        rows.sort(function (a, b) {
            const aVal = Number(a.getAttribute('data-total-bytes') || 0);
            const bVal = Number(b.getAttribute('data-total-bytes') || 0);
            return isDesc ? (bVal - aVal) : (aVal - bVal);
        });

        rows.forEach(function (row) {
            tbody.appendChild(row);
        });

        sortBtn.textContent = isDesc ? 'По убыванию' : 'По возрастанию';
    }

    sortBtn.addEventListener('click', function () {
        isDesc = !isDesc;
        sortRows();
    });

    sortRows();
})();
