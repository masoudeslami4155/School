/* =========================================================================
   calendar.js — منطق صفحهٔ «تقویم مدرسه · کارها و آلارم»
   -------------------------------------------------------------------------
   ساختار فایل:
     0) ابزارهای کمکی
     1) پنجرهٔ ثبت سریع روی روز
     2) تقویم ماهانه (شبکهٔ ۷ ستونه) + فهرست مناسبت‌های ماه
     3) تنظیمات یادآور گزارش پایان روز (localStorage)
     4) آلارم کارها (Notification)
   داده‌ها از طریق جزیره‌های JSON داخل قالب تزریق می‌شوند:
     #gcalOccasions, #gcalEvents, #gcalTasks, #taskAlarmData
   وابستگی‌ها: window.__JW و window.JDatePickers (partials/jalali_widgets.html)
   ========================================================================= */
(function () {
  'use strict';

  /* ---- 0) ابزارهای کمکی ---------------------------------------------- */
  function readJson(id, fallback) {
    var el = document.getElementById(id);
    if (!el) return fallback;
    try { return JSON.parse(el.textContent); } catch (e) { return fallback; }
  }
  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  /* ---- 1) پنجرهٔ ثبت سریع --------------------------------------------- */
  var addBox = document.getElementById('gcalAdd');
  var addDate = '';

  function openAdd(e, date) {
    if (!addBox) return;
    e.stopPropagation();
    addDate = date;
    document.getElementById('gcalAddTitle').textContent = 'روز ' + window.__JW.fa(date);
    var r = e.currentTarget.getBoundingClientRect();
    addBox.classList.add('is-open');
    var x = Math.max(8, Math.min(r.left, window.innerWidth - 220));
    addBox.style.left = x + 'px';
    addBox.style.top = (r.bottom + window.scrollY + 4) + 'px';
    document.querySelectorAll('.jw-popup.is-open').forEach(function (p) {
      p.classList.remove('is-open');
    });
  }
  function closeAdd() {
    if (addBox) addBox.classList.remove('is-open');
  }

  function initQuickAdd() {
    if (!addBox) return;
    document.getElementById('gcalAddClose').addEventListener('click', closeAdd);
    document.addEventListener('click', function (e) {
      if (!e.target.closest('.gcal-add') && !e.target.closest('.gcal-cell')) closeAdd();
    });
    document.getElementById('gcalAddEvent').addEventListener('click', function () {
      if (window.JDatePickers && window.JDatePickers.date) window.JDatePickers.date.set(addDate);
      closeAdd();
      var f = document.querySelector('.calendar-form');
      if (f) f.scrollIntoView({ behavior: 'smooth' });
    });
    document.getElementById('gcalAddTask').addEventListener('click', function () {
      if (window.JDatePickers && window.JDatePickers.due_date) window.JDatePickers.due_date.set(addDate);
      closeAdd();
      var f = document.querySelector('.task-form');
      if (f) f.scrollIntoView({ behavior: 'smooth' });
    });
  }

  /* ---- 2) تقویم ماهانه -------------------------------------------------- */
  function initMonthGrid() {
    var JW = window.__JW;
    if (!JW) return false;

    var fa = JW.fa, pad = JW.pad;
    var EV = readJson('gcalEvents', []);
    var TK = readJson('gcalTasks', []);
    var OC = readJson('gcalOccasions', {});
    var grid = document.getElementById('gcalGrid');
    var occList = document.getElementById('gcalOccList');
    var occCount = document.getElementById('gcalOccCount');
    if (!grid) return true;

    var today = JW.todayJ();
    var cur = [today[0], today[1]];

    function group(list) {
      var o = {};
      list.forEach(function (x) { (o[x.date] = o[x.date] || []).push(x); });
      return o;
    }
    var evMap = group(EV), tkMap = group(TK);

    /* جمعه در تقویم ایران تعطیل هفتگی است؛ جدا از تعطیلات رسمی منبع. */
    function isFriday(y, mo, d) {
      var g = JW.j2g(y, mo, d);
      /* UTC avoids timezone shifts; JavaScript Friday = 5. */
      return new Date(Date.UTC(g[0], g[1] - 1, g[2])).getUTCDay() === 5;
    }
    function weeklyHolidayLabel() { return 'تعطیل هفتگی جمعه'; }

    /* تاریخ هر خانهٔ شبکه با پوشش روزهای ماه قبل/بعد */
    function cellDate(y, mo, i, lead, days) {
      if (i < lead) {
        var pm = mo === 1 ? 12 : mo - 1, py = mo === 1 ? y - 1 : y;
        return [py, pm, JW.monthDays(py, pm) - lead + i + 1];
      }
      if (i >= lead + days) {
        var nm = mo === 12 ? 1 : mo + 1, ny = mo === 12 ? y + 1 : y;
        return [ny, nm, i - lead - days + 1];
      }
      return [y, mo, i - lead + 1];
    }

    /* چیپ‌های هر روز: مناسبت، رویداد، کار */
    function chipsFor(key) {
      var out = [];
      var parts = key.split('/').map(Number);
      var weekly = isFriday(parts[0], parts[1], parts[2]);
      var occ = OC[key.slice(5)];
      if (weekly) {
        out.push('<div class="gcal-chip gcal-chip--weekly" data-kind="weekly-holiday" title="' + weeklyHolidayLabel() + '">تعطیل هفتگی</div>');
      }
      if (occ) {
        (occ.t || []).forEach(function (title) {
          out.push('<div class="gcal-chip" data-kind="occasion" data-holiday="' + occ.h + '" title="' + esc(title) + '">🎉 ' + esc(title) + '</div>');
        });
      }
      (evMap[key] || []).forEach(function (e) {
        out.push('<div class="gcal-chip" data-kind="event" data-urgent="' + (e.priority === 'فوری' ? 1 : 0) + '" title="' + esc(e.title) + '">' + (e.time ? e.time + ' · ' : '') + esc(e.title) + '</div>');
      });
      (tkMap[key] || []).forEach(function (x) {
        var tm = (x.time && x.time !== 'بدون ساعت') ? x.time + ' · ' : '';
        out.push('<div class="gcal-chip" data-kind="task" data-done="' + (x.open ? 0 : 1) + '" title="' + esc(x.title) + '">' + tm + esc(x.title) + '</div>');
      });
      return out;
    }

    function renderGrid() {
      var y = cur[0], mo = cur[1];
      document.getElementById('gcalTitle').innerHTML =
        fa(y) + ' ' + JW.MONTHS[mo - 1] +
        ' <small>رویداد (آبی) · کار (سبز) · مناسبت (نارنجی)</small>';
      var first = JW.j2g(y, mo, 1);
      var lead = JW.satIdx(first[0], first[1], first[2]);
      var days = JW.monthDays(y, mo), html = '';
      for (var i = 0; i < 42; i++) {
        var cj = cellDate(y, mo, i, lead, days);
        var key = pad(cj[0]) + '/' + pad(cj[1]) + '/' + pad(cj[2]);
        var other = cj[1] !== mo;
        var isToday = (cj[0] === today[0] && cj[1] === today[1] && cj[2] === today[2]);
        var chips = chipsFor(key), show = chips.slice(0, 3), extra = chips.length - show.length;
        var occ = OC[key.slice(5)];
        var friday = isFriday(cj[0], cj[1], cj[2]);
        var cls = 'gcal-cell' + (other ? ' is-other' : '') + (isToday ? ' is-today' : '') +
          (friday ? ' is-weekly-holiday' : '') + (occ ? ' has-occasion' : '') +
          (occ && occ.h ? ' is-holiday' : '');
        var holidayText = friday && occ && occ.h ? 'تعطیل هفتگی جمعه و تعطیل رسمی' :
          (friday ? 'تعطیل هفتگی جمعه' : (occ && occ.h ? 'تعطیل رسمی' : ''));
        html += '<div class="' + cls + '" data-date="' + key + '" aria-label="' + fa(cj[2]) + (holidayText ? '، ' + holidayText : '') + '">';
        html += '<div class="gcal-num">' + fa(cj[2]) + '</div>';
        show.forEach(function (c) { html += c; });
        if (extra > 0) html += '<div class="gcal-more">+' + fa(extra) + ' مورد</div>';
        html += '</div>';
      }
      grid.innerHTML = html;
      grid.querySelectorAll('.gcal-cell').forEach(function (c) {
        c.addEventListener('click', function (e) { openAdd(e, c.dataset.date); });
      });
    }

    function renderOccasions() {
      var y = cur[0], mo = cur[1], rows = [], count = 0;
      var days = JW.monthDays(y, mo);
      for (var d = 1; d <= days; d++) {
        var dayOcc = OC[pad(mo) + '/' + pad(d)];
        var friday = isFriday(y, mo, d);
        if (!dayOcc && !friday) continue;
        if (dayOcc) {
          count += (dayOcc.t || []).length;
          (dayOcc.t || []).forEach(function (title) {
            var tag = dayOcc.h && friday ? 'تعطیل رسمی · تعطیل هفتگی' : (dayOcc.h ? 'تعطیل رسمی' : (friday ? 'تعطیل هفتگی' : 'مناسبت'));
            rows.push(
              '<div class="gcal-occ-row' + ((dayOcc.h || friday) ? ' is-holiday' : '') + '">' +
              '<span class="occ-day">' + fa(d) + '</span>' +
              '<span class="occ-title">' + esc(title) + '</span>' +
              '<span class="occ-tag">' + tag + '</span></div>'
            );
          });
        }
        if (friday) {
          count++;
          rows.push(
            '<div class="gcal-occ-row is-weekly-holiday is-holiday">' +
            '<span class="occ-day">' + fa(d) + '</span>' +
            '<span class="occ-title">' + weeklyHolidayLabel() + '</span>' +
            '<span class="occ-tag">' + (dayOcc && dayOcc.h ? 'همراه با تعطیل رسمی' : 'تعطیل هفتگی') + '</span></div>'
          );
        }
      }
      if (occList) {
        occList.innerHTML = rows.length ? rows.join('') : '<div class="empty-state">مناسبت یا تعطیلی برای این ماه ثبت نشده است.</div>';
      }
      if (occCount) occCount.textContent = count.toLocaleString('fa-IR') + ' مناسبت / تعطیلی';
    }

    function renderList() {
      var list = document.getElementById('gcalList');
      if (!list) return;
      var y = cur[0], mo = cur[1], days = JW.monthDays(y, mo), rows = [];
      for (var d = 1; d <= days; d++) {
        var key = pad(y) + '/' + pad(mo) + '/' + pad(d), items = [];
        var friday = isFriday(y, mo, d);
        var occ = OC[key.slice(5)];
        if (friday) items.push('<div class="gcal-list-item gcal-list-item--weekly-holiday">🔴 ' + weeklyHolidayLabel() + '</div>');
        if (occ) (occ.t || []).forEach(function (title) {
          items.push('<div class="gcal-list-item gcal-list-item--occasion' + (occ.h ? ' gcal-list-item--holiday' : '') + '">🎉 ' + esc(title) + (occ.h ? ' · تعطیل رسمی' : '') + '</div>');
        });
        (evMap[key] || []).forEach(function (e) {
          items.push('<div class="gcal-list-item">📘 ' + (e.time ? '<b>' + esc(e.time) + '</b> · ' : '') + esc(e.title) + '</div>');
        });
        (tkMap[key] || []).forEach(function (x) {
          items.push('<div class="gcal-list-item gcal-list-item--task">✅ ' + (x.time && x.time !== 'بدون ساعت' ? '<b>' + esc(x.time) + '</b> · ' : '') + esc(x.title) + (x.open ? '' : ' · انجام‌شده') + '</div>');
        });
        if (items.length) rows.push('<article class="gcal-list-day"><div class="gcal-list-day__head"><span>' + fa(d) + ' ' + JW.MONTHS[mo - 1] + '</span><span>' + fa(items.length) + ' مورد</span></div><div class="gcal-list-day__items">' + items.join('') + '</div></article>');
      }
      list.innerHTML = rows.length ? rows.join('') : '<div class="gcal-list-empty">برای این ماه رویداد، کار یا مناسبتی ثبت نشده است.</div>';
    }

    function setView(mode) {
      var section = document.querySelector('.gcal');
      var gridBtn = document.getElementById('gcalGridView'), listBtn = document.getElementById('gcalListView');
      if (!section) return;
      section.classList.toggle('gcal--list-mode', mode === 'list');
      if (gridBtn) gridBtn.classList.toggle('is-active', mode !== 'list');
      if (listBtn) listBtn.classList.toggle('is-active', mode === 'list');
      try { localStorage.setItem('calendar-view', mode); } catch (e) {}
    }

    function render() { renderGrid(); renderOccasions(); renderList(); }

    document.getElementById('gcalPrev').addEventListener('click', function () {
      cur[1]--; if (cur[1] < 1) { cur[1] = 12; cur[0]--; } render();
    });
    document.getElementById('gcalNext').addEventListener('click', function () {
      cur[1]++; if (cur[1] > 12) { cur[1] = 1; cur[0]++; } render();
    });
    document.getElementById('gcalTodayBtn').addEventListener('click', function () {
      cur = [today[0], today[1]]; render();
    });

    var gridView = document.getElementById('gcalGridView'), listView = document.getElementById('gcalListView');
    if (gridView) gridView.addEventListener('click', function () { setView('grid'); });
    if (listView) listView.addEventListener('click', function () { setView('list'); });
    var initialView = 'grid';
    try { initialView = localStorage.getItem('calendar-view') || (window.innerWidth <= 768 ? 'list' : 'grid'); } catch (e) { initialView = window.innerWidth <= 768 ? 'list' : 'grid'; }
    render();
    setView(initialView);
    return true;
  }

  /* ---- 3) تنظیمات گزارش پایان روز --------------------------------------- */
  function initDigestSettings() {
    var cb = document.getElementById('digestEnabled');
    var ts = document.getElementById('digestTime');
    var st = document.getElementById('digestSaveState');
    var test = document.getElementById('digestTestBtn');
    if (!cb) return;
    function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
    function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
    function fa(n) { return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[+d]; }); }
    function state() { st.textContent = cb.checked ? ('فعال · ساعت ' + fa(ts.value)) : 'غیرفعال'; }
    cb.checked = get('digest-enabled') === '1';
    ts.value = get('digest-time') || '17:30';
    cb.addEventListener('change', function () { set('digest-enabled', cb.checked ? '1' : '0'); state(); });
    ts.addEventListener('change', function () { set('digest-time', ts.value); state(); });
    if (test) test.addEventListener('click', function () { window.open('/daily_digest', '_blank'); });
    state();
  }

  /* ---- 4) آلارم کارها ---------------------------------------------------- */
  function initTaskAlarms() {
    var box = document.getElementById('taskAlarmData');
    if (!box) return;
    var tasks = [];
    try { tasks = JSON.parse(box.getAttribute('data-tasks') || '[]'); } catch (e) { return; }
    function key(id) { return 'task-alarm-fired-' + id; }
    function notify(t) {
      try {
        if (sessionStorage.getItem(key(t.id))) return;
        sessionStorage.setItem(key(t.id), '1');
      } catch (e) {}
      var body = (t.priority || '') + ' · موعد: ' + (t.due_at || '');
      if (window.Notification && Notification.permission === 'granted') {
        try { new Notification('یادآور کار: ' + t.title, { body: body, tag: 'task-' + t.id }); } catch (e) {}
      }
      try { alert('🔔 یادآور کار\n' + t.title + '\n' + body); } catch (e) {}
    }
    function tick() {
      var now = Date.now();
      tasks.forEach(function (t) {
        if (!t.alarm_at) return;
        var at = new Date(t.alarm_at).getTime();
        if (isNaN(at)) return;
        if (at <= now && at > now - 120000) notify(t);
      });
    }
    if (window.Notification && Notification.permission === 'default') {
      try { Notification.requestPermission(); } catch (e) {}
    }
    tick();
    setInterval(tick, 15000);
  }

  /* ---- راه‌اندازی --------------------------------------------------------- */
  function boot() {
    if (!initMonthGrid()) { setTimeout(boot, 120); return; }
    initQuickAdd();
    initDigestSettings();
    initTaskAlarms();
  }
  boot();
})();
