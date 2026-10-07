#!/usr/bin/env python
"""Exercise AI document settings, privacy boundaries and previews offline."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = Path(tempfile.mkdtemp(prefix='ai-documents-test-'))
_credentials = ROOT / 'initial_credentials.txt'
_credentials_existed = _credentials.exists()
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'ai-documents-test-secret-key',
})

from school_app import app  # noqa: E402
from school_app.ai_documents import (  # noqa: E402
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_URL,
    DEFAULT_OLLAMA_URL,
    _parse_model_document,
    effective_public_provider_config,
    generate_document,
    is_remote_provider,
    private_provider_config,
    provider_choices,
    public_provider_config,
)
from school_app.database import get_db  # noqa: E402
from school_app.routes.ai_documents import _load_records  # noqa: E402


CSRF = 'ai-documents-test-token'


def login(client, role: str, user_id: int = 700) -> None:
    with client.session_transaction() as session:
        session.update({
            'user_id': user_id,
            'role': role,
            'personnel_number': role,
            'full_name': 'کاربر آزمایشی',
            '_csrf_token': CSRF,
        })


def main() -> int:
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    with app.app_context():
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO students(first_name,last_name,code,father_name,grade,class_name)
                   VALUES('نمونه','آزمون','AI-ST-1','پدر نمونه','پایه سوم','کلاس ۲')'''
            )
            student_id = conn.execute('SELECT id FROM students WHERE code=?', ('AI-ST-1',)).fetchone()['id']
            conn.execute(
                "INSERT INTO students(first_name,last_name,code,status,grade) VALUES('بایگانی','قدیمی','AI-OLD','فارغ‌التحصیل','پایه اول')"
            )
            records = _load_records(conn, [student_id], 'letter')
            assert records, {
                'student_id': student_id,
                'rows': [dict(row) for row in conn.execute('SELECT id,code,status FROM students').fetchall()],
                'active_match': conn.execute(
                    "SELECT id FROM students WHERE id=? AND (status='فعال' OR status IS NULL)",
                    (student_id,),
                ).fetchall(),
            }

    admin = app.test_client()
    manager = app.test_client()
    teacher = app.test_client()
    login(admin, 'admin')
    login(manager, 'manager')
    login(teacher, 'teacher')

    assert manager.get('/ai-documents').status_code == 200
    assert 'ai_documents.css'.encode() in manager.get('/ai-documents').data
    assert manager.get('/settings/ai-documents').status_code == 403
    assert teacher.get('/ai-documents').status_code == 403
    assert admin.get('/settings/ai-documents').status_code == 200

    saved = admin.post('/settings/ai-documents', data={
        '_csrf_token': CSRF,
        'provider': 'openai-compatible',
        'base_url': 'https://example.invalid/v1',
        'model': 'test-model',
        'api_key': 'never-store-plaintext-test-key',
    })
    assert saved.status_code == 302
    with app.app_context(), get_db() as conn:
        public = public_provider_config(conn)
        private = private_provider_config(conn)
        stored = conn.execute(
            "SELECT value FROM app_settings WHERE key='ai_documents:provider_config'"
        ).fetchone()['value']
        assert public['configured'] and public['api_key_set']
        assert private['api_key'] == 'never-store-plaintext-test-key'
        assert 'never-store-plaintext-test-key' not in stored

    payload = {
        'document_type': 'letter',
        'student_ids': [student_id],
        'brief': 'نامهٔ آزمایشی',
        'paper': 'a4-portrait',
    }
    with patch('school_app.routes.ai_documents.generate_document') as generate:
        generate.return_value = ('سند آزمایشی', '<article>پیش‌نمایش</article>')
        missing_consent = manager.post('/ai-documents/generate', json=payload,
                                       headers={'X-CSRF-Token': CSRF})
        assert missing_consent.status_code == 400
        generate.assert_not_called()

        payload['allow_external_data'] = True
        generated = manager.post('/ai-documents/generate', json=payload,
                                 headers={'X-CSRF-Token': CSRF})
        assert generated.status_code == 200, generated.get_data(as_text=True)
        assert generated.json['ok'] and generated.json['paper'] == 'a4-portrait'
        records = generate.call_args.args[3]
        assert records, repr(generate.call_args)
        assert records[0]['student_name'] == 'نمونه آزمون'
        assert records[0]['parent_name'] == 'پدر نمونه'
        assert 'phone' not in records[0] and 'national_id' not in records[0]

        payload['document_type'] = 'card'
        generated = manager.post('/ai-documents/generate', json=payload,
                                 headers={'X-CSRF-Token': CSRF})
        assert generated.status_code == 200
        assert 'parent_name' not in generate.call_args.args[3][0]

        payload['document_type'] = 'receipt'
        payload['student_ids'] = [student_id, student_id + 1]
        receipt_multiple = manager.post('/ai-documents/generate', json=payload,
                                        headers={'X-CSRF-Token': CSRF})
        assert receipt_multiple.status_code == 400

        with app.app_context(), get_db() as conn:
            conn.executemany(
                '''INSERT INTO monthly_service(student_code,year,month,service_type,amount,paid_amount,status)
                   VALUES('AI-ST-1','1405',?,?,?,?,'جزئی')''',
                [('مهر', 'رفت و برگشت', 1_000_000, 100_000),
                 ('آذر', 'رفت و برگشت', 900_000, 250_000)],
            )
        payload['student_ids'] = [student_id]
        with app.app_context(),get_db() as conn:
            payload['service_id']=conn.execute("SELECT id FROM monthly_service WHERE student_code='AI-ST-1' AND month='آذر'").fetchone()['id']
        receipt = manager.post('/ai-documents/generate', json=payload,
                               headers={'X-CSRF-Token': CSRF})
        assert receipt.status_code == 200
        record = generate.call_args.args[3][0]
        assert record['amount_due'] == '۹۰۰,۰۰۰ تومان'
        assert record['amount_paid'] == '۲۵۰,۰۰۰ تومان'
        assert record['remaining'] == '۶۵۰,۰۰۰ تومان'

    malformed = manager.post('/ai-documents/generate', json=[], headers={'X-CSRF-Token': CSRF})
    assert malformed.status_code == 400
    no_csrf = manager.post('/ai-documents/generate', json={})
    assert no_csrf.status_code == 400

    _title, sanitized = _parse_model_document(json.dumps({
        'title': 'طرح امن',
        'html': '<div onclick="run()"><h1>{{student_name}}</h1><script>run()</script>'
                '<img src="x" onerror="run()"></div>',
    }), 'card')
    assert '<script' not in sanitized and '<img' not in sanitized and 'onclick' not in sanitized

    with app.app_context():
        _ai_docs = importlib.import_module('school_app.ai_documents')
        with patch.object(_ai_docs, 'request_chat_completion', return_value=json.dumps({
            'title': 'کارت', 'html': '<h1>{{student_name}}</h1>',
        })):
            _title, rendered = generate_document(
                {'provider': 'ollama', 'base_url': 'http://127.0.0.1:11434/v1', 'model': 'test'},
                'card', 'کارت نام', [{'student_name': '<img src=x>', 'grade': '', 'class_name': ''}],
            )
        assert '&lt;img src=x&gt;' in rendered and '<img src=x>' not in rendered

    with app.app_context(), get_db() as conn:
        config = json.loads(conn.execute(
            "SELECT value FROM app_settings WHERE key='ai_documents:provider_config'"
        ).fetchone()['value'])
        config.update(provider='ollama', base_url='http://127.0.0.1:11434/v1')
        conn.execute(
            "UPDATE app_settings SET value=? WHERE key='ai_documents:provider_config'",
            (json.dumps(config),),
        )
        app.config['SECRET_KEY'] = 'rotated-secret-for-local-ollama-test'
        assert private_provider_config(conn)['api_key'] == ''
        app.config['SECRET_KEY'] = 'ai-documents-test-secret-key'

    # list_ollama_models — empty result when server unreachable
    from school_app.ai_documents import list_ollama_models
    assert isinstance(list_ollama_models('http://127.0.0.1:9999/v1'), list)

    # ai_documents_list_models route returns JSON
    with app.app_context():
        resp = admin.get('/settings/ai-documents/models?url=http://127.0.0.1:9999/v1')
        assert resp.status_code == 200
        assert resp.content_type.startswith('application/json')
        data = resp.get_json()
        assert isinstance(data['models'], list)

    # Gemini provider — same OpenAI-compatible transport, its own defaults.
    gemini_saved = admin.post('/settings/ai-documents', data={
        '_csrf_token': CSRF,
        'provider': 'gemini',
        'base_url': '',
        'model': '',
        'api_key': 'gemini-test-key',
    })
    assert gemini_saved.status_code == 302
    with app.app_context(), get_db() as conn:
        gemini_public = public_provider_config(conn)
        assert gemini_public['provider'] == 'gemini'
        assert gemini_public['provider_label'] == 'Google Gemini'
        assert gemini_public['base_url'] == DEFAULT_GEMINI_URL
        assert gemini_public['model'] == DEFAULT_GEMINI_MODEL
        assert gemini_public['configured'] and gemini_public['api_key_set']
    assert is_remote_provider('gemini') and is_remote_provider('openai-compatible')
    assert not is_remote_provider('ollama')

    # A remote Gemini call must still require explicit consent.
    gemini_payload = {
        'document_type': 'letter',
        'student_ids': [student_id],
        'brief': 'gemini consent check',
        'paper': 'a4-portrait',
    }
    with patch('school_app.routes.ai_documents.generate_document') as generate_gemini:
        generate_gemini.return_value = ('t', '<article>x</article>')
        no_consent = manager.post('/ai-documents/generate', json=gemini_payload,
                                  headers={'X-CSRF-Token': CSRF})
        assert no_consent.status_code == 400
        generate_gemini.assert_not_called()
        gemini_payload['allow_external_data'] = True
        consented = manager.post('/ai-documents/generate', json=gemini_payload,
                                 headers={'X-CSRF-Token': CSRF})
        assert consented.status_code == 200

    # The settings page renders the Gemini option and its preset URL.
    settings_page = admin.get('/settings/ai-documents').get_data(as_text=True)
    assert 'value="gemini"' in settings_page
    assert DEFAULT_GEMINI_URL in settings_page
    assert 'Google Gemini' in settings_page

    # ── انتخاب سرویس و مدل در صفحهٔ طراحی ────────────────────────────────
    # سرویس ثبت‌شده باید در یک کادر قابل انتخاب باشد و مدل‌های Ollama محلی
    # خودکار خوانده شوند، بدون آنکه تنظیم ثبت‌شدهٔ مدیر تغییر کند.
    # ماژول مدل‌ها از راه object patch می‌شود: نام `school_app.ai_documents`
    # در فضای نام پکیج با ماژول route هم‌نام پوشانده شده است.
    ai_docs_module = importlib.import_module('school_app.ai_documents')
    design_page = manager.get('/ai-documents').get_data(as_text=True)
    assert 'id="aiProviderSelect"' in design_page
    assert 'id="aiModelSelect"' in design_page
    assert 'data-models-url="/ai-documents/models"' in design_page
    assert 'value="ollama"' in design_page and 'value="gemini"' in design_page
    assert 'id="aiProviderStatus"' in design_page

    models_response = manager.get('/ai-documents/models')
    assert models_response.status_code == 200
    models_payload = models_response.get_json()
    assert isinstance(models_payload['models'], list) and isinstance(models_payload['online'], bool)
    assert teacher.get('/ai-documents/models').status_code == 403
    assert teacher.post('/ai-documents/provider', json={'provider': 'ollama'},
                        headers={'X-CSRF-Token': CSRF}).status_code == 403

    unavailable = manager.post('/ai-documents/provider', json={'provider': 'openai-compatible'},
                              headers={'X-CSRF-Token': CSRF})
    assert unavailable.status_code == 400
    assert not unavailable.json['ok'] and unavailable.json['error']

    installed = [
        {'name': 'qwen2.5:7b', 'label': 'qwen2.5:7b — 4.7 GB'},
        {'name': 'llama3.1:8b', 'label': 'llama3.1:8b — 4.9 GB'},
    ]
    with patch.object(ai_docs_module, 'ollama_status',
                      return_value={'online': True, 'base_url': DEFAULT_OLLAMA_URL, 'models': installed}):
        missing_model = manager.post('/ai-documents/provider',
                                     json={'provider': 'ollama', 'model': 'not-installed:1b'},
                                     headers={'X-CSRF-Token': CSRF})
        assert missing_model.status_code == 400 and 'نصب نیست' in missing_model.json['error']

        chosen = manager.post('/ai-documents/provider',
                              json={'provider': 'ollama', 'model': 'qwen2.5:7b'},
                              headers={'X-CSRF-Token': CSRF})
        assert chosen.status_code == 200, chosen.get_data(as_text=True)
        assert chosen.json['ok'] and chosen.json['provider']['provider'] == 'ollama'
        assert chosen.json['provider']['model'] == 'qwen2.5:7b'
        assert chosen.json['provider']['configured']

        # سرویس محلی داده‌ای به بیرون نمی‌فرستد، پس رضایت اینترنتی لازم نیست؛
        # در عوض مدل و نشانی محلی دقیقاً همان چیزی است که کاربر انتخاب کرد.
        with patch('school_app.routes.ai_documents.generate_document') as local_generate:
            local_generate.return_value = ('سند محلی', '<article>محلی</article>')
            local_call = manager.post('/ai-documents/generate', json={
                'document_type': 'card',
                'student_ids': [student_id],
                'brief': 'کارت محلی',
                'paper': 'a4-portrait',
            }, headers={'X-CSRF-Token': CSRF})
            assert local_call.status_code == 200, local_call.get_data(as_text=True)
            local_config = local_generate.call_args.args[0]
            assert local_config['provider'] == 'ollama'
            assert local_config['model'] == 'qwen2.5:7b'
            assert local_config['base_url'] == DEFAULT_OLLAMA_URL
            assert local_config['api_key'] == ''

    # تنظیم ثبت‌شدهٔ Gemini دست‌نخورده مانده است.
    with app.app_context(), get_db() as conn:
        assert public_provider_config(conn)['provider'] == 'gemini'
        assert private_provider_config(conn)['api_key'] == 'gemini-test-key'

    # انتخاب per-user است: کاربر دیگری همچنان سرویس ثبت‌شده را می‌بیند.
    other = app.test_client()
    login(other, 'manager', 701)
    other_page = other.get('/ai-documents')
    assert other_page.status_code == 200
    assert 'data-provider="gemini"' in other_page.get_data(as_text=True)
    with app.app_context(), get_db() as conn:
        assert effective_public_provider_config(conn, 701)['provider'] == 'gemini'
        assert effective_public_provider_config(conn, 700)['model'] == 'qwen2.5:7b'
        assert [choice['key'] for choice in provider_choices(conn)] == ['ollama', 'gemini']

    with patch.object(ai_docs_module, 'ollama_status',
                      return_value={'online': False, 'base_url': DEFAULT_OLLAMA_URL, 'models': []}):
        offline = manager.post('/ai-documents/provider',
                               json={'provider': 'ollama', 'model': 'qwen2.5:7b'},
                               headers={'X-CSRF-Token': CSRF})
        assert offline.status_code == 400 and 'Ollama محلی' in offline.json['error']

    # بازگشت به سرویس ثبت‌شده: دوباره رضایت اینترنتی لازم می‌شود.
    back = manager.post('/ai-documents/provider', json={'provider': 'gemini'},
                        headers={'X-CSRF-Token': CSRF})
    assert back.status_code == 200 and back.json['provider']['provider'] == 'gemini'
    with app.app_context(), get_db() as conn:
        assert effective_public_provider_config(conn, 700)['model'] == DEFAULT_GEMINI_MODEL
    with patch('school_app.routes.ai_documents.generate_document') as remote_generate:
        remote_generate.return_value = ('نامه', '<article>ابر</article>')
        needs_consent = manager.post('/ai-documents/generate', json={
            'document_type': 'card',
            'student_ids': [student_id],
            'brief': 'بازگشت به سرویس اینترنتی',
            'paper': 'a4-portrait',
        }, headers={'X-CSRF-Token': CSRF})
        assert needs_consent.status_code == 400
        remote_generate.assert_not_called()

    # ثبت اتصال اینترنتی از خود صفحهٔ طراح اسناد: یک‌بار وارد و ذخیره می‌شود.
    manager_connection = manager.post('/ai-documents/connection', json={
        'provider': 'openai-compatible',
        'base_url': 'https://manager.invalid/v1',
        'model': 'manager-model',
        'api_key': 'manager-key-not-allowed',
    }, headers={'X-CSRF-Token': CSRF})
    assert manager_connection.status_code == 403, manager_connection.status_code
    with app.app_context(), get_db() as conn:
        assert public_provider_config(conn)['base_url'] != 'https://manager.invalid/v1'

    saved_connection = admin.post('/ai-documents/connection', json={
        'provider': 'openai-compatible',
        'base_url': 'https://design-page.invalid/v1',
        'model': 'design-page-model',
        'api_key': 'design-page-secret-key',
    }, headers={'X-CSRF-Token': CSRF})
    assert saved_connection.status_code == 200, saved_connection.get_data(as_text=True)
    connection_body = saved_connection.get_json()
    assert connection_body['ok'] and connection_body['provider']['configured']
    assert connection_body['provider']['api_key_set']
    assert any(
        choice['key'] == 'openai-compatible' and choice['ready']
        for choice in connection_body['choices']
    ), connection_body['choices']
    with app.app_context(), get_db() as conn:
        assert public_provider_config(conn)['base_url'] == 'https://design-page.invalid/v1'
        assert public_provider_config(conn)['model'] == 'design-page-model'
        assert private_provider_config(conn)['api_key'] == 'design-page-secret-key'
        stored_connection = conn.execute(
            "SELECT value FROM app_settings WHERE key='ai_documents:provider_config'"
        ).fetchone()['value']
        assert 'design-page-secret-key' not in stored_connection

    # ذخیرهٔ نامعتبر باید رد شود و اتصال ذخیره‌شدهٔ قبلی را خراب نکند.
    rejected_connection = admin.post('/ai-documents/connection', json={
        'provider': 'openai-compatible',
        'base_url': 'http://insecure.invalid/v1',
        'model': 'model',
        'api_key': 'key',
    }, headers={'X-CSRF-Token': CSRF})
    assert rejected_connection.status_code == 400
    assert 'HTTPS' in rejected_connection.get_json()['error']
    with app.app_context(), get_db() as conn:
        assert public_provider_config(conn)['base_url'] == 'https://design-page.invalid/v1'
        assert private_provider_config(conn)['api_key'] == 'design-page-secret-key'

    # کادر اتصال فقط برای مدیر رندر می‌شود.
    assert b'aiConnectionSave' in admin.get('/ai-documents').data
    assert b'aiConnectionSave' not in manager.get('/ai-documents').data

    if not _credentials_existed and _credentials.exists():
        _credentials.unlink()
    shutil.rmtree(_tmp, ignore_errors=True)
    print('AI documents: roles, encrypted settings, consent, field limits, receipts, sanitization and '
          'per-user service/model selection passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
