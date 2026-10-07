(() => {
    const root = document.querySelector('.attendance-daily');
    if (!root) return;

    const WEEKDAYS = ['شنبه', 'یک‌شنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه'];
    const form = root.querySelector('#adForm');
    const cards = () => Array.from(root.querySelectorAll('.student-card'));
    const dateInput = root.querySelector('#adDateInput');
    const monthSelect = root.querySelector('#adMonthSelect');
    const yearSelect = root.querySelector('#adYearSelect');
    const dayGrid = root.querySelector('#adDayGrid');
    const selectedLabel = root.querySelector('[data-selected-date]');
    const weekdayLabel = root.querySelector('.ad-weekday');
    const markedBadge = root.querySelector('.ad-marked-badge, .ad-unmarked-badge');
    const dirtyHint = root.querySelector('[data-dirty-hint]');
    const savebarSummary = root.querySelector('[data-savebar-summary]');
    const submitButton = root.querySelector('#adSubmitBtn');
    const searchInput = root.querySelector('#adSearchInput');
    const emptyFilter = root.querySelector('#adEmptyFilter');
    const markedDates = new Set(JSON.parse(root.dataset.marked || '[]'));
    const today = JSON.parse(root.dataset.today || '{}');
    let dirty = false;

    function toFa(value) {
        try { return Number(value).toLocaleString('fa-IR'); }
        catch (error) { return String(value); }
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
        for (let current = 1; current <= year - 1; current += 1) {
            if (isLeapYear(current)) leaps += 1;
        }
        let total = (year - 1) * 365 + leaps;
        for (let current = 1; current < month; current += 1) {
            total += current <= 6 ? 31 : (current <= 11 ? 30 : (isLeapYear(year) ? 30 : 29));
        }
        return total + day;
    }

    function weekdayOf(dateStr) {
        const parts = (dateStr || '').split('/').map(Number);
        if (parts.length !== 3 || parts.some(Number.isNaN)) return '';
        const index = parseInt(root.dataset.todayIndex || '0', 10);
        const delta = dayNumber(parts[0], parts[1], parts[2]) - dayNumber(today.year, today.month, today.day);
        return WEEKDAYS[((index + delta) % 7 + 7) % 7];
    }

    function pad(value) { return String(value).padStart(2, '0'); }

    function renderDays() {
        if (!dayGrid || !monthSelect || !yearSelect) return;
        const month = parseInt(monthSelect.value, 10);
        const year = parseInt(yearSelect.value, 10);
        const selectedDay = dateInput ? parseInt(dateInput.value.slice(8, 10), 10) : 0;
        const selectedMonth = dateInput ? parseInt(dateInput.value.slice(5, 7), 10) : 0;
        const selectedYear = dateInput ? parseInt(dateInput.value.slice(0, 4), 10) : 0;
        dayGrid.innerHTML = '';
        for (let day = 1; day <= daysInMonth(month, year); day += 1) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = toFa(day);
            const dateStr = `${year}/${pad(month)}/${pad(day)}`;
            if (markedDates.has(dateStr)) button.classList.add('has-record');
            if (today.year === year && today.month === month && today.day === day) button.classList.add('is-today');
            if (selectedYear === year && selectedMonth === month && selectedDay === day) button.classList.add('is-selected');
            button.addEventListener('click', () => selectDate(dateStr));
            dayGrid.appendChild(button);
        }
    }

    function selectDate(dateStr) {
        if (dateInput) dateInput.value = dateStr;
        if (selectedLabel) selectedLabel.textContent = toFa(dateStr).replace(/,/g, '');
        if (weekdayLabel) weekdayLabel.textContent = weekdayOf(dateStr);
        if (markedBadge) {
            const hasRecord = markedDates.has(dateStr);
            markedBadge.className = hasRecord ? 'ad-marked-badge' : 'ad-unmarked-badge';
            markedBadge.textContent = hasRecord ? 'این تاریخ سابقه ثبت دارد' : 'هنوز ثبت نشده';
        }
        renderDays();
    }

    function cardStatus(card) {
        const input = card.querySelector('.status-input');
        return input ? input.value : '';
    }

    function updateCard(card, status) {
        card.dataset.status = status;
        card.querySelectorAll('.status-buttons button').forEach((button) => {
            const active = button.dataset.status === status;
            button.classList.toggle('active', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        const input = card.querySelector('.status-input');
        if (input) input.value = status;
        const initial = card.dataset.initial || '';
        card.classList.toggle('is-changed', initial ? status !== initial : true);
    }

    function updateStats() {
        const summary = {};
        let unchanged = 0;
        let changed = 0;
        cards().forEach((card) => {
            const status = cardStatus(card);
            summary[status] = (summary[status] || 0) + 1;
            if (card.classList.contains('is-changed')) changed += 1;
            if (card.dataset.initial && card.dataset.initial === status) unchanged += 1;
        });
        root.querySelectorAll('[data-stat]').forEach((node) => {
            node.textContent = toFa(summary[node.dataset.stat] || 0);
        });
        root.querySelectorAll('[data-stat-unchanged]').forEach((node) => {
            node.textContent = toFa(unchanged);
        });
        if (savebarSummary) {
            const parts = Object.keys(summary).map((status) => `${status}: ${toFa(summary[status])}`);
            savebarSummary.textContent = parts.join(' · ') + (changed ? ` · ${toFa(changed)} تغییر` : '');
        }
        if (dirtyHint) dirtyHint.hidden = !dirty;
        if (form) form.dataset.dirty = dirty ? '1' : '0';
    }

    function markDirty() {
        dirty = true;
        updateStats();
    }

    root.querySelectorAll('.status-buttons button').forEach((button) => {
        button.addEventListener('click', () => {
            const card = button.closest('.student-card');
            if (!card) return;
            updateCard(card, button.dataset.status);
            markDirty();
        });
    });

    root.querySelectorAll('[data-set-all]').forEach((button) => {
        button.addEventListener('click', () => {
            const status = button.dataset.setAll;
            cards().forEach((card) => updateCard(card, status));
            markDirty();
        });
    });

    function matchesFilter(card, filter, query) {
        const name = (card.dataset.name || '').toLowerCase();
        const code = (card.dataset.code || '').toLowerCase();
        if (query && !name.includes(query) && !code.includes(query)) return false;
        if (filter === 'changed') return card.classList.contains('is-changed');
        if (filter === 'unmarked') return !card.dataset.initial;
        if (filter === 'absent') return ['غایب', 'تاخیر'].includes(cardStatus(card));
        return true;
    }

    let activeFilter = 'all';

    function applyFilter() {
        const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
        let visible = 0;
        cards().forEach((card) => {
            const show = matchesFilter(card, activeFilter, query);
            card.classList.toggle('is-hidden', !show);
            if (show) visible += 1;
        });
        if (emptyFilter) emptyFilter.hidden = visible !== 0 || cards().length === 0;
    }

    root.querySelectorAll('.ad-tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            activeFilter = tab.dataset.filter || 'all';
            root.querySelectorAll('.ad-tab').forEach((other) => other.classList.toggle('is-active', other === tab));
            applyFilter();
        });
    });

    if (searchInput) {
        searchInput.addEventListener('input', applyFilter);
        document.addEventListener('keydown', (event) => {
            if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
            const target = event.target;
            const tagName = target && target.tagName ? target.tagName.toLowerCase() : '';
            if (['input', 'select', 'textarea'].includes(tagName) || (target && target.isContentEditable)) return;
            event.preventDefault();
            searchInput.focus();
            searchInput.select();
        });
    }

    if (monthSelect) monthSelect.addEventListener('change', () => {
        if (yearSelect) {
            const dateStr = `${yearSelect.value}/${pad(parseInt(monthSelect.value, 10))}/01`;
            selectDate(dateStr);
        }
    });
    if (yearSelect) yearSelect.addEventListener('change', () => {
        if (monthSelect) {
            const dateStr = `${yearSelect.value}/${pad(parseInt(monthSelect.value, 10))}/01`;
            selectDate(dateStr);
        }
    });

    if (form) {
        form.addEventListener('submit', () => {
            dirty = false;
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = '<i class="cil-sync" aria-hidden="true"></i> در حال ذخیره…';
            }
        });
        window.addEventListener('beforeunload', (event) => {
            if (!dirty) return;
            event.preventDefault();
            event.returnValue = '';
        });
    }

    renderDays();
    updateStats();
    applyFilter();
})();
