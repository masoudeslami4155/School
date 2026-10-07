#!/usr/bin/env python
"""Exercise every print-studio screen and its real print preview in isolation."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = Path(tempfile.mkdtemp(prefix='print-studio-route-test-'))
_credentials = ROOT / 'initial_credentials.txt'
_credentials_existed = _credentials.exists()
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'print-studio-route-test-secret-key',
})

from school_app import app  # noqa: E402
from school_app.database import get_db  # noqa: E402
from school_app.print_layouts import (  # noqa: E402
    DOCUMENTS as SERVICE_DOCUMENTS,
    default_layout as default_service_layout,
)
from school_app.report_print_layouts import (  # noqa: E402
    REPORT_DOCUMENTS,
    default_layout as default_report_layout,
)
from school_app.student_certificate_layout import (  # noqa: E402
    default_layout as default_certificate_layout,
    load_layout as load_certificate_layout,
)
from school_app.ai_letter_layout import (  # noqa: E402
    default_layout as default_letter_layout,
    load_layout as load_letter_layout,
)
from school_app.routes.report_print_layouts import _preview_url  # noqa: E402
from school_app.student_dashboard import STUDENT_FILTER_REFERENCE  # noqa: E402


def login(client, role: str, personnel_number: str = 'admin') -> None:
    with client.session_transaction() as session:
        session.update({
            'user_id': 700,
            'role': role,
            'personnel_number': personnel_number,
            'full_name': 'کاربر آزمایشی',
            '_csrf_token': 'studio-test-token',
        })


def main() -> int:
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    with app.app_context():
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO students(first_name,last_name,code,status,teacher_code,grade,
                                         class_name,sida_class,gender)
                   VALUES('آزمون','کارت','ST-TEST','فعال','STALE-TEACHER',
                          'پایه آزمایش','کلاس آزمایش','سیدا آزمایش','نمونه')'''
            )
            active_id = conn.execute('SELECT id FROM students WHERE code=?', ('ST-TEST',)).fetchone()['id']
            conn.execute(
                "INSERT INTO attendance_students(student_code,date,status) VALUES('ST-TEST','1405/07/01','حاضر')"
            )
            conn.execute(
                "INSERT INTO students(first_name,last_name,code,status,teacher_code) VALUES('بایگانی','آزمون','ST-OLD','فارغ‌التحصیل','STALE-TEACHER')"
            )

    admin = app.test_client()
    login(admin, 'admin')

    documents = {**SERVICE_DOCUMENTS, **REPORT_DOCUMENTS, 'student_certificate': {}, 'ai_letter': {}}
    for document in documents:
        response = admin.get(f'/report-print-layouts?document={document}')
        assert response.status_code == 200, (document, response.status_code)
        assert f'data-studio-document="{document}"'.encode() in response.data
        if document in REPORT_DOCUMENTS:
            assert b'data-report-element="footer"' in response.data, document
        elif document in SERVICE_DOCUMENTS:
            assert b'data-report-element="footer"' not in response.data, document
        if document == 'student_certificate':
            assert b'id="certificateOrientation"' in response.data
            assert b'data-cert-element="title"' in response.data
        if document == 'ai_letter':
            assert b'id="letterOrientation"' in response.data
            assert b'data-letter-element="header"' in response.data
        default = (
            default_service_layout(document) if document in SERVICE_DOCUMENTS
            else default_certificate_layout() if document == 'student_certificate'
            else default_letter_layout() if document == 'ai_letter'
            else default_report_layout(document)
        )
        for action in ('save', 'reset'):
            response = admin.post(f'/report-print-layouts?document={document}', data={
                '_csrf_token': 'studio-test-token',
                'document': document,
                'action': action,
                'layout_json': json.dumps(default),
            })
            assert response.status_code == 302, (document, action, response.status_code)

    certificate_layout = default_certificate_layout()
    certificate_layout['orientation'] = 'landscape'
    certificate_layout['elements']['title'].update({'x': 99, 'w': 90})
    saved_certificate = admin.post('/report-print-layouts?document=student_certificate', data={
        '_csrf_token': 'studio-test-token',
        'document': 'student_certificate',
        'action': 'save',
        'layout_json': json.dumps(certificate_layout),
    })
    assert saved_certificate.status_code == 302
    with app.app_context(), get_db() as conn:
        stored_certificate = load_certificate_layout(conn, 700)
    assert stored_certificate['orientation'] == 'landscape'
    assert stored_certificate['elements']['title']['x'] == 99
    assert stored_certificate['elements']['title']['w'] == 1
    with app.app_context(), get_db() as conn:
        assert load_certificate_layout(conn, 701)['orientation'] == 'portrait'
    reset_certificate = admin.post('/report-print-layouts?document=student_certificate', data={
        '_csrf_token': 'studio-test-token',
        'document': 'student_certificate',
        'action': 'reset',
    })
    assert reset_certificate.status_code == 302
    with app.app_context(), get_db() as conn:
        assert load_certificate_layout(conn, 700)['orientation'] == 'portrait'

    letter_layout = default_letter_layout()
    letter_layout['orientation'] = 'landscape'
    letter_layout['margin']['top'] = 99
    letter_layout['font_size'] = 3
    letter_layout['elements']['body'].update({'x': 60, 'w': 80})
    saved_letter = admin.post('/report-print-layouts?document=ai_letter', data={
        '_csrf_token': 'studio-test-token',
        'document': 'ai_letter',
        'action': 'save',
        'layout_json': json.dumps(letter_layout),
    })
    assert saved_letter.status_code == 302
    with app.app_context(), get_db() as conn:
        stored_letter = load_letter_layout(conn, 700)
    assert stored_letter['orientation'] == 'landscape'
    assert stored_letter['margin']['top'] == 30
    assert stored_letter['font_size'] == 8
    assert stored_letter['elements']['body']['x'] == 60
    assert stored_letter['elements']['body']['w'] == 40
    with app.app_context(), get_db() as conn:
        assert load_letter_layout(conn, 701)['orientation'] == 'portrait'
    reset_letter = admin.post('/report-print-layouts?document=ai_letter', data={
        '_csrf_token': 'studio-test-token',
        'document': 'ai_letter',
        'action': 'reset',
    })
    assert reset_letter.status_code == 302
    with app.app_context(), get_db() as conn:
        assert load_letter_layout(conn, 700)['orientation'] == 'portrait'

    with app.test_request_context('/report-print-layouts'):
        preview_urls = {key: _preview_url(key) for key in documents}
    for document, preview_url in preview_urls.items():
        response = admin.get(preview_url, follow_redirects=True)
        assert response.status_code == 200, (document, preview_url, response.status_code)

    attendance_layout = default_report_layout('attendance_students')
    attendance_layout.update({'orientation': 'portrait', 'show_footer': False})
    attendance_layout['sections']['summary'] = False
    attendance_layout['elements']['hero'].update({'x': 7, 'y': 4, 'sx': 1.2, 'sy': 1})
    response = admin.post('/report-print-layouts?document=attendance_students', data={
        '_csrf_token': 'studio-test-token',
        'document': 'attendance_students',
        'action': 'save',
        'layout_json': json.dumps(attendance_layout),
    })
    assert response.status_code == 302
    printed_attendance = admin.get('/reports/attendance_report?print=landscape&autoprint=1&print_all=1')
    attendance_style = printed_attendance.data.decode('utf-8').split('@media print', 1)[1].split('</style>', 1)[0]
    assert b'@page { size: A4 portrait;' in printed_attendance.data
    assert 'translate(7.0mm,4.0mm)' in attendance_style, attendance_style
    assert 'scale(1.2,1.0)' in attendance_style, attendance_style
    assert b'class="ar-stats print-layout-hidden"' in printed_attendance.data
    assert b'class="ar-print-footer print-layout-hidden"' in printed_attendance.data, (
        printed_attendance.data.decode('utf-8').split('ar-print-footer', 1)[1][:180]
    )

    teacher_layout = default_report_layout('attendance_teachers')
    teacher_layout.update({'orientation': 'portrait', 'show_header': False})
    teacher_layout['elements']['hero'].update({'x': -3, 'y': 5, 'sx': 1, 'sy': 1.1})
    response = admin.post('/report-print-layouts?document=attendance_teachers', data={
        '_csrf_token': 'studio-test-token',
        'document': 'attendance_teachers',
        'action': 'save',
        'layout_json': json.dumps(teacher_layout),
    })
    assert response.status_code == 302
    printed_teachers = admin.get('/reports/teacher_attendance?print=landscape&autoprint=1')
    assert b'@page { size: A4 portrait;' in printed_teachers.data
    assert b'translate(-3.0mm,5.0mm) scale(1.0,1.1)' in printed_teachers.data
    assert b'class="print-header print-layout-hidden"' in printed_teachers.data

    statistics_layout = default_report_layout('school_statistics')
    statistics_layout['orientation'] = 'landscape'
    statistics_layout['sections']['risk'] = False
    statistics_layout['show_footer'] = False
    statistics_layout['elements']['hero'].update({'x': 3, 'y': 2, 'sx': 1.1, 'sy': 1})
    response = admin.post('/report-print-layouts?document=school_statistics', data={
        '_csrf_token': 'studio-test-token',
        'document': 'school_statistics',
        'action': 'save',
        'layout_json': json.dumps(statistics_layout),
    })
    assert response.status_code == 302
    printed_statistics = admin.get('/statistics')
    assert b'@page{size:A4 landscape' in printed_statistics.data
    assert b'translate(3.0mm,2.0mm) scale(1.1,1.0)' in printed_statistics.data
    assert b'data-hide-risk="1"' in printed_statistics.data
    assert b'class="stats-print-footer print-layout-hidden"' in printed_statistics.data

    student_info_layout = default_report_layout('student_info')
    student_info_layout['orientation'] = 'landscape'
    student_info_layout['sections']['family'] = False
    student_info_layout['elements']['hero'].update({'x': 4, 'y': 2, 'sx': 1, 'sy': 1.1})
    response = admin.post('/report-print-layouts?document=student_info', data={
        '_csrf_token': 'studio-test-token',
        'document': 'student_info',
        'action': 'save',
        'layout_json': json.dumps(student_info_layout),
    })
    assert response.status_code == 302

    guide = admin.get(preview_urls['student_filters'])
    for item in STUDENT_FILTER_REFERENCE:
        assert item['key'].encode() in guide.data

    wall_url = preview_urls['wall_cards'] + '&q=آزمون'
    wall = admin.get(wall_url)
    assert wall.status_code == 200
    assert 'آزمون کارت'.encode() in wall.data
    assert 'بایگانی آزمون'.encode() not in wall.data

    dashboard = admin.get('/?teacher_code=__empty__')
    filtered_print = admin.get('/print_filtered_students?teacher_code=__empty__')
    assert 'آزمون کارت'.encode() in dashboard.data
    assert 'آزمون کارت'.encode() in filtered_print.data
    assert b'@page{size:A4 landscape' in filtered_print.data
    assert b'translate(4.0mm,2.0mm) scale(1.0,1.1)' in filtered_print.data
    assert b'data-report-element="family"' not in filtered_print.data

    layout = {
        'orientation': 'portrait',
        'margin': {'top': 4, 'right': 4, 'bottom': 4, 'left': 4},
        'grid': {'columns': 2, 'rows': 1, 'gap_x': 2, 'gap_y': 1},
        'card': {
            'height': 43, 'photo_size': 0, 'font_size': 5.5, 'name_font_size': 7,
            'show_photo': False, 'show_school': True, 'show_year': True,
            'show_driver': False, 'show_grade': True, 'show_class_name': True,
            'show_sida_class': True, 'show_gender': False, 'show_teacher': True,
        },
    }
    response = admin.post('/report-print-layouts?document=wall_cards', data={
        '_csrf_token': 'studio-test-token',
        'document': 'wall_cards',
        'layout_json': json.dumps(layout),
        'q': 'آزمون',
        'ids': str(active_id),
    })
    assert response.status_code == 302
    query = parse_qs(urlparse(response.location).query)
    assert query.get('q') == ['آزمون'] and query.get('ids') == [str(active_id)]
    printed_wall = admin.get(f'/print_wall_cards?ids={active_id}')
    assert b'grid-template-columns:repeat(2' in printed_wall.data
    assert 'جنسیت'.encode() not in printed_wall.data

    teacher = app.test_client()
    login(teacher, 'teacher', 'TEACHER-TEST')
    assert teacher.get('/report-print-layouts?document=wall_cards').status_code == 200
    assert teacher.get('/report-print-layouts?document=service_receipt').status_code == 403
    assert teacher.get('/report-print-layouts?document=student_certificate').status_code == 403
    assert teacher.get('/report-print-layouts?document=ai_letter').status_code == 403
    assert teacher.get('/ai-letter-preview').status_code == 403
    assert teacher.get('/print-student-filters').status_code == 200
    assert teacher.get(f'/print_wall_cards?ids={active_id}').status_code == 200

    if not _credentials_existed and _credentials.exists():
        _credentials.unlink()
    shutil.rmtree(_tmp, ignore_errors=True)
    print(f'print studio routes: {len(documents)} editors and previews, certificate layout, filter guide, card layout, filters and role checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
