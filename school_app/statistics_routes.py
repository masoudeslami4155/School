from __future__ import annotations

from flask import render_template, request, session, abort, url_for, send_file, jsonify, current_app, after_this_request

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
    conditions.append(f'{_text_expr(column)} = ?')
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
            name=f"{teacher.get('first_name') or ''} {teacher.get('last_name') or ''}".strip() or 'معلم بدون نام'
            return f'{name} ({teacher_code})'
    return teacher_code


FREQUENCY_COLUMNS = (
    ('teacher', 'معلم'),
    ('grade', 'پایه'),
    ('boys', 'پسر'),
    ('girls', 'دختر'),
    ('missing', 'ثبت نشده'),
    ('total', 'جمع'),
    ('share', 'سهم'),
)

FREQUENCY_COLUMN_KEYS = tuple(key for key, _ in FREQUENCY_COLUMNS)

_GRADE_ORDER = (
    'پیش‌دبستانی', 'پیش دبستانی', 'آمادگی', 'آمادگی مقدماتی', 'آمادگی تکمیلی',
    'پایه اول', 'اول', 'پایه دوم', 'دوم', 'پایه سوم', 'سوم',
    'پایه چهارم', 'چهارم', 'پایه پنجم', 'پنجم', 'پایه ششم', 'ششم',
)


def _grade_rank(label: str) -> int:
    """Exact matches precede substrings; specific preparation grades stay ordered."""
    text = (label or '').strip()
    if text in _GRADE_ORDER:
        return _GRADE_ORDER.index(text)
    matches = [(len(name), i) for i, name in enumerate(_GRADE_ORDER) if name in text]
    return max(matches)[1] if matches else len(_GRADE_ORDER)


def _teacher_key_expr():
    return f"CASE WHEN {_teacher_unassigned_condition()} THEN '{UNASSIGNED_TEACHER}' ELSE TRIM(s.teacher_code) END"


def _teacher_name_expr():
    # Correlated lookup cannot multiply students if legacy teacher codes differ in whitespace.
    return f"""CASE WHEN {_teacher_unassigned_condition()} THEN 'بدون معلم یا کد نامعتبر'
        ELSE COALESCE((SELECT NULLIF(TRIM(COALESCE(t.first_name,'') || ' ' || COALESCE(t.last_name,'')),'')
             FROM teachers t WHERE TRIM(t.code)=TRIM(s.teacher_code) ORDER BY t.id LIMIT 1), 'معلم بدون نام') END"""


def _parse_print_columns(values, valid_keys) -> list[str]:
    """Accept repeated params and comma-separated values, keeping a stable order."""
    selected: list[str] = []
    for value in values or ():
        for item in str(value or '').split(','):
            key = item.strip()
            if key in valid_keys and key not in selected:
                selected.append(key)
    return selected


def _frequency_rows(conn, conditions, params) -> list[dict]:
    """One row per (teacher, grade) with the gender split the page needs."""
    teacher_code_expr = _teacher_key_expr()
    teacher_name_expr = _teacher_name_expr()
    grade_expr = _text_expr('grade')
    rows = _dict_rows(conn.execute(
        f'''SELECT {teacher_code_expr} AS code,
                   {teacher_name_expr} AS teacher_name,
                   {grade_expr} AS grade,
                   SUM(CASE WHEN {_gender_expr()} = 'پسر' THEN 1 ELSE 0 END) AS boys,
                   SUM(CASE WHEN {_gender_expr()} = 'دختر' THEN 1 ELSE 0 END) AS girls,
                   SUM(CASE WHEN {_gender_expr()} = '{MISSING_LABEL}' THEN 1 ELSE 0 END) AS missing,
                   COUNT(s.id) AS total
            FROM students s
            WHERE {' AND '.join(conditions)}
            GROUP BY {teacher_code_expr}, {teacher_name_expr}, {grade_expr}''',
        params,
    ).fetchall())
    for row in rows:
        for key in ('boys', 'girls', 'missing', 'total'):
            row[key] = _number(row.get(key))
    # The page reports frequency *in grades*; the teacher is the second axis.
    rows.sort(key=lambda row: (_grade_rank(row['grade']), row['grade'], row['teacher_name']))
    return rows


def _subtotal_row(kind: str, label: str, label_column: str, rows: list[dict], population: int) -> dict:
    """Aggregate one group of detail rows into a printable subtotal line."""
    totals = {key: sum(row[key] for row in rows) for key in ('boys', 'girls', 'missing', 'total')}
    return {
        'row_kind': kind,
        'label': label,
        'label_column': label_column,
        'code': '',
        'teacher_name': '',
        'grade': '',
        **totals,
        'share': _percent(totals['total'], population),
    }


def _frequency_display_rows(rows: list[dict], population: int, selected_columns, show_grade=True, show_teacher=True) -> list[dict]:
    """Detail rows plus a subtotal after each grade and one block per teacher.

    Grade subtotals sit directly under their group; teacher totals aggregate every
    grade that teacher appears in and form a separate closing block. Labels are
    placed in whichever identity column survives the print selection.
    """
    grade_label_column = 'grade' if 'grade' in selected_columns else 'teacher'
    teacher_label_column = 'teacher' if 'teacher' in selected_columns else 'grade'

    grade_groups: list[tuple[str, list[dict]]] = []
    teacher_groups: dict[str, list[dict]] = {}
    for row in rows:
        if not grade_groups or grade_groups[-1][0] != row['grade']:
            grade_groups.append((row['grade'], []))
        grade_groups[-1][1].append(row)
        teacher_groups.setdefault((row['code'], row['teacher_name']), []).append(row)

    display: list[dict] = []
    for grade, group in grade_groups:
        for row in group:
            item = dict(row)
            item['row_kind'] = 'detail'
            item['label'] = ''
            item['label_column'] = ''
            display.append(item)
        if show_grade:
            item=_subtotal_row('grade_total', 'جمع '+(grade if grade.startswith('پایه') else 'پایه '+grade), grade_label_column, group, population)
            item['drill']={'drill_grade':grade}
            display.append(item)

    if show_teacher and teacher_groups:
        display.append({
            'row_kind': 'section',
            'label': 'جمع هر معلم (در پایه‌های همین خروجی)',
            'label_column': '',
            'code': '',
            'teacher_name': '',
            'grade': '',
            'boys': 0, 'girls': 0, 'missing': 0, 'total': 0, 'share': 0,
        })
        ordered_teachers = sorted(
            teacher_groups.items(),
            key=lambda item: (item[0][1], item[0][0]),
        )
        for (_code, teacher_name), group in ordered_teachers:
            label=f'جمع {teacher_name}'+(f' ({_code})' if _code!=UNASSIGNED_TEACHER else '')
            item=_subtotal_row('teacher_total', label, teacher_label_column, group, population)
            item['drill']={'drill_teacher':_code}
            display.append(item)
    return display


def _unique_options(rows, key, label_key) -> list[dict]:
    seen = {}
    for row in rows:
        value = row[key]
        if value not in seen:
            seen[value] = {'value': value, 'label': row[label_key]}
    return list(seen.values())



# All actions share the existing statistics endpoint and its access policy.
VIEW_LABELS = {'detail':'پایه و معلم', 'grade':'جمع پایه‌ها', 'teacher':'جمع معلم‌ها'}
NUMERIC_COLUMNS = ('boys','girls','missing','total')
FILTER_LABELS = {'status':'وضعیت','gender':'جنسیت','grade':'پایه','teacher_code':'معلم','class_name':'کلاس','sida_class':'کلاس سیدا'}
QUALITY_LABELS = {'no_teacher':'بدون معلم', 'invalid_teacher':'کد معلم نامعتبر', 'missing_gender':'جنسیت ثبت‌نشده یا نامعتبر', 'missing_grade':'پایه ثبت‌نشده'}


def _query_url(changes=None, remove=()):
    from urllib.parse import urlencode
    args=request.args.to_dict(flat=False)
    for key in remove:args.pop(key,None)
    for key,value in (changes or {}).items():
        if value is None:args.pop(key,None)
        else:args[key]=value if isinstance(value,list) else [value]
    return url_for('statistics')+('?' + urlencode(args,doseq=True) if args else '')


def _flag(name, default=True):
    values=request.args.getlist(name)
    if not values:return default
    if values[-1] not in ('0','1'):raise ValueError('مقدار تنظیم نمایش معتبر نیست.')
    return values[-1]=='1'


def _quality_conditions():
    return {
        'no_teacher':"TRIM(COALESCE(s.teacher_code,''))=''",
        'invalid_teacher':"TRIM(COALESCE(s.teacher_code,''))<>'' AND NOT EXISTS (SELECT 1 FROM teachers t WHERE TRIM(t.code)=TRIM(s.teacher_code))",
        'missing_gender':f"{_gender_expr()}='{MISSING_LABEL}'",
        'missing_grade':f"{_text_expr('grade')}='{MISSING_LABEL}'",
    }


def _effective_conditions(conditions, params, teachers, grades):
    result=list(conditions);values=list(params)
    for selected,expr in ((teachers,_teacher_key_expr()),(grades,_text_expr('grade'))):
        if selected:
            result.append(expr+' IN ('+','.join('?' for _ in selected)+')')
            values.extend(selected)
    return result,values


def _group_view(rows, view, population):
    if view=='detail':return rows
    grouped={}
    for row in rows:
        key=row['grade'] if view=='grade' else row['code']
        if key not in grouped:
            grouped[key]={'grade':row['grade'] if view=='grade' else '',
                          'teacher_name':row['teacher_name'] if view=='teacher' else '',
                          'code':row['code'] if view=='teacher' else '',
                          'row_kind':'detail','label':'','label_column':'',
                          **{col:0 for col in NUMERIC_COLUMNS},
                          'drill':{'drill_grade' if view=='grade' else 'drill_teacher':key}}
        for col in NUMERIC_COLUMNS:grouped[key][col]+=row[col]
    output=list(grouped.values())
    for row in output:row['share']=_percent(row['total'],population)
    return sorted(output,key=lambda r:(_grade_rank(r['grade']),r['grade']) if view=='grade' else (r['teacher_name'],r['code']))


def _add_links(rows, permitted):
    for row in rows:
        row['links']={}
        if not permitted or row.get('row_kind')=='section':continue
        drill=row.get('drill',{'drill_grade':row.get('grade'), 'drill_teacher':row.get('code')})
        for metric in NUMERIC_COLUMNS:
            if row.get(metric):
                row['links'][metric]=_query_url({'action':'students', 'metric':metric, **drill},
                    remove=('page','format','autoprint','quality','drill_teacher','drill_grade'))


def _build_context(conn):
    from .security import current_session_endpoints
    from .dates import display_jalali_datetime
    filters={key:request.args.get(key,'').strip() for key in FILTER_LABELS}
    if any(len(value)>200 for value in filters.values()):raise ValueError('مقدار فیلتر بیش از حد طولانی است.')
    filters['status']=filters['status'] or 'all'
    if filters['status'] not in STATUS_LABELS:raise ValueError('وضعیت فیلتر معتبر نیست.')
    view=request.args.get('view','detail')
    if view not in VIEW_LABELS:raise ValueError('حالت نمایش معتبر نیست.')
    action=request.args.get('action','')
    if action not in ('','students','export'):raise ValueError('عملیات گزارش معتبر نیست.')
    conditions,params=_student_filters(filters['grade'],filters['class_name'],filters['sida_class'],filters['gender'],filters['teacher_code'])
    conditions.append(_status_sql(filters['status']))
    # The endpoint currently belongs to admins/managers. Keep a scope guard if that changes.
    if session.get('role')=='teacher':
        conditions.append("TRIM(s.teacher_code)=?");params.append(str(session.get('personnel_number') or '__no_scope__'))
    all_rows=_frequency_rows(conn,conditions,params)
    population=sum(row['total'] for row in all_rows)
    options_teachers=_unique_options(all_rows,'code','teacher_name')
    options_grades=_unique_options(all_rows,'grade','grade')
    selected_teachers=list(dict.fromkeys(v for v in request.args.getlist('print_teacher') if v))
    selected_grades=list(dict.fromkeys(v for v in request.args.getlist('print_grade') if v))
    if any(len(v)>200 for v in selected_teachers+selected_grades):raise ValueError('شناسه یا عنوان انتخابی بیش از حد طولانی است.')
    if len(selected_teachers)+len(selected_grades)>900:raise ValueError('تعداد انتخاب‌ها بیش از حد مجاز است.')
    explicit=request.args.get('selection')=='1'
    if explicit and (not selected_teachers or not selected_grades):
        raise ValueError('حداقل یک معلم و یک پایه را برای خروجی انتخاب کنید؛ لغو همه به معنی انتخاب همه نیست.')
    effective_conditions,effective_params=_effective_conditions(conditions,params,selected_teachers,selected_grades)
    rows=[dict(row) for row in all_rows if (not selected_teachers or row['code'] in selected_teachers) and (not selected_grades or row['grade'] in selected_grades)]
    for row in rows:row['share']=_percent(row['total'],population)
    allowed=[(k,v) for k,v in FREQUENCY_COLUMNS if not (view=='grade' and k=='teacher') and not (view=='teacher' and k=='grade')]
    allowed_keys=[k for k,v in allowed]
    selected_columns=_parse_print_columns(request.args.getlist('print_col'),allowed_keys)
    if explicit and not selected_columns:raise ValueError('حداقل یک ستون برای خروجی انتخاب کنید.')
    if not selected_columns:selected_columns=allowed_keys[:]
    identity=[k for k in ('grade','teacher') if k in allowed_keys]
    if not any(k in selected_columns for k in identity):
        if explicit:raise ValueError('حداقل یک ستون شناسه (پایه یا معلم متناسب با حالت نمایش) لازم است.')
        selected_columns.insert(0,identity[0])
    show_grade=_flag('grade_totals');show_teacher=_flag('teacher_totals')
    viewed=_group_view(rows,view,population)
    display=_frequency_display_rows(rows,population,selected_columns,show_grade,show_teacher) if view=='detail' else viewed
    totals={k:sum(row[k] for row in rows) for k in NUMERIC_COLUMNS}
    totals.update(share=_percent(totals['total'],population),drill={},row_kind='grand_total')
    permissions=current_session_endpoints()
    can_drill='student_profile' in permissions
    _add_links(display,can_drill);_add_links([totals],can_drill)
    quality={k:conn.execute(f"SELECT COUNT(*) FROM students s WHERE {' AND '.join(effective_conditions)} AND ({expr})",effective_params).fetchone()[0] for k,expr in _quality_conditions().items()}
    quality_items=[{'key':k,'label':QUALITY_LABELS[k],'count':count,
        'url':_query_url({'action':'students','quality':k},remove=('page','format','autoprint','metric','drill_teacher','drill_grade')) if can_drill else None} for k,count in quality.items() if count]
    teachers_list=_dict_rows(conn.execute("SELECT TRIM(code) code,first_name,last_name FROM teachers WHERE TRIM(COALESCE(code,''))<>'' GROUP BY TRIM(code) ORDER BY first_name,last_name").fetchall())
    teachers_list.append({'code':UNASSIGNED_TEACHER,'first_name':'بدون معلم یا کد نامعتبر','last_name':''})
    grade_list=sorted(_option_values(conn,'grade'),key=lambda x:(_grade_rank(x),x))
    class_list=_option_values(conn,'class_name');sida_list=_option_values(conn,'sida_class');gender_list=_gender_values(conn)
    for key,options in [('grade',grade_list),('class_name',class_list),('sida_class',sida_list),('gender',gender_list)]:
        if filters[key] and filters[key] not in options:options.append(filters[key])
    if filters['teacher_code'] and not any(t['code']==filters['teacher_code'] for t in teachers_list):
        teachers_list.append({'code':filters['teacher_code'],'first_name':'کد انتخاب‌شده:','last_name':filters['teacher_code']})
    labels={k:(STATUS_LABELS.get(v,v) if k=='status' else _teacher_filter_label(teachers_list,v) if k=='teacher_code' else v) for k,v in filters.items()}
    scope=' · '.join(FILTER_LABELS[k]+': '+labels[k] for k,v in filters.items() if v and not (k=='status' and v=='all')) or 'همهٔ دانش‌آموزان و وضعیت‌ها'
    chips=[{'label':FILTER_LABELS[k]+': '+labels[k],
            'url':_query_url(remove=(k,'selection','print_teacher','print_grade','action','format','autoprint','page','quality','metric','drill_teacher','drill_grade'))}
           for k,v in filters.items() if v and not (k=='status' and v=='all')]
    selection_labels=[]
    if selected_grades:selection_labels.append('پایه‌های خروجی: '+'، '.join(selected_grades))
    if selected_teachers:selection_labels.append('معلم‌های خروجی: '+'، '.join(_teacher_filter_label(teachers_list,t) for t in selected_teachers))
    layout=load_report_layout(conn,'school_statistics',session.get('user_id'))
    orientation=request.args.get('orientation') or layout['orientation']
    if orientation not in ('portrait','landscape'):raise ValueError('جهت کاغذ معتبر نیست.')
    layout=dict(layout);layout['orientation']=orientation
    ctx=dict(frequency_rows=viewed,frequency_display_rows=display,frequency_totals=totals,
        frequency_columns_view=[{'key':k,'label':v} for k,v in allowed if k in selected_columns],
        frequency_column_options=[{'key':k,'label':v,'selected':k in selected_columns} for k,v in allowed],
        frequency_teacher_options=[{**x,'selected':not selected_teachers or x['value'] in selected_teachers} for x in options_teachers],
        frequency_grade_options=[{**x,'selected':not selected_grades or x['value'] in selected_grades} for x in options_grades],
        totals_label_key='teacher' if 'teacher' in selected_columns else 'grade',
        population=population,selected_population=totals['total'],frequency_row_count=len(viewed),
        grade_count=len({r['grade'] for r in rows}),teacher_count=len({r['code'] for r in rows if r['code']!=UNASSIGNED_TEACHER}),
        grade_list=grade_list,class_list=class_list,sida_list=sida_list,
        gender_list=gender_list,teachers_list=teachers_list,**filters,
        status_filter=filters['status'],status_options=STATUS_LABELS,view=view,view_options=VIEW_LABELS,
        show_grade_totals=show_grade,show_teacher_totals=show_teacher,scope_label=scope,active_chips=chips,
        selection_label=' · '.join(selection_labels) or 'همهٔ ردیف‌های محدوده',output_selection=bool(selected_teachers or selected_grades),quality_items=quality_items,
        filters=filters,filter_active_count=len(chips),can_drill=can_drill,can_print_layout='report_print_layouts' in permissions,can_export_students='export_excel' in permissions,
        print_mode=request.args.get('print')=='1',auto_print=request.args.get('autoprint')=='1',
        school_statistics_layout=layout,orientation=orientation,current_role=session.get('role'),
        missing_label=MISSING_LABEL,unassigned_teacher_value=UNASSIGNED_TEACHER,
        extracted_at=display_jalali_datetime()[1],
        client_rows=[{k:r[k] for k in ('code','grade','total')} for r in all_rows],
        print_form_hidden=[(k,v) for k,v in filters.items()]+[('view',view),('grade_totals','1' if show_grade else '0'),('teacher_totals','1' if show_teacher else '0')],
        conditions=effective_conditions,params=effective_params)
    import json
    ctx['print_footer_css']=json.dumps(str(current_app.config.get('SCHOOL_NAME',''))+' · '+ctx['extracted_at']+' · صفحه ',ensure_ascii=False).replace('<',r'\3c ')
    return ctx


def _student_detail(conn,ctx):
    if not ctx['can_drill']:abort(403)
    conditions=list(ctx['conditions']);params=list(ctx['params']);detail_labels=[]
    for key,expr,label in [('drill_grade',_text_expr('grade'),'پایه'),('drill_teacher',_teacher_key_expr(),'معلم')]:
        value=request.args.get(key,'')
        if len(value)>200:raise ValueError('مقدار فیلتر جزئیات بیش از حد طولانی است.')
        if value:
            conditions.append(expr+'=?');params.append(value)
            detail_labels.append(label+': '+(_teacher_filter_label(ctx['teachers_list'],value) if key=='drill_teacher' else value))
    metric=request.args.get('metric','total')
    if metric not in NUMERIC_COLUMNS:raise ValueError('ستون آماری معتبر نیست.')
    if metric!='total':
        value={'boys':'پسر','girls':'دختر','missing':MISSING_LABEL}[metric]
        conditions.append(_gender_expr()+'=?');params.append(value);detail_labels.append('جنسیت: '+value)
    quality=request.args.get('quality','')
    if quality:
        if quality not in _quality_conditions():raise ValueError('فیلتر کیفیت داده معتبر نیست.')
        conditions.append('('+_quality_conditions()[quality]+')');detail_labels.append(QUALITY_LABELS[quality])
    where=' AND '.join(conditions)
    count=conn.execute('SELECT COUNT(*) FROM students s WHERE '+where,params).fetchone()[0]
    fmt=request.args.get('format','')
    if fmt and fmt not in ('xlsx','pdf'):raise ValueError('نوع خروجی معتبر نیست.')
    if fmt and not ctx['can_export_students']:abort(403)
    try:page=max(1,int(request.args.get('page','1')))
    except ValueError:raise ValueError('شمارهٔ صفحه معتبر نیست.') from None
    page=min(page,max(1,(count+49)//50))
    if fmt and count>10000:raise ValueError('خروجی فهرست بیش از ۱۰٬۰۰۰ نفر است؛ فیلتر را محدود کنید.')
    rows=_dict_rows(conn.execute(f"""SELECT s.id,s.code,TRIM(COALESCE(s.first_name,'')||' '||COALESCE(s.last_name,'')) name,
        {_text_expr('grade')} grade,{_text_expr('class_name')} class_name,{_teacher_name_expr()} teacher_name,
        {_gender_expr()} gender FROM students s WHERE {where}
        ORDER BY s.last_name,s.first_name,s.id LIMIT ? OFFSET ?""",params+[10001 if fmt else 50,0 if fmt else (page-1)*50]).fetchall())
    ctx.update(student_rows=rows,detail_count=count,page=page,pages=max(1,(count+49)//50),
        detail_label=' · '.join(detail_labels) or 'همهٔ افراد این محدوده',
        back_url=_query_url(remove=('action','metric','quality','drill_grade','drill_teacher','page','format','autoprint')),
        prev_url=_query_url({'page':page-1}) if page>1 else None,
        next_url=_query_url({'page':page+1}) if page*50<count else None,
        detail_export_urls={kind:_query_url({'format':kind},remove=('page','autoprint')) for kind in ('xlsx','pdf')})
    return fmt


def statistics_dashboard():
    @after_this_request
    def no_cache(response):
        response.headers['Cache-Control']='private, no-store'
        return response
    try:
        # A single read transaction keeps counts, rows and export metadata consistent.
        with get_db() as conn:
            conn.execute('BEGIN')
            ctx=_build_context(conn)
            if request.args.get('action')=='students':
                fmt=_student_detail(conn,ctx)
                if not fmt:return render_template('statistics_students.html',**ctx)
                detail=True
            else:
                detail=False
                fmt=request.args.get('format','') if request.args.get('action')=='export' else ''
                if request.args.get('action')=='export' and fmt not in ('xlsx','pdf'):
                    raise ValueError('نوع خروجی معتبر نیست.')
        if fmt:
            from .statistics_exports import export_statistics
            return export_statistics(ctx,fmt,detail)
        return render_template('statistics.html',**ctx)
    except ValueError as exc:
        if request.args.get('action')=='export' or request.args.get('format'):
            return jsonify(ok=False,error=str(exc)),400
        return render_template('statistics_error.html',message=str(exc)),400
