#!/usr/bin/env python
"""Exercise AI letter templates: presets, save/load/delete and generation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = Path(tempfile.mkdtemp(prefix='ai-letter-templates-'))
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'ai-letter-templates-secret',
})

from school_app import app  # noqa: E402
from school_app.ai_letter_layout import (  # noqa: E402
    TEMPLATE_PRESETS,
    default_layout,
    delete_user_template,
    list_templates,
    load_template,
    save_user_template,
)
from school_app.database import get_db  # noqa: E402

CSRF = 'letter-templates-token'


def login(client, role='admin'):
    with client.session_transaction() as session:
        session.update({
            'user_id': 700, 'role': role, 'personnel_number': role,
            'full_name': 'کاربر آزمایشی', '_csrf_token': CSRF,
        })


def main() -> int:
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    with app.app_context():
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO students(first_name,last_name,code,status,grade,class_name)
                   VALUES('زهرا','آزمونی','ST-TPL','فعال','پایه سوم','کلاس ۲')'''
            )
            student_id = conn.execute(
                "SELECT id FROM students WHERE code='ST-TPL'").fetchone()['id']

    client = app.test_client()
    login(client)

    # 1. Studio and generator page expose the built-in presets
    studio = client.get('/report-print-layouts?document=ai_letter')
    assert studio.status_code == 200, studio.status_code
    assert b'id="letterTemplateSelect"' in studio.data
    for label in ('تذکر رسمی', 'دعوت‌نامه', 'نامهٔ معرفی'):
        assert label.encode() in studio.data, label
    documents = client.get('/ai-documents')
    assert documents.status_code == 200, documents.status_code
    assert b'id="aiLetterTemplate"' in documents.data
    print('✓ الگوهای پیش‌فرض در استودیو و صفحهٔ طراح نمایش داده می‌شوند')

    with app.app_context(), get_db() as conn:
        presets = list_templates(conn, 700)
    assert [item['key'] for item in presets[:3]] == list(TEMPLATE_PRESETS)
    assert all(item['builtin'] for item in presets[:3])
    # presets differ from each other and from the plain default layout
    assert presets[1]['layout']['elements']['school']['font'] == 1.5
    assert presets[2]['layout']['elements']['signature']['x'] == 45
    assert presets[0]['layout'] == default_layout()
    print('✓ سه الگوی پیش‌فرض با چیدمان‌های متفاوت موجود است')

    # 2. Save a personal template from the studio with an out-of-range layout
    personal = default_layout()
    personal['orientation'] = 'landscape'
    personal['font_size'] = 99
    personal['elements']['body'].update({'x': 55, 'y': 30, 'w': 70, 'h': 20, 'font': 2})
    saved = client.post('/report-print-layouts?document=ai_letter', data={
        '_csrf_token': CSRF, 'document': 'ai_letter', 'action': 'save_template',
        'template_key': 'varzeshi', 'template_label': 'تذکر ورزشی',
        'layout_json': json.dumps(personal),
    })
    assert saved.status_code == 302, saved.status_code
    with app.app_context(), get_db() as conn:
        stored = load_template(conn, 700, 'varzeshi')
        names = [item['key'] for item in list_templates(conn, 700)]
    assert stored is not None
    assert stored['font_size'] == 18, stored['font_size']  # clamped
    assert stored['orientation'] == 'landscape'
    assert stored['elements']['body']['x'] == 55
    assert stored['elements']['body']['w'] == 45, stored['elements']['body']['w']  # clamped
    assert 'varzeshi' in names
    print('✓ الگوی شخصی ذخیره شد و مقادیر نامعتبر گرفته شدند')

    # 3. Built-in keys are reserved and invalid templates are rejected
    reserved = client.post('/report-print-layouts?document=ai_letter', data={
        '_csrf_token': CSRF, 'document': 'ai_letter', 'action': 'save_template',
        'template_key': 'tazzek', 'template_label': 'دزدی', 'layout_json': '{}',
    })
    assert reserved.status_code == 302, reserved.status_code
    with app.app_context(), get_db() as conn:
        assert load_template(conn, 700, 'tazzek') == default_layout()
    try:
        save_user_template(None, 700, 'tazzek', 'x', {})
        raise AssertionError('builtin key must be rejected')
    except ValueError:
        pass
    try:
        save_user_template(None, 700, 'bad key!', 'x', {})
        raise AssertionError('invalid key must be rejected')
    except ValueError:
        pass
    print('✓ کلیدهای پیش‌فرض محفوظ و کلیدهای نامعتبر رد شدند')

    # 4. Generating a letter with a template applies that template's layout
    response = client.post('/ai-documents/generate-letter', json={
        'brief': 'تذکر حضور و انضباط دانش‌آموز',
        'paper': 'a4-portrait',
        'template': 'varzeshi',
        'student_ids': [student_id],
    }, headers={'X-CSRF-Token': CSRF})
    assert response.status_code == 200, (response.status_code, response.data[:300])
    payload = response.get_json()
    assert payload['ok'] is True, payload
    assert payload['paper'] == 'a4-landscape', payload['paper']
    html = payload['html']
    assert 'width:297.0mm;height:210.0mm' in html
    assert 'left:55.0%;top:30.0%;width:45.0%' in html, 'template body position missing'
    assert 'font-size:18.0pt' in html
    print('✓ نامه با الگوی انتخاب‌شده ساخته شد (چیدمان الگو اعمال شد)')

    # 5. Unknown template is a clear error, not a silent fallback
    missing = client.post('/ai-documents/generate-letter', json={
        'brief': 'تذکر', 'paper': 'a4-portrait', 'template': 'ghost',
        'student_ids': [student_id],
    }, headers={'X-CSRF-Token': CSRF})
    assert missing.status_code == 400, missing.status_code
    assert 'الگوی نامه' in missing.get_json()['error']
    print('✓ الگوی ناموجود با خطای شفست رد شد')

    # 6. Delete removes the user template; built-ins stay
    deleted = client.post('/report-print-layouts?document=ai_letter', data={
        '_csrf_token': CSRF, 'document': 'ai_letter', 'action': 'delete_template',
        'template_key': 'varzeshi',
    })
    assert deleted.status_code == 302, deleted.status_code
    with app.app_context(), get_db() as conn:
        assert load_template(conn, 700, 'varzeshi') is None
        assert [item['key'] for item in list_templates(conn, 700)][:3] == list(TEMPLATE_PRESETS)
    try:
        delete_user_template(None, 700, 'daavat')
        raise AssertionError('builtin delete must be rejected')
    except ValueError:
        pass
    print('✓ حذف الگوی شخصی انجام شد و الگوهای پیش‌فرض باقی ماندند')

    print('\n✅ آزمون الگوهای نامه: پیش‌فرض، ذخیره، بارگذاری، حذف و تولید موفق بود')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
