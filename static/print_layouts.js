(() => {
    // Keep model, displayed controls and saved JSON on the same 0.01 grid.
    function roundLayout(value) {
        if (!value || typeof value !== 'object') return;
        Object.keys(value).forEach(key => {
            if (typeof value[key] === 'number' && Number.isFinite(value[key]))
                value[key] = Math.round((value[key] + Number.EPSILON) * 100) / 100;
            else if (value[key] && typeof value[key] === 'object') roundLayout(value[key]);
        });
    }

    const app = document.querySelector('#printLayoutApp');
    if (!app) return;

    const dataNode = app.querySelector('#printLayoutData');
    const paper = app.querySelector('#plaPaper');
    const canvas = app.querySelector('.pla-canvas-wrap');
    const form = app.querySelector('#printLayoutForm');
    const jsonField = app.querySelector('#layoutJsonField');
    const actionField = app.querySelector('#layoutAction');
    const documentKind = app.dataset.kind;
    const PX_PER_MM = 3.7795275591;
    let layout = JSON.parse(dataNode?.textContent || '{}');
    let selectedKey = null;
    let dragState = null;

    const pageSize = () => layout.orientation === 'landscape' ? { width: 297, height: 210 } : { width: 210, height: 297 };
    const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));
    const num = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;

    function scale() {
        const page = pageSize();
        const available = Math.max(280, (canvas?.clientWidth || 800) - 44);
        return Math.max(.38, Math.min(1.05, available / (page.width * PX_PER_MM)));
    }

    function mm(value) { return `${value * PX_PER_MM * scale()}px`; }
    function pt(value) { return `${value * 1.333 * scale()}px`; }

    function setPaperSize() {
        const page = pageSize();
        paper.style.width = mm(page.width);
        paper.style.height = mm(page.height);
        paper.dataset.orientation = layout.orientation;
    }

    function setInput(selector, value) {
        const input = app.querySelector(selector);
        if (input && document.activeElement !== input) input.value = value;
    }

    function renderMarginControls() {
        Object.entries(layout.margin || {}).forEach(([side, value]) => setInput(`[data-margin-side="${side}"]`, value));
    }

    function renderSlipControls() {
        Object.entries(layout.grid || {}).forEach(([key, value]) => setInput(`[data-grid-field="${key}"]`, value));
        app.querySelectorAll('[data-element-control]').forEach((control) => {
            const item = layout.elements?.[control.dataset.elementControl];
            if (!item) return;
            control.querySelectorAll('[data-element-field]').forEach((input) => {
                const key = input.dataset.elementField;
                if (input.type === 'checkbox') input.checked = Boolean(item[key]);
                else setInput(`[data-element-control="${control.dataset.elementControl}"] [data-element-field="${key}"]`, item[key]);
            });
        });
    }

    function renderDriverControls() {
        Object.entries(layout.table || {}).forEach(([key, value]) => {
            const input = app.querySelector(`[data-table-field="${key}"]`);
            if (!input) return;
            if (input.type === 'checkbox') input.checked = Boolean(value);
            else setInput(`[data-table-field="${key}"]`, value);
        });
    }

    function setElementStyles(element, item) {
        const s = scale();
        element.style.right = mm(item.x);
        element.style.top = mm(item.y);
        element.style.width = mm(item.w);
        element.style.height = mm(item.h);
        element.style.fontSize = pt(item.font);
        element.hidden = !item.visible;
        element.classList.toggle('is-selected', selectedKey === element.dataset.elementKey);
        let handle = element.querySelector('.pla-resize-handle');
        if (!handle) {
            handle = document.createElement('span');
            handle.className = 'pla-resize-handle';
            handle.setAttribute('aria-label', 'تغییر اندازه');
            element.appendChild(handle);
        }
        handle.style.width = `${Math.max(12, 12 * s)}px`;
        handle.style.height = `${Math.max(12, 12 * s)}px`;
    }

    function renderSlip() {
        const sample = app.querySelector('#plaSlipSample');
        if (!sample) return;
        const grid = layout.grid;
        sample.style.right = mm(layout.margin.right + grid.offset_x);
        sample.style.top = mm(layout.margin.top + grid.offset_y);
        sample.style.width = mm(grid.width);
        sample.style.height = mm(grid.height);
        app.querySelectorAll('.pla-element[data-element-key]').forEach((element) => {
            const item = layout.elements?.[element.dataset.elementKey];
            if (item) setElementStyles(element, item);
        });
        const type = app.querySelector('[data-element-key="badge"]');
        if (type) type.textContent = app.dataset.document === 'service_request' ? 'درخواست پرداخت' : 'رسید دریافت';
    }

    function renderDriver() {
        const sample = app.querySelector('#plaDriverSample');
        if (!sample) return;
        const table = layout.table;
        sample.style.padding = `${mm(layout.margin.top)} ${mm(layout.margin.right)} ${mm(layout.margin.bottom)} ${mm(layout.margin.left)}`;
        const header = sample.querySelector('header');
        const tableNode = sample.querySelector('.pla-driver-table');
        const footer = sample.querySelector('.pla-driver-footer');
        if (header) header.hidden = !table.show_header;
        if (footer) footer.hidden = !table.show_footer;
        if (header) header.style.fontSize = pt(table.header_font_size);
        if (tableNode) {
            tableNode.style.marginRight = mm(table.x);
            tableNode.style.marginTop = mm(table.y);
            tableNode.style.width = mm(table.width);
            tableNode.style.fontSize = pt(table.font_size);
            tableNode.style.transform = `scaleY(${table.scale_y || 1})`;
            tableNode.style.transformOrigin = 'top right';
            tableNode.style.setProperty('--driver-student-columns', table.student_columns);
            tableNode.querySelectorAll('.pla-driver-row').forEach((row) => {
                row.style.padding = `${mm(table.row_padding)} 0`;
            });
            if (!tableNode.querySelector(':scope > .pla-driver-resize-handle')) {
                const handle = document.createElement('span');
                handle.className = 'pla-driver-resize-handle';
                handle.setAttribute('aria-label', 'تغییر اندازه جدول');
                tableNode.appendChild(handle);
            }
        }
    }

    function render() {
        roundLayout(layout);
        setPaperSize();
        setInput('#layoutOrientation', layout.orientation);
        renderMarginControls();
        if (documentKind === 'slip') renderSlipControls();
        else renderDriverControls();
        if (documentKind === 'slip') renderSlip();
        else renderDriver();
    }

    function updateFromInput(input) {
        if (input.matches('[data-margin-side]')) {
            layout.margin[input.dataset.marginSide] = clamp(num(input.value, 0), 0, 40);
        } else if (input.matches('[data-grid-field]')) {
            const key = input.dataset.gridField;
            layout.grid[key] = clamp(num(input.value, layout.grid[key]), key === 'columns' || key === 'rows' ? 1 : (key.includes('offset') ? -80 : 0), key === 'columns' ? 6 : key === 'rows' ? 8 : key === 'width' ? 205 : key === 'height' ? 285 : key.includes('offset') ? 80 : 30);
            if (key === 'columns' || key === 'rows') layout.grid[key] = Math.round(layout.grid[key]);
        } else if (input.matches('[data-table-field]')) {
            const key = input.dataset.tableField;
            layout.table[key] = input.type === 'checkbox' ? input.checked : num(input.value, layout.table[key]);
        } else if (input.matches('[data-element-field]')) {
            const control = input.closest('[data-element-control]');
            const key = input.dataset.elementField;
            if (!control || !layout.elements?.[control.dataset.elementControl]) return;
            layout.elements[control.dataset.elementControl][key] = input.type === 'checkbox' ? input.checked : num(input.value, layout.elements[control.dataset.elementControl][key]);
            if (input.type !== 'checkbox') layout.elements[control.dataset.elementControl][key] = clamp(layout.elements[control.dataset.elementControl][key], key === 'font' ? 5 : 0, key === 'font' ? 30 : 285);
            selectedKey = control.dataset.elementControl;
        }
        render();
    }

    app.addEventListener('input', (event) => {
        if (event.target.matches('[data-margin-side], [data-grid-field], [data-table-field], [data-element-field]')) updateFromInput(event.target);
    });
    app.addEventListener('change', (event) => {
        if (event.target.matches('#layoutOrientation')) {
            layout.orientation = event.target.value === 'landscape' ? 'landscape' : 'portrait';
            render();
        } else if (event.target.matches('[data-margin-side], [data-grid-field], [data-table-field], [data-element-field]')) updateFromInput(event.target);
    });

    paper?.addEventListener('pointerdown', (event) => {
        const element = event.target.closest('.pla-element');
        if (element && !element.hidden) {
            const key = element.dataset.elementKey;
            const item = layout.elements?.[key];
            if (!item) return;
            selectedKey = key;
            dragState = {
                type: 'slip', element, key, resize: event.target.classList.contains('pla-resize-handle'),
                startX: event.clientX, startY: event.clientY, item: { ...item },
            };
            element.setPointerCapture?.(event.pointerId);
        } else if (documentKind === 'drivers') {
            const tableNode = event.target.closest('.pla-driver-table');
            if (!tableNode) return;
            dragState = {
                type: 'drivers', element: tableNode,
                resize: event.target.closest('.pla-driver-resize-handle') !== null,
                startX: event.clientX, startY: event.clientY,
                rect: tableNode.getBoundingClientRect(), item: { ...layout.table },
            };
            tableNode.setPointerCapture?.(event.pointerId);
        } else {
            return;
        }
        event.preventDefault();
        render();
    });
    paper?.addEventListener('pointermove', (event) => {
        if (!dragState) return;
        if (dragState.type === 'drivers') {
            const table = layout.table;
            const factor = PX_PER_MM * scale();
            const dx = (event.clientX - dragState.startX) / factor;
            const dy = (event.clientY - dragState.startY) / factor;
            if (dragState.resize) {
                table.width = clamp(dragState.item.width - dx, 50, 297);
                table.scale_y = clamp((dragState.item.scale_y || 1) * (1 + dy / Math.max(1, dragState.rect.height)), 0.5, 2.5);
            } else {
                table.x = clamp(dragState.item.x - dx, 0, 120);
                table.y = clamp(dragState.item.y + dy, 0, 120);
            }
            render();
            return;
        }
        const item = layout.elements[dragState.key];
        const factor = PX_PER_MM * scale();
        const dx = (event.clientX - dragState.startX) / factor;
        const dy = (event.clientY - dragState.startY) / factor;
        if (dragState.resize) {
            item.w = clamp(dragState.item.w - dx, 1, 205);
            item.h = clamp(dragState.item.h + dy, 1, 285);
        } else {
            item.x = clamp(dragState.item.x - dx, 0, 205);
            item.y = clamp(dragState.item.y + dy, 0, 285);
        }
        render();
    });
    paper?.addEventListener('pointerup', () => { dragState = null; });
    paper?.addEventListener('pointercancel', () => { dragState = null; });

    form?.addEventListener('submit', () => {
        jsonField.value = JSON.stringify(layout);
    });
    app.querySelector('#resetLayout')?.addEventListener('click', () => {
        if (!window.confirm('چیدمان این برگه به حالت پیش‌فرض برگردد؟')) return;
        actionField.value = 'reset';
        jsonField.value = '{}';
        form.submit();
    });
    window.addEventListener('resize', render);
    render();
})();
