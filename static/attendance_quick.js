(() => {
    const root = document.querySelector('.aw-quickview');
    if (!root) return;

    const WEEKDAYS = ['شنبه', 'یکشنبه', 'دوشنبه', 'سهشنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه'];
    const form = root.querySelector('form[data-quick-form]');
    const rows = () => Array.from(root.querySelectorAll('.aw-quick-row'));
    const dateInput = root.querySelector('input[name="date"]');
    const monthSelect = root.querySelector('#awQuickMonth');
    const yearSelect = root.querySelector('#awQuickYear');
    const calendar = root.querySelector('#awQuickCalendar');
    const selectedLabel = root.querySelector('[data-selected-date]');
    const weekdayLabel = root.querySelector('.aw-weekday');
    const recordPill = root.querySelector('.aw-record-pill, .aw-empty-pill');
    const search = root.querySelector('#awQuickSearch');
    const emptyFilter = root.querySelector('.aw-empty-filter');
    const countNode = root.querySelector('[data-quick-count]');
    const summaryNode = root.querySelector('[data-save-summary]');
    const submitButton = root.querySelector('.aw-submit');
    const markedDates = new Set(JSON.parse(root.dataset.marked || '[]'));
    const today = JSON.parse(root.dataset.today || '{}');
    let dirty = false;

    function fa(value) {
        return String(value ?? '').replace(/[0-9]/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]);
    }

    function isLeapYear(year) {
        return [1, 5, 9, 13, 17, 21, 25, 29].includes(year % 33);
    }

    function daysInMonth(month, year) {
        if (month <= 6) return 31;
        if (month <= 11) return 30;
        return isLeapYear(year) ? 30 : 29;
    }

    function dayNumber(year, month, day) {
        let leaps = 0;
        for (let current = 1; current < year; current += 1) {
            if (isLeapYear(current)) leaps += 1;
        }
        let total = (year - 1) * 365 + leaps;
        for (let current = 1; current < month; current += 1) {
            total += current <= 6 ? 31 : (current <= 11 ? 30 : (isLeapYear(year) ? 30 : 29));
        }
        return total + day;
    }

    function weekdayOf(date) {
        const parts = date.split('/').map(Number);
        if (parts.length !== 3 || parts.some(Number.isNaN)) return '';
        const todayIndex = parseInt(root.dataset.todayIndex || '0', 10);
        const delta = dayNumber(...parts) - dayNumber(today.year, today.month, today.day);
        return WEEKDAYS[((todayIndex + delta) % 7 + 7) % 7];
    }

    function pad(value) { return String(value).padStart(2, '0'); }

    function selectedParts() {
        const parts = (dateInput?.value || '').split('/').map(Number);
        return { year: parts[0] || 0, month: parts[1] || 0, day: parts[2] || 0 };
    }

    function renderCalendar() {
        if (!calendar || !monthSelect || !yearSelect) return;
        const month = parseInt(monthSelect.value, 10);
        const year = parseInt(yearSelect.value, 10);
        const selected = selectedParts();
        calendar.innerHTML = '';
        for (let day = 1; day <= daysInMonth(month, year); day += 1) {
            const date = `${year}/${pad(month)}/${pad(day)}`;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'aw-day';
            button.textContent = fa(day);
            button.dataset.date = date;
            if (markedDates.has(date)) button.classList.add('has-record');
            if (today.year === year && today.month === month && today.day === day) button.classList.add('is-today');
            if (selected.year === year && selected.month === month && selected.day === day) button.classList.add('is-selected');
            button.addEventListener('click', () => navigateToDate(date));
            calendar.appendChild(button);
        }
    }

    function updateDateSummary(date) {
        if (selectedLabel) selectedLabel.textContent = fa(date);
        if (weekdayLabel) weekdayLabel.textContent = weekdayOf(date);
        if (recordPill) {
            const hasRecord = markedDates.has(date);
            recordPill.className = hasRecord ? 'aw-record-pill' : 'aw-empty-pill';
            recordPill.textContent = hasRecord ? 'این تاریخ سابقه ثبت دارد' : 'هنوز ثبت نشده';
        }
    }

    function navigateToDate(date) {
        if (dateInput?.value === date) {
            updateDateSummary(date);
            renderCalendar();
            return;
        }
        if (dirty && !window.confirm('انتخابهای ذخیرهنشده دارید. با تغییر تاریخ از بین میروند. ادامه میدهید؟')) {
            renderCalendar();
            return;
        }
        const url = new URL(window.location.href);
        url.searchParams.set('date', date);
        window.location.assign(url.toString());
    }

    function updateCounts() {
        const total = rows().length;
        const absent = rows().filter((row) => row.querySelector('.aw-quick-check')?.checked).length;
        if (countNode) countNode.textContent = `${fa(absent)} نفر غایب از ${fa(total)} دانشآموز`;
        if (summaryNode) {
            summaryNode.textContent = absent
                ? `${fa(absent)} غایب · ${fa(total - absent)} حاضر خودکار`
                : `${fa(total)} حاضر خودکار`;
        }
    }

    function applyFilter() {
        const query = (search?.value || '').trim().toLowerCase();
        let visible = 0;
        rows().forEach((row) => {
            const name = (row.dataset.name || '').toLowerCase();
            const code = (row.dataset.code || '').toLowerCase();
            const show = !query || name.includes(query) || code.includes(query);
            row.classList.toggle('is-hidden', !show);
            if (show) visible += 1;
        });
        if (emptyFilter) emptyFilter.hidden = visible !== 0 || rows().length === 0;
    }

    function setAll(checked) {
        rows().forEach((row) => {
            const check = row.querySelector('.aw-quick-check');
            if (check) check.checked = checked;
            row.classList.toggle('is-absent', checked);
        });
        dirty = true;
        updateCounts();
        applyFilter();
    }

    rows().forEach((row) => {
        const check = row.querySelector('.aw-quick-check');
        if (!check) return;
        check.addEventListener('change', () => {
            row.classList.toggle('is-absent', check.checked);
            dirty = true;
            updateCounts();
            applyFilter();
        });
    });

    root.querySelectorAll('[data-quick-all]').forEach((button) => {
        button.addEventListener('click', () => setAll(true));
    });
    root.querySelectorAll('[data-quick-none]').forEach((button) => {
        button.addEventListener('click', () => setAll(false));
    });

    if (search) search.addEventListener('input', applyFilter);
    if (monthSelect) monthSelect.addEventListener('change', renderCalendar);
    if (yearSelect) yearSelect.addEventListener('change', renderCalendar);
    if (form) {
        form.addEventListener('submit', () => {
            dirty = false;
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = '<i class="cil-sync" aria-hidden="true"></i> در حال ذخیره...';
            }
        });
        window.addEventListener('beforeunload', (event) => {
            if (!dirty) return;
            event.preventDefault();
            event.returnValue = '';
        });
    }
    document.addEventListener('keydown', (event) => {
        if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || !search) return;
        const tag = event.target?.tagName?.toLowerCase();
        if (['input', 'select', 'textarea'].includes(tag)) return;
        event.preventDefault();
        search.focus();
        search.select();
    });

    updateDateSummary(dateInput?.value || '');
    renderCalendar();
    updateCounts();
    applyFilter();
})();
