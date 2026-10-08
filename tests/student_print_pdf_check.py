"""Optional Chromium + PyMuPDF print integrity check, using synthetic records only."""
import os
from pathlib import Path
from threading import Thread
import pymupdf
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import student_print_test as F

markers = [f'ADDR464-{i:03d}' for i in range(70)]
siblings = [f'SIB464-{i:03d}' for i in range(32)]
with F.app.app_context(), F.get_db() as conn:
    conn.execute('UPDATE students SET address=? WHERE id=?', ('\n'.join(f'{value} synthetic address line' for value in markers), F.student_id))
    for i, value in enumerate(siblings):
        conn.execute('INSERT INTO student_siblings(student_id,full_name,sort_order) VALUES(?,?,?)', (F.student_id, value, i))
    conn.commit()
F.admin.post('/student-print-settings', json={
    'font_size': 10, 'orientation': 'portrait', 'hide_empty_fields': True, 'hide_empty_sections': True,
    'sections': {'family': True, 'siblings': True},
}, headers={'X-CSRF-Token': 'studio-test-token'})
output = Path(os.environ.get('STUDENT_PRINT_ARTIFACTS', str(F.fixture._tmp)))
output.mkdir(parents=True, exist_ok=True)
server = make_server('127.0.0.1', 0, F.app, threaded=True)
Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'

def inspect_pdf(data, name, orientation, included, excluded):
    (output / f'{name}.pdf').write_bytes(data)
    with pymupdf.open(stream=data, filetype='pdf') as pdf:
        text = ''.join(''.join(page.get_text().split()) for page in pdf)
        for marker in included:
            assert marker in text, (name, 'missing', marker)
        for marker in excluded:
            assert marker not in text, (name, 'forbidden', marker)
        for page in pdf:
            assert page.get_text().strip(), (name, 'blank page')
            width, height = (595.28, 841.89) if orientation == 'portrait' else (841.89, 595.28)
            assert abs(page.rect.width - width) < 2 and abs(page.rect.height - height) < 2
            for word in page.get_text('words'):
                assert word[0] >= -1 and word[1] >= -1 and word[2] <= page.rect.width + 1 and word[3] <= page.rect.height + 1, (name, 'outside page', word)
        if name == 'student-portrait':
            pdf[0].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(str(output / 'student-portrait.png'))
        print(f'PASS {name}: {len(pdf)} A4 pages; required text intact, forbidden text absent, extracted words inside paper')
        return len(pdf)

try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(base + '/fixture-login')
        page.evaluate('document.fonts.ready')
        for orientation in ('portrait', 'landscape'):
            page.locator('[data-print-orientation]').select_option(orientation)
            page.emulate_media(media='print')
            data = page.pdf(prefer_css_page_size=True)
            assert inspect_pdf(data, f'student-{orientation}', orientation, ['PRINT-A'] + markers + siblings, ['PRINT-B']) > 1
            page.emulate_media(media='screen')
        page.goto(base + '/print_filtered_students')
        page.evaluate('document.fonts.ready')
        page.emulate_media(media='print')
        inspect_pdf(page.pdf(prefer_css_page_size=True), 'student-group', 'portrait', ['PRINT-A', 'PRINT-B'] + markers + siblings, ['PRINT-OLD'])
        page.emulate_media(media='screen')
        page.locator('[data-print-section="family"]').uncheck()
        page.locator('[data-print-section="siblings"]').uncheck()
        page.emulate_media(media='print')
        inspect_pdf(page.pdf(prefer_css_page_size=True), 'student-redacted', 'portrait', ['PRINT-A', 'PRINT-B'], markers + siblings + ['PRIVATE-FATHER'])
        browser.close()
finally:
    server.shutdown()
