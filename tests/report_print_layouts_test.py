#!/usr/bin/env python
"""Regression checks for the report print-layout store."""

from __future__ import annotations

import sqlite3
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = Path(tempfile.mkdtemp(prefix='report-print-layout-test-'))
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'report-print-layout-test-secret-key',
})

from school_app.report_print_layouts import (  # noqa: E402
    REPORT_DOCUMENTS,
    default_layout,
    element_css,
    load_layout,
    page_css,
    sanitize_layout,
    save_layout,
)
from school_app.student_dashboard import STUDENT_FILTER_REFERENCE  # noqa: E402


def main() -> int:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT)')

    layout = sanitize_layout('folder_labels', {
        'orientation': 'portrait',
        'margin': {'top': 99, 'right': -4},
        'grid': {'columns': 9, 'rows': 0},
        'columns': {key: False for key in default_layout('folder_labels')['columns']},
    })
    assert layout['orientation'] == 'portrait'
    assert layout['margin']['top'] == 30
    assert layout['margin']['right'] == 0
    assert layout['grid'] == {'columns': 6, 'rows': 1}
    assert sum(layout['columns'].values()) == 1

    save_layout(conn, 'folder_labels', 17, layout)
    loaded = load_layout(conn, 'folder_labels', 17)
    assert loaded == layout
    assert '@page{size:A4 portrait' in page_css(loaded)
    assert load_layout(conn, 'folder_labels', 18) == default_layout('folder_labels')

    movable = sanitize_layout('attendance_students', {
        'elements': {
            'hero': {'x': 12.5, 'y': -70, 'sx': 9, 'sy': 0.2},
            'unknown': {'x': 40},
        },
    })
    assert movable['elements']['hero'] == {'x': 12.5, 'y': -60, 'sx': 2.5, 'sy': 0.5}
    assert 'unknown' not in movable['elements']
    assert element_css(movable) == (
        '[data-report-element="hero"]{transform:translate(12.5mm,-60mm) '
        'scale(2.5,0.5);transform-origin:top left}'
    )
    assert element_css(default_layout('attendance_students')) == ''
    save_layout(conn, 'attendance_students', 17, movable)
    assert load_layout(conn, 'attendance_students', 17) == movable

    for document in REPORT_DOCUMENTS:
        assert default_layout(document)['version'] == 1

    wall = sanitize_layout('wall_cards', {
        'orientation': 'landscape',
        'grid': {'columns': 99, 'rows': 99, 'gap_x': 30},
        'card': {'height': 99, 'photo_size': -5, 'show_gender': False},
    })
    assert wall['grid'] == {'columns': 6, 'rows': 4, 'gap_x': 10, 'gap_y': 1.5}
    assert wall['card']['height'] == 40
    assert wall['card']['photo_size'] == 0
    assert wall['card']['show_gender'] is False
    save_layout(conn, 'wall_cards', 17, wall)
    assert load_layout(conn, 'wall_cards', 17) == wall
    dense = sanitize_layout('wall_cards', {
        'margin': {'top': 30, 'bottom': 30},
        'grid': {'rows': 6, 'gap_y': 10},
        'card': {'height': 48},
    })
    used_height = (
        dense['margin']['top'] + dense['margin']['bottom'] + 12
        + dense['grid']['rows'] * dense['card']['height']
        + (dense['grid']['rows'] - 1) * dense['grid']['gap_y']
    )
    assert used_height <= 297
    assert REPORT_DOCUMENTS['student_filters']['kind'] == 'filter_reference'
    assert {item['key'] for item in STUDENT_FILTER_REFERENCE} >= {
        'q', 'grade', 'class_name', 'sida_class', 'gender', 'teacher_code', 'quickStudentSearch',
    }

    print('report print layouts: sanitize, per-user persistence, element transforms, wall cards and page CSS passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
