#!/usr/bin/env python
"""آزمون تنظیمات پیشرفتهٔ دفترچه تلفن (``/contact-book`` و ``/contact-book/print``).

چه چیزی بررسی می‌شود
--------------------
* نمایش/مخفی‌کردن سربرگ جدول، نوار بخش، عنوان بخش‌ها و ستون ردیف
* انتخاب ستون‌های کارکنان و والدین (از جمله ستون‌های تازه: درس، کلاس، کد، خودرو)
* دسته‌بندی الفبایی/کلاس، فیلتر کلاس، فیلتر کارکنان و حذف ردیف‌های بی‌شماره
* شکل جای خالی، راه‌راه بودن و ردیف‌های خالی انتهای جدول
* سرصفحهٔ چاپ و شمارهٔ صفحه
* ذخیرهٔ تنظیمات پیش‌فرض کاربر و بازگشت به پیش‌فرض
* ورودی نامعتبر/مخرب (تزریق SQL و مقادیر خارج از فهرست) نباید چیزی را بشکند

کاملاً ایزوله است: دیتابیس، پشتیبان‌ها، لاگ‌ها و بارگذاری در پوشهٔ موقت.
کد خروج ۰ یعنی همهٔ بررسی‌ها سبز است؛ ۱ یعنی حداقل یک بررسی شکست خورد.

نمونه‌های اجرا::

    python tests/contact_book_settings_test.py
    python tests/contact_book_settings_test.py --brief
    python tests/contact_book_settings_test.py --keep
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for stream in (sys.stdout, sys.stderr):  # چاپ امن روی کنسول‌های ویندوزی
    try:
        stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

PASSWORD = 'Contact!12345'  # فقط برای دیتابیس موقت
PERSONNEL = 'M-7701'
FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa(text) -> str:
    return str(text).translate(FA_DIGITS)


def prepare_environment(tmp: Path) -> None:
    """مسیرهای اجرا را پیش از import برنامه به پوشهٔ موقت می‌برد."""
    os.environ.update({
        'DATABASE_PATH': str(tmp / 'contacts.db'),
        'BACKUP_DIR': str(tmp / 'backups'),
        'LOG_DIR': str(tmp / 'logs'),
        'UPLOAD_FOLDER': str(tmp / 'uploads'),
        'SECRET_KEY': 'contact-book-test-only-secret',
        'SCHOOL_NAME': 'مدرسهٔ آزمایشی دفترچه',
        'PROGRAMMER_NAME': 'آزمون تنظیمات',
    })


def build_manager(conn) -> None:
    from werkzeug.security import generate_password_hash

    conn.execute('DELETE FROM users WHERE personnel_number=?', (PERSONNEL,))
    conn.execute(
        '''INSERT INTO users(personnel_number,full_name,password_hash,role,is_active,
                             must_change_password,teacher_code,permissions,created_at)
           VALUES(?,?,?,'manager',1,0,NULL,'',?)''',
        (PERSONNEL, 'مسئول آزمایشی', generate_password_hash(PASSWORD),
         datetime.now().isoformat(timespec='seconds')),
    )
    conn.commit()


def insert_fixtures(conn) -> None:
    students = [
        # کد، نام، نام خانوادگی، پایه، کلاس، تلفن پدر، تلفن مادر، تلفن قدیمی
        # نام‌ها طوری انتخاب شده‌اند که زیررشتهٔ هیچ واژهٔ رایجی نباشند
        ('S-901', 'زهرا', 'نمونه‌الف', 'پایه اول', 'کلاس ۱', '09121110001', '09121110002', ''),
        ('S-902', 'علی', 'نمونه‌ب', 'پایه دوم', 'کلاس ۲', '09121110003', '', ''),
        ('S-903', 'مریم', 'نمونه‌پ', 'پایه دوم', 'کلاس ۲', '', '', ''),
        ('S-904', 'حسن', 'نمونه‌ث', 'پایه سوم', 'کلاس ۱۰', '', '', '09121110009'),
    ]
    for code, first, last, grade, class_name, father, mother, legacy in students:
        conn.execute(
            '''INSERT INTO students(code,first_name,last_name,status,grade,class_name,
                                   father_phone,mother_phone,parent_phone,gender)
               VALUES(?,?,?,'فعال',?,?,?,?,?,'پسر')''',
            (code, first, last, grade, class_name, father, mother, legacy),
        )
    teachers = [
        ('T-901', 'معلما', 'کادرالف', 'ریاضی', 'کلاس ۱', '09122220001'),
        ('T-902', 'معلمب', 'کادرب', '', '', ''),  # بدون شماره → با hide_empty حذف می‌شود
    ]
    for code, first, last, subject, class_name, phone in teachers:
        conn.execute(
            '''INSERT INTO teachers(code,first_name,last_name,subject,class_name,phone)
               VALUES(?,?,?,?,?,?)''',
            (code, first, last, subject, class_name, phone),
        )
    conn.execute(
        '''INSERT INTO service_driver_registry(driver_name,phone,vehicle,plate)
           VALUES('راننده‌تست','09123330001','پژو ۲۰۶','۱۲ ایران ۳۴۵')'''
    )
    conn.commit()


class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, title: str, ok: bool, detail: str = '') -> None:
        self.rows.append((title, bool(ok), detail))

    @property
    def failures(self) -> int:
        return sum(1 for _t, ok, _d in self.rows if not ok)

    def report(self, brief: bool) -> int:
        if brief and not self.failures:
            print(f'✓ تنظیمات دفترچه تلفن: {len(self.rows)} بررسی انجام شد — همه سبز.')
            return 0
        for title, ok, detail in self.rows:
            mark = '✓' if ok else '✗'
            print(f'  {mark} {title}')
            if not ok and detail:
                print(f'      {detail}')
        print('─' * 70)
        if self.failures:
            print(f'نتیجه: {self.failures} بررسی شکست خورد از {len(self.rows)} (کد خروج ۱).')
        else:
            print(f'نتیجه: همهٔ {len(self.rows)} بررسی سبز بود.')
        return 1 if self.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description='آزمون تنظیمات دفترچه تلفن')
    parser.add_argument('--brief', action='store_true', help='فقط خلاصهٔ یک‌خطی')
    parser.add_argument('--keep', action='store_true', help='پوشهٔ موقت پاک نشود')
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix='contact-book-test-'))
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
            build_manager(conn)
            insert_fixtures(conn)

    client = app.test_client()
    login = client.post('/login', data={'personnel_number': PERSONNEL, 'password': PASSWORD})
    if login.status_code not in (200, 302):
        print(f'! ورود آزمایشی ناموفق بود ({login.status_code}); آزمون متوقف شد.')
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    results = Results()

    def page(**params) -> str:
        response = client.get('/contact-book', query_string=params)
        if response.status_code != 200:
            raise AssertionError(f'پاسخ {response.status_code} برای {params}')
        return response.get_data(as_text=True)

    def printed(**params) -> str:
        response = client.get('/contact-book/print', query_string=params)
        if response.status_code != 200:
            raise AssertionError(f'پاسخ {response.status_code} برای چاپ {params}')
        return response.get_data(as_text=True)

    def multi(name, keys):
        """پارامترهای یک گروه چک‌باکس (با نشانهٔ حضور)."""
        return {name: list(keys), f'{name}__set': '1'}

    def book(text: str) -> str:
        """فقط بخش دفترچه (بدون نوار ابزار) برای بررسی‌های دقیق."""
        return text.split('<div id="bookHost"', 1)[-1]

    # ----------------------------------------------------------------- پایه
    base = page()
    results.check('صفحهٔ دفترچه با پیش‌فرض‌ها رندر می‌شود',
                  '<div id="bookHost"' in base and '<thead' in base
                  and '<div class="section-title"' in base,
                  'ساختار پایهٔ صفحه پیدا نشد')
    results.check('سربرگ جدول و ستون ردیف در حالت پیش‌فرض',
                  '>ردیف</th>' not in base and '>نام و نام خانوادگی</th>' in base,
                  'سربرگ پیش‌فرض درست نیست')
    toolbar_form = base.split('<form id="cbTools"', 1)[-1].split('</form>', 1)[0]
    results.check('فرم تنظیمات (GET) توکن CSRF را وارد آدرس نمی‌کند',
                  '_csrf_token' not in toolbar_form and 'name="_csrf_token"' in base,
                  'توکن در فرم GET دیده شد یا فرم ذخیره توکن ندارد')

    # ------------------------------------------------------- کلیدهای نمایش
    hidden_header = page(table_header='no')
    results.check('مخفی‌کردن سربرگ جدول', '<thead' not in hidden_header,
                  'با table_header=no هنوز سربرگ چاپ می‌شود')

    hidden_section = page(section_title='no')
    results.check('مخفی‌کردن نوار بخش (حرف/کلاس)',
                  '<div class="section-title"' not in hidden_section,
                  'نوار بخش مخفی نشد')

    hidden_titles = page(titles='no')
    results.check('مخفی‌کردن عنوان بخش‌ها', '<h1 class="book-title"' not in hidden_titles,
                  'عنوان بخش‌ها مخفی نشد')

    numbered = page(row_no='yes')
    results.check('ستون ردیف با شمارهٔ پیوسته',
                  f'>ردیف</th>' in book(numbered) and 'class="col-no"' in book(numbered)
                  and f'>{fa(1)}<' in book(numbered),
                  'ستون ردیف ساخته نشد')

    # --------------------------------------------------------- انتخاب ستون
    staff_cols = page(**multi('staff_cols', ['name', 'phone', 'subject']))
    results.check('ستون اختیاری کارکنان (درس) اضافه می‌شود',
                  '>درس</th>' in staff_cols and 'ریاضی' in staff_cols
                  and '>کد پرسنلی</th>' not in staff_cols,
                  'ستون درس یا حذف کد پرسنلی درست انجام نشد')

    parent_cols = page(**multi('parent_cols', ['name', 'mother']))
    results.check('حذف ستون پدر از جدول والدین',
                  '>مادر</th>' in parent_cols and '>پدر</th>' not in parent_cols
                  and fa('09121110001') not in parent_cols,
                  'ستون پدر با وجود حذف، چاپ شده است')

    parent_class = page(**multi('parent_cols', ['name', 'father', 'mother', 'class']))
    results.check('افزودن ستون کلاس به جدول والدین', '>کلاس</th>' in parent_class,
                  'ستون کلاس ساخته نشد')

    fallback = page()
    results.check('پرونده‌های قدیمی با یک شماره (parent_phone) کامل چاپ می‌شوند',
                  fa('09121110009') in fallback,
                  'شمارهٔ قدیمی روی دفترچه نیامد')

    # ------------------------------------------------------ ترتیب و فیلترها
    by_class = book(page(group_by='class'))
    order_ok = (by_class.find(f'>{fa("کلاس ۱")}<') < by_class.find(f'>{fa("کلاس ۲")}<')
                < by_class.find(f'>{fa("کلاس ۱۰")}<') != -1)
    results.check('دسته‌بندی بر اساس کلاس با مرتب‌سازی طبیعی', order_ok,
                  'ترتیب کلاس‌ها طبیعی نیست (کلاس ۱۰ باید بعد از کلاس ۲ بیاید)')

    class_two = book(page(class_filter='کلاس ۲'))
    results.check('فیلتر کلاس (فقط والدین کلاس ۲)',
                  'نمونه‌ب' in class_two and 'نمونه‌الف' not in class_two,
                  'فیلتر کلاس درست اعمال نشد')

    drivers = page(staff_filter='drivers')
    results.check('فیلتر کارکنان: فقط رانندگان سرویس',
                  fa('09123330001') in drivers and fa('09122220001') not in drivers,
                  'فیلتر رانندگان درست نیست')

    teachers = page(staff_filter='teachers')
    results.check('فیلتر کارکنان: فقط معلمان و کارکنان',
                  fa('09122220001') in teachers and fa('09123330001') not in teachers,
                  'فیلتر معلمان درست نیست')

    no_phone = book(page(hide_empty='yes'))
    results.check('حذف ردیف‌های بدون شماره',
                  'نمونه‌پ' not in no_phone and 'معلمب' not in no_phone
                  and 'نمونه‌ب' in no_phone,
                  'ردیف‌های بی‌شماره حذف نشدند یا ردیف‌های دارای شماره هم حذف شدند')

    # ------------------------------------------------------ نمایش سلول‌ها
    dashed = book(page(empty_style='dash'))
    results.check('شکل جای خالی: خط تیره',
                  '<span class="cell-empty">—</span>' in dashed, 'خط تیره چاپ نشد')

    blank = book(page(empty_style='blank'))
    results.check('شکل جای خالی: کاملاً خالی',
                  '<span class="cell-empty"' not in blank
                  and '<span class="blank-line"' not in blank,
                  'جای خالی هنوز نشانه دارد')

    plain = page(stripe='no')
    striped = page(stripe='yes')
    results.check('راه‌راه بودن ردیف‌ها خاموش/روشن می‌شود',
                  'class="contact-book no-stripe"' in plain
                  and 'class="contact-book"' in striped,
                  'کلاس راه‌راه درست اعمال نشد')

    extra = book(page(extra_rows='2'))
    sections = extra.count('<div class="section-title"')
    extra_rows = extra.count('class="extra-row"')
    results.check('ردیف‌های خالی انتهای هر جدول',
                  sections > 0 and extra_rows == sections * 2,
                  f'تعداد ردیف خالی: {extra_rows} برای {sections} بخش')

    # ------------------------------------------------------------ بخش‌ها
    same_page = book(page(parents_page='no'))
    new_page = book(page())
    results.check('والدین می‌توانند در ادامهٔ همان صفحه بیایند',
                  'new-page' not in same_page and 'new-page' in new_page,
                  'کلاس صفحهٔ جدید درست اعمال نشد')

    parents_only = book(page(section_filter='parents'))
    staff_only = book(page(section_filter='staff'))
    results.check('انتخاب بخش‌های دفترچه',
                  'رانندگان سرویس' not in parents_only
                  and 'والدین دانش‌آموزان' in parents_only
                  and 'والدین دانش‌آموزان' not in staff_only
                  and 'new-page' not in staff_only,
                  'فیلتر بخش‌ها درست عمل نکرد')

    # ------------------------------------------------------- صفحهٔ چاپ
    print_base = printed()
    print_no_header = printed(sheet_header='no')
    print_numbers = printed(page_num='yes')
    results.check('سرصفحهٔ مشخصات مدرسه در چاپ',
                  '<div class="sheet-header">' in print_base
                  and '<div class="sheet-header">' not in print_no_header,
                  'کلید sheet_header روی چاپ اثر نگذاشت')
    results.check('شمارهٔ صفحه در چاپ (اختیاری)',
                  '@bottom-center' in print_numbers and '@bottom-center' not in print_base,
                  'کلید page_num روی چاپ اثر نگذاشت')
    print_filtered = printed(class_filter='کلاس ۲', staff_filter='drivers')
    results.check('صفحهٔ چاپ پارامترهای فیلتر را نشان می‌دهد',
                  'کلاس: کلاس ۲' in print_filtered and 'فقط رانندگان سرویس' in print_filtered,
                  'خلاصهٔ فیلترها روی سرصفحهٔ چاپ نیامد')

    # ------------------------------------------------------ ذخیرهٔ پیش‌فرض
    token = re.search(r'name="_csrf_token" value="([^"]+)"', base)
    saved_ok, reset_ok = False, False
    if not token:
        results.check('ذخیرهٔ تنظیمات پیش‌فرض', False, 'توکن CSRF در صفحه پیدا نشد')
    else:
        payload = {'_csrf_token': token.group(1), 'action': 'save', 'cols': '2',
                   'font_size': '12', 'row_no': 'yes'}
        payload.update(multi('parent_cols', ['name', 'mother']))
        response = client.post('/contact-book', data=payload, follow_redirects=False)
        after_save = page()
        saved_ok = (response.status_code == 302
                    and '>مادر</th>' in after_save and '>پدر</th>' not in after_save
                    and 'value="2" selected' in after_save
                    and 'value="12"' in after_save
                    and 'پیش‌فرض ذخیره‌شده فعال است' in after_save)
        results.check('ذخیرهٔ تنظیمات پیش‌فرض کاربر (بار بعد بدون پارامتر هم می‌آید)', saved_ok,
                      f'کد پاسخ {response.status_code}؛ صفحهٔ بعدی تنظیمات ذخیره‌شده را نشان نداد')

        reset = client.post('/contact-book', data={
            '_csrf_token': token.group(1), 'action': 'reset'}, follow_redirects=False)
        after_reset = page()
        reset_ok = (reset.status_code == 302 and '>پدر</th>' in after_reset
                    and '>مادر</th>' in after_reset
                    and 'value="2" selected' not in after_reset
                    and 'پیش‌فرض ذخیره‌شده فعال است' not in after_reset)
        results.check('بازگشت به پیش‌فرض‌های کارخانه', reset_ok,
                      f'کد پاسخ {reset.status_code}؛ پیش‌فرض‌ها برنگشتند')

    # ------------------------------------------------- ورودی نامعتبر/مخرب
    hostile = page(cols='999', font_size='abc', empty_style='x;y', section_filter='nonsense',
                   class_filter="x' OR 1=1 --", group_by='bogus',
                   **multi('staff_cols', ['evil', '__class__']))
    with app.app_context():
        with get_db() as conn:
            students_left = conn.execute('SELECT COUNT(*) AS c FROM students').fetchone()['c']
    results.check('ورودی نامعتبر و مخرب بی‌اثر است',
                  students_left == 4 and '>شماره تماس</th>' in hostile
                  and 'value="4" selected' in hostile,
                  f'{students_left} دانش‌آموز در دیتابیس ماند (باید ۴ باشد)')

    code = results.report(args.brief)
    if args.keep:
        print(f'پوشهٔ موقت نگه داشته شد: {tmp}')
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
