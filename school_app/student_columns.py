"""Logic behind the "custom student columns" view.

The page lets every user decide which pieces of student information appear as
table columns, then prints the result on A4 and exports it to Excel.

Only pure data work lives here: building the catalogue of selectable columns,
remembering each user's choice, and turning stored values into readable text.
Database queries, permissions and HTTP handling stay in
`school_app/routes/student_columns.py` so this module keeps no Flask dependency
of its own.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence

from .dates import calculate_jalali_age, normalize_digits

EMPTY_LABEL = 'ثبت نشده'

# These columns are never offered: the retired general parent phone (migrated
# into the father's phone on startup) and the uploaded photo file name.
EXCLUDED_COLUMN_KEYS = {'parent_phone', 'photo'}

# The student columns a teacher may already see in the readable profile; the
# same boundary is applied to this table so nothing new is exposed.
TEACHER_ALLOWED_KEYS = {
    'id', 'first_name', 'last_name', 'code', 'birth_date', 'grade', 'class_name',
    'sida_class', 'gender', 'teacher_code', 'status',
}

# Columns that are computed for the table instead of being stored on the row.
VIRTUAL_LABELS: tuple[tuple[str, str], ...] = (
    ('full_name', 'نام و نام خانوادگی'),
    ('age', 'سن (سال، ماه، روز)'),
    ('teacher_name', 'معلم منتسب'),
)
VIRTUAL_GROUP_TITLE = '🧮 ستون‌های آماده و محاسباتی'
CUSTOM_GROUP_TITLE = '🧩 اطلاعات تکمیلی سفارشی'
LEFT_OVER_GROUP_TITLE = '🧾 سایر اطلاعات ثبت‌شده'

DEFAULT_COLUMN_KEYS: tuple[str, ...] = (
    'first_name', 'last_name', 'code', 'birth_date', 'grade', 'class_name', 'teacher_name',
)

SETTING_PREFIX = 'student_columns:user:'
BOOLEAN_TRUE = {'1', 'true', 'yes', 'بله', 'دارد'}
BOOLEAN_FALSE = {'0', 'false', 'no', 'خیر', 'ندارد'}


def column_types(conn) -> dict[str, str]:
    """Return the real column names and SQLite types of the students table."""
    rows = conn.execute('PRAGMA table_info("students")').fetchall()
    return {row['name']: (row['type'] or 'TEXT').upper() for row in rows}


def _student_item(key: str, labels: Mapping[str, str], types: Mapping[str, str],
                  boolean_fields: set[str], group_title: str) -> dict[str, Any]:
    return {
        'key': key,
        'label': labels[key],
        'kind': 'student',
        'field_type': 'checkbox' if key in boolean_fields else 'text',
        'boolean': key in boolean_fields,
        'numeric': 'INT' in types[key],
        'group': group_title,
        'teacher_visible': key in TEACHER_ALLOWED_KEYS,
    }


def column_catalogue(conn, *, labels: Mapping[str, str], sections: Sequence[tuple[str, Sequence[str]]],
                     boolean_fields: Iterable[str], restricted: bool = False,
                     custom_fields: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Build every selectable column, grouped exactly like the readable profile.

    A column is offered only when the students table really has it, so retired
    fields are skipped automatically. Custom form fields (including their
    teacher-visibility flag) are appended as an extra group.
    """
    types = column_types(conn)
    boolean_set = set(boolean_fields)
    allowed = {key for key in labels if key in types and key not in EXCLUDED_COLUMN_KEYS}
    if restricted:
        allowed &= TEACHER_ALLOWED_KEYS

    groups: list[dict[str, Any]] = []
    used: set[str] = set()
    for title, keys in sections:
        items = []
        for key in keys:
            if key in allowed and key not in used:
                used.add(key)
                items.append(_student_item(key, labels, types, boolean_set, title))
        if items:
            groups.append({'key': f'group-{len(groups)}', 'title': title, 'items': items})

    remaining = sorted((key for key in allowed if key not in used), key=lambda key: labels.get(key, key))
    if remaining:
        groups.append({
            'key': 'group-other',
            'title': LEFT_OVER_GROUP_TITLE,
            'items': [_student_item(key, labels, types, boolean_set, LEFT_OVER_GROUP_TITLE) for key in remaining],
        })

    groups.append({
        'key': 'group-virtual',
        'title': VIRTUAL_GROUP_TITLE,
        'items': [
            {'key': key, 'label': label, 'kind': 'virtual', 'field_type': 'text',
             'boolean': False, 'numeric': False, 'group': VIRTUAL_GROUP_TITLE,
             'teacher_visible': True}
            for key, label in VIRTUAL_LABELS
        ],
    })

    custom_items = [
        {'key': f"custom_{int(field['id'])}", 'field_id': int(field['id']), 'label': field['label'],
         'kind': 'custom', 'field_type': field['field_type'],
         'boolean': field['field_type'] == 'checkbox', 'numeric': field['field_type'] == 'number',
         'group': CUSTOM_GROUP_TITLE, 'teacher_visible': bool(field.get('show_to_teacher'))}
        for field in custom_fields
        if not restricted or field.get('show_to_teacher')
    ]
    if custom_items:
        groups.append({'key': 'group-custom', 'title': CUSTOM_GROUP_TITLE, 'items': custom_items})
    return groups


def allowed_keys(groups: Sequence[Mapping[str, Any]]) -> set[str]:
    return {item['key'] for group in groups for item in group['items']}


def default_selection(groups: Sequence[Mapping[str, Any]],
                      preferred: Sequence[str] = DEFAULT_COLUMN_KEYS) -> list[str]:
    """The starting columns, always inside the caller's own catalogue."""
    allowed = allowed_keys(groups)
    chosen = [key for key in preferred if key in allowed]
    if chosen:
        return chosen
    return [item['key'] for item in groups[0]['items'][:5]] if groups else []


def normalise_selection(raw_keys: Iterable[Any], allowed: set[str],
                        defaults: Sequence[str]) -> list[str]:
    """Keep only real column keys, without duplicates, and never return empty."""
    chosen: list[str] = []
    for key in raw_keys:
        text = str(key or '').strip()
        if text in allowed and text not in chosen:
            chosen.append(text)
    return chosen or list(defaults)


def selected_columns(groups: Sequence[Mapping[str, Any]], keys: Iterable[str]) -> list[dict[str, Any]]:
    chosen = set(keys)
    return [item for group in groups for item in group['items'] if item['key'] in chosen]


def load_saved_selection(conn, user_id: Any, allowed: set[str],
                         defaults: Sequence[str]) -> list[str]:
    row = conn.execute('SELECT value FROM app_settings WHERE key=?',
                       (f'{SETTING_PREFIX}{user_id}',)).fetchone()
    if not row:
        return list(defaults)
    try:
        stored = json.loads(row['value'] or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = []
    if not isinstance(stored, list):
        return list(defaults)
    return [key for key in stored if key in allowed] or list(defaults)


def save_selection(conn, user_id: Any, keys: Sequence[str]) -> None:
    conn.execute(
        'INSERT INTO app_settings(key,value) VALUES(?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (f'{SETTING_PREFIX}{user_id}', json.dumps(list(keys), ensure_ascii=False)),
    )


def display_value(value: object, *, boolean: bool = False, empty_label: str = EMPTY_LABEL) -> str:
    """Turn one stored value into the readable text used on screen and on paper."""
    text = '' if value is None else str(value).strip()
    if not text:
        return empty_label
    if boolean:
        normalized = text.lower()
        if normalized in BOOLEAN_TRUE:
            return 'بله'
        if normalized in BOOLEAN_FALSE:
            return 'خیر'
    return text


def _virtual_value(key: str, data: Mapping[str, Any], empty_label: str) -> str:
    if key == 'age':
        age = calculate_jalali_age(str(data.get('birth_date') or ''))
        return display_value(age.get('text'), empty_label=empty_label)
    if key == 'full_name':
        # Repeated spaces inside stored names are collapsed so the paper stays tidy.
        name = ' '.join(f"{data.get('first_name') or ''} {data.get('last_name') or ''}".split())
        return display_value(name, empty_label=empty_label)
    if key == 'teacher_name':
        name = ' '.join(f"{data.get('teacher_first') or ''} {data.get('teacher_last') or ''}".split())
        return display_value(name, empty_label=empty_label)
    return empty_label


def build_rows(students: Sequence[Any], columns: Sequence[Mapping[str, Any]],
               custom_values: Mapping[tuple[int, int], str] | None = None,
               empty_label: str = EMPTY_LABEL) -> list[dict[str, Any]]:
    """Build the table body: one entry per student with already-formatted cells."""
    custom_values = custom_values or {}
    rows: list[dict[str, Any]] = []
    for index, student in enumerate(students, 1):
        data = dict(student)
        student_id = int(data.get('id') or 0)
        cells: list[str] = []
        for column in columns:
            kind = column['kind']
            if kind == 'virtual':
                cells.append(_virtual_value(column['key'], data, empty_label))
                continue
            if kind == 'custom':
                raw = custom_values.get((student_id, int(column['field_id'])), '')
                cells.append(display_value(raw, boolean=bool(column['boolean']), empty_label=empty_label))
                continue
            cells.append(display_value(data.get(column['key']), boolean=bool(column['boolean']),
                                       empty_label=empty_label))
        rows.append({'index': index, 'student_id': student_id, 'cells': cells})
    return rows


def excel_cell(value: object, *, numeric: bool = False) -> Any:
    """Return a spreadsheet-safe value: numbers stay numbers, formulas never run."""
    if value is None:
        return ''
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if numeric:
        cleaned = normalize_digits(text).replace(',', '').replace('٬', '').replace('،', '').strip()
        for convert in (int, float):
            try:
                return convert(cleaned)
            except (TypeError, ValueError):
                continue
    if text[:1] in {'=', '+', '-', '@'}:
        return "'" + text
    return text