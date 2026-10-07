"""دفترچهٔ تلفن مدرسه — چاپی، فشرده و بسیار قابل تنظیم.

دو مسیر دارد:

* ``GET  /contact-book``        صفحهٔ تعاملی با پنل تنظیمات و پیش‌نمایش زنده
* ``POST /contact-book``        ذخیره (``action=save``) یا پاک کردن (``action=reset``)
                                تنظیمات پیش‌فرض همان کاربر
* ``GET  /contact-book/print``  صفحهٔ مستقل و آمادهٔ چاپ A4

همهٔ تنظیمات از آدرس (query string) خوانده می‌شوند؛ اگر پارامتری در آدرس نبود،
مقدار ذخیره‌شدهٔ کاربر از جدول ``app_settings`` و در نهایت پیش‌فرض همان گزینه
استفاده می‌شود. بنابراین یک آدرس، خودش همهٔ وضعیت چاپ را با خود می‌برد و
کاربر می‌تواند چیدمان دلخواهش را به‌عنوان پیش‌فرض ذخیره کند.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict

from flask import flash, redirect, render_template, request, session, url_for

from ..database import get_db
from ..security import audit


_PERSIAN_ALPHABET = 'اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی'
_TRANSLATE = str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ة': 'ه', 'ۀ': 'ه'})
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_FATHER_LABEL = 'پدر'
_MOTHER_LABEL = 'مادر'
_PHONE_LABELS = (_FATHER_LABEL, _MOTHER_LABEL)
_LABEL_REACH = 24  # فاصلهٔ مجاز بین برچسب و شماره در متن‌های به‌هم‌ریخته

SETTING_KEY = 'contact_book:user:{}'
MULTI_MARKER = '{}__set'  # نشانهٔ حضورِ گروه چک‌باکس در فرم

TITLES = {
    'staff': 'دفترچهٔ تلفن کارکنان و رانندگان سرویس',
    'parents': 'دفترچهٔ تلفن والدین دانش‌آموزان',
}


# ---------------------------------------------------------------------------
# ستون‌های قابل انتخاب
# ---------------------------------------------------------------------------
# kind یکی از name / phone / text / num است و ظاهر و پهنای ستون را تعیین می‌کند.
_STAFF_COLUMNS = OrderedDict([
    ('name',    {'label': 'نام و نام خانوادگی', 'kind': 'name'}),
    ('phone',   {'label': 'شماره تماس',         'kind': 'phone'}),
    ('subject', {'label': 'درس',                'kind': 'text'}),
    ('class',   {'label': 'کلاس',               'kind': 'text'}),
    ('code',    {'label': 'کد پرسنلی',          'kind': 'text'}),
    ('vehicle', {'label': 'خودروی سرویس',       'kind': 'text'}),
])
_PARENT_COLUMNS = OrderedDict([
    ('name',   {'label': 'نام دانش‌آموز',   'kind': 'name'}),
    ('father', {'label': 'پدر',             'kind': 'phone'}),
    ('mother', {'label': 'مادر',            'kind': 'phone'}),
    ('grade',  {'label': 'پایه',            'kind': 'text'}),
    ('class',  {'label': 'کلاس',            'kind': 'text'}),
    ('code',   {'label': 'کد دانش‌آموزی',   'kind': 'text'}),
])
_STAFF_DEFAULT = ('name', 'phone')
_PARENT_DEFAULT = ('name', 'father', 'mother')

_COLOR_NAMES = ('sec_bg', 'sec_fg', 'hdr_bg', 'hdr_fg', 'border_color',
                'even_bg', 'odd_bg', 'phone_bg')
_WEIGHTS = {'num': 6, 'name': 34, 'phone': 24, 'text': 17}
_CSS_CLASSES = {'num': 'col-no', 'name': 'col-name', 'phone': 'col-phone', 'text': 'col-text'}


# ---------------------------------------------------------------------------
# فهرست گزینه‌ها: نوع، پیش‌فرض و مقادیر مجاز
# ---------------------------------------------------------------------------
_CHOICES = {
    'col_gap': ('6px', ['0px', '2px', '3px', '5px', '6px', '8px', '10px', '12px']),
    'sec_bg':  ('#000', ['#000', '#1e3a5f', '#0b4f6c', '#047857', '#1e40af',
                         '#7c3aed', '#b91c1c', '#b45309', '#dc2626', '#2563eb',
                         '#16a34a', '#475569', '#0f172a', '#334155', '#6b7280']),
    'sec_fg':  ('#fff', ['#fff', '#000', '#111', '#fefce8', '#fef9c3', '#f1f5f9',
                         '#e2e8f0', '#ffffff', '#fee2e2', '#dc2626', '#f59e0b']),
    'hdr_bg':  ('#cfcfcf', ['#cfcfcf', '#d4d4d4', '#e2e8f0', '#f1f5f9', '#f8fafc',
                            '#e0e7ff', '#dbeafe', '#d1fae5', '#fef3c7', '#fce7f3',
                            '#f3e8ff', '#ccfbf1', '#eee']),
    'hdr_fg':  ('#000', ['#000', '#111', '#1e3a5f', '#0f172a', '#334155',
                         '#7c3aed', '#b91c1c', '#b45309', '#16a34a', '#2563eb']),
    'border_color': ('#b8b8b8', ['#b8b8b8', '#94a3b8', '#cbd5e1', '#e2e8f0', '#64748b',
                                 '#475569', '#334155', '#1e3a5f', '#0f172a', '#000',
                                 '#ccc', '#aaa']),
    'border_w': ('1', ['0.5', '1', '1.5', '2']),
    'even_bg': ('#f2f2f2', ['#f2f2f2', '#f8fafc', '#f1f5f9', '#eef2ff', '#f0f9ff',
                            '#f0fdf4', '#fefce8', '#faf5ff', '#fffbeb', '#fff1f2',
                            '#fff', '#fff7ed', '#fee2e2']),
    'odd_bg': ('#fff', ['#fff', '#ffffff', '#f8fafc', '#f1f5f9', '#fefce8',
                        '#faf5ff', '#fffbeb', '#fff7ed', '#eef2ff', '#f0f9ff']),
    'phone_bg': ('#e6e6e6', ['#e6e6e6', '#d4d4d4', '#e2e8f0', '#f1f5f9', '#f8fafc',
                             '#ede9fe', '#dbeafe', '#d1fae5', '#fef3c7', '#fce7f3',
                             '#fee2e2', '#faf5ff', '#fffbeb', '#f0f9ff', '#fff']),
    # --- تازه‌ها ---
    'empty_style': ('line', ['line', 'dash', 'dot', 'blank']),
    'group_by': ('family', ['family', 'first', 'class']),
    'staff_filter': ('all', ['all', 'teachers', 'drivers']),
    'section_filter': ('both', ['both', 'staff', 'parents']),
}
_RANGES = {
    'cols': (3, 1, 4),
    'font_size': (9, 7, 14),
    'cell_h': (14, 10, 28),
    'hdr_h': (15, 12, 24),
    'title_h': (17, 14, 26),
    'extra_rows': (0, 0, 3),
}
_YESNO = {
    'show_contact_type': 'yes',
    'table_header': 'yes',
    'section_title': 'yes',
    'titles': 'yes',
    'stripe': 'yes',
    'row_no': 'no',
    'hide_empty': 'no',
    'parents_page': 'yes',
    'sheet_header': 'yes',
    'page_num': 'no',
}
_FILTER_KEYS = ('class_filter', 'staff_filter', 'hide_empty', 'section_filter')
_PERSISTED_KEYS = tuple(list(_CHOICES) + list(_RANGES) + list(_YESNO)
                        + ['staff_cols', 'parent_cols'])

EMPTY_LABELS = {
    'line': 'جای خالی (خط‌چین)',
    'dash': 'خط تیره',
    'dot': 'نقطه‌چین',
    'blank': 'کاملاً خالی',
}
GROUP_LABELS = {
    'family': 'حرف اول نام خانوادگی',
    'first': 'حرف اول نام',
    'class': 'کلاس (هر کلاس یک بخش)',
}


# ---------------------------------------------------------------------------
# پاک‌سازی متن و شماره‌ها
# ---------------------------------------------------------------------------
def _clean(value):
    return str(value or '').translate(_TRANSLATE).strip()


def _phone_runs(text):
    """قطعه‌های عددی با ۷ رقم یا بیشتر را با موقعیتشان برمی‌گرداند."""
    runs = []
    start = None
    for index, char in enumerate(text):
        if char.isdigit():
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index, text[start:index]))
            start = None
    if start is not None:
        runs.append((start, len(text), text[start:]))
    return [(begin, end, digits) for begin, end, digits in runs if len(digits) >= 7]


def _split_phone_field(value, default_label):
    """شماره‌های یک فیلد تلفن را بین پدر و مادر تقسیم می‌کند.

    برخی رکوردها هر دو شماره را در یک فیلد دارند، مثل
    «پدر: ۰۹۱۲… مادر: ۰۹۹…»؛ اینجا بر اساس نزدیک‌ترین برچسب تفکیک می‌شوند
    تا هیچ شماره‌ای حذف نشود. مقدار بدون شماره دست‌نخورده در ستون خودش می‌ماند.
    """
    raw = _clean(value)
    if not raw:
        return '', ''
    normalized = raw.translate(_DIGITS)
    runs = _phone_runs(normalized)
    if not runs:
        return raw, ''
    labels = []
    for label in _PHONE_LABELS:
        start = normalized.find(label)
        while start != -1:
            labels.append((start, start + len(label), label))
            start = normalized.find(label, start + len(label))
    buckets = {_FATHER_LABEL: [], _MOTHER_LABEL: []}
    # سبک نوشتار: «پدر: شماره» (برچسب قبل از شماره) یا «شماره پدر» (برچسب بعد از شماره)
    label_first = bool(labels) and labels[0][0] < runs[0][0]
    for begin, end, digits in runs:
        owner = None
        if label_first:
            gap = None
            for label_start, label_end, label in labels:
                if label_end <= begin and (gap is None or begin - label_end < gap):
                    owner, gap = label, begin - label_end
        else:
            gap = None
            for label_start, label_end, label in labels:
                if label_start >= end and (gap is None or label_start - end < gap):
                    owner, gap = label, label_start - end
        if owner and gap is not None and gap <= _LABEL_REACH:
            buckets[owner].append(digits)
        else:
            buckets[default_label].append(digits)
    return ' / '.join(buckets[_FATHER_LABEL]), ' / '.join(buckets[_MOTHER_LABEL])


def _join_name(first, last):
    return ' '.join(part for part in (_clean(first), _clean(last)) if part)


def _natural_key(text):
    """کلید مرتب‌سازی طبیعی: «کلاس ۲» قبل از «کلاس ۱۰» می‌آید."""
    parts = [part for part in re.split(r'(\d+)', _clean(text)) if part]
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts)


def _letter_rank(text):
    try:
        return _PERSIAN_ALPHABET.index(_clean(text)[:1])
    except ValueError:
        return len(_PERSIAN_ALPHABET)


# ---------------------------------------------------------------------------
# خواندن/نوشتن تنظیمات
# ---------------------------------------------------------------------------
class _Settings:
    """مقدار هر گزینه را به ترتیب اولویت می‌خواند: آدرس/فرم ← ذخیره‌شده ← پیش‌فرض."""

    def __init__(self, source, saved):
        self.source = source
        self.saved = saved or {}

    def _pick(self, name):
        if name in self.source:
            return self.source.get(name)
        if name in self.saved:
            return self.saved.get(name)
        return None

    def choice(self, name):
        default, allowed = _CHOICES[name]
        text = str(self._pick(name) or '').strip()
        return text if text in allowed else default

    def number(self, name):
        default, low, high = _RANGES[name]
        try:
            value = int(str(self._pick(name)).strip())
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    def yesno(self, name):
        default = _YESNO[name]
        text = str(self._pick(name) or '').strip()
        return text if text in ('yes', 'no') else default

    def color(self, name):
        default, allowed = _CHOICES[name]
        text = str(self._pick(name) or default).strip()
        if text and not text.startswith('#'):
            text = '#' + text
        return text if text in allowed else default

    def text(self, name, limit=60):
        return str(self._pick(name) or '').strip()[:limit]

    def multi(self, name, default, allowed):
        marker = MULTI_MARKER.format(name)
        if marker in self.source or name in self.source:
            values = self.source.getlist(name)
        else:
            saved = self.saved.get(name)
            values = saved if isinstance(saved, list) else list(default)
        chosen = []
        for value in values:
            key = str(value or '').strip()
            if key in allowed and key not in chosen:
                chosen.append(key)
        # حداقل یک ستون همیشه می‌ماند تا جدول بی‌معنا نشود.
        return chosen or list(default)


def _options(source, saved):
    s = _Settings(source, saved)
    options = {}
    for name in _CHOICES:
        options[name] = s.color(name) if name in _COLOR_NAMES else s.choice(name)
    for name in _RANGES:
        options[name] = s.number(name)
    for name in _YESNO:
        options[name] = s.yesno(name)
    options['staff_cols'] = s.multi('staff_cols', _STAFF_DEFAULT, _STAFF_COLUMNS)
    options['parent_cols'] = s.multi('parent_cols', _PARENT_DEFAULT, _PARENT_COLUMNS)
    options['class_filter'] = s.text('class_filter')
    return options


def _params(options, only=None):
    """دیکشنری پارامترهای آدرس برای لینک چاپ/هدایت مجدد."""
    names = list(_CHOICES) + list(_RANGES) + list(_YESNO) + ['staff_cols', 'parent_cols']
    if only is not None:
        return {name: options[name] for name in only if options.get(name)}
    params = {name: options[name] for name in names}
    params['class_filter'] = options['class_filter']
    return params


def _flat_params(params):
    """پارامترها به شکل جفت‌های تخت (برای فیلدهای مخفی فرم ذخیره)."""
    flat = []
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            flat.extend((name, item) for item in value)
        else:
            flat.append((name, value))
    return flat


def _load_saved(conn, user_id):
    if not user_id:
        return {}
    row = conn.execute('SELECT value FROM app_settings WHERE key=?',
                       (SETTING_KEY.format(user_id),)).fetchone()
    if not row:
        return {}
    try:
        stored = json.loads(row['value'] or '{}')
    except (TypeError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def _save_settings(conn, user_id, values):
    conn.execute(
        'INSERT INTO app_settings(key,value) VALUES(?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (SETTING_KEY.format(user_id), json.dumps(values, ensure_ascii=False)),
    )


def _clear_settings(conn, user_id):
    conn.execute('DELETE FROM app_settings WHERE key=?', (SETTING_KEY.format(user_id),))


# ---------------------------------------------------------------------------
# ساختن جدول‌ها
# ---------------------------------------------------------------------------
def _column_spec(catalogue, keys, row_no):
    entries = []
    if row_no == 'yes':
        entries.append({'key': '#', 'label': 'ردیف', 'kind': 'num'})
    for key, info in catalogue.items():
        if key in keys:
            entries.append({'key': key, 'label': info['label'], 'kind': info['kind']})
    weights = [_WEIGHTS[entry['kind']] for entry in entries]
    total = sum(weights) or 1
    widths = [round(weight * 100 / total, 2) for weight in weights]
    widths[-1] = round(100 - sum(widths[:-1]), 2)
    for entry, width in zip(entries, widths):
        entry['width'] = width
        entry['cls'] = _CSS_CLASSES[entry['kind']]
    return entries


def _cells(item, columns, number=None):
    cells = []
    for column in columns:
        kind = column['kind']
        if kind == 'num':
            value, badge = (str(number) if number is not None else ''), ''
        else:
            value = item.get(column['key']) or ''
            badge = item.get('badge') or '' if kind == 'name' else ''
        cells.append({'cls': column['cls'], 'width': column['width'],
                      'kind': kind, 'value': value, 'badge': badge})
    return cells


def _sections(items, mode):
    indexed = []
    for item in items:
        if mode == 'class':
            label = item.get('class') or 'بدون کلاس'
            if item.get('service'):        # رانندگان سرویس همیشه در پایان فهرست کارکنان
                order = (2, ())
            elif item.get('class'):
                order = (0, _natural_key(label))
            else:
                order = (1, ())
            inner = (_natural_key(item.get('last_name') or item.get('name')),
                     _natural_key(item.get('name')))
        elif mode == 'first':
            label = (item.get('first_name') or item.get('name') or '—')[:1] or '—'
            order = (_letter_rank(label), ())
            inner = (_natural_key(item.get('name')),)
        else:
            label = (item.get('last_name') or item.get('name') or '—')[:1] or '—'
            order = (_letter_rank(label), ())
            inner = (_natural_key(item.get('last_name') or item.get('name')),
                     _natural_key(item.get('name')))
        indexed.append((order, inner, label, item))
    indexed.sort(key=lambda row: (row[0], row[1]))
    buckets = OrderedDict()
    for _order, _inner, label, item in indexed:
        buckets.setdefault(label, []).append(item)
    return [{'title': label, 'items': rows} for label, rows in buckets.items()]


def _build_book(items, columns, mode, extra_rows):
    sections = _sections(items, mode)
    counter = 0
    for section in sections:
        rows = []
        for item in section['items']:
            counter += 1
            rows.append(_cells(item, columns, counter))
        section['rows'] = rows
    return {'columns': columns, 'sections': sections,
            'count': len(items), 'blank_rows': extra_rows}


# ---------------------------------------------------------------------------
# دادهٔ خام دفترچه
# ---------------------------------------------------------------------------
def _parent_items(conn, options):
    query = '''SELECT first_name, last_name, code, grade, class_name,
                      father_phone, mother_phone, parent_phone
               FROM students
               WHERE (status IS NULL OR status = '' OR status = 'فعال')'''
    params = []
    if options['class_filter']:
        query += ' AND class_name = ?'
        params.append(options['class_filter'])
    items = []
    for row in conn.execute(query, params).fetchall():
        item = dict(row)
        item['name'] = _join_name(item.get('first_name'), item.get('last_name'))
        father_raw, mother_raw = item.get('father_phone'), item.get('mother_phone')
        legacy = _clean(item.get('parent_phone'))
        if not _clean(father_raw) and not _clean(mother_raw) and legacy:
            father_raw = legacy  # پرونده‌های قدیمی فقط یک شماره دارند
        father, mother = _split_phone_field(father_raw, _FATHER_LABEL)
        extra_father, extra_mother = _split_phone_field(mother_raw, _MOTHER_LABEL)
        item['father'] = ' / '.join(part for part in (father, extra_father) if part)
        item['mother'] = ' / '.join(part for part in (mother, extra_mother) if part)
        item['grade'] = _clean(item.get('grade'))
        item['class'] = _clean(item.get('class_name'))
        item['code'] = _clean(item.get('code'))
        item['badge'] = ''
        if options['hide_empty'] == 'yes' and not (item['father'] or item['mother']):
            continue
        items.append(item)
    return items


def _staff_items(conn, options):
    items = []
    if options['staff_filter'] in ('all', 'teachers'):
        rows = conn.execute('''SELECT first_name, last_name, code, subject,
                                      class_name, phone
                               FROM teachers''').fetchall()
        for row in rows:
            item = dict(row)
            item['name'] = _join_name(item.get('first_name'), item.get('last_name'))
            item['phone'] = _clean(item.get('phone'))
            item['subject'] = _clean(item.get('subject'))
            item['class'] = _clean(item.get('class_name'))
            item['code'] = _clean(item.get('code'))
            item['vehicle'] = ''
            item['badge'] = ''
            if options['hide_empty'] == 'yes' and not item['phone']:
                continue
            items.append(item)
    if options['staff_filter'] in ('all', 'drivers'):
        rows = conn.execute('''SELECT driver_name, phone, vehicle
                               FROM service_driver_registry
                               ORDER BY driver_name''').fetchall()
        for row in rows:
            item = {'name': _clean(row['driver_name']), 'last_name': _clean(row['driver_name']),
                    'first_name': _clean(row['driver_name']), 'phone': _clean(row['phone']),
                    'subject': '', 'class': 'سرویس مدرسه', 'code': '', 'service': True,
                    'vehicle': _clean(row['vehicle']), 'badge': 'راننده سرویس'}
            if options['hide_empty'] == 'yes' and not item['phone']:
                continue
            items.append(item)
    return items


def _class_options(conn, current):
    rows = conn.execute('''SELECT DISTINCT class_name FROM students
                           WHERE class_name IS NOT NULL AND class_name <> ''
                           ORDER BY class_name''').fetchall()
    names = [_clean(row['class_name']) for row in rows]
    names = [name for name in names if name]
    names.sort(key=_natural_key)
    if current and current not in names:
        names.insert(0, current)
    return names


def _collect(source, conn, saved):
    options = _options(source, saved)
    staff_columns = _column_spec(_STAFF_COLUMNS, options['staff_cols'], options['row_no'])
    parent_columns = _column_spec(_PARENT_COLUMNS, options['parent_cols'], options['row_no'])
    staff_items = _staff_items(conn, options)
    parent_items = _parent_items(conn, options)
    if options['show_contact_type'] == 'no':
        for item in staff_items:
            item['badge'] = ''
    staff_book = _build_book(staff_items, staff_columns, options['group_by'], options['extra_rows'])
    parent_book = _build_book(parent_items, parent_columns, options['group_by'], options['extra_rows'])

    books = []
    if options['section_filter'] in ('both', 'staff'):
        books.append(dict(staff_book, key='staff', title=TITLES['staff'], new_page=False))
    if options['section_filter'] in ('both', 'parents'):
        books.append(dict(parent_book, key='parents', title=TITLES['parents'],
                          new_page=options['section_filter'] == 'both'
                          and options['parents_page'] == 'yes'))

    context = dict(options)
    context.update({
        'books': books,
        'staff_count': staff_book['count'],
        'parent_count': parent_book['count'],
        'staff_coverage': _coverage(staff_items, 'phone'),
        'parent_coverage': _coverage(parent_items, None),
        'class_options': _class_options(conn, options['class_filter']),
        'empty_labels': EMPTY_LABELS,
        'group_labels': GROUP_LABELS,
        'staff_column_labels': _STAFF_COLUMNS,
        'parent_column_labels': _PARENT_COLUMNS,
        'settings_saved': bool(saved),
        'print_params': _params(options),
        'hidden_fields': _flat_params(_params(options)),
        'filter_params': _params(options, only=_FILTER_KEYS),
    })
    return context


def _coverage(items, key):
    """چه تعداد از ردیف‌ها شمارهٔ ثبت‌شده دارند (برای گزارش روی سرصفحه)."""
    if key is None:
        filled = sum(1 for item in items if item.get('father') or item.get('mother'))
    else:
        filled = sum(1 for item in items if _clean(item.get(key)))
    return {'filled': filled, 'total': len(items)}


# ---------------------------------------------------------------------------
# مسیرها
# ---------------------------------------------------------------------------
def _describe(options):
    return (f"cols={options['cols']}, staff={','.join(options['staff_cols'])}, "
            f"parents={','.join(options['parent_cols'])}, group_by={options['group_by']}, "
            f"table_header={options['table_header']}, row_no={options['row_no']}")


def contact_book():
    """صفحهٔ تعاملی دفترچه تلفن؛ POST یعنی ذخیره/پاک‌کردن تنظیمات پیش‌فرض."""
    user_id = session.get('user_id')
    action = (request.form.get('action') or '').strip() if request.method == 'POST' else ''
    with get_db() as conn:
        saved = _load_saved(conn, user_id)
        if action == 'save':
            explicit = _options(request.values, {})
            saved = {key: explicit[key] for key in _PERSISTED_KEYS}
            _save_settings(conn, user_id, saved)
        elif action == 'reset':
            _clear_settings(conn, user_id)
            saved = {}
        context = _collect(request.values, conn, saved)

    if action in ('save', 'reset'):
        audit(user_id, 'save_contact_book_settings', 'app_settings', f'user:{user_id}',
              action + ': ' + _describe(context))
        if action == 'save':
            flash('تنظیمات دفترچه تلفن ذخیره شد؛ از این پس همین چیدمان پیش‌فرض است.', 'success')
        else:
            flash('تنظیمات ذخیره‌شده پاک شد و پیش‌فرض‌های کارخانه برگشت.', 'info')
        return redirect(url_for('contact_book', **context['filter_params']))

    return render_template('contact_book.html', **context)


def contact_book_print():
    """صفحهٔ مستقل و آمادهٔ چاپ (بدون حاشیهٔ برنامه)."""
    with get_db() as conn:
        context = _collect(request.args, conn, _load_saved(conn, session.get('user_id')))
    return render_template('contact_book_print.html', **context)


def register(app):
    app.add_url_rule('/contact-book', endpoint='contact_book', view_func=contact_book,
                     methods=['GET', 'POST'])
    app.add_url_rule('/contact-book/print', endpoint='contact_book_print',
                     view_func=contact_book_print)
