"""Per-user orientation and element positions for enrollment certificates."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


_SETTING_PREFIX = 'student_certificate_layout:'
_ELEMENT_DEFAULTS = {
    'photo': (1, 2.8, 7.1, 17.4, 0.9),
    'number': (2.5, 21.2, 10, 3, 0.9),
    'country': (9, 1.2, 82, 3, 0.94),
    'ministry': (9, 4.5, 82, 3, 0.94),
    'period': (9, 7.8, 82, 3, 0.94),
    'title': (9, 11.2, 82, 5, 1.9),
    'statement': (63, 24.8, 34.7, 4.6, 0.84),
    'national_id': (34, 24.8, 27, 4.6, 0.9),
    'father': (2.3, 24.8, 30, 4.6, 0.9),
    'id_number': (63, 29.7, 34.7, 4.6, 0.9),
    'birth_date': (34, 29.7, 27, 4.6, 0.9),
    'academic_year': (2.3, 29.7, 30, 4.6, 0.9),
    'school': (63, 34.6, 34.7, 4.6, 0.9),
    'grade': (34, 34.6, 27, 4.6, 0.9),
    'program': (2.3, 34.6, 30, 4.6, 0.76),
    'status': (47.5, 42, 50, 4.5, 0.9),
    'request_label': (2.5, 48.9, 95, 4.5, 0.9),
    'issue_date': (2.5, 55, 95, 4.5, 0.9),
    'purpose_label': (2.5, 61.2, 95, 4.5, 0.9),
    'purpose': (2.5, 67.3, 95, 4.5, 0.9),
    'disclaimer': (2.5, 73.4, 95, 4.5, 0.9),
    'signature_title': (25, 75, 36, 5, 0.8),
    'signature_name': (25, 81, 36, 5, 0.8),
    'qr': (84.7, 84, 10.5, 10.5, 0.8),
    'warning': (0.8, 92, 35.5, 4, 1.25),
}

# A4 layout: readable two-column fields and full-page frame.
for _key, _values in list(_ELEMENT_DEFAULTS.items()):
    _ELEMENT_DEFAULTS[_key] = (*_values[:4], max(2.15, _values[4] * 1.9))
_ELEMENT_DEFAULTS['title'] = (9, 11, 82, 6, 3.4)
_ELEMENT_DEFAULTS['statement'] = (5, 22, 90, 6, 2.1)
for _index, _key in enumerate(('national_id','father','id_number','birth_date','academic_year','school','grade','program')):
    _ELEMENT_DEFAULTS[_key] = (52 if _index % 2 == 0 else 5, 29 + (_index // 2)*6, 43, 5.5, 2.15)
_ELEMENT_DEFAULTS['status'] = (5, 54, 90, 4, 1.9)
for _key, _y in [('request_label',59),('issue_date',63),('purpose_label',67),('purpose',71),('disclaimer',76)]:
    _ELEMENT_DEFAULTS[_key] = (5, _y, 90, 4, 1.9)
_ELEMENT_DEFAULTS['signature_title'] = (8, 82, 55, 4, 2.15)
_ELEMENT_DEFAULTS['signature_name'] = (8, 87, 55, 5, 2.15)
_ELEMENT_DEFAULTS['warning'] = (4, 95, 92, 4, 1.4)

ELEMENT_LABELS = {
    'photo': 'عکس دانش‌آموز',
    'number': 'شماره گواهی',
    'country': 'جمهوری اسلامی ایران',
    'ministry': 'وزارت آموزش و پرورش',
    'period': 'دوره تحصیلی',
    'title': 'عنوان گواهی',
    'statement': 'جمله تأیید تحصیل و نام',
    'national_id': 'کد ملی',
    'father': 'نام پدر',
    'id_number': 'شماره شناسنامه',
    'birth_date': 'تاریخ تولد',
    'academic_year': 'سال تحصیلی',
    'school': 'نام و کد مدرسه',
    'grade': 'پایه و کلاس',
    'program': 'رشته',
    'status': 'وضعیت تحصیل',
    'request_label': 'جمله تاریخ تقاضا',
    'issue_date': 'تاریخ تقاضا',
    'purpose_label': 'جمله مقصد ارائه',
    'purpose': 'مقصد ارائه',
    'disclaimer': 'جمله توضیح اعتبار',
    'signature_title': 'عنوان امضا',
    'signature_name': 'نام مدیر و مدرسه',
    'qr': 'کد QR',
    'warning': 'هشدار اعتبار گواهی',
}


def default_layout() -> dict[str, Any]:
    return {
        'version': 2,
        'paper_size': 'A4',
        'font_scale': 1.0,
        'frame_margin': 8,
        'border_width': 0.4,
        'orientation': 'portrait',
        'elements': {
            key: dict(zip(('x', 'y', 'w', 'h', 'font'), values))
            for key, values in _ELEMENT_DEFAULTS.items()
        },
    }


def _number(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        number = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        number = fallback
    return round(max(minimum, min(maximum, number)), 2)


def sanitize_layout(raw: Any) -> dict[str, Any]:
    """Accept only known elements and keep every draggable item inside the page."""
    base = default_layout()
    source = raw if isinstance(raw, dict) else {}
    result = deepcopy(base)
    result['orientation'] = source.get('orientation') if source.get('orientation') in {'portrait', 'landscape'} else 'portrait'
    result['paper_size'] = source.get('paper_size') if source.get('paper_size') in ('A4', 'A3') else 'A4'
    for key, lo, hi in (('font_scale', 0.8, 1.6), ('frame_margin', 5, 18), ('border_width', 0, 2)):
        result[key] = _number(source.get(key), base[key], lo, hi)
    # Older saved coordinates remain intact; increase their legacy tiny type
    # once while migrating to the A4-capable version-2 schema.
    legacy = source.get('version') == 1
    elements = source.get('elements') if isinstance(source.get('elements'), dict) else {}
    for key, defaults in base['elements'].items():
        item = elements.get(key) if isinstance(elements.get(key), dict) else {}
        x = _number(item.get('x'), defaults['x'], 0, 99)
        y = _number(item.get('y'), defaults['y'], 0, 99)
        w = _number(item.get('w'), defaults['w'], 1, 100 - x)
        h = _number(item.get('h'), defaults['h'], 1, 100 - y)
        result['elements'][key] = {
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'font': min(4, max(1.85, _number(item.get('font'), defaults['font'], 0.3, 4) * 1.5)) if legacy else _number(item.get('font'), defaults['font'], 0.3, 4),
        }
    return result


def settings_key(user_id: Any) -> str:
    return f'{_SETTING_PREFIX}{user_id}'


def load_layout(conn, user_id: Any) -> dict[str, Any]:
    if not user_id:
        return default_layout()
    row = conn.execute('SELECT value FROM app_settings WHERE key=?', (settings_key(user_id),)).fetchone()
    if not row:
        return default_layout()
    try:
        stored = json.loads(row['value'] or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = {}
    return sanitize_layout(stored)


def save_layout(conn, user_id: Any, layout: Any) -> dict[str, Any]:
    cleaned = sanitize_layout(layout)
    conn.execute(
        'INSERT INTO app_settings(key,value) VALUES(?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (settings_key(user_id), json.dumps(cleaned, ensure_ascii=False)),
    )
    return cleaned


def reset_layout(conn, user_id: Any) -> None:
    conn.execute('DELETE FROM app_settings WHERE key=?', (settings_key(user_id),))
