/**
 * Glassmorphism Mobile Features — نسخه ۴.۵۵
 * سوایپ، انیمیشن، منوی شیشه‌ای و حالت تمام‌صفحه
 */
(function() {
    'use strict';

    // تشخیص دستگاه لمسی
    const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

    // سوایپ برای ناوبری بین بخش‌ها
    let touchStartX = 0;
    let touchStartY = 0;
    let touchEndX = 0;
    let touchEndY = 0;

    const swipeThreshold = 50;

    function handleTouchStart(e) {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
    }

    function handleTouchEnd(e) {
        touchEndX = e.changedTouches[0].screenX;
        touchEndY = e.changedTouches[0].screenY;
        handleSwipe();
    }

    function handleSwipe() {
        const diffX = touchEndX - touchStartX;
        const diffY = touchEndY - touchStartY;

        if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > swipeThreshold) {
            if (diffX > 0) {
                // سوایپ به راست
                document.dispatchEvent(new CustomEvent('glass-swipe-right'));
            } else {
                // سوایپ به چپ
                document.dispatchEvent(new CustomEvent('glass-swipe-left'));
            }
        }
    }

    // منوی شیشه‌ای موبایل
    function initGlassMenu() {
        const menu = document.querySelector('.glass-mobile-menu');
        if (!menu) return;

        const toggle = document.getElementById('mobileMenuTrigger');
        if (toggle) {
            toggle.addEventListener('click', function() {
                menu.classList.toggle('is-open');
                toggle.setAttribute('aria-expanded', menu.classList.contains('is-open'));
            });
        }

        // بستن منو با کلیک بیرون
        document.addEventListener('click', function(e) {
            if (!menu.contains(e.target) && !e.target.closest('#mobileMenuTrigger')) {
                menu.classList.remove('is-open');
            }
        });
    }

    // حالت تمام‌صفحه
    function initFullscreen() {
        const fullscreenBtn = document.getElementById('fullscreenToggle');
        if (!fullscreenBtn) return;

        fullscreenBtn.addEventListener('click', function() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(function(err) {
                    console.error('خطا در فعال‌سازی تمام‌صفحه:', err);
                });
            } else {
                document.exitFullscreen();
            }
        });

        // به‌روزرسانی آیکن بر اساس وضعیت
        document.addEventListener('fullscreenchange', function() {
            const icon = fullscreenBtn.querySelector('i');
            if (document.fullscreenElement) {
                icon.className = 'cil-exit-fullscreen';
                fullscreenBtn.title = 'خروج از تمام‌صفحه';
            } else {
                icon.className = 'cil-fullscreen';
                fullscreenBtn.title = 'تمام‌صفحه';
            }
        });
    }

    // انیمیشن ورود المان‌ها
    function initAnimations() {
        const animatedElements = document.querySelectorAll('.glass-animate-in');
        animatedElements.forEach(function(el, index) {
            el.style.animationDelay = (index * 0.1) + 's';
        });
    }

    // مقداردهی اولیه
    if (isTouchDevice) {
        document.addEventListener('touchstart', handleTouchStart, { passive: true });
        document.addEventListener('touchend', handleTouchEnd, { passive: true });
    }

    document.addEventListener('DOMContentLoaded', function() {
        initGlassMenu();
        initFullscreen();
        initAnimations();
    });

    // در دسترس قرار دادن برای استفاده خارجی
    window.GlassDesign = {
        isTouchDevice: isTouchDevice,
        swipeThreshold: swipeThreshold
    };
})();
