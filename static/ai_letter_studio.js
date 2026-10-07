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

    const app = document.querySelector('#letterStudio');
    if (!app) return;

    const paper = app.querySelector('#letterPaper');
    const form = app.querySelector('#letterLayoutForm');
    const layoutField = app.querySelector('#letterLayoutJson');
    const actionField = app.querySelector('#letterLayoutAction');
    const elementSelect = app.querySelector('#letterElementSelect');
    const orientationSelect = app.querySelector('#letterOrientation');
    const fontSizeInput = app.querySelector('#letterFontSize');
    const layout = JSON.parse(app.querySelector('#letterLayoutData')?.textContent || '{}');
    const defaultLayout = JSON.parse(app.querySelector('#letterDefaultLayoutData')?.textContent || '{}');
    const templates = JSON.parse(app.querySelector('#letterTemplatesData')?.textContent || '[]');
    let selected = elementSelect?.value;
    let drag = null;

    const elements = () => app.querySelectorAll('[data-letter-element]');
    const selectedElement = () => layout.elements?.[selected];

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function renderElement(element) {
        const key = element.dataset.letterElement;
        const position = layout.elements?.[key];
        if (!position) return;
        element.style.left = `${position.x}%`;
        element.style.top = `${position.y}%`;
        element.style.width = `${position.w}%`;
        element.style.height = `${position.h}%`;
        element.style.fontSize = `${position.font}em`;
        element.classList.toggle('is-selected', key === selected);
        element.tabIndex = 0;
        element.setAttribute('aria-label', key);
        let handle = element.querySelector(':scope > .letter-resize-handle');
        if (!handle) {
            handle = document.createElement('span');
            handle.className = 'letter-resize-handle';
            handle.setAttribute('aria-label', 'تغییر اندازه');
            element.appendChild(handle);
        }
    }

    function renderPaper() {
        if (!paper) return;
        paper.dataset.orientation = layout.orientation;
        const margin = layout.margin || {};
        paper.style.padding = `${margin.top || 0}mm ${margin.right || 0}mm ${margin.bottom || 0}mm ${margin.left || 0}mm`;
        paper.style.fontSize = `${layout.font_size || 12}pt`;
    }

    function renderControls() {
        roundLayout(layout);
        const position = selectedElement();
        if (!position) return;
        app.querySelectorAll('[data-letter-field]').forEach((input) => {
            const key = input.dataset.letterField;
            if (document.activeElement !== input) input.value = position[key];
        });
        app.querySelectorAll('[data-letter-margin]').forEach((input) => {
            const side = input.dataset.letterMargin;
            if (document.activeElement !== input) input.value = layout.margin?.[side];
        });
        if (fontSizeInput && document.activeElement !== fontSizeInput) {
            fontSizeInput.value = layout.font_size;
        }
        elements().forEach(renderElement);
        renderPaper();
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
        renderPaper();
    });

    app.addEventListener('input', (event) => {
        const marginInput = event.target.closest('[data-letter-margin]');
        if (marginInput) {
            const side = marginInput.dataset.letterMargin;
            const next = Number(marginInput.value);
            if (Number.isFinite(next)) {
                layout.margin[side] = Math.round(clamp(next, 0, 30) * 100) / 100;
                renderControls();
            }
            return;
        }
        if (event.target === fontSizeInput) {
            const next = Number(fontSizeInput.value);
            if (Number.isFinite(next)) {
                layout.font_size = Math.round(clamp(next, 8, 18) * 100) / 100;
                renderControls();
            }
            return;
        }
        const fieldInput = event.target.closest('[data-letter-field]');
        const position = selectedElement();
        if (!fieldInput || !position) return;
        const key = fieldInput.dataset.letterField;
        const next = Number(fieldInput.value);
        if (!Number.isFinite(next)) return;
        const limits = key === 'font' ? [0.5, 2.5] : key === 'w' || key === 'h' ? [1, 100] : [0, 99];
        position[key] = Math.round(clamp(next, ...limits) * 100) / 100;
        if (key === 'x') position.x = Math.min(position.x, 100 - position.w);
        if (key === 'y') position.y = Math.min(position.y, 100 - position.h);
        if (key === 'w') position.w = Math.min(position.w, 100 - position.x);
        if (key === 'h') position.h = Math.min(position.h, 100 - position.y);
        renderControls();
    });

    app.addEventListener('pointerdown', (event) => {
        const element = event.target.closest('[data-letter-element]');
        if (!element || event.button !== 0) return;
        const key = element.dataset.letterElement;
        selectElement(key);
        const position = selectedElement();
        if (!position) return;
        event.preventDefault();
        element.setPointerCapture(event.pointerId);
        const rect = paper.getBoundingClientRect();
        drag = {
            key,
            resize: event.target.closest('.letter-resize-handle') !== null,
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
        if (!event.target.matches('[data-letter-element]') || !event.key.startsWith('Arrow')) return;
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
    app.querySelector('#resetLetterLayout')?.addEventListener('click', () => {
        if (!window.confirm('چیدمان نامه به حالت پیش‌فرض برگردد؟')) return;
        actionField.value = 'reset';
        layoutField.value = JSON.stringify(defaultLayout);
        form.submit();
    });

    const templateSelect = app.querySelector('#letterTemplateSelect');
    const templateKeyField = app.querySelector('#letterTemplateKey');
    const templateNameInput = app.querySelector('#letterTemplateName');
    const selectedTemplate = () => templates.find((item) => item.key === templateSelect?.value);

    function applyLayout(next) {
        Object.keys(layout).forEach((key) => { delete layout[key]; });
        Object.assign(layout, JSON.parse(JSON.stringify(next)));
        orientationSelect.value = layout.orientation === 'landscape' ? 'landscape' : 'portrait';
        renderControls();
    }

    app.querySelector('#loadLetterTemplate')?.addEventListener('click', () => {
        const item = selectedTemplate();
        if (!item) return;
        if (!window.confirm(`الگوی «${item.label}» جای چیدمان فعلی را می‌گیرد. ادامه می‌دهید؟`)) return;
        applyLayout(item.layout);
        templateKeyField.value = item.key;
    });

    app.querySelector('#saveLetterTemplate')?.addEventListener('click', () => {
        const name = (templateNameInput?.value || '').trim();
        if (!name) {
            window.alert('ابتدا نام الگوی جدید را وارد کنید.');
            templateNameInput?.focus();
            return;
        }
        actionField.value = 'save_template';
        templateKeyField.value = `t${Date.now().toString(36)}`;
        layoutField.value = JSON.stringify(layout);
        app.querySelector('input[name="template_label"]')?.remove();
        const labelInput = document.createElement('input');
        labelInput.type = 'hidden';
        labelInput.name = 'template_label';
        labelInput.value = name;
        form?.appendChild(labelInput);
        form?.submit();
    });

    app.querySelector('#deleteLetterTemplate')?.addEventListener('click', () => {
        const item = selectedTemplate();
        if (!item) return;
        if (item.builtin) {
            window.alert('الگوهای پیش‌فرض قابل حذف نیستند.');
            return;
        }
        if (!window.confirm(`الگوی «${item.label}» حذف شود؟`)) return;
        actionField.value = 'delete_template';
        templateKeyField.value = item.key;
        form?.submit();
    });

    templateSelect?.addEventListener('change', () => {
        const item = selectedTemplate();
        app.querySelector('#deleteLetterTemplate').disabled = Boolean(item?.builtin);
    });

    orientationSelect.value = layout.orientation;
    renderControls();
    templateSelect?.dispatchEvent(new Event('change'));
})();
