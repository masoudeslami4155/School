(() => {
    const app = document.querySelector('#aiDocuments');
    if (!app) return;

    const search = app.querySelector('#aiStudentSearch');
    const typeSelect = app.querySelector('#aiDocumentType');
    const studentList = app.querySelector('#aiStudentList');
    const countText = app.querySelector('#aiSelectionCount');
    const generateButton = app.querySelector('#aiGenerate');
    const printButton = app.querySelector('#aiPrint');
    const preview = app.querySelector('#aiPreview');
    const loading = app.querySelector('#aiLoading');
    const errorBox = app.querySelector('#aiError');
    const title = app.querySelector('#aiPreviewTitle');
    const consent = app.querySelector('#aiExternalConsent');
    let currentPaper = 'a4-portrait';

    // ── انتخاب سرویس و مدل ──────────────────────────────────────────────
    // سرویس و مدل انتخابی هر کاربر جداگانه ذخیره می‌شود؛ فهرست مدل‌های
    // Ollama محلی خودکار خوانده می‌شود تا کاربر مجبور به تایپ دستی نباشد.
    const providerSelect = app.querySelector('#aiProviderSelect');
    const modelSelect = app.querySelector('#aiModelSelect');
    const refreshModelsButton = app.querySelector('#aiRefreshModels');
    const providerStatus = app.querySelector('#aiProviderStatus');
    const consentRow = app.querySelector('#aiConsentRow');
    const localNote = app.querySelector('#aiLocalNote');
    const modelRow = app.querySelector('#aiModelRow');
    const saveModelButton = app.querySelector('#aiSaveModel');
    const connectionProvider = app.querySelector('#aiConnectionProvider');
    const connectionUrl = app.querySelector('#aiConnectionUrl');
    const connectionModel = app.querySelector('#aiConnectionModel');
    const connectionKey = app.querySelector('#aiConnectionKey');
    const connectionSave = app.querySelector('#aiConnectionSave');
    const connectionStatus = app.querySelector('#aiConnectionStatus');
    let currentProvider = app.dataset.provider;

    function isRemote(provider) {
        return ['gemini','openai-compatible'].includes(provider);
    }

    function isConfigured() {
        return app.dataset.configured === '1';
    }

    function updateGenerateButton() {
        if (generateButton) generateButton.disabled = !isConfigured();
    }

    function setProviderStatus(text, isError = false) {
        if (!providerStatus) return;
        providerStatus.textContent = text;
        providerStatus.classList.toggle('is-error', isError);
    }

    // ردیف رضایت اینترنتی، یادآوری محلی و کادر مدل با سرویس انتخابی هماهنگ می‌شوند؛
    // مدل سرویس اینترنتی از ثبت مدیر می‌آید و اینجا قابل تغییر نیست.
    function updateServiceVisibility() {
        const remote = isRemote(app.dataset.profileId ? app.dataset.provider : providerSelect?.value);
        if (consentRow) consentRow.hidden = !remote;
        if (localNote) localNote.hidden = remote;
        if (modelRow) modelRow.hidden = remote || !!app.dataset.profileId;
    }

    function fillModels(models, online, keep) {
        const previous = keep ? modelSelect.value : '';
        modelSelect.innerHTML = '';
        if (!models.length) {
            modelSelect.append(new Option(online ? 'مدلی روی Ollama نصب نیست' : 'Ollama در دسترس نیست', ''));
            return;
        }
        for (const model of models) {
            modelSelect.append(new Option(model.label || model.name, model.name));
        }
        if (previous && !models.some((model) => model.name === previous)) {
            modelSelect.append(new Option(`${previous} (نصب نیست)`, previous));
        }
        if (previous) modelSelect.value = previous;
    }

    async function loadModels(keep = true) {
        modelSelect.disabled = true;
        try {
            const response = await fetch(app.dataset.modelsUrl);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'خواندن مدل‌ها ممکن نشد.');
            fillModels(data.models || [], Boolean(data.online), keep);
            if (!data.models?.length) {
                setProviderStatus(data.online ? 'مدلی روی Ollama نصب نیست.' : 'Ollama در دسترس نیست؛ برنامهٔ Ollama را اجرا کنید.', true);
            } else if (!app.dataset.model) {
                setProviderStatus('یکی از مدل‌های نصب‌شده را انتخاب کنید.');
            } else {
                setProviderStatus(`${providerSelect.selectedOptions[0]?.text || ''} — ${app.dataset.model}`);
            }
        } catch (error) {
            fillModels([], false, false);
            setProviderStatus(error.message || 'خواندن مدل‌ها ممکن نشد.', true);
        } finally {
            modelSelect.disabled = false;
        }
    }

    async function saveSelection() {
        const provider = providerSelect.value;
        const model = provider === 'ollama' ? modelSelect.value : '';
        if (provider === 'ollama' && !model) {
            setProviderStatus('ابتدا یک مدل نصب‌شدهٔ Ollama را انتخاب کنید.', true);
            return false;
        }
        providerSelect.disabled = true;
        try {
            const response = await fetch(app.dataset.selectUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': app.dataset.csrf },
                body: JSON.stringify({ provider, model }),
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'ذخیرهٔ انتخاب انجام نشد.');
            app.dataset.provider = data.provider.provider;
            app.dataset.model = data.provider.model;
            app.dataset.configured = data.provider.configured ? '1' : '0';
            currentProvider = data.provider.provider;
            setProviderStatus(`${data.provider.provider_label} — ${data.provider.model || 'بدون مدل'}`);
            updateGenerateButton();
            return true;
        } catch (error) {
            setProviderStatus(error.message || 'ذخیرهٔ انتخاب انجام نشد.', true);
            providerSelect.value = app.dataset.provider;
            modelSelect.value = app.dataset.model;
            return false;
        } finally {
            providerSelect.disabled = false;
        }
    }

    // گزینه‌های سرویس پس از ثبت اتصال تازه از پاسخ سرور ساخته می‌شوند تا
    // کاربر برای انتخابِ همان اتصال به صفحه‌ٔ تنظیمات برنگردد.
    function applyChoices(choices) {
        const previous = providerSelect.value;
        providerSelect.innerHTML = '';
        for (const choice of choices) {
            const option = new Option(choice.label, choice.key);
            option.dataset.remote = choice.remote ? '1' : '0';
            option.dataset.model = choice.model || '';
            option.disabled = !choice.ready;
            providerSelect.append(option);
        }
        const keep = [...providerSelect.options].find((option) => option.value === previous && !option.disabled);
        if (keep) providerSelect.value = previous;
        updateServiceVisibility();
    }

    function setConnectionStatus(text, isError = false) {
        if (!connectionStatus) return;
        connectionStatus.textContent = text;
        connectionStatus.hidden = !text;
        connectionStatus.classList.toggle('is-error', isError);
    }

    // ثبت اتصال اینترنتی از همین صفحه (فقط مدیر): نشانی و کلید یک‌بار ذخیره
    // می‌شود و بعد همان سرویس برای این حساب انتخاب می‌گردد.
    async function saveConnection() {
        const provider = connectionProvider?.value || '';
        const baseUrl = connectionUrl?.value.trim() || '';
        const model = connectionModel?.value.trim() || '';
        const apiKey = connectionKey?.value.trim() || '';
        if (!baseUrl) { setConnectionStatus('نشانی پایهٔ API را وارد کنید.', true); return; }
        if (!model) { setConnectionStatus('نام مدل را وارد کنید.', true); return; }
        connectionSave.disabled = true;
        setConnectionStatus('در حال ذخیره…');
        try {
            const response = await fetch(app.dataset.connectionUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': app.dataset.csrf },
                body: JSON.stringify({ provider, base_url: baseUrl, model, api_key: apiKey }),
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'ذخیرهٔ اتصال انجام نشد.');
            app.dataset.configured = '1';
            app.dataset.provider = data.provider.provider;
            app.dataset.model = data.provider.model;
            currentProvider = data.provider.provider;
            applyChoices(data.choices || []);
            providerSelect.value = data.provider.provider;
            if (connectionKey) connectionKey.value = '';
            await saveSelection();
            invalidatePreview();
            setConnectionStatus(`ذخیره شد: ${data.provider.provider_label} — ${data.provider.model}. از این پس همین اتصال استفاده می‌شود.`);
        } catch (error) {
            setConnectionStatus(error.message || 'ذخیرهٔ اتصال انجام نشد.', true);
        } finally {
            connectionSave.disabled = false;
        }
    }

    connectionSave?.addEventListener('click', saveConnection);
    saveModelButton?.addEventListener('click', async () => {
        if (await saveSelection()) {
            setProviderStatus(`${providerSelect.selectedOptions[0]?.text || ''} — ${app.dataset.model || 'بدون مدل'} (ذخیره شد)`);
        }
    });

    providerSelect?.addEventListener('change', async () => {
        // هر سرویس اینترنتی به رضایت تازه نیاز دارد.
        if (consent) consent.checked = false;
        updateServiceVisibility();
        if (providerSelect.value === 'ollama') {
            // مدلِ به‌جامانده از سرویس اینترنتی روی Ollama نصب نیست؛ فقط وقتی
            // سرویس قبلی هم محلی بود، مدل انتخابی قبلی نگه داشته می‌شود.
            await loadModels(currentProvider === 'ollama');
            if (currentProvider !== 'ollama') {
                setProviderStatus('یکی از مدل‌های نصب‌شدهٔ Ollama را انتخاب کنید.');
                return;
            }
        }
        if (await saveSelection()) invalidatePreview();
    });
    modelSelect?.addEventListener('change', async () => {
        if (await saveSelection()) invalidatePreview();
    });
    refreshModelsButton?.addEventListener('click', () => loadModels(true));
    if(app.dataset.profileId){providerSelect.disabled=true;saveModelButton.disabled=true;providerStatus.textContent='اتصال منتخب: '+app.dataset.model+' (ذخیره‌شده؛ سلامت در تنظیمات)';}
    if (providerSelect && modelSelect) {
        updateServiceVisibility();
        if (providerSelect.value === 'ollama' && !app.dataset.profileId) loadModels(true);
    }

    function selectedInputs() {
        return [...studentList.querySelectorAll('input[type="checkbox"]:checked')];
    }

    function updateSelection() {
        const count = selectedInputs().length;
        countText.textContent = `${count} نفر انتخاب شده`;
        studentList.classList.toggle('is-single-only', typeSelect.value === 'receipt');
        studentList.querySelectorAll('input[type="checkbox"]').forEach((input) => {
            input.disabled = typeSelect.value === 'receipt' && count > 0 && !input.checked;
        });
    }

    function invalidatePreview() {
        if (printButton.disabled) return;
        printButton.disabled = true;
        title.textContent = 'برای تغییرات جدید، پیش‌نمایش را دوباره بسازید';
    }

    function paperRules(paper) {
        const options = {
            'a4-portrait': { size: 'A4 portrait', width: '210mm', height: '297mm', margin: '12mm' },
            'a4-landscape': { size: 'A4 landscape', width: '297mm', height: '210mm', margin: '12mm' },
            a5: { size: 'A5 portrait', width: '148mm', height: '210mm', margin: '9mm' },
            card: { size: '90mm 50mm', width: '90mm', height: '50mm', margin: '4mm' },
        };
        return options[paper] || options['a4-portrait'];
    }

    // فونت پروژه باید داخل خودِ iframe تعریف شود؛ @font-face صفحهٔ اصلی
    // روی سند srcdoc اثر ندارد. font-src 'self' اجازهٔ خواندن woff2
    // محلی (همان مسیر app.css، کاملاً آفلاین) را می‌دهد.
    const FONT_FACES = [
        ['Regular', 400], ['Medium', 500], ['SemiBold', 600],
        ['Bold', 700], ['ExtraBold', 800], ['Black', 900],
    ].map(([name, weight]) =>
        `@font-face{font-family:Vazirmatn;src:url('/static/Vazirmatn-${name}.woff2') format('woff2');font-weight:${weight};font-display:block}`
    ).join('');

    function buildPreviewDocument(body, paper, isLetter) {
        const page = paperRules(paper);
        // نامهٔ اداری خودش اندازهٔ ثابت کاغذ و حاشیه دارد؛ پیوستون
        // چاپ نباید حاشیهٔ تکراری اضافه کند.
        const copyRule = isLetter
            ? '.ai-letter-copy{position:relative;display:block;width:fit-content;margin:0 auto 20px;background:#fff;box-shadow:0 10px 28px #10233a24}'
            : `.ai-document-copy{position:relative;display:block;width:min(100%,${page.width});min-height:${page.height};margin:0 auto 20px;padding:${page.margin};background:#fff;box-shadow:0 10px 28px #10233a24}`;
        const printRule = isLetter
            ? '.ai-letter-copy{margin:0;box-shadow:none;break-after:page;page-break-after:always}'
            : `.ai-document-copy{width:${page.width};height:auto;min-height:${page.height};margin:0;padding:${page.margin};box-shadow:none;break-after:page;page-break-after:always}`;
        const copyClass = isLetter ? 'ai-letter-copy' : 'ai-document-copy';
        const content=!isLetter && body.includes('ai-document-copy') ? body : `<div class="${copyClass}">${body}</div>`;
        return `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'self' data:"><style>
            ${FONT_FACES}
            *{box-sizing:border-box}html,body{margin:0;background:#eef2f6;color:#172033;font-family:Vazirmatn,Tahoma,Arial,sans-serif;direction:rtl}
            .ai-document-copy,.ai-document-copy *,.ai-letter-copy,.ai-letter-copy *{font-family:Vazirmatn,Tahoma,Arial,sans-serif !important}
            body{padding:18px}${copyRule}
            .ai-document-copy:last-child,.ai-letter-copy:last-child{break-after:auto;page-break-after:auto}
            @page{size:${page.size};margin:0}
            @media print{html,body{background:#fff}body{padding:0}${printRule}.ai-document-copy:last-child,.ai-letter-copy:last-child{break-after:auto;page-break-after:auto}}
        </style></head><body>${content}</body></html>`;
    }

    window.aiShowDocument=(body,paper,isLetter=false)=>{currentPaper=paper;preview.srcdoc=buildPreviewDocument(body,paper,isLetter);printButton.disabled=false;};

    search?.addEventListener('input', () => {
        const query = search.value.trim().toLocaleLowerCase('fa');
        studentList.querySelectorAll('.ai-docs__student').forEach((item) => {
            item.hidden = !!query && !item.textContent.toLocaleLowerCase('fa').includes(query);
        });
    });
    studentList?.addEventListener('change', () => {
        updateSelection();
        invalidatePreview();
    });
    typeSelect?.addEventListener('change', () => {
        updateSelection();
        invalidatePreview();
    });
    app.querySelector('#aiPaper')?.addEventListener('change', invalidatePreview);
    app.querySelector('#aiBrief')?.addEventListener('input', invalidatePreview);
    updateSelection();

    generateButton?.addEventListener('click', async () => {
        errorBox.hidden = true;
        const selected = selectedInputs();
        const brief = app.querySelector('#aiBrief').value.trim();
        if (!selected.length) {
            errorBox.textContent = 'ابتدا یک یا چند دانش‌آموز را انتخاب کنید.';
            errorBox.hidden = false;
            return;
        }
        if (typeSelect.value === 'receipt' && selected.length !== 1) {
            errorBox.textContent = 'رسید را برای هر بار فقط به نام یک دانش‌آموز بسازید.';
            errorBox.hidden = false;
            return;
        }
        if (!brief) {
            errorBox.textContent = 'شرح متن و طرح را وارد کنید.';
            errorBox.hidden = false;
            return;
        }
        if (!isConfigured()) {
            errorBox.textContent = 'ابتدا یک سرویس و مدل آماده انتخاب کنید.';
            errorBox.hidden = false;
            return;
        }
        if (isRemote(app.dataset.provider) && !consent.checked) {
            errorBox.textContent = 'برای استفاده از API اینترنتی، اجازهٔ ارسال اطلاعات انتخاب‌شده را تأیید کنید.';
            errorBox.hidden = false;
            return;
        }

        generateButton.disabled = true;
        printButton.disabled = true;
        loading.hidden = false;
        try {
            const response = await fetch(app.dataset.generateUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': app.dataset.csrf },
                body: JSON.stringify({
                    ...(window.aiDocumentFields ? window.aiDocumentFields() : {}),
                    document_type: typeSelect.value,
                    ...(window.aiDocumentFields ? window.aiDocumentFields() : {}),
                    student_ids: selected.map((input) => input.value),
                    brief,
                    paper: app.querySelector('#aiPaper').value,
                    allow_external_data: isRemote(app.dataset.provider) && Boolean(consent.checked),
                }),
            });
            const result = await response.json();
            if (!response.ok || !result.ok) throw new Error(result.error || 'ساخت سند انجام نشد.');
            currentPaper = result.paper;
            title.textContent = result.title;
            preview.srcdoc = buildPreviewDocument(result.html, currentPaper);
            printButton.disabled = false;
            window.dispatchEvent(new CustomEvent('ai-document-generated',{detail:result}));
        } catch (error) {
            errorBox.textContent = error.message || 'اتصال به سرویس هوش مصنوعی برقرار نشد.';
            errorBox.hidden = false;
        } finally {
            loading.hidden = true;
            updateGenerateButton();
        }
    });

    const generateLetterButton = app.querySelector('#aiGenerateLetter');
    typeSelect?.addEventListener('change', () => {
        generateLetterButton.disabled = typeSelect.value !== 'letter';
    });
    generateLetterButton?.addEventListener('click', async () => {
        errorBox.hidden = true;
        const selected = selectedInputs();
        if (!selected.length) {
            errorBox.textContent = 'ابتدا یک دانشآموز را انتخاب کنید.';
            errorBox.hidden = false;
            return;
        }
        const brief = app.querySelector('#aiBrief').value.trim();
        if (!brief) {
            errorBox.textContent = 'متن نامه را در «شرح متن و طرح» بنویسید.';
            errorBox.hidden = false;
            return;
        }
        generateLetterButton.disabled = true;
        loading.hidden = false;
        try {
            const response = await fetch(app.dataset.generateLetterUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': app.dataset.csrf },
                body: JSON.stringify({
                    ...(window.aiDocumentFields ? window.aiDocumentFields() : {}),
                    student_ids: selected.map((input) => input.value),
                    brief,
                    paper: app.querySelector('#aiPaper').value,
                    template: app.querySelector('#aiLetterTemplate')?.value || '',
                }),
            });
            const result = await response.json();
            if (!response.ok || !result.ok) throw new Error(result.error || 'ساخت نامه انجام نشد.');
            currentPaper = result.paper || 'a4-portrait';
            title.textContent = result.title;
            preview.srcdoc = buildPreviewDocument(result.html, currentPaper, true);
            printButton.disabled = false;
            window.dispatchEvent(new CustomEvent('ai-document-generated',{detail:result}));
        } catch (error) {
            errorBox.textContent = error.message || 'ساخت نامه با خطا مواجه شد.';
            errorBox.hidden = false;
        } finally {
            loading.hidden = true;
            generateLetterButton.disabled = false;
        }
    });

    printButton?.addEventListener('click', () => {
        if(window.aiPrintBlocked){errorBox.textContent='متن از محدودهٔ چاپ خارج است؛ چیدمان را اصلاح یا خروجی PDF متنی بگیرید.';errorBox.hidden=false;return;}
        if (!preview.contentWindow || printButton.disabled) return;
        preview.contentWindow.focus();
        preview.contentWindow.print();
    });
})();
