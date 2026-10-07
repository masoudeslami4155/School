from __future__ import annotations

import json
import re
from typing import Any

from .database import get_db

CUSTOM_PREFIX = 'custom_'
ALLOWED_TYPES = {'text', 'textarea', 'number', 'date', 'select', 'checkbox'}


def _clean(value: object, limit: int = 1000) -> str:
    return str(value or '').strip()[:limit]


def _options(raw: object) -> list[str]:
    if not raw:
        return []
    try:
        values = json.loads(str(raw))
        if not isinstance(values, list):
            return []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [_clean(value, 120) for value in values if _clean(value, 120)]


def _row_dict(row, value: object = '') -> dict[str, Any]:
    item = dict(row)
    item['options'] = _options(item.get('options_json'))
    item['value'] = '' if value is None else str(value)
    return item


def list_fields(conn, active_only: bool = False) -> list[dict[str, Any]]:
    where = 'WHERE active=1' if active_only else ''
    rows = conn.execute(
        f'''SELECT * FROM student_custom_fields {where}
            ORDER BY sort_order, id'''
    ).fetchall()
    return [_row_dict(row) for row in rows]


def fields_for_form(conn, student_id: int | None = None) -> list[dict[str, Any]]:
    fields = list_fields(conn, active_only=True)
    values: dict[int, str] = {}
    if student_id is not None and fields:
        rows = conn.execute(
            'SELECT field_id,value FROM student_custom_values WHERE student_id=?', (student_id,)
        ).fetchall()
        values = {int(row['field_id']): row['value'] or '' for row in rows}
    for field in fields:
        field['value'] = values.get(int(field['id']), '')
        # Keep a saved value visible even if its option was later retired.
        if field['field_type'] == 'select' and field['value'] and field['value'] not in field['options']:
            field['options'].append(field['value'])
    return fields


def fields_for_profile(conn, student_id: int, include_teacher: bool = False) -> list[dict[str, Any]]:
    fields = list_fields(conn, active_only=True)
    if not include_teacher:
        fields = [field for field in fields if field.get('show_to_teacher')]
    if not fields:
        return []
    rows = conn.execute(
        'SELECT field_id,value FROM student_custom_values WHERE student_id=?', (student_id,)
    ).fetchall()
    values = {int(row['field_id']): row['value'] or '' for row in rows}
    for field in fields:
        field['value'] = values.get(int(field['id']), '')
    return fields


def collect_values(form, fields: list[dict[str, Any]]) -> dict[int, str]:
    values: dict[int, str] = {}
    for field in fields:
        key = f"{CUSTOM_PREFIX}{field['id']}"
        if field['field_type'] == 'checkbox':
            value = '1' if form.get(key) in {'1', 'on', 'true', 'بله'} else '0'
        elif field['field_type'] == 'select':
            value = _clean(form.get(key), 500)
            if value and value not in field['options']:
                value = ''
        else:
            value = _clean(form.get(key), 2000)
        values[int(field['id'])] = value
    return values


def apply_values_to_fields(fields: list[dict[str, Any]], values: dict[int, str]) -> None:
    for field in fields:
        field['value'] = values.get(int(field['id']), '')


def validate_values(fields: list[dict[str, Any]], values: dict[int, str]) -> list[str]:
    errors: list[str] = []
    for field in fields:
        value = values.get(int(field['id']), '')
        label = field['label']
        if field.get('required') and not value and field['field_type'] != 'checkbox':
            errors.append(f'فیلد «{label}» الزامی است.')
        if field['field_type'] == 'number' and value:
            try:
                float(value)
            except ValueError:
                errors.append(f'مقدار «{label}» باید عددی باشد.')
        if field['field_type'] == 'select' and value and value not in field['options']:
            errors.append(f'گزینهٔ انتخاب‌شده برای «{label}» معتبر نیست.')
    return errors


def save_values(conn, student_id: int, values: dict[int, str]) -> None:
    for field_id, value in values.items():
        conn.execute(
            '''INSERT INTO student_custom_values(student_id,field_id,value,updated_at)
               VALUES(?,?,?,datetime('now'))
               ON CONFLICT(student_id,field_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at''',
            (student_id, field_id, value),
        )
