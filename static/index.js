(() => {
    const toFaNumber = (value) => {
        try { return Number(value).toLocaleString('fa-IR'); }
        catch (error) { return String(value); }
    };

    const checkboxes = () => Array.from(document.querySelectorAll('.student-checkbox'));
    // هر دانش‌آموز یک بار شمارش می‌شود: کارت و جدول هرکدام checkbox خودشان را
    // دارند، پس انتخاب بین دو کپی هم‌گام می‌شود و شمارش بر اساس «مقدار» است.
    const selectedValues = () => Array.from(new Set(checkboxes().filter((box) => box.checked).map((box) => box.value)));
    const countLabels = Array.from(document.querySelectorAll('.selection-count'));
    const selectAll = document.querySelector('#select-all-students');
    const clearSelection = document.querySelector('#clear-selection');
    const bulkActions = document.querySelector('#bulkActions');
    const groupForm = document.getElementById('group-form');
    const floatClose = document.getElementById('bulkFloatClose');
    const actionButtons = Array.from(document.querySelectorAll('[data-group-action]'));

    // فرم عملیات در همان نوار انتخاب می‌ماند تا انتخاب همه و عملیات گروهی
    // روی موبایل یک کنترل واحد و بدون هم‌پوشانی بسازند.
    const floatForm = (on) => {
        if (!groupForm) return;
        groupForm.classList.toggle('is-floating', on);
        if (floatClose) floatClose.hidden = !on;
    };

    const clearAllSelection = () => {
        checkboxes().forEach((box) => { box.checked = false; });
        updateSelection();
    };

    function updateSelection() {
        const boxes = checkboxes();
        const values = new Set(boxes.filter((box) => box.checked).map((box) => box.value));
        const total = new Set(boxes.map((box) => box.value)).size;
        const count = values.size;

        countLabels.forEach((label) => { label.textContent = `${toFaNumber(count)} نفر انتخاب شده`; });
        if (selectAll) {
            selectAll.checked = total > 0 && count === total;
            selectAll.indeterminate = count > 0 && count < total;
        }
        actionButtons.forEach((button) => { button.disabled = count === 0; });
        if (clearSelection) clearSelection.hidden = count === 0;
        if (bulkActions) bulkActions.classList.toggle('has-selection', count > 0);
        document.documentElement.classList.toggle('has-selection', count > 0);
        floatForm(count > 0);
    }

    const syncDuplicates = (box) => {
        checkboxes().forEach((other) => {
            if (other !== box && other.value === box.value) other.checked = box.checked;
        });
    };
    checkboxes().forEach((box) => box.addEventListener('change', () => {
        syncDuplicates(box);
        updateSelection();
    }));

    if (selectAll) {
        selectAll.addEventListener('change', () => {
            checkboxes().forEach((box) => { box.checked = selectAll.checked; });
            updateSelection();
        });
    }

    if (clearSelection) {
        clearSelection.addEventListener('click', clearAllSelection);
    }

    window.clearSelectionFromFloat = clearAllSelection;
    if (floatClose) {
        floatClose.addEventListener('click', clearAllSelection);
    }

    const confirmations = {
        graduate: (count) => `آیا از فارغ‌التحصیل‌کردن ${toFaNumber(count)} دانش‌آموز انتخاب‌شده مطمئن هستید؟`,
        dropout: (count) => `آیا از ثبت «ترک تحصیل» برای ${toFaNumber(count)} دانش‌آموز انتخاب‌شده مطمئن هستید؟`,
        delete: (count) => `برای تغییر وضعیت ${toFaNumber(count)} دانش‌آموز به صفحهٔ مدیریت وضعیت منتقل می‌شوید. ادامه می‌دهید؟`,
    };

    window.groupAction = (action) => {
        const ids = selectedValues();
        if (!ids.length) {
            window.alert('لطفاً حداقل یک دانش‌آموز را انتخاب کنید.');
            return;
        }
        const ask = confirmations[action];
        if (ask && !window.confirm(ask(ids.length))) return;

        const form = document.querySelector('#group-form');
        if (!form) return;
        document.querySelector('#group-action').value = action;
        document.querySelector('#selected-ids').value = ids.join(',');
        if (action === 'wallcards') {
            const studioUrl = new URL('/report-print-layouts', window.location.href);
            studioUrl.searchParams.set('document', 'wall_cards');
            studioUrl.searchParams.set('ids', ids.join(','));
            window.open(studioUrl.toString(), '_blank', 'noopener');
            return;
        }
        form.action = action === 'print' ? '/print_selected' : '/group_action';
        form.target = action === 'print' ? '_blank' : '_self';
        form.submit();
    };

    const searchInput = document.querySelector('#q');
    const quickSearch = document.querySelector('#quickStudentSearch');
    const quickSearchToggle = document.querySelector('#quickStudentSearchToggle');
    const quickSearchPanel = document.querySelector('#quickStudentSearchPanel');
    const quickSearchInput = document.querySelector('#quickStudentSearchInput');
    const quickSearchClear = document.querySelector('#quickStudentSearchClear');
    const quickSearchStatus = document.querySelector('#quickStudentSearchStatus');
    const studentList = document.querySelector('.student-list');
    const studentCards = Array.from(document.querySelectorAll('.student-card, .student-row'));
    // فقط عناصر همان حالت نمایشی واقعی فعال شمرده می‌شوند؛ در موبایل جدول
    // حتی با نمای رومیزی «جدول کامل» به کارت‌های خلاصه تبدیل می‌شود.
    const inActiveView = (element) => {
        if (!studentList) return true;
        const desktopTable = studentList.dataset.view === 'table'
            && !window.matchMedia('(max-width: 720px)').matches;
        return desktopTable
            ? element.classList.contains('student-row')
            : element.classList.contains('student-card');
    };

    let refreshTablePagination = () => {};
    const studentTable = document.querySelector('.student-table');
    if (studentTable && studentTable.tBodies.length) {
        const tableBody = studentTable.tBodies[0];
        const tableWrap = studentTable.closest('.student-table-wrap');
        const pageStatus = tableWrap?.querySelector('[data-table-page-status]');
        const resultStatus = tableWrap?.querySelector('[data-table-result]');
        const previousPage = tableWrap?.querySelector('[data-table-page-previous]');
        const nextPage = tableWrap?.querySelector('[data-table-page-next]');
        const configuredPageSize = Number.parseInt(studentTable.dataset.pageSize || '20', 10);
        const pageSize = Number.isFinite(configuredPageSize) && configuredPageSize >= 0 ? configuredPageSize : 20;
        const collator = new Intl.Collator('fa', {numeric: true, sensitivity: 'base'});
        let currentPage = 0;
        let currentSort = studentTable.dataset.defaultSort || 'name';
        let currentDirection = studentTable.dataset.defaultDirection === 'desc' ? 'desc' : 'asc';
        const rows = () => Array.from(tableBody.querySelectorAll('tr.student-row'));
        const matchingRows = () => rows().filter((row) => !row.classList.contains('quick-search-hidden'));
        const syncStickyColumns = () => {
            const pickHeading = studentTable.querySelector('thead .student-table__pick');
            let offset = pickHeading ? pickHeading.getBoundingClientRect().width : 0;
            studentTable.querySelectorAll('thead [data-table-heading].student-table__column--pinned').forEach((heading) => {
                const field = heading.dataset.tableHeading;
                const width = heading.getBoundingClientRect().width;
                heading.style.insetInlineStart = `${offset}px`;
                studentTable.querySelectorAll('tbody [data-table-field]').forEach((cell) => {
                    if (cell.dataset.tableField === field) cell.style.insetInlineStart = `${offset}px`;
                });
                offset += width;
            });
        };
        window.addEventListener('resize', syncStickyColumns, {passive: true});

        const renderTablePage = () => {
            const allRows = rows();
            const matchedRows = matchingRows();
            const pages = pageSize > 0 ? Math.max(1, Math.ceil(matchedRows.length / pageSize)) : 1;
            currentPage = Math.min(Math.max(0, currentPage), pages - 1);
            const firstIndex = pageSize > 0 ? currentPage * pageSize : 0;
            const endIndex = pageSize > 0 ? Math.min(firstIndex + pageSize, matchedRows.length) : matchedRows.length;
            const visibleRows = new Set(matchedRows.slice(firstIndex, endIndex));
            allRows.forEach((row) => row.classList.toggle('table-page-hidden', !visibleRows.has(row)));
            if (pageStatus) pageStatus.textContent = `${toFaNumber(currentPage + 1)} / ${toFaNumber(pages)}`;
            if (resultStatus) {
                resultStatus.textContent = matchedRows.length
                    ? `نمایش ${toFaNumber(firstIndex + 1)} تا ${toFaNumber(endIndex)} از ${toFaNumber(matchedRows.length)} دانش‌آموز`
                    : 'هیچ دانش‌آموزی با این جست‌وجو پیدا نشد.';
            }
            if (previousPage) previousPage.disabled = currentPage <= 0;
            if (nextPage) nextPage.disabled = currentPage >= pages - 1;
        };
        refreshTablePagination = renderTablePage;

        const sortTable = (field, direction) => {
            const sortedRows = rows().sort((first, second) => {
                const firstValue = (first.getAttribute(`data-sort-${field}`) || '').trim();
                const secondValue = (second.getAttribute(`data-sort-${field}`) || '').trim();
                if (!firstValue && secondValue) return 1;
                if (firstValue && !secondValue) return -1;
                const comparison = collator.compare(firstValue, secondValue);
                return direction === 'desc' ? -comparison : comparison;
            });
            sortedRows.forEach((row) => tableBody.appendChild(row));
            syncStickyColumns();
            currentSort = field;
            currentDirection = direction;
            studentTable.querySelectorAll('[data-table-sort-key]').forEach((heading) => {
                const active = heading.dataset.tableSortKey === currentSort;
                heading.setAttribute('aria-sort', active ? (currentDirection === 'asc' ? 'ascending' : 'descending') : 'none');
            });
            studentTable.querySelectorAll('[data-table-sort]').forEach((button) => {
                const indicator = button.querySelector('span');
                if (!indicator) return;
                indicator.textContent = button.dataset.tableSort !== currentSort
                    ? '↕' : (currentDirection === 'asc' ? '↑' : '↓');
            });
            currentPage = 0;
            renderTablePage();
        };
        studentTable.querySelectorAll('[data-table-sort]').forEach((button) => {
            button.addEventListener('click', () => {
                const field = button.dataset.tableSort;
                const direction = field === currentSort && currentDirection === 'asc' ? 'desc' : 'asc';
                sortTable(field, direction);
            });
        });
        previousPage?.addEventListener('click', () => {
            currentPage = Math.max(0, currentPage - 1);
            renderTablePage();
        });
        nextPage?.addEventListener('click', () => {
            currentPage += 1;
            renderTablePage();
        });
        sortTable(currentSort, currentDirection);
    }

    const normalizeSearch = (value) => String(value || '').trim().toLocaleLowerCase('fa').replace(/\s+/g, ' ');
    const setQuickSearchOpen = (open) => {
        if (!quickSearchPanel || !quickSearchToggle) return;
        quickSearchPanel.hidden = !open;
        quickSearchToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open && quickSearchInput) window.setTimeout(() => quickSearchInput.focus(), 0);
    };
    const updateQuickSearch = () => {
        if (!quickSearchInput || !quickSearchStatus) return;
        const query = normalizeSearch(quickSearchInput.value);
        const total = studentCards.filter(inActiveView).length;
        let visible = 0;
        studentCards.forEach((card) => {
            const matches = !query || normalizeSearch(card.textContent).includes(query);
            card.classList.toggle('quick-search-hidden', !matches);
            if (matches && inActiveView(card)) visible += 1;
        });
        quickSearchStatus.textContent = query
            ? `${toFaNumber(visible)} دانش‌آموز از ${toFaNumber(total)} نتیجه نمایش داده می‌شود.`
            : 'برای شروع، نام دانش‌آموز را بنویسید.';
        refreshTablePagination();
    };
    if (quickSearchToggle) quickSearchToggle.addEventListener('click', () => setQuickSearchOpen(!quickSearchPanel || quickSearchPanel.hidden));
    if (quickSearchInput) quickSearchInput.addEventListener('input', updateQuickSearch);
    if (quickSearchClear) quickSearchClear.addEventListener('click', () => {
        if (!quickSearchInput) return;
        quickSearchInput.value = '';
        updateQuickSearch();
        quickSearchInput.focus();
    });
    if (quickSearch) quickSearch.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            setQuickSearchOpen(false);
            quickSearchToggle?.focus();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
        const target = event.target;
        const tagName = target && target.tagName ? target.tagName.toLowerCase() : '';
        if (['input', 'select', 'textarea'].includes(tagName) || (target && target.isContentEditable)) return;
        const targetInput = searchInput || quickSearchInput;
        if (!targetInput) return;
        event.preventDefault();
        if (targetInput === quickSearchInput) setQuickSearchOpen(true);
        const panel = targetInput.closest('details');
        if (panel) panel.open = true;
        targetInput.focus();
        targetInput.select();
    });

    const progress = document.createElement('div');
    progress.className = 'page-progress no-print';
    progress.setAttribute('aria-hidden', 'true');
    document.body.appendChild(progress);
    let progressTimer = null;

    function startProgress() {
        window.clearTimeout(progressTimer);
        progress.classList.add('is-active');
        document.body.setAttribute('aria-busy', 'true');
        progressTimer = window.setTimeout(stopProgress, 10000);
    }

    function stopProgress() {
        window.clearTimeout(progressTimer);
        progress.classList.remove('is-active');
        document.body.removeAttribute('aria-busy');
    }

    window.addEventListener('pageshow', stopProgress);

    function isPlainNavigation(link) {
        if (!link || link.target === '_blank' || link.hasAttribute('download')) return false;
        const href = link.getAttribute('href') || '';
        if (!href || href.startsWith('#') || /^(mailto:|tel:|javascript:)/i.test(href)) return false;
        try {
            return new URL(link.href, window.location.href).origin === window.location.origin;
        } catch (error) {
            return false;
        }
    }

    document.addEventListener('click', (event) => {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const target = event.target;
        const link = target && target.closest ? target.closest('a') : null;
        if (isPlainNavigation(link)) startProgress();
    }, true);

    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (form.method.toLowerCase() === 'get') {
            startProgress();
            return;
        }
        if (form.target === '_blank') return;
        const submitter = event.submitter;
        if (submitter && submitter.classList) submitter.classList.add('is-loading');
        actionButtons.forEach((button) => { button.disabled = true; });
        window.setTimeout(() => {
            actionButtons.forEach((button) => {
                if (button.classList) button.classList.remove('is-loading');
            });
            updateSelection();
        }, 8000);
    }, true);

    updateSelection();
})();
