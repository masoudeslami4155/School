#!/usr/bin/env python
"""هم‌خوانی نسخه و سلامت مستندات را بدون تماس با دیتابیس بررسی می‌کند."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# فقط برای یافتن مسیر ریشه؛ ماژول برنامه import نمی‌شود تا هیچ فایلی ساخته نشود.
sys.path.insert(0, str(ROOT))

LATIN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')

ACTIVE_DOCS = (
    'README.md',
    'README_MODULAR_FA.md',
    'AGENTS.md',
    'AGENT_PROJECT_GUIDE.md',
    'CHANGELOG_FA.md',
    'PALETTE_SOURCES.md',
    'docs/INDEX.md',
)
ARCHIVE_DIR = ROOT / 'docs' / 'archive'
ARCHIVED_DOCS = (
    'AI_AGENT_459_FA.md',
    'AI_DOCUMENTS_460_FA.md',
    'AI_CHANGE_FIX_461_FA.md',
    'AI_DESIGN_462_FA.md',
    'STATISTICS_463_FA.md',
    'STUDENT_PRINT_464_FA.md',
    'PATCH_NOTES_FA.txt',
)

CHANGELOG = 'CHANGELOG_FA.md'
# سرتیتر بخش‌های تغییرات؛ هر نسخه باید دقیقاً یک بار و فقط در CHANGELOG بیاید.
VERSION_HEADING_RE = re.compile(r'^#{2,3} ۴\.(?:۵۵|۵۶|۵۷|۵۸|۵۹|۶۰|۶۱|۶۲|۶۳|۶۴) —', re.MULTILINE)
EXPECTED_VERSIONS = tuple(f'۴.{number}' for number in ('۵۵', '۵۶', '۵۷', '۵۸', '۵۹', '۶۰', '۶۱', '۶۲', '۶۳', '۶۴'))
LINK_RE = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
SKIP_LINK_PREFIXES = ('http://', 'https://', 'mailto:', '#', 'tel:')


def to_latin(value: str) -> str:
    return value.translate(LATIN_DIGITS)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def check_version_sync() -> int:
    config_text = read('config.py')
    match = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", config_text)
    assert match, 'APP_VERSION در config.py پیدا نشد.'
    app_version = to_latin(match.group(1)).strip()
    version_file = to_latin(read('VERSION.txt')).strip()
    assert re.fullmatch(r'\d+\.\d+', version_file), f'قالب VERSION.txt نامعتبر است: {version_file!r}'
    assert app_version == version_file, (
        f'واگرایی نسخه: config.APP_VERSION={app_version!r} اما VERSION.txt={version_file!r}'
    )
    return 1


def check_active_docs_exist() -> int:
    checks = 0
    for name in ACTIVE_DOCS:
        path = ROOT / name
        assert path.is_file(), f'سند فعال پیدا نشد: {name}'
        checks += 1
    for name in ARCHIVED_DOCS:
        path = ARCHIVE_DIR / name
        assert path.is_file(), f'سند بایگانی‌شده پیدا نشد: docs/archive/{name}'
        checks += 1
    return checks


def check_relative_links() -> int:
    checks = 0
    for name in ACTIVE_DOCS:
        path = ROOT / name
        text = path.read_text(encoding='utf-8')
        for target in LINK_RE.findall(text):
            if target.startswith(SKIP_LINK_PREFIXES):
                continue
            target = target.split('#', 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.exists(), f'پیوند شکسته در {name}: {target}'
            checks += 1
    return checks


def check_single_changelog() -> int:
    checks = 0
    for name in ACTIVE_DOCS:
        headings = VERSION_HEADING_RE.findall(read(name))
        if name == CHANGELOG:
            continue
        assert not headings, f'بخش تغییرات نسخه در {name} تکرار شده است؛ این بخش فقط در {CHANGELOG} می‌ماند.'
    changelog_text = read(CHANGELOG)
    for version in EXPECTED_VERSIONS:
        heading = re.search(rf'^#{{2,3}} {re.escape(version)} —', changelog_text, re.MULTILINE)
        assert heading, f'بخش نسخهٔ {version} در {CHANGELOG} وجود ندارد؛ هنگام ادغام حذف شده است.'
        checks += 1
    assert read(CHANGELOG).count('## ۴.۶۴ —') == 1, 'بخش ۴.۶۴ باید یک بار در CHANGELOG باشد.'
    checks += 1
    return checks


def main() -> int:
    checks = 0
    checks += check_version_sync()
    checks += check_active_docs_exist()
    checks += check_relative_links()
    checks += check_single_changelog()
    assert ARCHIVE_DIR.is_dir() and not (ROOT / 'PATCH_NOTES_FA.txt').exists(), (
        'یادداشت نسخه باید در docs/archive/ باشد و از ریشهٔ پروژه برداشته شود.'
    )
    checks += 1
    print(f'✓ مستندات و نسخه: {checks} بررسی موفق بود (نسخهٔ واحد، پیوند سالم، تغییرات در یک سند).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
