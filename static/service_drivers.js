(() => {
    const root = document.querySelector('.service-dashboard');
    if (!root) return;

    const destinationMap = JSON.parse(root.dataset.destinationMap || '{}');
    const destinationFields = root.querySelector('#destinationFields');
    const bulkDestinationForm = root.querySelector('#bulkDestForm');
    const bulkAssignmentForm = root.querySelector('#bulkAssignForm');
    const searchInput = root.querySelector('#studentSearch');
    const selectAll = root.querySelector('#selectAllStudents');
    const selectionSummary = root.querySelector('#selectionSummary');
    const visibleCount = root.querySelector('#visibleStudentCount');
    const bulkDriver = root.querySelector('#bulkDriver');
    const bulkDestination = root.querySelector('#bulkDestination');

    function toFa(value) {
        return String(value ?? '').replace(/[0-9]/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]);
    }

    function bindDestinationRow(row) {
        const remove = row.querySelector('.sd-remove-destination');
        if (!remove) return;
        remove.addEventListener('click', () => {
            const rows = destinationFields.querySelectorAll('.sd-destination-row');
            if (rows.length > 1) row.remove();
            else row.querySelector('input').value = '';
        });
    }

    function addDestinationRow() {
        const row = document.createElement('div');
        row.className = 'sd-destination-row';
        row.innerHTML = '<input name="destinations[]" placeholder="شهر یا روستای مقصد"><button class="sd-link-button sd-remove-destination" type="button">حذف</button>';
        destinationFields.appendChild(row);
        bindDestinationRow(row);
        row.querySelector('input').focus();
    }

    root.querySelectorAll('.sd-destination-row').forEach(bindDestinationRow);
    root.querySelector('#addDestination')?.addEventListener('click', addDestinationRow);

    function fillDestinations(select, driverId, selectedId) {
        if (!select) return;
        const destinations = destinationMap[String(driverId)] || [];
        select.innerHTML = '<option value="">بدون مقصد مشخص</option>';
        destinations.forEach((item) => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = item.destination;
            if (String(item.id) === String(selectedId || '')) option.selected = true;
            select.appendChild(option);
        });
        select.disabled = !driverId;
    }

    root.querySelectorAll('.sd-student-driver').forEach((driverSelect) => {
        const row = driverSelect.closest('.sd-student');
        const destinationSelect = row?.querySelector('.sd-student-destination');
        fillDestinations(destinationSelect, driverSelect.value, driverSelect.dataset.currentDestination);
        driverSelect.addEventListener('change', () => fillDestinations(destinationSelect, driverSelect.value, ''));
    });

    if (bulkDriver) {
        fillDestinations(bulkDestination, bulkDriver.value, '');
        bulkDriver.addEventListener('change', () => fillDestinations(bulkDestination, bulkDriver.value, ''));
    }

    function bulkDestinationValues(row) {
        const values = [];
        row.querySelectorAll('.sd-bulk-dst-chip').forEach((chip) => {
            const value = (chip.dataset.destination || chip.textContent || '').trim();
            if (value && !values.includes(value)) values.push(value);
        });
        row.querySelectorAll('.sd-bulk-dst-input').forEach((input) => {
            const value = input.value.trim();
            if (value && !values.includes(value)) values.push(value);
        });
        return values.slice(0, 20);
    }

    if (bulkDestinationForm) {
        bulkDestinationForm.addEventListener('submit', () => {
            const data = {};
            root.querySelectorAll('#bulkDriverRows .sd-bulk-row').forEach((row) => {
                const driverId = row.dataset.driverId;
                if (driverId) data[driverId] = bulkDestinationValues(row);
            });
            const payload = root.querySelector('#destinationsJson');
            if (payload) payload.value = JSON.stringify(data);
            const button = root.querySelector('#saveAllBtn');
            if (button) {
                button.disabled = true;
                button.innerHTML = '<i class="cil-sync" aria-hidden="true"></i> در حال ذخیره...';
            }
        });
    }

    root.querySelectorAll('.sd-bulk-add-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const row = button.closest('.sd-bulk-row');
            const container = row?.querySelector('[data-dests-container]');
            if (!container) return;
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'sd-bulk-dst-input';
            input.placeholder = 'شهر یا روستا';
            container.appendChild(input);
            input.focus();
        });
    });

    root.querySelectorAll('.sd-bulk-dst-remove').forEach((button) => {
        button.addEventListener('click', () => button.closest('.sd-bulk-dst-chip')?.remove());
    });

    function studentRows() { return Array.from(root.querySelectorAll('.sd-student')); }

    function checkedBoxes() { return studentRows().map((row) => row.querySelector('.student-check')).filter((box) => box?.checked); }

    function syncSelection() {
        const rows = studentRows();
        const visibleRows = rows.filter((row) => !row.hidden);
        const checked = checkedBoxes();
        if (selectionSummary) selectionSummary.textContent = `${toFa(checked.length)} نفر انتخاب شده`;
        if (visibleCount) visibleCount.textContent = `${toFa(visibleRows.length)} دانش‌آموز`;
        if (selectAll) {
            const visibleChecked = visibleRows.filter((row) => row.querySelector('.student-check')?.checked).length;
            selectAll.disabled = visibleRows.length === 0;
            selectAll.checked = visibleRows.length > 0 && visibleChecked === visibleRows.length;
            selectAll.indeterminate = visibleChecked > 0 && visibleChecked < visibleRows.length;
        }
    }

    function applySearch() {
        const query = (searchInput?.value || '').trim().toLocaleLowerCase('fa');
        studentRows().forEach((row) => {
            const haystack = (row.dataset.search || '').toLocaleLowerCase('fa');
            row.hidden = Boolean(query && !haystack.includes(query));
        });
        syncSelection();
    }

    searchInput?.addEventListener('input', applySearch);
    root.querySelectorAll('.student-check').forEach((checkbox) => checkbox.addEventListener('change', syncSelection));
    selectAll?.addEventListener('change', () => {
        studentRows().forEach((row) => {
            if (!row.hidden) {
                const checkbox = row.querySelector('.student-check');
                if (checkbox) checkbox.checked = selectAll.checked;
            }
        });
        syncSelection();
    });

    bulkAssignmentForm?.addEventListener('submit', (event) => {
        bulkAssignmentForm.querySelectorAll('input[data-bulk-student]').forEach((input) => input.remove());
        const selected = checkedBoxes();
        if (!selected.length) {
            event.preventDefault();
            window.alert('حداقل یک دانش‌آموز را انتخاب کنید.');
            return;
        }
        selected.forEach((checkbox) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'student_ids';
            input.value = checkbox.dataset.studentId;
            input.dataset.bulkStudent = '1';
            bulkAssignmentForm.appendChild(input);
        });
    });

    syncSelection();
})();
