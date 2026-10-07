from __future__ import annotations

from flask import render_template

from ..database import get_db


def _missing_sql(column: str) -> str:
    return f"NULLIF(TRIM(COALESCE({column}, '')), '') IS NULL"


def _unassigned_teacher_sql() -> str:
    return (
        f"({_missing_sql('s.teacher_code')} OR NOT EXISTS ("
        "SELECT 1 FROM teachers dq_teacher WHERE dq_teacher.code = s.teacher_code))"
    )


_ACTIVE_SQL = "(s.status = 'فعال' OR s.status IS NULL)"

_COLUMNS = """
    SELECT s.id, s.first_name, s.last_name, s.code, s.grade, s.class_name,
           s.sida_class, s.gender, s.teacher_code,
           t.first_name AS teacher_first, t.last_name AS teacher_last
    FROM students s
    LEFT JOIN teachers t ON t.code = s.teacher_code
"""


def _fetch(conn, where_extra: str) -> list[dict]:
    rows = conn.execute(
        f"{_COLUMNS} WHERE {_ACTIVE_SQL} AND {where_extra} "
        "ORDER BY s.grade COLLATE NOCASE, s.class_name COLLATE NOCASE, s.last_name COLLATE NOCASE",
    ).fetchall()
    return [dict(row) for row in rows]


def data_quality():
    with get_db() as conn:
        gender_missing = _fetch(conn, _missing_sql('s.gender'))
        sida_missing = _fetch(conn, _missing_sql('s.sida_class'))
        class_missing = _fetch(conn, _missing_sql('s.class_name'))
        teacher_missing = _fetch(conn, _unassigned_teacher_sql())
        total_active = conn.execute(
            f'SELECT COUNT(*) AS count FROM students s WHERE {_ACTIVE_SQL}'
        ).fetchone()['count'] or 0

    all_ids = {row['id'] for row in gender_missing}
    all_ids |= {row['id'] for row in sida_missing}
    all_ids |= {row['id'] for row in class_missing}
    all_ids |= {row['id'] for row in teacher_missing}

    return render_template(
        'data_quality.html',
        total_active=total_active,
        incomplete_count=len(all_ids),
        gender_missing=gender_missing,
        sida_missing=sida_missing,
        class_missing=class_missing,
        teacher_missing=teacher_missing,
    )


def register(app):
    app.add_url_rule('/data-quality', endpoint='data_quality', view_func=data_quality)
