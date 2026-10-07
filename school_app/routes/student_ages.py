from __future__ import annotations

from flask import render_template, request

from ..database import get_db
from ..dates import calculate_jalali_age, today_string


def _clean(value: object, limit: int = 100) -> str:
    return str(value or '').strip()[:limit]


def _missing(column: str) -> str:
    return f"NULLIF(TRIM(COALESCE(s.{column}, '')), '') IS NULL"


def student_ages():
    """Show the calculated age of every student in the selected school scope."""
    selected = {
        'q': _clean(request.args.get('q')),
        'status': _clean(request.args.get('status')) or 'all',
        'grade': _clean(request.args.get('grade')),
        'class_name': _clean(request.args.get('class_name')),
        'sida_class': _clean(request.args.get('sida_class')),
        'gender': _clean(request.args.get('gender')),
        'teacher_code': _clean(request.args.get('teacher_code')),
    }
    clauses = ['1=1']
    params: list[object] = []
    status_sql = {
        'active': "(s.status='فعال' OR s.status IS NULL OR TRIM(COALESCE(s.status,''))='')",
        'graduate': "s.status IN ('فارغ‌التحصیل','فارغ التحصیل')",
        'dropout': "s.status='ترک تحصیل'",
        'other': "s.status='سایر'",
        'all': '1=1',
    }
    clauses.append(status_sql.get(selected['status'], status_sql['all']))
    if selected['q']:
        like = f"%{selected['q']}%"
        fields = ('first_name', 'last_name', 'code', 'grade', 'class_name', 'sida_class', 'gender')
        clauses.append('(' + ' OR '.join(f"COALESCE(s.{field}, '') LIKE ?" for field in fields) + ')')
        params.extend([like] * len(fields))
    for key in ('grade', 'class_name', 'sida_class', 'gender'):
        value = selected[key]
        if not value:
            continue
        if value == '__empty__':
            clauses.append(_missing(key))
        else:
            clauses.append(f's.{key}=?')
            params.append(value)
    if selected['teacher_code']:
        if selected['teacher_code'] == '__empty__':
            clauses.append(_missing('teacher_code'))
        else:
            clauses.append('s.teacher_code=?')
            params.append(selected['teacher_code'])

    where_sql = ' AND '.join(clauses)
    with get_db() as conn:
        students = conn.execute(f'''
            SELECT s.id,s.first_name,s.last_name,s.code,s.birth_date,s.gender,s.grade,
                   s.class_name,s.sida_class,s.teacher_code,s.status,
                   t.first_name AS teacher_first,t.last_name AS teacher_last
            FROM students s LEFT JOIN teachers t ON s.teacher_code=t.code
            WHERE {where_sql}
            ORDER BY CASE WHEN s.status='فعال' OR s.status IS NULL THEN 0 ELSE 1 END,
                     s.first_name,s.last_name,s.id
        ''', params).fetchall()
        grades = conn.execute("SELECT DISTINCT TRIM(COALESCE(grade,'')) AS value FROM students ORDER BY value").fetchall()
        classes = conn.execute("SELECT DISTINCT TRIM(COALESCE(class_name,'')) AS value FROM students ORDER BY value").fetchall()
        sida_classes = conn.execute("SELECT DISTINCT TRIM(COALESCE(sida_class,'')) AS value FROM students ORDER BY value").fetchall()
        genders = conn.execute("SELECT DISTINCT TRIM(COALESCE(gender,'')) AS value FROM students ORDER BY value").fetchall()
        teachers = conn.execute('SELECT code,first_name,last_name FROM teachers ORDER BY first_name,last_name').fetchall()

    def options(rows):
        values = []
        for row in rows:
            value = row['value'] or ''
            values.append({'value': '__empty__' if not value else value,
                           'label': 'ثبت نشده' if not value else value})
        return values

    rows = []
    for student in students:
        rows.append({'student': student, 'age': calculate_jalali_age(student['birth_date'])})
    return render_template(
        'student_ages.html', rows=rows, count=len(rows), today=today_string(),
        selected=selected, options={
            'grades': options(grades), 'classes': options(classes),
            'sida_classes': options(sida_classes), 'genders': options(genders),
        }, teachers=teachers,
    )


def register(app):
    app.add_url_rule('/student-ages', endpoint='student_ages', view_func=student_ages)
