"""Isolated regression and optional --browser / --serve synthetic preview."""
import sys
import os
from pathlib import Path
import print_studio_routes_test as fixture
from school_app.database import get_db
from school_app.report_print_layouts import load_layout

app = fixture.app
app.config.update(TESTING=True)
with app.app_context(), get_db() as conn:
    for code, teacher, status in [('PRINT-A', 'T-A', 'فعال'), ('PRINT-B', 'T-B', 'فعال'), ('PRINT-OLD', 'T-A', 'فارغ‌التحصیل')]:
        conn.execute('INSERT INTO students(first_name,last_name,code,teacher_code,status,father_name,address) VALUES(?,?,?,?,?,?,?)',
                     ('دانش‌آموز', 'آزمایشی', code, teacher, status, 'PRIVATE-FATHER', 'نشانی نمونه ' * 25))
    student_id = conn.execute("SELECT id FROM students WHERE code='PRINT-A'").fetchone()['id']
# Development-only synthetic fixture session; never registered in production.
@app.route('/fixture-login')
def fixture_login():
    from flask import session, redirect
    session.update(user_id=700, role='admin', personnel_number='admin', full_name='کاربر آزمایشی', _csrf_token='studio-test-token')
    return redirect(f'/print/{student_id}')

from school_app.security import AUTH_EXEMPT_ENDPOINTS
AUTH_EXEMPT_ENDPOINTS.add('fixture_login')
admin = app.test_client()
fixture.login(admin, 'admin')
url = f'/print/{student_id}'
payload = {'orientation': 'landscape', 'font_size': 11.25, 'sections': {'family': False, 'identity': False, 'custom': False}}
assert admin.post('/student-print-settings', json=payload).status_code == 400
response = admin.post('/student-print-settings', json=payload, headers={'X-CSRF-Token': 'studio-test-token'})
assert response.status_code == 200
assert response.json['layout']['sections']['identity'] is True
assert response.json['layout']['font_size'] == 11.25
assert admin.get(url).status_code == 200
assert 'hidden' in admin.get(url).text.split('data-print-section-key="family"', 1)[1].split('>', 1)[0]
with app.app_context(), get_db() as conn:
    assert load_layout(conn, 'student_info', 701)['orientation'] == 'portrait'
    assert load_layout(conn, 'student_info', 700)['orientation'] == 'landscape'
assert admin.post('/student-print-settings', json=[], headers={'X-CSRF-Token': 'studio-test-token'}).status_code == 400
assert admin.post('/student-print-settings', json={'font_size': 500, 'orientation': 'bad', 'sections': {}}, headers={'X-CSRF-Token': 'studio-test-token'}).json['layout']['font_size'] == 18
admin.post('/student-print-settings', json=payload, headers={'X-CSRF-Token': 'studio-test-token'})
for path in ('/', f'/student/{student_id}', url, '/print_filtered_students'):
    assert b'data-student-print-controls' in admin.get(path).data
assert b'PRINT-OLD' not in admin.get('/print_filtered_students').data
assert b'PRINT-A' in admin.post('/print_selected', data={'ids': str(student_id), '_csrf_token': 'studio-test-token'}).data
teacher = app.test_client()
fixture.login(teacher, 'teacher', 'T-A')
with teacher.session_transaction() as session:
    session['user_id'] = 701
for path in (url, '/print_filtered_students'):
    html = teacher.get(path).data
    assert b'PRIVATE-FATHER' not in html
    assert b'PRINT-B' not in html
    assert b'data-print-section="family"' not in html
from school_app.report_print_layouts import default_layout, sanitize_layout
from school_app.routes.students import _profile_value
from flask import render_template
assert sanitize_layout('student_info', {'hide_empty_fields': 'invalid'})['hide_empty_fields'] is False
options = default_layout('student_info')
options.update(hide_empty_fields=True, hide_empty_sections=True)
with app.test_request_context('/'):
    rendered = render_template('partials/student_print_record.html', student={},
        profile_sections=[{'key': 'custom', 'title': 'اطلاعات', 'items': [
            {'label': 'zero', 'value': _profile_value('', 0)},
            {'label': 'negative', 'value': 'خیر'},
            {'label': 'empty', 'value': _profile_value('', '   ')},
        ]}], student_info_layout=options, grade_repeat_rows=[], siblings=[])
assert rendered.count('data-print-empty="false"') == 3  # section + zero + خیر
assert rendered.count('data-print-empty="true" hidden') == 1
saved = admin.post('/student-print-settings', json={**payload, 'hide_empty_fields': True,
    'hide_empty_sections': True}, headers={'X-CSRF-Token': 'studio-test-token'})
assert saved.json['layout']['hide_empty_fields'] is True
assert saved.json['layout']['hide_empty_sections'] is True
assert 'data-print-empty="true" hidden' in admin.get(url).text
with app.app_context(), get_db() as conn:
    assert load_layout(conn, 'student_info', 701)['hide_empty_fields'] is False
admin.post('/student-print-settings', json={**payload, 'hide_empty_fields': False,
    'hide_empty_sections': False}, headers={'X-CSRF-Token': 'studio-test-token'})
print('PASS: settings, validation, CSRF, per-user isolation, teacher privacy, single/group routes, empty fields and zero values')

if '--browser' in sys.argv or '--serve' in sys.argv:
    from threading import Thread
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 5074 if '--serve' in sys.argv else 0, app, threaded=True)
    base = f'http://127.0.0.1:{server.server_port}'
    if '--serve' in sys.argv:
        print(f'PREVIEW {base}/fixture-login PID {os.getpid()}', flush=True)
        server.serve_forever()
    else:
        from playwright.sync_api import sync_playwright
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/fixture-login')
                assert page.locator('.section-title').first.evaluate('e=>getComputedStyle(e).color') == 'rgb(0, 0, 0)'
                page.evaluate('window.print = () => { window.printRequested = true; }')
                page.locator('[data-print-now]').click()
                page.wait_for_function('window.printRequested === true')
                page.locator('[data-print-section="family"]').check()
                assert page.locator('[data-print-section-key="family"]').is_visible()
                empty_fields = page.locator('.profile-detail[data-print-empty="true"]')
                assert empty_fields.count() > 0
                page.locator('[data-print-empty-option="hide_empty_fields"]').check()
                assert page.locator('.profile-detail[data-print-empty="true"]:visible').count() == 0
                assert page.locator('.profile-detail[data-print-empty="false"]:visible').count() > 0
                page.locator('[data-print-empty-option="hide_empty_sections"]').check()
                assert page.locator('.profile-section[data-print-empty="true"]').count() > 0
                assert page.locator('.profile-section[data-print-empty="true"]:visible').count() == 0
                page.locator('[data-print-font]').fill('10')
                page.locator('[data-print-orientation]').select_option('portrait')
                page.locator('[data-print-save]').click()
                page.get_by_role('status').filter(has_text='برای حساب شما ذخیره شد.').wait_for()
                page.reload()
                assert page.locator('[data-print-empty-option="hide_empty_fields"]').is_checked()
                assert page.locator('[data-print-empty-option="hide_empty_sections"]').is_checked()
                assert page.locator('.profile-detail[data-print-empty="true"]:visible').count() == 0
                assert page.locator('.profile-section[data-print-empty="true"]:visible').count() == 0
                page.locator('[data-print-empty-option="hide_empty_fields"]').uncheck()
                page.locator('[data-print-empty-option="hide_empty_sections"]').uncheck()
                assert empty_fields.first.is_visible()
                assert float(page.locator('[data-print-font]').input_value()) == 10
                assert page.locator('[data-print-orientation]').input_value() == 'portrait'
                assert page.locator('[data-print-section="family"]').is_checked()
                size = page.locator('.profile-detail__value').first.evaluate('e=>getComputedStyle(e).fontSize')
                assert abs(float(size[:-2]) - 13.3333) < .1
                page.locator('[data-print-section="family"]').uncheck()
                page.emulate_media(media='print')
                assert not page.locator('[data-student-print-controls]').is_visible()
                assert not page.locator('[data-print-section-key="family"]').is_visible()
                assert page.locator('.print-container').evaluate('e=>getComputedStyle(e).color') == 'rgb(0, 0, 0)'
                page.pdf(path=str(fixture._tmp / 'portrait.pdf'), prefer_css_page_size=True)
                page.emulate_media(media='screen')
                page.locator('[data-print-orientation]').select_option('landscape')
                page.emulate_media(media='print')
                page.pdf(path=str(fixture._tmp / 'landscape.pdf'), prefer_css_page_size=True)
                page.emulate_media(media='screen')
                page.goto(base + '/print_filtered_students')
                assert page.locator('.student-record').count() == 2
                assert page.locator('.profile-detail[data-print-empty="true"]:visible').count() == 0
                assert page.locator('.profile-section[data-print-empty="true"]:visible').count() == 0
                page.locator('[data-print-section="family"]').uncheck()
                assert page.locator('[data-print-section-key="family"]:visible').count() == 0
                page.emulate_media(media='print')
                page.pdf(path=str(fixture._tmp / 'group.pdf'), prefer_css_page_size=True)
                page.emulate_media(media='screen')
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                for source in ('/', f'/student/{student_id}'):
                    page.goto(base + source)
                    page.locator('[data-student-print-controls] summary').click()
                    page.locator('[data-print-font]').fill('9')
                    page.locator('[data-print-save]').click()
                    page.get_by_role('status').filter(has_text='برای حساب شما ذخیره شد.').wait_for()
                    page.goto(base + url)
                    assert float(page.locator('[data-print-font]').input_value()) == 9
                assert not errors, errors
                browser.close()
            print('PASS: Chromium selection, live font sizing, save/reload, group, mobile, print media; PDFs:', fixture._tmp)
        finally:
            server.shutdown()
