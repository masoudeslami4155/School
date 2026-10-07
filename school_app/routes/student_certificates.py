"""Manual and student-record based enrollment certificates."""

from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from pathlib import Path

import qrcode
from qrcode.image.svg import SvgPathImage
from flask import abort, current_app, render_template, request, session, url_for

from ..database import get_db
from ..dates import get_today_jalali, today_string
from ..student_certificate_layout import load_layout as load_certificate_layout


_FIELDS = {
    'full_name': ('نام و نام خانوادگی', 120),
    'father_name': ('نام پدر', 100),
    'student_code': ('کد دانش‌آموزی', 50),
    'national_id': ('شماره شناسنامه / کد ملی', 30),
    'birth_date': ('تاریخ تولد', 20),
    'grade': ('پایه', 80),
    'class_name': ('کلاس مدرسه', 80),
    'academic_year': ('سال تحصیلی', 20),
    'certificate_number': ('شماره گواهی', 30),
    'issue_date': ('تاریخ تقاضا', 20),
    'school_short_name': ('نام مدرسه روی گواهی', 100),
    'school_code': ('کد مدرسه', 30),
    'education_period': ('دوره تحصیلی', 100),
    'study_program': ('رشته', 160),
    'director_name': ('نام مدیر', 100),
    'purpose': ('ارائه به', 160),
}


def _academic_year() -> str:
    year = get_today_jalali()[0]
    return f'{year}-{year + 1}'


def _certificate_defaults() -> dict[str, str]:
    config = current_app.config
    return {
        'academic_year': _academic_year(),
        'certificate_number': '',
        'issue_date': today_string(),
        'school_short_name': config.get('CERTIFICATE_SCHOOL_NAME', ''),
        'school_code': config.get('CERTIFICATE_SCHOOL_CODE', ''),
        'education_period': config.get('CERTIFICATE_EDUCATION_PERIOD', ''),
        'study_program': config.get('CERTIFICATE_STUDY_PROGRAM', ''),
        'director_name': config.get('CERTIFICATE_DIRECTOR', ''),
        'purpose': 'بهزیستی',
    }


def _clean_values(source, fallback: dict[str, str] | None = None) -> dict[str, str]:
    fallback = fallback or _certificate_defaults()
    return {
        key: str((source.get(key) if key in source else fallback.get(key)) or '').strip()[:limit]
        for key, (_label, limit) in _FIELDS.items()
    }


def _student_values(student) -> dict[str, str]:
    name = f"{student['first_name'] or ''} {student['last_name'] or ''}".strip()
    return {
        **_certificate_defaults(),
        'full_name': name,
        'father_name': student['father_name'] or '',
        'student_code': student['code'] or '',
        # The data model has no separate student national-ID field. Per the
        # requested school rule, one editable value fills both printed labels.
        'national_id': student['student_id_serial'] or '',
        'birth_date': student['birth_date'] or '',
        'grade': student['grade'] or '',
        'class_name': student['class_name'] or '',
    }


def _student_photo_url(filename: str | None) -> str:
    if not filename or Path(filename).name != filename or '\\' in filename:
        return ''
    photo_path = Path(current_app.static_folder) / 'uploads' / filename
    if not photo_path.is_file():
        return ''
    return url_for('static', filename=f'uploads/{filename}')


def _uploaded_photo_data_uri(upload) -> str:
    if not upload or not upload.filename:
        return ''
    content = upload.stream.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError('حجم عکس باید حداکثر ۲ مگابایت باشد.')
    signatures = {
        'image/jpeg': content.startswith(b'\xff\xd8\xff'),
        'image/png': content.startswith(b'\x89PNG\r\n\x1a\n'),
    }
    if not signatures.get(upload.mimetype, False):
        raise ValueError('برای عکس فقط فایل JPG یا PNG انتخاب کنید.')
    encoded = base64.b64encode(content).decode('ascii')
    return f'data:{upload.mimetype};base64,{encoded}'


def _grade_line(values: dict[str, str]) -> str:
    grade = re.sub(r'^\s*پایه\s*[:：]?\s*', '', values['grade']).strip()
    class_name = re.sub(r'^\s*کلاس\s*[:：]?\s*', '', values['class_name']).strip()
    parts = [grade, class_name]
    if 'استثنایی' in values['education_period'] and not any('استثنایی' in part for part in parts):
        parts.append('استثنایی')
    return ' '.join(part for part in parts if part)


def _students_for_picker(conn):
    return conn.execute(
        """SELECT id, first_name, last_name, code FROM students
           WHERE status='فعال' OR status IS NULL
           ORDER BY first_name COLLATE NOCASE, last_name COLLATE NOCASE, id"""
    ).fetchall()


def _qr_data_uri(values: dict[str, str]) -> str:
    payload = json.dumps({
        'type': 'گواهی اشتغال به تحصیل',
        'name': values['full_name'],
        'student_code': values['student_code'],
        'grade': values['grade'],
        'class_name': values['class_name'],
        'academic_year': values['academic_year'],
    }, ensure_ascii=False, separators=(',', ':'))
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    code.add_data(payload)
    code.make(fit=True)
    svg = code.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    svg.save(output)
    encoded = base64.b64encode(output.getvalue()).decode('ascii')
    return f'data:image/svg+xml;base64,{encoded}'


def student_certificate():
    student_id = (request.args.get('student_id') or request.form.get('student_id') or '').strip()
    source = (request.form.get('source') or ('student' if student_id else 'manual')).strip()

    with get_db() as conn:
        students = _students_for_picker(conn)
        layout = load_certificate_layout(conn, session.get('user_id'))
        student = None
        if student_id:
            if not student_id.isdigit():
                abort(404)
            student = conn.execute(
                """SELECT id, first_name, last_name, father_name, code, student_id_serial,
                          birth_date, grade, class_name, photo FROM students
                   WHERE id=? AND (status='فعال' OR status IS NULL)""",
                (int(student_id),),
            ).fetchone()
            if not student:
                abort(404)

        if request.method == 'POST':
            fallback = _student_values(student) if student and source == 'student' else _certificate_defaults()
            values = _clean_values(request.form, fallback)
            if not values['full_name'] or not values['grade']:
                return render_template(
                    'student_certificate.html',
                    students=students,
                    selected_student_id=student_id,
                    source=source,
                    values=values,
                    error='نام دانش‌آموز و پایه برای صدور گواهی لازم است.',
                ), 400
            try:
                photo_url = _uploaded_photo_data_uri(request.files.get('photo'))
            except ValueError as exc:
                return render_template(
                    'student_certificate.html',
                    students=students,
                    selected_student_id=student_id,
                    source=source,
                    values=values,
                    error=str(exc),
                ), 400
            if not photo_url:
                photo_url = _student_photo_url(student['photo'] if student else '')
            return render_template(
                'print_student_certificate.html',
                values=values,
                layout=layout,
                qr_data_uri=_qr_data_uri(values),
                photo_url=photo_url,
                grade_line=_grade_line(values),
                auto_print=True,
                studio_mode=False,
            )

        values = _student_values(student) if student else {
            'full_name': '',
            'father_name': '',
            'student_code': '',
            'national_id': '',
            'birth_date': '',
            'grade': '',
            'class_name': '',
            **_certificate_defaults(),
        }

    return render_template(
        'student_certificate.html',
        students=students,
        selected_student_id=student_id,
        source=source,
        values=values,
        error=None,
    )


def register(app):
    app.add_url_rule(
        '/student-certificate',
        endpoint='student_certificate',
        view_func=student_certificate,
        methods=['GET', 'POST'],
    )
