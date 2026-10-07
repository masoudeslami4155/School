"""Per-user orientation, margins, element positions and templates for AI letters."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


_SETTING_PREFIX = 'ai_letter_layout:'
_TEMPLATES_PREFIX = 'ai_letter_templates:'
MAX_USER_TEMPLATES = 12
TEMPLATE_KEY_RE = re.compile(r'[a-z0-9_]{1,40}')
_MARGIN_SIDES = ('top', 'right', 'bottom', 'left')
_MARGIN_DEFAULTS = {'top': 18, 'right': 20, 'bottom': 18, 'left': 20}
_ELEMENT_DEFAULTS = {
    'header': (0, 0, 100, 7, 0.95),
    'school': (0, 8, 100, 6, 1.25),
    'office': (0, 14.5, 100, 5, 1.25),
    'subject': (0, 20.5, 100, 6, 1.0),
    'greeting': (0, 27, 100, 5, 1.0),
    'body': (0, 32.5, 100, 34, 1.0),
    'closing': (0, 67.5, 100, 6, 1.0),
    'student_info': (0, 75, 55, 20, 0.95),
    'signature': (60, 75, 40, 20, 0.95),
}

ELEMENT_LABELS = {
    'header': 'تاریخ، شماره و پیوست',
    'school': 'نام مدرسه',
    'office': 'دفتر مدیریت',
    'subject': 'موضوع نامه',
    'greeting': 'خطاب نامه',
    'body': 'متن نامه',
    'closing': 'با تشکر و سپاس',
    'student_info': 'مشخصات دانش‌آموز',
    'signature': 'امضای مدیر',
}


def default_layout() -> dict[str, Any]:
    return {
        'version': 1,
        'orientation': 'portrait',
        'margin': dict(_MARGIN_DEFAULTS),
        'font_size': 12,
        'elements': {
            key: dict(zip(('x', 'y', 'w', 'h', 'font'), values))
            for key, values in _ELEMENT_DEFAULTS.items()
        },
    }


def _preset(patch: dict[str, tuple]) -> dict[str, Any]:
    """Build a full layout from the defaults plus a position patch."""
    layout = default_layout()
    for key, values in patch.items():
        layout['elements'][key] = dict(zip(('x', 'y', 'w', 'h', 'font'), values))
    return layout


# الگوهای پیش‌فرض نامه؛ هرکدام چیدمان و قلم مخصوص خود را دارند.
TEMPLATE_PRESETS: dict[str, dict[str, Any]] = {
    'tazzek': {
        'label': 'تذکر رسمی',
        'builtin': True,
        'layout': default_layout(),
    },
    'daavat': {
        'label': 'دعوت‌نامه',
        'builtin': True,
        'layout': _preset({
            'header': (0, 0, 100, 7, 0.9),
            'school': (10, 8, 80, 8, 1.5),
            'office': (10, 16.5, 80, 5, 1.1),
            'subject': (15, 22.5, 70, 7, 1.2),
            'greeting': (15, 30.5, 70, 6, 1.2),
            'body': (15, 37.5, 70, 30, 1.1),
            'closing': (15, 68.5, 70, 6, 1.0),
            'student_info': (10, 76, 45, 20, 0.95),
            'signature': (55, 76, 40, 20, 0.95),
        }),
    },
    'moarefi': {
        'label': 'نامهٔ معرفی',
        'builtin': True,
        'layout': _preset({
            'header': (0, 0, 100, 7, 0.95),
            'school': (0, 8, 100, 6, 1.25),
            'office': (0, 14.5, 100, 5, 1.25),
            'subject': (0, 20.5, 100, 6, 1.0),
            'greeting': (0, 27, 100, 5, 1.0),
            'body': (0, 32.5, 100, 30, 1.0),
            'closing': (0, 63.5, 100, 6, 1.0),
            'student_info': (0, 71, 40, 24, 0.9),
            'signature': (45, 71, 55, 24, 1.0),
        }),
    },
}


def _number(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        number = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        number = fallback
    return round(float(max(minimum, min(maximum, number))), 2)


def sanitize_layout(raw: Any) -> dict[str, Any]:
    """Accept only known elements and keep every draggable item inside the page."""
    base = default_layout()
    source = raw if isinstance(raw, dict) else {}
    result = deepcopy(base)
    result['orientation'] = (
        source.get('orientation')
        if source.get('orientation') in {'portrait', 'landscape'}
        else 'portrait'
    )
    margin = source.get('margin') if isinstance(source.get('margin'), dict) else {}
    for side in _MARGIN_SIDES:
        result['margin'][side] = _number(
            margin.get(side), _MARGIN_DEFAULTS[side], 0, 30,
        )
    result['font_size'] = _number(source.get('font_size'), 12, 8, 18)
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
            'font': _number(item.get('font'), defaults['font'], 0.5, 2.5),
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


def templates_key(user_id: Any) -> str:
    return f'{_TEMPLATES_PREFIX}{user_id}'


def _stored_templates(conn, user_id: Any) -> dict[str, dict[str, Any]]:
    if not user_id:
        return {}
    row = conn.execute('SELECT value FROM app_settings WHERE key=?', (templates_key(user_id),)).fetchone()
    try:
        data = json.loads(row['value'] or '{}') if row else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def list_templates(conn, user_id: Any) -> list[dict[str, Any]]:
    """Built-in presets first, then the user's saved templates."""
    templates = [
        {'key': key, 'label': preset['label'], 'builtin': True, 'layout': preset['layout']}
        for key, preset in TEMPLATE_PRESETS.items()
    ]
    for key, item in _stored_templates(conn, user_id).items():
        if not isinstance(item, dict):
            continue
        templates.append({
            'key': key,
            'label': str(item.get('label') or key),
            'builtin': False,
            'layout': sanitize_layout(item.get('layout')),
        })
    return templates


def load_template(conn, user_id: Any, key: str) -> dict[str, Any] | None:
    """Return the layout of a built-in or user template, or ``None``."""
    preset = TEMPLATE_PRESETS.get(key)
    if preset:
        return deepcopy(preset['layout'])
    if not TEMPLATE_KEY_RE.fullmatch(str(key or '')):
        return None
    item = _stored_templates(conn, user_id).get(key)
    if not isinstance(item, dict):
        return None
    return sanitize_layout(item.get('layout'))


def save_user_template(conn, user_id: Any, key: str, label: str, layout: Any) -> dict[str, Any]:
    """Store one user template; built-in keys are reserved."""
    key = str(key or '').strip()
    label = str(label or '').strip()[:60]
    if not TEMPLATE_KEY_RE.fullmatch(key):
        raise ValueError('کلید الگوی نامه معتبر نیست.')
    if key in TEMPLATE_PRESETS:
        raise ValueError('نام این الگوی پیش‌فرض محفوظ است؛ نام دیگری برگزینید.')
    if not label:
        raise ValueError('نام الگو را وارد کنید.')
    saved = _stored_templates(conn, user_id)
    if key not in saved and len(saved) >= MAX_USER_TEMPLATES:
        raise ValueError(f'در هر بار حداکثر {MAX_USER_TEMPLATES} الگوی شخصی ذخیره کنید.')
    cleaned = sanitize_layout(layout)
    saved[key] = {'label': label, 'layout': cleaned}
    conn.execute(
        'INSERT INTO app_settings(key,value) VALUES(?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (templates_key(user_id), json.dumps(saved, ensure_ascii=False)),
    )
    return saved[key]


def delete_user_template(conn, user_id: Any, key: str) -> None:
    """Remove a user template; built-in presets can not be deleted."""
    if str(key or '') in TEMPLATE_PRESETS:
        raise ValueError('الگوهای پیش‌فرض قابل حذف نیستند.')
    saved = _stored_templates(conn, user_id)
    saved.pop(str(key), None)
    conn.execute(
        'INSERT INTO app_settings(key,value) VALUES(?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (templates_key(user_id), json.dumps(saved, ensure_ascii=False)),
    )
