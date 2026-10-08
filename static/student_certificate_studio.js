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

    const app = document.querySelector('#certificateStudio');
    if (!app) return;

    const paper = app.querySelector('.certificate');
    const form = app.querySelector('#certificateLayoutForm');
    const layoutField = app.querySelector('#certificateLayoutJson');
    const actionField = app.querySelector('#certificateLayoutAction');
    const elementSelect = app.querySelector('#certificateElementSelect');
    const orientationSelect = app.querySelector('#certificateOrientation');
    const layout = JSON.parse(app.querySelector('#certificateLayoutData')?.textContent || '{}');
    const defaultLayout = JSON.parse(app.querySelector('#certificateDefaultLayoutData')?.textContent || '{}');
    let selected = elementSelect?.value;
    let drag = null;

    const elements = () => app.querySelectorAll('[data-cert-element]');
    const selectedElement = () => layout.elements?.[selected];

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function renderElement(element) {
        const key = element.dataset.certElement;
        const position = layout.elements?.[key];
        if (!position) return;
        element.style.left = `${position.x}%`;
        element.style.top = `${position.y}%`;
        element.style.width = `${position.w}%`;
        element.style.height = `${position.h}%`;
        element.style.fontSize = `calc(${position.font}cqw * ${layout.font_scale || 1})`;
        element.classList.toggle('is-selected', key === selected);
        element.tabIndex = 0;
        element.setAttribute('aria-label', key);
        let handle = element.querySelector(':scope > .certificate-resize-handle');
        if (!handle) {
            handle = document.createElement('span');
            handle.className = 'certificate-resize-handle';
            handle.setAttribute('aria-label', 'تغییر اندازه');
            element.appendChild(handle);
        }
    }

    function renderControls() {
        roundLayout(layout);
        const position = selectedElement();
        if (!position) return;
        app.querySelectorAll('[data-certificate-field]').forEach((input) => {
            const key = input.dataset.certificateField;
            if (document.activeElement !== input) input.value = position[key];
        });
        elements().forEach(renderElement);
    }

    function selectElement(key) {
        if (!layout.elements?.[key]) return;
        selected = key;
        elementSelect.value = key;
        renderControls();
    }

    elementSelect?.addEventListener('change', () => selectElement(elementSelect.value));
    orientationSelect?.addEventListener('change', () => {
        layout.orientation = orientationSelect.value === 'landscape' ? 'landscape' : 'portrait';
        paper.closest('.certificate-page').dataset.orientation = layout.orientation;
    });

    app.addEventListener('input', (event) => {
        const input = event.target.closest('[data-certificate-field]');
        const position = selectedElement();
        if (!input || !position) return;
        const key = input.dataset.certificateField;
        const next = Number(input.value);
        if (!Number.isFinite(next)) return;
        const limits = key === 'font' ? [0.3, 4] : key === 'w' || key === 'h' ? [1, 100] : [0, 99];
        position[key] = Math.round(clamp(next, ...limits) * 100) / 100;
        if (key === 'x') position.x = Math.min(position.x, 100 - position.w);
        if (key === 'y') position.y = Math.min(position.y, 100 - position.h);
        if (key === 'w') position.w = Math.min(position.w, 100 - position.x);
        if (key === 'h') position.h = Math.min(position.h, 100 - position.y);
        renderControls();
    });

    app.addEventListener('pointerdown', (event) => {
        const element = event.target.closest('[data-cert-element]');
        if (!element || event.button !== 0) return;
        const key = element.dataset.certElement;
        selectElement(key);
        const position = selectedElement();
        if (!position) return;
        event.preventDefault();
        element.setPointerCapture(event.pointerId);
        const rect = paper.getBoundingClientRect();
        drag = {
            key,
            resize: event.target.closest('.certificate-resize-handle') !== null,
            x: event.clientX,
            y: event.clientY,
            startX: position.x,
            startY: position.y,
            startW: position.w,
            startH: position.h,
            paperWidth: rect.width,
            paperHeight: rect.height,
        };
    });

    app.addEventListener('pointermove', (event) => {
        if (!drag) return;
        const position = layout.elements[drag.key];
        const rect = paper.getBoundingClientRect();
        if (drag.resize) {
            position.w = Math.round(clamp(drag.startW + (event.clientX - drag.x) / drag.paperWidth * 100, 1, 100 - position.x) * 100) / 100;
            position.h = Math.round(clamp(drag.startH + (event.clientY - drag.y) / drag.paperHeight * 100, 1, 100 - position.y) * 100) / 100;
        } else {
            position.x = Math.round(clamp(drag.startX + (event.clientX - drag.x) / rect.width * 100, 0, 100 - position.w) * 100) / 100;
            position.y = Math.round(clamp(drag.startY + (event.clientY - drag.y) / rect.height * 100, 0, 100 - position.h) * 100) / 100;
        }
        renderControls();
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) => {
        app.addEventListener(name, () => { drag = null; });
    });

    app.addEventListener('keydown', (event) => {
        if (!event.target.matches('[data-cert-element]') || !event.key.startsWith('Arrow')) return;
        event.preventDefault();
        const position = selectedElement();
        if (!position) return;
        const step = event.shiftKey ? 1 : 0.2;
        if (event.key === 'ArrowLeft') position.x = clamp(position.x - step, 0, 100 - position.w);
        if (event.key === 'ArrowRight') position.x = clamp(position.x + step, 0, 100 - position.w);
        if (event.key === 'ArrowUp') position.y = clamp(position.y - step, 0, 100 - position.h);
        if (event.key === 'ArrowDown') position.y = clamp(position.y + step, 0, 100 - position.h);
        renderControls();
    });

    form?.addEventListener('submit', () => {
        layoutField.value = JSON.stringify(layout);
    });
    app.querySelector('#resetCertificateLayout')?.addEventListener('click', () => {
        if (!window.confirm('چیدمان گواهی به حالت پیش‌فرض برگردد؟')) return;
        actionField.value = 'reset';
        layoutField.value = JSON.stringify(defaultLayout);
        form.submit();
    });

    app.querySelector('#resetCertificateElement')?.addEventListener('click', () => {
        layout.elements[selected] = {...defaultLayout.elements[selected]};
        renderControls();
    });
    function renderPage() {
        roundLayout(layout);
        const page = paper.closest('.certificate-page');
        page.dataset.paper = layout.paper_size || 'A4';
        page.style.setProperty('--frame-margin', `${layout.frame_margin}mm`);
        page.style.setProperty('--frame-border', `${layout.border_width}mm`);
        elements().forEach(renderElement);
    }
    app.querySelectorAll('[data-certificate-global]').forEach(input => {
        const key = input.dataset.certificateGlobal;
        input.value = layout[key];
        input.addEventListener('input', () => {
            if (input.type === 'number' && (!input.checkValidity() || !input.value)) return;
            layout[key] = input.type === 'number' ? Number(input.value) : input.value;
            renderPage();
        });
    });
    renderPage();
    orientationSelect.value = layout.orientation;
    renderControls();
})();
