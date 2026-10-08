(() => {
  'use strict';
  const panel = document.querySelector('[data-student-print-controls]');
  if (!panel) return;
  let layout = JSON.parse(panel.querySelector('[data-print-config]').textContent);
  const orientation = panel.querySelector('[data-print-orientation]');
  const font = panel.querySelector('[data-print-font]');
  const status = panel.querySelector('[data-print-status]');
  const preview = document.body.classList.contains('student-print-page');
  let saving = false;
  function syncControls() {
    orientation.value = layout.orientation;
    font.value = layout.font_size;
    panel.querySelectorAll('[data-print-section]').forEach(input => {
      input.checked = layout.sections[input.dataset.printSection] !== false;
    });
    panel.querySelectorAll('[data-print-empty-option]').forEach(input => {
      input.checked = Boolean(layout[input.dataset.printEmptyOption]);
    });
  }
  syncControls();
  const style = document.createElement('style');
  document.head.append(style);
  function apply() {
    if (!font.checkValidity() || !font.value) return false;
    layout.orientation = orientation.value;
    layout.font_size = Number(font.value);
    panel.querySelectorAll('[data-print-section]').forEach(input => {
      layout.sections[input.dataset.printSection] = input.checked;
    });
    layout.sections.identity = true;
    panel.querySelectorAll('[data-print-empty-option]').forEach(input => {
      layout[input.dataset.printEmptyOption] = input.checked;
    });
    if (preview) {
      const m = layout.margin;
      style.textContent = `@page{size:A4 ${layout.orientation};margin:${m.top}mm ${m.right}mm ${m.bottom}mm ${m.left}mm}`;
      document.body.style.setProperty('--record-font', `${layout.font_size}pt`);
      document.body.style.setProperty('--paper-width', `${(layout.orientation === 'portrait' ? 210 : 297) - m.left - m.right}mm`);
      document.querySelectorAll('[data-print-section-key]').forEach(section => {
        section.hidden = layout.sections[section.dataset.printSectionKey] === false
          || (layout.hide_empty_sections && section.dataset.printEmpty === 'true');
      });
      document.querySelectorAll('.profile-detail[data-print-empty]').forEach(field => {
        field.hidden = layout.hide_empty_fields && field.dataset.printEmpty === 'true';
      });
    }
    return true;
  }
  panel.addEventListener('input', () => {
    if (saving) return;
    if (apply()) status.textContent = preview
      ? 'تغییرات در پیش‌نمایش اعمال شد؛ برای دفعات بعد ذخیره کنید.'
      : 'تغییرات هنوز ذخیره نشده‌اند؛ برای اعمال در چاپ، ابتدا ذخیره کنید.';
  });
  panel.querySelector('[data-print-save]').addEventListener('click', async () => {
    if (saving) return;
    if (!apply()) { font.reportValidity(); return; }
    saving = true;
    const controls = [...panel.querySelectorAll('input, select, button')]
      .map(control => ({control, disabled: control.disabled}));
    controls.forEach(({control}) => { control.disabled = true; });
    panel.setAttribute('aria-busy', 'true');
    status.textContent = 'در حال ذخیره…';
    try {
      const response = await fetch(panel.dataset.url, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': panel.dataset.token},
        body: JSON.stringify({orientation: layout.orientation, font_size: layout.font_size, sections: layout.sections,
          hide_empty_fields: layout.hide_empty_fields, hide_empty_sections: layout.hide_empty_sections})
      });
      if (!response.ok) throw new Error('save failed');
      layout = (await response.json()).layout;
      syncControls();
      apply();
      status.textContent = 'برای حساب شما ذخیره شد.';
    } catch (_) {
      status.textContent = 'ذخیره انجام نشد؛ اتصال یا اعتبار ورود را بررسی و دوباره تلاش کنید.';
    } finally {
      controls.forEach(({control, disabled}) => { control.disabled = disabled; });
      panel.removeAttribute('aria-busy');
      saving = false;
    }
  });
  panel.querySelector('[data-print-now]')?.addEventListener('click', async () => {
    if (saving) return;
    if (!apply()) { font.reportValidity(); return; }
    await document.fonts.ready;
    window.print();
  });
  apply();
})();
