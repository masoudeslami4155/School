#!/usr/bin/env python
"""Isolated tests for personal dashboard, accessibility, and color preferences."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

PASSWORD = 'Prefs!12345'
MANAGER = 'P-M-1001'
TEACHER = 'P-T-1001'


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='user-ui-preferences-test-'))
    os.environ.update({
        'DATABASE_PATH': str(tmp / 'preferences.db'),
        'BACKUP_DIR': str(tmp / 'backups'),
        'LOG_DIR': str(tmp / 'logs'),
        'UPLOAD_FOLDER': str(tmp / 'uploads'),
        'SECRET_KEY': 'user-ui-preferences-test-secret',
        'SCHOOL_NAME': 'مدرسه آزمایشی تنظیمات',
        'PROGRAMMER_NAME': 'آزمون تنظیمات رابط',
    })
    credentials = ROOT / 'initial_credentials.txt'
    credentials_existed = credentials.exists()

    from werkzeug.security import generate_password_hash
    from school_app import app
    from school_app.database import get_db
    from school_app.dates import get_today_jalali
    from school_app.student_dashboard import DEFAULT_STUDENT_VIEW, load_student_view
    from school_app.user_preferences import (
        COLOR_PALETTES,
        DEFAULT_DARK_COLORS,
        DEFAULT_PREFERENCES,
        USER_PREFERENCES_KEY,
        load_user_preferences,
        sanitize_preferences,
    )

    if not credentials_existed and credentials.exists():
        credentials.unlink()
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)

    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = '') -> None:
        if condition:
            print(f'  ✓ {label}')
        else:
            failures.append(f'{label} {detail}')
            print(f'  ✗ {label} {detail}')

    now = datetime.now().isoformat(timespec='seconds')
    with app.app_context():
        with get_db() as conn:
            for personnel, name, role, teacher_code in (
                ('admin', 'مدیر تنظیمات', 'admin', None),
                (MANAGER, 'معاون تنظیمات', 'manager', None),
                (TEACHER, 'معلم تنظیمات', 'teacher', TEACHER),
            ):
                conn.execute('DELETE FROM users WHERE personnel_number=?', (personnel,))
                conn.execute(
                    '''INSERT INTO users(personnel_number,full_name,password_hash,role,is_active,
                                         must_change_password,teacher_code,permissions,created_at)
                       VALUES(?,?,?,?,1,0,?,'',?)''',
                    (personnel, name, generate_password_hash(PASSWORD), role, teacher_code, now),
                )
            conn.execute(
                '''INSERT INTO students(code,first_name,last_name,status,class_name,grade,sida_class,gender,teacher_code)
                   VALUES('P-1','نرگس','آزمایشی','فعال','کلاس الف','پایه دوم','الف-۲','دختر',?)''',
                (TEACHER,),
            )
            conn.execute(
                '''INSERT INTO students(code,first_name,last_name,status,class_name,grade,sida_class,gender)
                   VALUES('P-2','آرمان','آزمایشی','فعال','کلاس ب','پایه سوم','ب-۳','پسر')''',
            )
            jy, jm, jd = get_today_jalali()
            conn.execute(
                '''INSERT INTO events(title,date,time,description,type,priority)
                   VALUES('آزمون یادآور فوری',?,'23:59','آزمون','یادآور','فوری')''',
                (f'{jy:04d}/{jm:02d}/{jd:02d}',),
            )
            conn.commit()

    def login(personnel: str):
        client = app.test_client()
        response = client.post('/login', data={'personnel_number': personnel, 'password': PASSWORD})
        assert response.status_code in (200, 302), response.status_code
        with client.session_transaction() as sess:
            return client, sess.get('_csrf_token', ''), sess.get('user_id')

    def user_prefs(user_id):
        with app.app_context():
            return load_user_preferences(user_id)

    def user_view(user_id):
        with app.app_context():
            with get_db() as conn:
                return load_student_view(conn, user_id)

    admin, _admin_token, admin_id = login('admin')
    manager, manager_token, manager_id = login(MANAGER)
    teacher, _teacher_token, teacher_id = login(TEACHER)

    print('دسترسی و گزینه‌های تنظیمات برای هر سه نقش')
    settings_bodies = {}
    for label, client in (('مدیر', admin), ('معاون', manager), ('معلم', teacher)):
        response = client.get('/my-settings')
        body = response.get_data(as_text=True)
        settings_bodies[label] = body
        check(f'{label} صفحهٔ تنظیمات را می‌بیند', response.status_code == 200,
              f'status={response.status_code}')
        check(f'{label} انتخاب جداگانهٔ کارت، جدول و موبایل را می‌بیند',
              'name="student_card_fields"' in body and 'name="student_table_fields"' in body
              and 'name="student_mobile_fields"' in body)
        check(f'{label} الگوها، پالت‌های آماده و دسترس‌پذیری را می‌بیند',
              'apply_preset' in body and body.count('name="apply_color_palette"') == len(COLOR_PALETTES)
              and 'name="text_scale"' in body and 'name="line_spacing"' in body
              and 'name="motion"' in body and 'dark_color_button' in body
              and 'contrastStatus' in body)
        check(f'{label} تنظیمات کامل جدول را می‌بیند',
              'name="student_table_order"' in body and 'name="student_table_pinned"' in body
              and 'name="student_table_width_name"' in body
              and 'name="student_table_sort"' in body
              and 'name="student_table_sort_direction"' in body
              and 'name="student_table_page_size"' in body)
    check('اقدام‌های سریع نقش‌محور: معلم گزینه‌های مدیریتی را نمی‌بیند',
          'name="quick_actions"' in settings_bodies['معلم']
          and 'id="quick-action-attendance_students"' in settings_bodies['معلم']
          and 'id="quick-action-student_columns"' in settings_bodies['معلم']
          and 'id="quick-action-add_student"' not in settings_bodies['معلم']
          and 'id="quick-action-calendar"' not in settings_bodies['معلم'])

    print('پالت‌های آماده و اعمال سراسری')
    def relative_luminance(color):
        rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                  for channel in rgb]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast_ratio(foreground, background):
        first, second = relative_luminance(foreground), relative_luminance(background)
        return (max(first, second) + 0.05) / (min(first, second) + 0.05)

    contrast_pairs = (
        ('text', 'background'), ('text', 'surface'), ('button_text', 'button'),
        ('secondary_button_text', 'secondary_button'), ('table_header_text', 'table_header'),
        ('text', 'table_row'), ('text', 'table_row_alt'),
    )
    all_palettes_have_contrast = all(
        contrast_ratio(palette[mode][foreground], palette[mode][background]) >= 4.5
        for palette in COLOR_PALETTES.values()
        for mode in ('light', 'dark')
        for foreground, background in contrast_pairs
    )
    check('یازده پالت درخواستی Figma در فهرست موجود است',
          {'blooming_romance','desert_dusk','lavender_fields','country_garden','cherry_blossom',
           'sunny_day','bubblegum_pop','electric_kiwi','alchemical_reaction','electropop','neon_noir'} <= set(COLOR_PALETTES))
    check('شش پالت آمادهٔ مجزا برای روز و شب وجود دارد',
          len(COLOR_PALETTES) >= 6
          and len({tuple(palette['light'].values()) for palette in COLOR_PALETTES.values()}) == len(COLOR_PALETTES))
    check('ترکیب‌های متن و دکمه در تمام پالت‌ها حداقل کنتراست ۴٫۵:۱ دارند', all_palettes_have_contrast)
    palette_applied = manager.post('/my-settings', data={
        '_csrf_token': manager_token, 'apply_color_palette': 'forest',
    })
    forest_prefs = user_prefs(manager_id)
    forest_dashboard = manager.get('/').get_data(as_text=True)
    forest_form = manager.get('/add').get_data(as_text=True)
    forest_print_page = manager.get('/contact-book/print').get_data(as_text=True)
    palette_css = manager.get('/static/user_preferences.css').get_data(as_text=True)
    check('پالت انتخابی هم‌زمان رنگ‌های روز و شب را ذخیره می‌کند',
          palette_applied.status_code == 302 and forest_prefs['color_palette'] == 'forest'
          and forest_prefs['colors'] == COLOR_PALETTES['forest']['light']
          and forest_prefs['dark_colors'] == COLOR_PALETTES['forest']['dark'])
    check('رنگ پالت در صفحهٔ اصلی و فرم ثبت‌نامِ مبتنی بر base.html اعمال می‌شود',
          'data-ui-palette="forest"' in forest_dashboard
          and '--primary:#176b4d' in forest_dashboard
          and 'user_preferences.css' in forest_dashboard
          and 'data-ui-palette="forest"' in forest_form
          and '--primary:#176b4d' in forest_form)
    standalone_templates = []
    for template_path in (ROOT / 'templates').rglob('*.html'):
        template_body = template_path.read_text(encoding='utf-8-sig', errors='ignore')
        # This template is never served as a browser page: it is an offline PDF input.
        if template_path.name == 'statistics_export.html':
            check('قالب PDF آفلاین فونت و CSS تعبیه‌شده دارد و منبع خارجی بارگذاری نمی‌کند',
                  'data:font/ttf;base64' in template_body and 'embedded_css' in template_body
                  and 'Content-Security-Policy' in template_body and '<script' not in template_body
                  and '<link' not in template_body)
            continue
        if '<html' in template_body.lower() and "extends 'base.html'" not in template_body \
                and 'extends "base.html"' not in template_body and template_path.name != 'base.html':
            standalone_templates.append(template_body)
    all_standalone_templates_themable = bool(standalone_templates) and all(
        "partials/user_palette_head.html" in template_body for template_body in standalone_templates
    )
    check('پالت در همهٔ قالب‌های مستقل (از ورود تا پیش‌نمایش چاپ) بارگذاری می‌شود',
          all_standalone_templates_themable)
    check('پالت در صفحهٔ چاپ مستقل هم به نمایشگر می‌رسد، بدون حذف CSS چاپ',
          'root.dataset.uiPalette = "forest"' in forest_print_page
          and '--primary: #176b4d;' in forest_print_page
          and 'user_preferences.css' in forest_print_page
          and '@media print' in palette_css)
    check('انتخاب پالت یک حساب به مدیر و معلم نشت نمی‌کند',
          user_prefs(admin_id) == DEFAULT_PREFERENCES
          and user_prefs(teacher_id) == DEFAULT_PREFERENCES)
    invalid_palette = manager.post('/my-settings', data={
        '_csrf_token': manager_token, 'apply_color_palette': 'not-a-palette',
    })
    check('شناسهٔ پالت خارج از فهرست رد می‌شود', invalid_palette.status_code == 400)

    print('تفکیک کارت، جدول و موبایل؛ اعمال در داشبورد')
    custom_form = {
        '_csrf_token': manager_token,
        'student_card_fields': ['name', 'class_name', 'gender'],
        'student_table_fields': ['name', 'code', 'grade', 'class_name', 'teacher'],
        'student_table_order': ['teacher', 'code', 'name', 'grade', 'class_name', 'photo', 'sida_class', 'gender', 'status'],
        'student_table_pinned': ['name', 'teacher'],
        'student_table_width_name': 'wide',
        'student_table_width_teacher': 'compact',
        'student_table_sort': 'grade',
        'student_table_sort_direction': 'desc',
        'student_table_page_size': '10',
        'student_mobile_fields': ['name', 'class_name'],
        'dashboard_cards': ['quick_actions'],
        'quick_actions': ['calendar', 'student_columns', 'attendance_quick'],
        'student_view': 'table',
        'ui_density': 'compact',
        'card_size': 'large',
        'visual_style': 'high_contrast',
        'font_family': 'tahoma',
        'text_scale': 'large',
        'line_spacing': 'relaxed',
        'motion': 'reduced',
        'color_button': '#c63322',
        'color_button_text': '#ffffff',
        'color_secondary_button': '#f0e8dc',
        'color_secondary_button_text': '#202020',
        'color_background': '#e8edf2',
        'color_surface': '#fffdf7',
        'color_text': '#202020',
        'color_border': '#b8c2cc',
        'color_table_header': '#243b53',
        'color_table_header_text': '#ffffff',
        'color_table_row': '#ffffff',
        'color_table_row_alt': '#eef2f5',
        'dark_color_button': '#4b5563',
        'dark_color_button_text': '#ffffff',
        'dark_color_secondary_button': '#263447',
        'dark_color_secondary_button_text': '#e6edf7',
        'dark_color_background': '#111923',
        'dark_color_surface': '#1b2636',
        'dark_color_text': '#e6edf7',
        'dark_color_border': '#344256',
        'dark_color_table_header': '#123d57',
        'dark_color_table_header_text': '#ffffff',
        'dark_color_table_row': '#1b2636',
        'dark_color_table_row_alt': '#202c3d',
    }
    saved = manager.post('/my-settings', data=custom_form)
    check('فرم تنظیمات معتبر ذخیره می‌شود', saved.status_code == 302)
    prefs = user_prefs(manager_id)
    check('فیلدهای کارت، جدول و موبایل جدا ذخیره می‌شوند',
          prefs['student_card_fields'] == ['name', 'class_name', 'gender']
          and prefs['student_table_fields'] == ['name', 'teacher', 'code', 'grade', 'class_name']
          and prefs['student_mobile_fields'] == ['name', 'class_name'], str(prefs))
    check('ترتیب، ستون‌های ثابت، عرض، مرتب‌سازی و صفحه‌بندی جدول ذخیره می‌شوند',
          prefs['student_table_order'][:5] == ['name', 'teacher', 'code', 'grade', 'class_name']
          and prefs['student_table_pinned'] == ['name', 'teacher']
          and prefs['student_table_column_widths']['name'] == 'wide'
          and prefs['student_table_column_widths']['teacher'] == 'compact'
          and (prefs['student_table_sort'], prefs['student_table_sort_direction'], prefs['student_table_page_size'])
          == ('grade', 'desc', 10))
    check('انتخاب و ترتیب اقدام‌های سریع حساب معاون ذخیره می‌شود',
          prefs['quick_actions'] == ['calendar', 'student_columns', 'attendance_quick'])
    custom_action_settings = manager.get('/my-settings').get_data(as_text=True)
    check('ترتیب ثبت‌شده در داشبورد در فهرست تنظیمات هم دیده می‌شود',
          custom_action_settings.index('id="quick-action-calendar"')
          < custom_action_settings.index('id="quick-action-student_columns"')
          < custom_action_settings.index('id="quick-action-attendance_quick"'))
    check('نام در هر سه نمای انتخابی اجباری باقی می‌ماند',
          all('name' in prefs[key] for key in ('student_card_fields', 'student_table_fields', 'student_mobile_fields')))
    check('تنظیم پیش‌فرض جدول جدا از تنظیمات رابط ذخیره می‌شود', user_view(manager_id) == 'table')
    check('تراکم، اندازه، سبک، قلم و گزینه‌های دسترس‌پذیری ذخیره می‌شوند',
          (prefs['card_size'], prefs['ui_density'], prefs['visual_style'], prefs['font_family'],
           prefs['text_scale'], prefs['line_spacing'], prefs['motion'])
          == ('large', 'compact', 'high_contrast', 'tahoma', 'large', 'relaxed', 'reduced'))
    check('رنگ‌های دستی و شناسهٔ پالت شخصی جداگانه ذخیره می‌شوند',
          prefs['color_palette'] == 'custom'
          and prefs['colors']['button'] == '#c63322'
          and prefs['dark_colors']['button'] == '#4b5563'
          and prefs['dark_colors']['text'] == '#e6edf7')

    manager_home = manager.get('/').get_data(as_text=True)
    head = manager_home.split('<thead>', 1)[1].split('</thead>', 1)[0]
    first_card = manager_home.split('<article class="student-card"', 1)[1].split('</article>', 1)[0]
    check('ستون‌های جدول فقط از انتخاب جدولی پیروی می‌کنند',
          'کد دانش‌آموزی' in head and 'پایه' in head and 'معلم منتسب' in head
          and 'جنسیت' not in head and 'کلاس سیدا' not in head and 'عکس' not in head)
    quick_action_html = manager_home.split('aria-label="اقدام‌های سریع"', 1)[1].split('</section>', 1)[0]
    check('اقدام‌های داشبورد دقیقاً مطابق انتخاب و ترتیب شخصی نمایش داده می‌شوند',
          quick_action_html.index('data-quick-action="calendar"')
          < quick_action_html.index('data-quick-action="student_columns"')
          < quick_action_html.index('data-quick-action="attendance_quick"'))
    check('مدیر از میان اقدام‌ها پیوندی خارج از مجوزهای خودش دریافت نمی‌کند',
          'data-quick-action="attendance_students"' not in quick_action_html
          and 'data-quick-action="calendar"' in quick_action_html)
    with manager.session_transaction() as manager_session:
        original_manager_permissions = manager_session.get('permissions')
        manager_session['permissions'] = '["calendar"]'
    restricted_settings = manager.get('/my-settings').get_data(as_text=True)
    restricted_dashboard = manager.get('/').get_data(as_text=True)
    with app.test_request_context():
        from flask import url_for
        restricted_student_columns_url = url_for('student_columns')
    restricted_route_status = manager.get(restricted_student_columns_url).status_code
    with manager.session_transaction() as manager_session:
        manager_session['permissions'] = original_manager_permissions
    restricted_actions = restricted_dashboard.split('aria-label="اقدام‌های سریع"', 1)[1].split('</section>', 1)[0]
    check('فهرست تنظیمات و داشبورد با مجوز سفارشی محدود می‌شوند و مسیر نامجاز ۴۰۳ می‌دهد',
          'id="quick-action-calendar"' in restricted_settings
          and 'id="quick-action-student_columns"' not in restricted_settings
          and 'data-quick-action="calendar"' in restricted_actions
          and 'data-quick-action="student_columns"' not in restricted_actions
          and restricted_route_status == 403)
    check('مرتب‌سازی و صفحه‌بندی پیش‌فرض جدول به HTML می‌رسند',
          'data-default-sort="grade"' in manager_home
          and 'data-default-direction="desc"' in manager_home
          and 'data-page-size="10"' in manager_home
          and 'data-sort-grade="پایه دوم"' in manager_home
          and 'data-table-sort="grade"' in head)
    check('کارت‌ها انتخاب جداگانهٔ خود را اعمال می‌کنند',
          'student-card__meta-item--gender' in first_card
          and 'student-card__meta-item--class' in first_card
          and 'student-card__assignment' not in first_card
          and 'کد دانش‌آموزی:' not in first_card
          and 'student-card__meta-item--grade' not in first_card)
    check('موبایل از کارت خلاصه استفاده می‌کند و فیلدهای اضافی را پنهان می‌سازد',
          'student-card__mobile-hidden' in first_card
          and '.student-list[data-view="table"] .student-table-wrap { display: none !important; }'
          in manager.get('/static/index.css').get_data(as_text=True))
    check('نمای جدول پیش‌فرض در رایانهٔ index حفظ می‌شود، کنترل نمایش در index نیست',
          'class="student-list" data-view="table"' in manager_home
          and 'میزان نمایش اطلاعات' not in manager_home and 'studentViewSelect' not in manager_home)
    check('کارت‌های اختیاری خاموش و هشدار فوری روشن باقی می‌ماند',
          'dashboard-overview' not in manager_home and 'dashboard-data-quality' not in manager_home
          and 'dashboard-upcoming' in manager_home and 'آزمون یادآور فوری' in manager_home
          and 'dashboard-upcoming dashboard-section" open' in manager_home)
    check('رنگ، حالت شب و گزینه‌های دسترس‌پذیری روی پوسته اعمال می‌شوند',
          'data-ui-density="compact"' in manager_home
          and 'data-ui-card-size="large"' in manager_home
          and 'data-ui-style="high_contrast"' in manager_home
          and 'data-ui-font="tahoma"' in manager_home
          and 'data-ui-text-scale="large"' in manager_home
          and 'data-ui-line-spacing="relaxed"' in manager_home
          and 'data-ui-motion="reduced"' in manager_home
          and '--user-dark-button-color:#4b5563' in manager_home
          and 'user_accessibility.js' in manager_home)
    check('پیوند تنظیمات در منوی مشترک و پنل جست‌وجو بسته است',
          'تنظیمات نمایش و رابط کاربری' in manager_home
          and 'dashboard-advanced-filters" open' not in manager_home)
    check('تنظیمات معاون به حساب معلم نشت نمی‌کند',
          user_prefs(teacher_id) == DEFAULT_PREFERENCES
          and 'data-ui-density="comfortable"' in teacher.get('/').get_data(as_text=True)
          and 'کد دانش‌آموزی' in teacher.get('/').get_data(as_text=True))

    preference_css = manager.get('/static/user_preferences.css').get_data(as_text=True)
    check('پالت شب قابل تنظیم و CSS حالت چاپ از ظاهر صفحه جدا است',
          'var(--user-dark-page-background' in preference_css and '@media print' in preference_css)
    check('CSS حالت کنتراست بالا، فاصلهٔ خطوط و حرکت کمتر وجود دارد',
          'data-ui-style="high_contrast"' in preference_css
          and 'data-ui-line-spacing="relaxed"' in preference_css
          and 'data-ui-motion="reduced"' in preference_css)

    with app.app_context():
        with get_db() as conn:
            settings_row = conn.execute(
                'SELECT value FROM app_settings WHERE key=?',
                (f'{USER_PREFERENCES_KEY}{manager_id}',),
            ).fetchone()
    check('کلید تنظیمات per-user در app_settings ساخته می‌شود', settings_row is not None)

    print('الگوهای آماده و بازنشانی بخشی')
    settings_page = manager.get('/my-settings').get_data(as_text=True)
    check('سه الگوی آماده روی صفحه هستند',
          all(f'name="apply_preset" value="{key}"' in settings_page
              for key in ('simple', 'teacher', 'management')))
    simple = manager.post('/my-settings', data={'_csrf_token': manager_token, 'apply_preset': 'simple'})
    simple_prefs = user_prefs(manager_id)
    check('الگوی ساده کارت و موبایل را خلاصه و جدول را کامل نگه می‌دارد',
          simple.status_code == 302
          and simple_prefs['student_card_fields'] == ['name', 'code', 'class_name']
          and set(simple_prefs['student_table_fields']) == set(DEFAULT_PREFERENCES['student_table_fields'])
          and simple_prefs['student_mobile_fields'] == ['name', 'code', 'class_name'])
    check('الگو رنگ روز/شب را حفظ و نمای فهرست را ذخیره می‌کند',
          simple_prefs['colors']['button'] == '#c63322'
          and simple_prefs['dark_colors']['button'] == '#4b5563'
          and user_view(manager_id) == 'sm')
    management = manager.post('/my-settings', data={'_csrf_token': manager_token, 'apply_preset': 'management'})
    check('الگوی مدیریتی جدول کامل را برای رایانه انتخاب می‌کند',
          management.status_code == 302 and user_view(manager_id) == 'table'
          and set(user_prefs(manager_id)['student_table_fields']) == set(DEFAULT_PREFERENCES['student_table_fields']))
    manager.post('/my-settings', data={'_csrf_token': manager_token, 'apply_preset': 'simple'})
    reset_table = manager.post('/my-settings', data={
        '_csrf_token': manager_token, 'reset_section': 'student_table_fields',
    })
    after_table_reset = user_prefs(manager_id)
    check('بازنشانی بخش جدول فقط تنظیمات جدول را به پیش‌فرض بازمی‌گرداند',
          reset_table.status_code == 302
          and after_table_reset['student_table_fields'] == DEFAULT_PREFERENCES['student_table_fields']
          and after_table_reset['student_table_order'] == DEFAULT_PREFERENCES['student_table_order']
          and after_table_reset['student_table_pinned'] == DEFAULT_PREFERENCES['student_table_pinned']
          and after_table_reset['student_table_column_widths'] == DEFAULT_PREFERENCES['student_table_column_widths']
          and after_table_reset['student_table_sort'] == DEFAULT_PREFERENCES['student_table_sort']
          and after_table_reset['student_table_page_size'] == DEFAULT_PREFERENCES['student_table_page_size']
          and after_table_reset['student_card_fields'] == ['name', 'code', 'class_name'])
    reset_quick_actions = manager.post('/my-settings', data={
        '_csrf_token': manager_token, 'reset_section': 'quick_actions',
    })
    with manager.session_transaction() as manager_session:
        manager_permissions_after_ui_reset = manager_session.get('permissions')
    check('بازنشانی اقدام‌های سریع، نقش و فهرست مجوزهای نشست را تغییر نمی‌دهد',
          reset_quick_actions.status_code == 302
          and user_prefs(manager_id)['quick_actions']
          == [key for key in DEFAULT_PREFERENCES['quick_actions'] if key != 'attendance_students']
          and manager_permissions_after_ui_reset == '')

    print('اعتبارسنجی ورودی‌ها، بازنشانی و CSRF')
    bad_form = {
        '_csrf_token': manager_token,
        'student_card_fields': ['bogus'],
        'student_table_fields': ['bogus'],
        'student_table_order': ['bogus', 'status', 'name'],
        'student_table_pinned': ['teacher', 'code', 'grade', 'status'],
        'student_table_width_name': 'url(javascript:alert(1))',
        'student_table_sort': 'evil',
        'student_table_sort_direction': 'sideways',
        'student_table_page_size': '999999',
        'student_mobile_fields': ['bogus'],
        'dashboard_cards': ['quick_actions'],
        'quick_actions': ['attendance_students', 'not-a-quick-action'],
        'student_view': 'javascript:alert(1)',
        'ui_density': 'url(javascript:alert(1))',
        'card_size': 'giant',
        'visual_style': 'script',
        'font_family': 'url(https://example.invalid)',
        'text_scale': 'huge',
        'line_spacing': 'script',
        'motion': 'fast-script',
        'color_button': 'red;--evil:url(javascript:alert(1))',
        'dark_color_button': 'red;--evil:url(javascript:alert(1))',
    }
    bad_save = manager.post('/my-settings', data=bad_form)
    sanitized = user_prefs(manager_id)
    check('فیلدهای خارج از allowlist حذف و نام حفظ می‌شود',
          bad_save.status_code == 302
          and sanitized['student_card_fields'] == ['name']
          and sanitized['student_table_fields'] == ['name']
          and sanitized['student_mobile_fields'] == ['name'])
    check('ترتیب و ستون ثابت معتبر می‌مانند و مقدارهای جدول نامعتبر به پیش‌فرض برمی‌گردند',
          sanitized['student_table_pinned'] == ['name']
          and set(sanitized['student_table_order']) == set(DEFAULT_PREFERENCES['student_table_order'])
          and sanitized['student_table_column_widths']['name'] == DEFAULT_PREFERENCES['student_table_column_widths']['name']
          and sanitized['student_table_sort'] == DEFAULT_PREFERENCES['student_table_sort']
          and sanitized['student_table_sort_direction'] == DEFAULT_PREFERENCES['student_table_sort_direction']
          and sanitized['student_table_page_size'] == DEFAULT_PREFERENCES['student_table_page_size'])
    crowded_pins = sanitize_preferences({
        'student_table_fields': ['name', 'photo', 'code', 'grade', 'class_name', 'teacher'],
        'student_table_pinned': ['name', 'photo', 'code', 'grade', 'class_name', 'teacher'],
    })
    check('سقف سه ستون ثابت در سمت سرور اجرا می‌شود و نام در آن اجباری است',
          len(crowded_pins['student_table_pinned']) == 3
          and crowded_pins['student_table_pinned'][0] == 'name'
          and set(crowded_pins['student_table_pinned']) <= set(crowded_pins['student_table_fields']))
    bad_action_dashboard = manager.get('/').get_data(as_text=True)
    check('ارسال دستی اقدام غیرمجاز هیچ پیوندی به داشبورد یا سطح دسترسی اضافه نمی‌کند',
          sanitized['quick_actions'] == []
          and 'data-quick-action="attendance_students"' not in bad_action_dashboard)
    check('CSS، قلم و اندازهٔ نامعتبر تزریق نمی‌شوند',
          sanitized['colors']['button'] == DEFAULT_PREFERENCES['colors']['button']
          and sanitized['dark_colors']['button'] == DEFAULT_DARK_COLORS['button']
          and sanitized['font_family'] == DEFAULT_PREFERENCES['font_family']
          and sanitized['text_scale'] == DEFAULT_PREFERENCES['text_scale']
          and user_view(manager_id) == DEFAULT_STUDENT_VIEW)
    invalid_preset = manager.post('/my-settings', data={
        '_csrf_token': manager_token, 'apply_preset': 'unknown',
    })
    check('الگوی آمادهٔ نامعتبر رد می‌شود', invalid_preset.status_code == 400)
    reset = manager.post('/my-settings', data={'_csrf_token': manager_token, 'reset_preferences': '1'})
    manager_default_preferences = {
        **DEFAULT_PREFERENCES,
        'quick_actions': [key for key in DEFAULT_PREFERENCES['quick_actions'] if key != 'attendance_students'],
    }
    check('بازنشانی همه، تنظیمات پیش‌فرض نقش معاون و نمای پیش‌فرض را برمی‌گرداند',
          reset.status_code == 302 and user_prefs(manager_id) == manager_default_preferences
          and user_view(manager_id) == DEFAULT_STUDENT_VIEW)
    no_csrf = manager.post('/my-settings', data={'ui_density': 'spacious'})
    check('POST بدون CSRF رد می‌شود', no_csrf.status_code == 400, str(no_csrf.status_code))
    check('تنظیم مدیر نیز دست‌نخورده و جدا می‌ماند', user_prefs(admin_id) == DEFAULT_PREFERENCES)

    if failures:
        print(f'نتیجه: {len(failures)} بررسی شکست خورد.')
        for failure in failures:
            print('  ✗', failure)
        code = 1
    else:
        print('نتیجه: ستون‌های جدا، موبایل، الگوها، دسترس‌پذیری، پالت‌ها و امنیت همگی موفق بود.')
        code = 0
    shutil.rmtree(tmp, ignore_errors=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
