#!/usr/bin/env python
"""Regression checks for selectable, combined statistics printing."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp = Path(tempfile.mkdtemp(prefix='statistics-print-test-'))
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'statistics-print-test-secret-key',
})

from school_app.statistics_routes import _combined_breakdown_rows, _parse_print_breakdowns  # noqa: E402


def main() -> int:
    assert _parse_print_breakdowns('gender,grade,class,gender') == (
        'gender', 'grade', 'class_name'
    )
    assert _parse_print_breakdowns('') == (
        'teacher', 'gender', 'grade', 'class_name', 'sida_class'
    )

    values = {
        'gender_stats': [{'label': 'دختر', 'total': 2, 'active_count': 2, 'share': 50}],
        'grade_stats': [{'label': 'پایه اول', 'total': 2, 'active_count': 1, 'share': 50}],
        'class_stats': [{'label': 'کلاس ۱', 'total': 2, 'active_count': 2, 'share': 50}],
    }
    rows = _combined_breakdown_rows(('gender', 'grade', 'class_name'), values)
    assert [row['dimension_key'] for row in rows] == ['gender', 'grade', 'class_name']
    assert [row['dimension_label'] for row in rows] == ['جنسیت', 'پایه', 'کلاس مدرسه']
    assert rows[0]['graduate_count'] == 0
    print('statistics print selection and combined rows passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
