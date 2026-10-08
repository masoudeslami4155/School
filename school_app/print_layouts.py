"""Validated, per-user layout settings for A4 print documents."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Iterable


DOCUMENTS = {
    'service_request': {
        'label': 'برگه درخواست پرداخت هزینه',
        'short_label': 'درخواست هزینه',
        'kind': 'slip',
        'preview_endpoint': 'monthly_service_print',
        'preview_query': 'kind=requests',
    },
    'service_receipt': {
        'label': 'رسید دریافت وجه',
        'short_label': 'رسید دریافت',
        'kind': 'slip',
        'preview_endpoint': 'monthly_service_print',
        'preview_query': 'kind=receipts',
    },
    'service_drivers': {
        'label': 'جدول رانندگان سرویس',
        'short_label': 'جدول رانندگان',
        'kind': 'drivers',
        'preview_endpoint': 'service_drivers_print',
        'preview_query': '',
    },
}

SLIP_ELEMENT_LABELS = {
    'badge': 'عنوان نوع برگه',
    'header': 'نام مدرسه و توضیح برگه',
    'routing': 'معلم و کلاس',
    'lead': 'متن اصلی برگه',
    'table': 'جدول مبالغ',
    'bank': 'اطلاعات واریز',
    'signatures': 'محل امضا',
    'footer': 'پابرگ و تاریخ',
}

_SETTING_PREFIX = 'print_layout:'
_SIDES = ('top', 'right', 'bottom', 'left')
_PAGE_MM = {'portrait': (210, 297), 'landscape': (297, 210)}


def _slip_elements() -> dict[str, dict[str, Any]]:
    return {
        'badge': {'x': 30, 'y': 3, 'w': 36, 'h': 9, 'font': 11, 'visible': True},
        'header': {'x': 4, 'y': 14, 'w': 88, 'h': 14, 'font': 10, 'visible': True},
        'routing': {'x': 4, 'y': 30, 'w': 88, 'h': 8, 'font': 7, 'visible': True},
        'lead': {'x': 4, 'y': 40, 'w': 88, 'h': 31, 'font': 8, 'visible': True},
        'table': {'x': 4, 'y': 74, 'w': 88, 'h': 23, 'font': 7.5, 'visible': True},
        'bank': {'x': 4, 'y': 100, 'w': 88, 'h': 20, 'font': 7.5, 'visible': True},
        'signatures': {'x': 4, 'y': 100, 'w': 88, 'h': 18, 'font': 7.5, 'visible': True},
        'footer': {'x': 4, 'y': 123, 'w': 88, 'h': 8, 'font': 6.5, 'visible': True},
    }


def _default_slip_layout() -> dict[str, Any]:
    return {
        'version': 1,
        'orientation': 'portrait',
        'margin': {'top': 6, 'right': 6, 'bottom': 6, 'left': 6},
        'grid': {
            'columns': 2,
            'rows': 2,
            'width': 96,
            'height': 136,
            'gap_x': 3.5,
            'gap_y': 3.5,
            'offset_x': 0,
            'offset_y': 0,
        },
        'elements': _slip_elements(),
    }


def _default_driver_layout() -> dict[str, Any]:
    return {
        'version': 1,
        'orientation': 'landscape',
        'margin': {'top': 8, 'right': 8, 'bottom': 8, 'left': 8},
        'table': {
            'x': 0,
            'y': 0,
            'width': 281,
            'font_size': 8,
            'header_font_size': 13,
            'row_padding': 1.1,
            'student_columns': 4,
            'photo_size': 9,
            'scale_y': 1,
            'show_photos': True,
            'show_teacher_names': True,
            'show_header': True,
            'show_footer': True,
        },
    }


def default_layout(document: str) -> dict[str, Any]:
    if document not in DOCUMENTS:
        document = 'service_receipt'
    if DOCUMENTS[document]['kind'] == 'drivers':
        return _default_driver_layout()
    return _default_slip_layout()


def _number(value: Any, fallback: float, minimum: float, maximum: float, *, integer: bool = False) -> float | int:
    try:
        number = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        number = fallback
    number = max(minimum, min(maximum, number))
    return int(round(number)) if integer else round(number, 2)


def _boolean(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.strip().lower() in {'1', 'true', 'yes', 'on', 'بله'}:
            return True
        if value.strip().lower() in {'0', 'false', 'no', 'off', 'خیر'}:
            return False
    return fallback


def sanitize_layout(document: str, raw: Any) -> dict[str, Any]:
    """Keep only known layout fields and bound every numeric value."""
    base = default_layout(document)
    source = raw if isinstance(raw, dict) else {}
    result = deepcopy(base)
    result['orientation'] = source.get('orientation') if source.get('orientation') in _PAGE_MM else base['orientation']

    margin = source.get('margin') if isinstance(source.get('margin'), dict) else {}
    result['margin'] = {
        side: _number(margin.get(side), base['margin'][side], 0, 40)
        for side in _SIDES
    }

    if DOCUMENTS[document]['kind'] == 'drivers':
        table = source.get('table') if isinstance(source.get('table'), dict) else {}
        defaults = base['table']
        result['table'] = {
            'x': _number(table.get('x'), defaults['x'], 0, 120),
            'y': _number(table.get('y'), defaults['y'], 0, 120),
            'width': _number(table.get('width'), defaults['width'], 50, 297),
            'font_size': _number(table.get('font_size'), defaults['font_size'], 5, 18),
            'header_font_size': _number(table.get('header_font_size'), defaults['header_font_size'], 8, 24),
            'row_padding': _number(table.get('row_padding'), defaults['row_padding'], 0, 8),
            'student_columns': _number(table.get('student_columns'), defaults['student_columns'], 1, 8, integer=True),
            'photo_size': _number(table.get('photo_size'), defaults['photo_size'], 0, 25),
            'scale_y': _number(table.get('scale_y'), defaults['scale_y'], 0.5, 2.5),
            'show_photos': _boolean(table.get('show_photos'), defaults['show_photos']),
            'show_teacher_names': _boolean(table.get('show_teacher_names'), defaults['show_teacher_names']),
            'show_header': _boolean(table.get('show_header'), defaults['show_header']),
            'show_footer': _boolean(table.get('show_footer'), defaults['show_footer']),
        }
        return result

    grid = source.get('grid') if isinstance(source.get('grid'), dict) else {}
    defaults = base['grid']
    result['grid'] = {
        'columns': _number(grid.get('columns'), defaults['columns'], 1, 6, integer=True),
        'rows': _number(grid.get('rows'), defaults['rows'], 1, 8, integer=True),
        'width': _number(grid.get('width'), defaults['width'], 20, 205),
        'height': _number(grid.get('height'), defaults['height'], 20, 285),
        'gap_x': _number(grid.get('gap_x'), defaults['gap_x'], 0, 30),
        'gap_y': _number(grid.get('gap_y'), defaults['gap_y'], 0, 30),
        'offset_x': _number(grid.get('offset_x'), defaults['offset_x'], -80, 80),
        'offset_y': _number(grid.get('offset_y'), defaults['offset_y'], -80, 80),
    }
    raw_elements = source.get('elements') if isinstance(source.get('elements'), dict) else {}
    for key, defaults in base['elements'].items():
        item = raw_elements.get(key) if isinstance(raw_elements.get(key), dict) else {}
        result['elements'][key] = {
            'x': _number(item.get('x'), defaults['x'], 0, 205),
            'y': _number(item.get('y'), defaults['y'], 0, 285),
            'w': _number(item.get('w'), defaults['w'], 1, 205),
            'h': _number(item.get('h'), defaults['h'], 1, 285),
            'font': _number(item.get('font'), defaults['font'], 5, 30),
            'visible': _boolean(item.get('visible'), defaults['visible']),
        }
    return result


def settings_key(document: str, user_id: Any) -> str:
    return f'{_SETTING_PREFIX}{document}:{user_id}'


def load_layout(conn, document: str, user_id: Any) -> dict[str, Any]:
    fallback = default_layout(document)
    if not user_id or document not in DOCUMENTS:
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


def _mm(value: Any) -> str:
    return f'{float(value):g}'


def page_style(layout: dict[str, Any]) -> str:
    width, height = _PAGE_MM[layout['orientation']]
    return f'width:{_mm(width)}mm;height:{_mm(height)}mm;'


def slip_style(layout: dict[str, Any], index: int) -> str:
    grid = layout['grid']
    column = index % grid['columns']
    row = index // grid['columns']
    right = layout['margin']['right'] + grid['offset_x'] + column * (grid['width'] + grid['gap_x'])
    top = layout['margin']['top'] + grid['offset_y'] + row * (grid['height'] + grid['gap_y'])
    return (
        f'right:{_mm(right)}mm;top:{_mm(top)}mm;'
        f'width:{_mm(grid["width"])}mm;height:{_mm(grid["height"])}mm;'
    )


def _element_style(item: dict[str, Any]) -> str:
    display = 'block' if item['visible'] else 'none'
    return (
        f'display:{display};right:{_mm(item["x"])}mm;top:{_mm(item["y"])}mm;'
        f'width:{_mm(item["w"])}mm;height:{_mm(item["h"])}mm;font-size:{_mm(item["font"])}pt;'
    )


def prepare_for_print(layout: dict[str, Any]) -> dict[str, Any]:
    """Add safe CSS strings to an already sanitized layout for Jinja."""
    prepared = deepcopy(layout)
    prepared['page_style'] = page_style(prepared)
    if 'elements' in prepared:
        for item in prepared['elements'].values():
            item['style'] = _element_style(item)
    if 'table' in prepared:
        table = prepared['table']
        prepared['table_style'] = (
            f'margin-right:{_mm(table["x"])}mm;margin-top:{_mm(table["y"])}mm;'
            f'width:{_mm(table["width"])}mm;font-size:{_mm(table["font_size"])}pt;'
            f'--driver-header-size:{_mm(table["header_font_size"])}pt;'
            f'--driver-row-padding:{_mm(table["row_padding"])}mm;'
            f'--driver-student-columns:{table["student_columns"]};'
            f'--driver-photo-size:{_mm(table["photo_size"])}mm;'
            f'transform:scaleY({_mm(table["scale_y"])});transform-origin:top right;'
        )
    return prepared


def build_slip_batch(slips: Iterable[dict[str, Any]], layout: dict[str, Any]) -> dict[str, Any]:
    cleaned = sanitize_layout('service_receipt', layout)
    per_page = cleaned['grid']['columns'] * cleaned['grid']['rows']
    items = list(slips)
    pages = []
    for start in range(0, len(items), per_page):
        page = []
        for index, slip in enumerate(items[start:start + per_page]):
            item = dict(slip)
            item['style'] = slip_style(cleaned, index)
            page.append(item)
        pages.append(page)
    return {'layout': prepare_for_print(cleaned), 'pages': pages}
