(() => {
    const root = document.documentElement;
    const toFa = (value) => String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]);
    const cardInputs = Array.from(document.querySelectorAll('[data-card-field]'));
    const tableInputs = Array.from(document.querySelectorAll('[data-table-field]'));
    const mobileInputs = Array.from(document.querySelectorAll('[data-mobile-field]'));

    const updateCount = (elementId, inputs) => {
        const output = document.getElementById(elementId);
        if (!output) return;
        // «نام» همیشه فعال است و در فهرست قابل تغییر وجود ندارد.
        output.textContent = `${toFa(1 + inputs.filter((input) => input.checked && !input.disabled).length)} مورد`;
    };
    const syncMobileFields = () => {
        mobileInputs.forEach((mobile) => {
            const correspondingCardField = cardInputs.find((card) => card.value === mobile.value);
            const canDisplay = !correspondingCardField || correspondingCardField.checked;
            mobile.disabled = !canDisplay;
            if (!canDisplay) mobile.checked = false;
        });
        updateCount('mobileFieldCount', mobileInputs);
    };
    const updateFieldCounts = () => {
        updateCount('cardFieldCount', cardInputs);
        updateCount('tableFieldCount', tableInputs);
        syncMobileFields();
    };
    cardInputs.forEach((input) => input.addEventListener('change', updateFieldCounts));
    tableInputs.forEach((input) => input.addEventListener('change', updateFieldCounts));
    mobileInputs.forEach((input) => input.addEventListener('change', () => updateCount('mobileFieldCount', mobileInputs)));
    updateFieldCounts();

    const tableOrderList = document.querySelector('[data-table-order-list]');
    const tableOrderRows = () => tableOrderList ? Array.from(tableOrderList.querySelectorAll('[data-table-order-item]')) : [];
    const tablePinInputs = Array.from(document.querySelectorAll('[data-table-pin]'));
    const parsedTablePinLimit = Number.parseInt(tableOrderList?.dataset.pinLimit || '3', 10);
    const tablePinLimit = Number.isFinite(parsedTablePinLimit) ? Math.max(1, parsedTablePinLimit) : 3;
    const tablePinnedCount = document.getElementById('tablePinnedCount');
    const quickActionList = document.querySelector('[data-quick-action-list]');
    const quickActionRows = () => quickActionList ? Array.from(quickActionList.querySelectorAll('[data-quick-action-item]')) : [];
    const toFaOrdinal = (value) => String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]);

    const updateTableOrderControls = () => {
        const rows = tableOrderRows();
        rows.forEach((row, index) => {
            const up = row.querySelector('[data-table-move="up"]');
            const down = row.querySelector('[data-table-move="down"]');
            const number = row.querySelector('[data-table-order-number]');
            if (up) up.disabled = index === 0;
            if (down) down.disabled = index === rows.length - 1;
            if (number) number.textContent = toFaOrdinal(index + 1);
        });
    };
    const syncPinnedColumns = () => {
        const selected = new Set(['name', ...tableInputs.filter((input) => input.checked).map((input) => input.value)]);
        tablePinInputs.forEach((input) => {
            input.disabled = !selected.has(input.value);
            if (input.disabled) input.checked = false;
        });
        if (tablePinnedCount) {
            const count = 1 + tablePinInputs.filter((input) => input.checked && !input.disabled).length;
            tablePinnedCount.textContent = `${toFaOrdinal(count)} ستون ثابت`;
        }
    };
    const updateQuickActionMoveControls = () => {
        const rows = quickActionRows();
        rows.forEach((row, index) => {
            const up = row.querySelector('[data-quick-action-move="up"]');
            const down = row.querySelector('[data-quick-action-move="down"]');
            if (up) up.disabled = index === 0;
            if (down) down.disabled = index === rows.length - 1;
        });
    };
    const moveRow = (row, direction, rows, refresh) => {
        const index = rows().indexOf(row);
        if (index < 0) return;
        if (direction === 'up' && row.previousElementSibling) {
            row.parentElement.insertBefore(row, row.previousElementSibling);
        } else if (direction === 'down' && row.nextElementSibling) {
            row.parentElement.insertBefore(row.nextElementSibling, row);
        }
        refresh();
    };
    tableOrderList?.addEventListener('click', (event) => {
        const button = event.target.closest('[data-table-move]');
        if (!button) return;
        const row = button.closest('[data-table-order-item]');
        if (row) moveRow(row, button.dataset.tableMove, tableOrderRows, updateTableOrderControls);
    });
    quickActionList?.addEventListener('click', (event) => {
        const button = event.target.closest('[data-quick-action-move]');
        if (!button) return;
        const row = button.closest('[data-quick-action-item]');
        if (row) moveRow(row, button.dataset.quickActionMove, quickActionRows, updateQuickActionMoveControls);
    });
    tableInputs.forEach((input) => input.addEventListener('change', syncPinnedColumns));
    tablePinInputs.forEach((input) => input.addEventListener('change', () => {
        if (tablePinInputs.filter((pin) => pin.checked && !pin.disabled).length > tablePinLimit - 1) {
            input.checked = false;
            if (tablePinnedCount) tablePinnedCount.textContent = `حداکثر ${toFaOrdinal(tablePinLimit)} ستون با احتساب نام را ثابت کنید`;
            return;
        }
        syncPinnedColumns();
    }));
    updateTableOrderControls();
    updateQuickActionMoveControls();
    syncPinnedColumns();

    const lightVariables = {
        button: ['--user-light-button-color', '--user-button-color', '--primary', '--primary2'],
        button_text: ['--user-light-button-text', '--user-button-text'],
        secondary_button: ['--user-light-secondary-button-color', '--user-secondary-button-color'],
        secondary_button_text: ['--user-light-secondary-button-text', '--user-secondary-button-text'],
        background: ['--user-light-page-background', '--user-page-background'],
        surface: ['--user-light-box-background', '--user-box-background', '--surface'],
        text: ['--user-light-text-color', '--user-text-color', '--ink'],
        border: ['--user-light-border-color', '--user-border-color', '--line', '--line-strong'],
        table_header: ['--user-light-table-header', '--user-table-header'],
        table_header_text: ['--user-light-table-header-text', '--user-table-header-text'],
        table_row: ['--user-light-table-row', '--user-table-row'],
        table_row_alt: ['--user-light-table-row-alt', '--user-table-row-alt', '--surface-soft'],
    };
    const darkVariables = {
        button: ['--user-dark-button-color'],
        button_text: ['--user-dark-button-text'],
        secondary_button: ['--user-dark-secondary-button-color'],
        secondary_button_text: ['--user-dark-secondary-button-text'],
        background: ['--user-dark-page-background'],
        surface: ['--user-dark-box-background'],
        text: ['--user-dark-text-color'],
        border: ['--user-dark-border-color'],
        table_header: ['--user-dark-table-header'],
        table_header_text: ['--user-dark-table-header-text'],
        table_row: ['--user-dark-table-row'],
        table_row_alt: ['--user-dark-table-row-alt'],
    };

    const colorInputs = (palette) => Object.fromEntries(
        Array.from(document.querySelectorAll(`[data-color-palette="${palette}"][data-color-key]`))
            .map((input) => [input.dataset.colorKey, input]),
    );
    const parseHex = (hex) => {
        const match = /^#([0-9a-f]{6})$/i.exec(hex || '');
        if (!match) return null;
        const digits = match[1];
        return [0, 2, 4].map((index) => parseInt(digits.slice(index, index + 2), 16) / 255);
    };
    const luminance = (hex) => {
        const rgb = parseHex(hex);
        if (!rgb) return null;
        const linear = rgb.map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
    };
    const contrastRatio = (foreground, background) => {
        const first = luminance(foreground);
        const second = luminance(background);
        if (first === null || second === null) return 0;
        return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
    };

    const contrastOutput = document.getElementById('contrastStatus');
    const paletteField = document.getElementById('colorPaletteValue');
    const paletteStatus = document.getElementById('colorPaletteStatus');
    const paletteCards = Array.from(document.querySelectorAll('[data-palette-card]'));
    const markPaletteCustom = () => {
        if (paletteField) paletteField.value = 'custom';
        root.dataset.uiPalette = 'custom';
        paletteCards.forEach((card) => {
            card.classList.remove('is-active');
            card.setAttribute('aria-pressed', 'false');
            const label = card.querySelector('small');
            if (label) label.textContent = 'اعمال روی همهٔ صفحه‌ها';
        });
        if (paletteStatus) paletteStatus.textContent = 'رنگ‌های شخصی‌شده؛ برای اعمال در همهٔ صفحه‌ها «ذخیرهٔ تنظیمات» را بزنید.';
    };
    const checkContrast = () => {
        if (!contrastOutput) return;
        const checks = [];
        for (const palette of ['light', 'dark']) {
            const inputs = colorInputs(palette);
            const label = palette === 'light' ? 'روز' : 'شب';
            const pairs = [
                ['متن و پس‌زمینه', 'text', 'background'],
                ['متن و کارت', 'text', 'surface'],
                ['متن دکمهٔ اصلی', 'button_text', 'button'],
                ['متن دکمهٔ فرعی', 'secondary_button_text', 'secondary_button'],
                ['متن سرستون', 'table_header_text', 'table_header'],
                ['متن ردیف جدول', 'text', 'table_row'],
                ['متن ردیف دوم جدول', 'text', 'table_row_alt'],
            ];
            pairs.forEach(([description, foregroundKey, backgroundKey]) => {
                const foreground = inputs[foregroundKey]?.value;
                const background = inputs[backgroundKey]?.value;
                const ratio = contrastRatio(foreground, background);
                checks.push({label: `${label}: ${description}`, ratio});
            });
        }
        const failures = checks.filter((item) => item.ratio < 4.5);
        const minimum = Math.min(...checks.map((item) => item.ratio));
        contrastOutput.classList.toggle('is-warning', failures.length > 0);
        contrastOutput.classList.toggle('is-good', failures.length === 0);
        if (failures.length) {
            const examples = failures.slice(0, 3).map((item) => `${item.label} (${item.ratio.toFixed(2)}:1)`).join('، ');
            contrastOutput.textContent = `هشدار کنتراست: ${failures.length} ترکیب از ${checks.length} مورد کمتر از ۴٫۵:۱ است. ${examples}`;
        } else {
            contrastOutput.textContent = `کنتراست متن در هر دو پالت مناسب است؛ کمترین نسبت ${minimum.toFixed(2)}:1 (حد توصیه‌شده ۴٫۵:۱).`;
        }
    };

    document.querySelectorAll('[data-color-palette][data-color-key]').forEach((input) => {
        const palette = input.dataset.colorPalette;
        const key = input.dataset.colorKey;
        const code = input.parentElement.querySelector('code');
        const updateColor = () => {
            const value = input.value.toLowerCase();
            markPaletteCustom();
            const variables = palette === 'dark' ? darkVariables[key] : lightVariables[key];
            (variables || []).forEach((variable) => root.style.setProperty(variable, value));
            if (code) code.textContent = value;
            if (key === 'button') {
                const themeMeta = document.querySelector('meta[name="theme-color"]');
                const currentTheme = root.dataset.theme;
                if (themeMeta && ((palette === 'light' && currentTheme !== 'dark') || (palette === 'dark' && currentTheme === 'dark'))) {
                    themeMeta.content = value;
                }
            }
            checkContrast();
        };
        input.addEventListener('input', updateColor);
        input.addEventListener('change', updateColor);
    });
    checkContrast();

    document.querySelectorAll('[data-ui-setting]').forEach((select) => {
        const updateSetting = () => {
            const key = select.dataset.uiSetting;
            if (key === 'density') root.dataset.uiDensity = select.value;
            if (key === 'card-size') root.dataset.uiCardSize = select.value;
            if (key === 'style') root.dataset.uiStyle = select.value;
            if (key === 'font') root.dataset.uiFont = select.value;
            if (key === 'text-scale') {
                root.dataset.uiTextScale = select.value;
                if (typeof window.applyUserTextScale === 'function') window.applyUserTextScale();
            }
            if (key === 'line-spacing') root.dataset.uiLineSpacing = select.value;
            if (key === 'motion') root.dataset.uiMotion = select.value;
        };
        select.addEventListener('change', updateSetting);
    });
})();
