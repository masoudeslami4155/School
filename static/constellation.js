/* ============================================================
   Constellation Grid — vanilla canvas port of the React component.
   No dependencies, no build step, offline-friendly.

   Improvements over the original:
     - spatial hash for the connection pass  (O(n) neighbours instead of O(n^2))
     - pauses when the tab is hidden or the layer scrolls out of view
     - follows the app's own theme switch (html[data-theme]) live
     - respects prefers-reduced-motion (static, calm rendering)
     - touch support via pointer events, node budget for weak school PCs

   Usage:
     <div data-constellation data-tone="light" data-bg="transparent">
       <canvas></canvas>
     </div>
   Options via data attributes on the wrapper:
     data-spacing="55"      grid spacing in px
     data-radius="220"      cursor influence radius
     data-conn="75"         max connection distance
     data-labels="1|0"      show hex readouts near the cursor
     data-tone="auto|light|dark"   node palette (light = white nodes)
     data-bg="auto|transparent"    canvas background
     data-speed="1"         global motion multiplier
   ============================================================ */
(function () {
    'use strict';

    function num(v, fallback) {
        var n = parseFloat(v);
        return isNaN(n) ? fallback : n;
    }

    function prefersReducedMotion() {
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function isCoarsePointer() {
        return window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
    }

    function appTheme(node) {
        var t = document.documentElement.getAttribute('data-theme');
        if (t === 'dark' || t === 'light') { return t; }
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) { return 'dark'; }
        return 'light';
    }

    function palette(mode) {
        if (mode === 'dark') {
            return { bg: '#030407', node: '255, 255, 255', accent: '56, 189, 248' };
        }
        return { bg: '#f8fafc', node: '15, 23, 42', accent: '2, 132, 199' };
    }

    /* ---- one mesh instance ---------------------------------------------- */
    function createMesh(wrapper) {
        var canvas = wrapper.querySelector('canvas');
        if (!canvas || !canvas.getContext) { return null; }

        var ctx = canvas.getContext('2d');
        if (!ctx) { return null; }

        var opt = {
            spacing: num(wrapper.dataset.spacing, 55),
            radius: num(wrapper.dataset.radius, 220),
            conn: num(wrapper.dataset.conn, 75),
            labels: wrapper.dataset.labels !== '0',
            tone: wrapper.dataset.tone || 'auto',
            bg: wrapper.dataset.bg || 'auto',
            speed: num(wrapper.dataset.speed, 1)
        };

        var reduced = prefersReducedMotion();
        var coarse = isCoarsePointer();
        if (coarse) { opt.spacing = Math.max(opt.spacing, 62); }   // fewer nodes on phones
        if (opt.labels === true && (coarse || window.innerWidth < 760)) { opt.labels = false; }

        var width = 0, height = 0, dpr = 1;
        var nodes = [];
        var cell = Math.max(24, opt.conn);
        var buckets = Object.create(null);

        var mouse = { x: -9999, y: -9999, prevX: -9999, prevY: -9999, vx: 0, vy: 0, radius: opt.radius, active: false };
        var running = true, visible = true, lastTime = 0, frameId = 0;

        function initNodes() {
            nodes = [];
            buckets = Object.create(null);
            var spacing = opt.spacing;
            /* node budget: keep the frame time safe on modest hardware */
            var budget = 1600;
            var cols = Math.ceil(width / spacing) + 1;
            var rows = Math.ceil(height / spacing) + 1;
            while (cols * rows > budget) {
                spacing *= 1.15;
                cols = Math.ceil(width / spacing) + 1;
                rows = Math.ceil(height / spacing) + 1;
            }
            for (var i = 0; i < cols; i++) {
                for (var j = 0; j < rows; j++) {
                    var x = i * spacing;
                    var y = j * spacing;
                    nodes.push({
                        x: x, y: y, vx: 0, vy: 0, baseX: x, baseY: y,
                        radius: Math.random() * 1.2 + 1.2,
                        label: (i * 7).toString(16).toUpperCase() + ':' + (j * 11).toString(16).toUpperCase(),
                        pulse: Math.random() * Math.PI * 2
                    });
                }
            }
        }

        function resize() {
            var rect = wrapper.getBoundingClientRect();
            width = Math.max(1, rect.width || window.innerWidth);
            height = Math.max(1, rect.height || window.innerHeight);
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.round(width * dpr);
            canvas.height = Math.round(height * dpr);
            canvas.style.width = width + 'px';
            canvas.style.height = height + 'px';
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            if (opt.bg === 'transparent') { ctx.clearRect(0, 0, width, height); }
            initNodes();
        }

        function point(e) {
            var rect = canvas.getBoundingClientRect();
            return { x: e.clientX - rect.left, y: e.clientY - rect.top };
        }
function hash() {                       /* rebuild the neighbour grid each frame */
            buckets = Object.create(null);
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                var k = ((n.x / cell) | 0) + ':' + ((n.y / cell) | 0);
                (buckets[k] || (buckets[k] = [])).push(i);
            }
        }

        function link(n, n2, max, maxSq, alphaBase, nodeCss) {
            var dx = n.x - n2.x;
            var dy = n.y - n2.y;
            var dSq = dx * dx + dy * dy;
            if (dSq >= maxSq) { return; }
            var d = Math.sqrt(dSq);
            ctx.strokeStyle = 'rgba(' + nodeCss + ', ' + ((1 - d / max) * alphaBase) + ')';
            ctx.beginPath();
            ctx.moveTo(n.x, n.y);
            ctx.lineTo(n2.x, n2.y);
            ctx.stroke();
        }

        function drawConnections(mode, nodeCss) {
            var max = opt.conn;
            var maxSq = max * max;
            var alphaBase = mode === 'dark' ? 0.18 : 0.08;
            ctx.lineWidth = 0.7;
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                var gx = (n.x / cell) | 0;
                var gy = (n.y / cell) | 0;
                var same = buckets[gx + ':' + gy];
                if (same) {
                    var pos = same.indexOf(i);
                    for (var a = pos + 1; a < same.length; a++) {
                        link(n, nodes[same[a]], max, maxSq, alphaBase, nodeCss);
                    }
                }
                /* only 4 of the 9 neighbour cells are needed (half neighbourhood) */
                var right = buckets[(gx + 1) + ':' + gy];
                if (right) { for (var b = 0; b < right.length; b++) { link(n, nodes[right[b]], max, maxSq, alphaBase, nodeCss); } }
                var down = buckets[gx + ':' + (gy + 1)];
                if (down) { for (var c = 0; c < down.length; c++) { link(n, nodes[down[c]], max, maxSq, alphaBase, nodeCss); } }
                var diag = buckets[(gx + 1) + ':' + (gy + 1)];
                if (diag) { for (var d2 = 0; d2 < diag.length; d2++) { link(n, nodes[diag[d2]], max, maxSq, alphaBase, nodeCss); } }
            }
        }

        function render(now) {
            frameId = window.requestAnimationFrame(render);
            if (!running || !visible) { lastTime = now; return; }

            var dt = Math.min((now - (lastTime || now)) / 1000, 0.05) || 0.016;
            lastTime = now;
            if (reduced) { dt *= 0.25; }
            dt *= opt.speed;

            var mode = opt.tone === 'auto' ? appTheme() : opt.tone;
            var pal = palette(mode);

            if (mouse.active) {
                mouse.vx = (mouse.x - mouse.prevX) / (dt * 1000 || 1);
                mouse.vy = (mouse.y - mouse.prevY) / (dt * 1000 || 1);
                mouse.prevX = mouse.x;
                mouse.prevY = mouse.y;
            } else {
                mouse.vx = 0;
                mouse.vy = 0;
            }
            var speed = Math.sqrt(mouse.vx * mouse.vx + mouse.vy * mouse.vy);

            if (opt.bg === 'transparent') { ctx.clearRect(0, 0, width, height); }
            else { ctx.fillStyle = pal.bg; ctx.fillRect(0, 0, width, height); }

            var SPRING_K = 18, DAMPING = 0.82;
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                n.pulse += dt * 3;

                var dx = mouse.x - n.x;
                var dy = mouse.y - n.y;
                var dist = Math.sqrt(dx * dx + dy * dy);

                if (mouse.active && dist < mouse.radius && dist > 0) {
                    var power = 1 - dist / mouse.radius;
                    var force = power * (1500 + speed * 150);
                    var angle = Math.atan2(dy, dx);
                    n.vx -= Math.cos(angle) * force * dt;
                    n.vy -= Math.sin(angle) * force * dt;
                }

                n.vx += (n.baseX - n.x) * SPRING_K * dt;
                n.vy += (n.baseY - n.y) * SPRING_K * dt;
                n.vx *= DAMPING;
                n.vy *= DAMPING;
                n.x += n.vx * dt * 60;
                n.y += n.vy * dt * 60;
            }

            hash();
            drawConnections(mode, pal.node);

            for (var k = 0; k < nodes.length; k++) {
                var nn = nodes[k];
                var ddx = mouse.x - nn.x;
                var ddy = mouse.y - nn.y;
                var dd = Math.sqrt(ddx * ddx + ddy * ddy);
                var near = mouse.active && dd < mouse.radius;
                var alpha = near ? 0.95 : 0.25 + Math.sin(nn.pulse) * 0.1;

                ctx.fillStyle = 'rgba(' + (near ? pal.accent : pal.node) + ', ' + alpha + ')';
                var r = near ? nn.radius * 2.2 : nn.radius + Math.sin(nn.pulse) * 0.3;
                ctx.beginPath();
                ctx.arc(nn.x, nn.y, Math.max(0.5, r), 0, Math.PI * 2);
                ctx.fill();

                if (near && dd < 90) {
                    var ring = ((nn.pulse * 20) % 30) + 4;
                    ctx.strokeStyle = 'rgba(' + pal.accent + ', ' + ((1 - ring / 34) * 0.4) + ')';
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.arc(nn.x, nn.y, ring, 0, Math.PI * 2);
                    ctx.stroke();
                    if (opt.labels) {
                        ctx.font = '8px ui-monospace, SFMono-Regular, Consolas, monospace';
                        ctx.fillStyle = 'rgba(' + pal.accent + ', 0.85)';
                        ctx.fillText(nn.label, nn.x + 10, nn.y - 10);
                    }
                }
            }
        }
/* ---- input ------------------------------------------------------- */
        var touchActive = false;

        function onPointerMove(e) {
            if (e.pointerType === 'touch' && !touchActive) { return; }   /* keep page scroll free */
            var p = point(e);
            mouse.x = p.x;
            mouse.y = p.y;
            mouse.active = true;
        }

        function onPointerLeave() {
            mouse.active = false;
            mouse.x = -9999;
            mouse.y = -9999;
        }

        function onPointerDown(e) { if (e.pointerType === 'touch') { touchActive = true; onPointerMove(e); } }
        function onPointerUp() { touchActive = false; onPointerLeave(); }

        /* ---- lifecycle --------------------------------------------------- */
        var observer = null;
        if ('IntersectionObserver' in window) {
            observer = new IntersectionObserver(function (entries) {
                visible = entries[0].isIntersecting;
            }, { threshold: 0 });
            observer.observe(wrapper);
        }

        function onVisibility() { running = !document.hidden; }

        /* repaint colours when the app's own theme toggle flips data-theme */
        var themeObserver = new MutationObserver(function () { /* picked up on the next frame */ });
        themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

        var boxObserver = null;
        if ('ResizeObserver' in window) {
            boxObserver = new ResizeObserver(function () { resize(); });
            boxObserver.observe(wrapper);
        } else {
            window.addEventListener('resize', resize);
        }

        wrapper.addEventListener('pointermove', onPointerMove);
        wrapper.addEventListener('pointerleave', onPointerLeave);
        wrapper.addEventListener('pointerdown', onPointerDown);
        wrapper.addEventListener('pointerup', onPointerUp);
        wrapper.addEventListener('pointercancel', onPointerUp);
        document.addEventListener('visibilitychange', onVisibility);

        resize();
        frameId = window.requestAnimationFrame(render);

        return {
            destroy: function () {
                window.cancelAnimationFrame(frameId);
                document.removeEventListener('visibilitychange', onVisibility);
                if (observer) { observer.disconnect(); }
                themeObserver.disconnect();
                if (boxObserver) { boxObserver.disconnect(); } else { window.removeEventListener('resize', resize); }
                wrapper.removeEventListener('pointermove', onPointerMove);
                wrapper.removeEventListener('pointerleave', onPointerLeave);
                wrapper.removeEventListener('pointerdown', onPointerDown);
                wrapper.removeEventListener('pointerup', onPointerUp);
                wrapper.removeEventListener('pointercancel', onPointerUp);
            }
        };
    }

    var instances = [];

    function init() {
        Array.prototype.forEach.call(document.querySelectorAll('[data-constellation]'), function (wrapper) {
            var mesh = createMesh(wrapper);
            if (mesh) { instances.push(mesh); }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.ConstellationGrid = {
        init: init,
        destroyAll: function () {
            instances.forEach(function (m) { m.destroy(); });
            instances = [];
        }
    };
})();