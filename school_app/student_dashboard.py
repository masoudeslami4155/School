from __future__ import annotations

from flask import request, session
from datetime import datetime, timedelta

from .database import get_db
from .dates import get_today_jalali
from .security import teacher_scope


_SAFE_SEARCH_FIELDS = (
    's.first_name',
    's.last_name',
    's.code',
    's.grade',
    's.class_name',
    's.sida_class',
    's.gender',
)
_FILTER_FIELDS = {
    'grade': 's.grade',
    'class_name': 's.class_name',
    'sida_class': 's.sida_class',
    'gender': 's.gender',
}

# شیوهٔ نمایش فهرست دانش‌آموزان: از خلاصهٔ نام و کد تا اطلاعات کامل.
STUDENT_VIEWS = {
    'xs': 'نام و کد',
    'sm': 'خلاصه',
    'md': 'استاندارد',
    'lg': 'درشت',
    'xl': 'خیلی درشت',
    'table': 'جدول کامل',
}
DEFAULT_STUDENT_VIEW = 'md'
STUDENT_VIEW_SETTING = 'student_card_view:'


def normalise_student_view(value: object) -> str:
    """Keep known view keys; fall back to the standard information level."""
    text = str(value or '').strip()
    return text if text in STUDENT_VIEWS else DEFAULT_STUDENT_VIEW


def load_student_view(conn, user_id: object) -> str:
    row = conn.execute('SELECT value FROM app_settings WHERE key=?',
                       (f'{STUDENT_VIEW_SETTING}{user_id}',)).fetchone()
    if not row:
        return DEFAULT_STUDENT_VIEW
    return normalise_student_view(row['value'])


def save_student_view(conn, user_id: object, value: object) -> str:
    """Persist the chosen view for this user and return the normalised key."""
    chosen = normalise_student_view(value)
    conn.execute(
        'INSERT INTO app_settings(key,value) VALUES(?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (f'{STUDENT_VIEW_SETTING}{user_id}', chosen),
    )
    return chosen

STUDENT_FILTER_REFERENCE = [
    {
        'key': 'q', 'label': 'جست‌وجوی فهرست', 'type': 'متن آزاد',
        'behavior': 'تا ۱۰۰ حرف؛ بخشی از نام، نام خانوادگی، کد، پایه، کلاس مدرسه، کلاس سیدا یا جنسیت؛ تطبیق در هرکدام کافی است.',
        'availability': 'همهٔ نقش‌ها',
    },
    {
        'key': 'grade', 'label': 'پایه', 'type': 'انتخاب دقیق',
        'behavior': 'انتخاب یک پایه؛ «ثبت نشده» موارد خالی را پیدا می‌کند.',
        'availability': 'همهٔ نقش‌ها',
    },
    {
        'key': 'class_name', 'label': 'کلاس مدرسه', 'type': 'انتخاب دقیق',
        'behavior': 'انتخاب یک کلاس مدرسه؛ «ثبت نشده» موارد خالی را پیدا می‌کند.',
        'availability': 'همهٔ نقش‌ها',
    },
    {
        'key': 'sida_class', 'label': 'کلاس سیدا', 'type': 'انتخاب دقیق',
        'behavior': 'انتخاب یک کلاس سیدا؛ «ثبت نشده» موارد خالی را پیدا می‌کند.',
        'availability': 'همهٔ نقش‌ها',
    },
    {
        'key': 'gender', 'label': 'جنسیت', 'type': 'انتخاب دقیق',
        'behavior': 'انتخاب یک مقدار ثبت‌شده؛ «ثبت نشده» موارد خالی را پیدا می‌کند.',
        'availability': 'همهٔ نقش‌ها',
    },
    {
        'key': 'teacher_code', 'label': 'معلم', 'type': 'انتخاب دقیق',
        'behavior': 'کد معلم؛ «ثبت نشده» شامل کد خالی یا معلم نامعتبر است.',
        'availability': 'مدیر و معاون؛ معلم فقط دانش‌آموزان منتسب به خودش را می‌بیند.',
    },
    {
        'key': 'quickStudentSearch', 'label': 'جست‌وجوی سریع روی کارت‌ها', 'type': 'متن آزاد',
        'behavior': 'فقط کارت‌های از قبل بارگذاری‌شده را پنهان/نمایش می‌دهد؛ روی چاپ و خروجی‌ها اثر ندارد.',
        'availability': 'همهٔ نقش‌ها',
    },
]


def _value(value: str | None, limit: int = 80) -> str:
    return (value or '').strip()[:limit]


def _missing_sql(column: str) -> str:
    return f"NULLIF(TRIM(COALESCE({column}, '')), '') IS NULL"


def _unassigned_teacher_sql() -> str:
    return (
        f"({_missing_sql('s.teacher_code')} OR NOT EXISTS ("
        "SELECT 1 FROM teachers teacher_match WHERE teacher_match.code = s.teacher_code))"
    )


def _option_rows(conn, column: str, where_sql: str, params: list[object]) -> list[dict[str, str]]:
    rows = conn.execute(
        f"""
        SELECT DISTINCT TRIM(COALESCE({column}, '')) AS value
        FROM students s
        WHERE {where_sql}
        ORDER BY CASE WHEN value = '' THEN 1 ELSE 0 END, value COLLATE NOCASE
        """,
        params,
    ).fetchall()
    options = []
    for row in rows:
        value = row['value'] or ''
        options.append({
            'value': '__empty__' if not value else value,
            'label': 'ثبت نشده' if not value else value,
        })
    return options


def _scope_where(scope: str | None) -> tuple[list[str], list[object]]:
    clauses = ["(s.status = 'فعال' OR s.status IS NULL)"]
    params: list[object] = []
    if scope:
        clauses.append('s.teacher_code = ?')
        params.append(scope)
    return clauses, params


def _apply_filters(clauses: list[str], params: list[object], filters: dict[str, str], scope: str | None) -> None:
    query = filters['q']
    if query:
        like = f'%{query}%'
        clauses.append('(' + ' OR '.join(f"COALESCE({field}, '') LIKE ?" for field in _SAFE_SEARCH_FIELDS) + ')')
        params.extend([like] * len(_SAFE_SEARCH_FIELDS))

    for key, column in _FILTER_FIELDS.items():
        selected = filters[key]
        if not selected:
            continue
        if selected == '__empty__':
            clauses.append(_missing_sql(column))
            continue
        clauses.append(f'{column} = ?')
        params.append(selected)

    # A teacher is always constrained to their own personnel number, regardless
    # of what a forged teacher_code parameter might contain.
    if not scope and filters['teacher_code']:
        if filters['teacher_code'] == '__empty__':
            clauses.append(_unassigned_teacher_sql())
        else:
            clauses.append('s.teacher_code = ?')
            params.append(filters['teacher_code'])


def _selected_filters() -> dict[str, str]:
    return {
        'q': _value(request.args.get('q'), 100),
        'grade': _value(request.args.get('grade')),
        'class_name': _value(request.args.get('class_name')),
        'sida_class': _value(request.args.get('sida_class')),
        'gender': _value(request.args.get('gender')),
        'teacher_code': _value(request.args.get('teacher_code')),
    }


def build_dashboard_context() -> dict[str, object]:
    role = session.get('role')
    user_id = session.get('user_id')
    scope = teacher_scope()
    filters = _selected_filters()
    base_clauses, base_params = _scope_where(scope)
    base_sql = ' AND '.join(base_clauses)
    list_clauses = list(base_clauses)
    list_params = list(base_params)
    _apply_filters(list_clauses, list_params, filters, scope)
    list_sql = ' AND '.join(list_clauses)

    year, month, day = get_today_jalali()
    today = f'{year:04d}/{month:02d}/{day:02d}'

    with get_db() as conn:
        student_view = load_student_view(conn, user_id)
        students = conn.execute(
            f"""
            SELECT
                s.id, s.first_name, s.last_name, s.code, s.birth_date,
                s.grade, s.class_name, s.sida_class, s.gender,
                s.photo, s.teacher_code,
                t.first_name AS teacher_first, t.last_name AS teacher_last
            FROM students s
            LEFT JOIN teachers t ON s.teacher_code = t.code
            WHERE {list_sql}
            ORDER BY s.id DESC
            """,
            list_params,
        ).fetchall()

        total_row = conn.execute(
            f'SELECT COUNT(*) AS count FROM students s WHERE {base_sql}',
            base_params,
        ).fetchone()
        class_row = conn.execute(
            f"SELECT COUNT(DISTINCT NULLIF(TRIM(COALESCE(s.class_name, '')), '')) AS count FROM students s WHERE {base_sql}",
            base_params,
        ).fetchone()
        teacher_row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT t.code) AS count
            FROM students s
            LEFT JOIN teachers t ON t.code = s.teacher_code
            WHERE {base_sql}
            """,
            base_params,
        ).fetchone()
        missing_row = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN {_missing_sql('s.gender')} THEN 1 ELSE 0 END) AS gender_missing,
                SUM(CASE WHEN {_missing_sql('s.sida_class')} THEN 1 ELSE 0 END) AS sida_missing,
                SUM(CASE WHEN {_missing_sql('s.class_name')} THEN 1 ELSE 0 END) AS class_missing,
                SUM(CASE WHEN {_unassigned_teacher_sql()} THEN 1 ELSE 0 END) AS teacher_missing,
                SUM(CASE WHEN (
                    {_missing_sql('s.gender')} OR
                    {_missing_sql('s.sida_class')} OR
                    {_missing_sql('s.class_name')} OR
                    {_unassigned_teacher_sql()}
                ) THEN 1 ELSE 0 END) AS incomplete_students
            FROM students s
            WHERE {base_sql}
            """,
            base_params,
        ).fetchone()
        attendance_row = conn.execute(
            f"""
            SELECT
                COUNT(a.id) AS marked,
                SUM(CASE WHEN a.status = 'حاضر' THEN 1 ELSE 0 END) AS present,
                SUM(CASE WHEN a.status = 'غایب' THEN 1 ELSE 0 END) AS absent,
                SUM(CASE WHEN a.status NOT IN ('حاضر', 'غایب') THEN 1 ELSE 0 END) AS other
            FROM students s
            LEFT JOIN attendance_students a
              ON a.student_code = s.code AND a.date = ?
            WHERE {base_sql}
            """,
            [today] + base_params,
        ).fetchone()

        filter_options = {
            'grades': _option_rows(conn, 's.grade', base_sql, base_params),
            'classes': _option_rows(conn, 's.class_name', base_sql, base_params),
            'sida_classes': _option_rows(conn, 's.sida_class', base_sql, base_params),
            'genders': _option_rows(conn, 's.gender', base_sql, base_params),
        }
        if role == 'teacher':
            teacher_options = []
        else:
            teacher_rows = conn.execute(
                """
                SELECT t.code, TRIM(COALESCE(t.first_name, '') || ' ' || COALESCE(t.last_name, '')) AS name
                FROM teachers t
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
            teacher_options = [
                {'value': row['code'], 'label': row['name'] or row['code']}
                for row in teacher_rows
                if row['code']
            ]
            if (missing_row['teacher_missing'] or 0) > 0:
                teacher_options.append({'value': '__empty__', 'label': 'ثبت نشده'})
        filter_options['teachers'] = teacher_options

    total_active = total_row['count'] or 0
    incomplete_students = missing_row['incomplete_students'] or 0
    attendance_marked = attendance_row['marked'] or 0
    attendance_present = attendance_row['present'] or 0
    attendance_absent = attendance_row['absent'] or 0
    attendance_other = attendance_row['other'] or 0
    attendance_rate = round((attendance_present / attendance_marked) * 100) if attendance_marked else None

    return {
        'students': students,
        'reminders': _reminders(),
        'event_alerts': _event_alerts(),
        'task_alerts': _task_alerts(),
        'summary': {
            'total_active': total_active,
            'filtered_count': len(students),
            'class_count': class_row['count'] or 0,
            'teacher_count': teacher_row['count'] or 0,
            'incomplete_students': incomplete_students,
            'gender_missing': missing_row['gender_missing'] or 0,
            'sida_missing': missing_row['sida_missing'] or 0,
            'class_missing': missing_row['class_missing'] or 0,
            'teacher_missing': missing_row['teacher_missing'] or 0,
            'attendance_marked': attendance_marked,
            'attendance_present': attendance_present,
            'attendance_absent': attendance_absent,
            'attendance_other': attendance_other,
            'attendance_rate': attendance_rate,
        },
        'filter_options': filter_options,
        'selected_filters': filters,
        'student_view': student_view,
        'student_view_labels': STUDENT_VIEWS,
        'today_jalali': today,
        'scope_label': 'فقط دانش‌آموزان منتسب به شما' if role == 'teacher' else 'کل دانش‌آموزان فعال مدرسه',
        'filters_applied': any(filters.values()),
    }


def _reminders() -> list[dict[str, object]]:
    # Kept as a separate query helper so the dashboard route stays focused on
    # permissions and filtering. The date strings match the calendar module.
    year, month, day = get_today_jalali()
    today = f'{year:04d}/{month:02d}/{day:02d}'
    from datetime import date, timedelta
    from .dates import gregorian_to_jalali

    tomorrow = date.today() + timedelta(days=1)
    ty, tm, td = gregorian_to_jalali(tomorrow.year, tomorrow.month, tomorrow.day)
    tomorrow_string = f'{ty:04d}/{tm:02d}/{td:02d}'
    with get_db() as conn:
        rows = conn.execute(
            'SELECT title, date, type FROM events WHERE date = ? OR date = ? ORDER BY date, id',
            (today, tomorrow_string),
        ).fetchall()
    return [dict(row) for row in rows]


def _event_alerts() -> list[dict[str, object]]:
    """Return upcoming events for the dashboard's inline reminder section."""
    from .dates import jalali_to_gregorian, get_today_jalali, gregorian_to_jalali
    now = datetime.now()
    today = get_today_jalali()
    end_date = now.date() + timedelta(days=7)
    ey, em, ed = gregorian_to_jalali(end_date.year, end_date.month, end_date.day)
    start = f'{today[0]:04d}/{today[1]:02d}/{today[2]:02d}'
    end = f'{ey:04d}/{em:02d}/{ed:02d}'
    with get_db() as conn:
        rows = conn.execute(
            'SELECT id,title,date,time,type,priority,description FROM events WHERE date>=? AND date<=? ORDER BY date,time,id',
            (start, end),
        ).fetchall()
    result = []
    for row in rows:
        try:
            jy, jm, jd = (int(x) for x in row['date'].split('/'))
            gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
            clock = (row['time'] or '00:00').strip()
            hh, mm = (int(x) for x in clock.replace('：', ':').split(':')[:2])
            target = datetime(gy, gm, gd, hh, mm)
        except (ValueError, TypeError, IndexError):
            continue
        item = dict(row)
        item['target_iso'] = target.strftime('%Y-%m-%dT%H:%M:%S')
        item['urgent'] = (row['priority'] or 'عادی') == 'فوری'
        item['important'] = (row['priority'] or 'عادی') in ('فوری', 'مهم')
        item['time_label'] = row['time'] or 'بدون ساعت'
        result.append(item)
    return result


def _task_alerts() -> list[dict[str, object]]:
    """Open tasks with due dates in the next week (and overdue) for dashboard alarms."""
    from .dates import jalali_to_gregorian, get_today_jalali, gregorian_to_jalali

    now = datetime.now()
    today = get_today_jalali()
    start = f'{today[0]:04d}/{today[1]:02d}/{today[2]:02d}'
    end_date = now.date() + timedelta(days=7)
    ey, em, ed = gregorian_to_jalali(end_date.year, end_date.month, end_date.day)
    end = f'{ey:04d}/{em:02d}/{ed:02d}'
    with get_db() as conn:
        try:
            rows = conn.execute(
                '''SELECT id,title,due_date,due_time,priority,status,alarm_enabled,alarm_minutes,category,description
                   FROM tasks
                   WHERE status NOT IN ('انجام‌شده','لغو‌شده')
                     AND due_date <= ?
                   ORDER BY due_date, due_time, id''',
                (end,),
            ).fetchall()
        except Exception:
            return []
    result = []
    for row in rows:
        try:
            jy, jm, jd = (int(x) for x in row['due_date'].split('/'))
            gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
            clock = (row['due_time'] or '00:00').strip().replace('：', ':')
            parts = clock.split(':')
            hh = int(parts[0]) if parts and parts[0] != '' else 0
            mm = int(parts[1]) if len(parts) > 1 and parts[1] != '' else 0
            due_at = datetime(gy, gm, gd, hh, mm)
        except (ValueError, TypeError, IndexError, AttributeError):
            continue
        alarm_minutes = int(row['alarm_minutes'] or 0) if row['alarm_enabled'] else 0
        alarm_enabled = int(row['alarm_enabled'] or 0) == 1
        alarm_at = due_at - timedelta(minutes=alarm_minutes) if alarm_enabled else due_at
        item = dict(row)
        item['target_iso'] = due_at.strftime('%Y-%m-%dT%H:%M:%S')
        item['alarm_at_iso'] = alarm_at.strftime('%Y-%m-%dT%H:%M:%S') if alarm_enabled else ''
        item['urgent'] = (row['priority'] or 'عادی') == 'فوری' or (row['due_date'] or '') < start
        item['important'] = item['urgent'] or (row['priority'] or 'عادی') in ('فوری', 'مهم')
        item['time_label'] = row['due_time'] or 'بدون ساعت'
        item['date'] = row['due_date']
        item['kind'] = 'task'
        result.append(item)
    return result
