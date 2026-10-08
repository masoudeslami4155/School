#!/usr/bin/env python
"""آزمون شیوه‌های نمایش فهرست دانش‌آموزان.

چه چیزی بررسی می‌شود
--------------------
* انتخاب پیش‌فرض شش‌حالته از صفحهٔ تنظیمات (دیگر در index نمایش داده نمی‌شود)
* نمایش جدولی کامل: همهٔ ستون‌ها، همان تعداد دانش‌آموز و همان مقدار checkbox کارت‌ها
* ذخیرهٔ حالت انتخابی هر کاربر در ``app_settings`` با کلید ``student_card_view:<user_id>``
* جداسازی کاربران (انتخاب معلم روی انتخاب مدیر اثری ندارد) و بازگشت به پیش‌فرض با مقدار خراب
* رد درخواست نامعتبر (مقدار خارج از فهرست) و درخواست بدون توکن CSRF

کاملاً ایزوله است: دیتابیس، پشتیبان‌ها، لاگ‌ها و بارگذاری در پوشهٔ موقت ساخته
می‌شوند و به ``school.db`` واقعی مدرسه دست نمی‌زنند.
کد خروج ۰ یعنی همهٔ بررسی‌ها سبز است؛ ۱ یعنی حداقل یک بررسی شکست خورد.

نمونهٔ اجرا::

    python tests/student_view_test.py
"""

from __future__ import annotations

import argparse
import os
import shutil
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

PASSWORD = 'View!12345'  # فقط برای دیتابیس موقت
MANAGER = 'M-1001'
TEACHER = 'T-1001'
VIEWS = ('xs', 'sm', 'md', 'lg', 'xl', 'table')
LABELS = ('نام و کد', 'خلاصه', 'استاندارد', 'درشت', 'خیلی درشت', 'جدول کامل در رایانه')


def prepare_environment(tmp: Path) -> None:
    """مسیرهای اجرا را پیش از import برنامه به پوشهٔ موقت می‌برد."""
    os.environ.update({
        'DATABASE_PATH': str(tmp / 'views.db'),
        'BACKUP_DIR': str(tmp / 'backups'),
        'LOG_DIR': str(tmp / 'logs'),
        'UPLOAD_FOLDER': str(tmp / 'uploads'),
        'SECRET_KEY': 'student-view-test-secret-key',
        'SCHOOL_NAME': 'مدرسه آزمایشی شیوه نمایش',
        'PROGRAMMER_NAME': 'آزمون شیوه نمایش',
    })


def seed(conn) -> None:
    """کاربران و دانش‌آموزان آزمایشی می‌سازد."""
    from werkzeug.security import generate_password_hash

    now = datetime.now().isoformat(timespec='seconds')
    for personnel, full_name, role, teacher_code in (
            ('admin', 'مدیر آزمایشی', 'admin', None),
            (MANAGER, 'معاون آزمایشی', 'manager', None),
            (TEACHER, 'معلم آزمایشی', 'teacher', TEACHER)):
        conn.execute('DELETE FROM users WHERE personnel_number=?', (personnel,))
        conn.execute(
            '''INSERT INTO users(personnel_number,full_name,password_hash,role,is_active,
                                 must_change_password,teacher_code,permissions,created_at)
               VALUES(?,?,?,?,1,0,?,'',?)''',
            (personnel, full_name, generate_password_hash(PASSWORD), role, teacher_code, now),
        )

    students = (
        ('V-1', 'زهرا', 'آزمونی', 'فعال', 'کلاس ۱', TEACHER),
        ('V-2', 'علی', 'نمونه', 'فعال', 'کلاس ۱', None),
        ('V-3', 'مریم', 'آزمونپور', 'فعال', 'کلاس ۲', None),
        ('V-4', 'حسین', 'سایرین', 'فعال', 'کلاس ۲', None),
        ('V-5', 'رضا', 'بایگانی', 'فارغ‌التحصیل', 'کلاس ۱', None),
    )
    for code, first, last, status, class_name, teacher_code in students:
        conn.execute(
            '''INSERT INTO students(code,first_name,last_name,status,class_name,grade,teacher_code)
               VALUES(?,?,?,?,?,?,?)''',
            (code, first, last, status, class_name, 'پایه اول', teacher_code),
        )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description='آزمون شیوه‌های نمایش فهرست دانش‌آموزان')
    parser.add_argument('--keep', action='store_true', help='پوشهٔ موقت پاک نشود')
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix='student-view-test-'))
    prepare_environment(tmp)
    credentials = ROOT / 'initial_credentials.txt'
    credentials_existed = credentials.exists()

    from school_app import app
    from school_app.database import get_db

    if not credentials_existed and credentials.exists():
        credentials.unlink()  # این فایل مربوط به دیتابیس واقعی است

    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    with app.app_context():
        with get_db() as conn:
            seed(conn)

    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = '') -> None:
        if condition:
            print(f'  ✓ {label}')
        else:
            failures.append(f'{label} {detail}')
            print(f'  ✗ {label} {detail}')

    def login(personnel: str):
        client = app.test_client()
        response = client.post('/login', data={'personnel_number': personnel, 'password': PASSWORD})
        assert response.status_code in (200, 302), response.status_code
        with client.session_transaction() as session_data:
            token = session_data.get('_csrf_token', '')
            user_id = session_data.get('user_id')
        return client, token, user_id

    def dashboard(client) -> str:
        response = client.get('/')
        assert response.status_code == 200, response.status_code
        return response.get_data(as_text=True)

    def save_view(client, token, payload):
        return client.post('/student-view', json=payload,
                           headers={'X-CSRF-Token': token})

    manager, manager_token, manager_id = login(MANAGER)
    teacher, teacher_token, teacher_id = login(TEACHER)
    manager_key = f'student_card_view:{manager_id}'
    teacher_key = f'student_card_view:{teacher_id}'

    print('کنترل میزان اطلاعات دانش‌آموزان')
    home = dashboard(manager)
    check('کانتینر فهرست با حالت پیش‌فرض «استاندارد» رندر می‌شود',
          'class="student-list" data-view="md"' in home, 'data-view=md پیدا نشد')
    settings_page = manager.get('/my-settings').get_data(as_text=True)
    for key, label in zip(VIEWS, LABELS):
        check(f'گزینهٔ پیش‌فرض «{label}» در تنظیمات هست',
              f'<option value="{key}"' in settings_page and f'>{label}</option>' in settings_page,
              'گزینه در تنظیمات پیدا نشد')
    check('کنترل «میزان نمایش اطلاعات» از index حذف شده است',
          'میزان نمایش اطلاعات' not in home and 'data-set-view' not in home
          and 'studentViewSelect' not in home)
    check('نمای پیش‌فرض در صفحهٔ تنظیمات قابل تغییر است',
          'name="student_view"' in settings_page and 'value="md" selected' in settings_page)
    css = (ROOT / 'static' / 'index.css').read_text(encoding='utf-8')
    check('حالت نام و کد، اطلاعات ثانویه را پنهان می‌کند',
          '.student-list[data-view="xs"] .student-card__meta { display: none !important; }' in css)
    check('حالت خلاصه، فیلدهای سیدا و جنسیت را پنهان می‌کند',
          '.student-list[data-view="sm"] .student-card__meta-item--sida' in css
          and '.student-list[data-view="sm"] .student-card__meta-item--gender' in css)
    check('نمای موبایل از فیلدهای جداگانه و کارت خلاصه استفاده می‌کند',
          '.student-list .student-card__mobile-hidden' in css
          and '.student-list[data-view="table"] .student-table-wrap { display: none !important; }' in css
          and '.student-list[data-view="table"] .student-grid { display: grid !important; }' in css)
    check('جست‌وجو از ابتدای داشبورد برداشته و داخل فیلترهای تاشو قرار گرفته است',
          home.index('dashboard-quick-actions') < home.index('dashboard-search-section')
          < home.index('id="q"') < home.index('id="students-heading"'),
          'ترتیب اقدام/فیلتر/فهرست نادرست است')
    check('فیلترهای پیشرفته در حالت عادی بسته هستند',
          'dashboard-advanced-filters" open' not in home,
          'فیلترهای پیشرفته به‌صورت باز رندر شدند')
    check('یادآورها مودال خودکار ندارند', 'eventAlertLayer' not in home and 'data-close-events' not in home,
          'کد مودال قدیمی هنوز رندر می‌شود')
    check('درخواست اجازهٔ اعلان فقط داخل رویداد کلیک است',
          home.index("button.addEventListener('click'") < home.index('Notification.requestPermission()'),
          'درخواست اعلان پیش از کلیک کاربر اجرا می‌شود')
    check('مدیر اقدام‌های متناسب با نقش را می‌بیند',
          'ثبت دانش‌آموز' in home and 'تقویم و کارها' in home and 'ثبت سریع حضور' in home)
    check('هم کارت‌ها و هم جدول در DOM هستند تا تعویض بدون بارگذاری انجام شود',
          'student-grid' in home and 'class="student-table"' in home,
          'ساختار کارت/جدول ناقص است')

    print('یادآورهای درون‌صفحه و اعلان اختیاری')
    from school_app.dates import get_today_jalali
    from school_app.student_dashboard import _task_alerts

    jy, jm, jd = get_today_jalali()
    today = f'{jy:04d}/{jm:02d}/{jd:02d}'
    with app.app_context():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO events(title,date,time,type,priority) VALUES(?,?,?,?,?)",
                ('رویداد فوری آزمون', today, '23:59', 'آزمون', 'فوری'),
            )
            conn.execute(
                "INSERT INTO tasks(title,due_date,due_time,priority,status,alarm_enabled,alarm_minutes,category) "
                "VALUES(?,?,?,'عادی','باز',0,30,'آزمون')",
                ('کار بدون اعلان', today, '23:59'),
            )
            conn.execute(
                "INSERT INTO tasks(title,due_date,due_time,priority,status,alarm_enabled,alarm_minutes,category) "
                "VALUES(?,?,?,'عادی','باز',1,30,'آزمون')",
                ('کار با اعلان', today, '23:59'),
            )
            conn.commit()
        alarm_rows = [task for task in _task_alerts() if task['alarm_at_iso']]
    reminder_home = dashboard(manager)
    check('هشدار فوری در بخش درون‌صفحه‌ای دیده می‌شود، نه مودال',
          'رویداد فوری آزمون' in reminder_home
          and 'dashboard-upcoming dashboard-section" open' in reminder_home
          and 'eventAlertLayer' not in reminder_home)
    check('دکمهٔ اجازهٔ اعلان فقط وقتی آلارم فعال وجود دارد نمایش داده می‌شود',
          'id="enableDashboardNotifications"' in reminder_home
          and [task['title'] for task in alarm_rows] == ['کار با اعلان'])

    print('نمایش جدولی کامل')
    rows = home.count('<tr class="student-row"')
    cards = home.count('<article class="student-card"')
    check('تعداد ردیف جدول برابر کارت‌هاست (۴ دانش‌آموز فعال)',
          rows == cards == 4, f'rows={rows} cards={cards}')
    check('دانش‌آموز غیرفعال در هیچ کدام از دو نمایش نیست', 'رضا' not in home)
    table_head = home.split('<thead>', 1)[1].split('</thead>', 1)[0]
    for heading in ('نام و نام خانوادگی', 'کد دانش‌آموزی', 'پایه', 'کلاس مدرسه',
                    'کلاس سیدا', 'جنسیت', 'معلم منتسب', 'وضعیت پرونده', 'اقدامات', 'عکس'):
        check(f'ستون «{heading}» در جدول هست', heading in table_head, 'ستون جدول ناقص است')
    check('جدول از مرتب‌سازی تعاملی و صفحه‌بندی پشتیبانی می‌کند',
          'data-table-sort="name"' in table_head
          and 'data-table-page-previous' in home and 'data-table-page-next' in home)
    check('ستون‌های شخصی‌سازی‌شده می‌توانند هنگام پیمایش ثابت بمانند',
          'student-table__column--pinned' in home and 'data-table-heading="name"' in table_head)
    check('دکمه‌های اقدامات در ردیف جدول هستند',
          'پرونده کامل' in home.split('<tbody>', 1)[-1]
          and 'ویرایش' in home.split('<tbody>', 1)[-1], 'اقدامات ردیف کم است')

    print('ذخیرهٔ حالت انتخابی در app_settings')
    saved = save_view(manager, manager_token, {'view': 'xl'})
    check('ذخیرهٔ حالت «خیلی درشت» موفق است',
          saved.status_code == 200 and saved.get_json().get('view') == 'xl',
          f'status={saved.status_code} body={saved.get_data(as_text=True)[:120]}')
    with app.app_context():
        with get_db() as conn:
            row = conn.execute('SELECT value FROM app_settings WHERE key=?', (manager_key,)).fetchone()
    check('کلید per-user در app_settings نوشته شده است',
          bool(row) and row['value'] == 'xl', f'row={dict(row) if row else None}')
    manager_home = dashboard(manager)
    check('انتخاب مدیر در بازدید بعدی حفظ می‌شود',
          'class="student-list" data-view="xl"' in manager_home)
    check('حالت «خیلی درشت» در index حفظ می‌شود',
          'class="student-list" data-view="xl"' in manager_home)
    updated_settings = manager.get('/my-settings').get_data(as_text=True)
    check('انتخاب حالت در صفحهٔ تنظیمات هم حفظ می‌شود',
          'name="student_view"' in updated_settings
          and '<option value="xl" selected>خیلی درشت</option>' in updated_settings)
    print('جداسازی کاربران و بازگشت به پیش‌فرض')
    check('معلم حالت پیش‌فرض را می‌بیند', 'data-view="md"' in dashboard(teacher))
    teacher_saved = save_view(teacher, teacher_token, {'view': 'table'})
    check('ذخیرهٔ حالت برای معلم مجاز است (endpoint مشترک)',
          teacher_saved.status_code == 200, f'status={teacher_saved.status_code}')
    check('جدول برای معلم اعمال می‌شود', 'data-view="table"' in dashboard(teacher))
    check('بعد از ذخیرهٔ معلم، حالت مدیر دست‌نخورده می‌ماند',
          'data-view="xl"' in dashboard(manager))
    with app.app_context():
        with get_db() as conn:
            conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) '
                         'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                         (manager_key, '<script>alert(1)</script>'))
            conn.commit()
    check('مقدار خراب در دیتابیس به پیش‌فرض «استاندارد» برمی‌گردد',
          'class="student-list" data-view="md"' in dashboard(manager))
    with app.app_context():
        with get_db() as conn:
            conn.execute('DELETE FROM app_settings WHERE key=?', (manager_key,))
            conn.commit()

    print('درخواست‌های نامعتبر')
    bad = save_view(manager, manager_token, {'view': '../../etc/passwd'})
    check('مقدار خارج از فهرست ۴۰۰ می‌گیرد', bad.status_code == 400, str(bad.status_code))
    no_csrf = manager.post('/student-view', json={'view': 'xs'})
    check('درخواست بدون توکن CSRF رد می‌شود', no_csrf.status_code == 400, str(no_csrf.status_code))
    check('بعد از درخواست‌های نامعتبر چیزی ذخیره نشده است',
          'class="student-list" data-view="md"' in dashboard(manager))

    print('─' * 70)
    if failures:
        for item in failures:
            print(f'  ✗ {item}')
        print(f'نتیجه: {len(failures)} بررسی شکست خورد از مجموع بررسی‌ها (کد خروج ۱).')
        code = 1
    else:
        print('نتیجه: همهٔ بررسی‌های شیوهٔ نمایش فهرست سبز بود.')
        code = 0

    if args.keep:
        print(f'پوشهٔ موقت نگه داشته شد: {tmp}')
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
