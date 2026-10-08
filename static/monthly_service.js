(() => {
    const root = document.querySelector('.monthly-service');
    if (!root) return;

    const toggle = root.querySelector('[data-toggle-filters]');
    const panel = root.querySelector('#msFilters');
    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function syncToggle() {
        if (toggle && panel) toggle.setAttribute('aria-expanded', panel.open ? 'true' : 'false');
    }

    if (toggle && panel) {
        toggle.addEventListener('click', () => {
            panel.open = !panel.open;
            if (panel.open && panel.scrollIntoView) {
                panel.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
            }
            syncToggle();
        });
        panel.addEventListener('toggle', syncToggle);
        syncToggle();
    }

    if (panel) {
        const form = panel.querySelector('form');
        if (form) {
            form.addEventListener('submit', () => {
                const submit = form.querySelector('button[type="submit"]');
                if (submit) submit.classList.add('is-loading');
            });
        }
    }

    const checkboxes = () => Array.from(root.querySelectorAll('.ms-row-check'));
    const selectAll = root.querySelector('#msSelectAll');
    const countLabel = root.querySelector('.ms-bulk__count');
    const printButton = root.querySelector('#msPrintSelected');
    const clearButton = root.querySelector('#msClearSelection');
    const printUrl = root.dataset.printUrl || '/monthly_service/print';

    function updateSelection() {
        const boxes = checkboxes();
        const count = boxes.filter((box) => box.checked).length;
        if (countLabel) {
            try { countLabel.textContent = `${count.toLocaleString('fa-IR')} ردیف انتخاب شده`; }
            catch (error) { countLabel.textContent = `${count} ردیف انتخاب شده`; }
        }
        if (selectAll) {
            selectAll.checked = boxes.length > 0 && count === boxes.length;
            selectAll.indeterminate = count > 0 && count < boxes.length;
        }
        if (printButton) printButton.disabled = count === 0;
        if (clearButton) clearButton.hidden = count === 0;
        root.classList.toggle('has-selection', count > 0);
    }

    checkboxes().forEach((box) => box.addEventListener('change', updateSelection));

    if (selectAll) {
        selectAll.addEventListener('change', () => {
            checkboxes().forEach((box) => { box.checked = selectAll.checked; });
            updateSelection();
        });
    }

    const selectAllButton = root.querySelector('#msSelectAllButton');
    if (selectAllButton) {
        selectAllButton.addEventListener('click', () => {
            const shouldCheck = checkboxes().some((box) => !box.checked);
            checkboxes().forEach((box) => { box.checked = shouldCheck; });
            if (selectAll) selectAll.checked = shouldCheck;
            updateSelection();
        });
    }

    if (clearButton) {
        clearButton.addEventListener('click', () => {
            checkboxes().forEach((box) => { box.checked = false; });
            updateSelection();
        });
    }

    if (printButton) {
        printButton.addEventListener('click', () => {
            const ids = checkboxes().filter((box) => box.checked).map((box) => box.value);
            if (!ids.length) return;
            const separator = printUrl.includes('?') ? '&' : '?';
            window.open(`${printUrl}${separator}kind=both&ids=${encodeURIComponent(ids.join(','))}`, '_blank');
        });
    }

    const search = root.querySelector('#msSearch');
    document.addEventListener('keydown', (event) => {
        if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
        const target = event.target;
        const tagName = target && target.tagName ? target.tagName.toLowerCase() : '';
        if (['input', 'select', 'textarea'].includes(tagName) || (target && target.isContentEditable)) return;
        if (!search) return;
        event.preventDefault();
        if (panel) panel.open = true;
        search.focus();
        search.select();
    });

    updateSelection();
})();
