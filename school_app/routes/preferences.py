from __future__ import annotations

from copy import deepcopy

from flask import abort, flash, redirect, render_template, request, session, url_for

from ..database import get_db
from ..security import audit, current_session_endpoints
from ..student_dashboard import (
    DEFAULT_STUDENT_VIEW,
    load_student_view,
    normalise_student_view,
    save_student_view,
)
from ..user_preferences import (
    CARD_SIZES,
    COLOR_FIELDS,
    COLOR_PALETTES,
    COLOR_PALETTE_CHOICES,
    DASHBOARD_CARDS,
    FONT_FAMILIES,
    LINE_SPACINGS,
    MOTION_OPTIONS,
    PRESET_LABELS,
    STUDENT_DISPLAY_FIELDS,
    STUDENT_MOBILE_FIELDS,
    STUDENT_VIEW_CHOICES,
    TABLE_COLUMN_WIDTHS,
    TABLE_PAGE_SIZES,
    TABLE_PIN_LIMIT,
    TABLE_SORT_DIRECTIONS,
    TABLE_SORT_FIELDS,
    TEXT_SCALES,
    UI_DENSITIES,
    UI_PRESETS,
    VISUAL_STYLES,
    available_quick_actions,
    default_preferences,
    load_user_preferences,
    preferences_from_form,
    save_user_preferences,
)

_RESET_SECTIONS = {
    'student_card_fields': ('student_card_fields',),
    'student_table_fields': (
        'student_table_fields', 'student_table_order', 'student_table_pinned',
        'student_table_column_widths', 'student_table_sort',
        'student_table_sort_direction', 'student_table_page_size',
    ),
    'student_mobile_fields': ('student_mobile_fields',),
    'dashboard_cards': ('dashboard_cards',),
    'quick_actions': ('quick_actions',),
    'layout': ('ui_density', 'card_size', 'visual_style', 'font_family',
               'text_scale', 'line_spacing', 'motion'),
    'light_colors': ('colors',),
    'dark_colors': ('dark_colors',),
}


def _save_student_view(user_id, value) -> str:
    with get_db() as conn:
        chosen = save_student_view(conn, user_id, value)
        conn.commit()
    return chosen


def _finish_save(user_id, prefs, message: str, action: str, student_view=None):
    permitted_action_keys = {
        item['key'] for item in available_quick_actions(
            session.get('role'), current_session_endpoints(),
        )
    }
    prefs = dict(prefs)
    prefs['quick_actions'] = [
        key for key in prefs.get('quick_actions', ()) if key in permitted_action_keys
    ]
    save_user_preferences(user_id, prefs)
    if student_view is not None:
        _save_student_view(user_id, student_view)
    audit(user_id, action, 'app_settings', f'ui_preferences:{user_id}')
    flash(message, 'success')
    return redirect(url_for('ui_preferences'))


def ui_preferences():
    user_id = session.get('user_id')
    if request.method == 'POST':
        if request.form.get('reset_preferences') == '1':
            return _finish_save(
                user_id,
                default_preferences(),
                'همهٔ تنظیمات نمایش به حالت پیش‌فرض بازنشانی شد.',
                'reset_ui_preferences',
                DEFAULT_STUDENT_VIEW,
            )

        section = request.form.get('reset_section', '')
        if section:
            fields = _RESET_SECTIONS.get(section)
            if fields is None:
                abort(400, description='بخش تنظیمات برای بازنشانی معتبر نیست.')
            prefs = load_user_preferences(user_id)
            defaults = default_preferences()
            for key in fields:
                prefs[key] = deepcopy(defaults[key])
            view = DEFAULT_STUDENT_VIEW if section == 'layout' else None
            return _finish_save(
                user_id, prefs, 'تنظیمات همین بخش به پیش‌فرض بازگشت.',
                'reset_ui_preferences_section', view,
            )

        color_palette_key = request.form.get('apply_color_palette', '')
        if color_palette_key:
            palette = COLOR_PALETTES.get(color_palette_key)
            if palette is None:
                abort(400, description='پالت رنگی معتبر نیست.')
            prefs = load_user_preferences(user_id)
            prefs['color_palette'] = color_palette_key
            prefs['colors'] = deepcopy(palette['light'])
            prefs['dark_colors'] = deepcopy(palette['dark'])
            label = palette['label']
            return _finish_save(
                user_id, prefs, f'پالت «{label}» در همهٔ صفحه‌های سامانه اعمال شد.',
                'apply_color_palette',
            )

        preset_key = request.form.get('apply_preset', '')
        if preset_key:
            preset = UI_PRESETS.get(preset_key)
            if preset is None:
                abort(400, description='الگوی آماده معتبر نیست.')
            prefs = load_user_preferences(user_id)
            view = preset['student_view']
            for key, value in preset.items():
                if key != 'student_view':
                    prefs[key] = deepcopy(value)
            label = dict(PRESET_LABELS)[preset_key]
            return _finish_save(
                user_id, prefs,
                f'الگوی «{label}» اعمال شد؛ رنگ‌های شخصی شما حفظ شدند.',
                'apply_ui_preferences_preset', view,
            )

        prefs = preferences_from_form(request.form)
        view = normalise_student_view(request.form.get('student_view'))
        return _finish_save(
            user_id, prefs, 'تنظیمات رابط کاربری برای حساب شما ذخیره شد.',
            'update_ui_preferences', view,
        )

    with get_db() as conn:
        student_view = load_student_view(conn, user_id)
    preferences = load_user_preferences(user_id)
    labels = dict(STUDENT_DISPLAY_FIELDS)
    table_order_fields = [
        (key, labels[key]) for key in preferences['student_table_order'] if key in labels
    ]
    return render_template(
        'user_preferences.html',
        preference_fields=STUDENT_DISPLAY_FIELDS,
        table_order_fields=table_order_fields,
        table_column_widths=TABLE_COLUMN_WIDTHS,
        table_pin_limit=TABLE_PIN_LIMIT,
        table_sort_fields=TABLE_SORT_FIELDS,
        table_sort_directions=TABLE_SORT_DIRECTIONS,
        table_page_sizes=TABLE_PAGE_SIZES,
        mobile_fields=STUDENT_MOBILE_FIELDS,
        dashboard_cards=DASHBOARD_CARDS,
        color_fields=COLOR_FIELDS,
        color_palettes=COLOR_PALETTES,
        color_palette_choices=COLOR_PALETTE_CHOICES,
        ui_densities=UI_DENSITIES,
        card_sizes=CARD_SIZES,
        visual_styles=VISUAL_STYLES,
        font_families=FONT_FAMILIES,
        text_scales=TEXT_SCALES,
        line_spacings=LINE_SPACINGS,
        motion_options=MOTION_OPTIONS,
        student_view_choices=STUDENT_VIEW_CHOICES,
        student_view=student_view,
        preset_labels=PRESET_LABELS,
    )


def register(app):
    app.add_url_rule(
        '/my-settings',
        endpoint='ui_preferences',
        view_func=ui_preferences,
        methods=['GET', 'POST'],
    )
