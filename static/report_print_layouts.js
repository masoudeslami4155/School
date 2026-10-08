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

    const app = document.querySelector('#reportLayoutApp');
    if (!app) return;

    const dataNode = app.querySelector('#reportLayoutData');
    const paper = app.querySelector('#rplPaper');
    const form = app.querySelector('#reportLayoutForm');
    const jsonField = app.querySelector('#reportLayoutJson');
    const actionField = app.querySelector('#reportLayoutAction');
    let layout = JSON.parse(dataNode?.textContent || '{}');
    let dragState = null;

    const extraPreviewElements = {
        student_info: { hero: '.rpl-profile > header' },
        wall_cards: { cards: '[data-wall-grid-preview]' },
        student_filters: {
            hero: '.rpl-filter-reference h3',
            table: '.rpl-filter-reference table',
            notes: '.rpl-filter-reference p',
        },
    };
    Object.entries(extraPreviewElements[app.dataset.document] || {}).forEach(([key, selector]) => {
        app.querySelectorAll(selector).forEach((element) => { element.dataset.reportElement = key; });
    });
    if (['folder_labels', 'wall_cards'].includes(app.dataset.document)) {
        const heading = document.createElement('div');
        heading.className = 'rpl-sample-heading';
        heading.dataset.reportElement = 'hero';
        heading.innerHTML = app.dataset.document === 'wall_cards'
            ? '<strong>نام مدرسه</strong><span>عنوان چاپ · کارت دیواری</span>'
            : '<strong>نام مدرسه</strong><span>عنوان چاپ · پشت پرونده</span>';
        paper?.prepend(heading);
    }

    const setValue = (selector, value) => {
        app.querySelectorAll(selector).forEach((input) => {
            if (document.activeElement !== input) input.value = value;
        });
    };

    function fitWallGrid() {
        if (app.dataset.kind !== 'wall_cards') return;
        const landscape = layout.orientation === 'landscape';
        const pageWidth = landscape ? 297 : 210;
        const pageHeight = landscape ? 210 : 297;
        const usableWidth = pageWidth - layout.margin.left - layout.margin.right;
        const usableHeight = pageHeight - layout.margin.top - layout.margin.bottom - 12;
        const maxColumns = Math.max(1, Math.min(6, Math.floor((usableWidth + layout.grid.gap_x) / (30 + layout.grid.gap_x))));
        const maxRows = Math.max(1, Math.min(landscape ? 4 : 6, Math.floor((usableHeight + layout.grid.gap_y) / (30 + layout.grid.gap_y))));
        layout.grid.columns = Math.min(layout.grid.columns, maxColumns);
        layout.grid.rows = Math.min(layout.grid.rows, maxRows);
        const availableHeight = (usableHeight - layout.grid.gap_y * (layout.grid.rows - 1)) / layout.grid.rows;
        const maxHeight = Math.min(landscape ? 40 : 48, availableHeight);
        layout.card.height = Math.max(30, Math.min(layout.card.height, maxHeight));
    }

    function renderVisibility() {
        app.querySelectorAll('[data-report-column]').forEach((element) => {
            const key = element.dataset.reportColumn;
            if (!Object.prototype.hasOwnProperty.call(layout.columns || {}, key)) return;
            element.style.display = layout.columns[key] ? '' : 'none';
        });
        app.querySelectorAll('[data-report-section]').forEach((element) => {
            const key = element.dataset.reportSection;
            if (!Object.prototype.hasOwnProperty.call(layout.sections || {}, key)) return;
            element.hidden = !layout.sections[key];
        });
        app.querySelectorAll('[data-report-element]').forEach((element) => {
            if (element.dataset.reportElement === 'hero') element.hidden = !layout.show_header;
            if (element.dataset.reportElement === 'footer') element.hidden = !layout.show_footer;
        });
        app.querySelectorAll('[data-card-preview]').forEach((element) => {
            element.hidden = layout.card?.[element.dataset.cardPreview] === false;
        });
    }

    function renderElements() {
        roundLayout(layout);
        app.querySelectorAll('[data-report-element], [data-report-section]').forEach((element) => {
            const key = element.dataset.reportElement || element.dataset.reportSection;
            const position = layout.elements?.[key];
            if (!position) return;
            element.dataset.reportElement = key;
            element.style.transform = `translate(${position.x}mm, ${position.y}mm) scale(${position.sx}, ${position.sy})`;
            element.style.transformOrigin = 'top left';
            element.classList.add('rpl-movable');
            element.classList.toggle('is-selected', key === app.dataset.selectedElement);
            let handle = element.querySelector(':scope > .rpl-resize-handle');
            if (!handle) {
                handle = document.createElement('span');
                handle.className = 'rpl-resize-handle';
                handle.setAttribute('aria-label', 'تغییر اندازه');
                element.appendChild(handle);
            }
        });
    }

    function renderControls() {
        roundLayout(layout);
        setValue('[data-layout-field="orientation"]', layout.orientation);
        ['font_size', 'header_font_size', 'row_height', 'header_height', 'line_height'].forEach((key) => {
            setValue(`[data-layout-field="${key}"]`, layout[key]);
        });
        Object.entries(layout.margin || {}).forEach(([key, value]) => setValue(`[data-margin-side="${key}"]`, value));
        Object.entries(layout.grid || {}).forEach(([key, value]) => setValue(`[data-grid-field="${key}"]`, value));
        Object.entries(layout.card || {}).forEach(([key, value]) => {
            const input = app.querySelector(`[data-card-field="${key}"]`);
            if (input && input.type === 'checkbox') input.checked = Boolean(value);
            else if (input) setValue(`[data-card-field="${key}"]`, value);
        });
        const rowsInput = app.querySelector('[data-grid-field="rows"]');
        if (rowsInput && app.dataset.kind === 'wall_cards') {
            const usableHeight = (layout.orientation === 'landscape' ? 210 : 297)
                - layout.margin.top - layout.margin.bottom - 12;
            rowsInput.max = String(Math.max(1, Math.min(layout.orientation === 'landscape' ? 4 : 6,
                Math.floor((usableHeight + layout.grid.gap_y) / (30 + layout.grid.gap_y)))));
        }
        const cardHeightInput = app.querySelector('[data-card-field="height"]');
        if (cardHeightInput && app.dataset.kind === 'wall_cards') {
            const usableHeight = (layout.orientation === 'landscape' ? 210 : 297)
                - layout.margin.top - layout.margin.bottom - 12;
            const availableHeight = (usableHeight - layout.grid.gap_y * (layout.grid.rows - 1)) / layout.grid.rows;
            cardHeightInput.max = String(Math.min(layout.orientation === 'landscape' ? 40 : 48, availableHeight));
            setValue('[data-card-field="height"]', layout.card.height);
        }
        const columnsInput = app.querySelector('[data-grid-field="columns"]');
        if (columnsInput && app.dataset.kind === 'wall_cards') {
            const usableWidth = (layout.orientation === 'landscape' ? 297 : 210)
                - layout.margin.left - layout.margin.right;
            columnsInput.max = String(Math.max(1, Math.min(6,
                Math.floor((usableWidth + layout.grid.gap_x) / (30 + layout.grid.gap_x)))));
        }
        app.querySelectorAll('[data-layout-field]').forEach((input) => {
            const key = input.dataset.layoutField;
            if (input.type === 'checkbox' && Object.prototype.hasOwnProperty.call(layout, key)) input.checked = Boolean(layout[key]);
        });
        app.querySelectorAll('[data-column-field]').forEach((input) => {
            input.checked = layout.columns?.[input.dataset.columnField] !== false;
        });
        app.querySelectorAll('[data-section-field]').forEach((input) => {
            input.checked = layout.sections?.[input.dataset.sectionField] !== false;
        });
    }

    function renderPaperSize() {
        if (!paper) return;
        paper.style.width = layout.orientation === 'landscape' ? '720px' : '520px';
        paper.style.minHeight = layout.orientation === 'landscape' ? '510px' : '720px';
        paper.style.fontSize = `${layout.font_size}pt`;
        paper.style.lineHeight = layout.line_height;
        app.querySelectorAll('.rpl-paper th').forEach((cell) => { cell.style.height = `${layout.header_height * 2}px`; });
        app.querySelectorAll('.rpl-paper td').forEach((cell) => { cell.style.height = `${layout.row_height * 2}px`; });
        const wallGrid = app.querySelector('[data-wall-grid-preview]');
        if (wallGrid && layout.grid) {
            wallGrid.style.gridTemplateColumns = `repeat(${layout.grid.columns}, minmax(0, 1fr))`;
            wallGrid.style.gap = `${layout.grid.gap_y}px ${layout.grid.gap_x}px`;
            wallGrid.querySelectorAll('.rpl-wall-card').forEach((card) => {
                card.style.minHeight = `${Math.min(260, Math.max(150, layout.card.height * 4))}px`;
            });
        }
    }

    function render() {
        fitWallGrid();
        renderControls();
        renderVisibility();
        renderPaperSize();
        renderElements();
    }

    function numberValue(input, fallback) {
        const value = Number(input.value);
        return Number.isFinite(value) ? value : fallback;
    }

    function update(input) {
        if (input.matches('[data-layout-field]')) {
            const key = input.dataset.layoutField;
            layout[key] = input.type === 'checkbox' ? input.checked : input.value;
            if (key === 'orientation') {
                layout.orientation = input.value === 'landscape' ? 'landscape' : 'portrait';
                if (app.dataset.kind === 'wall_cards' && layout.orientation === 'landscape') layout.grid.rows = Math.min(4, layout.grid.rows);
            }
        } else if (input.matches('[data-margin-side]')) {
            layout.margin[input.dataset.marginSide] = numberValue(input, layout.margin[input.dataset.marginSide]);
        } else if (input.matches('[data-grid-field]')) {
            const key = input.dataset.gridField;
            if (app.dataset.kind === 'wall_cards' && key.startsWith('gap_')) {
                layout.grid[key] = Math.max(0, Math.min(10, numberValue(input, layout.grid[key])));
            } else {
                const max = app.dataset.kind === 'wall_cards' && key === 'rows' && layout.orientation === 'landscape' ? 4 : 6;
                layout.grid[key] = Math.max(1, Math.min(max, Math.round(numberValue(input, layout.grid[key]))));
            }
        } else if (input.matches('[data-column-field]')) {
            layout.columns[input.dataset.columnField] = input.checked;
        } else if (input.matches('[data-section-field]')) {
            layout.sections[input.dataset.sectionField] = input.checked;
        } else if (input.matches('[data-card-field]')) {
            const key = input.dataset.cardField;
            layout.card[key] = input.type === 'checkbox'
                ? input.checked
                : Math.max(key === 'photo_size' ? 0 : 4, Math.min(key === 'height' ? (layout.orientation === 'landscape' ? 40 : 48) : key === 'photo_size' ? 30 : key === 'font_size' ? 12 : 18, numberValue(input, layout.card[key])));
        }
        render();
    }

    app.addEventListener('change', (event) => {
        if (event.target.matches('[data-layout-field], [data-margin-side], [data-grid-field], [data-column-field], [data-section-field], [data-card-field]')) update(event.target);
    });
    app.addEventListener('input', (event) => {
        if (event.target.matches('[data-layout-field], [data-margin-side], [data-grid-field], [data-card-field]')) update(event.target);
    });
    app.addEventListener('focusout', render);
    paper?.addEventListener('pointerdown', (event) => {
        const element = event.target.closest('[data-report-element]');
        if (!element || event.button !== 0) return;
        const key = element.dataset.reportElement;
        const position = layout.elements?.[key];
        if (!position) return;
        app.dataset.selectedElement = key;
        dragState = {
            element,
            key,
            resize: event.target.closest('.rpl-resize-handle') !== null,
            startX: event.clientX,
            startY: event.clientY,
            rect: element.getBoundingClientRect(),
            position: { ...position },
        };
        element.setPointerCapture?.(event.pointerId);
        event.preventDefault();
        renderElements();
    });
    paper?.addEventListener('pointermove', (event) => {
        if (!dragState) return;
        const position = layout.elements[dragState.key];
        const pageWidth = layout.orientation === 'landscape' ? 297 : 210;
        const pageHeight = layout.orientation === 'landscape' ? 210 : 297;
        const paperRect = paper.getBoundingClientRect();
        if (dragState.resize) {
            position.sx = Math.max(0.5, Math.min(2.5,
                dragState.position.sx * (1 + (event.clientX - dragState.startX) / Math.max(1, dragState.rect.width))));
            position.sy = Math.max(0.5, Math.min(2.5,
                dragState.position.sy * (1 + (event.clientY - dragState.startY) / Math.max(1, dragState.rect.height))));
        } else {
            position.x = Math.max(-60, Math.min(60, dragState.position.x
                + (event.clientX - dragState.startX) / paperRect.width * pageWidth));
            position.y = Math.max(-60, Math.min(60, dragState.position.y
                + (event.clientY - dragState.startY) / paperRect.height * pageHeight));
        }
        renderElements();
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) => {
        paper?.addEventListener(name, () => { dragState = null; });
    });
    form?.addEventListener('submit', () => {
        jsonField.value = JSON.stringify(layout);
    });
    app.querySelector('#resetReportLayout')?.addEventListener('click', () => {
        if (!window.confirm('چیدمان این گزارش به حالت پیش‌فرض برگردد؟')) return;
        actionField.value = 'reset';
        jsonField.value = '{}';
        form.submit();
    });
    window.addEventListener('resize', render);
    render();
})();
