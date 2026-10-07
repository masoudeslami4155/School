#!/usr/bin/env python
"""اسموکتست مسیرهای GET سامانهٔ مدیریت مدرسه.

هدف: قبل از هر کامیت، همهٔ مسیرهای GET برنامه با نشست نقش‌های ``admin``،
``manager`` و ``teacher`` زده می‌شود و هر پاسخ ۵۰۰ یا استثنای پایتون با
جزئیات (مسیر، نقش، ردّ استثنا و لاگ خطای برنامه) گزارش می‌گردد.

این اسکریپت کاملاً ایزوله است: دیتابیس، پشتیبان‌ها، لاگ‌ها و پوشهٔ بارگذاری
در یک پوشهٔ موقت ساخته می‌شوند و به ``school.db`` واقعی مدرسه دست نمی‌زند.
شمارهٔ ورود در پایان چاپ می‌شود تا اگر خواستید همان دیتابیس موقت را باز کنید.

نمونه‌های اجرا::

    python tests/smoke_get_routes.py                # با داده‌های نمونه
    python tests/smoke_get_routes.py --empty        # فقط دیتابیس خالی (بدون داده)
    python tests/smoke_get_routes.py --role admin   # فقط یک نقش
    python tests/smoke_get_routes.py --keep         # پوشهٔ موقت پاک نشود
    python tests/smoke_get_routes.py --verbose      # فهرست کامل کدها
    python tests/smoke_get_routes.py --brief        # فقط یک خط خلاصه (مناسب هوک کامیت)

کد خروج ۰ یعنی هیچ خطای ۵۰۰ یا استثنایی پیدا نشد؛ ۱ یعنی حداقل یک خطا دیده شد.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for stream in (sys.stdout, sys.stderr):  # چاپ امن روی کنسول‌های ویندوزی
    try:
        stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

ROLES = ('admin', 'manager', 'teacher')
PASSWORD = 'Smoke!12345'  # فقط برای دیتابیس موقت؛ بیرون از تست استفاده نمی‌شود
OK_STATUSES = {200, 201, 204, 302, 303, 304}


# --------------------------------------------------------------------------
# محیط ایزوله
# --------------------------------------------------------------------------
def prepare_environment(tmp: Path) -> None:
    """مسیرهای اجرا را پیش از import برنامه به پوشهٔ موقت می‌برد."""
    os.environ.update({
        'DATABASE_PATH': str(tmp / 'smoke.db'),
        'BACKUP_DIR': str(tmp / 'backups'),
        'LOG_DIR': str(tmp / 'logs'),
        'UPLOAD_FOLDER': str(tmp / 'uploads'),
        'SECRET_KEY': 'smoke-test-only-secret-key',
        'SCHOOL_NAME': 'مدرسه آزمایشی اسموکتست',
        'PROGRAMMER_NAME': 'اسموکتست',
    })


def build_users(conn, app) -> dict[str, str]:
    """سه کاربر تست با رمز شناخته‌شده می‌سازد (یا رمزشان را بازنشانی می‌کند)."""
    from werkzeug.security import generate_password_hash

    people = {
        'admin': ('admin', 'مدیر آزمایشی', None),
        'manager': ('M-1001', 'معاون آزمایشی', None),
        'teacher': ('T-1001', 'معلم آزمایشی', 'T-1001'),
    }
    for role, (personnel, full_name, teacher_code) in people.items():
        conn.execute(
            'DELETE FROM users WHERE personnel_number=?', (personnel,)
        )
        conn.execute(
            '''INSERT INTO users(personnel_number,full_name,password_hash,role,is_active,
                                 must_change_password,teacher_code,permissions,created_at)
               VALUES(?,?,?,?,1,0,?,'',?)''',
            (personnel, full_name, generate_password_hash(PASSWORD), role, teacher_code,
             datetime.now().isoformat(timespec='seconds')),
        )
    conn.commit()
    return {role: personnel for role, (personnel, _n, _c) in people.items()}


def insert_fixtures(conn, upload_folder: Path) -> dict[str, object]:
    """دادهٔ کمینه برای اینکه مسیرها حالت «خالی» را تست نکنند."""
    from school_app.dates import today_string
    from school_app.routes import meetings as meetings_module

    try:  # جدول‌های جلسات در اولین درخواست ساخته می‌شوند
        meetings_module.schema()
    except Exception:
        pass

    today = today_string()
    ids: dict[str, object] = {'today': today}

    students = [
        ('S-1001', 'زهرا', 'آزمونی', 'فعال', 'دختر', 'T-1001', '1390/05/10'),
        ('S-1002', 'علی', 'نمونه', 'فارغ‌التحصیل', 'پسر', 'T-1001', '1389/02/01'),
        ('S-1003', 'مریم', 'آزمون‌پور', 'ترک تحصیل', 'دختر', '', '1391/11/20'),
        ('S-1004', 'حسین', 'سایرین', 'سایر', 'پسر', '', '1392/01/05'),
    ]
    for code, first, last, status, gender, teacher_code, birth in students:
        conn.execute(
            '''INSERT INTO students(code,first_name,last_name,status,gender,teacher_code,
                                   birth_date,grade,class_name,sida_class,father_phone,
                                   mother_phone,father_name,mother_name,address,service_fee)
               VALUES(?,?,?,?,?,?,?,'پایه اول','کلاس ۱','سیدا ۱','09120000001',
                      '09120000002','پدر آزمایشی','مادر آزمایشی','نشانی آزمایشی',1000000)''',
            (code, first, last, status, gender, teacher_code, birth),
        )
    ids['student_id'] = conn.execute(
        "SELECT id FROM students WHERE code='S-1001'"
    ).fetchone()['id']
    ids['student_code'] = 'S-1001'
    ids['inactive_student_id'] = conn.execute(
        "SELECT id FROM students WHERE code='S-1002'"
    ).fetchone()['id']

    conn.execute(
        """INSERT INTO teachers(first_name,last_name,code,subject,class_name,sida_class,
                                national_id,phone)
           VALUES('معلم','آزمایشی','T-1001','آموزش','کلاس ۱','سیدا ۱','0012345678','09120000003')"""
    )
    ids['teacher_id'] = conn.execute(
        "SELECT id FROM teachers WHERE code='T-1001'"
    ).fetchone()['id']

    conn.execute(
        "INSERT INTO attendance_students(student_code,date,status) VALUES('S-1001',?, 'حاضر')",
        (today,),
    )
    conn.execute(
        "INSERT INTO attendance_students(student_code,date,status) VALUES('S-1001','1404/07/01','غایب')"
    )
    conn.execute(
        "INSERT INTO attendance_teachers(teacher_code,date,status,late_duration) VALUES('T-1001',?,'تاخیر',10)",
        (today,),
    )
    conn.execute(
        """INSERT INTO events(title,date,time,description,type,priority)
           VALUES('رویداد آزمایشی',?,'08:00','توضیح آزمایشی','جلسه','عادی')""",
        (today,),
    )
    ids['event_id'] = conn.execute('SELECT id FROM events ORDER BY id DESC LIMIT 1').fetchone()['id']

    conn.execute(
        """INSERT INTO tasks(title,description,due_date,due_time,priority,status,
                             alarm_enabled,alarm_minutes,category,created_at)
           VALUES('کار آزمایشی','توضیح',?,'09:00','عادی','باز',1,30,'کار',?)""",
        (today, datetime.now().isoformat(timespec='seconds')),
    )
    ids['task_id'] = conn.execute('SELECT id FROM tasks ORDER BY id DESC LIMIT 1').fetchone()['id']

    conn.execute(
        """INSERT INTO discipline(target_type,target_code,date,type,points,description)
           VALUES('student','S-1001',?,'تذکر',1,'توضیح آزمایشی')""",
        (today,),
    )
    conn.execute(
        """INSERT INTO class_visits(teacher_code,class_name,date,report)
           VALUES('T-1001','کلاس ۱',?,'گزارش آزمایشی')""",
        (today,),
    )
    conn.execute(
        """INSERT INTO teacher_performance(teacher_code,student_code,date,report)
           VALUES('T-1001','S-1001',?,'عملکرد آزمایشی')""",
        (today,),
    )
    ids['performance_id'] = conn.execute(
        'SELECT id FROM teacher_performance ORDER BY id DESC LIMIT 1'
    ).fetchone()['id']

    conn.execute(
        """INSERT INTO financial_help(student_code,amount,date,description)
           VALUES('S-1001',250000,?,'کمک آزمایشی')""",
        (today,),
    )
    conn.execute(
        """INSERT INTO monthly_service(student_code,year,month,service_type,amount,
                                       paid_amount,payment_date,status,description)
           VALUES('S-1001','1404','مهر','رفت و برگشت',1000000,400000,?,'جزئی','آزمایشی')""",
        (today,),
    )
    ids['payment_id'] = conn.execute(
        'SELECT id FROM monthly_service ORDER BY id DESC LIMIT 1'
    ).fetchone()['id']

    upload_folder.mkdir(parents=True, exist_ok=True)
    document = upload_folder / 'smoke-document.txt'
    document.write_text('سند آزمایشی اسموکتست\n', encoding='utf-8')
    conn.execute(
        """INSERT INTO support_plans(student_code,provider_role,provider_name,topic,
                                     planned_sessions,completed_sessions,cost,status,
                                     document_path,document_name)
           VALUES('S-1001','مشاور','مشاور آزمایشی','موضوع آزمایشی',4,1,100000,'برنامه‌ریزی‌شده',?,?)""",
        (document.name, 'سند آزمایشی.txt'),
    )
    ids['plan_id'] = conn.execute(
        'SELECT id FROM support_plans ORDER BY id DESC LIMIT 1'
    ).fetchone()['id']

    now = datetime.now().isoformat(timespec='seconds')
    try:
        conn.execute(
            """INSERT INTO meetings(meeting_type,meeting_date,meeting_time,location,subject,
                                    agenda,decisions,follow_up,created_at,updated_at)
               VALUES('شورای مدرسه',?,'10:00','اتاق مدیر','موضوع آزمایشی','دستور','تصمیم','پیگیری',?,?)""",
            (today, now, now),
        )
        ids['meeting_id'] = conn.execute('SELECT id FROM meetings ORDER BY id DESC LIMIT 1').fetchone()['id']
    except Exception as exc:
        ids['meeting_id'] = 1
        ids['meeting_error'] = f'{type(exc).__name__}: {exc}'

    conn.commit()
    ids['user_id'] = conn.execute(
        "SELECT id FROM users WHERE personnel_number='M-1001'"
    ).fetchone()['id']
    return ids


# --------------------------------------------------------------------------
# ساخت آدرس و انتخاب شناسهٔ درست برای پارامترها
# --------------------------------------------------------------------------
def value_for(endpoint: str, argument: str, ids: dict) -> object:
    mapping = (
        ('download_support_document', 'plan_id', ids.get('plan_id', 1)),
        ('meeting_view', 'id', ids.get('meeting_id', 1)),
        ('edit_teacher_performance', 'id', ids.get('performance_id', 1)),
        ('edit_teacher', 'id', ids.get('teacher_id', 1)),
        ('edit_user', 'id', ids.get('user_id', 1)),
        ('edit_event', 'id', ids.get('event_id', 1)),
        ('edit_task', 'id', ids.get('task_id', 1)),
        ('edit_payment', 'id', ids.get('payment_id', 1)),
        ('confirm_delete_student', 'id', ids.get('inactive_student_id', 1)),
        ('static', 'filename', 'app.css'),
    )
    for name, arg, value in mapping:
        if endpoint == name and argument == arg:
            return value
    if argument == 'student_code':
        return ids.get('student_code', 'S-1001')
    if argument == 'filename':
        return 'app.css'
    return ids.get('student_id', 1)


def collect_targets(app, ids: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """برای هر قاعدهٔ GET یک آدرس می‌سازد و قواعد ساخته‌نشده را برمی‌گرداند."""
    from flask import url_for

    adapter = app.url_map.bind('localhost')
    targets: list[tuple[str, str]] = []
    skipped: list[str] = []
    seen: set[str] = set()
    with app.test_request_context():
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
            if 'GET' not in (rule.methods or set()):
                continue
            values = {arg: value_for(rule.endpoint, arg, ids) for arg in rule.arguments}
            try:
                url = adapter.build(rule.endpoint, values, append_unknown=False)
            except Exception:
                try:
                    url = url_for(rule.endpoint, **values)
                except Exception as exc:  # هیچ قاعده‌ای نباید بی‌صدا رد شود
                    skipped.append(f'{rule.endpoint} {rule} → {type(exc).__name__}: {exc}')
                    continue
            key = f'{rule.endpoint} {url}'
            if key in seen:
                continue
            seen.add(key)
            targets.append((rule.endpoint, url))
    return targets, skipped


# --------------------------------------------------------------------------
# اجرای تست
# --------------------------------------------------------------------------
def short_traceback(exc: BaseException, limit: int = 12) -> str:
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    text = ''.join(lines).strip().splitlines()
    if len(text) > limit:
        text = text[-limit:]
    return '\n'.join(f'      {line}' for line in text)


def run_group(app, role: str, personnel: str, targets, verbose: bool) -> dict:
    client = app.test_client()
    result = {'role': role, 'errors': [], 'warnings': [], 'statuses': {}, 'login': ''}

    response = client.post('/login', data={'personnel_number': personnel, 'password': PASSWORD})
    if response.status_code not in OK_STATUSES:
        result['login'] = f'ورود ناموفق ({response.status_code})'
        return result
    with client.session_transaction() as session_data:
        if session_data.get('role') != role:
            result['login'] = f'نقش نشست «{session_data.get("role")}» شد، نه «{role}».'
            return result

    for endpoint, url in targets:
        try:
            response = client.get(url)
            status = response.status_code
        except Exception as exc:  # استثنای پایتون که به ۵۰۰ تبدیل می‌شد
            result['errors'].append({
                'endpoint': endpoint, 'url': url, 'status': 'exception',
                'detail': f'{type(exc).__name__}: {exc}', 'traceback': short_traceback(exc),
            })
            result['statuses']['exception'] = result['statuses'].get('exception', 0) + 1
            continue
        result['statuses'][status] = result['statuses'].get(status, 0) + 1
        if status >= 500:
            result['errors'].append({
                'endpoint': endpoint, 'url': url, 'status': status,
                'detail': f'پاسخ {status}', 'traceback': '',
            })
        elif status not in OK_STATUSES:
            entry = {'endpoint': endpoint, 'url': url, 'status': status,
                     'detail': f'پاسخ {status}', 'traceback': ''}
            # ۴۰۳ برای نقش مدیر یعنی نقشهٔ دسترسی‌ها جایی اشتباه است.
            if status == 403 and role == 'admin':
                result['errors'].append(entry)
            else:
                result['warnings'].append(entry)
    return result


def print_report(results, verbose: bool, log_path: Path | None,
                 skipped: list[str] | None = None, brief: bool = False) -> int:
    failures = 0
    seen_signatures: set[str] = set()
    requests = sum(sum(item['statuses'].values()) for item in results)
    role_names = '، '.join(item['role'] for item in results)

    if brief:
        for item in results:
            failures += 1 if item['login'] else 0
            failures += len(item['errors'])
        failures += len(skipped or [])
        # لاگ خطا حتی در حالت خلاصه هم بررسی می‌شود
        log_text = ''
        if log_path and log_path.is_file():
            log_text = log_path.read_text(encoding='utf-8', errors='replace').strip()
        if not failures and not log_text:
            print(f"✓ اسموکتست GET: {requests} درخواست با نقش‌های {role_names} — "
                  f"هیچ خطای ۵۰۰ یا استثنایی نبود.")
            return 0

    print('=' * 78)
    print('گزارش اسموکتست مسیرهای GET')
    print('=' * 78)

    for item in results:
        counts = ', '.join(f'{key}: {value}' for key, value in sorted(item['statuses'].items(), key=str))
        print(f"\nنقش {item['role']:8s} | {counts or 'هیچ درخواستی انجام نشد'}")
        if item['login']:
            print(f"  ⚠ {item['login']}")
            failures += 1
        for error in item['errors']:
            failures += 1
            signature = f"{error['endpoint']}|{error['detail']}"
            print(f"  ✗ {error['status']}  {error['url']}")
            print(f"      endpoint: {error['endpoint']}")
            if error['traceback']:
                print(error['traceback'])
            elif signature in seen_signatures:
                print('      (همان خطای قبلی)')
            seen_signatures.add(signature)
        if verbose:
            for warning in item['warnings']:
                print(f"  · {warning['status']}  {warning['url']}")
        elif item['warnings']:
            grouped: dict[object, int] = {}
            for warning in item['warnings']:
                grouped[warning['status']] = grouped.get(warning['status'], 0) + 1
            summary = ', '.join(f'پاسخ {k}: {v} مورد' for k, v in sorted(grouped.items(), key=str))
            print(f'  · موارد طبیعی خارج از ۲۰۰/۳۰۲ → {summary} (با --verbose کامل ببینید)')

    if skipped:
        print(f'\n⚠ {len(skipped)} قاعدهٔ GET آدرس‌شان ساخته نشد و تست نشدند:')
        for row in skipped:
            print(f'   - {row}')
        failures += len(skipped)

    if log_path and log_path.is_file():
        text = log_path.read_text(encoding='utf-8', errors='replace').strip()
        if text:
            print('\n--- لاگ خطای برنامه (logs/error.log دیتابیس موقت) ---')
            for line in text.splitlines()[-25:]:
                print(f'  {line}')

    print('\n' + '=' * 78)
    if failures:
        print(f'نتیجه: {failures} خطا پیدا شد (کد خروج ۱).')
    else:
        print('نتیجه: هیچ خطای ۵۰۰ یا استثنایی پیدا نشد.')
    print('=' * 78)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description='اسموکتست مسیرهای GET سامانهٔ مدیریت مدرسه')
    parser.add_argument('--empty', action='store_true', help='بدون دادهٔ نمونه (دیتابیس خالی)')
    parser.add_argument('--role', choices=ROLES, help='فقط یک نقش را تست کن')
    parser.add_argument('--verbose', action='store_true', help='فهرست کامل کدهای وضعیت')
    parser.add_argument('--brief', action='store_true', help='فقط خلاصهٔ یک‌خطی (برای هوک کامیت)')
    parser.add_argument('--keep', action='store_true', help='پوشهٔ موقت پاک نشود')
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix='school-smoke-'))
    prepare_environment(tmp)
    credentials = ROOT / 'initial_credentials.txt'
    credentials_existed = credentials.exists()

    if args.brief:  # خروجی خلاصه نباید هدر استقبال را نشان دهد
        print('اجرای اسموکتست مسیرهای GET...')

    from school_app import app
    from school_app.database import get_db

    if not credentials_existed and credentials.exists():
        credentials.unlink()  # رمز کاربران پاک شود؛ این فایل مربوط به دیتابیس واقعی است
        print('! فایل initial_credentials.txt که این تست ساخته بود پاک شد.')

    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)

    with app.app_context():
        with get_db() as conn:
            people = build_users(conn, app)
            ids = insert_fixtures(conn, Path(app.config['UPLOAD_FOLDER']))

    if args.empty:
        with app.app_context():
            with get_db() as conn:
                conn.executescript(
                    'DELETE FROM students; DELETE FROM teachers; DELETE FROM discipline; '
                    'DELETE FROM class_visits; DELETE FROM teacher_performance; '
                    'DELETE FROM financial_help; DELETE FROM monthly_service; '
                    'DELETE FROM support_plans; DELETE FROM events; DELETE FROM tasks;'
                )
                conn.commit()
        print('! حالت --empty: همهٔ داده‌های آموزشی حذف شدند.')

    targets, skipped = collect_targets(app, ids)
    get_rules = [rule for rule in app.url_map.iter_rules() if 'GET' in (rule.methods or set())]
    if not args.brief:
        print(f'دیتابیس موقت: {tmp}')
        print(f'هدف‌ها: {len(targets)} مسیر GET از {len(get_rules)} قاعدهٔ GET × '
              f'{len(ROLES) if not args.role else 1} نقش')
        if ids.get('meeting_error'):
            print(f"! فیکسچر جلسه ثبت نشد → {ids['meeting_error']}")
        if skipped:
            print('! قواعدی که آدرس‌شان ساخته نشد (باید بررسی شوند):')
            for row in skipped:
                print(f'   - {row}')

    results = []
    for role in ROLES:
        if args.role and role != args.role:
            continue
        results.append(run_group(app, role, people[role], targets, args.verbose))

    code = print_report(results, args.verbose, tmp / 'logs' / 'error.log', skipped, args.brief)

    if args.keep:
        print(f'پوشهٔ موقت نگه داشته شد: {tmp}')
        print(f"ورود آزمایشی: admin / {PASSWORD} (فقط روی همان دیتابیس موقت)")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
