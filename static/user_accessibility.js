(() => {
    const root = document.documentElement;
    const tracked = new Map();
    const ignored = new Set(['SCRIPT', 'STYLE', 'SVG', 'PATH', 'I', 'CODE', 'PRE']);
    let suspended = false;

    const hasOwnText = (element) => Array.from(element.childNodes).some(
        (node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0,
    );
    const isTextControl = (element) => ['INPUT', 'SELECT', 'TEXTAREA', 'OPTION'].includes(element.tagName);
    const canScale = (element) => {
        if (!(element instanceof Element) || ignored.has(element.tagName)) return false;
        if (element.closest('svg, i, code, pre, script, style')) return false;
        return isTextControl(element) || hasOwnText(element);
    };
    const remember = (element) => {
        if (!canScale(element) || tracked.has(element)) return;
        tracked.set(element, {
            value: element.style.getPropertyValue('font-size'),
            priority: element.style.getPropertyPriority('font-size'),
        });
    };
    const rememberTree = (node) => {
        if (!(node instanceof Element)) return;
        remember(node);
        node.querySelectorAll('*').forEach(remember);
    };
    const restore = (element, original) => {
        if (original.value) element.style.setProperty('font-size', original.value, original.priority);
        else element.style.removeProperty('font-size');
    };
    const scaleFactor = () => ({normal: 1, large: 1.1, larger: 1.22}[root.dataset.uiTextScale] || 1);

    const applyUserTextScale = () => {
        if (suspended) return;
        const factor = scaleFactor();
        tracked.forEach((original, element) => {
            if (!element.isConnected) {
                tracked.delete(element);
                return;
            }
            restore(element, original);
            if (factor === 1) return;
            const base = Number.parseFloat(window.getComputedStyle(element).fontSize);
            if (Number.isFinite(base) && base > 0) {
                element.style.setProperty('font-size', `${Math.round(base * factor * 100) / 100}px`);
            }
        });
    };
    window.applyUserTextScale = applyUserTextScale;

    rememberTree(document.body);
    applyUserTextScale();

    if ('MutationObserver' in window) {
        const observer = new MutationObserver((records) => {
            if (suspended) return;
            records.forEach((record) => record.addedNodes.forEach(rememberTree));
            applyUserTextScale();
        });
        observer.observe(document.body, {childList: true, subtree: true});
    }

    let resizeTimer;
    window.addEventListener('resize', () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(applyUserTextScale, 120);
    }, {passive: true});

    window.addEventListener('beforeprint', () => {
        suspended = true;
        tracked.forEach((original, element) => restore(element, original));
    });
    window.addEventListener('afterprint', () => {
        suspended = false;
        rememberTree(document.body);
        applyUserTextScale();
    });
})();
