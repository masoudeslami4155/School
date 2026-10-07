"""Per-user print layouts for reports and student-facing print sheets."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


REPORT_DOCUMENTS = {
    'attendance_students': {
        'label': 'گزارش حضور و غیاب دانش‌آموزان',
        'short_label': 'حضور دانش‌آموزان',
        'kind': 'table',
        'preview_endpoint': 'attendance_report',
        'preview_query': {'autoprint': '1', 'print_all': '1'},
    },
    'attendance_teachers': {
        'label': 'گزارش حضور و غیاب معلمان',
        'short_label': 'حضور معلمان',
        'kind': 'table',
        'preview_endpoint': 'teacher_attendance_report',
        'preview_query': {'autoprint': '1'},
    },
    'folder_labels': {
        'label': 'لیست چسباننده به پشت پرونده',
        'short_label': 'پشت پرونده',
        'kind': 'cards',
        'preview_endpoint': 'list_for_folders_print',
        'preview_query': {'use_layout': '1'},
    },
    'student_info': {
        'label': 'اطلاعات کامل دانش‌آموز',
        'short_label': 'اطلاعات دانش‌آموز',
        'kind': 'profile',
        'preview_endpoint': 'print_filtered_students',
        'preview_query': {},
    },
    'wall_cards': {
        'label': 'کارت‌های دیواری دانش‌آموزان',
        'short_label': 'کارت دیواری',
        'kind': 'wall_cards',
        'preview_endpoint': 'print_wall_cards',
        'preview_query': {'autoprint': '1'},
    },
    'student_filters': {
        'label': 'راهنمای فشردهٔ فیلترهای دانش‌آموزان',
        'short_label': 'راهنمای فیلترها',
        'kind': 'filter_reference',
        'preview_endpoint': 'student_filters_print',
        'preview_query': {'autoprint': '1'},
    },
    'school_statistics': {
        'label': 'آمار مدرسه',
        'short_label': 'آمار مدرسه',
        'kind': 'dashboard',
        'preview_endpoint': 'statistics',
        'preview_query': {},
    },
}

REPORT_COLUMNS = {
    'attendance_students': [
        ('index', 'ردیف'), ('name', 'نام و نام خانوادگی'), ('code', 'کد'),
        ('grade', 'پایه'), ('class_name', 'کلاس'), ('sida_class', 'سیدا'),
        ('teacher', 'معلم'), ('date', 'تاریخ'), ('status', 'وضعیت'),
    ],
    'attendance_teachers_summary': [
        ('index', 'ردیف'), ('first_name', 'نام'), ('last_name', 'نام خانوادگی'),
        ('absent', 'تعداد غیبت'), ('late', 'تعداد تأخیر'), ('late_minutes', 'دقایق تأخیر'),
    ],
    'attendance_teachers_detail': [
        ('index', 'ردیف'), ('first_name', 'نام'), ('last_name', 'نام خانوادگی'),
        ('code', 'کد'), ('subject', 'درس'), ('class_name', 'کلاس'), ('date', 'تاریخ'),
        ('status', 'وضعیت'), ('late_duration', 'میزان تأخیر'),
    ],
    'folder_labels': [
        ('teacher', 'نام معلم'), ('teacher_meta', 'درس و کلاس'), ('count', 'تعداد دانش‌آموز'),
        ('student_number', 'شماره ردیف'), ('student_name', 'نام دانش‌آموز'),
        ('student_grade', 'پایه'), ('student_photo', 'عکس'),
    ],
}

REPORT_SECTIONS = {
    'attendance_students': [
        ('summary', 'خلاصه آمار'), ('detail', 'جدول حضور و غیاب'),
    ],
    'attendance_teachers': [
        ('summary', 'خلاصه عملکرد'), ('detail', 'جزئیات روزانه'),
    ],
    'folder_labels': [('cards', 'کارت‌های پشت پرونده')],
    'student_info': [
        ('identity', 'اطلاعات هویتی و پرونده'),
        ('identity_card', 'اطلاعات شناسنامه‌ای'),
        ('education', 'اطلاعات آموزشی و انتساب'),
        ('family', 'خانواده و راه‌های تماس'),
        ('health', 'سلامت و ویژگی‌های فردی'),
        ('finance', 'وضعیت مالی و حمایتی'),
        ('bank', 'اطلاعات حساب بانکی'),
        ('grade_repeats', 'سوابق توقف و سال ورود'),
        ('siblings', 'خواهر و برادر'),
    ],
    'school_statistics': [
        ('hero', 'عنوان و دامنه گزارش'), ('quality', 'کیفیت داده‌ها'), ('kpi', 'کارت‌های شاخص'),
        ('status', 'وضعیت پرونده‌ها'), ('attendance', 'کیفیت حضور'), ('trend', 'روند غیبت و تأخیر'),
        ('teachers', 'وضعیت معلمان'), ('breakdowns', 'جدول‌های آماری'),
        ('risk', 'دانش‌آموزان نیازمند پیگیری'), ('finance', 'خلاصه خدمات و پرداخت‌ها'),
    ],
}

REPORT_ELEMENTS = {
    'attendance_students': ('hero', 'summary', 'detail', 'footer'),
    'attendance_teachers': ('hero', 'summary', 'detail', 'footer'),
    'folder_labels': ('hero', 'cards', 'footer'),
    'student_info': ('hero', 'identity', 'identity_card', 'education', 'family', 'health',
                     'finance', 'bank', 'grade_repeats', 'siblings', 'footer'),
    'wall_cards': ('hero', 'cards', 'footer'),
    'student_filters': ('hero', 'table', 'notes', 'footer'),
    'school_statistics': ('hero', 'quality', 'kpi', 'status', 'attendance', 'trend',
                          'teachers', 'breakdowns', 'risk', 'finance', 'footer'),
}

_SETTING_PREFIX = 'report_print_layout:'
_SIDES = ('top', 'right', 'bottom', 'left')
_PAGE_SIZES = {'portrait': (210, 297), 'landscape': (297, 210)}


def _default_columns(document: str) -> dict[str, bool]:
    if document == 'attendance_teachers':
        keys = [key for key, _ in REPORT_COLUMNS['attendance_teachers_summary']]
        keys += [key for key, _ in REPORT_COLUMNS['attendance_teachers_detail']]
    else:
        keys = [key for key, _ in REPORT_COLUMNS.get(document, [])]
    return {key: True for key in dict.fromkeys(keys)}


def default_layout(document: str) -> dict[str, Any]:
    if document not in REPORT_DOCUMENTS:
        document = 'attendance_students'
    layout: dict[str, Any] = {
        'version': 1,
        'orientation': 'portrait' if document in {'student_info', 'wall_cards'} else 'landscape',
        'margin': {'top': 8, 'right': 8, 'bottom': 8, 'left': 8},
        'font_size': 8,
        'header_font_size': 10,
        'row_height': 7,
        'header_height': 9,
        'line_height': 1.35,
        'show_header': True,
        'show_footer': True,
        'repeat_header': True,
        'columns': _default_columns(document),
        'sections': {key: True for key, _ in REPORT_SECTIONS.get(document, [])},
        'elements': {
            key: {'x': 0, 'y': 0, 'sx': 1, 'sy': 1}
            for key in REPORT_ELEMENTS.get(document, ())
        },
        'grid': {'columns': 3, 'rows': 2},
    }
    if document == 'wall_cards':
        layout['margin'] = {'top': 4, 'right': 4, 'bottom': 4, 'left': 4}
        layout['grid'] = {'columns': 4, 'rows': 6, 'gap_x': 2, 'gap_y': 1.5}
        layout['card'] = {
            'height': 43,
            'photo_size': 15,
            'font_size': 5.5,
            'name_font_size': 7,
            'show_photo': True,
            'show_school': True,
            'show_year': True,
            'show_driver': True,
            'show_grade': True,
            'show_class_name': True,
            'show_sida_class': True,
            'show_gender': True,
            'show_teacher': True,
        }
    if document == 'folder_labels':
        layout['grid'] = {'columns': 3, 'rows': 2}
    if document == 'school_statistics':
        layout['font_size'] = 7
    return layout


def _number(value: Any, fallback: float, minimum: float, maximum: float, *, integer: bool = False):
    try:
        number = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        number = fallback
    number = max(minimum, min(maximum, number))
    return int(round(number)) if integer else round(number, 2)


def _boolean(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.strip().lower() in {'1', 'true', 'yes', 'on', 'بله'}:
            return True
        if value.strip().lower() in {'0', 'false', 'no', 'off', 'خیر'}:
            return False
    return fallback


def sanitize_layout(document: str, raw: Any) -> dict[str, Any]:
    """Keep only supported fields and bound all user-controlled numbers."""
    if document not in REPORT_DOCUMENTS:
        document = 'attendance_students'
    base = default_layout(document)
    source = raw if isinstance(raw, dict) else {}
    result = deepcopy(base)
    result['orientation'] = source.get('orientation') if source.get('orientation') in _PAGE_SIZES else base['orientation']
    margin = source.get('margin') if isinstance(source.get('margin'), dict) else {}
    result['margin'] = {side: _number(margin.get(side), base['margin'][side], 0, 30) for side in _SIDES}
    for key, minimum, maximum in (
        ('font_size', 5, 18), ('header_font_size', 6, 24), ('row_height', 3, 25), ('header_height', 4, 30),
    ):
        result[key] = _number(source.get(key), base[key], minimum, maximum)
    result['line_height'] = _number(source.get('line_height'), base['line_height'], 1, 2.5)
    for key in ('show_header', 'show_footer', 'repeat_header'):
        result[key] = _boolean(source.get(key), base[key])

    allowed_columns = result['columns']
    raw_columns = source.get('columns') if isinstance(source.get('columns'), dict) else {}
    result['columns'] = {key: _boolean(raw_columns.get(key), value) for key, value in allowed_columns.items()}
    if result['columns'] and not any(result['columns'].values()):
        first = next(iter(result['columns']))
        result['columns'][first] = True

    allowed_sections = result['sections']
    raw_sections = source.get('sections') if isinstance(source.get('sections'), dict) else {}
    result['sections'] = {key: _boolean(raw_sections.get(key), value) for key, value in allowed_sections.items()}
    if result['sections'] and not any(result['sections'].values()):
        first = next(iter(result['sections']))
        result['sections'][first] = True

    raw_elements = source.get('elements') if isinstance(source.get('elements'), dict) else {}
    result['elements'] = {}
    for key, defaults in base['elements'].items():
        item = raw_elements.get(key) if isinstance(raw_elements.get(key), dict) else {}
        result['elements'][key] = {
            'x': _number(item.get('x'), defaults['x'], -60, 60),
            'y': _number(item.get('y'), defaults['y'], -60, 60),
            'sx': _number(item.get('sx'), defaults['sx'], 0.5, 2.5),
            'sy': _number(item.get('sy'), defaults['sy'], 0.5, 2.5),
        }

    grid = source.get('grid') if isinstance(source.get('grid'), dict) else {}
    if document == 'wall_cards':
        width_mm, height_mm = _PAGE_SIZES[result['orientation']]
        gap_x = _number(grid.get('gap_x'), base['grid']['gap_x'], 0, 10)
        gap_y = _number(grid.get('gap_y'), base['grid']['gap_y'], 0, 10)
        usable_width = width_mm - result['margin']['right'] - result['margin']['left']
        usable_height = height_mm - result['margin']['top'] - result['margin']['bottom'] - 12
        max_columns = max(1, min(6, int((usable_width + gap_x) // (30 + gap_x))))
        max_rows = max(1, min(6 if result['orientation'] == 'portrait' else 4,
                              int((usable_height + gap_y) // (30 + gap_y))))
        result['grid'] = {
            'columns': _number(grid.get('columns'), base['grid']['columns'], 1, max_columns, integer=True),
            'rows': _number(grid.get('rows'), base['grid']['rows'], 1, max_rows, integer=True),
            'gap_x': gap_x,
            'gap_y': gap_y,
        }
        raw_card = source.get('card') if isinstance(source.get('card'), dict) else {}
        defaults = base['card']
        available_card_height = (
            usable_height - gap_y * (result['grid']['rows'] - 1)
        ) / result['grid']['rows']
        max_height = min(40 if result['orientation'] == 'landscape' else 48, available_card_height)
        result['card'] = {
            'height': _number(raw_card.get('height'), defaults['height'], 30, max(30, max_height)),
            'photo_size': _number(raw_card.get('photo_size'), defaults['photo_size'], 0, 30),
            'font_size': _number(raw_card.get('font_size'), defaults['font_size'], 4, 12),
            'name_font_size': _number(raw_card.get('name_font_size'), defaults['name_font_size'], 5, 18),
            **{
                key: _boolean(raw_card.get(key), value)
                for key, value in defaults.items()
                if key.startswith('show_')
            },
        }
    else:
        result['grid'] = {
            'columns': _number(grid.get('columns'), base['grid']['columns'], 1, 6, integer=True),
            'rows': _number(grid.get('rows'), base['grid']['rows'], 1, 6, integer=True),
        }
    return result


def settings_key(document: str, user_id: Any) -> str:
    return f'{_SETTING_PREFIX}{document}:{user_id}'


def load_layout(conn, document: str, user_id: Any) -> dict[str, Any]:
    fallback = default_layout(document)
    if not user_id or document not in REPORT_DOCUMENTS:
        return fallback
    row = conn.execute('SELECT value FROM app_settings WHERE key=?', (settings_key(document, user_id),)).fetchone()
    if not row:
        return fallback
    try:
        stored = json.loads(row['value'] or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = {}
    return sanitize_layout(document, stored)


def save_layout(conn, document: str, user_id: Any, layout: Any) -> dict[str, Any]:
    cleaned = sanitize_layout(document, layout)
    conn.execute(
        'INSERT INTO app_settings(key,value) VALUES(?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (settings_key(document, user_id), json.dumps(cleaned, ensure_ascii=False)),
    )
    return cleaned


def reset_layout(conn, document: str, user_id: Any) -> None:
    conn.execute('DELETE FROM app_settings WHERE key=?', (settings_key(document, user_id),))


def page_css(layout: dict[str, Any]) -> str:
    width, height = _PAGE_SIZES[layout['orientation']]
    margin = layout['margin']
    return (
        f'@page{{size:A4 {layout["orientation"]};margin:{margin["top"]}mm '
        f'{margin["right"]}mm {margin["bottom"]}mm {margin["left"]}mm}} '
        f'--report-font-size:{layout["font_size"]}pt;'
    )


def element_css(layout: dict[str, Any]) -> str:
    """Build print-safe transforms for the editor's movable report boxes."""
    rules = []
    for key, item in layout.get('elements', {}).items():
        if item['x'] == 0 and item['y'] == 0 and item['sx'] == 1 and item['sy'] == 1:
            continue
        rules.append(
            f'[data-report-element="{key}"]{{'
            f'transform:translate({item["x"]}mm,{item["y"]}mm) scale({item["sx"]},{item["sy"]});'
            'transform-origin:top left}'
        )
    return ''.join(rules)
