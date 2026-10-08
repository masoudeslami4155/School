#!/usr/bin/env python
"""آزمون ثبت سریع حضور و غیاب کل مدرسه.

مدیر فقط غایبین را انتخاب میکند؛ بقیهٔ دانشآموزان فعال خودکار «حاضر» ثبت میشوند
و رکوردهای موجود هرگز بازنویسی نمیشوند. این آزمون روی یک دیتابیس موقت اجرا میشود
و به ``school.db`` واقعی مدرسه دست نمیزند.

نمونهٔ اجرا::

    python tests/attendance_quick_test.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for stream in (sys.stdout, sys.stderr):  # چاپ امن روی کنسولهای ویندوزی
    try:
        stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

PASSWORD = 'Quick!12345'
CLASSES = ('کلاس ۱', 'کلاس ۲')


def prepare_environment(tmp: Path) -> None:
    import os
    os.environ.update({
        'DATABASE_PATH': str(tmp / 'quick.db'),
        'BACKUP_DIR': str(tmp / 'backups'),
        'LOG_DIR': str(tmp / 'logs'),
        'UPLOAD_FOLDER': str(tmp / 'uploads'),
        'SECRET_KEY': 'quick-test-only-secret-key',
        'SCHOOL_NAME': 'مدرسه آزمایشی',
        'PROGRAMMER_NAME': 'آزمایش',
    })


def seed(conn) -> str:
    """کاربران و دانشآموزان آزمایشی میسازد و تاریخ امروز را برمیگرداند."""
    from werkzeug.security import generate_password_hash

    from school_app.dates import today_string

    now = datetime.now().isoformat(timespec='seconds')
    for personnel, full_name, role, teacher_code in (
            ('admin', 'مدیر آزمایشی', 'admin', None),
            ('M-1001', 'معاون آزمایشی', 'manager', None),
            ('T-1001', 'معلم آزمایشی', 'teacher', 'T-1001')):
        conn.execute('DELETE FROM users WHERE personnel_number=?', (personnel,))
        conn.execute(
            '''INSERT INTO users(personnel_number,full_name,password_hash,role,is_active,
                                 must_change_password,teacher_code,permissions,created_at)
               VALUES(?,?,?,?,1,0,?,'',?)''',
            (personnel, full_name, generate_password_hash(PASSWORD), role, teacher_code, now),
        )

    students = (
        ('S-1', 'زهرا', 'آزمونی', 'فعال', CLASSES[0]),
        ('S-2', 'علی', 'نمونه', 'فعال', CLASSES[0]),
        ('S-3', 'مریم', 'آزمونپور', 'فعال', CLASSES[1]),
        ('S-4', 'حسین', 'سایرین', 'فعال', CLASSES[1]),
        ('S-5', 'رضا', 'غیرفعال', 'فارغ‌التحصیل', CLASSES[0]),
    )
    for code, first, last, status, class_name in students:
        conn.execute(
            '''INSERT INTO students(code,first_name,last_name,status,class_name,grade)
               VALUES(?,?,?,?,?,?)''',
            (code, first, last, status, class_name, 'پایه اول'),
        )
    conn.commit()
    return today_string()


def status_of(conn, code: str, date: str) -> str | None:
    row = conn.execute(
        'SELECT status FROM attendance_students WHERE student_code=? AND date=?', (code, date)
    ).fetchone()
    return row['status'] if row else None


def count_for_date(conn, date: str) -> int:
    return conn.execute(
        'SELECT COUNT(*) AS count FROM attendance_students WHERE date=?', (date,)
    ).fetchone()['count']


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='attendance-quick-'))
    prepare_environment(tmp)

    from school_app import app
    from school_app.database import get_db

    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    with app.app_context():
        with get_db() as conn:
            today = seed(conn)

    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = '') -> None:
        if condition:
            print(f'  ✓ {label}')
        else:
            failures.append(f'{label} {detail}')
            print(f'  ✗ {label} {detail}')

    def login(role: str):
        client = app.test_client()
        personnel = {'admin': 'admin', 'manager': 'M-1001', 'teacher': 'T-1001'}[role]
        response = client.post('/login', data={'personnel_number': personnel, 'password': PASSWORD})
        assert response.status_code in (200, 302), response.status_code
        return client

    def csrf(client) -> str:
        with client.session_transaction() as session_data:
            return session_data.get('_csrf_token', '')

    print('دسترسی و نمایش فهرست')
    admin = login('admin')
    manager = login('manager')
    teacher = login('teacher')

    response = admin.get('/attendance_quick')
    check('مدیر کل به ثبت سریع دسترسی دارد', response.status_code == 200, str(response.status_code))
    body = response.get_data(as_text=True)
    for name in ('زهرا', 'علی', 'مریم', 'حسین'):
        check(f'فهرست شامل {name} است', name in body)
    check('دانشآموز غیرفعال در فهرست نیست', 'رضا' not in body)

    check('مدیر به ثبت سریع دسترسی دارد', manager.get('/attendance_quick').status_code == 200)
    check('معلم به ثبت سریع دسترسی ندارد',
          teacher.get('/attendance_quick').status_code == 403,
          str(teacher.get('/attendance_quick').status_code))

    print('ثبت خودکار حاضر برای بقیه')
    response = admin.post('/attendance_quick', data={
        '_csrf_token': csrf(admin), 'date': today, 'class_name': '', 'absent_S-2': '1',
    })
    check('پاسخ ثبت سریع تغییرمسیر است', response.status_code == 302, str(response.status_code))

    with app.app_context():
        with get_db() as conn:
            check('غایب انتخابشده غایب ثبت شد', status_of(conn, 'S-2', today) == 'غایب',
                  str(status_of(conn, 'S-2', today)))
            for code in ('S-1', 'S-3', 'S-4'):
                check(f'{code} خودکار حاضر ثبت شد', status_of(conn, code, today) == 'حاضر',
                      str(status_of(conn, code, today)))
            check('دانشآموز غیرفعال رکورد نگرفت', status_of(conn, 'S-5', today) is None)
            check('چهار رکورد برای امروز ثبت شد', count_for_date(conn, today) == 4,
                  str(count_for_date(conn, today)))

    print('رکورد موجود دست نخورده میماند')
    response = admin.post('/attendance_quick', data={
        '_csrf_token': csrf(admin), 'date': today, 'class_name': '', 'absent_S-1': '1',
    })
    with app.app_context():
        with get_db() as conn:
            check('S-1 که حاضر بود حاضر میماند', status_of(conn, 'S-1', today) == 'حاضر',
                  str(status_of(conn, 'S-1', today)))
            check('S-2 که غایب شد غایب میماند', status_of(conn, 'S-2', today) == 'غایب',
                  str(status_of(conn, 'S-2', today)))
            check('تعداد رکوردها افزایش نیافت', count_for_date(conn, today) == 4,
                  str(count_for_date(conn, today)))

    print('فیلتر کلاس')
    other_date = '1404/07/01'  # تاریخی بدون رکورد قبلی
    response = manager.post('/attendance_quick', data={
        '_csrf_token': csrf(manager), 'date': other_date, 'class_name': CLASSES[1],
        'absent_S-3': '1',
    })
    with app.app_context():
        with get_db() as conn:
            check('S-3 در کلاس ۲ غایب شد', status_of(conn, 'S-3', other_date) == 'غایب',
                  str(status_of(conn, 'S-3', other_date)))
            check('S-4 در کلاس ۲ حاضر شد', status_of(conn, 'S-4', other_date) == 'حاضر',
                  str(status_of(conn, 'S-4', other_date)))
            check('فقط کلاس ۲ در این تاریخ ثبت شد', count_for_date(conn, other_date) == 2,
                  str(count_for_date(conn, other_date)))
            check('کلاس ۱ در این تاریخ ثبت نشده', status_of(conn, 'S-1', other_date) is None)

    print('ورودی نامعتبر')
    response = admin.post('/attendance_quick', data={
        '_csrf_token': csrf(admin), 'date': 'تاریخ غلط', 'class_name': '', 'absent_S-1': '1',
    })
    check('تاریخ نامعتبر رد میشود', response.status_code == 302, str(response.status_code))
    response = admin.post('/attendance_quick', data={
        '_csrf_token': csrf(admin), 'date': today, 'class_name': '', 'absent_S-999': '1',
    })
    with app.app_context():
        with get_db() as conn:
            check('کد نامعتبر نادیده گرفته شد', status_of(conn, 'S-999', today) is None)

    print('حسابرسی')
    with app.app_context():
        with get_db() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) AS count FROM audit_log WHERE action='quick_student_attendance'"
            ).fetchone()['count']
            check('ثبت سریع در حسابرسی ثبت شد', rows == 2, str(rows))

    print()
    if failures:
        print(f'نتیجه: {len(failures)} مورد شکست خورد:')
        for item in failures:
            print(f'  - {item}')
        return 1
    print('نتیجه: همهٔ آزمونهای ثبت سریع حضور و غیاب سبز است.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
