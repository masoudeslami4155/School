#!/usr/bin/env python
"""ایمنی و رفتار پایهٔ تنظیمات چاپ A4 را بررسی می‌کند."""

from __future__ import annotations

import sqlite3
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = Path(tempfile.mkdtemp(prefix='print-layout-test-'))
_credentials_path = Path(__file__).resolve().parent.parent / 'initial_credentials.txt'
_credentials_existed = _credentials_path.exists()
os.environ.update({
    'DATABASE_PATH': str(_tmp / 'school.db'),
    'BACKUP_DIR': str(_tmp / 'backups'),
    'LOG_DIR': str(_tmp / 'logs'),
    'UPLOAD_FOLDER': str(_tmp / 'uploads'),
    'SECRET_KEY': 'print-layout-test-secret-key',
})

from school_app.print_layouts import (
    build_slip_batch,
    default_layout,
    load_layout,
    prepare_for_print,
    save_layout,
    sanitize_layout,
)

if not _credentials_existed and _credentials_path.exists():
    _credentials_path.unlink()


def main() -> int:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT)')

    layout = default_layout('service_receipt')
    layout['margin']['top'] = '9999'
    layout['grid']['columns'] = '4'
    layout['elements']['header']['font'] = 'not-a-number'
    cleaned = sanitize_layout('service_receipt', layout)
    assert cleaned['margin']['top'] == 40
    assert cleaned['grid']['columns'] == 4
    assert cleaned['elements']['header']['font'] == 10

    save_layout(conn, 'service_receipt', 7, cleaned)
    loaded = load_layout(conn, 'service_receipt', 7)
    assert loaded['grid']['columns'] == 4
    assert prepare_for_print(loaded)['elements']['header']['style'].startswith('display:')

    slips = [{'kind': 'receipt', 'row': {'id': index}} for index in range(9)]
    batch = build_slip_batch(slips, loaded)
    assert len(batch['pages']) == 2
    assert batch['pages'][0][0]['style'] != batch['pages'][0][1]['style']

    driver = sanitize_layout('service_drivers', {
        'orientation': 'portrait',
        'table': {'width': 999, 'scale_y': 9},
    })
    assert driver['orientation'] == 'portrait'
    assert driver['table']['width'] == 297
    assert driver['table']['show_teacher_names'] is True
    assert driver['table']['scale_y'] == 2.5
    assert 'transform:scaleY(2.5)' in prepare_for_print(driver)['table_style']
    print('✓ تنظیمات طراحی چاپ A4: sanitize، ذخیره، بازیابی و صفحه‌بندی موفق بود.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
