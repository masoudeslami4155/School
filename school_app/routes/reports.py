from __future__ import annotations

from flask import render_template


def features_hub():
    features = [
        {'icon': '👨🎓', 'title': 'مدیریت دانشآموزان', 'text': 'ثبت، ویرایش، پرونده خوانا، حذف امن و چاپ فیلترشده.', 'endpoint': 'index'},
        {'icon': '🏫', 'title': 'کلاسبندی هوشمند', 'text': 'مدیریت همزمان کلاس مدرسه، کلاس سیدا و معلم.', 'endpoint': 'class_management'},
        {'icon': '🎂', 'title': 'محاسبه سن دانشآموزان', 'text': 'محاسبه خودکار سن سال، ماه و روز بر اساس تاریخ تولد شمسی.', 'endpoint': 'student_ages'},
        {'icon': '🧮', 'title': 'جدول ستونهای دلخواه', 'text': 'انتخاب آزاد ستونهای اطلاعات دانشآموزان، چاپ A4 و خروجی اکسل.', 'endpoint': 'student_columns'},
        {'icon': '🗂️', 'title': 'فهرست معلم و دانشآموزان', 'text': 'فهرستهای سیاهوسفید و خوانا؛ شش فهرست در هر برگه A4.', 'endpoint': 'teacher_student_lists'},
        {'icon': '🏷️', 'title': 'لیست چسباننده به پشت پرونده', 'text': 'برچسب فشردهٔ باریک؛ ۶ کارت در A4 افقی با خطوط برش.', 'endpoint': 'list_for_folders'},
        {'icon': '📜', 'title': 'گواهی اشتغال به تحصیل', 'text': 'صدور دستی یا تکمیل خودکار از پروندهٔ دانش‌آموز؛ همراه QR چاپی.', 'endpoint': 'student_certificate'},

        {'icon': '📋', 'title': 'حضور و غیاب', 'text': 'ثبت و حذف رکوردها با تاریخ شمسی و گزارش قابل چاپ.', 'endpoint': 'attendance_report'},

        {'icon': '💳', 'title': 'امور مالی', 'text': 'ثبت و ویرایش کامل پرداخت، سرویس و گزارش بدهکاران.', 'endpoint': 'monthly_service'},
        {'icon': '📊', 'title': 'آمار و گزارشها', 'text': 'فیلترهای مدیریتی و گزارشهای چاپی مناسب A4.', 'endpoint': 'statistics'},
        {'icon': '🏆', 'title': 'صورتجلسههای رسمی', 'text': 'تنظیم، ثبت، انتخاب حاضران و چاپ صورتجلسه شوراها.', 'endpoint': 'meetings'},

        {'icon': '📅', 'title': 'تقویم، کارها و آلارم', 'text': 'رویدادها، To-Do، مهلت، اولویت و هشدار مرورگر.', 'endpoint': 'calendar'},

        {'icon': '👩🏫', 'title': 'کارکنان و کاربران', 'text': 'کد ملی، شماره تماس， نقشها， دسترسی و بازیابی آفلاین رمز.', 'endpoint': 'teachers'},
    ]

    categories = [
        {'key': 'education',    'label': 'مدیریت آموزشی و دانشآموزان', 'icon': '📚', 'items': features[0:7]},
        {'key': 'attendance',   'label': 'حضور و غیاب',               'icon': '✅', 'items': features[7:8]},
        {'key': 'finance',      'label': 'امور مالی و گزارشات',        'icon': '💰', 'items': features[8:11]},
        {'key': 'calendar',     'label': 'برنامه‌ریزی و تقویم',         'icon': '📅', 'items': features[11:12]},
        {'key': 'users',        'label': 'کارکنان و کاربران',           'icon': '👥', 'items': features[12:13]},
    ]

    return render_template('features_hub.html', categories=categories)


def register(app):
    app.add_url_rule('/features', endpoint='features_hub', view_func=features_hub)
