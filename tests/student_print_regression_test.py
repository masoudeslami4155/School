"""4.64 regressions; synthetic DB only. Optional --browser also runs base browser tests."""
import sys
from threading import Thread
import student_print_test as F
from school_app.database import get_db
from school_app.report_print_layouts import default_layout, load_layout, sanitize_layout

assert default_layout('school_statistics')['font_size'] == 10
headers = {'X-CSRF-Token': 'studio-test-token'}
with F.app.app_context(), get_db() as conn:
    before = load_layout(conn, 'student_info', 700)
for value in ([], {}, None, 42, True):
    response = F.admin.post('/student-print-settings', json={'orientation': value, 'sections': {}}, headers=headers)
    assert response.status_code == 400, (value, response.status_code)
    assert sanitize_layout('student_info', {'orientation': value})['orientation'] == 'portrait'
with F.app.app_context(), get_db() as conn:
    assert load_layout(conn, 'student_info', 700) == before
    for key, visible, value in [('reg_public', 1, 'PUBLIC-CUSTOM-464'), ('reg_private', 0, 'PRIVATE-CUSTOM-464')]:
        field_id = conn.execute('INSERT INTO student_custom_fields(field_key,label,show_to_teacher,created_at) VALUES(?,?,?,?)',
                                (key, key, visible, '2026-10-08')).lastrowid
        conn.execute('INSERT INTO student_custom_values(student_id,field_id,value,updated_at) VALUES(?,?,?,?)',
                     (F.student_id, field_id, value, '2026-10-08'))
    other_id = conn.execute("SELECT id FROM students WHERE code='PRINT-B'").fetchone()['id']
    conn.commit()

for path in ('/', f'/student/{F.student_id}', F.url, '/print_filtered_students'):
    assert b'data-student-print-controls' in F.admin.get(path).data
for path in (F.url, '/print_filtered_students'):
    html = F.teacher.get(path).data
    assert b'data-print-section="custom"' in html
    assert b'PUBLIC-CUSTOM-464' in html
    assert b'PRIVATE-CUSTOM-464' not in html
    assert b'PRIVATE-FATHER' not in html
    assert b'PRINT-B' not in html
response = F.teacher.post('/student-print-settings', json={'sections': {'custom': False, 'family': True}}, headers=headers)
assert response.status_code == 200 and response.json['layout']['sections']['custom'] is False
html = F.teacher.get(F.url).text
assert 'hidden' in html.split('data-print-section-key="custom"', 1)[1].split('>', 1)[0]
assert 'PUBLIC-CUSTOM-464' in html  # Presentation only, not access control.
assert 'PRIVATE-CUSTOM-464' not in html and 'PRIVATE-FATHER' not in html
response = F.teacher.post('/student-print-settings', json={'sections': {'custom': True}}, headers=headers)
assert response.json['layout']['sections']['custom'] is True
with F.app.app_context(), get_db() as conn:
    assert load_layout(conn, 'student_info', 700) == before
selected = F.teacher.post('/print_selected', data={'ids': f'{F.student_id},{other_id}', '_csrf_token': 'studio-test-token'})
assert selected.status_code == 200
assert b'PUBLIC-CUSTOM-464' in selected.data
for secret in (b'PRINT-B', b'PRIVATE-FATHER', b'PRIVATE-CUSTOM-464'):
    assert secret not in selected.data
assert F.teacher.get(f'/print/{other_id}').status_code in (302, 403, 404)
assert F.app.test_client().post('/student-print-settings', json={'sections': {}}).status_code == 302
print('PASS 4.64: dashboard integration, invalid orientation, statistics font, teacher custom controls, privacy and cross-student scope')

if '--browser' in sys.argv:
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 0, F.app, threaded=True)
    Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        F.admin.post('/student-print-settings', json={'font_size': 9, 'sections': {'family': True}}, headers=headers)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/fixture-login')
            page.goto(base + f'/student/{F.student_id}')
            page.locator('[data-student-print-controls] summary').click()
            page.locator('[data-print-font]').fill('12')
            assert 'هنوز ذخیره نشده' in page.locator('[data-print-status]').inner_text()
            page.locator('[data-print-save]').click()
            page.locator('[data-print-status]').filter(has_text='برای حساب شما ذخیره شد.').wait_for()
            with page.expect_popup() as event:
                page.locator(f'a[href="/print/{F.student_id}"]').click()
            popup = event.value
            popup.wait_for_load_state()
            assert float(popup.locator('[data-print-font]').input_value()) == 12
            popup.close()
            page.goto(base + F.url)
            observed = []
            def delayed_response(route):
                response = route.fetch()
                for selector in ('[data-print-font]', '[data-print-orientation]', '[data-print-section="family"]', '[data-print-save]', '[data-print-now]'):
                    assert page.locator(selector).is_disabled(), selector
                observed.append(True)
                # Even a programmatic DOM change is reconciled with the canonical response.
                page.locator('[data-print-section="family"]').evaluate('el => { el.checked = false; }')
                route.fulfill(response=response)
            page.route('**/student-print-settings', delayed_response)
            page.locator('[data-print-save]').click()
            page.locator('[data-print-status]').filter(has_text='برای حساب شما ذخیره شد.').wait_for()
            assert observed and page.locator('[data-print-section="family"]').is_checked()
            assert page.locator('[data-print-section="identity"]').is_disabled()
            assert page.locator('[data-print-font]').is_enabled()
            page.unroute('**/student-print-settings', delayed_response)
            page.reload()
            assert page.locator('[data-print-section="family"]').is_checked()
            assert float(page.locator('[data-print-font]').input_value()) == 12
            def failed_response(route):
                route.fulfill(status=503, body='Unavailable')
            page.route('**/student-print-settings', failed_response)
            page.locator('[data-print-font]').fill('11')
            page.locator('[data-print-save]').click()
            page.locator('[data-print-status]').filter(has_text='ذخیره انجام نشد').wait_for()
            assert page.locator('[data-print-save]').is_enabled()
            assert page.locator('[data-print-font]').is_enabled()
            assert page.locator('[data-print-section="identity"]').is_disabled()
            assert float(page.locator('[data-print-font]').input_value()) == 11
            page.unroute('**/student-print-settings', failed_response)
            page.reload()
            assert float(page.locator('[data-print-font]').input_value()) == 12
            assert not errors, errors
            browser.close()
        print('PASS 4.64 Chromium: unsaved guidance, profile-to-print persistence, pending-save lock, canonical response, failure recovery')
    finally:
        server.shutdown()
