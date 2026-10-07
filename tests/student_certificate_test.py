#!/usr/bin/env python
"""Check manual/autofilled enrollment certificates using a disposable database."""

from __future__ import annotations

import base64
from io import BytesIO
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = Path(tempfile.mkdtemp(prefix='student-certificate-test-'))
_credentials = ROOT / 'initial_credentials.txt'
_credentials_existed = _credentials.exists()
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'student-certificate-test-secret-key',
})

from school_app import app  # noqa: E402
from school_app.database import get_db  # noqa: E402
from school_app.student_certificate_layout import (  # noqa: E402
    default_layout as default_certificate_layout,
    save_layout as save_certificate_layout,
)


def login(client, role: str) -> None:
    with client.session_transaction() as session:
        session.update({
            'user_id': 700,
            'role': role,
            'personnel_number': 'manager',
            'full_name': 'مدیر آزمایشی',
            '_csrf_token': 'certificate-test-token',
        })


def main() -> int:
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    with app.app_context():
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO students(first_name,last_name,code,status,father_name,
                                         student_id_serial,student_id_serial_letter,
                                         birth_date,grade,class_name,is_behzisti_member)
                   VALUES('نمونه','دانش‌آموز','ST-CERT','فعال','پدر نمونه',
                          '1234567890','الف','1390/01/02','پایه سوم','کلاس ۲',1)'''
            )
            student_id = conn.execute(
                'SELECT id FROM students WHERE code=?', ('ST-CERT',)
            ).fetchone()['id']
            conn.execute(
                "INSERT INTO students(first_name,last_name,code,status,grade) VALUES('بایگانی','آزمون','ST-OLD','فارغ‌التحصیل','پایه اول')"
            )

    manager = app.test_client()
    login(manager, 'manager')
    hub = manager.get('/features')
    assert hub.status_code == 200
    assert 'گواهی اشتغال به تحصیل'.encode() in hub.data
    profile = manager.get(f'/student/{student_id}')
    assert profile.status_code == 200
    assert f'/student-certificate?student_id={student_id}'.encode() in profile.data
    dashboard = manager.get('/')
    assert dashboard.status_code == 200
    assert f'/student-certificate?student_id={student_id}'.encode() in dashboard.data
    assert 'صدور گواهی اشتغال به تحصیل'.encode() in dashboard.data
    form = manager.get(f'/student-certificate?student_id={student_id}')
    assert form.status_code == 200
    assert 'name="full_name" value="نمونه دانش‌آموز"'.encode() in form.data
    assert 'value="1234567890"'.encode() in form.data
    assert 'ST-OLD'.encode() not in form.data

    automatic = manager.post('/student-certificate', data={
        '_csrf_token': 'certificate-test-token',
        'source': 'student',
        'student_id': str(student_id),
    })
    assert automatic.status_code == 200
    assert 'نمونه دانش‌آموز'.encode() in automatic.data
    assert 'پدر نمونه'.encode() in automatic.data
    assert automatic.data.count('۱۲۳۴۵۶۷۸۹۰'.encode()) >= 2

    manual = manager.post('/student-certificate', data={
        '_csrf_token': 'certificate-test-token',
        'source': 'manual',
        'student_id': '',
        'full_name': 'ورودی دستی',
        'father_name': 'پدر دستی',
        'student_code': 'MAN-1',
        'national_id': '1112223334',
        'birth_date': '۱۳۹۵/۰۲/۱۱',
        'grade': 'پایه چهارم',
        'class_name': 'کلاس ۱',
        'academic_year': '۱۴۰۵-۱۴۰۶',
        'certificate_number': '593648',
        'issue_date': '۱۴۰۵/۰۷/۱۱',
        'school_short_name': 'حمید',
        'school_code': '55614406',
        'education_period': 'ابتدایی استثنایی',
        'study_program': 'آموزش ابتدایی',
        'director_name': 'مدیر نمونه',
        'purpose': 'بهزیستی',
        'photo': (BytesIO(base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
        )), 'student.png', 'image/png'),
    }, content_type='multipart/form-data')
    assert manual.status_code == 200
    assert 'ورودی دستی'.encode() in manual.data
    assert manual.data.count('۱۱۱۲۲۲۳۳۳۴'.encode()) >= 2
    assert 'جمهوری اسلامی ایران'.encode() in manual.data
    assert 'تاریخ تولد'.encode() in manual.data
    assert '۱۴۰۵/۰۷/۱۱'.encode() in manual.data
    assert 'بهزیستی'.encode() in manual.data
    assert 'چهارم ۱ استثنایی'.encode() in manual.data
    assert 'size:A4 portrait'.encode() in manual.data
    assert b'data:image/png;base64,' in manual.data
    assert b'data-qr-position="right"' in manual.data
    match = re.search(rb'data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)', manual.data)
    assert match, 'inline QR image was not rendered'
    assert b'<svg' in base64.b64decode(match.group(1))

    custom_layout = default_certificate_layout()
    custom_layout['orientation'] = 'landscape'
    custom_layout['font_scale'] = 1.25
    custom_layout['frame_margin'] = 10
    custom_layout['border_width'] = 0.7
    custom_layout['elements']['title']['x'] = 12.5
    with app.app_context(), get_db() as conn:
        save_certificate_layout(conn, 700, custom_layout)
    landscape = manager.post('/student-certificate', data={
        '_csrf_token': 'certificate-test-token',
        'source': 'manual',
        'full_name': 'ورودی دوم',
        'grade': 'پایه پنجم',
    })
    assert landscape.status_code == 200
    assert b'size:A4 landscape' in landscape.data
    assert b'--frame-margin:10.0mm' in landscape.data
    assert b'* 1.25)' in landscape.data
    assert b'left:12.5%;top:11.0%' in landscape.data

    assert manager.get('/student-certificate?student_id=999999').status_code == 404
    teacher = app.test_client()
    login(teacher, 'teacher')
    assert teacher.get('/student-certificate').status_code == 403

    if not _credentials_existed and _credentials.exists():
        _credentials.unlink()
    shutil.rmtree(_tmp, ignore_errors=True)
    print('student certificate: auto-fill, A4 layout fields, temporary photo, shared ID, QR and role scope passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
