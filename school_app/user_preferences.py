from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from .database import get_db


USER_PREFERENCES_KEY = 'ui_preferences:'

# These are dashboard student-list fields, not the database's full student
# profile. Student names remain visible so that every list is identifiable.
STUDENT_DISPLAY_FIELDS = (
    ('name', 'نام و نام خانوادگی'),
    ('photo', 'عکس'),
    ('code', 'کد دانش‌آموزی'),
    ('grade', 'پایه'),
    ('class_name', 'کلاس مدرسه'),
    ('sida_class', 'کلاس سیدا'),
    ('gender', 'جنسیت'),
    ('teacher', 'معلم منتسب'),
    ('status', 'وضعیت پرونده'),
)
STUDENT_DISPLAY_KEYS = tuple(key for key, _label in STUDENT_DISPLAY_FIELDS)
STUDENT_MOBILE_FIELDS = tuple(item for item in STUDENT_DISPLAY_FIELDS if item[0] != 'photo')
STUDENT_MOBILE_KEYS = tuple(key for key, _label in STUDENT_MOBILE_FIELDS)

# The existing display modes are retained, but are now chosen in settings,
# rather than from the dashboard's result bar.
STUDENT_VIEW_CHOICES = (
    ('xs', 'نام و کد'),
    ('sm', 'خلاصه'),
    ('md', 'استاندارد'),
    ('lg', 'درشت'),
    ('xl', 'خیلی درشت'),
    ('table', 'جدول کامل در رایانه'),
)

DASHBOARD_CARDS = (
    ('quick_actions', 'اقدام‌های سریع'),
    ('overview', 'نمای کلی و آمار مدرسه'),
    ('reminders', 'رویدادها و یادآورهای نزدیک'),
    ('data_quality', 'هشدار کیفیت داده‌ها'),
)
DASHBOARD_CARD_KEYS = tuple(key for key, _label in DASHBOARD_CARDS)

# A quick action is selectable only when its endpoint is already authorized for
# the current session. These IDs are display preferences, never grants.
QUICK_ACTIONS = (
    {
        'key': 'attendance_students', 'endpoint': 'attendance_students',
        'label': 'حضور و غیاب دانش‌آموزان', 'teacher_label': 'حضور و غیاب کلاس‌های من',
        'description': 'ثبت یا بررسی حضور امروز', 'icon': 'cil-check-circle',
        'roles': ('admin', 'teacher'), 'primary': True,
    },
    {
        'key': 'attendance_quick', 'endpoint': 'attendance_quick',
        'label': 'ثبت سریع حضور', 'description': 'ثبت غایبین در چند گام',
        'icon': 'cil-bolt', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'student_columns', 'endpoint': 'student_columns',
        'label': 'جدول دانش‌آموزان', 'teacher_label': 'جدول دانش‌آموزان',
        'description': 'انتخاب ستون‌های موردنیاز', 'icon': 'cil-list',
        'roles': ('admin', 'manager', 'teacher'),
    },
    {
        'key': 'teacher_student_lists', 'endpoint': 'teacher_student_lists',
        'label': 'فهرست کلاس‌ها', 'teacher_label': 'فهرست کلاس‌های من',
        'description': 'فهرست چاپی و کلاسی', 'icon': 'cil-people',
        'roles': ('admin', 'manager', 'teacher'),
    },
    {
        'key': 'add_student', 'endpoint': 'add_student',
        'label': 'ثبت دانش‌آموز', 'description': 'افزودن پروندهٔ جدید',
        'icon': 'cil-user-follow', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'calendar', 'endpoint': 'calendar',
        'label': 'تقویم و کارها', 'description': 'رویدادها و یادآورها',
        'icon': 'cil-calendar', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'statistics', 'endpoint': 'statistics',
        'label': 'آمار مدرسه', 'description': 'گزارش‌ها و نمای آماری',
        'icon': 'cil-chart', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'teachers', 'endpoint': 'teachers',
        'label': 'فهرست کارکنان', 'description': 'مشاهده و مدیریت معلمان',
        'icon': 'cil-briefcase', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'class_management', 'endpoint': 'class_management',
        'label': 'کلاس‌بندی', 'description': 'مدیریت کلاس‌های مدرسه',
        'icon': 'cil-school', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'contact_book', 'endpoint': 'contact_book',
        'label': 'دفترچه تلفن', 'description': 'اطلاعات تماس مدرسه',
        'icon': 'cil-address-book', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'data_quality', 'endpoint': 'data_quality',
        'label': 'کیفیت داده‌ها', 'description': 'پرونده‌های نیازمند تکمیل',
        'icon': 'cil-warning', 'roles': ('admin', 'manager'),
    },
    {
        'key': 'monthly_service', 'endpoint': 'monthly_service',
        'label': 'پرداخت و سرویس', 'description': 'پیگیری وضعیت سرویس ماهانه',
        'icon': 'cil-credit-card', 'roles': ('admin', 'manager'),
    },
)
QUICK_ACTION_KEYS = tuple(action['key'] for action in QUICK_ACTIONS)

TABLE_COLUMN_WIDTHS = (
    ('compact', 'فشرده'),
    ('normal', 'معمولی'),
    ('wide', 'عریض'),
)
TABLE_COLUMN_WIDTH_KEYS = tuple(key for key, _label in TABLE_COLUMN_WIDTHS)
TABLE_PIN_LIMIT = 3
DEFAULT_TABLE_COLUMN_WIDTHS = {
    'name': 'wide', 'photo': 'compact', 'code': 'normal', 'grade': 'compact',
    'class_name': 'normal', 'sida_class': 'normal', 'gender': 'compact',
    'teacher': 'normal', 'status': 'compact',
}
TABLE_SORT_FIELDS = tuple(item for item in STUDENT_DISPLAY_FIELDS if item[0] != 'photo')
TABLE_SORT_KEYS = tuple(key for key, _label in TABLE_SORT_FIELDS)
TABLE_SORT_DIRECTIONS = (('asc', 'صعودی'), ('desc', 'نزولی'))
TABLE_PAGE_SIZES = ((10, '۱۰ ردیف'), (20, '۲۰ ردیف'), (50, '۵۰ ردیف'), (100, '۱۰۰ ردیف'), (0, 'همهٔ ردیف‌ها'))

UI_DENSITIES = (
    ('compact', 'فشرده'),
    ('comfortable', 'استاندارد'),
    ('spacious', 'باز و درشت'),
)
CARD_SIZES = (
    ('small', 'کوچک'),
    ('medium', 'متوسط'),
    ('large', 'بزرگ'),
)
VISUAL_STYLES = (
    ('classic', 'کلاسیک'),
    ('soft', 'نرم و گرد'),
    ('minimal', 'ساده و کم‌سایه'),
    ('high_contrast', 'کنتراست بالا'),
)
FONT_FAMILIES = (
    ('vazirmatn', 'وزیرمتن (پیش‌فرض)'),
    ('tahoma', 'Tahoma'),
    ('segoe', 'Segoe UI'),
    ('arial', 'Arial'),
    ('noto', 'Noto Sans Arabic (در صورت نصب)'),
)
TEXT_SCALES = (
    ('normal', 'معمولی'),
    ('large', 'بزرگ'),
    ('larger', 'بسیار بزرگ'),
)
LINE_SPACINGS = (
    ('compact', 'فشرده'),
    ('comfortable', 'معمولی'),
    ('relaxed', 'باز و خوانا'),
)
MOTION_OPTIONS = (
    ('normal', 'حرکت معمولی'),
    ('reduced', 'حرکت کمتر'),
)

COLOR_FIELDS = (
    ('button', 'رنگ دکمهٔ اصلی'),
    ('button_text', 'متن دکمهٔ اصلی'),
    ('secondary_button', 'رنگ دکمهٔ فرعی'),
    ('secondary_button_text', 'متن دکمهٔ فرعی'),
    ('background', 'پس‌زمینهٔ صفحه'),
    ('surface', 'پس‌زمینهٔ کارت و باکس'),
    ('text', 'رنگ نوشتهٔ اصلی'),
    ('border', 'حاشیهٔ کارت و جدول'),
    ('table_header', 'سرستون جدول'),
    ('table_header_text', 'متن سرستون'),
    ('table_row', 'زمینهٔ ردیف جدول'),
    ('table_row_alt', 'زمینهٔ ردیف‌های یکی‌درمیان'),
)
COLOR_KEYS = tuple(key for key, _label in COLOR_FIELDS)
_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')

DEFAULT_LIGHT_COLORS: dict[str, str] = {
    'button': '#0b6374',
    'button_text': '#ffffff',
    'secondary_button': '#ffffff',
    'secondary_button_text': '#14213d',
    'background': '#eef3f7',
    'surface': '#ffffff',
    'text': '#14213d',
    'border': '#e4eaf2',
    'table_header': '#123d57',
    'table_header_text': '#ffffff',
    'table_row': '#ffffff',
    'table_row_alt': '#fbfcfe',
}
DEFAULT_DARK_COLORS: dict[str, str] = {
    'button': '#25a4b5',
    'button_text': '#07131a',
    'secondary_button': '#263447',
    'secondary_button_text': '#e6edf7',
    'background': '#111923',
    'surface': '#1b2636',
    'text': '#e6edf7',
    'border': '#344256',
    'table_header': '#123d57',
    'table_header_text': '#ffffff',
    'table_row': '#1b2636',
    'table_row_alt': '#202c3d',
}

DEFAULT_COLOR_PALETTE = 'ocean'
COLOR_PALETTES: dict[str, dict[str, Any]] = {
    'ocean': {
        'label': 'اقیانوس آبی',
        'description': 'آبی و فیروزه‌ای آرام؛ مناسب استفادهٔ روزانه',
        'light': deepcopy(DEFAULT_LIGHT_COLORS),
        'dark': deepcopy(DEFAULT_DARK_COLORS),
    },
    'forest': {
        'label': 'جنگل سبز',
        'description': 'سبز طبیعی با پس‌زمینهٔ روشن و آرام',
        'light': {
            'button': '#176b4d', 'button_text': '#ffffff',
            'secondary_button': '#ffffff', 'secondary_button_text': '#17362a',
            'background': '#f1f7f3', 'surface': '#ffffff', 'text': '#1d3025',
            'border': '#d1e1d5', 'table_header': '#1e5138', 'table_header_text': '#ffffff',
            'table_row': '#ffffff', 'table_row_alt': '#f2f8f4',
        },
        'dark': {
            'button': '#4fb789', 'button_text': '#082015',
            'secondary_button': '#273a30', 'secondary_button_text': '#e8f5ec',
            'background': '#111d16', 'surface': '#1a2b21', 'text': '#e8f5ec',
            'border': '#3a5746', 'table_header': '#25593d', 'table_header_text': '#ffffff',
            'table_row': '#1a2b21', 'table_row_alt': '#20342a',
        },
    },
    'lavender': {
        'label': 'یاس بنفش',
        'description': 'بنفش ملایم با سطح‌های یاسی و خوانا',
        'light': {
            'button': '#6341a5', 'button_text': '#ffffff',
            'secondary_button': '#ffffff', 'secondary_button_text': '#2b1d45',
            'background': '#f5f2fb', 'surface': '#ffffff', 'text': '#2d2540',
            'border': '#ded5ef', 'table_header': '#4f327d', 'table_header_text': '#ffffff',
            'table_row': '#ffffff', 'table_row_alt': '#f7f4fc',
        },
        'dark': {
            'button': '#bda4f3', 'button_text': '#211239',
            'secondary_button': '#332a47', 'secondary_button_text': '#f2edfb',
            'background': '#171320', 'surface': '#231d31', 'text': '#f2edfb',
            'border': '#493a63', 'table_header': '#49376f', 'table_header_text': '#ffffff',
            'table_row': '#231d31', 'table_row_alt': '#2b2440',
        },
    },
    'rose': {
        'label': 'رز صورتی',
        'description': 'صورتی و زرشکی ملایم با سطح‌های گرم',
        'light': {
            'button': '#b4235a', 'button_text': '#ffffff',
            'secondary_button': '#ffffff', 'secondary_button_text': '#3d2030',
            'background': '#fff4f7', 'surface': '#ffffff', 'text': '#39202b',
            'border': '#efd3dc', 'table_header': '#7a1e43', 'table_header_text': '#ffffff',
            'table_row': '#ffffff', 'table_row_alt': '#fff4f7',
        },
        'dark': {
            'button': '#f08aaa', 'button_text': '#30101d',
            'secondary_button': '#442535', 'secondary_button_text': '#ffeaf1',
            'background': '#1d1117', 'surface': '#2c1b24', 'text': '#ffedf3',
            'border': '#553544', 'table_header': '#69304b', 'table_header_text': '#ffffff',
            'table_row': '#2c1b24', 'table_row_alt': '#36212c',
        },
    },
    'amber': {
        'label': 'کهربایی گرم',
        'description': 'طلایی و کرم گرم؛ بدون کاهش خوانایی',
        'light': {
            'button': '#8a4b08', 'button_text': '#ffffff',
            'secondary_button': '#ffffff', 'secondary_button_text': '#382811',
            'background': '#fff8eb', 'surface': '#ffffff', 'text': '#382811',
            'border': '#ead8b8', 'table_header': '#70400e', 'table_header_text': '#ffffff',
            'table_row': '#ffffff', 'table_row_alt': '#fdf5e6',
        },
        'dark': {
            'button': '#f0b348', 'button_text': '#2e1c05',
            'secondary_button': '#453620', 'secondary_button_text': '#fff4dc',
            'background': '#1b160d', 'surface': '#292114', 'text': '#fff5e1',
            'border': '#54452c', 'table_header': '#69470e', 'table_header_text': '#ffffff',
            'table_row': '#292114', 'table_row_alt': '#342a1a',
        },
    },
    'slate': {
        'label': 'خاکستری آبی',
        'description': 'خنثی و حرفه‌ای با آبی سنگی',
        'light': {
            'button': '#334e68', 'button_text': '#ffffff',
            'secondary_button': '#ffffff', 'secondary_button_text': '#1c2938',
            'background': '#f2f5f8', 'surface': '#ffffff', 'text': '#1c2938',
            'border': '#d5dee8', 'table_header': '#34495e', 'table_header_text': '#ffffff',
            'table_row': '#ffffff', 'table_row_alt': '#f5f7fa',
        },
        'dark': {
            'button': '#9ab3cc', 'button_text': '#101b26',
            'secondary_button': '#293849', 'secondary_button_text': '#e7eef5',
            'background': '#111820', 'surface': '#1c2834', 'text': '#e8eef5',
            'border': '#3b4c5d', 'table_header': '#304963', 'table_header_text': '#ffffff',
            'table_row': '#1c2834', 'table_row_alt': '#23313f',
        },
    },
}
# Additional palettes based on supplied Figma color-combination references.
COLOR_PALETTES.update({'blooming_romance': {'label': 'Blooming romance',
                      'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از '
                                     'Figma',
                      'light': {'button': '#660032',
                                'button_text': '#ffffff',
                                'secondary_button': '#fbe7f1',
                                'secondary_button_text': '#161421',
                                'background': '#fdf7fa',
                                'surface': '#ffffff',
                                'text': '#161421',
                                'border': '#a6c2a9',
                                'table_header': '#005209',
                                'table_header_text': '#ffffff',
                                'table_row': '#ffffff',
                                'table_row_alt': '#fdf5f9'},
                      'dark': {'button': '#ea8fbd',
                               'button_text': '#101018',
                               'secondary_button': '#0e1d16',
                               'secondary_button_text': '#f8f6ff',
                               'background': '#100814',
                               'surface': '#19141f',
                               'text': '#f8f6ff',
                               'border': '#3c6346',
                               'table_header': '#005209',
                               'table_header_text': '#ffffff',
                               'table_row': '#19141f',
                               'table_row_alt': '#1d2628'},
                      'swatches': ['#660032', '#005209', '#e573ac', '#46920f']},
 'desert_dusk': {'label': 'Desert dusk',
                 'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
                 'light': {'button': '#993a8c',
                           'button_text': '#ffffff',
                           'secondary_button': '#fbe9e2',
                           'secondary_button_text': '#161421',
                           'background': '#fef7f5',
                           'surface': '#ffffff',
                           'text': '#161421',
                           'border': '#dfc4c1',
                           'table_header': '#a3574e',
                           'table_header_text': '#ffffff',
                           'table_row': '#ffffff',
                           'table_row_alt': '#fdf6f3'},
                 'dark': {'button': '#eb9979',
                          'button_text': '#101018',
                          'secondary_button': '#2e1e24',
                          'secondary_button_text': '#f8f6ff',
                          'background': '#140d1b',
                          'surface': '#1c1725',
                          'text': '#f8f6ff',
                          'border': '#8d6669',
                          'table_header': '#a3574e',
                          'table_header_text': '#ffffff',
                          'table_row': '#1c1725',
                          'table_row_alt': '#2d262f'},
                 'swatches': ['#993a8c', '#a3574e', '#e68057', '#be7587']},
 'lavender_fields': {'label': 'Lavender fields',
                     'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از '
                                    'Figma',
                     'light': {'button': '#974fb8',
                               'button_text': '#ffffff',
                               'secondary_button': '#f4f4ff',
                               'secondary_button_text': '#161421',
                               'background': '#fbfbff',
                               'surface': '#ffffff',
                               'text': '#161421',
                               'border': '#e8e6cb',
                               'table_header': '#6f6d3e',
                               'table_header_text': '#ffffff',
                               'table_row': '#ffffff',
                               'table_row_alt': '#fbfbff'},
                     'dark': {'button': '#cdccff',
                              'button_text': '#101018',
                              'secondary_button': '#333229',
                              'secondary_button_text': '#f8f6ff',
                              'background': '#181124',
                              'surface': '#1f1a2b',
                              'text': '#f8f6ff',
                              'border': '#9a9677',
                              'table_header': '#6f6d3e',
                              'table_header_text': '#ffffff',
                              'table_row': '#1f1a2b',
                              'table_row_alt': '#303032'},
                     'swatches': ['#d06dfc', '#bcb96a', '#c1bfff', '#fdfad5']},
 'country_garden': {'label': 'Country garden',
                    'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
                    'light': {'button': '#723480',
                              'button_text': '#ffffff',
                              'secondary_button': '#f9f8ff',
                              'secondary_button_text': '#161421',
                              'background': '#fdfcff',
                              'surface': '#ffffff',
                              'text': '#161421',
                              'border': '#d3d3b8',
                              'table_header': '#68682b',
                              'table_header_text': '#ffffff',
                              'table_row': '#ffffff',
                              'table_row_alt': '#fcfcff'},
                    'dark': {'button': '#e2ddff',
                             'button_text': '#101018',
                             'secondary_button': '#27271f',
                             'secondary_button_text': '#f8f6ff',
                             'background': '#100c1a',
                             'surface': '#1a1724',
                             'text': '#f8f6ff',
                             'border': '#7c7a5c',
                             'table_header': '#68682b',
                             'table_header_text': '#ffffff',
                             'table_row': '#1a1724',
                             'table_row_alt': '#2a2b2d'},
                    'swatches': ['#723480', '#808135', '#dbd4ff', '#ffffe3']},
 'cherry_blossom': {'label': 'Cherry blossom',
                    'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
                    'light': {'button': '#876168',
                              'button_text': '#ffffff',
                              'secondary_button': '#fdf6f6',
                              'secondary_button_text': '#161421',
                              'background': '#fefcfc',
                              'surface': '#ffffff',
                              'text': '#161421',
                              'border': '#f0fbf1',
                              'table_header': '#5c685e',
                              'table_header_text': '#ffffff',
                              'table_row': '#ffffff',
                              'table_row_alt': '#fefbfb'},
                    'dark': {'button': '#f5d6d6',
                             'button_text': '#101018',
                             'secondary_button': '#383d3f',
                             'secondary_button_text': '#f8f6ff',
                             'background': '#1c171f',
                             'surface': '#221f28',
                             'text': '#f8f6ff',
                             'border': '#a6b4ae',
                             'table_header': '#5c685e',
                             'table_header_text': '#ffffff',
                             'table_row': '#221f28',
                             'table_row_alt': '#32363d'},
                    'swatches': ['#ffb7c5', '#d5f3d8', '#f3cccc', '#ffffff']},
 'sunny_day': {'label': 'Sunny day',
               'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
               'light': {'button': '#2300ff',
                         'button_text': '#ffffff',
                         'secondary_button': '#fff4d4',
                         'secondary_button_text': '#161421',
                         'background': '#fffbf0',
                         'surface': '#ffffff',
                         'text': '#161421',
                         'border': '#d3cdbc',
                         'table_header': '#73663a',
                         'table_header_text': '#ffffff',
                         'table_row': '#ffffff',
                         'table_row_alt': '#fffbed'},
               'dark': {'button': '#ffcc34',
                        'button_text': '#101018',
                        'secondary_button': '#272321',
                        'secondary_button_text': '#f8f6ff',
                        'background': '#0a0824',
                        'surface': '#15142c',
                        'text': '#f8f6ff',
                        'border': '#7c7262',
                        'table_header': '#73663a',
                        'table_header_text': '#ffffff',
                        'table_row': '#15142c',
                        'table_row_alt': '#2a292e'},
               'swatches': ['#2300ff', '#807141', '#ffbf01', '#017eff']},
 'bubblegum_pop': {'label': 'Bubblegum pop',
                   'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
                   'light': {'button': '#047878',
                             'button_text': '#ffffff',
                             'secondary_button': '#edfeff',
                             'secondary_button_text': '#161421',
                             'background': '#f9ffff',
                             'surface': '#ffffff',
                             'text': '#161421',
                             'border': '#ffd0e7',
                             'table_header': '#a74e7a',
                             'table_header_text': '#ffffff',
                             'table_row': '#ffffff',
                             'table_row_alt': '#f8feff'},
                   'dark': {'button': '#acf9fd',
                            'button_text': '#101018',
                            'secondary_button': '#412539',
                            'secondary_button_text': '#f8f6ff',
                            'background': '#08141b',
                            'surface': '#131d25',
                            'text': '#f8f6ff',
                            'border': '#bb76a0',
                            'table_header': '#a74e7a',
                            'table_header_text': '#ffffff',
                            'table_row': '#131d25',
                            'table_row_alt': '#362a3a'},
                   'swatches': ['#069494', '#ff78bb', '#97f7fd', '#ffffff']},
 'electric_kiwi': {'label': 'Electric kiwi',
                   'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
                   'light': {'button': '#000000',
                             'button_text': '#ffffff',
                             'secondary_button': '#ffffd4',
                             'secondary_button_text': '#161421',
                             'background': '#fffff0',
                             'surface': '#ffffff',
                             'text': '#161421',
                             'border': '#f4ffa6',
                             'table_header': '#606e00',
                             'table_header_text': '#ffffff',
                             'table_row': '#ffffff',
                             'table_row_alt': '#ffffed'},
                   'dark': {'button': '#ffff33',
                            'button_text': '#101018',
                            'secondary_button': '#3a4014',
                            'secondary_button_text': '#f8f6ff',
                            'background': '#070810',
                            'surface': '#13141c',
                            'text': '#f8f6ff',
                            'border': '#abba42',
                            'table_header': '#606e00',
                            'table_header_text': '#ffffff',
                            'table_row': '#13141c',
                            'table_row_alt': '#333728'},
                   'swatches': ['#000000', '#dfff00', '#ffff00', '#d1ff19']},
 'alchemical_reaction': {'label': 'Alchemical reaction',
                         'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از '
                                        'Figma',
                         'light': {'button': '#9d00ff',
                                   'button_text': '#ffffff',
                                   'secondary_button': '#f9ead9',
                                   'secondary_button_text': '#161421',
                                   'background': '#fdf7f1',
                                   'surface': '#ffffff',
                                   'text': '#161421',
                                   'border': '#c6d2bc',
                                   'table_header': '#537239',
                                   'table_header_text': '#ffffff',
                                   'table_row': '#ffffff',
                                   'table_row_alt': '#fdf6ef'},
                         'dark': {'button': '#e59a4a',
                                  'button_text': '#101018',
                                  'secondary_button': '#202621',
                                  'secondary_button_text': '#f8f6ff',
                                  'background': '#140824',
                                  'surface': '#1c142c',
                                  'text': '#f8f6ff',
                                  'border': '#6a7a62',
                                  'table_header': '#537239',
                                  'table_header_text': '#ffffff',
                                  'table_row': '#1c142c',
                                  'table_row_alt': '#262a2e'},
                         'swatches': ['#9d00ff', '#5c7f3f', '#de811d', '#6bff00']},
 'electropop': {'label': 'Electropop',
                'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
                'light': {'button': '#5200ff',
                          'button_text': '#ffffff',
                          'secondary_button': '#f6ffd4',
                          'secondary_button_text': '#161421',
                          'background': '#fcfff0',
                          'surface': '#ffffff',
                          'text': '#161421',
                          'border': '#fda6ff',
                          'table_header': '#b600ba',
                          'table_header_text': '#ffffff',
                          'table_row': '#ffffff',
                          'table_row_alt': '#fbffed'},
                'dark': {'button': '#d6ff34',
                         'button_text': '#101018',
                         'secondary_button': '#3f0d47',
                         'secondary_button_text': '#f8f6ff',
                         'background': '#0e0824',
                         'surface': '#18142c',
                         'text': '#f8f6ff',
                         'border': '#b83ac2',
                         'table_header': '#b600ba',
                         'table_header_text': '#ffffff',
                         'table_row': '#18142c',
                         'table_row_alt': '#361e41'},
                'swatches': ['#5200ff', '#f900ff', '#ccff01', '#ff6a00']},
 'neon_noir': {'label': 'Neon noir',
               'description': 'پالت چندرنگ با گرادیانت روشن و تیره؛ الهام\u200cگرفته از Figma',
               'light': {'button': '#ac00e6',
                         'button_text': '#ffffff',
                         'secondary_button': '#dbffd4',
                         'secondary_button_text': '#161421',
                         'background': '#f2fff0',
                         'surface': '#ffffff',
                         'text': '#161421',
                         'border': '#aeaeae',
                         'table_header': '#191919',
                         'table_header_text': '#ffffff',
                         'table_row': '#ffffff',
                         'table_row_alt': '#f0ffee'},
               'dark': {'button': '#56ff37',
                        'button_text': '#101018',
                        'secondary_button': '#131219',
                        'secondary_button_text': '#f8f6ff',
                        'background': '#170824',
                        'surface': '#1e142c',
                        'text': '#f8f6ff',
                        'border': '#48464e',
                        'table_header': '#191919',
                        'table_header_text': '#ffffff',
                        'table_row': '#1e142c',
                        'table_row_alt': '#1f202a'},
               'swatches': ['#bf00ff', '#191919', '#2cff05', '#2d2d2d']}})
COLOR_PALETTE_CHOICES = tuple((key, palette['label']) for key, palette in COLOR_PALETTES.items())

DEFAULT_PREFERENCES: dict[str, Any] = {
    'color_palette': DEFAULT_COLOR_PALETTE,
    'student_card_fields': list(STUDENT_DISPLAY_KEYS),
    'student_table_fields': list(STUDENT_DISPLAY_KEYS),
    'student_table_order': list(STUDENT_DISPLAY_KEYS),
    'student_table_pinned': ['name'],
    'student_table_column_widths': deepcopy(DEFAULT_TABLE_COLUMN_WIDTHS),
    'student_table_sort': 'name',
    'student_table_sort_direction': 'asc',
    'student_table_page_size': 20,
    # Keep mobile cards readable by default; users can add or remove fields.
    'student_mobile_fields': ['name', 'code', 'grade', 'class_name'],
    'dashboard_cards': list(DASHBOARD_CARD_KEYS),
    'quick_actions': list(QUICK_ACTION_KEYS),
    'ui_density': 'comfortable',
    'card_size': 'medium',
    'visual_style': 'soft',
    'font_family': 'vazirmatn',
    'text_scale': 'normal',
    'line_spacing': 'comfortable',
    'motion': 'normal',
    'colors': deepcopy(DEFAULT_LIGHT_COLORS),
    'dark_colors': deepcopy(DEFAULT_DARK_COLORS),
}

# Presets affect information density and layout. Personal color palettes are
# preserved when a preset is applied.
UI_PRESETS: dict[str, dict[str, Any]] = {
    'simple': {
        'student_card_fields': ['name', 'code', 'class_name'],
        'student_table_fields': list(STUDENT_DISPLAY_KEYS),
        'student_mobile_fields': ['name', 'code', 'class_name'],
        'dashboard_cards': ['quick_actions', 'reminders'],
        'ui_density': 'compact', 'card_size': 'small', 'visual_style': 'minimal',
        'font_family': 'vazirmatn', 'text_scale': 'normal',
        'line_spacing': 'comfortable', 'motion': 'reduced', 'student_view': 'sm',
    },
    'teacher': {
        'student_card_fields': ['name', 'code', 'grade', 'class_name', 'sida_class', 'status'],
        'student_table_fields': ['name', 'code', 'grade', 'class_name', 'sida_class', 'gender', 'status'],
        'student_mobile_fields': ['name', 'code', 'grade', 'class_name'],
        'dashboard_cards': ['quick_actions', 'overview', 'reminders'],
        'ui_density': 'compact', 'card_size': 'medium', 'visual_style': 'soft',
        'font_family': 'vazirmatn', 'text_scale': 'normal',
        'line_spacing': 'comfortable', 'motion': 'normal', 'student_view': 'sm',
    },
    'management': {
        'student_card_fields': list(STUDENT_DISPLAY_KEYS),
        'student_table_fields': list(STUDENT_DISPLAY_KEYS),
        'student_mobile_fields': ['name', 'code', 'grade', 'class_name'],
        'dashboard_cards': list(DASHBOARD_CARD_KEYS),
        'ui_density': 'comfortable', 'card_size': 'medium', 'visual_style': 'soft',
        'font_family': 'vazirmatn', 'text_scale': 'normal',
        'line_spacing': 'comfortable', 'motion': 'normal', 'student_view': 'table',
    },
}
PRESET_LABELS = (
    ('simple', 'ساده و فشرده'),
    ('teacher', 'کار روزانهٔ معلم'),
    ('management', 'نمای مدیریتی'),
)


def default_preferences() -> dict[str, Any]:
    """Return a fresh, mutable copy of the safe defaults."""
    return deepcopy(DEFAULT_PREFERENCES)


def matching_color_palette(light: dict[str, str], dark: dict[str, str]) -> str:
    """Return a named palette only when both day and night colors match exactly."""
    for key, palette in COLOR_PALETTES.items():
        if light == palette['light'] and dark == palette['dark']:
            return key
    return 'custom'


def available_quick_actions(role: str | None, allowed_endpoints, selected=None) -> list[dict[str, Any]]:
    """Return only role- and session-authorized actions, in the user's order."""
    endpoints = set(allowed_endpoints or ())
    available = []
    for action in QUICK_ACTIONS:
        if role not in action['roles'] or action['endpoint'] not in endpoints:
            continue
        item = dict(action)
        if role == 'teacher' and item.get('teacher_label'):
            item['label'] = item['teacher_label']
        if role == 'manager' and item['key'] == 'attendance_quick':
            item['primary'] = True
        item.pop('teacher_label', None)
        item.pop('roles', None)
        available.append(item)
    if selected is None:
        return available
    if isinstance(selected, str):
        selected = [part for part in selected.split(',') if part]
    if not isinstance(selected, (list, tuple, set)):
        return []
    by_key = {item['key']: item for item in available}
    result = []
    seen = set()
    for key in selected:
        key = str(key)
        if key in by_key and key not in seen:
            result.append(by_key[key])
            seen.add(key)
    return result


def _ordered_allowlist(raw: object, allowed: tuple[str, ...], fallback: object,
                       append_missing: bool = False) -> list[str]:
    if raw is None:
        raw = fallback
    if isinstance(raw, str):
        raw = [part for part in raw.split(',') if part]
    if isinstance(raw, set):
        raw = [key for key in allowed if key in raw]
    if not isinstance(raw, (list, tuple)):
        raw = []
    chosen = []
    seen = set()
    for item in raw:
        key = str(item)
        if key in allowed and key not in seen:
            chosen.append(key)
            seen.add(key)
    if append_missing:
        fallback_values = fallback if isinstance(fallback, (list, tuple)) else allowed
        for item in fallback_values:
            key = str(item)
            if key in allowed and key not in seen:
                chosen.append(key)
                seen.add(key)
    return chosen


def _allowed_fields(raw: object, allowed: tuple[str, ...], fallback: object) -> list[str]:
    if raw is None:
        raw = fallback
    if isinstance(raw, str):
        raw = [part for part in raw.split(',') if part]
    if not isinstance(raw, (list, tuple, set)):
        raw = []
    selected = {str(item) for item in raw if str(item) in allowed}
    selected.add('name')
    return [key for key in allowed if key in selected]


def sanitize_preferences(value: object) -> dict[str, Any]:
    """Validate persisted or submitted UI preferences against strict allowlists."""
    source = value if isinstance(value, dict) else {}
    result = default_preferences()

    # Upgrade preferences saved by the earlier unified student_fields control.
    legacy_fields = source.get('student_fields')
    card_raw = source.get('student_card_fields', legacy_fields)
    table_raw = source.get('student_table_fields', legacy_fields)
    card_fields = _allowed_fields(card_raw, STUDENT_DISPLAY_KEYS, result['student_card_fields'])
    table_fields = _allowed_fields(table_raw, STUDENT_DISPLAY_KEYS, result['student_table_fields'])
    table_selected = set(table_fields)
    table_order = _ordered_allowlist(
        source.get('student_table_order'), STUDENT_DISPLAY_KEYS,
        result['student_table_order'], append_missing=True,
    )
    if 'name' in table_order:
        table_order.remove('name')
    table_order.insert(0, 'name')

    raw_pinned = _ordered_allowlist(
        source.get('student_table_pinned'), STUDENT_DISPLAY_KEYS,
        result['student_table_pinned'],
    )
    pinned_set = {key for key in raw_pinned if key in table_selected}
    pinned_set.add('name')
    pinned = [key for key in table_order if key in pinned_set][:TABLE_PIN_LIMIT]
    if 'name' not in pinned:
        pinned.insert(0, 'name')
    pinned_set = set(pinned)
    table_order = pinned + [key for key in table_order if key not in pinned_set]

    mobile_raw = source.get('student_mobile_fields', legacy_fields if legacy_fields is not None else result['student_mobile_fields'])
    mobile_fields = _allowed_fields(mobile_raw, STUDENT_MOBILE_KEYS, result['student_mobile_fields'])
    mobile_fields = [key for key in mobile_fields if key in card_fields]
    if 'name' not in mobile_fields:
        mobile_fields.insert(0, 'name')
    result['student_card_fields'] = card_fields
    result['student_table_fields'] = [key for key in table_order if key in table_selected]
    result['student_table_order'] = table_order
    result['student_table_pinned'] = pinned
    result['student_mobile_fields'] = [key for key in STUDENT_MOBILE_KEYS if key in mobile_fields]

    raw_widths = source.get('student_table_column_widths', {})
    if not isinstance(raw_widths, dict):
        raw_widths = {}
    allowed_widths = set(TABLE_COLUMN_WIDTH_KEYS)
    result['student_table_column_widths'] = {
        key: raw_widths.get(key) if isinstance(raw_widths.get(key), str) and raw_widths.get(key) in allowed_widths else DEFAULT_TABLE_COLUMN_WIDTHS[key]
        for key in STUDENT_DISPLAY_KEYS
    }
    candidate_sort = source.get('student_table_sort')
    if isinstance(candidate_sort, str) and candidate_sort in TABLE_SORT_KEYS:
        result['student_table_sort'] = candidate_sort
    candidate_direction = source.get('student_table_sort_direction')
    if isinstance(candidate_direction, str) and candidate_direction in {'asc', 'desc'}:
        result['student_table_sort_direction'] = candidate_direction
    try:
        candidate_page_size = int(source.get('student_table_page_size', result['student_table_page_size']))
    except (TypeError, ValueError):
        candidate_page_size = result['student_table_page_size']
    if candidate_page_size in {size for size, _label in TABLE_PAGE_SIZES}:
        result['student_table_page_size'] = candidate_page_size

    result['quick_actions'] = _ordered_allowlist(
        source.get('quick_actions'), QUICK_ACTION_KEYS, result['quick_actions'],
    )

    raw_cards = source.get('dashboard_cards', result['dashboard_cards'])
    if isinstance(raw_cards, str):
        raw_cards = [part for part in raw_cards.split(',') if part]
    if not isinstance(raw_cards, (list, tuple, set)):
        raw_cards = []
    chosen_cards = {str(item) for item in raw_cards if str(item) in DASHBOARD_CARD_KEYS}
    result['dashboard_cards'] = [key for key in DASHBOARD_CARD_KEYS if key in chosen_cards]

    for key, allowed in (
        ('ui_density', {item[0] for item in UI_DENSITIES}),
        ('card_size', {item[0] for item in CARD_SIZES}),
        ('visual_style', {item[0] for item in VISUAL_STYLES}),
        ('font_family', {item[0] for item in FONT_FAMILIES}),
        ('text_scale', {item[0] for item in TEXT_SCALES}),
        ('line_spacing', {item[0] for item in LINE_SPACINGS}),
        ('motion', {item[0] for item in MOTION_OPTIONS}),
    ):
        candidate = source.get(key)
        if isinstance(candidate, str) and candidate in allowed:
            result[key] = candidate

    for source_key, result_key, defaults in (
        ('colors', 'colors', DEFAULT_LIGHT_COLORS),
        ('dark_colors', 'dark_colors', DEFAULT_DARK_COLORS),
    ):
        raw_colors = source.get(source_key, {})
        if not isinstance(raw_colors, dict):
            raw_colors = {}
        for key in COLOR_KEYS:
            candidate = raw_colors.get(key)
            if isinstance(candidate, str) and _HEX_COLOR.fullmatch(candidate):
                result[result_key][key] = candidate.lower()
            else:
                result[result_key][key] = defaults[key]

    matched_palette = matching_color_palette(result['colors'], result['dark_colors'])
    requested_palette = source.get('color_palette')
    if requested_palette == 'custom':
        result['color_palette'] = 'custom'
    elif isinstance(requested_palette, str) and requested_palette in COLOR_PALETTES and requested_palette == matched_palette:
        result['color_palette'] = requested_palette
    else:
        # Older accounts have no palette key. Detect exact matches, but never
        # relabel an older hand-edited color set as one of the named presets.
        result['color_palette'] = matched_palette

    return result


def load_user_preferences(user_id: object) -> dict[str, Any]:
    """Load and sanitize a user's preferences from app_settings."""
    if user_id in (None, ''):
        return default_preferences()
    with get_db() as conn:
        row = conn.execute(
            'SELECT value FROM app_settings WHERE key=?',
            (f'{USER_PREFERENCES_KEY}{user_id}',),
        ).fetchone()
    if not row:
        return default_preferences()
    try:
        stored = json.loads(row['value'] or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = {}
    return sanitize_preferences(stored)


def save_user_preferences(user_id: object, value: object) -> dict[str, Any]:
    """Sanitize and save one account's preferences; never touches other keys."""
    if user_id in (None, ''):
        raise ValueError('user_id is required')
    prefs = sanitize_preferences(value)
    payload = json.dumps(prefs, ensure_ascii=False, separators=(',', ':'))
    with get_db() as conn:
        conn.execute(
            'INSERT INTO app_settings(key,value) VALUES(?,?) '
            'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (f'{USER_PREFERENCES_KEY}{user_id}', payload),
        )
        conn.commit()
    return prefs


def preferences_from_form(form) -> dict[str, Any]:
    """Build a plain preference object from the settings page's POST form."""
    return sanitize_preferences({
        'color_palette': form.get('color_palette'),
        'student_card_fields': form.getlist('student_card_fields'),
        'student_table_fields': form.getlist('student_table_fields'),
        'student_table_order': form.getlist('student_table_order'),
        'student_table_pinned': form.getlist('student_table_pinned'),
        'student_table_column_widths': {
            key: form.get(f'student_table_width_{key}', '') for key in STUDENT_DISPLAY_KEYS
        },
        'student_table_sort': form.get('student_table_sort', ''),
        'student_table_sort_direction': form.get('student_table_sort_direction', ''),
        'student_table_page_size': form.get('student_table_page_size', ''),
        'student_mobile_fields': form.getlist('student_mobile_fields'),
        'dashboard_cards': form.getlist('dashboard_cards'),
        'quick_actions': form.getlist('quick_actions'),
        'ui_density': form.get('ui_density', ''),
        'card_size': form.get('card_size', ''),
        'visual_style': form.get('visual_style', ''),
        'font_family': form.get('font_family', ''),
        'text_scale': form.get('text_scale', ''),
        'line_spacing': form.get('line_spacing', ''),
        'motion': form.get('motion', ''),
        'colors': {key: form.get(f'color_{key}', '') for key in COLOR_KEYS},
        'dark_colors': {key: form.get(f'dark_color_{key}', '') for key in COLOR_KEYS},
    })
