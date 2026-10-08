(() => {
    const root = document.querySelector('.attendance-report');
    if (!root) return;

    const toggle = root.querySelector('[data-toggle-filters]');
    const panel = root.querySelector('#arFilters');
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

    const filterForm = panel ? panel.querySelector('form') : null;
    if (filterForm) {
        filterForm.addEventListener('submit', () => {
            const submit = filterForm.querySelector('button[type="submit"]');
            if (submit) submit.classList.add('is-loading');
        });
    }

    const search = root.querySelector('#arSearch');
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

    if (root.dataset.autoprint === '1') {
        window.setTimeout(() => window.print(), 300);
    }
})();
