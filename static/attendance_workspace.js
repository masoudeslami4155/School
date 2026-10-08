(() => {
    const root = document.querySelector('.attendance-workspace');
    if (!root) return;

    const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
    const WEEKDAYS = ['شنبه', 'یک‌شنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه'];
    const form = root.querySelector('form[data-attendance-form]');
    const cards = () => Array.from(root.querySelectorAll('.aw-person-card'));
    const dateInput = root.querySelector('#awDateInput');
    const monthSelect = root.querySelector('#awMonthSelect');
    const yearSelect = root.querySelector('#awYearSelect');
    const calendar = root.querySelector('#awCalendar');
    const selectedLabel = root.querySelector('[data-selected-date]');
    const weekdayLabel = root.querySelector('.aw-weekday');
    const recordPill = root.querySelector('.aw-record-pill, .aw-empty-pill');
    const search = root.querySelector('#awSearch');
    const emptyFilter = root.querySelector('.aw-empty-filter');
    const submitButton = root.querySelector('.aw-submit');
    const markedDates = new Set(JSON.parse(root.dataset.marked || '[]'));
    const today = JSON.parse(root.dataset.today || '{}');
    let dirty = false;
    let activeFilter = 'all';

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
        if (dirty && !window.confirm('تغییرات ذخیره‌نشده دارید. با تغییر تاریخ، این تغییرات از بین می‌رود. ادامه می‌دهید؟')) {
            renderCalendar();
            return;
        }
        const url = new URL(window.location.href);
        url.searchParams.set('date', date);
        window.location.assign(url.toString());
    }

    function cardStatus(card) {
        return card.querySelector('.aw-status-input')?.value || '';
    }

    function cardChanged(card) {
        const initial = card.dataset.initial || '';
        const touched = Boolean(card.dataset.touched);
        const statusChanged = touched && (!initial || initial !== cardStatus(card));
        const lateInput = card.querySelector('.aw-late-field input');
        const lateChanged = Boolean(lateInput && touched && String(lateInput.value || 0) !== String(card.dataset.initialLate || 0));
        return statusChanged || lateChanged;
    }

    function updateCard(card, status, touched = true) {
        card.dataset.status = status;
        if (touched) card.dataset.touched = '1';
        card.querySelectorAll('.aw-status-btn').forEach((button) => {
            const active = button.dataset.status === status;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        const input = card.querySelector('.aw-status-input');
        if (input) input.value = status;
        const printValue = card.querySelector('.aw-print-status-value');
        if (printValue) printValue.textContent = status;
        const printLate = card.querySelector('.aw-print-late');
        if (printLate) printLate.style.display = status === 'تاخیر' ? 'inline' : 'none';
        const state = card.querySelector('.aw-person-state');
        if (state && touched) {
            state.className = 'aw-person-state is-saved';
            state.textContent = 'ویرایش‌شده';
        }
        card.classList.toggle('is-changed', cardChanged(card));
    }

    function updateStats() {
        const counts = {};
        let changed = 0;
        let unchanged = 0;
        cards().forEach((card) => {
            const status = cardStatus(card);
            counts[status] = (counts[status] || 0) + 1;
            if (card.classList.contains('is-changed')) changed += 1;
            if (card.dataset.initial && card.dataset.initial === status) unchanged += 1;
        });
        root.querySelectorAll('[data-stat]').forEach((node) => {
            node.textContent = fa(counts[node.dataset.stat] || 0);
        });
        root.querySelectorAll('[data-stat-total]').forEach((node) => { node.textContent = fa(cards().length); });
        root.querySelectorAll('[data-stat-unchanged]').forEach((node) => { node.textContent = fa(unchanged); });
        const summary = Object.entries(counts).map(([status, count]) => `${status}: ${fa(count)}`);
        const summaryNode = root.querySelector('[data-save-summary]');
        if (summaryNode) summaryNode.textContent = summary.join(' · ') + (changed ? ` · ${fa(changed)} تغییر` : '');
        const hint = root.querySelector('[data-dirty-hint]');
        if (hint) hint.hidden = !dirty;
        if (form) form.dataset.dirty = dirty ? '1' : '0';
    }

    function markDirty() { dirty = true; updateStats(); }

    function matches(card) {
        const query = (search?.value || '').trim().toLowerCase();
        const name = (card.dataset.name || '').toLowerCase();
        const code = (card.dataset.code || '').toLowerCase();
        if (query && !name.includes(query) && !code.includes(query)) return false;
        const status = cardStatus(card);
        if (activeFilter === 'changed') return card.classList.contains('is-changed');
        if (activeFilter === 'unmarked') return !card.dataset.initial;
        if (activeFilter === 'attention') return ['غایب', 'تاخیر'].includes(status);
        return true;
    }

    function applyFilter() {
        let visible = 0;
        cards().forEach((card) => {
            const show = matches(card);
            card.classList.toggle('is-hidden', !show);
            if (show) visible += 1;
        });
        if (emptyFilter) emptyFilter.hidden = visible !== 0 || cards().length === 0;
    }

    cards().forEach((card) => {
        updateCard(card, cardStatus(card), false);
        card.querySelectorAll('.aw-status-btn').forEach((button) => {
            button.addEventListener('click', () => {
                updateCard(card, button.dataset.status);
                markDirty();
                applyFilter();
            });
        });
        const lateInput = card.querySelector('.aw-late-field input');
        if (lateInput) {
            lateInput.addEventListener('input', () => {
                const output = card.querySelector('.aw-print-late-value');
                if (output) output.textContent = fa(lateInput.value || 0);
                card.dataset.touched = '1';
                card.classList.toggle('is-changed', cardChanged(card));
                markDirty();
            });
        }
    });

    root.querySelectorAll('[data-set-all]').forEach((button) => {
        button.addEventListener('click', () => {
            cards().forEach((card) => updateCard(card, button.dataset.setAll));
            markDirty();
            applyFilter();
        });
    });
    root.querySelectorAll('.aw-tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            activeFilter = tab.dataset.filter || 'all';
            root.querySelectorAll('.aw-tab').forEach((other) => other.classList.toggle('is-active', other === tab));
            applyFilter();
        });
    });
    if (search) search.addEventListener('input', applyFilter);
    if (monthSelect) monthSelect.addEventListener('change', renderCalendar);
    if (yearSelect) yearSelect.addEventListener('change', renderCalendar);
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
    updateStats();
    applyFilter();
})();
