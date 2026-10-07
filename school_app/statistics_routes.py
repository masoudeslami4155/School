from __future__ import annotations

from flask import render_template, request, session

from .database import get_db
from .dates import normalize_jalali_date
from .report_print_layouts import load_layout as load_report_layout


STATUS_LABELS = {
    'all': 'همه وضعیت‌ها',
    'active': 'فعال',
    'graduate': 'فارغ‌التحصیل',
    'dropout': 'ترک تحصیل',
    'other': 'سایر',
}

MISSING_LABEL = 'ثبت نشده'
UNASSIGNED_TEACHER = '__unassigned__'

STAT_BREAKDOWNS = (
    ('teacher', 'معلم', 'teacher_stats'),
    ('gender', 'جنسیت', 'gender_stats'),
    ('grade', 'پایه', 'grade_stats'),
    ('class_name', 'کلاس مدرسه', 'class_stats'),
    ('sida_class', 'کلاس سیدا', 'sida_stats'),
)


def _status_sql(status: str, alias: str = 's') -> str:
    active = f"({alias}.status = 'فعال' OR {alias}.status IS NULL OR TRIM(COALESCE({alias}.status, '')) = '')"
    graduate = f"({alias}.status IN ('فارغ‌التحصیل', 'فارغ التحصیل'))"
    dropout = f"({alias}.status = 'ترک تحصیل')"
    return {
        'active': active,
        'graduate': graduate,
        'dropout': dropout,
        'other': f'(NOT ({active} OR {graduate} OR {dropout}))',
    }.get(status, '1=1')


def _status_select(alias: str = 's') -> str:
    return f'''COUNT({alias}.id) AS total,
        SUM(CASE WHEN {_status_sql('active', alias)} THEN 1 ELSE 0 END) AS active_count,
        SUM(CASE WHEN {_status_sql('graduate', alias)} THEN 1 ELSE 0 END) AS graduate_count,
        SUM(CASE WHEN {_status_sql('dropout', alias)} THEN 1 ELSE 0 END) AS dropout_count,
        SUM(CASE WHEN {_status_sql('other', alias)} THEN 1 ELSE 0 END) AS other_count'''


def _dict_rows(rows):
    return [dict(row) for row in rows]


def _number(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _percent(part: int, total: int) -> float:
    if not total:
        return 0.0
    return round((part / total) * 100, 1)


def _parse_print_breakdowns(raw: str | None) -> tuple[str, ...]:
    """Normalize the selected statistic tables used by the print-only view."""
    aliases = {'class': 'class_name', 'sida': 'sida_class'}
    allowed = {key for key, _, _ in STAT_BREAKDOWNS}
    values = []
    for item in (raw or '').split(','):
        key = aliases.get(item.strip(), item.strip())
        if key in allowed and key not in values:
            values.append(key)
    if not values:
        values = [key for key, _, _ in STAT_BREAKDOWNS]
    return tuple(values)


def _combined_breakdown_rows(selected: tuple[str, ...], values: dict[str, list[dict]]) -> list[dict]:
    """Flatten selected breakdowns into one print-friendly table."""
    metadata = {key: (label, source) for key, label, source in STAT_BREAKDOWNS}
    combined = []
    for key in selected:
        label, source = metadata[key]
        for row in values.get(source, []):
            combined.append({
                'dimension_key': key,
                'dimension_label': label,
                'label': row.get('label') or MISSING_LABEL,
                'total': _number(row.get('total')),
                'active_count': _number(row.get('active_count')),
                'graduate_count': _number(row.get('graduate_count')),
                'dropout_count': _number(row.get('dropout_count')),
                'share': row.get('share', 0),
            })
    return combined


def _date_filters():
    raw_from = request.args.get('date_from', '').strip()
    raw_to = request.args.get('date_to', '').strip()
    date_from = ''
    date_to = ''
    error = ''
    try:
        date_from = normalize_jalali_date(raw_from) if raw_from else ''
        date_to = normalize_jalali_date(raw_to) if raw_to else ''
        if date_from and date_to and date_from > date_to:
            raise ValueError('تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد.')
    except ValueError as exc:
        error = str(exc)
        date_from = ''
        date_to = ''
    return raw_from, raw_to, date_from, date_to, error


def _gender_expr(alias: str = 's') -> str:
    value = f"TRIM(COALESCE({alias}.gender, ''))"
    return f'''CASE
        WHEN {value} IN ('پسر', 'مذکر', 'مرد', 'male', 'Male', 'MALE', 'm', 'M', '1', '۱') THEN 'پسر'
        WHEN {value} IN ('دختر', 'مونث', 'مؤنث', 'زن', 'female', 'Female', 'FEMALE', 'f', 'F', '0', '۰') THEN 'دختر'
        ELSE '{MISSING_LABEL}'
    END'''


def _text_expr(column: str, alias: str = 's') -> str:
    # column is selected only from fixed internal values below; it is never user input.
    return f"COALESCE(NULLIF(TRIM({alias}.{column}), ''), '{MISSING_LABEL}')"


def _missing_condition(column: str, alias: str = 's') -> str:
    return f"TRIM(COALESCE({alias}.{column}, '')) = ''"


def _teacher_unassigned_condition(alias: str = 's') -> str:
    return f"(TRIM(COALESCE({alias}.teacher_code, '')) = '' OR NOT EXISTS (SELECT 1 FROM teachers t0 WHERE TRIM(t0.code) = TRIM({alias}.teacher_code)))"


def _add_value_filter(conditions, params, column: str, value: str):
    if not value:
        return
    if value == MISSING_LABEL:
        conditions.append(_missing_condition(column))
    else:
        conditions.append(f'TRIM(COALESCE(s.{column}, \'\')) = ?')
        params.append(value)


def _student_filters(grade: str, class_name: str, sida_class: str, gender: str, teacher_code: str):
    conditions = ['1=1']
    params = []
    _add_value_filter(conditions, params, 'grade', grade)
    _add_value_filter(conditions, params, 'class_name', class_name)
    _add_value_filter(conditions, params, 'sida_class', sida_class)
    if gender:
        conditions.append(f'{_gender_expr()} = ?')
        params.append(gender)
    if teacher_code == UNASSIGNED_TEACHER:
        conditions.append(_teacher_unassigned_condition())
    elif teacher_code:
        conditions.append("TRIM(COALESCE(s.teacher_code, '')) = ?")
        params.append(teacher_code)
    return conditions, params


def _attendance_conditions(student_conditions, student_params, date_from, date_to):
    conditions = list(student_conditions)
    params = list(student_params)
    if date_from:
        conditions.append('a.date >= ?')
        params.append(date_from)
    if date_to:
        conditions.append('a.date <= ?')
        params.append(date_to)
    return conditions, params


def _breakdown(conn, expression: str, conditions, params, denominator: int):
    rows = _dict_rows(conn.execute(
        f'''SELECT {expression} AS label,
                   {_status_select('s')}
            FROM students s
            WHERE {' AND '.join(conditions)}
            GROUP BY {expression}
            ORDER BY total DESC, label''',
        params,
    ).fetchall())
    for row in rows:
        row['total'] = _number(row.get('total'))
        for key in ('active_count', 'graduate_count', 'dropout_count', 'other_count'):
            row[key] = _number(row.get(key))
        row['share'] = _percent(row['total'], denominator)
    return rows


def _option_values(conn, column: str):
    values = [row['value'] for row in conn.execute(
        f"SELECT DISTINCT TRIM({column}) AS value FROM students WHERE TRIM(COALESCE({column}, '')) <> '' ORDER BY value"
    ).fetchall()]
    missing = conn.execute(
        f"SELECT 1 FROM students s WHERE {_missing_condition(column)} LIMIT 1"
    ).fetchone()
    if missing:
        values.append(MISSING_LABEL)
    return values


def _gender_values(conn):
    values = [row['value'] for row in conn.execute(
        f'''SELECT DISTINCT {_gender_expr()} AS value
            FROM students s
            ORDER BY CASE value WHEN 'پسر' THEN 1 WHEN 'دختر' THEN 2 ELSE 3 END, value'''
    ).fetchall()]
    return values or [MISSING_LABEL]


def _teacher_filter_label(teachers_list, teacher_code):
    if teacher_code == UNASSIGNED_TEACHER:
        return 'بدون معلم یا کد نامعتبر'
    for teacher in teachers_list:
        if teacher['code'] == teacher_code:
            return f"{teacher['first_name']} {teacher['last_name']}".strip()
    return teacher_code


def statistics_dashboard():
    raw_date_from, raw_date_to, date_from, date_to, date_error = _date_filters()
    grade = request.args.get('grade', '').strip()
    class_name = request.args.get('class_name', '').strip()
    sida_class = request.args.get('sida_class', '').strip()
    gender = request.args.get('gender', '').strip()
    teacher_code = request.args.get('teacher_code', '').strip()
    status_filter = request.args.get('status', 'all').strip().lower() or 'all'
    if status_filter not in STATUS_LABELS:
        status_filter = 'all'

    student_conditions, student_params = _student_filters(
        grade, class_name, sida_class, gender, teacher_code
    )
    selected_student_conditions = student_conditions + [_status_sql(status_filter)]
    selected_student_params = list(student_params)

    with get_db() as conn:
        total_row = conn.execute(
            f'''SELECT COUNT(*) AS total_students,
                       SUM(CASE WHEN {_status_sql('active')} THEN 1 ELSE 0 END) AS active,
                       SUM(CASE WHEN {_status_sql('graduate')} THEN 1 ELSE 0 END) AS graduate,
                       SUM(CASE WHEN {_status_sql('dropout')} THEN 1 ELSE 0 END) AS dropout,
                       SUM(CASE WHEN {_status_sql('other')} THEN 1 ELSE 0 END) AS other
                FROM students s
                WHERE {' AND '.join(student_conditions)}''',
            student_params,
        ).fetchone()
        total_stats = {key: _number(total_row[key]) for key in ('total_students', 'active', 'graduate', 'dropout', 'other')}

        selected_count_row = conn.execute(
            f'''SELECT COUNT(*) AS count FROM students s
                WHERE {' AND '.join(selected_student_conditions)}''',
            selected_student_params,
        ).fetchone()
        selected_count = _number(selected_count_row['count'])

        teachers_list = _dict_rows(conn.execute(
            '''SELECT code, first_name, last_name
               FROM teachers
               WHERE code IS NOT NULL AND TRIM(code) <> ''
               ORDER BY first_name, last_name'''
        ).fetchall())
        unassigned_count = _number(conn.execute(
            f'SELECT COUNT(*) AS count FROM students s WHERE {_teacher_unassigned_condition()}'
        ).fetchone()['count'])
        if unassigned_count:
            teachers_list.append({
                'code': UNASSIGNED_TEACHER,
                'first_name': 'بدون معلم',
                'last_name': 'یا کد نامعتبر',
                'is_unassigned': True,
            })

        grade_list = _option_values(conn, 'grade')
        class_list = _option_values(conn, 'class_name')
        sida_list = _option_values(conn, 'sida_class')
        gender_list = _gender_values(conn)

        attendance_conditions, attendance_params = _attendance_conditions(
            selected_student_conditions, selected_student_params, date_from, date_to
        )
        attendance_where = ' AND '.join(attendance_conditions)
        attendance_row = conn.execute(
            f'''SELECT COUNT(a.id) AS total_records,
                       SUM(CASE WHEN a.status = 'حاضر' THEN 1 ELSE 0 END) AS present,
                       SUM(CASE WHEN a.status = 'غایب' THEN 1 ELSE 0 END) AS absent,
                       SUM(CASE WHEN a.status = 'تاخیر' THEN 1 ELSE 0 END) AS late
                FROM attendance_students a
                JOIN students s ON s.code = a.student_code
                WHERE {attendance_where}''',
            attendance_params,
        ).fetchone()
        attendance_stats = {key: _number(attendance_row[key]) for key in ('total_records', 'present', 'absent', 'late')}
        attendance_stats['attended'] = attendance_stats['present'] + attendance_stats['late']
        attendance_stats['attendance_rate'] = _percent(attendance_stats['attended'], attendance_stats['total_records'])
        attendance_stats['absence_rate'] = _percent(attendance_stats['absent'], attendance_stats['total_records'])

        absent_students_row = conn.execute(
            f'''SELECT COUNT(*) AS count FROM (
                    SELECT a.student_code
                    FROM attendance_students a
                    JOIN students s ON s.code = a.student_code
                    WHERE {attendance_where} AND a.status = 'غایب'
                    GROUP BY a.student_code
                )''',
            attendance_params,
        ).fetchone()
        at_risk_row = conn.execute(
            f'''SELECT COUNT(*) AS count FROM (
                    SELECT a.student_code
                    FROM attendance_students a
                    JOIN students s ON s.code = a.student_code
                    WHERE {attendance_where} AND a.status = 'غایب'
                    GROUP BY a.student_code
                    HAVING COUNT(*) >= 3
                )''',
            attendance_params,
        ).fetchone()
        attendance_stats['absent_students'] = _number(absent_students_row['count'])
        attendance_stats['at_risk_students'] = _number(at_risk_row['count'])

        teacher_attendance_conditions = ['1=1']
        teacher_attendance_params = []
        if teacher_code == UNASSIGNED_TEACHER:
            teacher_attendance_conditions.append(
                "(TRIM(COALESCE(a.teacher_code, '')) = '' OR NOT EXISTS (SELECT 1 FROM teachers t0 WHERE TRIM(t0.code) = TRIM(a.teacher_code)))"
            )
        elif teacher_code:
            teacher_attendance_conditions.append('TRIM(COALESCE(a.teacher_code, \'\')) = ?')
            teacher_attendance_params.append(teacher_code)
        if date_from:
            teacher_attendance_conditions.append('a.date >= ?')
            teacher_attendance_params.append(date_from)
        if date_to:
            teacher_attendance_conditions.append('a.date <= ?')
            teacher_attendance_params.append(date_to)
        teacher_attendance_where = ' AND '.join(teacher_attendance_conditions)
        teacher_attendance_row = conn.execute(
            f'''SELECT COUNT(a.id) AS total_records,
                       SUM(CASE WHEN a.status = 'حاضر' THEN 1 ELSE 0 END) AS present,
                       SUM(CASE WHEN a.status = 'غایب' THEN 1 ELSE 0 END) AS absent,
                       SUM(CASE WHEN a.status = 'تاخیر' THEN 1 ELSE 0 END) AS late,
                       COALESCE(SUM(CASE WHEN a.status = 'تاخیر' THEN a.late_duration ELSE 0 END), 0) AS late_minutes
                FROM attendance_teachers a
                WHERE {teacher_attendance_where}''',
            teacher_attendance_params,
        ).fetchone()
        teacher_attendance_stats = {key: _number(teacher_attendance_row[key]) for key in ('total_records', 'present', 'absent', 'late', 'late_minutes')}
        teacher_attendance_stats['attended'] = teacher_attendance_stats['present'] + teacher_attendance_stats['late']
        teacher_attendance_stats['attendance_rate'] = _percent(teacher_attendance_stats['attended'], teacher_attendance_stats['total_records'])

        teacher_code_expr = f"CASE WHEN {_teacher_unassigned_condition()} THEN '{UNASSIGNED_TEACHER}' ELSE TRIM(s.teacher_code) END"
        teacher_name_expr = f'''CASE
            WHEN TRIM(COALESCE(s.teacher_code, '')) = '' THEN 'بدون معلم'
            WHEN t.code IS NULL THEN 'کد معلم نامعتبر'
            ELSE TRIM(COALESCE(t.first_name, '') || ' ' || COALESCE(t.last_name, ''))
        END'''
        teacher_stats = _dict_rows(conn.execute(
            f'''SELECT {teacher_code_expr} AS code,
                       {teacher_name_expr} AS teacher_name,
                       {_status_select('s')}
                FROM students s
                LEFT JOIN teachers t ON TRIM(t.code) = TRIM(s.teacher_code)
                WHERE {' AND '.join(selected_student_conditions)}
                GROUP BY {teacher_code_expr}, {teacher_name_expr}
                ORDER BY total DESC, teacher_name''',
            selected_student_params,
        ).fetchall())
        for row in teacher_stats:
            row['total'] = _number(row.get('total'))
            for key in ('active_count', 'graduate_count', 'dropout_count', 'other_count'):
                row[key] = _number(row.get(key))
            row['share'] = _percent(row['total'], selected_count)

        teacher_absence_rows = conn.execute(
            f'''SELECT {teacher_code_expr} AS code, COUNT(a.id) AS absent_count
                FROM attendance_students a
                JOIN students s ON s.code = a.student_code
                LEFT JOIN teachers t ON TRIM(t.code) = TRIM(s.teacher_code)
                WHERE {attendance_where} AND a.status = 'غایب'
                GROUP BY {teacher_code_expr}''',
            attendance_params,
        ).fetchall()
        absence_by_teacher = {row['code']: _number(row['absent_count']) for row in teacher_absence_rows}
        for row in teacher_stats:
            row['absent_count'] = absence_by_teacher.get(row['code'], 0)

        gender_stats = _breakdown(conn, _gender_expr(), selected_student_conditions, selected_student_params, selected_count)
        sida_stats = _breakdown(conn, _text_expr('sida_class'), selected_student_conditions, selected_student_params, selected_count)
        class_stats = _breakdown(conn, _text_expr('class_name'), selected_student_conditions, selected_student_params, selected_count)
        grade_stats = _breakdown(conn, _text_expr('grade'), selected_student_conditions, selected_student_params, selected_count)

        trend_rows = _dict_rows(conn.execute(
            f'''SELECT a.date AS label,
                       COUNT(*) AS total,
                       SUM(CASE WHEN a.status = 'غایب' THEN 1 ELSE 0 END) AS absent,
                       SUM(CASE WHEN a.status = 'تاخیر' THEN 1 ELSE 0 END) AS late
                FROM attendance_students a
                JOIN students s ON s.code = a.student_code
                WHERE {attendance_where}
                GROUP BY a.date
                ORDER BY a.date DESC
                LIMIT 30''',
            attendance_params,
        ).fetchall())
        trend_data = list(reversed(trend_rows))

        absentee_students = _dict_rows(conn.execute(
            f'''SELECT s.first_name, s.last_name, s.code, s.grade, s.class_name,
                       COUNT(a.id) AS absent_count
                FROM attendance_students a
                JOIN students s ON s.code = a.student_code
                WHERE {attendance_where} AND a.status = 'غایب'
                GROUP BY s.code
                ORDER BY absent_count DESC, s.first_name, s.last_name
                LIMIT 10''',
            attendance_params,
        ).fetchall())

        quality_row = conn.execute(
            f'''SELECT
                    SUM(CASE WHEN TRIM(COALESCE(s.gender, '')) = '' THEN 1 ELSE 0 END) AS missing_gender,
                    SUM(CASE WHEN TRIM(COALESCE(s.sida_class, '')) = '' THEN 1 ELSE 0 END) AS missing_sida,
                    SUM(CASE WHEN TRIM(COALESCE(s.class_name, '')) = '' THEN 1 ELSE 0 END) AS missing_class,
                    SUM(CASE WHEN {_teacher_unassigned_condition()} THEN 1 ELSE 0 END) AS unassigned_teacher
                FROM students s
                WHERE {' AND '.join(selected_student_conditions)}''',
            selected_student_params,
        ).fetchone()
        data_quality = {key: _number(quality_row[key]) for key in ('missing_gender', 'missing_sida', 'missing_class', 'unassigned_teacher')}

        service_stats = {'records': 0, 'billed': 0, 'paid': 0, 'outstanding': 0}
        service_columns = {row['name'] for row in conn.execute('PRAGMA table_info(monthly_service)').fetchall()}
        if service_columns:
            paid_column = 'paid_amount' if 'paid_amount' in service_columns else ('paid' if 'paid' in service_columns else None)
            if 'amount' in service_columns and paid_column:
                service_row = conn.execute(
                    f'''SELECT COUNT(ms.id) AS records,
                               COALESCE(SUM(ms.amount), 0) AS billed,
                               COALESCE(SUM({paid_column}), 0) AS paid
                        FROM monthly_service ms
                        JOIN students s ON s.code = ms.student_code
                        WHERE {' AND '.join(selected_student_conditions)}''',
                    selected_student_params,
                ).fetchone()
                service_stats['records'] = _number(service_row['records'])
                service_stats['billed'] = _number(service_row['billed'])
                service_stats['paid'] = _number(service_row['paid'])
                service_stats['outstanding'] = max(0, service_stats['billed'] - service_stats['paid'])
        school_statistics_layout = load_report_layout(conn, 'school_statistics', session.get('user_id'))

    print_breakdown_raw = request.args.get('print_breakdowns')
    print_breakdown_mode = print_breakdown_raw is not None
    selected_breakdowns = _parse_print_breakdowns(print_breakdown_raw) if print_breakdown_mode else ()
    breakdown_values = {
        'teacher_stats': teacher_stats,
        'gender_stats': gender_stats,
        'grade_stats': grade_stats,
        'class_stats': class_stats,
        'sida_stats': sida_stats,
    }
    combined_breakdown_rows = _combined_breakdown_rows(selected_breakdowns, breakdown_values)

    filter_active_count = sum(bool(value) for value in (
        raw_date_from, raw_date_to, grade, class_name, sida_class, gender, teacher_code, status_filter != 'all'
    ))
    scope_label = 'کل دانش‌آموزان'
    if status_filter != 'all':
        scope_label = STATUS_LABELS[status_filter]
    for label, value in (
        ('پایه', grade), ('کلاس', class_name), ('کلاس سیدا', sida_class), ('جنسیت', gender)
    ):
        if value:
            scope_label += f' | {label}: {value}'
    if teacher_code:
        scope_label += f' | معلم: {_teacher_filter_label(teachers_list, teacher_code)}'

    return render_template(
        'statistics.html',
        total_stats=total_stats,
        selected_count=selected_count,
        attendance_stats=attendance_stats,
        teacher_attendance_stats=teacher_attendance_stats,
        teacher_stats=teacher_stats,
        gender_stats=gender_stats,
        sida_stats=sida_stats,
        class_stats=class_stats,
        grade_stats=grade_stats,
        trend_data=trend_data,
        absentee_students=absentee_students,
        service_stats=service_stats,
        data_quality=data_quality,
        teachers_list=teachers_list,
        grade_list=grade_list,
        class_list=class_list,
        sida_list=sida_list,
        gender_list=gender_list,
        date_from=raw_date_from,
        date_to=raw_date_to,
        grade=grade,
        class_name=class_name,
        sida_class=sida_class,
        gender=gender,
        teacher_code=teacher_code,
        status_filter=status_filter,
        status_options=STATUS_LABELS,
        filter_active_count=filter_active_count,
        scope_label=scope_label,
        date_error=date_error,
        missing_label=MISSING_LABEL,
        unassigned_teacher_value=UNASSIGNED_TEACHER,
        current_role=session.get('role'),
        school_statistics_layout=school_statistics_layout,
        stat_breakdown_options=[{'key': key, 'label': label} for key, label, _ in STAT_BREAKDOWNS],
        selected_breakdowns=selected_breakdowns,
        combined_breakdown_rows=combined_breakdown_rows,
        print_breakdown_mode=print_breakdown_mode,
        auto_print=request.args.get('autoprint') == '1',
    )
