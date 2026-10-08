from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for

from ..custom_fields import (apply_values_to_fields, collect_values, fields_for_form,
                              fields_for_profile, save_values, validate_values)
from ..database import auto_backup, get_db
from ..dates import calculate_jalali_age
from ..report_print_layouts import (REPORT_SECTIONS, load_layout as load_report_layout,
                                    save_layout as save_report_layout)
from ..security import audit, teacher_scope
from ..student_dashboard import (STUDENT_VIEWS, build_dashboard_context,
                                 save_student_view)


STUDENT_FIELDS = [
    'first_name', 'last_name', 'code', 'birth_date', 'grade', 'class_name', 'sida_class',
    'parent_phone', 'father_phone', 'mother_phone', 'father_name', 'father_code',
    'mother_name', 'mother_last_name', 'mother_code', 'address', 'teacher_code', 'admission_year',
    'admission_type', 'religion', 'insurance_type', 'sisters_count', 'brothers_count',
    'postal_code', 'economic_decile', 'medications', 'father_job', 'father_education',
    'mother_job', 'mother_education', 'repeat_grade_prep', 'repeat_grade_advanced', 'repeat_grade_first1', 'repeat_grade_first2', 'repeat_grade_first3', 'repeat_grade_1', 'repeat_grade_2', 'repeat_grade_3',
    'repeat_grade_4', 'repeat_grade_5', 'repeat_grade_6', 'license_years', 'child_order',
    'diseases', 'vaccinations_complete', 'drug_allergy', 'behavioral_traits', 'parents_alive',
    'parents_separated', 'child_lives_with', 'parents_related', 'martyr_quota',
    'financial_status', 'father_birth_date', 'father_id_serial', 'father_id_serial_letter',
    'father_id_issue_place', 'mother_birth_date', 'mother_id_serial', 'mother_id_serial_letter',
    'mother_id_issue_place', 'student_id_serial', 'student_id_serial_letter',
    'student_id_issue_place', 'is_emdad_member', 'is_behzisti_member', 'entry_year_grade_prep', 'entry_year_grade_advanced', 'entry_year_grade_first1', 'entry_year_grade_first2', 'entry_year_grade_first3', 'entry_year_grade_1',
    'entry_year_grade_2', 'entry_year_grade_3', 'entry_year_grade_4', 'entry_year_grade_5',
    'entry_year_grade_6', 'photo', 'student_birth_place', 'gender', 'student_id_issue_date',
    'father_birth_place', 'father_id_issue_date', 'mother_birth_place', 'mother_id_issue_date',
    'father_physical_status', 'father_mental_status', 'mother_physical_status', 'mother_mental_status',
    'assessment_result', 'disability_type', 'bank_name', 'iban',
]


EMPTY = 'ثبت نشده'

PROFILE_LABELS = {
    'id': 'شناسه داخلی',
    'first_name': 'نام', 'last_name': 'نام خانوادگی', 'code': 'کد دانش‌آموزی',
    'birth_date': 'تاریخ تولد', 'gender': 'جنسیت', 'student_birth_place': 'محل تولد',
    'religion': 'مذهب', 'insurance_type': 'نوع بیمه', 'status': 'وضعیت پرونده',
    'photo': 'نام فایل عکس', 'student_id_serial': 'سریال شناسنامه',
    'student_id_serial_letter': 'حرف سریال شناسنامه', 'student_id_issue_place': 'محل صدور شناسنامه',
    'student_id_issue_date': 'تاریخ صدور شناسنامه',
    'grade': 'پایه', 'class_name': 'کلاس مدرسه', 'sida_class': 'کلاس سیدا',
    'teacher_name': 'معلم منتسب', 'teacher_code': 'کد معلم / پرسنلی',
    'admission_year': 'سال ورود', 'admission_type': 'نوع پذیرش', 'license_years': 'مجوز سال‌های تحصیلی',
    'repeat_grade_prep': 'توقف آمادگی مقدماتی', 'repeat_grade_advanced': 'توقف آمادگی تکمیلی', 'repeat_grade_first1': 'توقف پایه اول۱', 'repeat_grade_first2': 'توقف پایه اول۲', 'repeat_grade_first3': 'توقف پایه اول۳',
    'repeat_grade_1': 'توقف پایه اول (قدیمی)', 'repeat_grade_2': 'تکرار پایه دوم',
    'repeat_grade_3': 'تکرار پایه سوم', 'repeat_grade_4': 'تکرار پایه چهارم',
    'repeat_grade_5': 'تکرار پایه پنجم', 'repeat_grade_6': 'تکرار پایه ششم',
    'entry_year_grade_prep': 'سال ورود آمادگی مقدماتی', 'entry_year_grade_advanced': 'سال ورود آمادگی تکمیلی', 'entry_year_grade_first1': 'سال ورود پایه اول۱', 'entry_year_grade_first2': 'سال ورود پایه اول۲', 'entry_year_grade_first3': 'سال ورود پایه اول۳',
    'entry_year_grade_1': 'سال ورود پایه اول (قدیمی)', 'entry_year_grade_2': 'سال ورود پایه دوم',
    'entry_year_grade_3': 'سال ورود پایه سوم', 'entry_year_grade_4': 'سال ورود پایه چهارم',
    'entry_year_grade_5': 'سال ورود پایه پنجم', 'entry_year_grade_6': 'سال ورود پایه ششم',
    'father_name': 'نام پدر', 'father_code': 'کد ملی پدر', 'father_phone': 'تلفن پدر',
    'father_birth_date': 'تاریخ تولد پدر', 'father_birth_place': 'محل تولد پدر',
    'father_id_serial': 'سریال شناسنامه پدر', 'father_id_serial_letter': 'حرف سریال پدر',
    'father_id_issue_place': 'محل صدور شناسنامه پدر', 'father_id_issue_date': 'تاریخ صدور شناسنامه پدر',
    'father_job': 'شغل پدر', 'father_education': 'تحصیلات پدر',
    'mother_name': 'نام مادر', 'mother_last_name': 'نام خانوادگی مادر', 'mother_code': 'کد ملی مادر', 'mother_phone': 'تلفن مادر',
    'mother_birth_date': 'تاریخ تولد مادر', 'mother_birth_place': 'محل تولد مادر',
    'mother_id_serial': 'سریال شناسنامه مادر', 'mother_id_serial_letter': 'حرف سریال مادر',
    'mother_id_issue_place': 'محل صدور شناسنامه مادر', 'mother_id_issue_date': 'تاریخ صدور شناسنامه مادر',
    'mother_job': 'شغل مادر', 'mother_education': 'تحصیلات مادر',
    'parent_phone': 'تلفن ولی', 'address': 'نشانی', 'postal_code': 'کد پستی',
    'parents_alive': 'وضعیت حیات والدین', 'parents_separated': 'جدایی والدین',
    'child_lives_with': 'دانش‌آموز با چه کسی زندگی می‌کند', 'parents_related': 'نسبت فامیلی والدین',
    'sisters_count': 'تعداد خواهر', 'brothers_count': 'تعداد برادر', 'child_order': 'فرزند چندم',
    'diseases': 'بیماری‌ها', 'medications': 'داروها', 'vaccinations_complete': 'کامل‌بودن واکسن',
    'drug_allergy': 'حساسیت دارویی', 'behavioral_traits': 'ویژگی‌های رفتاری',
    'economic_decile': 'دهک اقتصادی', 'financial_status': 'وضعیت مالی', 'service_fee': 'مبلغ سرویس',
    'bank_name': 'نام بانک حساب دانش‌آموز', 'iban': 'شماره شبا حساب دانش‌آموز',
    'martyr_quota': 'سهمیه ایثارگری', 'is_emdad_member': 'عضو کمیته امداد',
    'is_behzisti_member': 'عضو بهزیستی', 'grade_repeats': 'سوابق تکرار پایه',
    'father_physical_status': 'وضعیت جسمی پدر', 'father_mental_status': 'وضعیت روانی پدر',
    'mother_physical_status': 'وضعیت جسمی مادر', 'mother_mental_status': 'وضعیت روانی مادر',
    'assessment_result': 'نتیجه تست سنجش', 'disability_type': 'نوع معلولیت',
}

PROFILE_SECTIONS = [
    ('👤 اطلاعات هویتی و پرونده', ['id', 'first_name', 'last_name', 'code', 'birth_date', 'gender', 'student_birth_place', 'religion', 'insurance_type', 'status', 'photo']),
    ('🪪 اطلاعات شناسنامه‌ای دانش‌آموز', ['student_id_serial', 'student_id_serial_letter', 'student_id_issue_place', 'student_id_issue_date']),
    ('📚 اطلاعات آموزشی و انتساب', ['grade', 'class_name', 'sida_class', 'teacher_name', 'teacher_code', 'admission_year', 'admission_type', 'license_years', 'assessment_result', 'disability_type', 'child_order']),
    ('👨‍👩‍👧 خانواده و راه‌های تماس', ['father_name', 'father_code', 'father_phone', 'father_birth_date', 'father_birth_place', 'father_id_serial', 'father_id_serial_letter', 'father_id_issue_place', 'father_id_issue_date', 'father_job', 'father_education', 'father_physical_status', 'father_mental_status', 'mother_name', 'mother_last_name', 'mother_code', 'mother_phone', 'mother_birth_date', 'mother_birth_place', 'mother_id_serial', 'mother_id_serial_letter', 'mother_id_issue_place', 'mother_id_issue_date', 'mother_job', 'mother_education', 'mother_physical_status', 'mother_mental_status', 'parent_phone', 'address', 'postal_code', 'parents_alive', 'parents_separated', 'child_lives_with', 'parents_related', 'sisters_count', 'brothers_count']),
    ('🩺 سلامت و ویژگی‌های فردی', ['diseases', 'medications', 'vaccinations_complete', 'drug_allergy', 'behavioral_traits']),
    ('💳 وضعیت مالی و حمایتی', ['economic_decile', 'financial_status', 'service_fee', 'martyr_quota', 'is_emdad_member', 'is_behzisti_member']),
    ('🏦 اطلاعات حساب بانکی', ['bank_name', 'iban']),
]

PROFILE_BOOLEAN_FIELDS = {'parents_separated', 'parents_related', 'vaccinations_complete', 'drug_allergy', 'is_emdad_member', 'is_behzisti_member'}
PROFILE_WIDE_FIELDS = {'address', 'diseases', 'medications', 'behavioral_traits', 'financial_status', 'grade_repeats'}

GRADE_REPEAT_DEFS = [
    ('repeat_grade_prep', 'entry_year_grade_prep', 'آمادگی مقدماتی'),
    ('repeat_grade_advanced', 'entry_year_grade_advanced', 'آمادگی تکمیلی'),
    ('repeat_grade_first1', 'entry_year_grade_first1', 'اول ۱'),
    ('repeat_grade_first2', 'entry_year_grade_first2', 'اول ۲'),
    ('repeat_grade_first3', 'entry_year_grade_first3', 'اول ۳'),
    ('repeat_grade_2', 'entry_year_grade_2', 'دوم'),
    ('repeat_grade_3', 'entry_year_grade_3', 'سوم'),
    ('repeat_grade_4', 'entry_year_grade_4', 'چهارم'),
    ('repeat_grade_5', 'entry_year_grade_5', 'پنجم'),
    ('repeat_grade_6', 'entry_year_grade_6', 'ششم'),
]

SIBLING_FIELDS = ('sibling_type', 'full_name', 'age', 'education', 'marital_status', 'job', 'physical_status', 'mental_status', 'kinship')
SIBLING_FORM_KEYS = {
    'sibling_type': 'sibling_type[]', 'full_name': 'sibling_name[]', 'age': 'sibling_age[]',
    'education': 'sibling_education[]', 'marital_status': 'sibling_marital_status[]',
    'job': 'sibling_job[]', 'physical_status': 'sibling_physical_status[]',
    'mental_status': 'sibling_mental_status[]', 'kinship': 'sibling_kinship[]',
}


def _build_grade_repeat_rows(data: dict) -> list[dict[str, str]]:
    """Build a compact, print-friendly table of stop-in-grade counts and entry years."""
    rows = []
    for repeat_key, entry_key, label in GRADE_REPEAT_DEFS:
        count = str(data.get(repeat_key) or '').strip()
        entry_year = str(data.get(entry_key) or '').strip()
        if not count and not entry_year:
            continue
        rows.append({
            'grade': label,
            'count': count if count else '۰',
            'entry_year': entry_year if entry_year else EMPTY,
        })
    return rows


def _collect_siblings(form) -> list[dict[str, str]]:
    """Read the repeatable sibling rows submitted from the add/edit student form."""
    raw = {field: form.getlist(SIBLING_FORM_KEYS[field]) for field in SIBLING_FIELDS}
    row_count = max((len(values) for values in raw.values()), default=0)
    siblings = []
    for index in range(row_count):
        row = {field: _text((raw[field][index] if index < len(raw[field]) else ''), 200) for field in SIBLING_FIELDS}
        if any(row.values()):
            siblings.append(row)
    return siblings


def _get_siblings(conn, student_id: int) -> list[dict[str, str]]:
    rows = conn.execute(
        'SELECT * FROM student_siblings WHERE student_id=? ORDER BY sort_order,id', (student_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def _save_siblings(conn, student_id: int, siblings: list[dict[str, str]]) -> None:
    conn.execute('DELETE FROM student_siblings WHERE student_id=?', (student_id,))
    for order, sibling in enumerate(siblings):
        conn.execute(
            'INSERT INTO student_siblings '
            '(student_id, sibling_type, full_name, age, education, marital_status, job, '
            'physical_status, mental_status, kinship, sort_order) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (student_id, sibling.get('sibling_type', ''), sibling.get('full_name', ''), sibling.get('age', ''),
             sibling.get('education', ''), sibling.get('marital_status', ''), sibling.get('job', ''),
             sibling.get('physical_status', ''), sibling.get('mental_status', ''), sibling.get('kinship', ''), order),
        )



def _text(value: object, limit: int = 500) -> str:
    return str(value or '').strip()[:limit]


def _safe_return_url(value: object, fallback: str) -> str:
    candidate = _text(value, 500)
    return candidate if candidate.startswith('/') and not candidate.startswith('//') else fallback


def _remove_uploaded_photo(filename: object) -> None:
    name = str(filename or '').strip()
    if not name:
        return
    # Only remove a basename created by upload_photo; never follow a user-supplied path.
    safe_name = Path(name).name
    if safe_name != name:
        return
    try:
        path = Path(current_app.config['UPLOAD_FOLDER']) / safe_name
        if path.is_file():
            path.unlink()
    except OSError:
        current_app.logger.warning('could not remove student photo: %s', safe_name)


def _student_form_data(form) -> dict[str, str]:
    data = {field: _text(form.get(field), 500) for field in STUDENT_FIELDS}
    digit_map = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    data['iban'] = data.get('iban', '').replace(' ', '').translate(digit_map).upper()
    return data


def _validate_extra_fields(data: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for field, label in (('father_code', 'کد ملی پدر'), ('mother_code', 'کد ملی مادر')):
        value = data.get(field, '')
        if value and (not re.fullmatch(r'\d{10}', value)):
            errors.append(f'{label} باید دقیقاً ۱۰ رقم باشد.')
    postal = data.get('postal_code', '')
    if postal and not re.fullmatch(r'\d{10}', postal):
            errors.append('کد پستی باید دقیقاً ۱۰ رقم باشد.')
    iban = data.get('iban', '').replace(' ', '').upper()
    if iban and not re.fullmatch(r'IR\d{24}', iban):
        errors.append('شماره شبا باید با IR و سپس ۲۴ رقم وارد شود.')
    if data.get('economic_decile'):
        try:
            decile = int(data['economic_decile'])
            if not 1 <= decile <= 10:
                errors.append('دهک اقتصادی باید بین ۱ تا ۱۰ باشد.')
        except ValueError:
            errors.append('دهک اقتصادی نامعتبر است.')
    if data.get('child_order'):
        try:
            if not 1 <= int(data['child_order']) <= 20:
                errors.append('فرزند چندم باید بین ۱ تا ۲۰ باشد.')
        except ValueError:
            errors.append('فرزند چندم نامعتبر است.')
    if data.get('teacher_code'):
        with get_db() as conn:
            if not conn.execute('SELECT 1 FROM teachers WHERE code=?', (data['teacher_code'],)).fetchone():
                errors.append('معلم انتخاب‌شده معتبر نیست.')
    return errors


def _teacher_options(conn):
    return conn.execute('SELECT code,first_name,last_name FROM teachers ORDER BY first_name,last_name').fetchall()


def index():
    return render_template('index.html', **build_dashboard_context())


def student_card_view():
    """ذخیرهٔ شیوهٔ نمایش فهرست دانش‌آموزان (کارت‌های پنج‌تراکم یا جدول کامل) برای همین کاربر."""
    payload = request.get_json(silent=True) or {}
    value = payload.get('view', request.form.get('view'))
    chosen = str(value or '').strip()
    if chosen not in STUDENT_VIEWS:
        return jsonify({'error': 'شیوهٔ نمایش نامعتبر است.', 'views': list(STUDENT_VIEWS)}), 400
    user_id = session.get('user_id')
    with get_db() as conn:
        saved = save_student_view(conn, user_id, chosen)
        conn.commit()
    audit(user_id, 'save_student_card_view', 'app_settings', f'user:{user_id}', saved)
    return jsonify({'ok': True, 'view': saved, 'label': STUDENT_VIEWS[saved]})


def vdashboard():
    # Keep old bookmarks working while presenting one consistent dashboard.
    return redirect(url_for('index'))


def upload_photo():
    if 'photo' not in request.files:
        return jsonify({'error': 'فایلی ارسال نشده است.'}), 400
    file = request.files['photo']
    if not file.filename:
        return jsonify({'error': 'فایلی انتخاب نشده است.'}), 400
    allowed = {'png', 'jpg', 'jpeg', 'gif'}
    ext = Path(file.filename).suffix.lower().lstrip('.')
    if ext not in allowed:
        return jsonify({'error': 'فرمت فایل مجاز نیست.'}), 400
    new_filename = f'{uuid.uuid4().hex}.{ext}'
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], new_filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)
    return jsonify({'filename': new_filename})


def add_student():
    with get_db() as conn:
        teachers = _teacher_options(conn)
        custom_fields = fields_for_form(conn)
        if request.method == 'POST':
            data = _student_form_data(request.form)
            custom_values = collect_values(request.form, custom_fields)
            apply_values_to_fields(custom_fields, custom_values)
            siblings = _collect_siblings(request.form)
            errors = _validate_extra_fields(data) + validate_values(custom_fields, custom_values)
            if not data['first_name'] or not data['last_name'] or not data['code']:
                errors.append('نام، نام‌خانوادگی و کد دانش‌آموزی الزامی است.')
            if errors:
                return render_template('add_student.html', errors=errors, form_data=data,
                                       teachers=teachers, custom_fields=custom_fields, siblings=siblings)
            try:
                auto_backup()
                columns = ','.join(STUDENT_FIELDS)
                placeholders = ','.join('?' for _ in STUDENT_FIELDS)
                cursor = conn.execute(f'INSERT INTO students ({columns}) VALUES ({placeholders})',
                                      [data[field] for field in STUDENT_FIELDS])
                save_values(conn, cursor.lastrowid, custom_values)
                _save_siblings(conn, cursor.lastrowid, siblings)
                conn.commit()
                flash('دانش‌آموز با موفقیت ثبت شد.', 'success')
                return redirect(url_for('index'))
            except Exception:
                current_app.logger.exception('student creation failed')
                errors.append('ثبت دانش‌آموز انجام نشد؛ احتمالاً کد دانش‌آموزی تکراری است.')
                return render_template('add_student.html', errors=errors, form_data=data,
                                       teachers=teachers, custom_fields=custom_fields, siblings=siblings)
    return render_template('add_student.html', errors=None, form_data={}, teachers=teachers,
                           custom_fields=custom_fields, siblings=[])


def edit_student(id):
    with get_db() as conn:
        student = conn.execute('SELECT * FROM students WHERE id=?', (id,)).fetchone()
        if not student:
            flash('دانش‌آموز پیدا نشد.', 'danger')
            return redirect(url_for('index'))
        teachers = _teacher_options(conn)
        custom_fields = fields_for_form(conn, id)
        if request.method == 'POST':
            data = _student_form_data(request.form)
            custom_values = collect_values(request.form, custom_fields)
            apply_values_to_fields(custom_fields, custom_values)
            siblings = _collect_siblings(request.form)
            errors = _validate_extra_fields(data) + validate_values(custom_fields, custom_values)
            if not data['first_name'] or not data['last_name'] or not data['code']:
                errors.append('نام، نام‌خانوادگی و کد دانش‌آموزی الزامی است.')
            if errors:
                return render_template('edit_student.html', student=student, errors=errors,
                                       form_data=data, teachers=teachers, custom_fields=custom_fields, siblings=siblings)
            try:
                auto_backup()
                assignments = ','.join(f'{field}=?' for field in STUDENT_FIELDS)
                conn.execute(f'UPDATE students SET {assignments} WHERE id=?',
                             [data[field] for field in STUDENT_FIELDS] + [id])
                save_values(conn, id, custom_values)
                _save_siblings(conn, id, siblings)
                conn.commit()
                if student['photo'] and student['photo'] != data.get('photo', ''):
                    _remove_uploaded_photo(student['photo'])
                flash('اطلاعات دانش‌آموز به‌روزرسانی شد.', 'success')
                return redirect(url_for('student_profile', id=id))
            except Exception:
                current_app.logger.exception('student update failed')
                errors.append('ویرایش دانش‌آموز انجام نشد؛ احتمالاً کد دانش‌آموزی تکراری است.')
                return render_template('edit_student.html', student=student, errors=errors,
                                       form_data=data, teachers=teachers, custom_fields=custom_fields, siblings=siblings)
        siblings = _get_siblings(conn, id)
    return render_template('edit_student.html', student=student, errors=None, form_data={}, teachers=teachers,
                           custom_fields=custom_fields, siblings=siblings)


def search():
    q = _text(request.args.get('q'), 100)
    return redirect(url_for('index', q=q)) if q else redirect(url_for('index'))


def _safe_student_dict(row):
    safe = {
        'id', 'first_name', 'last_name', 'code', 'birth_date', 'grade', 'class_name',
        'sida_class', 'gender', 'teacher_code', 'teacher_first', 'teacher_last',
        'status', 'photo',
    }
    return {key: row[key] for key in row.keys() if key in safe}


def _profile_value(key: str, value: object) -> str:
    if value is None or str(value).strip() == '':
        return EMPTY
    if key in PROFILE_BOOLEAN_FIELDS:
        normalized = str(value).strip().lower()
        if normalized in {'1', 'true', 'yes', 'بله', 'دارد'}:
            return 'بله'
        if normalized in {'0', 'false', 'no', 'خیر', 'ندارد'}:
            return 'خیر'
    return str(value)


def _profile_sections(student, restricted: bool, age: dict[str, object], custom_fields=None) -> list[dict[str, object]]:
    """Build a complete, readable profile without weakening teacher privacy."""
    data = dict(student)
    # parent_phone is a retired field; its values are migrated to father_phone
    # during database startup and it must not reappear in the readable profile.
    data.pop('parent_phone', None)
    teacher_first = data.pop('teacher_first', '') or ''
    teacher_last = data.pop('teacher_last', '') or ''
    data['teacher_name'] = f'{teacher_first} {teacher_last}'.strip()
    allowed = set(data) if not restricted else {
        'id', 'first_name', 'last_name', 'code', 'birth_date', 'grade', 'class_name',
        'sida_class', 'gender', 'teacher_code', 'status', 'photo', 'teacher_name',
    }
    used: set[str] = set()
    # Grade-repeat and entry-year columns are already rendered in their own dedicated
    # "تعداد توقف و سال ورود" table below; skip them here so they are not shown twice.
    for repeat_key, entry_key, _label in GRADE_REPEAT_DEFS:
        used.add(repeat_key)
        used.add(entry_key)
    used.add('repeat_grade_1')
    used.add('entry_year_grade_1')
    used.add('grade_repeats')  # legacy free-text field superseded by the per-grade table above
    sections: list[dict[str, object]] = [
        {'key': 'identity', 'title': '🎂 سن محاسبه‌شده', 'items': [
            {'key': 'age', 'label': 'سن در تاریخ امروز', 'value': str(age.get('text') or EMPTY), 'wide': False},
        ]}
    ]
    section_keys = ('identity', 'identity_card', 'education', 'family', 'health', 'finance', 'bank')
    for section_key, (title, keys) in zip(section_keys, PROFILE_SECTIONS):
        items = []
        for key in keys:
            if key not in allowed or key in used:
                continue
            if key not in data:
                continue
            items.append({
                'key': key,
                'label': PROFILE_LABELS.get(key, key),
                'value': _profile_value(key, data.get(key)),
                'wide': key in PROFILE_WIDE_FIELDS,
            })
            used.add(key)
        if items:
            sections.append({'key': section_key, 'title': title, 'items': items})

    remaining = [key for key in data if key not in used and key in allowed]
    if remaining:
        sections.append({'key': 'other', 'title': '🧾 سایر اطلاعات ثبت‌شده', 'items': [
            {'key': key, 'label': PROFILE_LABELS.get(key, key),
             'value': _profile_value(key, data.get(key)), 'wide': key in PROFILE_WIDE_FIELDS}
            for key in remaining
        ]})
    if custom_fields:
        sections.append({'key': 'custom', 'title': '🧩 اطلاعات تکمیلی سفارشی', 'items': [
            {'key': f"custom_{field['id']}", 'label': field['label'],
             'value': _profile_value('', field.get('value')), 'wide': False}
            for field in custom_fields
        ]})
    return sections


def _student_scope_query(id_value=None, include_inactive: bool = False):
    scope = teacher_scope()
    active_clause = " WHERE 1=1" if include_inactive else " WHERE (s.status='فعال' OR s.status IS NULL)"
    query = '''SELECT s.*, t.first_name AS teacher_first, t.last_name AS teacher_last
               FROM students s LEFT JOIN teachers t ON s.teacher_code=t.code''' + active_clause
    params: list[object] = []
    if id_value is not None:
        query += ' AND s.id=?'
        params.append(id_value)
    if scope:
        query += ' AND s.teacher_code=?'
        params.append(scope)
    return query, params


def student_profile(id):
    restricted = session.get('role') == 'teacher'
    with get_db() as conn:
        query, params = _student_scope_query(id, include_inactive=not restricted)
        student = conn.execute(query, params).fetchone()
        custom_fields = fields_for_profile(conn, id, include_teacher=not restricted)
        siblings = [] if restricted else _get_siblings(conn, id)
    if not student:
        flash('دانش‌آموز پیدا نشد یا در محدوده دسترسی شما نیست.', 'danger')
        return redirect(url_for('index'))
    grade_repeat_rows = _build_grade_repeat_rows(dict(student))
    if restricted:
        student = _safe_student_dict(student)
    age = calculate_jalali_age(student.get('birth_date') if isinstance(student, dict) else student['birth_date'])
    return render_template(
        'student_profile.html', student=student, age=age,
        profile_sections=_profile_sections(student, restricted, age, custom_fields), restricted=restricted,
        grade_repeat_rows=grade_repeat_rows, siblings=siblings,
    )


def print_student(id):
    restricted = session.get('role') == 'teacher'
    with get_db() as conn:
        query, params = _student_scope_query(id, include_inactive=not restricted)
        student = conn.execute(query, params).fetchone()
        custom_fields = fields_for_profile(conn, id, include_teacher=not restricted)
        siblings = [] if restricted else _get_siblings(conn, id)
        student_info_layout = load_report_layout(conn, 'student_info', session.get('user_id'))
    if not student:
        flash('دانش‌آموز یافت نشد.', 'danger')
        return redirect(url_for('index'))
    grade_repeat_rows = _build_grade_repeat_rows(dict(student))
    if restricted:
        student = _safe_student_dict(student)
    age = calculate_jalali_age(student.get('birth_date') if isinstance(student, dict) else student['birth_date'])
    profile_sections = _profile_sections(student, restricted, age, custom_fields)
    return render_template(
        'print_student.html', student=student, age=age,
        profile_sections=profile_sections, restricted=restricted,
        grade_repeat_rows=grade_repeat_rows,
        siblings=siblings,
        student_info_layout=student_info_layout,
    )


"""Public filter helper shared by the print/Excel views of the students list.

Any caller passes a mapping (``request.args`` or ``request.form``) and receives
the ready SQL, its parameters and the chosen filter values. Teacher scoping and
the "active records only" rule are always applied here, exactly like the
dashboard, so no view has to repeat them.
"""
def filtered_students_query(args):
    scope = teacher_scope()
    values = {key: _text(args.get(key), 100) for key in ('q', 'grade', 'class_name', 'sida_class', 'gender', 'teacher_code')}
    clauses = ["(s.status='فعال' OR s.status IS NULL)"]
    params: list[object] = []
    if scope:
        clauses.append('s.teacher_code=?')
        params.append(scope)
    if values['q']:
        like = f"%{values['q']}%"
        clauses.append("(" + " OR ".join(f"COALESCE(s.{field},'') LIKE ?" for field in ('first_name','last_name','code','grade','class_name','sida_class','gender')) + ")")
        params.extend([like] * 7)
    for key in ('grade', 'class_name', 'sida_class', 'gender'):
        value = values[key]
        if value == '__empty__':
            clauses.append(f"NULLIF(TRIM(COALESCE(s.{key},'')),'') IS NULL")
        elif value:
            clauses.append(f's.{key}=?')
            params.append(value)
    if not scope and values['teacher_code']:
        if values['teacher_code'] == '__empty__':
            clauses.append(
                "(NULLIF(TRIM(COALESCE(s.teacher_code,'')),'') IS NULL OR NOT EXISTS ("
                "SELECT 1 FROM teachers teacher_match WHERE teacher_match.code=s.teacher_code))"
            )
        else:
            clauses.append('s.teacher_code=?')
            params.append(values['teacher_code'])
    query = '''SELECT s.*, t.first_name AS teacher_first, t.last_name AS teacher_last
               FROM students s LEFT JOIN teachers t ON s.teacher_code=t.code
               WHERE ''' + ' AND '.join(clauses) + ' ORDER BY s.first_name,s.last_name,s.id'
    return query, params, values


def _build_print_rows(students, restricted: bool, custom_by_student=None, siblings_by_student=None, layout=None):
    rows = []
    custom_by_student = custom_by_student or {}
    siblings_by_student = siblings_by_student or {}
    for row in students:
        view = _safe_student_dict(row) if restricted else row
        age = calculate_jalali_age(view.get('birth_date') if isinstance(view, dict) else view['birth_date'])
        profile_sections = _profile_sections(view, restricted, age,
                                              custom_by_student.get(int(row['id']), []))
        rows.append({
            'student': view,
            'age': age,
            'profile_sections': profile_sections,
            'grade_repeat_rows': _build_grade_repeat_rows(dict(row)),
            'siblings': ([] if restricted else siblings_by_student.get(int(row['id']), [])),
        })
    return rows


def print_filtered_students():
    query, params, selected = filtered_students_query(request.args)
    restricted = session.get('role') == 'teacher'
    with get_db() as conn:
        students = conn.execute(query, params).fetchall()
        student_info_layout = load_report_layout(conn, 'student_info', session.get('user_id'))
        custom_by_student = {
            int(row['id']): fields_for_profile(conn, int(row['id']), include_teacher=not restricted)
            for row in students
        }
        siblings_by_student = {} if restricted else {
            int(row['id']): _get_siblings(conn, int(row['id'])) for row in students
        }
    print_rows = _build_print_rows(students, restricted, custom_by_student, siblings_by_student, student_info_layout)
    section_keys = [
        [section['key'] for section in row['profile_sections']]
        + (['grade_repeats'] if row['grade_repeat_rows'] else [])
        + (['siblings'] if row['siblings'] else [])
        for row in print_rows
    ]
    return render_template(
        'print_selected.html', students=students,
        print_rows=print_rows, print_section_keys=section_keys,
        count=len(students), selected_filters=selected, restricted=restricted,
        student_info_layout=student_info_layout,
    )


def teacher_student_lists():
    """Print six monochrome teacher/student lists per A4 page.

    A teacher account is always constrained to its own personnel number. Managers
    and admins may print one teacher or all teachers; student rows are joined by
    the teacher_code stored on the student record.
    """
    restricted = session.get('role') == 'teacher'
    requested_code = _text(request.args.get('teacher_code'), 80)
    scope = teacher_scope()
    selected_code = scope if restricted else requested_code
    with get_db() as conn:
        teachers_query = '''
            SELECT t.id, t.code, t.first_name, t.last_name, t.subject, t.class_name,
                   t.sida_class, COUNT(s.id) AS student_count
            FROM teachers t
            LEFT JOIN students s ON s.teacher_code=t.code
                AND (s.status IS NULL OR s.status='' OR s.status='فعال')
        '''
        params = []
        if selected_code:
            teachers_query += ' WHERE t.code=? '
            params.append(selected_code)
        teachers_query += '''
            GROUP BY t.id, t.code, t.first_name, t.last_name, t.subject,
                     t.class_name, t.sida_class
            ORDER BY t.last_name, t.first_name, t.code
        '''
        teacher_rows = conn.execute(teachers_query, params).fetchall()
        lists = []
        for teacher in teacher_rows:
            students = conn.execute('''
                SELECT first_name, last_name, code, grade, class_name, sida_class, photo
                FROM students
                WHERE teacher_code=? AND (status IS NULL OR status='' OR status='فعال')
                ORDER BY last_name, first_name, id
            ''', (teacher['code'],)).fetchall()
            lists.append({
                'teacher': teacher,
                'students': students,
            })
        teacher_options = [] if restricted else conn.execute('''
            SELECT code, first_name, last_name FROM teachers
            ORDER BY last_name, first_name, code
        ''').fetchall()
    selected_label = None
    if selected_code and teacher_rows:
        selected_label = f"{teacher_rows[0]['first_name'] or ''} {teacher_rows[0]['last_name'] or ''}".strip()
    return render_template(
        'teacher_student_lists.html', lists=lists,
        teacher_options=teacher_options, selected_code=selected_code,
        selected_label=selected_label, restricted=restricted,
    )


def list_for_folders():
    """Compact label cards for attaching to the back of student folders.

    The screen preview is separate from the standalone print page. Teachers see
    only their own students.
    """
    restricted = session.get('role') == 'teacher'
    requested_code = _text(request.args.get('teacher_code'), 80)
    scope = teacher_scope()
    selected_code = scope if restricted else requested_code
    with get_db() as conn:
        folder_layout = load_report_layout(conn, 'folder_labels', session.get('user_id'))
    orientation = request.args.get('orientation')
    if orientation not in {'portrait', 'landscape'}:
        orientation = folder_layout['orientation']

    # ── تنظیمات ظاهری ────────────────────────────────────────────────────
    def _int(param: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int(request.args.get(param, default))
            return max(lo, min(hi, v))
        except (TypeError, ValueError):
            return default

    def _str(param: str, default: str, choices: list[str]) -> str:
        v = request.args.get(param, default) or default
        return v if v in choices else default

    cols         = _int('cols',         folder_layout['grid']['columns'], 1, 6)
    rows         = _int('rows',         folder_layout['grid']['rows'], 1, 6)
    card_gap     = _str('card_gap',     '1.8mm', ['0.5mm','1mm','1.5mm','1.8mm','2mm','2.5mm','3mm'])
    card_padding = _str('card_padding', '3.5mm 4mm',
                        ['2mm 3mm','2.5mm 3mm','3mm 3.5mm','3.5mm 4mm','4mm 5mm','5mm 6mm'])
    stu_font     = _int('stu_font',     8, 5, 14)
    tea_font     = _int('tea_font',     11, 7, 18)
    meta_font    = _int('meta_font',    6, 4, 10)
    count_font   = _int('count_font',   6, 4, 10)
    stu_name_size= _int('stu_name_size', 6, 4, 10)
    stu_grade_size=_int('stu_grade_size', 5, 3, 8)
    tea_weight   = _str('tea_weight', '900', ['400','500','600','700','800','900'])
    stu_weight   = _str('stu_weight', '600', ['400','500','600','700','800'])
    meta_weight  = _str('meta_weight', '400', ['400','500','600','700'])
    count_weight = _str('count_weight', '800', ['400','500','600','700','800','900'])
    line_height  = _str('line_height', '1.4', ['1.2','1.3','1.4','1.5','1.6','1.8'])
    stu_spacing  = _str('stu_spacing', '0.4mm', ['0mm','0.2mm','0.3mm','0.4mm','0.5mm','0.6mm','0.8mm'])
    border_style  = _str('border_style', 'dashed', ['solid', 'dashed', 'dotted'])
    border_width  = _str('border_width', '1.2',  ['0.8','1.0','1.2','1.5','2.0'])
    border_color  = _str('border_color', '#6b7280',
                           ['#6b7280','#334155','#1e3a5f','#0f172a',
                            '#1e40af','#047857','#b91c1c','#7c3aed',
                            '#b45309','#dc2626','#2563eb','#16a34a',
                            '#fff','#e2e8f0','#94a3b8','#475569',
                            '#f59e0b','#ef4444','#8b5cf6','#06b6d4',
                            '#84cc16','#f97316','#ec4899','#64748b'])
    bg_card      = _str('bg_card',  '#ffffff',
                       ['#ffffff','#fafaf8','#f0f9ff','#f0fdf4',
                        '#fefce8','#fdf2f8','#faf5ff','#fff7ed',
                        '#f1f5f9','#eef2ff','#ecfeff','#f0fdf4',
                        '#fef9c3','#fff1f2','#faf5ff','#fffbeb'])
    radius       = _str('radius',   '3mm', ['0mm','1mm','2mm','3mm','4mm','5mm','6mm','8mm','10mm','12mm'])
    primary_color= _str('primary_color', '#1e3a5f',
                         ['#1e3a5f','#0b4f6c','#047857','#1e40af',
                          '#7c3aed','#b91c1c','#b45309','#dc2626',
                          '#2563eb','#16a34a','#475569','#0f172a',
                          '#6b7280','#92400e','#581c87','#991b1b',
                          '#1e3a8a','#065f46','#312e81','#7f1d1d'])
    count_radius = _str('count_radius', '2mm', ['0mm','1mm','1.5mm','2mm','3mm','4mm','5mm','999px'])
    tea_border_color = _str('tea_border_color', '#1e3a5f',
                             ['#1e3a5f','#0b4f6c','#047857','#1e40af',
                              '#7c3aed','#b91c1c','#b45309','#475569',
                              '#6b7280','#94a3b8','#0f172a','#334155',
                              '#000000','#333333','#666666','#999999',
                              '#2563eb','#16a34a','#dc2626','#f59e0b'])
    count_bg_color = _str('count_bg_color', '#1e3a5f',
                           ['#1e3a5f','#0b4f6c','#047857','#1e40af',
                            '#7c3aed','#b91c1c','#b45309','#2563eb',
                            '#16a34a','#475569','#0f172a','#334155',
                            '#000000','#333333','#666666','#999999',
                            '#dc2626','#f59e0b','#ec4899','#8b5cf6'])
    row_divider_style = _str('row_divider_style', 'dotted', ['none', 'dotted', 'dashed', 'solid'])
    row_divider_color = _str('row_divider_color', '#cbd5e1',
                              ['#cbd5e1','#94a3b8','#e2e8f0','#64748b',
                               '#475569','#334155','#1e3a5f','#0f172a',
                               '#f1f5f9','#f8fafc','#fff','#000000','#333333'])
    row_divider_width = _str('row_divider_width', '0.3', ['0','0.3','0.5','0.8','1.0','1.2'])
    photo_width  = _int('photo_width',  5, 4, 30)
    photo_height = _int('photo_height', 6, 4, 30)
    photo_shape  = _str('photo_shape',  'rounded', ['square', 'rounded', 'circle'])
    photo_border = _str('photo_border', 'yes', ['yes', 'no'])
    photo_border_color = _str('photo_border_color', '#cbd5e1',
                                ['#cbd5e1','#94a3b8','#e2e8f0','#64748b',
                                 '#475569','#334155','#1e3a5f','#fff',
                                 '#0f172a','#000000','#333333'])
    photo_radius = _str('photo_radius', '1.5mm', ['0mm','0.5mm','1mm','1.5mm','2mm','3mm','4mm','5mm'])
    show_photo   = _str('show_photo',   'yes', ['yes','no'])
    show_grade   = _str('show_grade',   'yes', ['yes','no'])
    show_subject = _str('show_subject', 'yes', ['yes','no'])
    show_numbering = _str('show_numbering', 'no', ['yes','no'])
    max_students = _int('max_students', 18, 5, 30)
    card_shadow  = _str('card_shadow',  'yes', ['yes','no'])
    show_divider_below_teacher = _str('show_divider_below_teacher', 'yes', ['yes','no'])
    heading_align = _str('heading_align', 'right', ['right', 'center', 'left'])
    stu_name_align = _str('stu_name_align', 'right', ['right', 'center', 'left'])
    grade_align  = _str('grade_align', 'left', ['right', 'center', 'left'])

    with get_db() as conn:
        teachers_query = '''
            SELECT t.id, t.code, t.first_name, t.last_name, t.subject,
                   COALESCE(t.class_name, '') AS class_name,
                   COUNT(s.id) AS student_count
            FROM teachers t
            LEFT JOIN students s ON s.teacher_code=t.code
                AND (s.status IS NULL OR s.status='' OR s.status='فعال')
        '''
        params = []
        if selected_code:
            teachers_query += ' WHERE t.code=? '
            params.append(selected_code)
        teachers_query += '''
            GROUP BY t.id, t.code, t.first_name, t.last_name, t.subject,
                     t.class_name
            ORDER BY t.last_name, t.first_name, t.code
        '''
        teacher_rows = conn.execute(teachers_query, params).fetchall()
        lists = []
        for teacher in teacher_rows:
            students = conn.execute('''
                SELECT first_name, last_name, code, grade, class_name, sida_class, photo
                FROM students
                WHERE teacher_code=? AND (status IS NULL OR status='' OR status='فعال')
                ORDER BY last_name, first_name, id
            ''', (teacher['code'],)).fetchall()
            lists.append({
                'teacher': dict(teacher),
                'students': [dict(s) for s in students],
            })
        teacher_options = [] if restricted else conn.execute('''
            SELECT code, first_name, last_name FROM teachers
            ORDER BY last_name, first_name, code
        ''').fetchall()
    selected_label = None
    if selected_code and teacher_rows:
        selected_label = f"{teacher_rows[0]['first_name'] or ''} {teacher_rows[0]['last_name'] or ''}".strip()
    return render_template(
        'list_for_folders.html', lists=lists,
        teacher_options=teacher_options, selected_code=selected_code,
        selected_label=selected_label, restricted=restricted,
        orientation=orientation,
        # تنظیمات ظاهری
        cols=cols, rows=rows, card_gap=card_gap, card_padding=card_padding,
        stu_font=stu_font, tea_font=tea_font, meta_font=meta_font, count_font=count_font,
        stu_name_size=stu_name_size, stu_grade_size=stu_grade_size,
        tea_weight=tea_weight, stu_weight=stu_weight, meta_weight=meta_weight, count_weight=count_weight,
        line_height=line_height, stu_spacing=stu_spacing,
        border_style=border_style, border_width=border_width, border_color=border_color,
        bg_card=bg_card, radius=radius, primary_color=primary_color, count_radius=count_radius,
        tea_border_color=tea_border_color, count_bg_color=count_bg_color,
        row_divider_style=row_divider_style, row_divider_color=row_divider_color, row_divider_width=row_divider_width,
        photo_width=photo_width, photo_height=photo_height, photo_shape=photo_shape,
        show_photo=show_photo, show_grade=show_grade, show_subject=show_subject, show_numbering=show_numbering,
        max_students=max_students, card_shadow=card_shadow,
        show_divider_below_teacher=show_divider_below_teacher,
         heading_align=heading_align, stu_name_align=stu_name_align, grade_align=grade_align,
         photo_border=photo_border, photo_border_color=photo_border_color, photo_radius=photo_radius,
         folder_layout=folder_layout,
    )


def list_for_folders_print():
    """Standalone print-optimized page — no base template, no JS, minimal CSS."""
    restricted = session.get('role') == 'teacher'
    requested_code = _text(request.args.get('teacher_code'), 80)
    scope = teacher_scope()
    selected_code = scope if restricted else requested_code

    def _int(param: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int(request.args.get(param, default))
            return max(lo, min(hi, v))
        except (TypeError, ValueError):
            return default

    def _str(param: str, default: str, choices: list[str]) -> str:
        v = request.args.get(param, default) or default
        return v if v in choices else default

    with get_db() as conn:
        folder_layout = load_report_layout(conn, 'folder_labels', session.get('user_id'))
    cols = folder_layout['grid']['columns']
    rows = folder_layout['grid']['rows']
    orientation = folder_layout['orientation']
    page_width_mm = (210 if orientation == 'portrait' else 297) - folder_layout['margin']['left'] - folder_layout['margin']['right']
    page_height_mm = (297 if orientation == 'portrait' else 210) - folder_layout['margin']['top'] - folder_layout['margin']['bottom']
    card_gap      = _str('card_gap',      '3mm', ['0.5mm','1mm','1.5mm','2mm','2.5mm','3mm'])
    card_padding  = _str('card_padding',  '1.5mm 1.8mm',
                         ['1mm 1.5mm','1.2mm 1.5mm','1.5mm 1.8mm','1.5mm 2mm','2mm 2.5mm','2mm 3mm'])
    tea_font      = _int('tea_font',      12, 7, 18)
    meta_font     = _int('meta_font',     7, 4, 10)
    count_font    = _int('count_font',    7, 4, 10)
    stu_font      = _int('stu_font',      8, 5, 14)
    stu_name_size = _int('stu_name_size', 9, 4, 10)
    stu_grade_size=_int('stu_grade_size', 7, 3, 8)
    tea_weight    = _str('tea_weight',    '900', ['400','500','600','700','800','900'])
    stu_weight    = _str('stu_weight',    '600', ['400','500','600','700','800'])
    meta_weight   = _str('meta_weight',   '400', ['400','500','600','700'])
    count_weight  = _str('count_weight',  '800', ['400','500','600','700','800','900'])
    line_height   = _str('line_height',   '1.4', ['1.2','1.3','1.4','1.5','1.6','1.8'])
    stu_spacing   = _str('stu_spacing',   '0.5mm', ['0mm','0.2mm','0.3mm','0.5mm','0.6mm','0.8mm'])
    border_style  = _str('border_style',  'solid', ['solid', 'dashed', 'dotted'])
    border_width  = _str('border_width',  '1.2',  ['0.8','1.0','1.2','1.5','2.0'])
    border_color  = _str('border_color',  '#333', ['#6b7280','#334155','#1e3a5f','#0f172a','#1e40af','#047857','#b91c1c','#7c3aed','#b45309','#dc2626','#2563eb','#16a34a','#475569','#94a3b8','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#84cc16','#f97316','#ec4899','#333'])
    bg_card       = _str('bg_card',       '#ffffff', ['#ffffff','#fafaf8','#f0f9ff','#f0fdf4','#fefce8','#faf5ff','#fff7ed','#f1f5f9','#eef2ff','#fef9c3','#fff1f2','#fffbeb'])
    radius        = _str('radius',        '1.2mm', ['0mm','1mm','1.2mm','2mm','3mm','4mm','5mm','6mm','8mm','10mm','12mm'])
    primary_color = _str('primary_color', '#1e3a5f',
                          ['#1e3a5f','#0b4f6c','#047857','#1e40af','#7c3aed','#b91c1c',
                           '#b45309','#dc2626','#2563eb','#16a34a','#475569','#0f172a',
                           '#6b7280','#92400e','#581c87','#991b1b','#1e3a8a','#065f46'])
    count_radius  = _str('count_radius',  '.8mm', ['0mm','.5mm','.8mm','1mm','1.5mm','2mm','3mm','999px'])
    tea_border_color = _str('tea_border_color', '#1e3a5f',
                             ['#1e3a5f','#0b4f6c','#047857','#1e40af','#7c3aed',
                              '#b91c1c','#b45309','#475569','#6b7280','#94a3b8',
                              '#0f172a','#334155','#000000','#333333','#666666','#999999',
                              '#2563eb','#16a34a','#dc2626','#f59e0b'])
    count_bg_color = _str('count_bg_color', '#1e3a5f',
                           ['#1e3a5f','#0b4f6c','#047857','#1e40af','#7c3aed',
                            '#b91c1c','#b45309','#2563eb','#16a34a','#475569',
                            '#0f172a','#334155','#000000','#333333','#666666','#999999',
                            '#dc2626','#f59e0b','#ec4899','#8b5cf6'])
    row_divider_style = _str('row_divider_style', 'dotted', ['none', 'dotted', 'dashed', 'solid'])
    row_divider_color = _str('row_divider_color', '#ccc',
                              ['#ccc','#94a3b8','#e2e8f0','#64748b','#475569',
                               '#334155','#1e3a5f','#f1f5f9','#f8fafc','#fff',
                               '#000000','#333333','#cbd5e1'])
    row_divider_width = _str('row_divider_width', '.3', ['0','.3','.5','.8','1.0','1.2'])
    photo_width  = _int('photo_width',  5, 4, 30)
    photo_height = _int('photo_height', 6, 4, 30)
    photo_shape  = _str('photo_shape',  'rounded', ['square', 'rounded', 'circle'])
    photo_border = _str('photo_border', 'yes', ['yes', 'no'])
    photo_border_color = _str('photo_border_color', '#aaa',
                                ['#aaa','#94a3b8','#e2e8f0','#64748b','#475569',
                                 '#334155','#1e3a5f','#fff','#0f172a','#000000','#333333'])
    photo_radius = _str('photo_radius', '.6mm', ['0mm','.4mm','.6mm','1mm','1.5mm','2mm','3mm'])
    show_photo   = _str('show_photo',   'yes', ['yes','no'])
    show_grade   = _str('show_grade',   'yes', ['yes','no'])
    show_subject = _str('show_subject', 'yes', ['yes','no'])
    show_numbering = _str('show_numbering', 'yes', ['yes','no'])
    max_students = _int('max_students', 8, 3, 20)
    show_divider_below_teacher = _str('show_divider_below_teacher', 'yes', ['yes','no'])
    heading_align = _str('heading_align', 'right', ['right', 'center', 'left'])
    stu_name_align = _str('stu_name_align', 'right', ['right', 'center', 'left'])
    grade_align  = _str('grade_align', 'left', ['right', 'center', 'left'])
    with get_db() as conn:
        teachers_query = '''
            SELECT t.id, t.code, t.first_name, t.last_name, t.subject,
                   COALESCE(t.class_name, '') AS class_name,
                   COUNT(s.id) AS student_count
            FROM teachers t
            LEFT JOIN students s ON s.teacher_code=t.code
                AND (s.status IS NULL OR s.status='' OR s.status='فعال')
        '''
        params = []
        if selected_code:
            teachers_query += ' WHERE t.code=? '
            params.append(selected_code)
        teachers_query += '''
            GROUP BY t.id, t.code, t.first_name, t.last_name, t.subject,
                     t.class_name
            ORDER BY t.last_name, t.first_name, t.code
        '''
        teacher_rows = conn.execute(teachers_query, params).fetchall()
        lists = []
        for teacher in teacher_rows:
            students = conn.execute('''
                SELECT first_name, last_name, code, grade, class_name, sida_class, photo
                FROM students
                WHERE teacher_code=? AND (status IS NULL OR status='' OR status='فعال')
                ORDER BY last_name, first_name, id
            ''', (teacher['code'],)).fetchall()
            lists.append({
                'teacher': dict(teacher),
                'students': [dict(s) for s in students],
            })
    per_page = cols * rows
    pages = [lists[i:i + per_page] for i in range(0, len(lists), per_page)] if lists else []
    return render_template(
        'list_for_folders_print.html', pages=pages, restricted=restricted,
        cols=cols, rows=rows, card_gap=card_gap, card_padding=card_padding,
        tea_font=tea_font, meta_font=meta_font, count_font=count_font, stu_font=stu_font,
        stu_name_size=stu_name_size, stu_grade_size=stu_grade_size,
        tea_weight=tea_weight, stu_weight=stu_weight, meta_weight=meta_weight, count_weight=count_weight,
        line_height=line_height, stu_spacing=stu_spacing,
        border_style=border_style, border_width=border_width, border_color=border_color,
        bg_card=bg_card, radius=radius, primary_color=primary_color, count_radius=count_radius,
        tea_border_color=tea_border_color, count_bg_color=count_bg_color,
        row_divider_style=row_divider_style, row_divider_color=row_divider_color, row_divider_width=row_divider_width,
        photo_width=photo_width, photo_height=photo_height, photo_shape=photo_shape,
        show_photo=show_photo, show_grade=show_grade, show_subject=show_subject, show_numbering=show_numbering,
        max_students=max_students,
        show_divider_below_teacher=show_divider_below_teacher,
         heading_align=heading_align, stu_name_align=stu_name_align, grade_align=grade_align,
         photo_border=photo_border, photo_border_color=photo_border_color, photo_radius=photo_radius,
         folder_layout=folder_layout, orientation=orientation,
         page_width_mm=page_width_mm, page_height_mm=page_height_mm,
    )


def print_wall_cards():
    """Print compact, wall-mountable ID cards (photo + main info)."""
    restricted = session.get('role') == 'teacher'
    ids_raw = _text(request.args.get('ids'), 5000)
    ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    if ids:
        scope = teacher_scope()
        with get_db() as conn:
            placeholders = ','.join('?' for _ in ids)
            query = f'''SELECT s.*, t.first_name AS teacher_first, t.last_name AS teacher_last
                        FROM students s LEFT JOIN teachers t ON s.teacher_code=t.code
                        WHERE s.id IN ({placeholders}) AND (s.status='فعال' OR s.status IS NULL)
                        AND (? IS NULL OR s.teacher_code=?) ORDER BY s.first_name,s.last_name,s.id'''
            students = conn.execute(query, ids + [scope, scope]).fetchall()
            wall_layout = load_report_layout(conn, 'wall_cards', session.get('user_id'))
        selected = {}
    else:
        query, params, selected = filtered_students_query(request.args)
        with get_db() as conn:
            students = conn.execute(query, params).fetchall()
            wall_layout = load_report_layout(conn, 'wall_cards', session.get('user_id'))
    student_ids = [row['id'] for row in students]
    driver_names = {}
    if student_ids:
        with get_db() as conn:
            placeholders = ','.join('?' for _ in student_ids)
            driver_rows = conn.execute(
                f'''SELECT s.id,d.driver_name
                    FROM students s LEFT JOIN service_driver_registry d
                    ON d.id=s.service_driver_id
                    WHERE s.id IN ({placeholders})''', student_ids
            ).fetchall()
            driver_names = {row['id']: row['driver_name'] for row in driver_rows}
    cards = []
    for row in students:
        teacher = f"{row['teacher_first'] or ''} {row['teacher_last'] or ''}".strip()
        cards.append({
            'first_name': row['first_name'],
            'full_name': f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or 'بدون نام',
            'code': row['code'],
            'grade': row['grade'],
            'class_name': row['class_name'],
            'sida_class': row['sida_class'],
            'gender': row['gender'],
            'photo': row['photo'],
            'teacher': teacher or None,
            'driver': driver_names.get(row['id']) or None,
        })
    per_page = wall_layout['grid']['columns'] * wall_layout['grid']['rows']
    pages = [cards[start:start + per_page] for start in range(0, len(cards), per_page)]
    return render_template(
        'print_wall_cards.html', cards=cards, pages=pages, count=len(cards),
        selected_filters=selected, restricted=restricted,
        wall_layout=wall_layout,
        autoprint=request.args.get('autoprint') == '1',
    )


def permanent_delete_student(id):
    # Permanent deletion is intentionally available from archived lists only.
    # Active records must first be moved to a documented status so an accidental
    # click cannot destroy a current student's file.
    with get_db() as conn:
        student = conn.execute(
            'SELECT id,code,first_name,last_name,photo,status FROM students WHERE id=?', (id,)
        ).fetchone()
    if not student:
        flash('دانش‌آموز پیدا نشد.', 'danger')
        return redirect(url_for('index'))
    if not student['status'] or student['status'] == 'فعال':
        flash('برای حذف دائمی، ابتدا دانش‌آموز را به یکی از بخش‌های بایگانی منتقل کنید.', 'warning')
        return redirect(url_for('index'))

    auto_backup()
    with get_db() as conn:
        code = student['code']
        table_names = {r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, column in (
            ('attendance_students', 'student_code'), ('attendance', 'student_code'),
            ('teacher_performance', 'student_code'), ('financial_help', 'student_code'),
            ('monthly_service', 'student_code'), ('discipline', 'target_code'),
        ):
            if table in table_names:
                conn.execute(f'DELETE FROM "{table}" WHERE "{column}"=?', (code,))
        cursor = conn.execute('DELETE FROM students WHERE id=? AND status<>"فعال"', (id,))
        conn.commit()
    if not cursor.rowcount:
        flash('پرونده دانش‌آموز حذف نشد یا قبلاً تغییر کرده است.', 'warning')
        return redirect(url_for('other_inactive'))
    _remove_uploaded_photo(student['photo'])
    audit(session.get('user_id'), 'permanent_delete_student', 'student', id, str(code))
    flash('پرونده دانش‌آموز و سوابق وابسته حذف شد؛ نسخه پشتیبان ساخته شد.', 'success')
    return redirect(url_for('other_inactive'))


def confirm_delete_student(id):
    """Show the confirmation page; the state-changing action is POST-only."""
    with get_db() as conn:
        query, params = _student_scope_query(id)
        student = conn.execute(query, params).fetchone()
    if not student:
        flash('دانش‌آموز پیدا نشد یا در محدوده دسترسی شما نیست.', 'danger')
        return redirect(url_for('index'))
    return render_template('confirm_delete.html', student=student)


def delete_student(id):
    """Archive a student after an explicit POST confirmation."""
    with get_db() as conn:
        query, params = _student_scope_query(id)
        student = conn.execute(query, params).fetchone()
        if not student:
            flash('دانش‌آموز پیدا نشد یا در محدوده دسترسی شما نیست.', 'danger')
            return redirect(url_for('index'))
        reason = _text(request.form.get('reason'), 40)
        status_map = {
            'فارغ‌التحصیل': 'فارغ‌التحصیل',
            'ترک تحصیل': 'ترک تحصیل',
            'سایر': 'سایر',
        }
        if reason not in status_map:
            flash('لطفاً دلیل تغییر وضعیت را انتخاب کنید.', 'danger')
            return render_template('confirm_delete.html', student=student), 400
        auto_backup()
        cursor = conn.execute('UPDATE students SET status=? WHERE id=?', (status_map[reason], id))
        conn.commit()
    if not cursor.rowcount:
        flash('تغییر وضعیت دانش‌آموز انجام نشد.', 'warning')
        return redirect(url_for('index'))
    audit(session.get('user_id'), 'archive_student', 'student', id, status_map[reason])
    flash(f'وضعیت دانش‌آموز به «{status_map[reason]}» تغییر یافت.', 'success')
    return redirect(url_for('index'))


def restore_student(id):
    with get_db() as conn:
        student = conn.execute('SELECT id,status FROM students WHERE id=?', (id,)).fetchone()
    if not student:
        flash('دانش‌آموز پیدا نشد.', 'warning')
        return redirect(url_for('other_inactive'))
    if student['status'] in (None, '', 'فعال'):
        flash('این پرونده در فهرست فعال قرار دارد.', 'info')
        return redirect(_safe_return_url(request.form.get('next'), url_for('other_inactive')))
    auto_backup()
    with get_db() as conn:
        cursor = conn.execute("UPDATE students SET status='فعال' WHERE id=? AND status<> 'فعال'", (id,))
        conn.commit()
    if cursor.rowcount:
        audit(session.get('user_id'), 'restore_student', 'student', id)
        flash('دانش‌آموز به فهرست فعال بازگردانده شد.', 'success')
    else:
        flash('بازگردانی انجام نشد؛ پرونده تغییر کرده است.', 'warning')
    return redirect(_safe_return_url(request.form.get('next'), url_for('other_inactive')))


def _inactive_students(status: str, title: str):
    with get_db() as conn:
        students = conn.execute('''
            SELECT s.*, t.first_name AS teacher_first, t.last_name AS teacher_last
            FROM students s LEFT JOIN teachers t ON s.teacher_code=t.code
            WHERE s.status=? ORDER BY s.id DESC
        ''', (status,)).fetchall()
    ages = {row['id']: calculate_jalali_age(row['birth_date']) for row in students}
    return render_template('inactive_students.html', students=students, ages=ages, title=title, status=status)


def graduates():
    return _inactive_students('فارغ‌التحصیل', '🎓 فارغ‌التحصیلان')


def dropouts():
    return _inactive_students('ترک تحصیل', '🚫 ترک‌تحصیلان')


def other_inactive():
    return _inactive_students('سایر', '🔸 سایر موارد')

def print_selected():
    ids_str = _text(request.form.get('ids'), 5000)
    ids = [int(x) for x in ids_str.split(',') if x.strip().isdigit()]
    if not ids:
        flash('هیچ دانش‌آموز معتبری انتخاب نشده است.', 'danger')
        return redirect(url_for('index'))
    scope = teacher_scope()
    restricted = session.get('role') == 'teacher'
    with get_db() as conn:
        placeholders = ','.join('?' for _ in ids)
        query = f'''SELECT s.*, t.first_name AS teacher_first, t.last_name AS teacher_last
                    FROM students s LEFT JOIN teachers t ON s.teacher_code=t.code
                    WHERE s.id IN ({placeholders}) AND (s.status='فعال' OR s.status IS NULL)
                    AND (? IS NULL OR s.teacher_code=?) ORDER BY s.id'''
        students = conn.execute(query, ids + [scope, scope]).fetchall()
        student_info_layout = load_report_layout(conn, 'student_info', session.get('user_id'))
        siblings_by_student = {} if restricted else {
            int(row['id']): _get_siblings(conn, int(row['id'])) for row in students
        }
        custom_by_student = {
            int(row['id']): fields_for_profile(conn, int(row['id']), include_teacher=not restricted)
            for row in students
        }
    print_rows = _build_print_rows(students, restricted, custom_by_student, siblings_by_student, student_info_layout)
    section_keys = [
        [section['key'] for section in row['profile_sections']]
        + (['grade_repeats'] if row['grade_repeat_rows'] else [])
        + (['siblings'] if row['siblings'] else [])
        for row in print_rows
    ]
    return render_template(
        'print_selected.html', students=students,
        print_rows=print_rows, print_section_keys=section_keys,
        count=len(students), selected_filters={}, restricted=restricted,
        student_info_layout=student_info_layout,
    )


def student_print_settings():
    raw = request.get_json(silent=True)
    if not isinstance(raw, dict) or not isinstance(raw.get('sections'), dict):
        return jsonify(error='تنظیمات نامعتبر است.'), 400
    if 'orientation' in raw and not isinstance(raw['orientation'], str):
        return jsonify(error='جهت کاغذ باید یک مقدار متنی معتبر باشد.'), 400
    with get_db() as conn:
        layout = load_report_layout(conn, 'student_info', session['user_id'])
        for key in ('orientation', 'font_size', 'hide_empty_fields', 'hide_empty_sections'):
            if key in raw:
                layout[key] = raw[key]
        allowed = {'identity', 'education', 'grade_repeats', 'other', 'custom'} if session.get('role') == 'teacher' else dict(REPORT_SECTIONS['student_info'])
        for key in allowed:
            if key in raw['sections'] and isinstance(raw['sections'][key], bool):
                layout['sections'][key] = raw['sections'][key]
        layout = save_report_layout(conn, 'student_info', session['user_id'], layout)
        conn.commit()
    return jsonify(layout=layout)


def register(app):
    app.add_url_rule('/student-print-settings', endpoint='student_print_settings',
                     view_func=student_print_settings, methods=['POST'])

    @app.context_processor
    def student_print_context():
        if request.endpoint not in {'index', 'student_profile', 'print_student', 'print_selected', 'print_filtered_students'}:
            return {}
        with get_db() as conn:
            layout = load_report_layout(conn, 'student_info', session.get('user_id'))
        sections = REPORT_SECTIONS['student_info']
        if session.get('role') == 'teacher':
            sections = [(key, label) for key, label in sections
                        if key in {'identity', 'education', 'grade_repeats', 'other', 'custom'}]
        return {'student_print_options': layout, 'student_print_sections': sections}

    app.add_url_rule('/', endpoint='index', view_func=index)
    app.add_url_rule('/student-view', endpoint='student_card_view', view_func=student_card_view,
                     methods=['POST'])
    app.add_url_rule('/v-dashboard', endpoint='vdashboard', view_func=vdashboard)
    app.add_url_rule('/upload_photo', endpoint='upload_photo', view_func=upload_photo, methods=['POST'])
    app.add_url_rule('/add', endpoint='add_student', view_func=add_student, methods=['GET', 'POST'])
    app.add_url_rule('/edit/<int:id>', endpoint='edit_student', view_func=edit_student, methods=['GET', 'POST'])
    app.add_url_rule('/search', endpoint='search', view_func=search)
    app.add_url_rule('/student/<int:id>', endpoint='student_profile', view_func=student_profile)
    app.add_url_rule('/print/<int:id>', endpoint='print_student', view_func=print_student)
    app.add_url_rule('/print_selected', endpoint='print_selected', view_func=print_selected, methods=['POST'])
    app.add_url_rule('/print_filtered_students', endpoint='print_filtered_students', view_func=print_filtered_students, methods=['GET'])
    app.add_url_rule('/teacher_student_lists', endpoint='teacher_student_lists', view_func=teacher_student_lists, methods=['GET'])
    app.add_url_rule('/list_for_folders', endpoint='list_for_folders', view_func=list_for_folders, methods=['GET'])
    app.add_url_rule('/list_for_folders/print', endpoint='list_for_folders_print', view_func=list_for_folders_print, methods=['GET'])
    app.add_url_rule('/print_wall_cards', endpoint='print_wall_cards', view_func=print_wall_cards, methods=['GET'])
    app.add_url_rule('/delete_student/<int:id>/confirm', endpoint='confirm_delete_student', view_func=confirm_delete_student, methods=['GET'])
    app.add_url_rule('/delete_student/<int:id>', endpoint='delete_student', view_func=delete_student, methods=['POST'])
    app.add_url_rule('/permanent_delete_student/<int:id>', endpoint='permanent_delete_student', view_func=permanent_delete_student, methods=['POST'])
    app.add_url_rule('/restore_student/<int:id>', endpoint='restore_student', view_func=restore_student, methods=['POST'])
    app.add_url_rule('/graduates', endpoint='graduates', view_func=graduates)
    app.add_url_rule('/dropouts', endpoint='dropouts', view_func=dropouts)
    app.add_url_rule('/other_inactive', endpoint='other_inactive', view_func=other_inactive)
