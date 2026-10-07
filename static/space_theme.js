/* Space Glass Theme — لایه‌های فضایی
   ستاره‌ها، کهکشان، منظومه شمسی، دنباله‌دار و شهاب تعاملی (کلیک روی فضای خالی)
   بدون وابستگی، آفلاین و سبک. برای چاپ غیرفعال است. */
(function () {
    'use strict';
    if (document.getElementById('spaceStars')) return;

    var reduceMotion = false;
    try {
        reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* مرورگر قدیمی */ }

    function ensureLayer(tag, id, className) {
        var el = document.getElementById(id);
        if (el) return el;
        el = document.createElement(tag);
        el.id = id;
        if (className) el.className = className;
        el.setAttribute('aria-hidden', 'true');
        (document.body || document.documentElement).appendChild(el);
        return el;
    }

    // لایه ستاره‌ها (استایل در space_theme.css)
    ensureLayer('div', 'spaceStars', 'space-stars');
    // کهکشان راه شیری کم‌رنگ
    ensureLayer('div', 'spaceGalaxy', 'space-galaxy');

    // ستاره‌های درشت با هاله نور (موقعیت‌های ثابت پراکنده روی صفحه)
    if (!document.getElementById('spaceStarsBright')) {
        var bright = ensureLayer('div', 'spaceStarsBright', 'space-stars-bright');
        var brightSpots = [
            [7, 22, 7], [13, 68, 6], [22, 40, 8], [28, 12, 5], [33, 80, 7],
            [41, 30, 6], [48, 58, 9], [55, 16, 6], [61, 84, 7], [66, 46, 8],
            [72, 70, 6], [79, 24, 8], [84, 60, 6], [90, 38, 7], [95, 76, 6],
            [18, 88, 5], [36, 52, 6], [59, 8, 5], [76, 92, 6], [88, 16, 5]
        ];
        for (var b = 0; b < brightSpots.length; b++) {
            var spot = document.createElement('span');
            var size = brightSpots[b][2];
            spot.style.left = brightSpots[b][1] + '%';
            spot.style.top = brightSpots[b][0] + '%';
            spot.style.width = size + 'px';
            spot.style.height = size + 'px';
            spot.style.animationDelay = (-(b * 0.7) % 6) + 's';
            bright.appendChild(spot);
        }
    }

    if (!reduceMotion) {
        // دنباله‌دار خودکار
        ensureLayer('div', 'spaceComet', 'comet');
        ensureLayer('div', 'spaceCometMinor', 'comet comet--minor');

        // منظومه شمسی اصلی گوشه صفحه: خورشید + ۳ مدار با سیاره
        var solar = ensureLayer('div', 'spaceSolar', 'space-solar');
        if (!solar.dataset.built) {
            solar.dataset.built = '1';
            solar.innerHTML =
                '<span class="space-sun"></span>' +
                '<span class="space-orbit space-orbit--1"><span class="orbit-spin"><span class="space-planet planet--a"></span></span></span>' +
                '<span class="space-orbit space-orbit--2"><span class="orbit-spin"><span class="space-planet planet--b"></span></span></span>' +
                '<span class="space-orbit space-orbit--3"><span class="orbit-spin"><span class="space-planet planet--c"></span></span></span>';
        }

        // دو منظومه فرعی کوچک‌تر (نمای دورتر) در نقاط دیگر صفحه
        var miniTop = ensureLayer('div', 'spaceSolarTop', 'space-solar space-solar--mini space-solar--top');
        var miniMid = ensureLayer('div', 'spaceSolarMid', 'space-solar space-solar--mini space-solar--mid');
        if (!miniTop.dataset.built || !miniMid.dataset.built) {
            var miniHTML =
                '<span class="space-sun space-sun--cool"></span>' +
                '<span class="space-orbit space-orbit--1"><span class="orbit-spin"><span class="space-planet planet--a"></span></span></span>' +
                '<span class="space-orbit space-orbit--2"><span class="orbit-spin"><span class="space-planet planet--b"></span></span></span>' +
                '<span class="space-orbit space-orbit--3"><span class="orbit-spin"><span class="space-planet planet--c"></span></span></span>';
            if (!miniTop.dataset.built) { miniTop.dataset.built = '1'; miniTop.innerHTML = miniHTML; }
            if (!miniMid.dataset.built) { miniMid.dataset.built = '1'; miniMid.innerHTML = miniHTML; }
        }

        // شهاب تعاملی: کلیک/لمس روی فضای خالی (نه روی دکمه، لینک و فرم)
        document.addEventListener('pointerdown', function (event) {
            var t = event.target;
            if (t && t.closest && t.closest('a, button, input, select, textarea, label, summary, form, .stat-card, .student-card, .quick-action, nav, header, .mobile-bottom-nav')) return;
            var shot = document.createElement('span');
            shot.className = 'click-comet';
            var angle = -12 - Math.round(Math.random() * 26); // بین ‎-۱۲ تا ‎-۳۸ درجه
            shot.style.setProperty('--angle', angle + 'deg');
            shot.style.left = (event.clientX + 10) + 'px';
            shot.style.top = (event.clientY - 6) + 'px';
            document.body.appendChild(shot);
            shot.addEventListener('animationend', function () { shot.remove(); });
            setTimeout(function () { shot.remove(); }, 1600); // پاک‌سازی اطمینان
        }, { passive: true });
    }

    // اگر صفحه دیر لود شده باشد، لایه‌ها را به body منتقل کن
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            ['spaceStars', 'spaceGalaxy', 'spaceSolar'].forEach(function (id) {
                var el = document.getElementById(id);
                if (el && el.parentNode !== document.body) document.body.appendChild(el);
            });
        });
    }
})();
