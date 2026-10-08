#!/usr/bin/env python
"""Prove AI provider settings survive a process restart (persistence check)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if sys.stdout.encoding and sys.stdout.encoding.lower() not in {'utf-8', 'utf8'}:
    sys.stdout.reconfigure(encoding='utf-8')

STEP1 = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, {root!r})
from school_app import app
from school_app.ai_documents import save_provider_config
from school_app.database import get_db

with app.app_context():
    with get_db() as conn:
        saved = save_provider_config(conn, {{
            'provider': 'gemini',
            'base_url': '',
            'model': '',
            'api_key': 'persist-test-key-۱۲۳',
        }})
        conn.commit()
    print(json.dumps({{'saved': saved}}, ensure_ascii=False))
'''

STEP2 = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, {root!r})
from school_app import app
from school_app.ai_documents import private_provider_config, public_provider_config
from school_app.database import get_db

with app.app_context():
    with get_db() as conn:
        raw = conn.execute(
            "SELECT value FROM app_settings WHERE key='ai_documents:provider_config'"
        ).fetchone()['value']
        public = public_provider_config(conn)
        private = private_provider_config(conn)

print(json.dumps({{
    'raw_row_has_plaintext_key': 'persist-test-key' in raw,
    'public': public,
    'decrypted_key_ok': private['api_key'] == 'persist-test-key-۱۲۳',
}}, ensure_ascii=False))
'''


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='ai-persist-'))
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env.update({
        'DATABASE_PATH': str(tmp / 'school.db'),
        'BACKUP_DIR': str(tmp / 'backups'),
        'LOG_DIR': str(tmp / 'logs'),
        'UPLOAD_FOLDER': str(tmp / 'uploads'),
        'SECRET_KEY': 'persistence-check-secret',
    })
    try:
        # Step 1: save settings in process #1
        code1 = STEP1.format(root=str(ROOT))
        r1 = subprocess.run(
            [sys.executable, '-c', code1], env=env,
            capture_output=True, text=True, timeout=120,
        )
        if r1.returncode != 0:
            print('STEP1 FAILED:\n', r1.stdout, r1.stderr)
            return 1
        saved = json.loads(r1.stdout.strip().splitlines()[-1])['saved']
        print('مرحله ۱ — ذخیره در process اول:')
        print('  provider      :', saved['provider_label'])
        print('  base_url      :', saved['base_url'])
        print('  model         :', saved['model'])
        print('  api_key_set   :', saved['api_key_set'])
        print('  configured    :', saved['configured'])

        # Step 2: read back in a BRAND NEW process
        code2 = STEP2.format(root=str(ROOT))
        r2 = subprocess.run(
            [sys.executable, '-c', code2], env=env,
            capture_output=True, text=True, timeout=120,
        )
        if r2.returncode != 0:
            print('STEP2 FAILED:\n', r2.stdout, r2.stderr)
            return 1
        result = json.loads(r2.stdout.strip().splitlines()[-1])
        print('\nمرحله ۲ — بارگذاری در process دوم (برنامه کاملاً بسته و باز شده):')
        pub = result['public']
        print('  provider      :', pub['provider_label'])
        print('  base_url      :', pub['base_url'])
        print('  model         :', pub['model'])
        print('  api_key_set   :', pub['api_key_set'])
        print('  configured    :', pub['configured'])
        print('  کلید رمزگشایی شد :', result['decrypted_key_ok'])
        print('  کلید ساده در دیتابیس نیست:', not result['raw_row_has_plaintext_key'])

        assert pub['provider'] == 'gemini', pub
        assert pub['base_url'].startswith('https://generativelanguage'), pub
        assert pub['model'] == 'gemini-2.0-flash', pub
        assert pub['configured'] and pub['api_key_set'], pub
        assert result['decrypted_key_ok'], result
        assert not result['raw_row_has_plaintext_key'], result
        print('\n✅ تنظیمات و اتصال پس از بستن برنامه، برای همیشه در school.db باقی ماندند.')
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
