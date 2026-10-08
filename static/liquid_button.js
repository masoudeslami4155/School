/* ============================================================
   Liquid metal button — behaviour layer (vanilla, offline).
   Replaces the React state machine of the shadcn component:
     hover  -> faster metal flow
     press  -> depth + inner shadow
     click  -> ripple from the pointer position
   Usage: <button class="lmb" data-liquid-button>...</button>
   Optional: data-liquid-mode="text|icon", data-liquid-block
   ============================================================ */
(function () {
    'use strict';

    var RIPPLE_LIFE = 620;   // ms

    function ripple(btn, x, y) {
        var span = document.createElement('span');
        span.className = 'lmb__ripple';
        span.style.left = x + 'px';
        span.style.top = y + 'px';
        btn.appendChild(span);
        window.setTimeout(function () {
            if (span.parentNode) { span.parentNode.removeChild(span); }
        }, RIPPLE_LIFE);
    }

    function localPoint(btn, clientX, clientY) {
        var rect = btn.getBoundingClientRect();
        return { x: clientX - rect.left, y: clientY - rect.top };
    }

    function attach(btn) {
        if (btn.dataset.lmbInit) { return; }
        btn.dataset.lmbInit = '1';

        /* mode: circle vs pill */
        var mode = btn.getAttribute('data-liquid-mode');
        if (mode === 'icon') { btn.classList.add('lmb--icon'); }
        /* optional full-width on small screens */
        if (btn.hasAttribute('data-liquid-block')) { btn.classList.add('lmb--block'); }

        /* keep the original click handlers working: we only decorate */
        btn.addEventListener('pointerdown', function (e) {
            btn.classList.add('is-pressed');
            var p = localPoint(btn, e.clientX, e.clientY);
            ripple(btn, p.x, p.y);
        });
        ['pointerup', 'pointerleave', 'pointercancel'].forEach(function (evt) {
            btn.addEventListener(evt, function () { btn.classList.remove('is-pressed'); });
        });
        btn.addEventListener('keydown', function (e) {
            if (e.key === ' ' || e.key === 'Enter') { btn.classList.add('is-pressed'); }
        });
        btn.addEventListener('keyup', function () { btn.classList.remove('is-pressed'); });
        btn.addEventListener('blur', function () { btn.classList.remove('is-pressed'); });
    }

    function init() {
        Array.prototype.forEach.call(document.querySelectorAll('[data-liquid-button]'), function (el) {
            /* anchors and buttons both supported */
            if (el.tagName === 'A') { el.setAttribute('role', 'button'); }
            attach(el);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.LiquidButton = { init: init };
})();