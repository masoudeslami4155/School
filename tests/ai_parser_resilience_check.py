#!/usr/bin/env python
"""Offline checks for the resilient _parse_model_document and retry loop."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = Path(tempfile.mkdtemp(prefix='ai-parser-check-'))
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'ai-parser-check-secret',
})

from school_app import app  # noqa: E402
from school_app.ai_documents import AIProviderError, _parse_model_document, generate_document  # noqa: E402

# school_app.routes.ai_documents shadows the package attribute, so patch
# against the real module object from sys.modules.
AI_DOCUMENTS_MODULE = sys.modules['school_app.ai_documents']

GOOD = '{"title": "نامه", "html": "<p>برای {{student_name}} در پایهٔ {{grade}}</p>"}'
failures = []


def check(name, fn):
    try:
        fn()
        print(f'ok   {name}')
    except AssertionError as exc:
        failures.append(name)
        print(f'FAIL {name}: {exc}')


def case_clean():
    title, html = _parse_model_document(GOOD, 'letter')
    assert title == 'نامه' and '{{student_name}}' in html, (title, html)


def case_prose():
    messy = 'سلام! این خروجی مدل است:\n' + GOOD + '\nامیدوارم مفید باشد. با تشکر.'
    title, html = _parse_model_document(messy, 'letter')
    assert title == 'نامه' and '{{student_name}}' in html, (title, html)


def case_fence():
    fenced = '```json\n' + GOOD + '\n```'
    title, html = _parse_model_document(fenced, 'letter')
    assert title == 'نامه' and '{{student_name}}' in html, (title, html)


def case_bare_html():
    title, html = _parse_model_document('<p>متن ساده برای {{student_name}}</p>', 'letter')
    assert title == 'سند چاپی' and '{{student_name}}' in html, (title, html)


def case_garbage():
    try:
        _parse_model_document('این خروجی هیچ JSON یا HTML ندارد.', 'letter')
    except AIProviderError as exc:
        assert 'قالب مورد انتظار' in str(exc), str(exc)
    else:
        raise AssertionError('garbage should raise FORMAT_ERROR')


def case_json_missing_token():
    bad = '{"title": "نامه", "html": "<p>بدون توکن</p>"}'
    try:
        _parse_model_document(bad, 'letter')
    except AIProviderError as exc:
        assert 'فیلدهای ضروری' in str(exc), str(exc)
    else:
        raise AssertionError('missing required token should raise')


def case_retry_success():
    answers = ['خروجی بی‌ربط و بدون قالب', GOOD]

    def fake(config, messages, tools=None):
        return answers.pop(0)

    config = {'base_url': 'http://x', 'model': 'm'}
    records = [{'student_name': 'علی', 'grade': 'سوم'}]
    with app.app_context():
        with patch.object(AI_DOCUMENTS_MODULE, 'request_chat_completion', side_effect=fake):
            title, html = generate_document(config, 'letter', 'تست', records)
    assert title == 'نامه', title
    assert 'علی' in html and 'سوم' in html, html


def case_retry_exhausted():
    def fake(config, messages, tools=None):
        return 'همیشه بی‌ربط'

    config = {'base_url': 'http://x', 'model': 'm'}
    records = [{'student_name': 'علی'}]
    with app.app_context():
        with patch.object(AI_DOCUMENTS_MODULE, 'request_chat_completion', side_effect=fake):
            try:
                generate_document(config, 'letter', 'تست', records)
            except AIProviderError as exc:
                assert 'قالب مورد انتظار' in str(exc), str(exc)
            else:
                raise AssertionError('two bad answers must raise FORMAT_ERROR')


def case_retry_not_used_for_token_error():
    answers = ['{"title":"ن","html":"<p>بدون توکن</p>"}']

    def fake(config, messages, tools=None):
        answers.pop(0)
        return answers.pop(0) if answers else '{"title":"n","html":"<p>بدون توکن</p>"}'

    config = {'base_url': 'http://x', 'model': 'm'}
    with app.app_context():
        with patch.object(AI_DOCUMENTS_MODULE, 'request_chat_completion', side_effect=fake) as mock:
            try:
                generate_document(config, 'letter', 'تست', [{'student_name': 'علی'}])
            except AIProviderError as exc:
                assert 'فیلدهای ضروری' in str(exc), str(exc)
            else:
                raise AssertionError('missing token must raise without retry')
            assert mock.call_count == 1, f'retry should not fire, got {mock.call_count}'


def main() -> int:
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    check('clean json', case_clean)
    check('json in prose', case_prose)
    check('json in fence', case_fence)
    check('bare html fallback', case_bare_html)
    check('garbage raises format error', case_garbage)
    check('json missing required token', case_json_missing_token)
    check('retry recovers from garbage', case_retry_success)
    check('retry exhausted raises', case_retry_exhausted)
    check('token error does not retry', case_retry_not_used_for_token_error)
    print(f'\n{len(failures)} failure(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
